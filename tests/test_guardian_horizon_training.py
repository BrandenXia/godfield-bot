"""Explicit longer-bound transfer preserves the prefix, not terminal semantics."""

import hashlib
import json
import stat
from dataclasses import fields
from pathlib import Path

import pytest
from structlog.testing import capture_logs
from typer.testing import CliRunner

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.guardian_neural import (  # noqa: E402
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
    guardian_feature_tensors,
    migrate_guardian_horizon_policy,
)
from godfield_bot.guardian_rollout import (  # noqa: E402
    GuardianRolloutArena,
    GuardianRolloutConfig,
    greedy_guardian_actions,
)
from godfield_bot.guardian_training import (  # noqa: E402
    GuardianArenaManifest,
    GuardianTrainingConfig,
    GuardianTrainingError,
    _migrate_horizon_checkpoint,
    _runtime,
    evaluate_guardian_checkpoint,
    load_guardian_checkpoint,
    train_guardian_candidate,
)
from godfield_bot.model_registry import load_model  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
KINDS = ("old", "utility", "discard")


def cfg(kind="discard", **changes):
    return GuardianRolloutConfig.model_validate(
        {
            "batch_size": 4,
            "max_turns": 8,
            "max_decisions": 32,
            "inventory_utilities": kind != "old",
            "inventory_discards": kind == "discard",
            "refill": "weighted-discard-consumption-v1"
            if kind == "discard"
            else "weighted-utility-consumption-v1"
            if kind == "utility"
            else "weighted-consumption-v1",
            "opening": "mixed",
            **changes,
        }
    )


def game(config):
    return GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=config)


def arch(kind="discard"):
    return GuardianPolicyArchitecture(
        vocabulary_size=297,
        hidden_size=32,
        embedding_size=8,
        hand_feature_count=7 if kind == "old" else 9,
        action_count=48 if kind == "discard" else 30,
        observation_schema_id="actor-relative-guardian-discard-arena-v3"
        if kind == "discard"
        else "actor-relative-guardian-utility-arena-v2"
        if kind == "utility"
        else "actor-relative-guardian-arena-v1",
    )


def train_cfg(kind="discard", **changes):
    return GuardianTrainingConfig(
        arena=cfg(kind, **changes),
        hidden_size=32,
        embedding_size=8,
        rollout_steps=16,
        teacher_updates=1,
        updates=1,
        ppo_epochs=1,
        environment_minibatch_size=2,
        evaluation_games=4,
        cpu_threads=1,
    )


def train(root, config, **kwargs):
    return train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=root, config=config, **kwargs
    )


