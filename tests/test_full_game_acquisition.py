"""Native receipts, complete gift weights and approved provisional FIFO overflow."""

import hashlib
import json
from collections import Counter
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
from godfield_bot.full_game_acquisition import (
    FULL_GAME_GIFT_SHA256,
    FullGameAcquisitionPlan,
    build_full_game_acquisition_plan,
)

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
CAT = read_api_catalog_snapshot(CATALOG)
REF = BibleSnapshot.model_validate_json(BIBLE.read_text())
PLAN = build_full_game_plan(CAT, REF)
MAX_ID = 2**53 - 1


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *,
    size=1,
    players=3,
    capacity=18,
    gifts=((191, 1),),
    initial=0,
    refill=True,
    prayer=True,
    limit=18,
    oldest=True,
    seed=67,
    max_turns=1000,
    max_decisions=4000,
):
    # Single-model pools isolate scheduling only; never relabeled full-game pools.
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity,
        seed,
        max_turns,
        max_decisions,
        40,
        80,
        0,
        ids(PLAN.combat.attack_profiles),
        ids(PLAN.combat.armor_profiles),
        None if gifts is None else ids(gifts).reshape(-1, 2),
        initial,
        refill,
        prayer,
        limit,
        oldest,
    )


def seed(batch, cards, *, env=0, owner=0):
    batch.seed_hand(env, owner, ids(cards).reshape(-1, 4))


def load(batch, *, env=0, owner=0, hp=40, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, 80, 0, illness]]), ids([mask]))


def hand(batch, *, env=0, owner=0):
    raw = batch.diagnostic_inventory()[env, owner]
    return raw[raw[:, 0] != 0]


def step(batch, choices, envs=None):
    envs = list(range(len(choices))) if envs is None else envs
    episodes = batch.episode_snapshot()
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def snapshot(batch):
    arrays = tuple(
        getattr(batch, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "selected_defenses",
            "acquisition_snapshot",
        )
    )
    counters = tuple(
        getattr(batch, name)
        for name in (
            "action_count",
            "pass_count",
            "utility_count",
            "mp_spent",
            "gift_count",
            "consumed_count",
            "miracle_use_count",
            "restored_count",
            "attack_count",
            "resolved_attack_count",
            "defense_toggle_count",
            "hp_damage",
            "automatic_gift_count",
            "suppressed_gift_count",
            "overflow_count",
            "prayer_count",
        )
    )
    return arrays, counters


def same(batch, before):
    after = snapshot(batch)
    for a, b in zip(after[0], before[0], strict=True):
        np.testing.assert_array_equal(a, b)
    assert after[1] == before[1]


def ranks(env, seed, epoch, bound):
    """Independent SplitMix reference for the new model-only stream."""
    mask = 2**64 - 1
    state = (
        seed
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ 0xCA5A826395121157
    )
    while True:
        for _ in range(16):
            state = (state + 0x9E3779B97F4A7C15) & mask
            word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
            word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
            word ^= word >> 31
            if word >= 2**64 % bound:
                yield word % bound
                break
        else:
            raise AssertionError("reference exceeded rejection bound")


def test_complete_237_model_weights_include_held_trade_exclude_controls_and_events():
    gifts = PLAN.gifts
    assert len(gifts.model_weights) == 237 and sum(w for _, w in gifts.model_weights) == 500
    assert {m for m, _ in gifts.model_weights} == {m for m, _ in PLAN.inventory.profiles}
    assert dict(gifts.model_weights)[3] == dict(gifts.model_weights)[4] == 20
    assert dict(gifts.model_weights)[5] == 20
    assert not {1, 2} & dict(gifts.model_weights).keys()
    assert (
        hashlib.sha256(json.dumps(gifts.model_weights, separators=(",", ":")).encode()).hexdigest()
        == FULL_GAME_GIFT_SHA256
    )
    assert not gifts.full_game_training_ready and not gifts.all_gifted_effects_implemented
    totals = Counter()
    for model, weight in gifts.model_weights:
        totals[dict(PLAN.inventory.profiles)[model]] += weight
    assert dict(totals) == {1: 181, 2: 147, 3: 82, 4: 30, 5: 60}


