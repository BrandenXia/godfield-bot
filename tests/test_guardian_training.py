"""Recurrent replay, policy learning, paired evaluation, and checkpoint isolation."""

import hashlib
import json
import math
import stat
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.guardian_neural import (  # noqa: E402
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
    guardian_feature_tensors,
)
from godfield_bot.guardian_rollout import (  # noqa: E402
    GuardianObservation,
    GuardianRolloutArena,
    GuardianRolloutConfig,
    greedy_guardian_actions,
)
from godfield_bot.guardian_training import (  # noqa: E402
    DEFENSE_FEEDBACK_ALGORITHM,
    MANIFEST_FILE,
    WEIGHTS_FILE,
    GuardianDuelCollector,
    GuardianTrainingConfig,
    GuardianTrainingError,
    _runtime,
    evaluate_guardian_checkpoint,
    evaluate_guardian_policy,
    load_guardian_checkpoint,
    replay_guardian_rollout,
    train_guardian_candidate,
    train_guardian_ppo,
    train_guardian_teacher,
)
from godfield_bot.model_registry import load_model  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def config(**kwargs):
    return GuardianTrainingConfig(
        **{
            "arena": GuardianRolloutConfig(batch_size=4, max_turns=8, max_decisions=16),
            "hidden_size": 32,
            "embedding_size": 8,
            "rollout_steps": 16,
            "updates": 1,
            "teacher_updates": 1,
            "ppo_epochs": 1,
            "environment_minibatch_size": 2,
            "evaluation_games": 4,
            "cpu_threads": 1,
            **kwargs,
        }
    )


def arena(cfg):
    return GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena)


def policy(cfg):
    return GuardianArenaPolicy(
        GuardianPolicyArchitecture(
            vocabulary_size=297, hidden_size=cfg.hidden_size, embedding_size=cfg.embedding_size
        )
    )


@pytest.fixture
def runtime():
    with _runtime(67, 1):
        yield


@pytest.mark.parametrize(
    "bad",
    [
        {"arena": GuardianRolloutConfig(player_count=3)},
        {"arena": GuardianRolloutConfig(batch_size=1)},
        {"arena": GuardianRolloutConfig(batch_size=1024), "rollout_steps": 64},
        {"evaluation_games": 3},
        {"learning_rate": float("nan")},
        {"updates": True},
        {"cpu_threads": 0},
        {"defense_feedback_weight": -1},
        {"defense_feedback_weight": 5},
        {"defense_feedback_weight": float("nan")},
        {"defense_feedback_scope": "shield"},
    ],
)
def test_training_configuration_is_bounded_and_duel_only(bad):
    with pytest.raises(ValueError):
        config(**bad)


def test_policy_shapes_masks_and_numeric_selection_gradients(runtime):
    cfg = config()
    model = policy(cfg)
    obs = arena(cfg).observe()
    inputs = guardian_feature_tensors(obs)
    logits, values, states = model(*inputs)
    assert logits.shape == (4, 30) and values.shape == (4,) and states.shape == (4, 32)
    assert np.all(obs.action_mask[np.arange(4), logits.argmax(dim=-1).detach().numpy()])
    assert torch.all(logits[~inputs[-1]] == torch.finfo(torch.float32).min)
    changed = list(inputs)
    changed[4] = changed[4].clone()
    env = int(np.flatnonzero(obs.action_mask[:, 1:19].any(axis=1))[0])
    slot = int(np.flatnonzero(obs.action_mask[env, 1:19])[0])
    changed[4][env, slot, 6] = 1 - changed[4][env, slot, 6]
    other, _, _ = model(*changed)
    assert not torch.allclose(other[env, slot + 1], logits[env, slot + 1])
    (values.square().sum() + logits[inputs[-1]].sum()).backward()
    assert model.card_encoder[0].weight.grad is not None
    assert torch.any(model.card_encoder[0].weight.grad[:, -7:] != 0)
    terminal = list(inputs)
    terminal[-1] = torch.zeros_like(terminal[-1])
    with pytest.raises(ValueError, match="active legal"):
        model(*terminal)
    malformed = list(inputs)
    malformed[4] = malformed[4][:, :9]
    with pytest.raises(ValueError, match="shape"):
        model(*malformed)


