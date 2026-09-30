"""Isolated 48-action rollout, explicit checkpoint transfer, and closed gates."""

import hashlib
import json
import stat
from dataclasses import fields
from pathlib import Path

import pytest
from typer.testing import CliRunner

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.guardian_neural import (  # noqa: E402
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
    guardian_feature_tensors,
    migrate_guardian_discard_policy,
)
from godfield_bot.guardian_rollout import (  # noqa: E402
    DISCARD_OBSERVATION_ID,
    GuardianRolloutArena,
    GuardianRolloutConfig,
    GuardianRolloutMetadata,
    collect_guardian_rollout,
    greedy_guardian_actions,
)
from godfield_bot.guardian_training import (  # noqa: E402
    GuardianArenaManifest,
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
)
from godfield_bot.model_registry import load_model  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values):
    return np.ascontiguousarray(values, dtype=np.int64)


def cfg(*, discards=True, **kwargs):
    return GuardianRolloutConfig.model_validate(
        {
            "batch_size": 4,
            "max_turns": 8,
            "max_decisions": 32,
            "inventory_utilities": True,
            "inventory_discards": discards,
            "refill": "weighted-discard-consumption-v1"
            if discards
            else "weighted-utility-consumption-v1",
            "opening": "cards-only",
            **kwargs,
        }
    )


def arena(**kwargs):
    return GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg(**kwargs))


def arch(*, discards=True, **kwargs):
    return GuardianPolicyArchitecture.model_validate(
        {
            "vocabulary_size": 297,
            "hidden_size": 32,
            "embedding_size": 8,
            "hand_feature_count": 9,
            "action_count": 48 if discards else 30,
            "observation_schema_id": DISCARD_OBSERVATION_ID
            if discards
            else "actor-relative-guardian-utility-arena-v2",
            **kwargs,
        }
    )


def train_cfg(*, discards=True):
    return GuardianTrainingConfig(
        arena=cfg(discards=discards),
        hidden_size=32,
        embedding_size=8,
        rollout_steps=16,
        teacher_updates=1,
        updates=1,
        ppo_epochs=1,
        environment_minibatch_size=2,
        evaluation_games=4,
        cpu_threads=1,
        defense_feedback_weight=1,
    )


def train(root, config, **kwargs):
    return train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=root, config=config, **kwargs
    )


def prepare(game, hands):
    game._native.reset_environments(ids(range(game.config.batch_size)))
    for env in range(game.config.batch_size):
        for player, models in enumerate(hands):
            count = len(models)
            game._native.deal_cards(
                ids([env] * count),
                ids([player] * count),
                ids(range(count)),
                ids(range(100 + 18 * player, 100 + 18 * player + count)),
                ids(models),
            )


@pytest.mark.parametrize("players", [2, 3, 9])
def test_visible_projection_masks_and_original_controls(players):
    game = arena(player_count=players)
    obs = game.observe()
    assert obs.action_mask.shape == (4, 48) and obs.hand_features.shape == (4, 18, 9)
    assert game.metadata.schema_version == 3 and game.metadata.action_count == 48
    assert not game.metadata.full_game_training_ready and not game.metadata.promotion_eligible
    native = game._native.actor_hand_snapshot()
    expected = np.isin(native[:, :, 1], game.metadata.native.discard_plan.discard_model_ids)
    np.testing.assert_array_equal(obs.action_mask[:, 30:], expected)
    for field in fields(obs):
        assert not getattr(obs, field.name).flags.writeable
    game._native.deal_cards(ids([0]), ids([1]), ids([17]), ids([999]), ids([194]))
    for field in fields(obs):
        np.testing.assert_array_equal(getattr(obs, field.name), getattr(game.observe(), field.name))
    # Target selection and pending defense disable discard, without moving old action IDs.
    prepare(game, [[0 + game.metadata.base_native.attack_weapon_model_ids[0]], [113]])
    game.step(ids([1] * 4))
    assert not game.observe().action_mask[:, 30:].any()
    game.step(ids([20] * 4))
    assert not game.observe().action_mask[:, 30:].any()
    assert game.observe().action_mask[:, 28:30].shape == (4, 2)


