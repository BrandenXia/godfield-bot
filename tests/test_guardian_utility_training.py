"""Explicit migration, recurrent equivalence, utility learning, and closed gates."""

import hashlib
import json
import stat
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
    migrate_guardian_utility_policy,
)
from godfield_bot.guardian_rollout import (  # noqa: E402
    GuardianRolloutArena,
    GuardianRolloutConfig,
    greedy_guardian_actions,
)
from godfield_bot.guardian_training import (  # noqa: E402
    MANIFEST_FILE,
    WEIGHTS_FILE,
    GuardianArenaManifest,
    GuardianDuelCollector,
    GuardianTrainingConfig,
    GuardianTrainingError,
    _runtime,
    evaluate_guardian_checkpoint,
    load_guardian_checkpoint,
    replay_guardian_rollout,
    train_guardian_candidate,
    train_guardian_teacher,
)
from godfield_bot.model_registry import load_model  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def cfg(*, utilities=False, refill="none", **kwargs):
    return GuardianTrainingConfig(
        **{
            "arena": GuardianRolloutConfig(
                batch_size=4,
                max_turns=8,
                max_decisions=16,
                inventory_utilities=utilities,
                refill=refill,
            ),
            "hidden_size": 32,
            "embedding_size": 8,
            "rollout_steps": 16,
            "teacher_updates": 1,
            "updates": 1,
            "ppo_epochs": 1,
            "environment_minibatch_size": 2,
            "evaluation_games": 4,
            "cpu_threads": 1,
            **kwargs,
        }
    )


def architecture(*, utilities=False, **kwargs):
    return GuardianPolicyArchitecture(
        **{
            "vocabulary_size": 297,
            "hidden_size": 32,
            "embedding_size": 8,
            "hand_feature_count": 9 if utilities else 7,
            "observation_schema_id": "actor-relative-guardian-utility-arena-v2"
            if utilities
            else "actor-relative-guardian-arena-v1",
            **kwargs,
        }
    )


def train(root, config, **kwargs):
    return train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=root, config=config, **kwargs
    )


@pytest.fixture
def runtime():
    with _runtime(67, 1):
        yield


@pytest.fixture
def source(tmp_path):
    return train(tmp_path / "source", cfg())


@pytest.fixture
def migrated(source, tmp_path):
    return train(tmp_path / "utility", cfg(utilities=True), migrate_utilities_from=source[0])


def test_migration_copies_every_other_tensor_and_never_changes_source(runtime):
    old = GuardianArenaPolicy(architecture())
    original = {name: value.detach().clone() for name, value in old.state_dict().items()}
    new = migrate_guardian_utility_policy(old, architecture(utilities=True))
    for name, value in original.items():
        torch.testing.assert_close(old.state_dict()[name], value, rtol=0, atol=0)
        if name != "card_encoder.0.weight":
            torch.testing.assert_close(new.state_dict()[name], value, rtol=0, atol=0)
    encoder = new.card_encoder[0].weight
    assert encoder.shape == (32, 17) and torch.count_nonzero(encoder[:, -2:]) == 0
    expected = original["card_encoder.0.weight"].clone()
    expected[:, 8] *= 7 / 5
    torch.testing.assert_close(encoder[:, :-2], expected, rtol=0, atol=0)


def test_old_card_logits_values_and_per_seat_memory_remain_equivalent(runtime):
    old = GuardianArenaPolicy(architecture())
    new = migrate_guardian_utility_policy(old, architecture(utilities=True))
    game = GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg().arena)
    old_states = torch.randn(4, 2, 32)
    new_states = old_states.clone()
    rows = torch.arange(4)
    for _ in range(48):
        done = ~game.observe().active
        old_states[done] = 0
        new_states[done] = 0
        obs = game.reset_done()
        features = guardian_feature_tensors(obs)
        wider = list(features)
        numeric = torch.cat((features[4], torch.zeros(4, 18, 2)), dim=-1)
        numeric[:, :, 0] *= 5 / 7
        wider[4] = numeric
        actors = torch.from_numpy(obs.actors.copy())
        with torch.no_grad():
            left = old(*features, recurrent_state=old_states[rows, actors])
            right = new(*wider, recurrent_state=new_states[rows, actors])
        for before, after in zip(left, right, strict=True):
            torch.testing.assert_close(before, after, rtol=1e-5, atol=2e-6)
        old_states[rows, actors] = left[2]
        new_states[rows, actors] = right[2]
        game.step(greedy_guardian_actions(obs))


