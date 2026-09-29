"""Provisional parallel guardian lifecycle state, not a trainable game kernel."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.guardian_batch import create_provisional_guardian_batch
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values: list[int]) -> object:
    return np.asarray(values, dtype=np.int64)


def profiles() -> object:
    return np.asarray([[0, 101, 2], [0, 102, 3], [1, 201, 1]], dtype=np.int64)


def batch() -> object:
    return native.GuardianLifecycleBatch(3, 4, 4, profiles())


def test_versioned_batch_preserves_explicit_lifecycle_and_ownership() -> None:
    guardian = batch()
    assert native.GUARDIAN_LIFECYCLE_KERNEL_SCHEMA_VERSION == 1
    assert native.GUARDIAN_LIFECYCLE_OBSERVATION_SCHEMA_VERSION == 1
    assert native.GUARDIAN_LIFECYCLE_RULESET_ID == (
        "caller-driven-guardian-lifecycle-provisional-v1"
    )
    assert native.GUARDIAN_LIFECYCLE_RULESET_ID != native.RULESET_ID
    assert guardian.batch_size == 3 and guardian.player_count == 4
    assert guardian.slots_per_environment == 4
    initial = guardian.snapshot()
    assert initial.shape == (3, 4, 3)
    assert not np.any(initial)
    assert not initial.flags.writeable
    guardian.summon(ids([0, 1]), ids([0, 2]), ids([11, 22]), ids([3, 1]), ids([0, 1]))
    state = guardian.snapshot()
    np.testing.assert_array_equal(state[0, 0], ids([11, 3, 0]))
    np.testing.assert_array_equal(state[1, 2], ids([22, 1, 1]))
    assert guardian.active_count == 2 and guardian.summon_count == 2
    np.testing.assert_array_equal(
        guardian.attack_models(ids([0, 0, 1]), ids([0, 0, 2]), ids([11, 11, 22]), ids([0, 2, 0])),
        ids([101, 102, 201]),
    )
    guardian.remove(ids([1]), ids([2]), ids([22]))
    assert guardian.active_count == 1 and guardian.removal_count == 1
    guardian.reset_environments(ids([0, 2]))
    assert guardian.active_count == 0 and guardian.reset_count == 2
    assert not np.any(guardian.snapshot())
    np.testing.assert_array_equal(state[0, 0], ids([11, 3, 0]))
    assert not hasattr(guardian, "step")


@pytest.mark.parametrize(
    "environment, slot, instance, owner, group, message",
    [
        (-1, 0, 12, 0, 0, "out of range"),
        (3, 0, 12, 0, 0, "out of range"),
        (0, 4, 12, 0, 0, "out of range"),
        (0, 1, 0, 0, 0, "invalid state"),
        (0, 1, 12, -1, 0, "invalid state"),
        (0, 1, 12, 4, 0, "invalid state"),
        (0, 1, 12, 0, 2, "unknown"),
    ],
)
def test_invalid_multi_row_summon_does_not_partially_mutate(
    environment: int, slot: int, instance: int, owner: int, group: int, message: str
) -> None:
    guardian = batch()
    before = guardian.snapshot()
    with pytest.raises(ValueError, match=message):
        guardian.summon(
            ids([0, environment]),
            ids([0, slot]),
            ids([11, instance]),
            ids([0, owner]),
            ids([0, group]),
        )
    np.testing.assert_array_equal(guardian.snapshot(), before)
    assert guardian.active_count == 0 and guardian.summon_count == 0


def test_duplicate_identity_and_target_are_atomic() -> None:
    guardian = batch()
    for environments, slots, instances in (
        ([0, 0], [0, 1], [11, 11]),
        ([0, 0], [0, 0], [11, 12]),
    ):
        with pytest.raises(ValueError, match="duplicate"):
            guardian.summon(
                ids(environments), ids(slots), ids(instances), ids([0, 1]), ids([0, 1])
            )
    guardian.summon(ids([0]), ids([0]), ids([11]), ids([0]), ids([0]))
    before = guardian.snapshot()
    with pytest.raises(ValueError, match="already exists"):
        guardian.summon(ids([0]), ids([1]), ids([11]), ids([1]), ids([1]))
    with pytest.raises(ValueError, match="occupied"):
        guardian.summon(ids([0]), ids([0]), ids([12]), ids([1]), ids([1]))
    np.testing.assert_array_equal(guardian.snapshot(), before)
    assert guardian.active_count == 1 and guardian.summon_count == 1


def test_remove_reset_and_attack_validate_before_state_changes() -> None:
    guardian = batch()
    guardian.summon(ids([0, 1]), ids([0, 0]), ids([11, 22]), ids([0, 1]), ids([0, 1]))
    before = guardian.snapshot()
    with pytest.raises(ValueError, match="differs"):
        guardian.remove(ids([0, 1]), ids([0, 0]), ids([11, 23]))
    with pytest.raises(ValueError, match="differs"):
        guardian.attack_models(ids([0]), ids([0]), ids([12]), ids([0]))
    with pytest.raises(ValueError, match="out of range"):
        guardian.attack_models(ids([0]), ids([0]), ids([11]), ids([5]))
    with pytest.raises(ValueError, match="duplicate"):
        guardian.reset_environments(ids([0, 0]))
    with pytest.raises(ValueError, match="out of range"):
        guardian.reset_environments(ids([0, 3]))
    np.testing.assert_array_equal(guardian.snapshot(), before)
    assert guardian.active_count == 2
    assert guardian.removal_count == 0 and guardian.reset_count == 0


def test_batch_dimensions_and_vectorized_access_are_bounded() -> None:
    for args in ((0, 2, 1), (1, 1, 1), (1, 10, 1), (1, 2, 0), (1, 2, 65), (40000, 2, 64)):
        with pytest.raises(ValueError, match="capacity"):
            native.GuardianLifecycleBatch(*args, profiles())
    guardian = native.GuardianLifecycleBatch(128, 9, 1, profiles())
    environments = ids(list(range(128)))
    guardian.summon(
        environments,
        ids([0] * 128),
        ids(list(range(1, 129))),
        ids([8] * 128),
        ids([0] * 128),
    )
    models = guardian.attack_models(
        environments,
        ids([0] * 128),
        ids(list(range(1, 129))),
        ids([4] * 128),
    )
    assert models.shape == (128,)
    assert not models.flags.writeable
    assert np.all(models == 102)
    guardian.reset_environments(environments)
    assert guardian.active_count == 0 and guardian.reset_count == 128


def test_catalog_pinned_factory_and_cli_remain_nontrainable(monkeypatch) -> None:
    created = create_provisional_guardian_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=16,
        player_count=9,
        slots_per_environment=4,
    )
    metadata = created.metadata
    assert metadata.ruleset_id == native.GUARDIAN_LIFECYCLE_RULESET_ID
    assert metadata.picker_ruleset_id == native.PROVISIONAL_GUARDIAN_RULESET_ID
    assert metadata.kernel_schema_version == 1
    assert metadata.observation_schema_version == 1
    assert metadata.batch_size == 16 and metadata.player_count == 9
    assert metadata.slots_per_environment == 4 and metadata.weighted_profile_count == 40
    assert metadata.caller_driven_events_only
    assert not metadata.effect_resolution_implemented
    assert not metadata.local_training_eligible
    assert not metadata.full_game_training_ready
    assert not metadata.promotion_eligible
    assert not np.any(created.batch.snapshot())
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(app, ["simulation", "guardian-batch-plan"])
    assert result.exit_code == 0, result.output
    assert '"full_game_training_ready": false' in result.output
    assert '"batch_size": 512' in result.output
    monkeypatch.setattr(native, "GUARDIAN_LIFECYCLE_KERNEL_SCHEMA_VERSION", 2)
    with pytest.raises(ProvisionalRuleUnavailableError, match="identity differs"):
        create_provisional_guardian_batch(catalog_path=CATALOG, bible_path=BIBLE, batch_size=1)
