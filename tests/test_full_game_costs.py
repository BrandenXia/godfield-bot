"""Ordered cost waivers across utility, attack, chance and special defense."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_costs import FullGameCostPlan, build_full_game_cost_plan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
REDUCERS = [row[0] for row in PLAN.costs.profiles]


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *, size=1, players=3, profiles=PLAN.costs.profiles, decisions=4000, turns=1000, refill=False
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        initial_hp=100,
        initial_mp=30,
        initial_cp=7,
        max_turns=turns,
        max_decisions=decisions,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        passive_profiles=ids(PLAN.passives.profiles),
        removal_profiles=ids(PLAN.removal.profiles),
        cost_reducer_profiles=ids(profiles).reshape(-1, 4) if profiles is not None else None,
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, models, *, env=0, owner=0):
    batch.seed_hand(env, owner, ids([[100 * owner + i + 1, m, 0, 0] for i, m in enumerate(models)]))


def load(batch, *, env=0, owner=0, hp=100, mp=0, cp=7, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(ids([[env, *rows[env, :4], c] for env, c in zip(envs, choices, strict=True)]))


def snapshot(batch):
    return [
        getattr(batch, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "player_observations",
            "utility_selection_observations",
            "pending_observations",
            "attack_order",
            "defense_order",
            "attack_selection_observations",
            "special_defense_observations",
            "cost_snapshot",
            "cp_utility_snapshot",
            "acquisition_snapshot",
            "revival_snapshot",
        )
    ], (
        batch.action_count,
        batch.utility_count,
        batch.mp_spent,
        batch.waived_mp,
        batch.cost_waiver_count,
        batch.consumed_count,
        batch.miracle_use_count,
        batch.automatic_gift_count,
    )


def same(a, b):
    assert a[1] == b[1]
    for first, second in zip(a[0], b[0], strict=True):
        np.testing.assert_array_equal(first, second)


@pytest.mark.parametrize("reducer", REDUCERS)
@pytest.mark.parametrize("model,cost", [(235, 7), (236, 5), (237, 2), (238, 5)])
def test_all_reducers_pay_all_current_utility_miracles_only_on_confirmation(reducer, model, cost):
    batch = game(refill=True)
    seed(batch, [model, reducer, 191])
    load(batch, hp=40, mp=0, cp=0, illness=3, mask=15)
    batch.start_environments(ids([0]))
    assert bool(batch.choice_masks()[0, 2]) == (reducer == 46)  # Staff has its real ATK12 role.
    before = batch.diagnostic_players().copy()
    step(batch, [1])
    assert batch.utility_selection_observations()[0, [0, 3]].tolist() == [1, cost]
    assert not batch.choice_masks()[0, 0] and batch.choice_masks()[0, 2]
    np.testing.assert_array_equal(before, batch.diagnostic_players())
    assert batch.utility_count == batch.mp_spent == batch.cost_waiver_count == 0
    assert np.count_nonzero(batch.pending_observations()) == 0
    assert np.count_nonzero(batch.chance_observations()) == 0
    step(batch, [2])
    assert batch.utility_selection_observations()[0, 3] == 0
    assert batch.choice_masks()[0, 0]
    assert batch.utility_count == batch.cost_waiver_count == 0
    step(batch, [0])
    assert batch.cost_snapshot()[0].tolist() == [1, cost, 1, 0, 0]
    assert batch.waived_mp == cost and batch.cost_waiver_count == 1
    assert batch.utility_count == batch.miracle_use_count == batch.consumed_count == 1
    assert batch.mp_spent == batch.attack_count == batch.attack_component_count == 0
    assert batch.diagnostic_players()[0, 0, 1] == 0
    assert batch.diagnostic_players()[0, 0, 2] == (10 if model == 236 else 0)
    assert batch.diagnostic_players()[0, 0, 5] == 1
    assert batch.automatic_gift_count == 2
    assert np.count_nonzero(batch.utility_selection_observations()) == 0


@pytest.mark.parametrize("reducer", REDUCERS)
def test_all_reducers_free_standalone_attack_miracle_without_adding_atk_or_element(reducer):
    batch = game()
    load(batch)
    seed(batch, [215, reducer])
    batch.start_environments(ids([0]))
    for choice in (1, 2):
        step(batch, [choice])
    assert batch.attack_selection_observations()[0, :4].tolist() == [2, 10, 1, 0]
    for choice in (0, 20, 0):
        step(batch, [choice])
    assert batch.hp_damage == 10 and batch.mp_spent == 0
    assert batch.cost_snapshot()[0].tolist() == [1, 5, 0, 1, 0]
    assert batch.consumed_count == batch.miracle_use_count == 1
    assert batch.diagnostic_players()[0, 0, 2] == 7  # Price is not use cost.


@pytest.mark.parametrize("model", [row[0] for row in PLAN.combat.chance_profiles if row[0] >= 210])
@pytest.mark.parametrize("reducer", REDUCERS)
def test_reducer_exception_applies_to_automatic_target_chance_miracles(model, reducer):
    batch = game()
    load(batch)
    for owner in (1, 2):
        load(batch, owner=owner, mask=8)
    seed(batch, [model, reducer])
    batch.start_environments(ids([0]))
    for choice in (1, 2, 0, 0):
        step(batch, [choice])
    cost = next(row[4] for row in PLAN.combat.attack_profiles if row[0] == model)
    assert batch.cost_snapshot()[0].tolist() == [1, cost, 0, 1, 0]
    assert batch.chance_count == batch.chance_hit_count == 1
    assert batch.mp_spent == 0 and batch.consumed_count == batch.miracle_use_count == 1
    assert batch.diagnostic_players()[0, 0, 5] == 1


@pytest.mark.parametrize("reducer", REDUCERS)
@pytest.mark.parametrize("model,incoming,cost", [(233, 35, 6), (234, 215, 5)])
def test_reducers_waive_special_defense_without_violating_exclusive_response(
    reducer, model, incoming, cost
):
    batch = game()
    seed(batch, [incoming])
    seed(batch, [model, reducer, 130], owner=1)
    load(batch, owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1):
        step(batch, [choice])
    assert not batch.choice_masks()[0, 0]
    assert batch.choice_masks()[0, 2]
    step(batch, [2])
    assert batch.choice_masks()[0, 0] and not batch.choice_masks()[0, 3]
    assert batch.special_defense_observations()[0, 4] == 0
    step(batch, [0])
    assert batch.cost_snapshot()[0].tolist() == [1, cost, 0, 0, 1]
    assert batch.diagnostic_players()[0, 1, 1] == 0
    assert batch.consumed_count >= 1 and batch.miracle_use_count >= 1
    if batch.episode_snapshot()[0, 3] == 4:
        step(batch, [0])
    assert batch.diagnostic_players()[0, 0, 5] == 1
    assert batch.diagnostic_players()[0, 1, 5] == 0


@pytest.mark.parametrize(
    "model,attack,defense", [(46, 12, 0), (143, 0, 6), (163, 0, 9), (173, 0, 12)]
)
def test_reducers_keep_their_independent_standalone_combat_role(model, attack, defense):
    batch = game()
    seed(batch, [model if attack else 35])
    if not attack:
        seed(batch, [model], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20):
        step(batch, [choice])
    if not attack:
        step(batch, [1])
        assert batch.pending_observations()[0, 6] == defense
    step(batch, [0])
    assert batch.hp_damage == (attack if attack else max(0, 10 - defense))
    assert batch.cost_waiver_count == batch.waived_mp == 0


def test_multiple_adjacent_waivers_and_undo_prunes_orphan_reducer_in_display_order():
    batch = game()
    load(batch)
    seed(batch, [35, 210, 204, 217, 143])
    batch.start_environments(ids([0]))
    for choice in (1, 2, 3, 4, 5):
        step(batch, [choice])
    assert batch.attack_selection_observations()[0, :4].tolist() == [5, 22, 0, 0]
    step(batch, [2])
    assert batch.attack_order()[0, :4].tolist() == [1, 4, 5, 0]
    assert batch.selected_attacks()[0, :5].tolist() == [True, False, False, True, True]
    assert batch.attack_selection_observations()[0, :4].tolist() == [3, 20, 0, 0]
    for choice in (0, 20, 0):
        step(batch, [choice])
    assert batch.cost_snapshot()[0].tolist() == [1, 7, 0, 1, 0]
    assert batch.hp_damage == 20 and batch.mp_spent == 0


def test_multiple_waivers_are_each_committed_once_and_no_global_turn_discount():
    batch = game()
    load(batch)
    seed(batch, [35, 210, 204, 217, 143])
    batch.start_environments(ids([0]))
    for choice in (1, 2, 3, 4, 5, 0, 20, 0):
        step(batch, [choice])
    assert batch.cost_snapshot()[0].tolist() == [2, 9, 0, 2, 0]
    assert batch.mp_spent == 0 and batch.hp_damage == 22
    assert batch.consumed_count == 3 and batch.miracle_use_count == 2
    assert batch.attack_component_count == 5


def test_unaffordable_defense_at_toggle_limit_has_undo_escape_and_prunes_attachment():
    batch = game()
    curtain = next(row[0] for row in PLAN.combat.defense_effect_profiles if row[1] == 5)
    seed(batch, [35])
    seed(batch, [curtain, 233, 204], owner=1)
    load(batch, owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 2):
        step(batch, [choice])
    for _ in range(62):
        step(batch, [3])
    assert batch.pending_observations()[0, 8] == 64
    assert not batch.choice_masks()[0, 0]
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [1, 2]
    step(batch, [2])
    assert batch.defense_order()[0, :3].tolist() == [1, 0, 0]
    assert batch.choice_masks()[0, 0]
    step(batch, [0])
    assert batch.cost_waiver_count == batch.mp_spent == 0
    assert batch.hp_damage == 10


def test_cost_snapshot_is_owned_read_only_and_epoch_reset_preserves_lifetime_only():
    batch = game(turns=1)
    load(batch)
    seed(batch, [236, 204])
    batch.start_environments(ids([0]))
    old = batch.cost_snapshot()
    with pytest.raises(ValueError):
        old[0, 0] = 1
    for choice in (1, 2, 0):
        step(batch, [choice])
    assert np.count_nonzero(old) == 0
    assert batch.cost_waiver_count == 1 and batch.waived_mp == 5
    batch.reset_environments(ids([0]))
    assert np.count_nonzero(batch.cost_snapshot()) == 0
    assert batch.cost_waiver_count == 1 and batch.waived_mp == 5


def test_unaffordable_selection_at_toggle_limit_retains_cancel_escape_and_global_bound():
    batch = game(decisions=66)
    seed(batch, [236, 204])
    load(batch)
    batch.start_environments(ids([0]))
    step(batch, [1])
    for _ in range(62):
        step(batch, [2])
    assert batch.attack_selection_observations()[0, 4] == 63
    step(batch, [2])  # Attached at action 64; confirm can finish, no other toggles.
    assert batch.choice_masks()[0, 0]
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]
    # Another episode reaches the same limit with its reducer removed.
    other = game(decisions=66)
    seed(other, [35, 210, 204])
    load(other)
    other.start_environments(ids([0]))
    for choice in (1, 2):
        step(other, [choice])
    for _ in range(62):
        step(other, [3])
    assert not other.choice_masks()[0, 0]
    assert np.flatnonzero(other.choice_masks()[0]).tolist() == [1]
    step(other, [1])
    assert other.episode_snapshot()[0, 3] == 1
    step(other, [1])
    assert other.episode_snapshot()[0, 3:7].tolist() == [13, 0, 4, -1]
    assert other.cost_waiver_count == other.mp_spent == other.utility_count == 0


def test_flash_prevents_attaching_second_card_but_undo_keeps_unaffordable_defense_live():
    batch = game()
    seed(batch, [35])
    seed(batch, [233, 204], owner=1)
    load(batch, owner=1, mask=4)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1):
        step(batch, [choice])
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [1]
    step(batch, [1])
    assert batch.choice_masks()[0, 0]
    step(batch, [0])
    assert batch.hp_damage == 10 and batch.cost_waiver_count == 0


@pytest.mark.parametrize("failure", ["hidden-reducer", "hidden-leader", "decision", "duplicate"])
def test_late_failure_rolls_back_waiver_credit_tick_receipts_and_corrected_retry(failure):
    first, reference = game(size=2, refill=True), game(size=2, refill=True)
    for batch in (first, reference):
        for env in (0, 1):
            seed(batch, [236, 204], env=env)
            load(batch, env=env)
        if failure == "hidden-reducer":
            batch.seed_hand(1, 0, ids([[1, 236, 0, 0], [2, 191, 204, 0]]))
        if failure == "hidden-leader":
            batch.seed_hand(1, 0, ids([[1, 215, 236, 0], [2, 204, 0, 0]]))
        batch.start_environments(ids([0, 1]))
        step(batch, [1, 1])
        step(batch, [2, 2])
    before = snapshot(first)
    episodes = first.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in (0, 1)])
    if failure == "decision":
        commands[1, 2] += 1
    if failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        first.step(commands)
    same(snapshot(first), before)
    step(first, [0], [0])
    step(reference, [0], [0])
    same(snapshot(first), snapshot(reference))
    assert first.cost_snapshot()[0].tolist() == [1, 5, 1, 0, 0]
    assert first.automatic_gift_count == 2


def test_raw_omission_preserves_old_immediate_utility_and_old_affordability():
    batch = game(profiles=None)
    seed(batch, [236])
    load(batch, mp=5)
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.utility_count == 1 and batch.mp_spent == 5
    assert np.count_nonzero(batch.cost_snapshot()) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((46, 1, 11, 0),)},
        {"profile_fields": ("x",)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"waiver": "whole-turn-free"},
        {"effect_count": 6},
        {"official_compound_timing_verified": True},
        {"promotion_eligible": True},
    ],
)
def test_cost_plan_pins_rules_and_never_claims_full_validation(change):
    with pytest.raises(ValidationError):
        FullGameCostPlan.model_validate(PLAN.costs.model_dump() | change)


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(46, 2, 12, 0)],
        [(46, 1, 0, 0)],
        [(143, 2, 1, 6)],
        [(204, 3, 0, 1)],
        [(204, 3, 0, 0), (204, 3, 0, 0)],
        [(215, 4, 10, 0)],
        [(191, 3, 0, 0)],
        [(46, 1, 65536, 0)],
        [(143, 2, 0, -1)],
        [(204, 3, 0, 0), (3, 5, 0, 0)],
    ],
)
def test_raw_reducer_shapes_roles_collisions_and_values_fail_closed(profiles):
    with pytest.raises(ValueError, match="cost reducer"):
        game(profiles=profiles)


def test_source_builder_revalidates_unchecked_copies():
    catalog = read_api_catalog_snapshot(CATALOG)
    item = next(item for item in catalog.items if item.model_id == 204)
    changed = item.model_copy(update={"raw": dict(item.raw) | {"ability": "boostHP"}})
    catalog = catalog.model_copy(
        update={"items": tuple(changed if i.model_id == 204 else i for i in catalog.items)}
    )
    with pytest.raises(ValueError):
        build_full_game_cost_plan(catalog, BibleSnapshot.model_validate_json(BIBLE.read_text()))


@pytest.fixture(scope="module")
def metadata():
    return create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1
    ).metadata


def test_current_contract_describes_cost_exceptions_and_never_claims_readiness(metadata):
    assert "adjacent-miracle-waiver" in metadata.chance_policy
    assert "optional-miracle-waiver" in metadata.special_selection
    assert "otherwise-leader-cancel" in metadata.attack_limit
    assert "otherwise-selected-undo" in metadata.defense_limit
    assert metadata.cost_snapshot_fields == (
        "waivers",
        "waived_mp",
        "utility_waivers",
        "attack_waivers",
        "defense_waivers",
    )
    assert metadata.plan.costs == PLAN.costs
    assert not metadata.full_game_training_ready and not metadata.promotion_eligible


@pytest.mark.parametrize(
    "change",
    [
        {
            "chance_policy": (
                "standalone-no-additions-native-roll-on-confirm-no-defense-on-miss-provisional"
            )
        },
        {
            "special_selection": (
                "filter-prefix-then-exclusive-special-or-compatible-armor-source-pinned"
            )
        },
        {"attack_limit": "confirm-only-after-64-selections-toggles-provisional"},
        {"defense_limit": "confirm-only-after-64-toggles-not-silent-auto-defense"},
        {"cost_snapshot_fields": ("hidden-actual-model",)},
        {"utility_selection_observation_fields": ("hidden-actual-effect",)},
        {"cost_limit_escape": "no-cancel"},
        {"cost_reservation": "cannot-select-at-zero-mp"},
        {"utility_command_timing": "pay-before-confirm"},
    ],
)
def test_current_contract_rejects_obsolete_and_unsafe_boundaries(metadata, change):
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(metadata.model_dump() | change)