def test_card_permutation_changes_only_corresponding_card_logits(runtime):
    cfg = config()
    model = policy(cfg)
    inputs = guardian_feature_tensors(arena(cfg).observe())
    permutation = torch.arange(18).flip(0)
    permuted = list(inputs)
    permuted[3], permuted[4], permuted[5] = (value[:, permutation] for value in inputs[3:6])
    permuted[6] = inputs[6].clone()
    permuted[6][:, 1:19] = inputs[6][:, 1:19][:, permutation]
    original, values, _ = model(*inputs)
    changed, changed_values, _ = model(*permuted)
    torch.testing.assert_close(changed[:, 1:19], original[:, 1:19][:, permutation])
    torch.testing.assert_close(changed[:, 19:], original[:, 19:])
    torch.testing.assert_close(changed[:, :1], original[:, :1])
    torch.testing.assert_close(changed_values, values)


def test_recurrent_rollouts_replay_exactly_across_update_boundaries(runtime):
    cfg = config(rollout_steps=4)
    model = policy(cfg)
    collector = GuardianDuelCollector(arena(cfg), model)
    for _ in range(3):
        rollout = collector.collect(cfg)
        logits, values = replay_guardian_rollout(model, rollout, torch.arange(4))
        actual = torch.distributions.Categorical(logits=logits).log_prob(rollout.actions)
        torch.testing.assert_close(actual, rollout.old_log_probabilities)
        torch.testing.assert_close(values, rollout.old_values)
        assert all(not tensor.requires_grad for tensor in rollout.observations)
        assert rollout.rewards.shape == rollout.returns.shape == (4, 4)
        assert sum(rollout.phase_counts) == 16
    assert torch.any(rollout.initial_states != 0)


def test_absorbing_truncations_reset_both_memories_and_do_not_bootstrap(runtime):
    cfg = config(arena=GuardianRolloutConfig(batch_size=4, max_turns=1, max_decisions=1))
    model = policy(cfg)
    collector = GuardianDuelCollector(arena(cfg), model)
    rollout = collector.collect(cfg)
    assert torch.all(rollout.done) and torch.all(rollout.starts)
    torch.testing.assert_close(rollout.returns, rollout.rewards)
    assert rollout.completed_games + rollout.truncated_games == 64
    assert collector.arena.observe().episode_ids.tolist() == [15] * 4
    collector.collect(cfg)
    assert collector.arena.observe().episode_ids.tolist() == [31] * 4


def test_teacher_update_learns_fixed_legal_labels_and_ppo_changes_weights(runtime):
    cfg = config()
    model = policy(cfg)
    collector = GuardianDuelCollector(arena(cfg), model)
    teacher = collector.collect(cfg, teacher=True)
    initial, _ = replay_guardian_rollout(model, teacher, torch.arange(4))
    initial_loss = torch.nn.functional.cross_entropy(
        initial.flatten(0, 1), teacher.actions.flatten()
    ).detach()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
    for _ in range(5):
        metric = train_guardian_teacher(model, optimizer, teacher, cfg)
        assert math.isfinite(metric.loss)
    final, _ = replay_guardian_rollout(model, teacher, torch.arange(4))
    final_loss = torch.nn.functional.cross_entropy(
        final.flatten(0, 1), teacher.actions.flatten()
    ).detach()
    assert final_loss < initial_loss
    rollout = collector.collect(cfg)
    assert torch.any(~rollout.policy_trainable) and torch.any(rollout.policy_trainable)
    before = {key: value.clone() for key, value in model.state_dict().items()}
    metrics = train_guardian_ppo(
        model, torch.optim.Adam(model.parameters(), lr=0.001), rollout, cfg
    )
    assert all(math.isfinite(value) for value in metrics.model_dump().values())
    assert any(not torch.equal(value, before[key]) for key, value in model.state_dict().items())
    assert all(torch.isfinite(value).all() for value in model.parameters())
    with pytest.raises(GuardianTrainingError, match="no learner"):
        train_guardian_ppo(
            model,
            optimizer,
            replace(rollout, policy_trainable=torch.zeros_like(rollout.policy_trainable)),
            cfg,
        )


