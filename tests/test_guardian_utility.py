"""Separate inventory utility rules; no old arena/checkpoint schema changes."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_batch import create_provisional_guardian_turn_batch
from godfield_bot.guardian_utility import (
    UTILITY_PROFILE_SHA256,
    UTILITY_RULESET_ID,
    GuardianUtilityPlan,
    build_guardian_utility_plan,
    create_provisional_guardian_utility_turn_batch,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PROFILES = (
    (191, 0, 5, 0, 0),
    (192, 0, 10, 0, 0),
    (193, 0, 15, 0, 0),
    (194, 0, 20, 0, 0),
    (195, 1, 5, 0, 0),
    (196, 1, 10, 0, 0),
    (197, 1, 15, 0, 0),
    (235, 0, 10, 1, 7),
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=2, players=3, hp=40, mp=10, max_turns=1000, profiles=PROFILES):
    return native.GuardianUtilityTurnBatch(
        size,
        players,
        4,
        ids([[0, 245, 1], [1, 260, 1], [2, 259, 1]]),
        ids([[245, 10, 0, 100, 0, 0, 0], [260, 0, 0, 100, 6, 10, 0], [259, 0, 0, 100, 3, 0, 2]]),
        ids([[113, 4, 0, 0, 0], [233, 0, 0, 1, 6], [234, 0, 0, 2, 5]]),
        ids([[6, 10, 0, 0, 0], [211, 10, 0, 1, 5]]),
        ids(profiles),
        4,
        max_turns,
        hp,
        mp,
    )


def deal(batch, envs, models, *, player=0, slots=None):
    count = len(envs)
    slots = list(range(count)) if slots is None else slots
    batch.deal_cards(
        ids(envs),
        ids([player] * count),
        ids(slots),
        ids([100 + player * 18 + slot for slot in slots]),
        ids(models),
    )


def use(batch, envs=(0,), *, player=0, slot=0):
    batch.use_utility_cards(ids(envs), ids([player] * len(envs)), ids([slot] * len(envs)))


def pass_turn(batch, player, envs=(0,)):
    batch.pass_turns(ids(envs), ids([player] * len(envs)))


def state(batch):
    return (
        batch.resource_snapshot(),
        batch.inventory_snapshot(),
        batch.turn_snapshot(),
        batch.combat_snapshot(),
        batch.guardian_snapshot(),
        (
            batch.consumed_card_count,
            batch.miracle_cast_count,
            batch.mp_spent,
            batch.utility_use_count,
            batch.hp_gained,
            batch.mp_gained,
        ),
    )


def assert_same_state(batch, before):
    for actual, expected in zip(state(batch)[:-1], before[:-1], strict=True):
        np.testing.assert_array_equal(actual, expected)
    assert state(batch)[-1] == before[-1]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("hp,mp", [(40, 10), (96, 97), (100, 100), (1, 0), (40, 7), (40, 6)])
def test_every_pinned_utility_gain_cost_consumption_and_caps(profile, hp, mp):
    model, resource, gain, reusable, cost = profile
    batch = game(hp=hp, mp=mp)
    deal(batch, [0], [model])
    before = state(batch)
    current = hp if resource == 0 else mp
    legal = current < 100 and cost <= mp
    assert bool(batch.utility_action_masks()[0, 0]) == legal
    assert bool(batch.ready_action_masks()[0, 0]) == legal
    assert not batch.attack_action_masks()[0, 0]
    assert batch.ready_action_masks()[0, 4]  # Pass remains legal.
    if not legal:
        with pytest.raises(ValueError):
            use(batch)
        assert_same_state(batch, before)
        return
    use(batch)
    effective = min(gain, 100 - current)
    expected = [hp, mp, 0, 0]
    expected[1] -= cost
    expected[resource] += effective
    np.testing.assert_array_equal(batch.resource_snapshot()[0, 0], expected)
    np.testing.assert_array_equal(batch.resource_snapshot()[0, 1:], before[0][0, 1:])
    assert batch.utility_use_count == 1
    assert batch.hp_gained == (effective if resource == 0 else 0)
    assert batch.mp_gained == (effective if resource == 1 else 0)
    assert batch.mp_spent == cost
    assert batch.miracle_cast_count == reusable
    assert batch.consumed_card_count == 1 - reusable
    np.testing.assert_array_equal(
        batch.inventory_snapshot()[0, 0, 0], [100, model, 0] if reusable else [0, 0, 0]
    )
    np.testing.assert_array_equal(batch.turn_snapshot()[0, :4], [0, 1, 1, 1])
    assert batch.turn_snapshot()[0, 9] == 3
    assert batch.combat_snapshot()[0, 0] == 0  # No defense window.
    assert batch.combat_snapshot()[0, 7] == (5 if resource == 0 else 6)
    assert batch.resolved_effect_count == 0  # Not a guardian effect.
    assert not np.any(batch.defense_action_masks())
    # Snapshots must be copies, including resources before the use.
    np.testing.assert_array_equal(before[0][0, 0], [hp, mp, 0, 0])


def test_spring_is_retained_and_mp_item_can_fund_another_cast():
    batch = game(players=2, mp=7)
    deal(batch, [0, 0], [235, 195])
    use(batch)
    pass_turn(batch, 1)
    assert not batch.utility_action_masks()[0, 0]
    use(batch, slot=1)  # +5 MP is not yet enough.
    pass_turn(batch, 1)
    assert not batch.utility_action_masks()[0, 0]
    deal(batch, [0], [195], slots=[1])
    use(batch, slot=1)
    pass_turn(batch, 1)
    assert batch.utility_action_masks()[0, 0]
    use(batch)
    np.testing.assert_array_equal(batch.resource_snapshot()[0, 0], [60, 3, 0, 0])
    assert batch.inventory_snapshot()[0, 0, 0, 1] == 235
    assert batch.utility_use_count == 4
    assert batch.miracle_cast_count == 2
    assert batch.mp_spent == 14
    assert batch.consumed_card_count == 2


def test_utility_hand_projection_is_actor_only_selected_safe_and_readonly():
    batch = game()
    deal(batch, [0, 0, 0, 0], [191, 195, 235, 6])
    deal(batch, [0, 0], [192, 113], player=1)
    hand = batch.actor_hand_snapshot()
    assert hand.shape == (2, 4, 11)
    np.testing.assert_array_equal(hand[0, :, 1], [191, 195, 235, 6])
    np.testing.assert_array_equal(
        hand[0, :, 3:],
        [
            [6, 0, 0, 0, 0, 0, 5, 0],
            [7, 0, 0, 0, 0, 0, 0, 5],
            [6, 0, 0, 0, 7, 1, 10, 0],
            [2, 10, 0, 0, 0, 0, 0, 0],
        ],
    )
    assert not hand.flags.writeable
    assert not batch.hand_feature_snapshot().flags.writeable
    assert batch.hand_feature_snapshot().shape == (2, 3, 4, 8)
    batch.begin_card_attacks(ids([0]), ids([0]), ids([3]), ids([1]))
    defender = batch.actor_hand_snapshot()
    np.testing.assert_array_equal(defender[0, :2, 1], [192, 113])
    assert not np.any(batch.utility_action_masks()[0])
    assert not np.any(batch.ready_action_masks()[0])
    assert not batch.defense_action_masks()[0, 0]  # HP item is not armor.
    batch.step_defenses(ids([0]), ids([1]), ids([1]))
    assert batch.actor_hand_snapshot()[0, 1, 2] == 1
    before = state(batch)
    with pytest.raises(ValueError):
        use(batch, player=1)
    assert_same_state(batch, before)
    batch.step_defenses(ids([0]), ids([1]), ids([5]))
    assert batch.resource_snapshot()[0, 1, 0] == 34
    assert batch.turn_snapshot()[0, 1] == 1
    use(batch, player=1)
    assert batch.resource_snapshot()[0, 1, 0] == 44
    np.testing.assert_array_equal(hand[0, :, 1], [191, 195, 235, 6])


@pytest.mark.parametrize(
    "envs,players,slots",
    [
        ([0, 1], [0, 1], [0, 0]),
        ([0, 1], [0, 0], [0, 4]),
        ([0, 1], [0, 0], [0, -1]),
        ([0, 1], [0, 0], [0, 2]),
        ([0, 0], [0, 0], [0, 0]),
        ([0, 2], [0, 0], [0, 0]),
        ([0, -1], [0, 0], [0, 0]),
        ([0, 1], [0], [0, 0]),
        ([0, 1], [0, 0], [0]),
        ([0, 1], [0, -1], [0, 0]),
    ],
)
def test_rejected_multirow_use_is_atomic(envs, players, slots):
    batch = game()
    deal(batch, [0, 1], [191, 235], slots=[0, 0])
    before = state(batch)
    with pytest.raises(ValueError):
        batch.use_utility_cards(ids(envs), ids(players), ids(slots))
    assert_same_state(batch, before)


def test_invalid_last_affordability_does_not_consume_first_row():
    batch = game(mp=6)
    deal(batch, [0, 1], [191, 235], slots=[0, 0])
    before = state(batch)
    with pytest.raises(ValueError):
        use(batch, [0, 1])
    assert_same_state(batch, before)


def test_mp_item_enables_attack_miracle_and_keeps_existing_defense_costs():
    batch = game(players=2, mp=0)
    deal(batch, [0, 0], [195, 211])
    deal(batch, [0, 0], [196, 233], player=1)
    assert not batch.attack_action_masks()[0, 1]
    use(batch)
    use(batch, player=1)
    assert batch.attack_action_masks()[0, 1]
    batch.begin_card_attacks(ids([0]), ids([0]), ids([1]), ids([1]))
    assert batch.resource_snapshot()[0, 0, 1] == 0
    assert batch.inventory_snapshot()[0, 0, 1, 1] == 211
    assert not batch.defense_action_masks()[0, 1]  # Wall cannot answer a miracle.
    batch.step_defenses(ids([0]), ids([1]), ids([4]))
    np.testing.assert_array_equal(batch.resource_snapshot()[0, 1], [30, 10, 0, 0])
    pass_turn(batch, 1)
    deal(batch, [0], [6], slots=[0])
    batch.begin_card_attacks(ids([0]), ids([0]), ids([0]), ids([1]))
    batch.step_defenses(ids([0]), ids([1]), ids([1]))
    batch.step_defenses(ids([0]), ids([1]), ids([5]))
    np.testing.assert_array_equal(batch.resource_snapshot()[0, 1], [30, 4, 0, 0])
    assert batch.miracle_cast_count == 2
    assert batch.mp_spent == 11
    assert batch.consumed_card_count == 3
    assert batch.utility_use_count == 2


def test_bounce_phase_does_not_enable_utility_or_consume_it():
    batch = game(players=2)
    deal(batch, [0], [211])
    deal(batch, [0, 0], [234, 191], player=1)
    batch.begin_card_attacks(ids([0]), ids([0]), ids([0]), ids([1]))
    batch.step_defenses(ids([0]), ids([1]), ids([0]))
    batch.step_defenses(ids([0]), ids([1]), ids([5]))
    assert batch.turn_snapshot()[0, 0] == 4
    assert not np.any(batch.utility_action_masks()[0])
    assert not np.any(batch.ready_action_masks()[0])
    assert batch.actor_hand_snapshot()[0, 1, 1] == 191
    before = state(batch)
    with pytest.raises(ValueError):
        use(batch, player=1, slot=1)
    assert_same_state(batch, before)
    batch.resolve_bounces(ids([0]), ids([1]), ids([0]))
    batch.step_defenses(ids([0]), ids([0]), ids([4]))
    use(batch, player=1, slot=1)
    assert batch.resource_snapshot()[0, 1, 0] == 45


def test_eliminated_player_is_not_revived_and_rotation_skips_them():
    batch = game(hp=10)
    deal(batch, [0], [6])
    deal(batch, [0], [191], player=1)
    deal(batch, [0], [191], player=2)
    batch.begin_card_attacks(ids([0]), ids([0]), ids([0]), ids([1]))
    batch.step_defenses(ids([0]), ids([1]), ids([4]))
    assert batch.turn_snapshot()[0, 1] == 2
    before = state(batch)
    with pytest.raises(ValueError):
        use(batch, player=1)
    assert_same_state(batch, before)
    use(batch, player=2)
    np.testing.assert_array_equal(batch.resource_snapshot()[0, :, 0], [10, 0, 15])
    assert batch.turn_snapshot()[0, 1] == 0


def test_guardian_resources_and_curses_are_preserved_across_utility_turns():
    batch = game(players=2, mp=0)
    deal(batch, [0, 0], [235, 195])
    batch.summon(ids([0, 0]), ids([0, 1]), ids([1, 2]), ids([0, 1]), ids([1, 2]))
    batch.begin_effects(ids([0]), ids([0]), ids([1]), ids([0]), ids([0]), ids([0]))
    assert batch.resource_snapshot()[0, 0, 1] == 10
    batch.begin_effects(ids([0]), ids([1]), ids([2]), ids([0]), ids([0]), ids([0]))
    assert batch.turn_snapshot()[0, 0] == 0  # Direct guardian curse resolves immediately.
    assert batch.resource_snapshot()[0, 0, 3] == 2
    use(batch)
    np.testing.assert_array_equal(batch.resource_snapshot()[0, 0], [50, 3, 0, 2])
    assert batch.resolved_effect_count == 2
    assert batch.utility_use_count == 1


def test_empty_native_calls_do_not_change_any_state():
    batch = game()
    before = state(batch)
    batch.use_utility_cards(ids([]), ids([]), ids([]))
    batch.deal_cards(ids([]), ids([]), ids([]), ids([]), ids([]))
    assert_same_state(batch, before)


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [[191, 0, 5, 0]],
        [[191, 0, 5, 0, 0], [191, 0, 10, 0, 0]],
        [[113, 0, 5, 0, 0]],
        [[6, 0, 5, 0, 0]],
        [[0, 0, 5, 0, 0]],
        [[2**53, 0, 5, 0, 0]],
        [[191, -1, 5, 0, 0]],
        [[191, 2, 5, 0, 0]],
        [[191, 0, 0, 0, 0]],
        [[191, 0, 101, 0, 0]],
        [[191, 0, 5, 2, 0]],
        [[191, 0, 5, 0, 1]],
        [[191, 0, 5, 1, 0]],
        [[191, 0, 5, 1, 101]],
        [[191, 1, 5, 1, 1]],
    ],
)
def test_invalid_profiles_rejected(profiles):
    # [] needs a valid 2-D ndarray to test the explicit empty-profile check.
    profiles = np.empty((0, 5), dtype=np.int64) if profiles == [] else profiles
    with pytest.raises(ValueError):
        game(profiles=profiles)


def test_mixed_deal_is_atomic_and_defense_only_does_not_accept_utilities():
    batch = game()
    before = state(batch)
    with pytest.raises(ValueError):
        deal(batch, [0, 1], [191, 999], slots=[0, 0])
    assert_same_state(batch, before)
    with pytest.raises(ValueError):
        batch.deal_defenses(ids([0]), ids([0]), ids([0]), ids([100]), ids([191]))
    assert_same_state(batch, before)
    deal(batch, [0, 0, 0], [113, 6, 191])
    np.testing.assert_array_equal(batch.ready_action_masks()[0], [False, True, True, False, True])
    # Utility slot must not bypass the explicit utility path.
    before = state(batch)
    with pytest.raises(ValueError):
        batch.begin_card_attacks(ids([0]), ids([0]), ids([2]), ids([1]))
    assert_same_state(batch, before)


def test_bounds_reset_and_lifetime_counters():
    batch = game(max_turns=1)
    deal(batch, [0, 1], [191, 235], slots=[0, 0])
    use(batch)
    assert batch.turn_snapshot()[0, 0] == 3
    assert not np.any(batch.actor_hand_snapshot()[0])
    assert not np.any(batch.utility_action_masks()[0])
    assert not np.any(batch.ready_action_masks()[0])
    before = state(batch)
    with pytest.raises(ValueError):
        use(batch)
    assert_same_state(batch, before)
    batch.reset_environments(ids([0]))
    np.testing.assert_array_equal(batch.resource_snapshot()[0], [[40, 10, 0, 0]] * 3)
    assert not np.any(batch.inventory_snapshot()[0])
    assert batch.inventory_snapshot()[1, 0, 0, 1] == 235
    assert batch.utility_use_count == 1
    assert batch.hp_gained == 5
    deal(batch, [0], [195])
    use(batch)
    assert batch.utility_use_count == 2
    assert batch.hp_gained == 5 and batch.mp_gained == 5


def test_batched_cpp_matches_a_simple_resource_oracle():
    batch = game(size=512, players=9, hp=93, mp=7)
    models = [PROFILES[index % 8][0] for index in range(512)]
    deal(batch, list(range(512)), models, slots=[0] * 512)
    before = batch.resource_snapshot()
    use(batch, list(range(512)))
    expected = before.copy()
    consumed = miracles = spent = hp_gain = mp_gain = 0
    for env in range(512):
        _, resource, gain, reusable, cost = PROFILES[env % 8]
        effective = min(gain, 100 - expected[env, 0, resource])
        expected[env, 0, 1] -= cost
        expected[env, 0, resource] += effective
        consumed += 1 - reusable
        miracles += reusable
        spent += cost
        hp_gain += effective if resource == 0 else 0
        mp_gain += effective if resource == 1 else 0
    np.testing.assert_array_equal(batch.resource_snapshot(), expected)
    np.testing.assert_array_equal(batch.turn_snapshot()[:, 1:4], [[1, 1, 1]] * 512)
    assert (
        batch.consumed_card_count,
        batch.miracle_cast_count,
        batch.mp_spent,
        batch.hp_gained,
        batch.mp_gained,
    ) == (consumed, miracles, spent, hp_gain, mp_gain)


def test_factory_pins_all_eight_cards_and_keeps_old_schema_unchanged():
    created = create_provisional_guardian_utility_turn_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=2,
    )
    assert created.metadata.utility_plan.profiles == PROFILES
    assert created.metadata.utility_plan.profile_sha256 == UTILITY_PROFILE_SHA256
    assert created.metadata.ruleset_id == UTILITY_RULESET_ID
    assert created.metadata.total_inventory_models == 102
    assert not created.metadata.local_training_eligible
    assert not created.metadata.full_game_training_ready
    assert not created.metadata.promotion_eligible
    assert created.batch.actor_hand_snapshot().shape == (2, 18, 11)
    old = create_provisional_guardian_turn_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=2,
    )
    assert native.GUARDIAN_TURN_KERNEL_SCHEMA_VERSION == 2
    assert native.GUARDIAN_ACTOR_HAND_SCHEMA_VERSION == 1
    assert old.batch.actor_hand_snapshot().shape == (2, 18, 9)
    assert old.batch.hand_feature_snapshot().shape == (2, 2, 18, 6)
    with pytest.raises(ValueError):
        deal(old.batch, [0], [191])


@pytest.mark.parametrize(
    "field,value",
    [
        ("catalog_sha256", "0" * 64),
        ("bible_client_sha256", "0" * 64),
        ("profiles", PROFILES[:-1]),
        ("profiles", tuple(reversed(PROFILES))),
    ],
)
def test_utility_plan_rejects_unpinned_profiles(field, value):
    plan = build_guardian_utility_plan(
        read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
    )
    payload = plan.model_dump()
    payload[field] = value
    with pytest.raises(ValueError):
        GuardianUtilityPlan.model_validate(payload)


@pytest.mark.parametrize(
    "field,value", [("ability", "boostMP"), ("cost", 8), ("abilityValue", 11), ("element", "fire")]
)
def test_cross_source_utility_disagreement_is_rejected(field, value):
    catalog = read_api_catalog_snapshot(CATALOG)
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    spring = catalog.items[234]
    changed = spring.model_copy(update={"raw": {**spring.raw, field: value}})
    catalog = catalog.model_copy(
        update={"items": (*catalog.items[:234], changed, *catalog.items[235:])}
    )
    with pytest.raises(ValueError, match="differs between sources"):
        build_guardian_utility_plan(catalog, bible)


@pytest.mark.parametrize(
    "constant,value",
    [
        ("GUARDIAN_UTILITY_TURN_KERNEL_SCHEMA_VERSION", 99),
        ("GUARDIAN_UTILITY_TURN_OBSERVATION_SCHEMA_VERSION", 99),
        ("GUARDIAN_UTILITY_ACTOR_HAND_SCHEMA_VERSION", 99),
        ("GUARDIAN_UTILITY_TURN_RULESET_ID", "not-the-reviewed-ruleset"),
        ("GUARDIAN_TURN_KERNEL_SCHEMA_VERSION", 99),
        ("GUARDIAN_TURN_OBSERVATION_SCHEMA_VERSION", 99),
        ("GUARDIAN_COMBAT_KERNEL_SCHEMA_VERSION", 99),
        ("GUARDIAN_COMBAT_OBSERVATION_SCHEMA_VERSION", 99),
        ("GUARDIAN_COMBAT_RULESET_ID", "not-the-composed-kernel"),
    ],
)
def test_factory_checks_native_identity(monkeypatch, constant, value):
    monkeypatch.setattr(native, constant, value)
    with pytest.raises(ProvisionalRuleUnavailableError, match="identity differs"):
        create_provisional_guardian_utility_turn_batch(
            catalog_path=CATALOG,
            bible_path=BIBLE,
            batch_size=1,
        )


def test_cli_requires_explicit_versioned_opt_in(monkeypatch):
    # Match other CLI tests: do not retain Click's captured/closed stderr in
    # process-global structlog configuration used by later training tests.
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "simulation",
            "guardian-batch-plan",
            "--turns",
            "--inventory-utilities",
            "--batch-size",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ruleset_id"] == UTILITY_RULESET_ID
    assert payload["total_inventory_models"] == 102
    assert payload["local_training_eligible"] is False
    rejected = runner.invoke(app, ["simulation", "guardian-batch-plan", "--inventory-utilities"])
    assert rejected.exit_code == 1
    assert "requires --turns" in rejected.output