@pytest.mark.parametrize("model,weight", PLAN.gifts.model_weights)
def test_every_held_model_can_be_sampled_natively_without_silent_effect_claim(model, weight):
    batch = game(gifts=((model, weight),), initial=9)
    batch.start_environments(ids([0]))
    assert batch.automatic_gift_count == batch.gift_count == 27
    assert batch.action_count == 0
    for owner in range(3):
        cards = hand(batch, owner=owner)
        assert cards[:, 0].tolist() == list(range(owner * 9 + 1, owner * 9 + 10))
        assert cards[:, 1].tolist() == [model] * 9
        assert not np.any(cards[:, 2:])
    assert batch.acquisition_snapshot()[0].tolist() == [[0, 9, 0]] * 3


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed_value", [0, 67, 2**64 - 1])
def test_weighted_draw_matches_independent_reference_order_and_sorted_profiles(players, seed_value):
    weights = list(PLAN.gifts.model_weights)
    batch = game(
        size=4, players=players, initial=9, gifts=tuple(reversed(weights)), seed=seed_value
    )
    batch.start_environments(ids([3, 1, 0, 2]))
    for env in range(4):
        tickets = ranks(env, seed_value, 1, 500)
        expanded = [model for model, weight in weights for _ in range(weight)]
        expected = [expanded[next(tickets)] for _ in range(players * 9)]
        observed = batch.diagnostic_inventory()[env, :, :9, 1].ravel().tolist()
        assert observed == expected


def test_only_living_seats_receive_initial_cards_and_terminal_setup_has_no_draws():
    batch = game(size=3, initial=9)
    load(batch, env=0, owner=0, hp=0)
    for owner in (0, 1):
        load(batch, env=1, owner=owner, hp=0)
    for owner in range(3):
        load(batch, env=2, owner=owner, hp=0)
    batch.start_environments(ids([0, 1, 2]))
    assert batch.automatic_gift_count == 18
    assert not len(hand(batch)) and len(hand(batch, owner=1)) == 9
    assert batch.episode_snapshot()[:, 5].tolist() == [0, 1, 2]
    assert not np.any(batch.diagnostic_inventory()[1:])
    assert not np.any(batch.acquisition_snapshot()[1:])


@pytest.mark.parametrize("failure", ["nonempty", "duplicate", "range", "exhausted"])
def test_start_is_transactional_including_late_sampling_and_instance_failure(failure):
    batch = game(size=2, initial=9)
    envs = [0, 1]
    if failure == "nonempty":
        seed(batch, [(99, 191, 0, 0)], env=1)
    elif failure == "exhausted":
        load(batch, env=1, owner=2, hp=0)
        seed(batch, [(MAX_ID, 191, 0, 0)], env=1, owner=2)
    elif failure == "duplicate":
        envs = [0, 0]
    else:
        envs = [0, 2]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        batch.start_environments(ids(envs))
    same(batch, before)
    control = game(size=2, initial=9)
    control.start_environments(ids([0]))
    batch.start_environments(ids([0]))
    np.testing.assert_array_equal(hand(batch), hand(control))