def test_evaluation_paired_seats_is_reproducible_and_counts_all_attempts(runtime):
    cfg = config()
    model = policy(cfg)
    arguments = dict(
        catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena, games=8, seed=1000070
    )
    a, b = (
        evaluate_guardian_policy(model, **arguments),
        evaluate_guardian_policy(model, **arguments),
    )
    assert a == b
    assert a.wins + a.losses + a.truncations == 8
    assert a.win_fraction_all_games == a.wins / 8
    assert sum(a.wins_by_learner_seat) == a.wins
    for seat in (0, 1):
        assert (
            a.wins_by_learner_seat[seat]
            + a.losses_by_learner_seat[seat]
            + a.truncations_by_learner_seat[seat]
            == 4
        )
    assert not a.promotion_eligible
    assert sum(a.truncation_causes.model_dump().values()) == a.truncations
    reference = evaluate_guardian_policy(None, **arguments)
    assert reference.policy_kind == "greedy-reference"
    assert reference.wins == reference.losses
    assert reference.truncation_causes.defense_selection_limit == 0
    assert reference.defense_deselections == 0
    with pytest.raises(GuardianTrainingError, match="paired"):
        evaluate_guardian_policy(model, **{**arguments, "games": 7})


def test_feedback_labels_are_visible_legal_and_do_not_override_sampled_play():
    cfg = config(teacher_updates=0)
    feedback_cfg = cfg.model_copy(update={"defense_feedback_weight": 1})
    with _runtime(67, 1):
        original = GuardianDuelCollector(arena(cfg), policy(cfg)).collect(cfg)
    with _runtime(67, 1):
        labeled = GuardianDuelCollector(arena(feedback_cfg), policy(feedback_cfg)).collect(
            feedback_cfg
        )
    assert original.defense_teacher_actions is None
    assert labeled.defense_teacher_actions is not None
    for attribute in (
        "actors",
        "actions",
        "starts",
        "initial_states",
        "policy_trainable",
        "old_log_probabilities",
        "old_values",
        "rewards",
        "done",
        "advantages",
        "returns",
    ):
        torch.testing.assert_close(getattr(original, attribute), getattr(labeled, attribute))
    for left, right in zip(original.observations, labeled.observations, strict=True):
        torch.testing.assert_close(left, right)
    labels = labeled.defense_teacher_actions
    assert bool(labeled.observations[6].gather(-1, labels.unsqueeze(-1)).all())
    mask = labeled.policy_trainable & (labeled.observations[0][:, :, 1] > 0)
    assert bool((labeled.actions[mask] != labels[mask]).any())
    for tick in range(labeled.steps):
        # Reconstruct solely from the seven stored policy projections; no world
        # inventory or extra teacher-only state is needed to reproduce labels.
        observation = GuardianObservation(
            *(value[tick].numpy() for value in labeled.observations),
            labeled.actors[tick].numpy(),
            labeled.observations[0][tick, :, :6].argmax(-1).numpy(),
            np.zeros(labeled.batch_size, dtype=np.int64),
            np.full(labeled.batch_size, tick, dtype=np.int64),
            np.ones(labeled.batch_size, dtype=np.bool_),
        )
        np.testing.assert_array_equal(greedy_guardian_actions(observation), labels[tick].numpy())


def test_feedback_loss_teaches_learner_defense_without_reward_changes(runtime):
    cfg = config(
        defense_feedback_weight=1,
        value_weight=0,
        entropy_weight=0,
        environment_minibatch_size=4,
        teacher_selected_defense_weight=1,
    )
    model = policy(cfg)
    collected = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    rollout = replace(collected, advantages=torch.zeros_like(collected.advantages))
    mask = rollout.policy_trainable & (rollout.observations[0][:, :, 1] > 0)
    labels = rollout.defense_teacher_actions
    assert labels is not None and mask.any()
    initial, _ = replay_guardian_rollout(model, rollout, torch.arange(4))
    initial_loss = torch.nn.functional.cross_entropy(initial[mask], labels[mask]).detach()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
    for _ in range(5):
        metrics = train_guardian_ppo(model, optimizer, rollout, cfg)
        assert metrics.defense_teacher_samples == int(mask.sum()) * cfg.ppo_epochs
        assert metrics.defense_teacher_loss > 0
        assert 0 <= metrics.defense_teacher_accuracy <= 1
    final, _ = replay_guardian_rollout(model, rollout, torch.arange(4))
    assert torch.nn.functional.cross_entropy(final[mask], labels[mask]).detach() < initial_loss
    torch.testing.assert_close(rollout.rewards, collected.rewards)
    torch.testing.assert_close(rollout.actions, collected.actions)


