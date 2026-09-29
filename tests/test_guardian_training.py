"""Recurrent replay, policy learning, paired evaluation, and checkpoint isolation."""

import hashlib
import json
import math
import stat
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
from godfield_bot.guardian_rollout import GuardianRolloutArena, GuardianRolloutConfig  # noqa: E402
from godfield_bot.guardian_training import (  # noqa: E402
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
    with pytest.raises(GuardianTrainingError, match="paired"):
        evaluate_guardian_policy(model, **{**arguments, "games": 7})


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


def test_cli_trains_only_local_checkpoint_and_rejects_oversized_rollout(tmp_path, monkeypatch):
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
            ],
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.stdout)
        assert Path(report["checkpoint_directory"]).is_dir()
        assert report["manifest"]["local_training_eligible"]
        assert not report["manifest"]["promotion_eligible"]
        assert report["manifest"]["training"]["environment_minibatch_size"] == 2
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
