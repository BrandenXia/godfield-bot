"""Complete generated guardian route admission, effects, custody and one-tick queue."""

from pathlib import Path

import pytest

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
ROUTES = dict(PLAN.guardians.action_profiles)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def tickets(seed, env, stream, epoch=1):
    mask = 2**64 - 1
    word = seed ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
    word ^= (epoch * 0xBF58476D1CE4E5B9) & mask
    word ^= stream
    while True:
        word = (word + 0x9E3779B97F4A7C15) & mask
        value = word
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        yield value ^ (value >> 31)


SEED = next(s for s in range(1000) if next(tickets(s, 0, 0x9216D5D98979FB1B)) % 100 < 25)


def game(*, size=1, players=3, pool=PLAN.guardians.generated_profiles, **options):
    kwargs = dict(
        capacity=18,
        seed=SEED,
        initial_hp=100,
        initial_mp=20,
        initial_cp=20,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        passive_profiles=ids(PLAN.passives.profiles),
        removal_profiles=ids(PLAN.removal.profiles),
        cost_reducer_profiles=ids(PLAN.costs.profiles),
        complex_weapon_profiles=ids(PLAN.weapons.profiles),
        danger_profiles=ids(PLAN.danger.profiles),
        dream_defense_profiles=ids(PLAN.dream_defense.profiles),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        area_profiles=ids(PLAN.area.profiles),
        discard_model_ids=ids(PLAN.discard.discard_model_ids),
        guardian_profiles=ids(PLAN.guardians.profiles),
        summon_profiles=ids(PLAN.guardians.summon_profiles),
        gift_profiles=ids(PLAN.gifts.model_weights),
        devil_profiles=ids(PLAN.devils.profiles),
        phenomenon_profiles=ids(PLAN.phenomena.profiles),
        fate_model_ids=ids(PLAN.phenomena.fate_model_ids),
        exchange_model_ids=ids(PLAN.trade.exchange_model_ids),
        market_profiles=ids(PLAN.trade.price_profiles),
        guardian_generated_profiles=None if pool is None else ids(pool).reshape(-1, 4),
        guardian_action_profiles=ids(PLAN.guardians.action_profiles),
    )
    kwargs.update(options)
    return native.FullGameBatch(
        size, players, ids(PLAN.inventory.profiles), ids(PLAN.effect_profiles), **kwargs
    )


def hand(b, models, owner=0, env=0):
    b.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + i + 1, *(m if isinstance(m, tuple) else (m, 0, 0))]
                for i, m in enumerate(models)
            ]
        ).reshape(-1, 4),
    )