def migrate(model, source=(8, 32), target=(32, 128)):
    return migrate_guardian_horizon_policy(
        model,
        source_max_turns=source[0],
        source_max_decisions=source[1],
        target_max_turns=target[0],
        target_max_decisions=target[1],
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("source,target", [((8, 32), (32, 128)), ((7, 31), (29, 97))])
def test_only_two_columns_change_and_recurrent_prefix_matches(kind, source, target):
    with _runtime(67, 1):
        old = GuardianArenaPolicy(arch(kind))
        snapshots = {name: value.clone() for name, value in old.state_dict().items()}
        new = migrate(old, source, target)
        assert old.architecture == new.architecture
        for name, value in snapshots.items():
            torch.testing.assert_close(old.state_dict()[name], value, rtol=0, atol=0)
            expected = value.clone()
            if name == "global_encoder.0.weight":
                expected[:, 7] *= target[0] / source[0]
                expected[:, 42] *= target[1] / source[1]
            torch.testing.assert_close(new.state_dict()[name], expected, rtol=0, atol=0)
        arena = game(cfg(kind, max_turns=source[0], max_decisions=source[1]))
        left_states = torch.randn(4, 2, 32)
        right_states = left_states.clone()
        for _ in range(64):
            done = ~arena.observe().active
            left_states[done] = right_states[done] = 0
            obs = arena.reset_done()
            original = guardian_feature_tensors(obs)
            longer = list(original)
            longer[0] = original[0].clone()
            longer[0][:, 7] *= source[0] / target[0]
            longer[0][:, 42] *= source[1] / target[1]
            actors = torch.from_numpy(obs.actors.copy())
            rows = torch.arange(4)
            with torch.no_grad():
                left = old(*original, recurrent_state=left_states[rows, actors])
                right = new(*longer, recurrent_state=right_states[rows, actors])
            for a, b in zip(left, right, strict=True):
                torch.testing.assert_close(a, b, rtol=1e-5, atol=1e-6)
            left_states[rows, actors], right_states[rows, actors] = left[2], right[2]
            arena.step(greedy_guardian_actions(obs))


@pytest.mark.parametrize("kind", KINDS)
def test_actual_arenas_share_mechanics_and_rng_before_old_absorbing_limit(kind):
    short = game(cfg(kind, max_turns=4, max_decisions=16))
    long = game(cfg(kind, max_turns=16, max_decisions=64))
    decisions = 0
    while short.observe().active.all():
        before, after = short.observe(), long.observe()
        for field in fields(before):
            left, right = getattr(before, field.name), getattr(after, field.name)
            if field.name == "global_features":
                right = right.copy()
                right[:, [7, 42]] *= 4
            np.testing.assert_array_equal(left, right)
        np.testing.assert_array_equal(
            short._native.inventory_snapshot(), long._native.inventory_snapshot()
        )
        assert [r.bit_generator.state for r in short._refill_rngs.values()] == [
            r.bit_generator.state for r in long._refill_rngs.values()
        ]
        actions = greedy_guardian_actions(before)
        a, b = short.step(actions), long.step(actions)
        decisions += 1
        if not (a.terminated | a.truncated).any():
            np.testing.assert_array_equal(a.rewards, b.rewards)
            np.testing.assert_array_equal(a.terminated, b.terminated)
            assert not (b.terminated | b.truncated).any()
    assert decisions > 1


def test_limits_really_extend_without_claiming_equal_terminal_rewards():
    short = game(cfg(max_turns=2, max_decisions=8))
    long = game(cfg(max_turns=4, max_decisions=16))
    environments = np.arange(4, dtype=np.int64)
    for arena in (short, long):
        arena._native.reset_environments(environments)  # empty hands: deterministic passes
    actions = np.zeros(4, dtype=np.int64)
    short.step(actions)
    long.step(actions)
    assert short.step(actions).truncated.all()
    result = long.step(actions)
    assert not (result.terminated | result.truncated).any()
    assert not short.observe().action_mask.any()
    assert long.observe().action_mask[:, 0].all()
    long.step(actions)
    assert long.step(actions).truncated.all()


@pytest.mark.parametrize(
    "source,target",
    [
        ((8, 32), (8, 32)),
        ((8, 32), (7, 64)),
        ((8, 32), (16, 31)),
        ((0, 32), (16, 64)),
        ((8, -1), (16, 64)),
        ((8, 32), (100001, 64)),
        ((True, 32), (16, 64)),
        ((8, 32), (16.0, 64)),
    ],
)
def test_bounds_are_explicit_strict_and_never_shrink(source, target):
    with pytest.raises(ValueError, match="horizon migration"):
        migrate(GuardianArenaPolicy(arch()), source, target)


@pytest.mark.parametrize("target", [(16, 32), (8, 64)])
def test_extending_only_one_bound_is_supported(target):
    old = GuardianArenaPolicy(arch())
    new = migrate(old, target=target)
    unchanged = 42 if target[1] == 32 else 7
    torch.testing.assert_close(
        old.global_encoder[0].weight[:, unchanged],
        new.global_encoder[0].weight[:, unchanged],
        rtol=0,
        atol=0,
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), torch.finfo(torch.float32).max])
def test_nonfinite_source_or_scaling_overflow_rejected_without_mutating_parent(value):
    old = GuardianArenaPolicy(arch())
    with torch.no_grad():
        old.global_encoder[0].weight[:, 7].fill_(value)
    snapshot = old.global_encoder[0].weight.clone()
    with pytest.raises(ValueError, match="non-finite"):
        migrate(old)
    torch.testing.assert_close(old.global_encoder[0].weight, snapshot, equal_nan=True)


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("guardian-horizon")
    return {kind: train(root / kind, train_cfg(kind)) for kind in KINDS}