@pytest.mark.parametrize("model,kind,value,cost", PLAN.effect_profiles)
def test_each_utility_use_receives_one_gift_including_first_and_reused_miracles(
    model, kind, value, cost
):
    batch = game(players=2)
    load(batch, hp=30, illness=1, mask=1)
    seed(batch, [(1, model, 0, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    reusable = dict(PLAN.inventory.profiles)[model] == 4
    assert batch.automatic_gift_count == 1
    assert hand(batch)[:, 0].tolist() == ([1, 2] if reusable else [2])
    assert batch.acquisition_snapshot()[0, 0].tolist() == [0, 1, 0]
    if not reusable:
        return
    step(batch, [0])  # Opponent Prayer, separately counted.
    if kind >= 3:
        # Reusing a cure without any affected state is correctly unavailable.
        assert not batch.choice_masks()[0, 1]
        return
    step(batch, [1])
    assert hand(batch)[:, 0].tolist() == [2, 1, 4]
    assert hand(batch)[1, 3] == 1
    assert batch.miracle_use_count == 2 and batch.mp_spent == 2 * cost
    assert batch.automatic_gift_count == 3 and batch.prayer_count == 1


@pytest.mark.parametrize("model", [35, 215])
def test_attack_receipt_waits_for_resolution_and_selected_armor_gets_one_each(model):
    batch = game()
    seed(batch, [(1, model, 0, 0)])
    seed(batch, [(10, 118, 0, 0), (11, 123, 0, 0), (12, 194, 0, 0)], owner=1)
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.automatic_gift_count == 0
    step(batch, [20])  # C + 1 + target1.
    assert batch.acquisition_snapshot()[0, 0].tolist() == [1, 0, 0]
    assert batch.automatic_gift_count == 0
    # Flame is fire, requiring water armor; attack35 has ordinary element.
    selectable = np.flatnonzero(batch.choice_masks()[0, 1:4]) + 1
    for slot in selectable:
        step(batch, [int(slot)])
        assert batch.automatic_gift_count == 0
    step(batch, [0])
    assert batch.automatic_gift_count == 1 + len(selectable)
    assert batch.acquisition_snapshot()[0, 0, 1] == 1
    assert batch.acquisition_snapshot()[0, 1, 1] == len(selectable)
    assert not np.any(batch.acquisition_snapshot()[:, :, 0])
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_reusing_flame_receives_another_gift_even_though_instance_is_retained():
    batch = game(players=2, prayer=False)
    seed(batch, [(1, 215, 0, 0)])
    batch.start_environments(ids([0]))
    for slot in (1, 1):
        step(batch, [slot])
        step(batch, [20])
        step(batch, [0])
        step(batch, [0])
    assert batch.miracle_use_count == 2 and batch.automatic_gift_count == 2
    assert hand(batch)[:, 0].tolist() == [2, 1, 3]
    assert batch.acquisition_snapshot()[0, 0, 1] == 2


@pytest.mark.parametrize("kind", ["turn", "decision", "midcast", "terminal", "dead-attacker"])
def test_gifts_suppressed_after_terminal_limits_and_dead_owner_not_fabricated(kind):
    batch = game(
        max_turns=1 if kind == "turn" else 1000,
        max_decisions=1 if kind == "decision" else 2 if kind == "midcast" else 4000,
        players=2 if kind == "terminal" else 3,
    )
    if kind in ("turn", "decision"):
        seed(batch, [(1, 194, 0, 0)])
        batch.start_environments(ids([0]))
        step(batch, [1])
    else:
        seed(batch, [(1, 35, 0, 0)])
        if kind == "terminal":
            load(batch, owner=1, hp=1)
        elif kind == "dead-attacker":
            load(batch, owner=0, hp=1, illness=1)
        batch.start_environments(ids([0]))
        step(batch, [1])
        step(batch, [20])
        if kind != "midcast":
            step(batch, [0])
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 1
    assert not np.any(batch.acquisition_snapshot()[:, :, 0])
    assert not len(hand(batch))
    if kind == "dead-attacker":
        assert batch.episode_snapshot()[0, 3] == 1
        assert batch.episode_snapshot()[0, 2] == 1
    else:
        assert batch.episode_snapshot()[0, 3] in (12, 13)


def test_dead_defender_receipt_suppressed_while_attacker_receives_in_three_seat_game():
    batch = game()
    seed(batch, [(1, 57, 0, 0)])  # ATK30.
    seed(batch, [(10, 118, 0, 0)], owner=1)
    load(batch, owner=1, hp=1)
    batch.start_environments(ids([0]))
    for choice in (1, 20, 1, 0):
        step(batch, [choice])
    assert batch.automatic_gift_count == 1 and batch.suppressed_gift_count == 1
    assert len(hand(batch)) == 1 and not len(hand(batch, owner=1))
    assert batch.episode_snapshot()[0, 2] == 2


def test_prayer_uses_any_nonused_displayed_weapon_not_only_implemented_leaders():
    unsupported = next(
        m
        for m, category in PLAN.inventory.profiles
        if category == 1 and m not in {r[0] for r in PLAN.combat.attack_profiles}
    )
    batch = game()
    seed(batch, [(1, unsupported, 0, 0)])
    batch.start_environments(ids([0]))
    assert not np.any(batch.choice_masks()[0])  # Honest incomplete-mechanics boundary.
    before = snapshot(batch)
    with pytest.raises(ValueError, match="unavailable"):
        step(batch, [0])
    same(batch, before)
    manual = game(prayer=False)
    seed(manual, [(1, unsupported, 0, 0)])
    manual.start_environments(ids([0]))
    assert manual.choice_masks()[0, 0]
    step(manual, [0])
    assert manual.automatic_gift_count == manual.prayer_count == 0


def test_prayer_adds_gift_without_consumption_even_when_refill_on_use_disabled():
    batch = game(refill=False)
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert hand(batch).tolist() == [[1, 191, 0, 0]]
    assert batch.prayer_count == batch.pass_count == 1
    assert batch.consumed_count == batch.miracle_use_count == 0


@pytest.mark.parametrize("capacity", [18, 32, 512])
def test_oldest_eviction_uses_logical_held_order_not_lowest_instance_and_no_new_phase(capacity):
    batch = game(capacity=capacity)
    seed(batch, [(90, 235, 0, 0)] + [(80 - i, 191, 0, 0) for i in range(17)])
    batch.start_environments(ids([0]))
    step(batch, [1])  # Miracle retained at tail BEFORE new gift and eviction.
    expected_ids = [*range(79, 63, -1), 90, 91]
    assert hand(batch)[:, 0].tolist() == expected_ids
    assert len(hand(batch)) == 18
    assert batch.overflow_count == 1 and batch.consumed_count == 0
    assert batch.miracle_use_count == batch.automatic_gift_count == 1
    assert batch.episode_snapshot()[0, 3] == 1
    assert batch.acquisition_snapshot()[0, 0].tolist() == [0, 1, 1]


def test_repeated_prayer_evicts_oldest_and_never_grows_beyond_explicit_18_cap():
    batch = game(players=2)
    seed(batch, [(i + 1, 191, 0, 0) for i in range(18)])
    batch.start_environments(ids([0]))
    for _ in range(12):
        step(batch, [0])
        step(batch, [0])
    assert len(hand(batch)) == 18 and len(hand(batch, owner=1)) == 12
    assert hand(batch)[:, 0].tolist() == list(range(13, 19)) + list(range(19, 43, 2))
    assert batch.overflow_count == 12 and batch.automatic_gift_count == 24
    assert batch.consumed_count == 0 and batch.acquisition_snapshot()[0, 0, 2] == 12


@pytest.mark.parametrize("failure", ["overflow", "exhausted", "stale", "duplicate"])
def test_late_step_error_rolls_back_earlier_gift_rng_inventory_and_diagnostics(failure):
    batch = game(size=2, oldest=failure != "overflow", gifts=PLAN.gifts.model_weights)
    if failure == "overflow":
        seed(batch, [(i + 1, 191, 0, 0) for i in range(18)], env=1)
    elif failure == "exhausted":
        seed(batch, [(MAX_ID, 191, 0, 0)], env=1)
    batch.start_environments(ids([0, 1]))
    before = snapshot(batch)
    episodes = batch.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in range(2)])
    if failure == "stale":
        commands[1, 2] += 1
    elif failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        batch.step(commands)
    same(batch, before)
    control = game(size=2, gifts=PLAN.gifts.model_weights)
    control.start_environments(ids([0]))
    step(control, [0])
    step(batch, [0], [0])
    np.testing.assert_array_equal(hand(batch), hand(control))


def test_explicit_setup_ids_advance_native_gift_id_and_failed_deal_does_not():
    batch = game()
    batch.deal_cards(ids([0]), ids([1]), ids([120]), ids([191]))
    before = snapshot(batch)
    with pytest.raises(ValueError):
        batch.deal_cards(ids([0]), ids([0]), ids([500]), ids([999]))
    same(batch, before)
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert hand(batch)[0, 0] == 121
    assert batch.gift_count == 2 and batch.automatic_gift_count == 1


def test_gift_model_stream_independent_of_dream_and_disguises_full_same_category_pool():
    plain, dream = (
        game(size=32, initial=9, gifts=PLAN.gifts.model_weights),
        game(size=32, initial=9, gifts=PLAN.gifts.model_weights),
    )
    for env in range(32):
        for owner in range(3):
            load(dream, env=env, owner=owner, mask=2)
    plain.start_environments(ids(range(32)))
    dream.start_environments(ids(range(32)))
    a, b = plain.diagnostic_inventory(), dream.diagnostic_inventory()
    np.testing.assert_array_equal(a[:, :, :, :2], b[:, :, :, :2])
    assert np.count_nonzero(b[:, :, :, 2]) > 0
    categories = dict(PLAN.inventory.profiles)
    for actual, fake in b[:, :, :, 1:3].reshape(-1, 2):
        if fake:
            assert categories[int(actual)] == categories[int(fake)]
    assert not np.any(a[:, :, :, 2])


def test_full_cure_restores_existing_cards_before_replacement_gift_without_dream():
    batch = game()
    load(batch, mask=2)
    seed(batch, [(1, 238, 0, 0), (2, 191, 194, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert hand(batch).tolist() == [[2, 191, 0, 0], [1, 238, 0, 1], [3, 191, 0, 0]]
    assert batch.restored_count == 1 and batch.automatic_gift_count == 1


def test_automatic_receipt_sampling_does_not_advance_illness_stream():
    first, second = game(size=32), game(size=32, prayer=False, refill=False)
    for batch in (first, second):
        for env in range(32):
            for owner in range(3):
                load(batch, env=env, owner=owner, illness=(env + owner) % 5)
        batch.start_environments(ids(range(32)))
    for _ in range(100):
        active = np.flatnonzero(first.episode_snapshot()[:, 3] == 1).tolist()
        if not active:
            break
        step(first, [0] * len(active), active)
        step(second, [0] * len(active), active)
        np.testing.assert_array_equal(first.diagnostic_players(), second.diagnostic_players())
        np.testing.assert_array_equal(first.episode_snapshot(), second.episode_snapshot())
    assert first.automatic_gift_count > 0 and second.automatic_gift_count == 0


def test_model_sampling_does_not_advance_fog_target_stream():
    # Use Prayer draws before the same attack on the second actor, not setup mutation.
    first, second = game(size=32), game(size=32, prayer=False, refill=False)
    for batch in (first, second):
        for env in range(32):
            seed(batch, [(1, 215, 0, 0)], env=env, owner=1)
            load(batch, env=env, owner=1, mask=1)
        batch.start_environments(ids(range(32)))
        step(batch, [0] * 32)
        step(batch, [1] * 32)
        step(batch, [19] * 32)  # Nominally seat0; Fog samples its own target.
    np.testing.assert_array_equal(first.pending_observations(), second.pending_observations())
    assert first.automatic_gift_count == 32 and second.automatic_gift_count == 0


def test_reset_clears_pending_receipts_ids_and_per_episode_counters_preserving_lifetime():
    batch = game(size=2, initial=9, gifts=PLAN.gifts.model_weights)
    batch.start_environments(ids([0, 1]))
    before_other = batch.diagnostic_inventory()[1].copy()
    batch.reset_environments(ids([0]))
    assert not np.any(batch.acquisition_snapshot()[0])
    assert batch.automatic_gift_count == 54
    batch.start_environments(ids([0]))
    assert batch.automatic_gift_count == 81
    assert batch.diagnostic_inventory()[0, :, :9, 0].ravel().tolist() == list(range(1, 28))
    expanded = [m for m, weight in PLAN.gifts.model_weights for _ in range(weight)]
    tickets = ranks(0, 67, 2, 500)
    assert batch.diagnostic_inventory()[0, :, :9, 1].ravel().tolist() == [
        expanded[next(tickets)] for _ in range(27)
    ]
    np.testing.assert_array_equal(before_other, batch.diagnostic_inventory()[1])
    snapshot_copy = batch.acquisition_snapshot()
    assert snapshot_copy.shape == (2, 3, 3) and not snapshot_copy.flags.writeable
    batch.reset_environments(ids([0]))
    assert np.sum(snapshot_copy[:, :, 1]) == 54


@pytest.mark.parametrize(
    "changes",
    [
        {"gifts": None},
        {"gifts": ()},
        {"gifts": ((191, 0),)},
        {"gifts": ((191, 501),)},
        {"gifts": ((191, 1), (191, 2))},
        {"gifts": ((1, 1),)},
        {"gifts": ((2, 1),)},
        {"gifts": ((999, 1),)},
        {"initial": 19},
        {"limit": 19},
        {"capacity": 1},
    ],
)
def test_native_acquisition_configuration_fails_closed(changes):
    with pytest.raises((ValueError, TypeError)):
        game(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"model_weights": tuple(PLAN.gifts.model_weights[:-1])},
        {"model_weights": tuple(reversed(PLAN.gifts.model_weights))},
        {"total_weight": 295},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"excluded_virtual_controls": (3, 4)},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"local_training_eligible": True},
        {"all_gifted_effects_implemented": True},
    ],
)
def test_plan_rejects_restricted_pool_forged_sources_and_readiness(changes):
    with pytest.raises(ValidationError):
        FullGameAcquisitionPlan.model_validate({**PLAN.gifts.model_dump(), **changes})


