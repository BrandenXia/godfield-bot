"""Ordered source-pinned attacks execute on the joined native state, not a helper."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
    execute_full_game_commands,
    full_game_decision_contexts,
)
from godfield_bot.full_game_combat_plan import FullGameCombatPlan
from godfield_bot.full_game_protocol import FullGameCommand

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *,
    size=1,
    players=3,
    capacity=18,
    mp=80,
    boosts=None,
    attacks=None,
    refill=False,
    prayer=False,
    max_turns=1000,
    max_decisions=4000,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity,
        67,
        max_turns,
        max_decisions,
        40,
        mp,
        0,
        ids(PLAN.combat.attack_profiles if attacks is None else attacks),
        ids(
            [
                row
                for row in PLAN.combat.armor_profiles
                if attacks is None
                or dict(PLAN.inventory.profiles)[row[0]] == 2
                or row[0] in {attack[0] for attack in attacks}
            ]
        ),
        ids([[191, 1]]) if refill or prayer else None,
        0,
        refill,
        prayer,
        capacity,
        refill or prayer,
        ids(PLAN.combat.boost_profiles if boosts is None else boosts).reshape(-1, 6),
    )


def seed(batch, cards, *, env=0, owner=0):
    batch.seed_hand(env, owner, ids(cards).reshape(-1, 4))


def load(batch, *, env=0, owner=0, hp=40, mp=80, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    envs = list(range(len(choices))) if envs is None else envs
    ep = batch.episode_snapshot()
    batch.step(
        ids(
            [[env, *ep[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def hand(batch, owner=0, env=0):
    cards = batch.diagnostic_inventory()[env, owner]
    return cards[cards[:, 0] != 0]


def state(batch):
    arrays = [
        getattr(batch, view)()
        for view in (
            "episode_snapshot",
            "diagnostic_inventory",
            "diagnostic_players",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "selected_attacks",
            "attack_order",
            "attack_selection_observations",
            "selected_defenses",
            "pending_observations",
            "acquisition_snapshot",
        )
    ]
    counters = [
        getattr(batch, key)
        for key in (
            "action_count",
            "attack_toggle_count",
            "attack_confirm_count",
            "attack_component_count",
            "attack_count",
            "resolved_attack_count",
            "hp_damage",
            "mp_spent",
            "consumed_count",
            "miracle_use_count",
            "automatic_gift_count",
            "suppressed_gift_count",
            "overflow_count",
            "darkness_finish_count",
        )
    ]
    return arrays, counters


def same(batch, before):
    now = state(batch)
    for first, second in zip(now[0], before[0], strict=True):
        np.testing.assert_array_equal(first, second)
    assert now[1] == before[1]


def element(first, added):
    if first == added:
        return first
    if first == 5 and 1 <= added <= 4:
        return added
    if added == 5 and 1 <= first <= 4:
        return first
    return 0


@pytest.mark.parametrize("profile", PLAN.combat.boost_profiles)
def test_all_additions_join_costs_order_consumption_retention_and_refill(profile):
    model, power, elem, cost, kind, _ = profile
    batch = game(refill=True)
    seed(batch, [(1, 35, 0, 0), (2, model, 0, 0), (3, 194, 0, 0)])
    load(batch, illness=1)
    batch.start_environments(ids([0]))
    before_hand = hand(batch).copy()
    step(batch, [1])
    assert batch.episode_snapshot()[0, 3] == 2
    assert batch.attack_order()[0, :3].tolist() == [1, 0, 0]
    assert batch.attack_selection_observations()[0].tolist() == [1, 10, 0, 0, 1]
    assert batch.choice_masks()[0, 2]
    step(batch, [2])
    total = 20 if kind == 2 else 10 + power
    final_element = elem if kind == 1 else element(0, elem)
    assert batch.attack_selection_observations()[0].tolist() == [2, total, final_element, cost, 2]
    assert batch.attack_order()[0, :3].tolist() == [1, 2, 0]
    np.testing.assert_array_equal(before_hand, hand(batch))
    assert batch.mp_spent == batch.consumed_count == batch.automatic_gift_count == 0
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 3
    step(batch, [20])
    reusable = dict(PLAN.inventory.profiles)[model] == 4
    assert batch.pending_observations()[0, 3:6].tolist() == [total, final_element, 0]
    assert batch.diagnostic_players()[0, 0, 1] == 80 - cost
    assert batch.consumed_count == (1 if reusable else 2)
    assert batch.miracle_use_count == int(reusable)
    assert hand(batch).tolist() == [[3, 194, 0, 0]] + ([[2, model, 0, 1]] if reusable else [])
    assert batch.acquisition_snapshot()[0, 0, 0] == 2
    assert batch.automatic_gift_count == 0 and batch.attack_component_count == 2
    assert not np.any(batch.selected_attacks()) and not np.any(batch.attack_order())
    step(batch, [0])
    assert batch.automatic_gift_count == 2
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.diagnostic_players()[0, 0, 0] == 39
    assert batch.attack_toggle_count == batch.attack_confirm_count == 1


@pytest.mark.parametrize("profile", PLAN.combat.boost_profiles)
def test_standalone_lead_restrictions_match_category_and_positive_atk(profile):
    model, power, elem, cost, _, can_lead = profile
    batch = game()
    seed(batch, [(1, model, 0, 0), (2, 9, 0, 0)])
    batch.start_environments(ids([0]))
    assert bool(batch.choice_masks()[0, 1]) == bool(can_lead)
    if not can_lead:
        before = state(batch)
        with pytest.raises(ValueError, match="unavailable"):
            step(batch, [1])
        same(batch, before)
        return
    step(batch, [1])
    assert batch.attack_selection_observations()[0, 1:4].tolist() == [power, elem, cost]
    is_miracle = dict(PLAN.inventory.profiles)[model] == 4
    assert bool(batch.choice_masks()[0, 2]) == (not is_miracle)
    for choice in (0, 20, 0):
        step(batch, [choice])
    assert batch.mp_spent == cost and batch.attack_component_count == 1
    assert batch.hp_damage == (40 if elem == 6 else power)


@pytest.mark.parametrize("model", [211, 215, 218, 210, 217])
def test_base_and_additive_miracles_cannot_receive_weapon_armor_sundry_or_miracle_additions(model):
    batch = game()
    seed(batch, [(1, model, 0, 0), (2, 9, 0, 0), (3, 124, 0, 0), (4, 203, 0, 0), (5, 210, 0, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0, 1]  # Confirm or cancel leader.
    before = state(batch)
    with pytest.raises(ValueError):
        step(batch, [2])
    same(batch, before)


@pytest.mark.parametrize("first,second", [(a, b) for a in range(7) for b in range(7)])
def test_all_49_element_pairs_use_bible_mixing_in_preview_and_actual_cast(first, second):
    batch = game(attacks=[(6, 10, first, 0, 0)], boosts=[(9, 3, second, 0, 0, 1)])
    seed(batch, [(1, 6, 0, 0), (2, 9, 0, 0)])
    batch.start_environments(ids([0]))
    for choice in (1, 2, 0):
        step(batch, [choice])
    assert batch.attack_selection_observations()[0, 2] == element(first, second)
    step(batch, [20])
    assert batch.pending_observations()[0, 4] == element(first, second)


@pytest.mark.parametrize(
    "order,expected",
    [
        ((2, 3), (23, 1)),
        ((3, 2), (25, 0)),
    ],
)
def test_aura_and_wand_compose_in_selection_order_and_undo_recomputes(order, expected):
    batch = game()
    seed(batch, [(1, 35, 0, 0), (2, 231, 0, 0), (3, 66, 0, 0), (4, 63, 0, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    for choice in (*order, 4):
        step(batch, [choice])
    assert batch.attack_selection_observations()[0, 1:3].tolist() == list(expected)
    step(batch, [order[0]])
    # Retained order, not slot-sorted recomputation, is the public contract.
    assert batch.attack_order()[0, :4].tolist() == [1, order[1], 4, 0]
    step(batch, [order[0]])
    assert batch.attack_order()[0, :4].tolist() == [1, order[1], 4, order[0]]
    for choice in (0, 20):
        step(batch, [choice])
    assert batch.mp_spent == 6


def test_leader_undo_cancels_entire_composition_without_paying_consuming_or_ticking():
    batch = game()
    seed(batch, [(1, 35, 0, 0), (2, 210, 0, 0), (3, 231, 0, 0)])
    batch.start_environments(ids([0]))
    original = hand(batch).copy()
    for choice in (1, 2, 3, 1):
        step(batch, [choice])
    assert batch.episode_snapshot()[0, 3:5].tolist() == [1, 0]
    assert not np.any(batch.selected_attacks()) and not np.any(
        batch.attack_selection_observations()
    )
    assert batch.mp_spent == batch.consumed_count == batch.miracle_use_count == 0
    assert batch.action_count == 4 and batch.attack_toggle_count == 3
    np.testing.assert_array_equal(original, hand(batch))


def test_confirm_only_after_64_selection_actions_and_no_infinite_attack_toggling():
    batch = game()
    seed(batch, [(1, 35, 0, 0), (2, 9, 0, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    for _ in range(63):
        step(batch, [2])
    assert batch.attack_selection_observations()[0, 4] == 64
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]
    before = state(batch)
    with pytest.raises(ValueError):
        step(batch, [1])
    same(batch, before)
    for choice in (0, 20, 0):
        step(batch, [choice])
    assert batch.resolved_attack_count == 1 and batch.episode_snapshot()[0, 4] == 1


def test_displayed_cost_reserves_sum_and_undo_releases_affordability_without_payment():
    batch = game(mp=7)
    seed(batch, [(1, 35, 0, 0), (2, 210, 0, 0), (3, 217, 0, 0), (4, 231, 0, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [2])
    assert batch.attack_selection_observations()[0, 3] == 2
    assert not batch.choice_masks()[0, 3] and not batch.choice_masks()[0, 4]
    step(batch, [2])
    assert batch.choice_masks()[0, 3] and batch.choice_masks()[0, 4]
    assert batch.mp_spent == 0 and batch.diagnostic_players()[0, 0, 1] == 7


def test_exact_integer_limit_masks_impossible_doubling_and_never_wraps_actual_power():
    # Synthetic cheap Auras reach the numeric boundary without a fake official claim.
    batch = game(capacity=64, mp=100, attacks=[(6, 65535, 0, 0, 0)], boosts=[(231, 0, 0, 1, 2, 0)])
    seed(batch, [(1, 6, 0, 0)] + [(i + 2, 231, 0, 0) for i in range(50)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    power, additions = 65535, 0
    for choice in range(2, 52):
        if power > (2**53 - 1) // 2:
            assert not batch.choice_masks()[0, choice]
            before = state(batch)
            with pytest.raises(ValueError, match="unavailable"):
                step(batch, [choice])
            same(batch, before)
            break
        assert batch.choice_masks()[0, choice]
        step(batch, [choice])
        power *= 2
        additions += 1
        assert batch.attack_selection_observations()[0, 1] == power
    assert additions == 37 and power <= 2**53 - 1
    step(batch, [0])
    step(batch, [66])  # C+1+seat1.
    assert batch.pending_observations()[0, 3] == power
    assert batch.mp_spent == additions and batch.attack_component_count == additions + 1


def test_multiple_retained_additions_keep_selection_order_and_receive_gifts_each_reuse():
    batch = game(refill=True)
    seed(batch, [(1, 35, 0, 0), (2, 217, 0, 1), (3, 210, 0, 1), (4, 194, 0, 0)])
    batch.start_environments(ids([0]))
    for choice in (1, 3, 2, 0, 20):
        step(batch, [choice])
    assert hand(batch).tolist() == [[4, 194, 0, 0], [3, 210, 0, 1], [2, 217, 0, 1]]
    assert batch.miracle_use_count == 2 and batch.mp_spent == 9
    assert batch.automatic_gift_count == 0 and batch.acquisition_snapshot()[0, 0, 0] == 3
    step(batch, [0])
    assert batch.automatic_gift_count == 3 and hand(batch)[:, 0].tolist() == [4, 3, 2, 5, 6, 7]


def test_multi_card_receipts_preserve_miracle_order_and_apply_each_provisional_eviction():
    batch = game(refill=True)
    seed(
        batch,
        [(1, 35, 0, 0), (2, 217, 0, 0), (3, 210, 0, 0)] + [(i, 191, 0, 0) for i in range(4, 19)],
    )
    batch.start_environments(ids([0]))
    for choice in (1, 3, 2, 0, 20, 0):
        step(batch, [choice])
    assert hand(batch)[:, 0].tolist() == [*range(6, 19), 3, 2, 19, 20, 21]
    assert batch.overflow_count == 2 and batch.consumed_count == 1
    assert batch.miracle_use_count == 2 and batch.automatic_gift_count == 3
    assert batch.acquisition_snapshot()[0, 0].tolist() == [0, 3, 2]


def test_hidden_actual_integer_overflow_does_not_change_public_mask_or_partially_pay():
    batch = game(
        capacity=64,
        mp=100,
        attacks=[(6, 65535, 0, 0, 0), (35, 1, 0, 0, 0)],
        boosts=[(231, 0, 0, 1, 2, 0)],
    )
    seed(batch, [(1, 6, 35, 0)] + [(i + 2, 231, 0, 0) for i in range(38)])
    batch.start_environments(ids([0]))
    for choice in range(1, 40):
        assert batch.choice_masks()[0, choice]
        step(batch, [choice])
    assert batch.attack_selection_observations()[0, 1] == 2**38
    step(batch, [0])
    before = state(batch)
    with pytest.raises(ValueError, match="integer bound"):
        step(batch, [66])
    same(batch, before)


@pytest.mark.parametrize("bad_env", [0, 1])
def test_composition_source_identity_errors_are_atomic_across_target_cast_batch(bad_env):
    batch = game(size=2)
    for env in range(2):
        seed(batch, [(1, 35, 0, 0), (2, 210, 0, 0)], env=env)
    seed(batch, [(1, 35, 0, 0), (2, 232, 210, 0)], env=bad_env)
    batch.start_environments(ids([0, 1]))
    for choice in (1, 2, 0):
        step(batch, [choice, choice])
    before = state(batch)
    with pytest.raises(ValueError, match="actual"):
        step(batch, [20, 20])
    same(batch, before)


def test_leader_cancel_cycles_are_bounded_by_real_decision_truncation_not_fake_turns():
    batch = game(max_decisions=20)
    seed(batch, [(1, 35, 0, 0)])
    batch.start_environments(ids([0]))
    for _ in range(10):
        step(batch, [1])
        step(batch, [1])
    assert batch.episode_snapshot()[0, 3:6].tolist() == [13, 0, 4]
    assert batch.action_count == 20 and batch.attack_component_count == batch.mp_spent == 0


@pytest.mark.parametrize("failure", ["unimplemented", "hidden-cost", "unsupported-addition"])
def test_true_identity_failure_is_atomic_after_public_confirmation_without_leaking_mask(failure):
    first, second = game(mp=2), game(mp=2)
    for batch in (first, second):
        seed(batch, [(1, 35, 0, 0), (2, 210, 0, 0)])
    if failure == "unimplemented":
        seed(second, [(1, 41, 35, 0), (2, 210, 0, 0)])
    elif failure == "hidden-cost":
        seed(second, [(1, 35, 0, 0), (2, 217, 210, 0)])
    else:
        seed(second, [(1, 35, 0, 0), (2, 202, 203, 0)])
        seed(first, [(1, 35, 0, 0), (2, 203, 0, 0)])
    for batch in (first, second):
        batch.start_environments(ids([0]))
        for choice in (1, 2, 0):
            step(batch, [choice])
    for view in (
        "choice_masks",
        "actor_hands",
        "attack_order",
        "attack_selection_observations",
        "pending_observations",
    ):
        np.testing.assert_array_equal(getattr(first, view)(), getattr(second, view)())
    before = state(second)
    with pytest.raises(ValueError, match="actual"):
        step(second, [20])
    same(second, before)
    step(first, [20])


@pytest.mark.parametrize("limit", ["selection", "confirmation", "cast", "resolution"])
def test_decision_limits_do_not_fabricate_completed_turns_or_early_gifts(limit):
    decisions = {"selection": 2, "confirmation": 3, "cast": 4, "resolution": 5}[limit]
    batch = game(max_decisions=decisions, refill=True)
    seed(batch, [(1, 35, 0, 0), (2, 210, 0, 0)])
    batch.start_environments(ids([0]))
    for choice in (1, 2, 0, 20, 0)[:decisions]:
        step(batch, [choice])
    assert batch.episode_snapshot()[0, 3] == 13
    assert batch.episode_snapshot()[0, 4] == int(limit == "resolution")
    assert batch.automatic_gift_count == 0
    assert batch.suppressed_gift_count == (2 if limit in ("cast", "resolution") else 0)
    assert not np.any(batch.selected_attacks()) and not np.any(batch.attack_order())
    assert not np.any(batch.attack_selection_observations()) and not np.any(
        batch.pending_observations()
    )


@pytest.mark.parametrize("armor,dead", [((), True), ((148,), False), ((130,), True)])
def test_darkness_positive_damage_is_lethal_but_full_armor_block_is_not(armor, dead):
    batch = game()
    seed(batch, [(1, 86, 0, 0)])  # Darkness ATK5.
    seed(batch, [(10 + i, model, 0, 0) for i, model in enumerate(armor)], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20):
        step(batch, [choice])
    for index in range(len(armor)):
        step(batch, [index + 1])
    step(batch, [0])
    assert batch.diagnostic_players()[0, 1, 0] == (0 if dead else 40)
    assert batch.darkness_finish_count == int(dead)
    assert batch.hp_damage == (40 if dead else 0)


def test_mixed_phase_late_error_rolls_back_order_cost_consumption_and_receipt_rng():
    batch = game(size=2, refill=True)
    for env in range(2):
        seed(batch, [(1, 35, 0, 0), (2, 210, 0, 0)], env=env)
    batch.start_environments(ids([0, 1]))
    step(batch, [1, 1])
    step(batch, [2, 2])
    step(batch, [0], [0])
    before = state(batch)
    episodes = batch.episode_snapshot()
    bad = ids([[0, *episodes[0, :4], 20], [1, *episodes[1, :4], 19]])
    with pytest.raises(ValueError):
        batch.step(bad)
    same(batch, before)
    step(batch, [20], [0])
    assert batch.attack_component_count == 2 and batch.mp_spent == 2


def test_public_order_snapshots_reset_and_native_command_protocol_recheck():
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    batch = configured.batch
    seed(batch, [(1, 35, 0, 0), (2, 9, 0, 0)])
    batch.start_environments(ids([0]))
    for choice in (1, 2, 0, 20, 0):
        context = full_game_decision_contexts(configured)[0]
        command = FullGameCommand(
            **context.model_dump(exclude={"legal_choice_ids"}), choice_id=choice
        )
        execute_full_game_commands(configured, [command])
        if choice == 2:
            selected, order, preview = (
                batch.selected_attacks(),
                batch.attack_order(),
                batch.attack_selection_observations(),
            )
    assert (
        not selected.flags.writeable and not order.flags.writeable and not preview.flags.writeable
    )
    assert order[0, :2].tolist() == [1, 2]
    assert batch.attack_component_count == 2
    batch.reset_environments(ids([0]))
    assert not np.any(batch.attack_order()) and not np.any(batch.attack_selection_observations())
    assert order[0, :2].tolist() == [1, 2] and batch.attack_component_count == 2


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(9, 1, 0, 0, 0)],
        [(9, 1, 0, 0, 0, 1)] * 2,
        [(1, 1, 0, 0, 0, 1)],
        [(9, 0, 0, 0, 0, 1)],
        [(9, 1, 7, 0, 0, 1)],
        [(9, 1, 0, 2, 0, 1)],
        [(210, 2, 1, 0, 0, 1)],
        [(9, 1, 0, 0, 0, 2)],
        [(203, 10, 0, 0, 0, 1)],
        [(9, 1, 0, 0, 3, 1)],
        [(231, 0, 0, 6, 2, 1)],
    ],
)
def test_native_composition_profiles_fail_closed(profiles):
    with pytest.raises((ValueError, TypeError)):
        game(boosts=profiles)


@pytest.mark.parametrize(
    "changes",
    [
        {"boost_profiles": ()},
        {"boost_fields": ("hidden_model",)},
        {"combat_effect_count": 237},
        {"excluded_additive_models": ()},
        {"composition_kinds": ("sum-only",)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
    ],
)
def test_source_plan_rejects_restricted_forged_composition_contracts(changes):
    with pytest.raises(ValidationError):
        FullGameCombatPlan.model_validate({**PLAN.combat.model_dump(), **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"attack_selection_fields": ("actual_cost",)},
        {"max_attack_actions": 10000},
        {"max_exact_attack": 2**63 - 1},
        {"attack_limit": "unbounded"},
        {"kernel_schema_version": 3},
        {"local_training_eligible": True},
        {"promotion_eligible": True},
    ],
)
def test_metadata_cannot_claim_old_versions_unbounded_selection_or_readiness(changes):
    conf = create_development_full_game_batch(catalog_path=CATALOG, bible_path=BIBLE, batch_size=1)
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate({**conf.metadata.model_dump(), **changes})