@pytest.mark.parametrize("kind", KINDS)
def test_child_provenance_parent_immutable_gates_and_ordinary_resume(sources, tmp_path, kind):
    source, parent = sources[kind]
    old_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    config = train_cfg(kind, max_turns=32, max_decisions=128)
    directory, manifest = train(tmp_path / "child", config, migrate_horizon_from=source)
    transfer = manifest.horizon_migration
    assert transfer is not None and transfer.source_model_id == parent.model_id
    assert transfer.source_weights_sha256 == manifest.parent_weights_sha256 == parent.weights_sha256
    assert transfer.source_manifest_sha256 == old_hashes["arena-manifest.json"]
    assert transfer.source_arena == parent.arena
    assert transfer.turn_column_multiplier == transfer.decision_column_multiplier == 4
    assert transfer.target_max_turns == 32 and transfer.target_max_decisions == 128
    assert not transfer.optimizer_resumed and manifest.utility_migration is None
    assert manifest.discard_migration is None
    assert not manifest.live_checkpoint_compatible and not manifest.promotion_eligible
    assert not manifest.official_fidelity_verified and not manifest.full_game_training_ready
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for p in directory.iterdir():
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    loaded, model = load_guardian_checkpoint(directory)
    assert loaded == manifest and model.architecture == parent.architecture
    assert old_hashes == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()
    }
    with pytest.raises(FileNotFoundError):
        load_model(directory)
    evaluate_guardian_checkpoint(
        directory, catalog_path=CATALOG, bible_path=BIBLE, games=4, seed=901, cpu_threads=1
    )
    _, resumed = train(tmp_path / "resume", config, resume=directory)
    assert resumed.parent_weights_sha256 == manifest.weights_sha256
    assert resumed.horizon_migration is None  # immediate-parent transfer, not invented lineage
    with pytest.raises(GuardianTrainingError):
        train(tmp_path / "implicit", config, resume=source)
    assert not (tmp_path / "implicit").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"max_turns": 8, "max_decisions": 32},
        {"max_turns": 7, "max_decisions": 128},
        {"max_turns": 32, "max_decisions": 31},
        {"initial_mp": 11},
        {"initial_hp": 41},
        {"gamma": 0.9},
        {"shaping_scale": 0.2},
        {"opening": "cards-only"},
    ],
)
def test_transfer_rejects_implicit_rules_reward_and_invalid_bounds(sources, tmp_path, change):
    settings = {"max_turns": 32, "max_decisions": 128, **change}
    with pytest.raises((ValueError, GuardianTrainingError)):
        train(tmp_path / "wrong", train_cfg(**settings), migrate_horizon_from=sources["discard"][0])
    assert not (tmp_path / "wrong").exists()


def test_transfer_does_not_widen_architecture_or_mix_other_migrations(sources, tmp_path):
    config = train_cfg(max_turns=32, max_decisions=128)
    with pytest.raises(GuardianTrainingError):
        train(tmp_path / "wrong", config, migrate_horizon_from=sources["utility"][0])
    for option in ("resume", "migrate_utilities_from", "migrate_discards_from"):
        with pytest.raises(GuardianTrainingError, match="only one"):
            train(
                tmp_path / "wrong",
                config,
                migrate_horizon_from=sources["discard"][0],
                **{option: sources["utility"][0]},
            )
    config = config.model_copy(update={"hidden_size": 64})
    with pytest.raises(GuardianTrainingError):
        train(tmp_path / "wrong", config, migrate_horizon_from=sources["discard"][0])