def test_discard_one_turn_no_cost_same_slot_refill_and_separate_counters():
    game = arena(initial_mp=0)
    prepare(game, [[113, 235], [235]])
    game._refill_models, game._refill_cumulative = ids([197]), ids([1])
    old = game._native.resource_snapshot().copy()
    result = game.step(ids([30] * 4))
    np.testing.assert_array_equal(game._native.resource_snapshot(), old)
    assert result.observation.actors.tolist() == [1] * 4
    assert game.discarded_cards == game.replacement_gifts == 4
    assert game._native.consumed_card_count == game._native.miracle_cast_count == 0
    assert game.utility_statistics.uses == 0
    inventory = game._native.inventory_snapshot()
    assert np.all(inventory[:, 0, 0, 1] == 197) and np.all(inventory[:, 0, 1, 1] == 235)
    game.step(ids([0] * 4))
    game.step(ids([1] * 4))
    assert game.utility_statistics.mp_gained == 60 and game.discarded_cards == 4
    assert game.replacement_gifts == 8
    np.testing.assert_allclose(result.rewards.sum(axis=1), 0, atol=1e-7)


@pytest.mark.parametrize("boundary", [{"max_turns": 1}, {"max_decisions": 1}])
def test_atomic_illegal_last_row_and_terminal_drops_without_rng_draw(boundary):
    game = arena(initial_mp=0, **boundary)
    prepare(game, [[113, 235], [235]])
    before = game._native.inventory_snapshot().copy()
    random_before = [
        json.dumps(game._refill_rngs[i].bit_generator.state, sort_keys=True) for i in range(4)
    ]
    with pytest.raises(ValueError, match="batch was not changed"):
        game.step(ids([30, 30, 30, 47]))
    np.testing.assert_array_equal(before, game._native.inventory_snapshot())
    assert game.discarded_cards == game.replacement_gifts == 0
    ended = game.step(ids([30] * 4))
    assert ended.truncated.all() and not ended.observation.action_mask.any()
    assert game.discarded_cards == 4 and game.replacement_gifts == 0
    assert random_before == [
        json.dumps(game._refill_rngs[i].bit_generator.state, sort_keys=True) for i in range(4)
    ]
    assert not any(game._pending_refills)


def test_padded_last_slot_and_discarded_miracle_never_cast_or_spend_mp():
    game = arena(initial_mp=0)
    prepare(game, [[235], [235]])
    game._native.deal_cards(
        ids(range(4)), ids([0] * 4), ids([17] * 4), ids([999] * 4), ids([233] * 4)
    )
    game._refill_models, game._refill_cumulative = ids([197]), ids([1])
    assert game.observe().action_mask[:, 47].all()
    game.step(ids([47] * 4))
    assert np.all(game._native.inventory_snapshot()[:, 0, 17, 1] == 197)
    assert game.discarded_cards == 4 and game.replacement_gifts == 4
    assert game._native.miracle_cast_count == game._native.mp_spent == 0
    assert game.utility_statistics.uses == 0
    assert np.all(game._native.resource_snapshot()[:, :, 1] == 0)


def test_recovery_only_teacher_and_independent_reproducible_stream():
    game = arena(initial_mp=0)
    prepare(game, [[113, 235], [235]])
    assert np.all(greedy_guardian_actions(game.observe()) >= 30)
    prepare(game, [[191, 235], [235]])
    assert greedy_guardian_actions(game.observe()).tolist() == [1] * 4
    old = arena(discards=False)
    new = arena()
    np.testing.assert_array_equal(old.observe().hand_model_ids, new.observe().hand_model_ids)
    assert old._refill_rngs[0].bit_generator.state != new._refill_rngs[0].bit_generator.state
    left = collect_guardian_rollout(arena(), steps=128)
    right = collect_guardian_rollout(arena(), steps=128)
    assert left == right and len(left.actions_by_index) == 48
    assert sum(left.actions_by_index[30:]) == left.discarded_cards


@pytest.mark.parametrize(
    "change",
    [
        {"inventory_utilities": False},
        {"inventory_discards": False},
        {"refill": "none"},
        {"refill": "weighted-utility-consumption-v1"},
    ],
)
def test_separate_config_rejects_implicit_rule_change(change):
    with pytest.raises(ValueError, match="discard requires"):
        cfg(**change)


