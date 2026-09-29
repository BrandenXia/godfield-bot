"""Provisional guardian combat phases, probabilities, and atomic state changes."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.guardian_batch import create_provisional_guardian_combat_batch

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def batch():
    return native.GuardianCombatBatch(
        5,
        3,
        2,
        ids([[0, 101, 1], [1, 102, 1], [2, 103, 1], [3, 104, 1], [4, 105, 1]]),
        ids([[101, 10, 1, 75], [102, 6, 3, 100], [103, 4, 5, 100], [104, 1, 6, 100]]),
    )


def summon(guardian, environments, groups):
    count = len(environments)
    guardian.summon(
        ids(environments), ids([0] * count), ids([1] * count), ids([0] * count), ids(groups)
    )


def attack(guardian, environments, hits=None):
    count = len(environments)
    guardian.begin_attacks(
        ids(environments),
        ids([0] * count),
        ids([1] * count),
        ids([1] * count),
        ids([0] * count),
        ids(hits or [0] * count),
    )


def test_basic_combat_phases_elemental_defense_and_hp_loss():
    guardian = batch()
    summon(guardian, [0, 1, 2, 3], [0, 1, 2, 3])
    attack(guardian, [0, 1, 2, 3], [74, 0, 0, 0])
    pending = guardian.combat_snapshot()
    assert np.all(pending[:4, 0] == 1)
    np.testing.assert_array_equal(pending[:4, 4], ids([10, 6, 4, 1]))
    guardian.resolve_defenses(ids([0, 1, 2, 3]), ids([4, 3, 0, 0]), ids([2, 4, 0, 0]))
    np.testing.assert_array_equal(guardian.hp_snapshot()[:4, 1], ids([34, 37, 36, 0]))
    np.testing.assert_array_equal(guardian.combat_snapshot()[:4, 6], ids([6, 3, 4, 40]))
    assert np.all(guardian.combat_snapshot()[:, 0] == 0)
    assert guardian.resolved_attack_count == 4
    assert np.all(pending[:4, 0] == 1)  # Copied snapshots survive mutation.
    with pytest.raises(ValueError, match="target"):
        attack(guardian, [3])  # Target's HP is zero.
    guardian.reset_environments(ids([3]))
    assert np.all(guardian.hp_snapshot()[3] == 40)
    assert not np.any(guardian.guardian_snapshot()[3])


def test_hit_ticket_boundary_and_pending_lifecycle_lock():
    guardian = batch()
    summon(guardian, [0], [0])
    attack(guardian, [0], [75])
    assert guardian.combat_snapshot()[0, 4] == 0
    with pytest.raises(ValueError, match="awaits defense"):
        attack(guardian, [0])
    with pytest.raises(ValueError, match="awaits defense"):
        guardian.remove(ids([0]), ids([0]), ids([1]))
    guardian.resolve_defenses(ids([0]), ids([0]), ids([0]))
    assert guardian.hp_snapshot()[0, 1] == 40
    assert guardian.combat_snapshot()[0, 6] == 0


def test_unsupported_weighted_effect_aborts_whole_queue_without_resampling():
    guardian = batch()
    summon(guardian, [0, 4], [0, 4])
    before = guardian.combat_snapshot()
    with pytest.raises(ValueError, match="unsupported"):
        attack(guardian, [0, 4])
    np.testing.assert_array_equal(guardian.combat_snapshot(), before)
    assert np.all(guardian.hp_snapshot() == 40)


def test_invalid_multirow_defense_is_atomic():
    guardian = batch()
    summon(guardian, [0, 1], [0, 1])
    attack(guardian, [0, 1])
    pending = guardian.combat_snapshot()
    with pytest.raises(ValueError, match="element"):
        guardian.resolve_defenses(ids([0, 1]), ids([3, 3]), ids([2, 1]))
    np.testing.assert_array_equal(guardian.combat_snapshot(), pending)
    assert np.all(guardian.hp_snapshot() == 40)
    assert guardian.resolved_attack_count == 0
    with pytest.raises(ValueError, match="phase"):
        guardian.resolve_defenses(ids([0, 0]), ids([0, 0]), ids([0, 0]))
    guardian.reset_environments(ids([0, 1]))
    assert not np.any(guardian.combat_snapshot())


def test_light_has_no_positive_elemental_defense():
    guardian = batch()
    summon(guardian, [2], [2])
    attack(guardian, [2])
    for element in range(7):
        with pytest.raises(ValueError, match="element"):
            guardian.resolve_defenses(ids([2]), ids([10]), ids([element]))
    guardian.resolve_defenses(ids([2]), ids([0]), ids([0]))
    assert guardian.hp_snapshot()[2, 1] == 36


def test_pinned_factory_reports_39_effects_and_one_unsupported_weighted_effect(monkeypatch):
    created = create_provisional_guardian_combat_batch(
        catalog_path=Path("data/snapshots/2026-09-21/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=16,
    )
    metadata = created.metadata
    assert metadata.ruleset_id == native.GUARDIAN_COMBAT_RULESET_ID
    assert len(metadata.basic_attack_model_ids) == 21
    assert len(metadata.supported_effect_model_ids) == 39
    assert metadata.unsupported_weighted_model_ids == (264,)
    assert metadata.kernel_schema_version == metadata.observation_schema_version == 2
    assert not metadata.local_training_eligible
    assert not metadata.full_game_training_ready
    assert not metadata.promotion_eligible
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(app, ["simulation", "guardian-batch-plan", "--combat"])
    assert result.exit_code == 0, result.output
    assert '"caller-driven-guardian-resource-curse-combat-provisional-v2"' in result.output