@pytest.mark.parametrize(
    "change", [{"vocabulary_size": 298}, {"hidden_size": 64}, {"embedding_size": 16}]
)
def test_migration_rejects_other_architecture_changes(runtime, change):
    with pytest.raises(ValueError, match="matching 7→9"):
        migrate_guardian_utility_policy(
            GuardianArenaPolicy(architecture()), architecture(utilities=True, **change)
        )


def test_migration_rejects_already_wide_or_nonfinite_weights(runtime):
    old = GuardianArenaPolicy(architecture())
    wide = migrate_guardian_utility_policy(old, architecture(utilities=True))
    with pytest.raises(ValueError):
        migrate_guardian_utility_policy(wide, architecture(utilities=True))
    with torch.no_grad():
        old.value_head.weight[0, 0] = float("nan")
    with pytest.raises(ValueError, match="non-finite source"):
        migrate_guardian_utility_policy(old, architecture(utilities=True))


def test_utility_rollout_replays_exact_likelihoods_and_new_columns_can_learn(runtime):
    config = cfg(utilities=True, defense_feedback_weight=1)
    game = GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=config.arena)
    model = migrate_guardian_utility_policy(
        GuardianArenaPolicy(architecture()), architecture(utilities=True)
    )
    rollout = GuardianDuelCollector(game, model).collect(config, teacher=True)
    logits, values = replay_guardian_rollout(model, rollout, torch.arange(4))
    distribution = torch.distributions.Categorical(logits=logits)
    torch.testing.assert_close(
        distribution.log_prob(rollout.actions), rollout.old_log_probabilities
    )
    torch.testing.assert_close(values, rollout.old_values)
    assert rollout.observations[4].shape == (16, 4, 18, 9)
    assert rollout.utility_statistics is not None and rollout.utility_statistics.uses > 0
    metrics = train_guardian_teacher(
        model, torch.optim.Adam(model.parameters(), lr=0.001), rollout, config
    )
    assert metrics.utility_statistics == rollout.utility_statistics
    assert torch.count_nonzero(model.card_encoder[0].weight[:, -2:]) > 0
    assert all(torch.isfinite(value).all() for value in model.parameters())


def test_wide_checkpoint_records_transfer_costs_tags_and_keeps_live_gate_closed(source, migrated):
    parent_dir, parent = source
    directory, saved = migrated
    loaded, model = load_guardian_checkpoint(directory)
    assert loaded == saved
    assert loaded.schema_version == 2 and model.architecture.hand_feature_count == 9
    record = saved.utility_migration
    assert record.source_model_id == parent.model_id
    assert record.source_weights_sha256 == saved.parent_weights_sha256 == parent.weights_sha256
    assert (
        record.source_manifest_sha256
        == hashlib.sha256((parent_dir / MANIFEST_FILE).read_bytes()).hexdigest()
    )
    assert record.role_column_multiplier == "7/5" and record.target_hand_features == 9
    assert saved.local_training_eligible and not saved.full_game_training_ready
    assert not saved.live_checkpoint_compatible and not saved.promotion_eligible
    assert not saved.optimizer_resumed
    for metric in (*saved.teacher_metrics, *saved.update_metrics):
        assert metric.utility_statistics is not None
    assert saved.evaluation_after.utility_statistics is not None
    assert saved.evaluation_baseline.opponent == "greedy-utility-smoke-baseline-v2"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / WEIGHTS_FILE).stat().st_mode) == 0o600
    with pytest.raises(FileNotFoundError):
        load_model(directory)


def test_transfer_and_resume_preserve_parents_and_utility_lineage(source, migrated, tmp_path):
    source_dir, parent = source
    original = [(source_dir / filename).read_bytes() for filename in (MANIFEST_FILE, WEIGHTS_FILE)]
    directory, wide = migrated
    wide_bytes = [(directory / filename).read_bytes() for filename in (MANIFEST_FILE, WEIGHTS_FILE)]
    _, child = train(tmp_path / "resume", cfg(utilities=True, teacher_updates=0), resume=directory)
    assert child.parent_weights_sha256 == wide.weights_sha256
    assert (
        child.utility_migration is None
    )  # Not another 7→9 migration; direct parent is already wide.
    assert original == [
        (source_dir / filename).read_bytes() for filename in (MANIFEST_FILE, WEIGHTS_FILE)
    ]
    assert wide_bytes == [
        (directory / filename).read_bytes() for filename in (MANIFEST_FILE, WEIGHTS_FILE)
    ]
    loaded, _ = load_guardian_checkpoint(source_dir)
    assert loaded == parent and loaded.schema_version == 1