@pytest.mark.parametrize(
    "field,value",
    [
        ("action_count", 30),
        ("schema_version", 2),
        ("observation_schema_id", "actor-relative-guardian-utility-arena-v2"),
        ("action_layout", ("0:pass",)),
    ],
)
def test_metadata_rejects_mixed_layout(field, value):
    data = arena().metadata.model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        GuardianRolloutMetadata.model_validate(data)


def test_migration_preserves_source_and_masked_logits_values_and_memory():
    with _runtime(67, 1):
        old = GuardianArenaPolicy(arch(discards=False))
        snapshots = {name: value.clone() for name, value in old.state_dict().items()}
        new = migrate_guardian_discard_policy(old, arch())
        assert old.discard_head is None and new.discard_head is not None
        for name, value in snapshots.items():
            torch.testing.assert_close(old.state_dict()[name], value, rtol=0, atol=0)
            torch.testing.assert_close(new.state_dict()[name], value, rtol=0, atol=0)
        game = arena(discards=False)
        left_state = torch.randn(4, 2, 32)
        right_state = left_state.clone()
        for _ in range(32):
            ended = ~game.observe().active
            left_state[ended] = right_state[ended] = 0
            obs = game.reset_done()
            features = guardian_feature_tensors(obs)
            wide = list(features)
            wide[-1] = torch.cat((features[-1], torch.zeros(4, 18, dtype=torch.bool)), dim=1)
            actors = torch.from_numpy(obs.actors.copy())
            rows = torch.arange(4)
            with torch.no_grad():
                left = old(*features, recurrent_state=left_state[rows, actors])
                right = new(*wide, recurrent_state=right_state[rows, actors])
            torch.testing.assert_close(left[0], right[0][:, :30], rtol=0, atol=0)
            for a, b in zip(left[1:], right[1:], strict=True):
                torch.testing.assert_close(a, b, rtol=0, atol=0)
            left_state[rows, actors], right_state[rows, actors] = left[2], right[2]
            game.step(greedy_guardian_actions(obs))


@pytest.mark.parametrize(
    "change", [{"hidden_size": 64}, {"vocabulary_size": 298}, {"embedding_size": 16}]
)
def test_transfer_rejects_other_architectural_changes(change):
    with pytest.raises(ValueError, match="30→48"):
        migrate_guardian_discard_policy(GuardianArenaPolicy(arch(discards=False)), arch(**change))


def test_transfer_refuses_nonfinite_parent_without_mutation():
    model = GuardianArenaPolicy(arch(discards=False))
    with torch.no_grad():
        model.value_head.bias.fill_(float("nan"))
    with pytest.raises(ValueError, match="non-finite"):
        migrate_guardian_discard_policy(model, arch())
    assert torch.isnan(model.value_head.bias).all() and model.discard_head is None