def test_baseline_teacher_labels_do_not_affect_feedback_gradients(runtime):
    cfg = config(defense_feedback_weight=1)
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    assert rollout.defense_teacher_actions is not None
    labels = rollout.defense_teacher_actions.clone()
    excluded = ~rollout.policy_trainable
    assert excluded.any()
    labels[excluded] = rollout.actions[excluded]  # different but still legal labels
    changed = replace(rollout, defense_teacher_actions=labels)
    first, second = deepcopy(model), deepcopy(model)
    with _runtime(778, 1):
        a = train_guardian_ppo(first, torch.optim.Adam(first.parameters(), lr=0.001), rollout, cfg)
    with _runtime(778, 1):
        b = train_guardian_ppo(
            second, torch.optim.Adam(second.parameters(), lr=0.001), changed, cfg
        )
    assert a == b
    for name, weight in first.state_dict().items():
        torch.testing.assert_close(weight, second.state_dict()[name])


@pytest.mark.parametrize("mutation", ["missing", "shape", "dtype", "range", "illegal"])
def test_feedback_requires_legal_observed_labels_before_optimization(runtime, mutation):
    cfg = config(defense_feedback_weight=1)
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    assert rollout.defense_teacher_actions is not None
    labels = rollout.defense_teacher_actions.clone()
    if mutation == "missing":
        labels = None
    elif mutation == "shape":
        labels = labels[:-1]
    elif mutation == "dtype":
        labels = labels.to(torch.float32)
    elif mutation == "range":
        labels[0, 0] = 30
    else:
        tick, env, action = (~rollout.observations[6]).nonzero()[0]
        labels[tick, env] = action
    before = deepcopy(model.state_dict())
    with pytest.raises(GuardianTrainingError, match="legal observed-state labels"):
        train_guardian_ppo(
            model,
            torch.optim.Adam(model.parameters()),
            replace(rollout, defense_teacher_actions=labels),
            cfg,
        )
    for name, value in before.items():
        torch.testing.assert_close(value, model.state_dict()[name])


def test_feedback_with_no_learner_defense_samples_is_finite(runtime):
    cfg = config(defense_feedback_weight=1)
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    trainable = rollout.policy_trainable & (rollout.observations[0][:, :, 1] == 0)
    assert trainable.any()
    metric = train_guardian_ppo(
        model,
        torch.optim.Adam(model.parameters()),
        replace(rollout, policy_trainable=trainable),
        cfg,
    )
    assert metric.defense_teacher_samples == metric.defense_teacher_loss == 0
    assert all(math.isfinite(value) for value in metric.model_dump().values())


@pytest.mark.parametrize("scope", ["all-defense", "finish-decisions"])
def test_feedback_scope_counts_only_the_requested_learner_states(runtime, scope):
    cfg = config(defense_feedback_weight=1, defense_feedback_scope=scope)
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    labels = rollout.defense_teacher_actions
    assert labels is not None
    eligible = rollout.policy_trainable & (rollout.observations[0][:, :, 1] > 0)
    if scope == "finish-decisions":
        eligible &= labels >= 28
    metric = train_guardian_ppo(model, torch.optim.Adam(model.parameters()), rollout, cfg)
    assert metric.defense_teacher_samples == int(eligible.sum()) * cfg.ppo_epochs