def load(b, *, owner=0, env=0, hp=100, mp=20, cp=20, illness=0, mask=8):
    b.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(b, choices, envs=None):
    envs = range(len(choices)) if envs is None else envs
    rows = b.episode_snapshot()
    b.step(ids([[env, *rows[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]))
    q = b.attack_family_snapshot()
    np.testing.assert_array_equal(q[:, 0], q[:, 2] + q[:, 3] + q[:, 13] + (q[:, 14] > 0))


def start(b, group, size=1):
    b.seed_guardians(ids(range(size)), ids([1] * size), ids([group] * size))
    b.start_environments(ids(range(size)))


def drain(b):
    for _ in range(128):
        rows = np.flatnonzero(np.isin(b.episode_snapshot()[:, 3], (4, 6)))
        if not len(rows):
            return
        step(b, [0] * len(rows), rows)
    raise AssertionError("generated family exceeded bounded first-turn drain")


@pytest.mark.parametrize("profile", PLAN.guardians.generated_profiles, ids=lambda r: str(r[1]))
@pytest.mark.parametrize("players", [2, 3, 9])
def test_every237_generated_model_executes_its_declared_route_without_borrowing_a_card(
    profile, players
):
    group, model, _, _ = profile
    b = game(players=players, pool=(profile,))
    for seat in range(players):
        hand(b, [208], seat)
        load(b, owner=seat)
    start(b, group)
    step(b, [0])
    drain(b)
    stats = b.guardian_generated_snapshot()[0]
    assert stats[0] == (group == 9) and stats[7] == (group == 10)
    assert stats[1] == 1 and b.guardian_generated_model_counts()[0, model - 3] == 1
    assert b.guardian_generated_execution_counts()[0, model - 3] == 1
    assert stats[8 + ROUTES[model] - 1] == 1
    assert stats[15] == stats[16] + stats[17]
    assert b.episode_snapshot()[0, 4] == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)
    assert b.miracle_use_count == b.attack_count == b.resolved_attack_count == b.gift_count == 0
    assert b.mp_spent == stats[20]
    assert b.consumed_count == b.revival_count
    assert not b.generated_action_observations().any()
    assert not b.attack_family_snapshot()[0, 13:].any()


@pytest.mark.parametrize(
    "model,power,recipients", [(231, 20, 1), (232, 10, 2), (233, 10, 1), (234, 10, 1)]
)
def test_full_moon_blade_fallback_preserves_weapon_origin_and_ordered_power(
    model, power, recipients
):
    b = game(pool=((10, model, 4, 1),))
    start(b, 10)
    step(b, [0])
    assert b.generated_action_observations()[0, :4].tolist() == [1, 286, model, 286]
    assert b.pending_observations()[0, 3] == power
    drain(b)
    assert b.guardian_generated_snapshot()[0, 18] == power * recipients
    assert b.mp_spent == b.miracle_use_count == b.consumed_count == 0


def test_multiple_generated_utilities_accumulate_lifetime_counters_without_extra_ticks_or_costs():
    seed = next(s for s in range(10000) if both_guardians_trigger(s))
    b = game(seed=seed, pool=((10, 236, 4, 1),))
    hand(b, [236])
    b.seed_guardians(ids([0, 0]), ids([1, 2]), ids([10, 10]))
    b.start_environments(ids([0]))
    step(b, [1])
    step(b, [0])
    assert b.cp_utility_count == 3 and b.utility_cp_gain == 30
    assert b.cp_utility_snapshot()[0].tolist() == [3, 30, 5, 0]
    assert b.mp_spent == 5 and b.miracle_use_count == 1
    assert b.guardian_generated_snapshot()[0, 9] == 2
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def both_guardians_trigger(seed):
    iterator = tickets(seed, 0, 0x9216D5D98979FB1B)
    return all(next(iterator) % 100 < 25 for _ in range(2))


def profile(model):
    row = next(row for row in PLAN.guardians.generated_profiles if row[1] == model)
    return (*row[:3], 1)


def model_pair_seed(first_rank, second_rank, *, two_guardians=False, target_zero=False):
    for seed in range(100000):
        trigger = tickets(seed, 0, 0x9216D5D98979FB1B)
        if next(trigger) % 100 >= 25 or (two_guardians and next(trigger) % 100 >= 25):
            continue
        models = tickets(seed, 0, 0x2BA9C55D741831F6)
        if [next(models) % 2, next(models) % 2] != [first_rank, second_rank]:
            continue
        if target_zero and next(tickets(seed, 0, 0x2FFD72DBD01ADFB7)) % 2:
            continue
        return seed
    raise AssertionError("bounded seed search failed")


@pytest.mark.parametrize(
    "generated,origin,element",
    [(6, 0, 0), (210, 1, 1), (219, 1, 0), (127, 4, 0), (231, 0, 0), (233, 0, 0)],
)
@pytest.mark.parametrize("special", PLAN.combat.special_profiles, ids=lambda row: str(row[0]))
def test_generated_attacks_and_virtual_fallbacks_keep_typed_special_defenses(
    generated, origin, element, special
):
    b = game(players=2, pool=(profile(generated),))
    hand(b, [special[0]])
    load(b, mp=100)
    start(b, profile(generated)[0])
    step(b, [0])
    _, _, required_origin, neutral_only, _ = special
    expected = (required_origin == -1 or required_origin == origin) and (
        not neutral_only or element == 0
    )
    pending = b.pending_observations()[0]
    assert pending[4:6].tolist() == [element, origin]
    armor = next((row for row in PLAN.combat.armor_profiles if row[0] == special[0]), None)
    numeric = (
        armor is not None
        and pending[3] > 0
        and (
            element in (0, 6)
            or (element != 5 and armor[2] in ({1: 2, 2: 1, 3: 4, 4: 3}[element], 5))
        )
    )
    assert bool(b.choice_masks()[0, 1]) == (expected or numeric)
    if expected or numeric:
        step(b, [1])
        assert b.special_defense_observations()[0, 3] == (special[1] if expected else 0)


def test_generated_defensive_miracle_is_a_free_blade_but_real_defender_still_pays():
    b = game(players=2, pool=(profile(233),))
    hand(b, [233])
    load(b, mp=6)
    start(b, 10)
    step(b, [0])
    step(b, [1])
    step(b, [0])
    assert b.mp_spent == 6 and b.miracle_use_count == 1
    assert b.diagnostic_inventory()[0, 0, 0, 3] == 1
    assert b.diagnostic_players()[0, 1, 1] == 20
    assert b.guardian_generated_snapshot()[0, 20] == 0
    assert b.hp_damage == 0


def test_generated_mp_weapon_pays_original_owner_once_even_when_reflected():
    model = next(row[0] for row in PLAN.weapons.profiles if row[1] == 1)
    b = game(players=2, pool=(profile(model),))
    hand(b, [190])
    hand(b, [6], 1)
    load(b, owner=1, mp=7)
    start(b, 9)
    step(b, [0])
    assert b.pending_observations()[0, 3] == 14
    assert b.diagnostic_players()[0, :, 1].tolist() == [20, 0]
    step(b, [1])
    step(b, [0])
    assert b.pending_observations()[0, 3] == 14
    step(b, [0])
    assert b.mp_spent == b.guardian_generated_snapshot()[0, 20] == 7
    assert b.diagnostic_inventory()[0, 1, 0, 1] == 6
    assert b.consumed_count == 1 and b.reflection_count == 1


def test_generated_song_restores_staged_dream_hand_without_using_owned_miracles():
    b = game(pool=(profile(238),))
    hand(b, [(127, 142, 0), (210, 217, 1)], 1)
    load(b, owner=1, mask=15, illness=2, mp=0)
    start(b, 10)
    step(b, [0])
    assert b.diagnostic_players()[0, 1, 3:5].tolist() == [0, 0]
    assert b.diagnostic_inventory()[0, 1, :2, 2].tolist() == [0, 0]
    assert b.diagnostic_inventory()[0, 1, :2, 3].tolist() == [0, 1]
    assert b.restored_count == 2 and b.mp_spent == b.miracle_use_count == 0
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_generated_solar_replaces_later_guardian_identity_without_new_wave():
    seed = next(s for s in range(10000) if both_guardians_trigger(s))
    solar = next(row for row in PLAN.phenomena.profiles if row[0] == 296)
    b = game(seed=seed, pool=(profile(207),), phenomenon_profiles=ids([solar]))
    b.seed_guardians(ids([0, 0]), ids([1, 2]), ids([9, 1]))
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.guardian_statistics()[0, 2:4].tolist() == [2, 2]
    assert b.guardian_statistics()[0, 9] == 1
    assert b.guardian_statistics()[0, 0] == 3
    assert b.guardian_generated_snapshot()[0, 9] == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert not b.attack_family_snapshot()[0, 13:].any()


@pytest.mark.parametrize("model", [58, 232, 127, 4, 5])
def test_no_living_opponent_suppresses_generated_action_without_self_target_or_mp_debit(model):
    b = game(players=2, pool=(profile(model),))
    load(b, owner=0, hp=1, illness=3)
    start(b, 10 if model >= 210 else 9)
    step(b, [0])
    assert b.guardian_generated_model_counts()[0, model - 3] == 1
    assert b.guardian_generated_execution_counts()[0].sum() == 0
    assert b.guardian_generated_snapshot()[0, 6] == 1
    assert not b.guardian_generated_snapshot()[0, 8:].any()
    assert b.mp_spent == 0 and b.diagnostic_players()[0, 1, 1] == 20
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert not b.attack_family_snapshot()[0, 13:].any()


def test_replaced_generated_producer_is_drawn_but_not_executed():
    seed = next(s for s in range(10000) if both_guardians_trigger(s))
    solar = next(row for row in PLAN.phenomena.profiles if row[0] == 296)
    b = game(seed=seed, pool=(profile(207),), phenomenon_profiles=ids([solar]))
    b.seed_guardians(ids([0, 0]), ids([1, 2]), ids([9, 9]))
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.guardian_generated_model_counts()[0, 207 - 3] == 2
    assert b.guardian_generated_execution_counts()[0, 207 - 3] == 1
    assert b.guardian_generated_snapshot()[0, 6] == 1


def test_generated_enemy_only_phenomenon_suppresses_without_sampling_empty_roster():
    phenomenon = next(row for row in PLAN.phenomena.profiles if row[1] == 6)
    b = game(players=2, pool=(profile(207),), phenomenon_profiles=ids([phenomenon]))
    load(b, owner=0, hp=1, illness=3)
    start(b, 9)
    step(b, [0])
    assert b.guardian_generated_execution_counts()[0, 207 - 3] == 1
    assert b.phenomenon_snapshot()[0, 3:7].tolist() == [1, 0, 0, 1]
    assert b.diagnostic_players()[0, 1, 0] == 100
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert not b.attack_family_snapshot()[0, 13:].any()


@pytest.mark.parametrize("reflect", [False, True])
def test_generated_sell_keeps_real_hand_and_private_generated_parcel_through_reflection(reflect):
    seed = model_pair_seed(0, 1)
    b = game(players=2, seed=seed, pool=(profile(4), profile(127)))
    hand(b, [190] if reflect else [6])
    hand(b, [7], 1)
    start(b, 9)
    step(b, [0])
    escrow = b.market_escrow_snapshot()[0]
    assert escrow[0] == -2 and escrow[2] == 127 and escrow[5] == 1
    if reflect:
        step(b, [1])
        step(b, [0])
    step(b, [0])
    recipient = 1 if reflect else 0
    assert b.diagnostic_inventory()[0, recipient, 1, 1] == 127
    assert b.diagnostic_inventory()[0, 1, 0, 1] == 7
    assert b.consumed_count == int(reflect)
    assert b.market_snapshot()[0, 13] == b.guardian_generated_snapshot()[0, 21] == 1
    assert b.market_snapshot()[0, 14] == b.gift_count == 0
    assert not b.market_escrow_snapshot().any()


def test_generated_sell_receives_sun_before_payment_death_and_does_not_tick_buyer_again():
    seed = model_pair_seed(0, 1)
    b = game(players=2, seed=seed, pool=(profile(4), profile(208)))
    load(b, hp=1, mp=0, cp=0)
    start(b, 9)
    step(b, [0])
    step(b, [0])
    assert b.revival_count == b.consumed_count == 1
    assert b.diagnostic_players()[0, 0, 0] == 10
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert b.hp_damage == b.mp_spent == b.gift_count == 0
    assert b.market_snapshot()[0, 17] == 1
    assert b.guardian_generated_snapshot()[0, 21:23].tolist() == [1, 0]


def test_reflected_generated_buy_exposes_voluntary_purchase_only_to_new_current_source():
    b = game(players=2, pool=(profile(5),))
    hand(b, [190])
    hand(b, [6], 1)
    start(b, 9)
    step(b, [0])
    step(b, [1])
    step(b, [0])
    step(b, [0])
    assert b.episode_snapshot()[0, 2:4].tolist() == [0, 6]
    assert b.policy_gradient_masks()[0, 0]
    assert b.generated_action_observations()[0].tolist() == [1, 285, 5, 0, 0, 1]
    assert b.market_snapshot()[0, 23] == 0
    step(b, [1])
    assert b.diagnostic_inventory()[0, 0, 0, 1] == 6
    assert b.consumed_count == 1 and b.market_snapshot()[0, 11] == 1


def test_unreflected_generated_buy_decides_natively_with_no_learner_purchase_prompt():
    b = game(players=2, pool=(profile(5),))
    hand(b, [127])
    start(b, 9)
    step(b, [0])
    step(b, [0])
    bought = next(tickets(SEED, 0, 0x636920D871574E69)) % 2 != 0
    assert b.episode_snapshot()[0, 3] == 1
    assert b.market_snapshot()[0, 23] == 1
    assert b.market_snapshot()[0, 11] == bought
    assert b.market_snapshot()[0, 12] == (not bought)
    assert b.consumed_count == b.miracle_use_count == 0


def test_drop_receipt_can_supply_real_mortar_to_a_later_generated_pestle_in_same_command():
    pestle = next(row[0] for row in PLAN.danger.profiles if row[1] == 1)
    seed = model_pair_seed(1, 0, two_guardians=True, target_zero=True)
    b = game(seed=seed, pool=(profile(pestle), profile(209)))
    b.seed_guardians(ids([0, 0]), ids([1, 2]), ids([9, 9]))
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.generated_action_observations()[0, 2] == 209
    step(b, [0])
    assert b.consumed_count == 1 and b.danger_snapshot()[0, 3] == 1
    assert not b.diagnostic_inventory().any()
    assert b.guardian_generated_snapshot()[0, 2] == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def snapshot(b):
    return tuple(
        getattr(b, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "guardian_snapshot",
            "guardian_statistics",
            "guardian_generated_snapshot",
            "guardian_generated_model_counts",
            "guardian_generated_execution_counts",
            "generated_action_observations",
            "attack_family_snapshot",
            "market_snapshot",
            "market_escrow_snapshot",
            "trade_snapshot",
            "cp_utility_snapshot",
        )
    )


def same(first, second):
    for a, b in zip(first, second, strict=True):
        np.testing.assert_array_equal(a, b)


def test_late_missing_generated_dependency_rolls_back_prior_utility_counts_and_native_draws():
    seed = next(
        s
        for s in range(10000)
        if all(next(tickets(s, env, 0x9216D5D98979FB1B)) % 100 < 25 for env in (0, 1))
    )
    b, reference = [
        game(size=2, seed=seed, pool=(profile(207), profile(236)), fate_model_ids=None)
        for _ in range(2)
    ]
    for current in (b, reference):
        current.seed_guardians(ids([0, 1]), ids([1, 1]), ids([10, 9]))
        current.start_environments(ids([0, 1]))
    before = snapshot(b)
    with pytest.raises(ValueError, match="generated utility dependency"):
        step(b, [0, 0])
    same(before, snapshot(b))
    assert b.cp_utility_count == b.utility_cp_gain == b.action_count == 0
    step(b, [0], [0])
    step(reference, [0], [0])
    same(snapshot(b), snapshot(reference))


def test_generated_repeat_payload_survives_nested_counter_without_stale_weapon_views():
    model = next(row[0] for row in PLAN.weapons.profiles if row[1] == 3)
    b = game(players=2, pool=(profile(model),))
    hand(b, [188])
    start(b, 9)
    step(b, [0])
    assert b.complex_weapon_observations()[0, 0] == 1
    step(b, [1])
    step(b, [0])
    assert b.attack_family_snapshot()[0, 14] == 1
    assert not b.complex_weapon_observations().any()
    step(b, [0])
    assert b.generated_action_observations()[0, 2] == model
    assert b.pending_observations()[0, 3] == 3
    step(b, [0])
    assert b.guardian_generated_snapshot()[0, 15:17].tolist() == [2, 2]
    assert b.complex_weapon_snapshot()[0, 6] == 2
    assert b.consumed_count == 1 and b.counter_count == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0]