@pytest.fixture(scope="module")
def child(sources, tmp_path_factory):
    return train(
        tmp_path_factory.mktemp("guardian-horizon-child"),
        train_cfg(max_turns=32, max_decisions=128),
        migrate_horizon_from=sources["discard"][0],
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "parent-hash",
        "ratio",
        "decision-ratio",
        "target-bound",
        "source-bound",
        "native-bound",
        "source-pin",
        "reward",
        "native-toggle-bound",
        "source-layout",
        "source-discard-layout",
        "source-refill",
        "column",
        "optimizer",
        "live-gate",
    ],
)
def test_manifest_tampering_fails_closed(child, mutation):
    data = child[1].model_dump()
    transfer = data["horizon_migration"]
    source = transfer["source_arena"]
    if mutation == "parent-hash":
        transfer["source_weights_sha256"] = "a" * 64
    elif mutation == "ratio":
        transfer["turn_column_multiplier"] = 5
    elif mutation == "decision-ratio":
        transfer["decision_column_multiplier"] = 5
    elif mutation == "target-bound":
        transfer["target_max_turns"] += 1
    elif mutation == "source-bound":
        source["config"]["max_decisions"] += 1
    elif mutation == "native-bound":
        source["native"]["utility_base"]["max_turns"] += 1
    elif mutation == "source-pin":
        source["native"]["utility_base"]["catalog_sha256"] = "a" * 64
    elif mutation == "reward":
        source["config"]["gamma"] = 0.9
    elif mutation == "native-toggle-bound":
        source["native"]["utility_base"]["max_defense_actions"] += 1
    elif mutation == "source-layout":
        source["global_fields"] = ("wrong",)
    elif mutation == "source-discard-layout":
        source["native"]["pending_observation_fields"] = ("wrong",)
    elif mutation == "source-refill":
        source["refill_plan"]["random_stream"] = "seed-environment-episode-channel-6772-v1"
    elif mutation == "column":
        transfer["turn_column"] = 8
    elif mutation == "optimizer":
        transfer["optimizer_resumed"] = True
    else:
        data["live_checkpoint_compatible"] = True
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)


def test_migration_initial_model_equals_standalone_rescale(sources):
    source, parent = sources["discard"]
    metadata = game(cfg(max_turns=32, max_decisions=128)).metadata
    with _runtime(67, 1):
        loaded, expected = load_guardian_checkpoint(source)
        loaded_again, actual, record = _migrate_horizon_checkpoint(
            source, metadata, arch(), catalog_path=CATALOG, bible_path=BIBLE
        )
        expected = migrate(expected)
        assert loaded == loaded_again == parent
        assert record.source_arena == parent.arena
        for name, value in expected.state_dict().items():
            torch.testing.assert_close(actual.state_dict()[name], value, rtol=0, atol=0)


def test_historical_manifest_has_unknown_horizon_record(sources):
    data = sources["discard"][1].model_dump()
    data.pop("horizon_migration")
    assert GuardianArenaManifest.model_validate(data).horizon_migration is None


def test_cli_explicit_horizon_migration(sources, tmp_path, monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    with capture_logs():
        result = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--migrate-horizon-from",
                str(sources["discard"][0]),
                "--checkpoint-root",
                str(tmp_path / "cli"),
                "--inventory-utilities",
                "--inventory-discards",
                "--refill",
                "weighted-discard-consumption-v1",
                "--batch-size",
                "4",
                "--max-turns",
                "32",
                "--max-decisions",
                "128",
                "--rollout-steps",
                "16",
                "--teacher-updates",
                "0",
                "--updates",
                "1",
                "--ppo-epochs",
                "1",
                "--environment-minibatch-size",
                "2",
                "--evaluation-games",
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
    data = json.loads(result.output)
    manifest = GuardianArenaManifest.model_validate(data["manifest"])
    assert manifest.horizon_migration.turn_column_multiplier == 4
    assert manifest.horizon_migration.decision_column_multiplier == 4
    assert manifest.evaluation_teacher is None
    assert manifest.teacher_metrics == ()
    assert manifest.update_metrics[0].outcome_coverage is not None