def test_builder_checks_raw_weight_and_bible_details_in_addition_to_recorded_hashes(monkeypatch):
    # Bypass the already-tested outer hash check to exercise inner field checks.
    monkeypatch.setattr(
        "godfield_bot.full_game_acquisition.build_dream_inventory_plan",
        lambda catalog, bible: PLAN.inventory,
    )
    changed = CAT.model_copy(deep=True)
    next(item for item in changed.items if item.model_id == 3).raw["giftRate"] = 19
    with pytest.raises(ValueError, match="trade"):
        build_full_game_acquisition_plan(changed, REF)
    changed = CAT.model_copy(deep=True)
    next(item for item in changed.items if item.model_id == 191).raw["giftRate"] += 1
    with pytest.raises(ValueError, match="Bible"):
        build_full_game_acquisition_plan(changed, REF)


def configured(**changes):
    return create_development_full_game_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=2,
        capacity=18,
        acquisition_mode="all-held-weighted",
        **changes,
    )


def test_source_checked_factory_enables_full_pool_and_labels_all_provisional_boundaries():
    conf = configured()
    conf.batch.start_environments(ids([0, 1]))
    meta = conf.metadata
    assert meta.initial_deal_cards == 9 and meta.refill_on_use and meta.prayer_gifts
    assert meta.hand_limit == 18 and meta.overflow_policy == "oldest-held-provisional"
    assert not meta.full_game_training_ready and not meta.promotion_eligible
    assert conf.batch.automatic_gift_count == 36


@pytest.mark.parametrize(
    "changes",
    [
        {"acquisition_mode": "manual"},
        {"capacity": 17},
        {"initial_deal_cards": 8},
        {"refill_on_use": False},
        {"refill_on_use": 1},
        {"prayer_gifts": False},
        {"overflow_policy": "reject"},
        {"hand_limit": 17},
        {"acquisition_snapshot_fields": ("fake",)},
        {"full_game_training_ready": True},
    ],
)
def test_metadata_prevents_mixing_modes_and_relabeling_subset_or_overflow(changes):
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate({**configured().metadata.model_dump(), **changes})