def test_evaluation_reports_deselections_instead_of_hiding_loops(runtime, monkeypatch):
    import godfield_bot.guardian_training as module

    original_constructor = GuardianRolloutArena

    def prepared(**kwargs):
        game = original_constructor(**kwargs)
        envs = np.arange(game.config.batch_size, dtype=np.int64)
        zeros, ones = np.zeros_like(envs), np.ones_like(envs)
        game._native.reset_environments(envs)
        game._native.deal_cards(envs, zeros, zeros, ones, np.full_like(envs, 6))
        game._native.deal_cards(envs, ones, zeros, np.full_like(envs, 2), np.full_like(envs, 113))
        game._native.begin_card_attacks(envs, zeros, zeros, ones)
        return game

    monkeypatch.setattr(module, "GuardianRolloutArena", prepared)
    cfg = config(arena=GuardianRolloutConfig(batch_size=4, max_turns=8, max_decisions=128))
    model = policy(cfg)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()  # ties pick the first legal slot, repeatedly toggling it
    evaluated = evaluate_guardian_policy(
        model, catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena, games=2, seed=67
    )
    assert evaluated.defense_deselections == 32
    assert evaluated.truncation_causes.defense_selection_limit == 1
    assert not evaluated.promotion_eligible


@pytest.mark.parametrize(
    "mutation", ["missing-metrics", "algorithm", "sample-count", "disabled-config"]
)
def test_feedback_checkpoint_records_algorithm_metrics_and_preserves_old_parent(
    checkpoint, tmp_path, mutation
):
    source, parent = checkpoint
    original = (source / WEIGHTS_FILE).read_bytes()
    cfg = config(teacher_updates=0, defense_feedback_weight=1)
    directory, saved = train_guardian_candidate(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        checkpoint_root=tmp_path / "feedback",
        config=cfg,
        resume=source,
    )
    loaded, _ = load_guardian_checkpoint(directory)
    assert loaded == saved and saved.algorithm == DEFENSE_FEEDBACK_ALGORITHM
    assert saved.parent_weights_sha256 == parent.weights_sha256
    assert saved.update_metrics[0].ppo.defense_teacher_samples > 0
    assert not saved.promotion_eligible and not saved.live_checkpoint_compatible
    assert (source / WEIGHTS_FILE).read_bytes() == original
    record = json.loads((directory / MANIFEST_FILE).read_text())
    if mutation == "missing-metrics":
        del record["update_metrics"][0]["ppo"]["defense_teacher_samples"]
    elif mutation == "algorithm":
        record["algorithm"] = "provisional-guardian-duel-recurrent-imitation-ppo-v1"
    elif mutation == "sample-count":
        record["update_metrics"][0]["ppo"]["defense_teacher_samples"] = 999999
    else:
        record["training"]["defense_feedback_weight"] = 0
    (directory / MANIFEST_FILE).write_text(json.dumps(record))
    with pytest.raises(ValueError):
        load_guardian_checkpoint(directory)


def test_historical_feedback_measurements_remain_unknown_and_default_is_disabled(checkpoint):
    directory, _ = checkpoint
    record = json.loads((directory / MANIFEST_FILE).read_text())
    del record["training"]["defense_feedback_weight"]
    del record["training"]["defense_feedback_scope"]
    for update in record["update_metrics"]:
        for key in ("defense_teacher_loss", "defense_teacher_accuracy", "defense_teacher_samples"):
            del update["ppo"][key]
    for key in ("evaluation_before", "evaluation_after", "evaluation_baseline"):
        del record[key]["defense_deselections"]
    (directory / MANIFEST_FILE).write_text(json.dumps(record))
    loaded, _ = load_guardian_checkpoint(directory)
    assert loaded.training.defense_feedback_weight == 0
    assert loaded.training.defense_feedback_scope == "all-defense"
    assert loaded.update_metrics[0].ppo.defense_teacher_samples is None
    assert loaded.evaluation_after.defense_deselections is None


@pytest.fixture
def checkpoint(tmp_path):
    return train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "arena", config=config()
    )