@pytest.mark.parametrize("mirage", [False, True])
def test_owned_repeated_attack_restores_its_views_after_nested_counter(mirage):
    b = game(players=3)
    hand(b, [14, 232] if mirage else [14])
    hand(b, [188], 1)
    b.start_environments(ids([0]))
    step(b, [1])
    if mirage:
        step(b, [2])
    step(b, [0])
    step(b, [21 if mirage else 20])
    assert b.complex_weapon_observations()[0, 0] == 1
    assert bool(b.area_observations()[0, 0]) == mirage
    step(b, [1])
    step(b, [0])
    assert b.attack_family_snapshot()[0, 14] == 1
    assert not b.complex_weapon_observations().any()
    assert not b.area_observations().any()
    step(b, [0])
    assert b.complex_weapon_observations()[0, 0] == 1
    assert bool(b.area_observations()[0, 0]) == mirage
    drain(b)
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert b.consumed_count == 2 and b.counter_count == 1


def test_virtual_mirage_suppresses_later_recipients_when_reflection_kills_original_source():
    b = game(players=3, pool=(profile(232),))
    hand(b, [190])
    load(b, owner=1, hp=1)
    start(b, 10)
    step(b, [0])
    step(b, [1])
    step(b, [0])
    step(b, [0])
    assert b.guardian_generated_snapshot()[0, 15:18].tolist() == [2, 1, 1]
    assert b.diagnostic_players()[0, 2, 0] == 100
    assert not b.attack_family_snapshot()[0, 13:].any()
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_generated_bow_does_not_replace_actual_held_postdeath_bow_ownership():
    b = game(players=2, pool=(profile(112),))
    hand(b, [189, 188])
    hand(b, [112], 1)
    load(b, owner=1, hp=1, mp=0, cp=0)
    load(b, hp=100)
    start(b, 9)
    step(b, [0])
    step(b, [1])
    step(b, [2])
    step(b, [0])
    drain(b)
    assert b.ascension_count == b.consumed_count - 2 == 1
    assert b.guardian_generated_snapshot()[0, 15] == 1
    assert b.diagnostic_players()[0, 1, 0] == 0
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0]


