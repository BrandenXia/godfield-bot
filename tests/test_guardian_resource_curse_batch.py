import pytest

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def batch(cp=98):
    profiles = [
        [201, 10, 0, 100, 1, 0, 0],  # Absorb HP.
        [202, 4, 2, 100, 2, 0, 1],  # Fog on damage.
        [203, 0, 3, 100, 3, 0, 2],  # Direct Dream.
        [204, 0, 0, 100, 4, 0, 0],  # Remove owner's curses.
        [205, 0, 0, 100, 5, 10, 0],  # HP+10.
        [206, 0, 0, 100, 6, 10, 0],  # MP+10.
        [207, 0, 0, 100, 7, 20, 0],  # CP+20.
        [208, 0, 0, 100, 8, 1, 0],  # Everybody CP+1.
        [209, 0, 0, 100, 9, 5, 0],  # Enemy CP+5.
        [210, 0, 0, 100, 10, 3, 0],  # Levy CP3.
    ]
    guardian = native.GuardianCombatBatch(
        2,
        3,
        12,
        ids([[group, 201 + group, 1] for group in range(10)]),
        ids(profiles),
        80,
        95,
        cp,
    )
    for env in range(2):
        guardian.summon(
            ids([env] * 10),
            ids(list(range(10))),
            ids(list(range(1, 11))),
            ids([0] * 10),
            ids(list(range(10))),
        )
    return guardian


def effect(guardian, slot, target=0, env=0):
    guardian.begin_effects(
        ids([env]), ids([slot]), ids([slot + 1]), ids([target]), ids([0]), ids([0])
    )


def test_absorption_and_utility_caps_use_actual_resource_changes():
    guardian = batch()
    effect(guardian, 0, target=1)
    guardian.resolve_defenses(ids([0]), ids([5]), ids([0]))
    state = guardian.resource_snapshot()
    assert state[0, 0, 0] == 85 and state[0, 1, 0] == 75
    effect(guardian, 4)
    effect(guardian, 4)
    effect(guardian, 5)
    effect(guardian, 6)
    np.testing.assert_array_equal(guardian.resource_snapshot()[0, 0, :3], ids([100, 100, 100]))
    assert state[0, 0, 0] == 85  # Outputs are independent copies.
    assert guardian.resolved_attack_count == 1 and guardian.resolved_effect_count == 5


def test_direct_and_on_damage_curses_accumulate_and_owner_cure_clears_them():
    guardian = batch()
    effect(guardian, 2, target=1)
    assert guardian.combat_snapshot()[0, 0] == 0
    assert guardian.resource_snapshot()[0, 1, 3] == 2
    effect(guardian, 1, target=1)
    guardian.resolve_defenses(ids([0]), ids([4]), ids([1]))
    assert guardian.resource_snapshot()[0, 1, 3] == 2  # Fully blocked.
    effect(guardian, 1, target=1)
    guardian.resolve_defenses(ids([0]), ids([0]), ids([0]))
    assert guardian.resource_snapshot()[0, 1, 3] == 3
    guardian.summon(ids([0]), ids([10]), ids([11]), ids([1]), ids([3]))
    guardian.begin_effects(ids([0]), ids([10]), ids([11]), ids([1]), ids([0]), ids([0]))
    assert guardian.resource_snapshot()[0, 1, 3] == 0


def test_money_to_everybody_bribe_and_levy_preserve_transfer_capacity():
    guardian = batch()
    effect(guardian, 7)
    np.testing.assert_array_equal(guardian.resource_snapshot()[0, :, 2], ids([99, 99, 99]))
    effect(guardian, 8, target=1)
    effect(guardian, 9, target=1)
    np.testing.assert_array_equal(guardian.resource_snapshot()[0, :, 2], ids([100, 99, 99]))
    empty = batch(cp=0)
    effect(empty, 9, target=1)
    assert not np.any(empty.resource_snapshot()[0, :, 2])


def test_multirow_utility_validation_is_atomic_and_reset_restores_all_resources():
    guardian = batch()
    before = guardian.resource_snapshot()
    with pytest.raises(ValueError, match="role"):
        guardian.begin_effects(
            ids([0, 1]), ids([4, 4]), ids([5, 5]), ids([0, 1]), ids([0, 0]), ids([0, 0])
        )
    np.testing.assert_array_equal(guardian.resource_snapshot(), before)
    assert guardian.resolved_effect_count == 0
    effect(guardian, 5)
    effect(guardian, 2, target=1)
    guardian.reset_environments(ids([0]))
    np.testing.assert_array_equal(guardian.resource_snapshot()[0], before[0])
    assert not np.any(guardian.combat_snapshot()[0])
    assert not np.any(guardian.guardian_snapshot()[0])


@pytest.mark.parametrize(
    "profile",
    [
        [201, 0, 0, 100, 0, 0, 0],
        [201, 1, 0, 100, 2, 0, 0],
        [201, 0, 0, 100, 5, 0, 0],
        [201, 0, 0, 100, 11, 1, 0],
        [202, 1, 0, 100, 0, 0, 0],
    ],
)
def test_malformed_effect_profiles_cannot_construct_a_batch(profile):
    with pytest.raises(ValueError, match="profile"):
        native.GuardianCombatBatch(1, 2, 1, ids([[0, 201, 1]]), ids([profile]))