def test_checkpoint_private_checked_and_incompatible_with_live_registry(checkpoint):
    directory, saved = checkpoint
    manifest, model = load_guardian_checkpoint(directory)
    assert manifest == saved
    assert manifest.local_training_eligible
    assert not manifest.full_game_training_ready and not manifest.promotion_eligible
    assert not manifest.live_checkpoint_compatible
    assert len(manifest.teacher_metrics) == len(manifest.update_metrics) == 1
    assert manifest.architecture.vocabulary_size == 297
    assert manifest.evaluation_after.games == 4
    assert manifest.evaluation_baseline is not None
    assert manifest.evaluation_baseline.policy_kind == "greedy-reference"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / WEIGHTS_FILE).stat().st_mode) == 0o600
    assert stat.S_IMODE((directory / MANIFEST_FILE).stat().st_mode) == 0o600
    assert (
        hashlib.sha256((directory / WEIGHTS_FILE).read_bytes()).hexdigest()
        == manifest.weights_sha256
    )
    assert not (directory / "manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        load_model(directory)
    assert all(torch.isfinite(value).all() for value in model.parameters())


def test_seeded_training_reproduces_weights_and_restores_global_rng(checkpoint, tmp_path):
    first, manifest = checkpoint
    old_rng, old_threads = torch.random.get_rng_state().clone(), torch.get_num_threads()
    second, repeated = train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "repeat", config=config()
    )
    torch.testing.assert_close(torch.random.get_rng_state(), old_rng)
    assert torch.get_num_threads() == old_threads
    assert repeated.rollout_sha256 == manifest.rollout_sha256
    assert repeated.weights_sha256 == manifest.weights_sha256
    assert repeated.update_metrics == manifest.update_metrics
    assert first != second


def test_resume_is_source_checked_cold_optimizer_and_never_overwrites(checkpoint, tmp_path):
    source, parent = checkpoint
    original = (source / WEIGHTS_FILE).read_bytes()
    destination, child = train_guardian_candidate(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        checkpoint_root=tmp_path / "children",
        config=config(teacher_updates=0),
        resume=source,
    )
    assert destination != source
    assert child.parent_weights_sha256 == parent.weights_sha256 and not child.optimizer_resumed
    assert (source / WEIGHTS_FILE).read_bytes() == original
    with pytest.raises(GuardianTrainingError, match="configuration differs"):
        train_guardian_candidate(
            catalog_path=CATALOG,
            bible_path=BIBLE,
            checkpoint_root=tmp_path / "rejected",
            config=config(arena=GuardianRolloutConfig(batch_size=4, max_turns=8, max_decisions=17)),
            resume=source,
        )
    assert not (tmp_path / "rejected").exists()


def test_no_redraw_checkpoint_cannot_silently_resume_with_provisional_refills(checkpoint, tmp_path):
    source, _ = checkpoint
    with pytest.raises(GuardianTrainingError, match="curriculum/reward configuration differs"):
        train_guardian_candidate(
            catalog_path=CATALOG,
            bible_path=BIBLE,
            checkpoint_root=tmp_path / "rejected-refill",
            config=config(
                arena=GuardianRolloutConfig(
                    batch_size=4, max_turns=8, max_decisions=16, refill="weighted-consumption-v1"
                )
            ),
            resume=source,
        )
    assert not (tmp_path / "rejected-refill").exists()


def test_refill_learning_saves_explicit_contract_and_rejects_no_redraw_resume(tmp_path):
    cfg = config(
        arena=GuardianRolloutConfig(
            batch_size=4, max_turns=8, max_decisions=16, refill="weighted-consumption-v1"
        )
    )
    directory, saved = train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "refill", config=cfg
    )
    loaded, _ = load_guardian_checkpoint(directory)
    assert loaded == saved
    assert saved.arena.refill_plan is not None
    assert saved.arena.curriculum_id == "synthetic-guardian-weighted-refill-provisional-v1"
    assert saved.evaluation_baseline.replacement_gifts > 0
    assert saved.update_metrics[0].replacement_gifts is not None
    assert not saved.full_game_training_ready and not saved.promotion_eligible
    evaluated = evaluate_guardian_checkpoint(
        directory, catalog_path=CATALOG, bible_path=BIBLE, games=4, seed=93, cpu_threads=1
    )
    assert evaluated.replacement_gifts is not None
    with pytest.raises(GuardianTrainingError, match="curriculum/reward configuration differs"):
        train_guardian_candidate(
            catalog_path=CATALOG,
            bible_path=BIBLE,
            checkpoint_root=tmp_path / "rejected-no-refill",
            config=config(),
            resume=directory,
        )
    assert not (tmp_path / "rejected-no-refill").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "checksum",
        "identity",
        "promotion",
        "missing-update",
        "decision-count",
        "evaluation-count",
        "nonfinite",
    ],
)
def test_tampered_checkpoint_fails_closed(checkpoint, mutation):
    directory, _ = checkpoint
    path = directory / MANIFEST_FILE
    record = json.loads(path.read_text())
    if mutation == "checksum":
        record["weights_sha256"] = "0" * 64
    elif mutation == "identity":
        del record["observation_schema_id"]
    elif mutation == "promotion":
        record["promotion_eligible"] = True
    elif mutation == "missing-update":
        record["update_metrics"] = []
    elif mutation == "decision-count":
        record["update_metrics"][0]["learner_decisions"] += 1
    elif mutation == "evaluation-count":
        record["evaluation_after"]["truncations"] += 1
    else:
        record["update_metrics"][0]["ppo"]["total_loss"] = float("nan")
    path.write_text(json.dumps(record))
    with pytest.raises((ValueError, GuardianTrainingError)):
        load_guardian_checkpoint(directory)