def test_recurrent_replay_and_discard_head_gradient():
    with _runtime(67, 1):
        config = train_cfg()
        model = GuardianArenaPolicy(arch())
        game = arena(initial_mp=0)
        prepare(game, [[113, 235], [235]])
        config = config.model_copy(update={"arena": game.config})
        rollout = GuardianDuelCollector(game, model).collect(config)
        logits, values = replay_guardian_rollout(model, rollout, torch.arange(4))
        actual = torch.distributions.Categorical(logits=logits).log_prob(rollout.actions)
        torch.testing.assert_close(actual, rollout.old_log_probabilities, rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(values, rollout.old_values, rtol=1e-5, atol=1e-6)
        assert logits.shape[-1] == 48 and rollout.discarded_cards > 0
        assert not rollout.policy_trainable.all()
        train_guardian_ppo(model, torch.optim.Adam(model.parameters()), rollout, config)
        assert model.discard_head[2].weight.grad.abs().sum() > 0


@pytest.fixture
def source(tmp_path):
    return train(tmp_path / "source", train_cfg(discards=False))


def test_private_child_save_load_readonly_evaluation_and_strict_resume(source, tmp_path):
    parent_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source[0].iterdir()}
    directory, manifest = train(tmp_path / "child", train_cfg(), migrate_discards_from=source[0])
    assert manifest.schema_version == 3 and manifest.discard_migration is not None
    assert manifest.parent_weights_sha256 == source[1].weights_sha256
    assert manifest.discard_migration.source_model_id == source[1].model_id
    loaded, model = load_guardian_checkpoint(directory)
    assert loaded == manifest and model.architecture.action_count == 48
    assert not manifest.live_checkpoint_compatible and not manifest.promotion_eligible
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / "arena-weights.pt").stat().st_mode) == 0o600
    with pytest.raises(FileNotFoundError):
        load_model(directory)
    assert parent_files == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source[0].iterdir()
    }
    result = evaluate_guardian_checkpoint(
        directory, catalog_path=CATALOG, bible_path=BIBLE, games=4, seed=900, cpu_threads=1
    )
    assert result.discarded_cards == result.play_statistics.ready_actions.discards
    train(tmp_path / "resume", train_cfg(), resume=directory)
    with pytest.raises(GuardianTrainingError):
        train(tmp_path / "wrong", train_cfg(), resume=source[0])
    for field in ("max_turns", "max_decisions", "initial_mp"):
        changed = train_cfg().model_copy(
            update={"arena": cfg(**{field: getattr(cfg(), field) + 1})}
        )
        with pytest.raises(GuardianTrainingError):
            train(tmp_path / "wrong", changed, migrate_discards_from=source[0])
    data = manifest.model_dump()
    data["discard_migration"]["source_weights_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)
    with pytest.raises(GuardianTrainingError, match="only one"):
        train(tmp_path / "wrong", train_cfg(), resume=directory, migrate_discards_from=source[0])


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-discard-count",
        "count-over-budget",
        "missing-evaluation-count",
        "wrong-opponent",
        "source-bound",
        "source-native",
        "source-observation",
        "refill-rng",
        "refill-profile",
        "live-gate",
        "played-count",
    ],
)
def test_tampered_discard_contract_fails_closed(source, tmp_path, mutation):
    _, manifest = train(tmp_path / "child", train_cfg(), migrate_discards_from=source[0])
    data = manifest.model_dump()
    if mutation == "missing-discard-count":
        data["update_metrics"][0]["discarded_cards"] = None
    elif mutation == "count-over-budget":
        data["teacher_metrics"][0]["discarded_cards"] = 1000000
    elif mutation == "missing-evaluation-count":
        data["evaluation_after"]["discarded_cards"] = None
    elif mutation == "wrong-opponent":
        data["evaluation_after"]["opponent"] = "greedy-utility-smoke-baseline-v2"
    elif mutation == "source-bound":
        data["discard_migration"]["source_arena"]["config"]["max_turns"] += 1
    elif mutation == "source-native":
        data["discard_migration"]["source_arena"]["native"]["initial_mp"] += 1
    elif mutation == "source-observation":
        data["discard_migration"]["source_arena"]["global_fields"] = ("different",)
    elif mutation == "refill-rng":
        data["arena"]["refill_plan"]["random_stream"] = "seed-environment-episode-channel-6772-v1"
    elif mutation == "refill-profile":
        data["arena"]["refill_plan"]["distribution_base"]["model_weights"] = ((1, 277),)
    elif mutation == "live-gate":
        data["live_checkpoint_compatible"] = True
    else:
        data["evaluation_after"]["discarded_cards"] += 1
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)


def test_evaluation_accounts_for_every_discard():
    with _runtime(67, 1):
        result = evaluate_guardian_policy(
            None,
            catalog_path=CATALOG,
            bible_path=BIBLE,
            config=cfg(max_turns=128, max_decisions=512),
            games=8,
            seed=1000070,
        )
    assert result.discarded_cards > 0
    assert result.discarded_cards == result.play_statistics.ready_actions.discards
    assert result.play_statistics.mutual_forced_pass_games == 0
    assert result.opponent == "greedy-discard-smoke-baseline-v3"


def test_cli_explicit_48_action_rollout(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "guardian-rollout",
            "--inventory-utilities",
            "--inventory-discards",
            "--refill",
            "weighted-discard-consumption-v1",
            "--batch-size",
            "2",
            "--steps",
            "8",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["metadata"]["action_count"] == 48