def test_generated_cards_do_not_read_held_disguises_or_perform_real_miracles():
    b = game(players=2, pool=(profile(210),))
    hand(b, [(127, 142, 0), (210, 217, 1)], 1)
    load(b, owner=1, mask=2, mp=0)
    start(b, 10)
    before = b.diagnostic_inventory().copy()
    step(b, [0])
    assert b.generated_action_observations()[0, 2] == 210
    step(b, [0])
    np.testing.assert_array_equal(before, b.diagnostic_inventory())
    assert b.miracle_use_count == b.mp_spent == 0


def test_generated_sell_truncation_preserves_unsettled_diagnostics_then_reset_clears_them():
    b = game(players=2, pool=(profile(4),), max_decisions=1)
    start(b, 9)
    step(b, [0])
    assert b.episode_snapshot()[0, 3] == 13
    old = b.market_escrow_snapshot()
    draws = b.guardian_generated_model_counts()
    dispatches = b.guardian_generated_execution_counts()
    assert old[0, 0] == -2 and old[0, 5] == 1
    assert draws[0, 4 - 3] == dispatches[0, 4 - 3] == 1
    assert not draws.flags.writeable and not dispatches.flags.writeable
    assert not b.generated_action_observations().any()
    assert b.market_snapshot()[0, 13] == 0 and not old.flags.writeable
    b.reset_environments(ids([0]))
    assert not b.market_escrow_snapshot().any()
    assert not b.guardian_generated_snapshot().any()
    assert not b.guardian_generated_model_counts().any()
    assert not b.guardian_generated_execution_counts().any()
    assert draws[0, 4 - 3] == dispatches[0, 4 - 3] == 1
    assert old[0, 5] == 1


@pytest.mark.parametrize(
    "routes",
    [
        (),
        ((6, 0),),
        ((6, 8),),
        ((6, 6),),
        ((127, 1),),
        ((231, 1),),
        ((3, 4),),
        ((6, 1), (6, 1)),
        ((127, 6),),
    ],
)
def test_generated_route_profiles_reject_bad_roles_duplicates_and_missing_pool_coverage(routes):
    with pytest.raises(ValueError, match="guardian action profile"):
        game(pool=(profile(6),), guardian_action_profiles=ids(routes).reshape(-1, 2))