def test_migration_is_seeded_reproducible(source, migrated, tmp_path):
    _, first = migrated
    _, repeated = train(tmp_path / "repeat", cfg(utilities=True), migrate_utilities_from=source[0])
    assert repeated.weights_sha256 == first.weights_sha256
    assert repeated.rollout_sha256 == first.rollout_sha256
    assert repeated.update_metrics == first.update_metrics
    assert repeated.utility_migration == first.utility_migration


@pytest.mark.parametrize("error", ["implicit", "no-opt-in", "both", "changed-bound"])
def test_transfer_requires_explicit_authority_and_preserved_bounds(source, tmp_path, error):
    target = tmp_path / "rejected"
    config = cfg(utilities=True)
    options = {"migrate_utilities_from": source[0]}
    if error == "implicit":
        options = {"resume": source[0]}
    elif error == "no-opt-in":
        config = cfg()
    elif error == "both":
        options["resume"] = source[0]
    else:
        config = cfg(
            utilities=True,
            arena=GuardianRolloutConfig(
                batch_size=4, max_turns=9, max_decisions=16, inventory_utilities=True
            ),
        )
    with pytest.raises(GuardianTrainingError):
        train(target, config, **options)
    assert not target.exists()


def test_weighted_migration_and_evaluation_use_only_new_pool(tmp_path):
    parent_dir, old = train(tmp_path / "old-refill", cfg(refill="weighted-consumption-v1"))
    directory, wide = train(
        tmp_path / "new-refill",
        cfg(utilities=True, refill="weighted-utility-consumption-v1"),
        migrate_utilities_from=parent_dir,
    )
    assert wide.utility_migration.source_arena.refill_plan.supported_models == 94
    assert wide.arena.refill_plan.supported_models == 102
    assert wide.utility_migration.source_weights_sha256 == old.weights_sha256
    report = evaluate_guardian_checkpoint(
        directory, catalog_path=CATALOG, bible_path=BIBLE, games=4, seed=91, cpu_threads=1
    )
    assert report.utility_statistics is not None and report.replacement_gifts > 0
    assert report.wins + report.losses + report.truncations == 4


@pytest.mark.parametrize(
    "mutation",
    [
        "outer-tag",
        "architecture",
        "migration-hash",
        "source-width",
        "missing-metrics",
        "gift-pool",
        "live",
        "opponent",
        "statistics",
        "source-pins",
        "source-bound",
        "source-native",
    ],
)
def test_tampered_utility_checkpoint_fails_closed(migrated, mutation):
    _, saved = migrated
    record = saved.model_dump(mode="json")
    if mutation == "outer-tag":
        record["schema_version"] = 1
    elif mutation == "architecture":
        record["architecture"]["hand_feature_count"] = 7
    elif mutation == "migration-hash":
        record["utility_migration"]["source_weights_sha256"] = "0" * 64
    elif mutation == "source-width":
        record["utility_migration"]["source_architecture"]["hand_feature_count"] = 9
    elif mutation == "missing-metrics":
        record["update_metrics"][0]["utility_statistics"] = None
    elif mutation == "gift-pool":
        record["arena"]["refill_plan"] = saved.utility_migration.source_arena.refill_plan
        record["arena"]["config"]["refill"] = "weighted-utility-consumption-v1"
    elif mutation == "live":
        record["live_checkpoint_compatible"] = True
    elif mutation == "opponent":
        record["evaluation_after"]["opponent"] = "greedy-smoke-baseline-v1"
    elif mutation == "source-pins":
        record["utility_migration"]["source_arena"]["native"]["catalog_sha256"] = "0" * 64
    elif mutation == "source-bound":
        record["utility_migration"]["source_arena"]["config"]["max_decisions"] += 1
    elif mutation == "source-native":
        record["utility_migration"]["source_arena"]["native"]["initial_hp"] += 1
    else:
        record["evaluation_after"]["utility_statistics"]["uses"] += 1
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(record)


def test_cli_migrates_into_new_child_with_explicit_flags(source, tmp_path, monkeypatch):
    from structlog.testing import capture_logs

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    with capture_logs():
        result = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--inventory-utilities",
                "--migrate-utilities-from",
                str(source[0]),
                "--checkpoint-root",
                str(tmp_path / "cli"),
                "--batch-size",
                "4",
                "--rollout-steps",
                "8",
                "--teacher-updates",
                "0",
                "--updates",
                "1",
                "--hidden-size",
                "32",
                "--embedding-size",
                "8",
                "--evaluation-games",
                "4",
                "--max-turns",
                "8",
                "--max-decisions",
                "16",
            ],
        )
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)["manifest"]
    assert record["schema_version"] == 2 and record["utility_migration"] is not None
    assert not record["live_checkpoint_compatible"] and not record["promotion_eligible"]