def test_selected_defense_weighting_keeps_subgroup_metrics_visible(runtime):
    cfg = config(teacher_selected_defense_weight=8)
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg, teacher=True)
    metrics = train_guardian_teacher(
        model, torch.optim.Adam(model.parameters(), lr=0.001), rollout, cfg
    )
    assert metrics.selected_defense_samples is not None
    assert metrics.selected_defense_samples > 0
    assert metrics.selected_defense_accuracy is not None
    assert 0 <= metrics.selected_defense_accuracy <= 1


@pytest.mark.parametrize("refill", ["none", "weighted-consumption-v1"])
def test_cli_trains_only_local_checkpoint_and_rejects_oversized_rollout(
    tmp_path, monkeypatch, refill
):
    from structlog.testing import capture_logs

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    with capture_logs():
        result = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--checkpoint-root",
                str(tmp_path / "cli"),
                "--batch-size",
                "2",
                "--rollout-steps",
                "2",
                "--updates",
                "1",
                "--teacher-updates",
                "0",
                "--ppo-epochs",
                "1",
                "--evaluation-games",
                "2",
                "--max-turns",
                "4",
                "--max-decisions",
                "4",
                "--hidden-size",
                "32",
                "--embedding-size",
                "8",
                "--cpu-threads",
                "1",
                "--refill",
                refill,
                "--defense-feedback-weight",
                "1" if refill != "none" else "0",
                "--defense-feedback-scope",
                "finish-decisions",
            ],
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.stdout)
        assert Path(report["checkpoint_directory"]).is_dir()
        assert report["manifest"]["local_training_eligible"]
        assert not report["manifest"]["promotion_eligible"]
        assert report["manifest"]["training"]["environment_minibatch_size"] == 2
        assert report["manifest"]["arena"]["config"]["refill"] == refill
        if refill != "none":
            assert report["manifest"]["algorithm"] == DEFENSE_FEEDBACK_ALGORITHM
        before = Path(report["checkpoint_directory"], WEIGHTS_FILE).read_bytes()
        evaluated = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-evaluate",
                "--checkpoint",
                report["checkpoint_directory"],
                "--games",
                "2",
                "--seed",
                "99",
                "--cpu-threads",
                "1",
            ],
        )
        assert evaluated.exit_code == 0, evaluated.output
        evaluation = json.loads(evaluated.stdout)
        assert evaluation["games"] == 2 and evaluation["seed"] == 99
        assert Path(report["checkpoint_directory"], WEIGHTS_FILE).read_bytes() == before
        invalid = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--checkpoint-root",
                str(tmp_path / "bad"),
                "--batch-size",
                "4096",
                "--rollout-steps",
                "256",
            ],
        )
        assert invalid.exit_code == 1
        assert not (tmp_path / "bad").exists()


def test_checkpoint_evaluation_checks_source_pins_before_inference(checkpoint, monkeypatch):
    directory, _ = checkpoint
    import godfield_bot.guardian_training as module

    original = module.GuardianRolloutArena

    def changed_source(**kwargs):
        created = original(**kwargs)
        created.metadata.native.catalog_sha256 = "0" * 64
        return created

    monkeypatch.setattr(module, "GuardianRolloutArena", changed_source)
    with pytest.raises(GuardianTrainingError, match="source pins"):
        evaluate_guardian_checkpoint(
            directory, catalog_path=CATALOG, bible_path=BIBLE, games=2, seed=99
        )
