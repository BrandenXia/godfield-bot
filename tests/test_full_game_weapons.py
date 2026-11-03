"""Complex weapons join costs, ordered defenses, reactions and atomic state."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan
from godfield_bot.full_game_weapons import FullGameWeaponPlan, build_full_game_weapon_plan

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
    profiles=PLAN.weapons.profiles,
    decisions=4000,
    turns=1000,
    refill=False,
    capacity=18,
    seed_value=67,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=capacity,
        seed=seed_value,
        initial_hp=100,
        initial_mp=10,
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
        cost_reducer_profiles=ids(PLAN.costs.profiles),
        complex_weapon_profiles=ids(profiles).reshape(-1, 4) if profiles is not None else None,
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, models, *, owner=0, env=0):
    batch.seed_hand(
        env,
        owner,
        ids([[100 * owner + i + 1, m, 0, 0] for i, m in enumerate(models)]).reshape(-1, 4),
    )


def load(batch, *, hp=100, mp=10, illness=0, mask=0, owner=0, env=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(ids([[env, *rows[env, :4], c] for env, c in zip(envs, choices, strict=True)]))


def cast(batch, model, *, defenses=(), additions=(), target=1):
    seed(batch, [model, *additions])
    seed(batch, defenses, owner=target)
    batch.start_environments(ids([0]))
    step(batch, [1])
    for slot in range(2, len(additions) + 2):
        step(batch, [slot])
    step(batch, [0])
    step(batch, [batch.choice_masks().shape[1] - 9 + target])


def snapshot(batch):
    arrays = [
        getattr(batch, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "attack_order",
            "defense_order",
            "attack_selection_observations",
            "utility_selection_observations",
            "complex_weapon_observations",
            "complex_weapon_snapshot",
            "attack_effect_observations",
            "acquisition_snapshot",
            "revival_snapshot",
            "cost_snapshot",
            "counter_snapshot",
        )
    ]
    totals = (
        batch.action_count,
        batch.mp_spent,
        batch.attack_count,
        batch.resolved_attack_count,
        batch.consumed_count,
        batch.miracle_use_count,
        batch.hp_damage,
        batch.recoil_hp_damage,
        batch.automatic_gift_count,
        batch.counter_count,
    )
    return arrays, totals


def same(first, second):
    assert first[1] == second[1]
    for a, b in zip(first[0], second[0], strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("mp", [0, 1, 9, 10, 99, 100])
def test_magical_stick_snapshots_scaling_spends_all_mp_even_on_reflection(mp):
    batch = game(refill=True)
    load(batch, mp=mp)
    cast(batch, 58, defenses=[190])
    assert batch.pending_observations()[0, 3] == 2 * mp
    assert batch.diagnostic_players()[0, 0, 1] == 0 and batch.mp_spent == mp
    assert batch.complex_weapon_snapshot()[0, :2].tolist() == [1, mp]
    assert batch.complex_weapon_observations()[0].tolist() == [1, 1, 2, 1]
    step(batch, [1])
    step(batch, [0])
    assert batch.pending_observations()[0, 3] == 2 * mp
    step(batch, [0])
    assert batch.hp_damage == min(100, 2 * mp)
    assert batch.mp_spent == mp and batch.resolved_attack_count == 1
    assert batch.diagnostic_players()[0, 0, 5] == 1


@pytest.mark.parametrize(
    "additions,value,cost,waivers",
    [
        ([210], 18, 2, 0),
        ([231, 204, 210], 34, 2, 1),
        ([210, 231, 204], 36, 2, 1),
        ([210, 204, 231, 204], 44, 0, 2),
        ([231, 210], 10, 8, 0),
        ([210, 231], 12, 8, 0),
    ],
)
def test_paid_miracles_reduce_dynamic_base_before_ordered_boosts(additions, value, cost, waivers):
    batch = game()
    seed(batch, [58, *additions])
    batch.start_environments(ids([0]))
    step(batch, [1])
    for slot in range(2, len(additions) + 2):
        step(batch, [slot])
    assert batch.attack_selection_observations()[0, :3].tolist() == [len(additions) + 1, value, 0]
    assert batch.attack_selection_observations()[0, 3] == cost
    assert batch.mp_spent == 0 and batch.diagnostic_players()[0, 0, 1] == 10
    step(batch, [0])
    step(batch, [20])
    assert batch.pending_observations()[0, 3] == value and batch.mp_spent == 10
    assert batch.cost_waiver_count == waivers
    step(batch, [0])
    assert batch.hp_damage == value


def test_zero_mp_can_waive_miracle_and_undo_recomputes_dynamic_base():
    batch = game()
    load(batch, mp=0)
    seed(batch, [58, 210, 204])
    batch.start_environments(ids([0]))
    for choice in (1, 2):
        step(batch, [choice])
    assert not batch.choice_masks()[0, 0]
    step(batch, [3])
    assert batch.choice_masks()[0, 0]
    assert batch.attack_selection_observations()[0, 1] == 2
    step(batch, [2])
    assert batch.attack_order()[0, :3].tolist() == [1, 0, 0]
    assert batch.attack_selection_observations()[0, 1:4].tolist() == [0, 0, 0]
    for choice in (2, 3, 0, 20, 0):
        step(batch, [choice])
    assert batch.hp_damage == 2 and batch.mp_spent == 0


@pytest.mark.parametrize("armor,damage", [(None, 14), (135, 9), (179, 0)])
def test_same_damage_uses_actual_positive_post_defense_loss_on_surviving_target(armor, damage):
    batch = game()
    cast(batch, 53, defenses=[] if armor is None else [armor])
    assert batch.attack_effect_observations()[0, 1] == 10
    if armor is not None:
        step(batch, [1])
    step(batch, [0])
    assert batch.diagnostic_players()[0, :2, 0].tolist() == [100 - damage, 100 - damage]
    assert batch.hp_damage == damage and batch.recoil_hp_damage == damage
    assert batch.complex_weapon_snapshot()[0, 2:5].tolist() == [1, int(damage > 0), damage]


@pytest.mark.parametrize("players", [2, 3, 9])
def test_defeated_target_short_circuits_recoil_even_if_other_players_survive(players):
    batch = game(players=players)
    load(batch, hp=5, owner=1)
    cast(batch, 53)
    step(batch, [0])
    assert batch.diagnostic_players()[0, :2, 0].tolist() == [100, 0]
    assert batch.recoil_hp_damage == 0 and batch.resolved_attack_count == 1
    assert batch.episode_snapshot()[0, 3] == (12 if players == 2 else 1)


@pytest.mark.parametrize("revive", [False, True])
def test_recoil_self_ko_and_actual_owned_amulet_use_shared_hp_zero_hook(revive):
    batch = game(players=2)
    load(batch, hp=1)
    seed(batch, [53, *([208] if revive else [])])
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 0):
        step(batch, [choice])
    assert batch.diagnostic_players()[0, 1, 0] == 86
    assert batch.diagnostic_players()[0, 0, 0] == (10 if revive else 0)
    assert batch.recoil_hp_damage == 1 and batch.revival_count == int(revive)
    assert batch.episode_snapshot()[0, 3] == (1 if revive else 12)
    if not revive:
        assert batch.episode_snapshot()[0, 6] == 1


def test_reflected_recoil_follows_current_source_explicitly_provisional():
    batch = game()
    cast(batch, 53, defenses=[190])
    for choice in (1, 0, 0):
        step(batch, [choice])
    assert batch.diagnostic_players()[0, :2, 0].tolist() == [86, 86]
    assert batch.recoil_hp_damage == 14 and batch.reflection_count == 1


def test_double_attack_has_fresh_independent_armor_and_no_intermediate_tick_or_gift():
    batch = game(refill=True)
    cast(batch, 14, defenses=[113, 113])
    assert batch.complex_weapon_observations()[0].tolist() == [1, 3, 3, 2]
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.diagnostic_players()[0, 1, 0] == 98
    assert batch.episode_snapshot()[0, 2:5].tolist() == [1, 4, 0]
    assert batch.complex_weapon_observations()[0, 3] == 1
    assert batch.resolved_attack_count == batch.automatic_gift_count == 0
    assert np.count_nonzero(batch.selected_defenses()) == 0
    assert batch.diagnostic_inventory()[0, 1, 0, 1] == 113
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.diagnostic_players()[0, 1, 0] == 96
    assert batch.resolved_attack_count == batch.attack_count == 1
    assert batch.automatic_gift_count == batch.consumed_count == 3
    assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 2, 0]
    assert batch.diagnostic_players()[0, :2, 5].tolist() == [1, 0]


@pytest.mark.parametrize("defense", [113, 233, 190])
def test_double_strike_second_response_returns_to_original_target_and_payload(defense):
    batch = game()
    cast(batch, 14, defenses=[defense])
    for choice in (1, 0):
        step(batch, [choice])
    if defense == 190:
        assert batch.episode_snapshot()[0, 2] == 0
        step(batch, [0])
        assert batch.diagnostic_players()[0, 0, 0] == 97
    assert batch.episode_snapshot()[0, 2:4].tolist() == [1, 4]
    assert batch.pending_observations()[0, 3] == 3
    assert batch.complex_weapon_observations()[0, 3] == 1
    step(batch, [0])
    assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 2, 0]
    assert batch.resolved_attack_count == 1


@pytest.mark.parametrize("source_hp", [5, 100])
def test_counter_family_finishes_between_strikes_and_dead_source_suppresses_second(source_hp):
    batch = game()
    load(batch, hp=source_hp)
    cast(batch, 14, defenses=[184])
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.episode_snapshot()[0, 2] == 0
    assert batch.counter_observations()[0, 1] == 1
    # The active counter must not reveal the queued weapon's remaining strike.
    assert not batch.complex_weapon_observations().any()
    step(batch, [0])
    if source_hp == 5:
        assert batch.episode_snapshot()[0, 3] == 1
        assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 1, 1]
        assert batch.diagnostic_players()[0, 1, 0] == 97
    else:
        assert batch.episode_snapshot()[0, 2:4].tolist() == [1, 4]
        assert batch.complex_weapon_observations()[0, 3] == 1
        step(batch, [0])
        assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 2, 0]
        assert batch.diagnostic_players()[0, :2, 0].tolist() == [94, 94]
    assert batch.counter_count == batch.resolved_counter_count == 1
    assert batch.resolved_attack_count == 1


@pytest.mark.parametrize("players", [2, 3, 9])
def test_first_strike_lethal_skips_second_and_preserves_real_ending_precedence(players):
    batch = game(players=players, turns=1)
    load(batch, hp=2, owner=1)
    cast(batch, 14)
    step(batch, [0])
    assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 1, 1]
    assert batch.resolved_attack_count == 1 and batch.hp_damage == 2
    assert batch.episode_snapshot()[0, 3] == (12 if players == 2 else 13)


def test_decision_limit_between_strikes_truncates_without_an_extra_effect():
    batch = game(decisions=4, refill=True)
    cast(batch, 14)
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3:6].tolist() == [13, 0, 4]
    assert batch.hp_damage == 3 and batch.resolved_attack_count == 0
    assert batch.automatic_gift_count == 0
    assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 1, 0]


@pytest.mark.parametrize("actual", [14, 53, 58])
def test_displayed_role_is_used_before_cast_actual_role_only_after_resolution(actual):
    batch = game()
    batch.seed_hand(0, 0, ids([[1, actual, 58, 0]]))
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.complex_weapon_observations()[0].tolist() == [1, 1, 2, 1]
    assert batch.pending_observations()[0, 3] == 20
    step(batch, [0])
    step(batch, [20])
    assert batch.complex_weapon_observations()[0, 1] == {14: 3, 53: 2, 58: 1}[actual]
    assert batch.mp_spent == (10 if actual == 58 else 0)


@pytest.mark.parametrize("failure", ["hidden", "stale", "duplicate"])
def test_late_error_rolls_back_mp_recoil_sequence_queue_receipts_and_retry(failure):
    first, reference = game(size=2, refill=True), game(size=2, refill=True)
    for batch in (first, reference):
        for env in (0, 1):
            seed(batch, [53], env=env)
            seed(batch, [113], owner=1, env=env)
        if failure == "hidden":
            batch.seed_hand(1, 1, ids([[101, 178, 113, 0]]))
        batch.start_environments(ids([0, 1]))
        for choices in ([1, 1], [0, 0], [20, 20], [1, 1]):
            step(batch, choices)
    before = snapshot(first)
    rows = first.episode_snapshot()
    commands = ids([[env, *rows[env, :4], 0] for env in (0, 1)])
    if failure == "stale":
        commands[1, 2] += 1
    if failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        first.step(commands)
    same(snapshot(first), before)
    step(first, [0], [0])
    step(reference, [0], [0])
    same(snapshot(first), snapshot(reference))
    assert first.recoil_hp_damage == 13 and first.automatic_gift_count == 2


def test_owned_readonly_snapshots_reset_episode_not_lifetime_recoil():
    batch = game()
    old = batch.complex_weapon_snapshot()
    with pytest.raises(ValueError):
        old[0, 0] = 1
    cast(batch, 53)
    step(batch, [0])
    assert np.count_nonzero(old) == 0 and batch.recoil_hp_damage == 14
    batch.reset_environments(ids([0]))
    assert np.count_nonzero(batch.complex_weapon_snapshot()) == 0
    assert np.count_nonzero(batch.complex_weapon_observations()) == 0
    assert batch.recoil_hp_damage == 14


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(14, 0, 3, 0)],
        [(14, 4, 3, 0)],
        [(14, 3, 0, 0)],
        [(14, 3, 65536, 0)],
        [(14, 3, 3, 7)],
        [(204, 3, 3, 0)],
        [(35, 3, 3, 0)],
        [(14, 3, 3, 0), (14, 3, 3, 0)],
    ],
)
def test_raw_complex_profile_validation_fails_closed(profiles):
    with pytest.raises(ValueError, match="complex weapon"):
        game(profiles=profiles)


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((14, 3, 4, 0),)},
        {"catalog_sha256": "0" * 64},
        {"profile_fields": ("true-inventory",)},
        {"effect_codes": ("global-discount",)},
        {"compound_rules_verified": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
    ],
)
def test_source_plan_scope_and_readiness_are_not_relabelable(change):
    with pytest.raises(ValidationError):
        FullGameWeaponPlan.model_validate(PLAN.weapons.model_dump() | change)


def test_source_builder_revalidates_unchecked_catalog_copies():
    catalog = read_api_catalog_snapshot(CATALOG)
    item = next(i for i in catalog.items if i.model_id == 14)
    changed = item.model_copy(update={"raw": dict(item.raw) | {"ability": "attackThrice"}})
    altered = catalog.model_copy(
        update={"items": tuple(changed if i.model_id == 14 else i for i in catalog.items)}
    )
    with pytest.raises(ValueError):
        build_full_game_weapon_plan(altered, BibleSnapshot.model_validate_json(BIBLE.read_text()))


def test_raw_omission_keeps_complex_cards_unsupported():
    batch = game(profiles=None)
    seed(batch, [14, 53, 58, 35])
    batch.start_environments(ids([0]))
    assert not np.any(batch.choice_masks()[0, 1:4]) and batch.choice_masks()[0, 4]
    assert np.count_nonzero(batch.complex_weapon_observations()) == 0


def test_double_boost_and_waiver_are_paid_and_consumed_once_for_both_strikes():
    batch = game(refill=True)
    load(batch, mp=0)
    cast(batch, 14, additions=[210, 204])
    assert batch.pending_observations()[0, 3] == 5
    assert batch.attack_component_count == 3 and batch.cost_waiver_count == 1
    step(batch, [0])
    assert batch.automatic_gift_count == 0 and batch.miracle_use_count == 1
    step(batch, [0])
    assert batch.hp_damage == 10 and batch.mp_spent == 0
    assert batch.consumed_count == 2 and batch.miracle_use_count == 1
    assert batch.automatic_gift_count == 3 and batch.cost_waiver_count == 1


def test_first_strike_filter_does_not_change_second_strike_original_element():
    batch = game()
    cast(batch, 14, additions=[66], defenses=[189])
    assert batch.pending_observations()[0, 3:5].tolist() == [5, 1]
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.filtered_attack_count == 1
    assert batch.pending_observations()[0, 3:5].tolist() == [5, 1]
    step(batch, [0])
    assert batch.hp_damage == 10


def test_target_amulet_resolves_before_provisional_recoil_and_second_strike_liveness():
    recoil = game(refill=True)
    load(recoil, hp=5, owner=1)
    cast(recoil, 53, defenses=[208])
    step(recoil, [0])
    assert recoil.diagnostic_players()[0, :2, 0].tolist() == [95, 10]
    assert recoil.recoil_hp_damage == 5 and recoil.revival_count == 1
    repeat = game(refill=True)
    load(repeat, hp=1, owner=1)
    cast(repeat, 14, defenses=[208])
    step(repeat, [0])
    assert repeat.diagnostic_players()[0, 1, 0] == 10
    assert repeat.automatic_gift_count == 0
    step(repeat, [0])
    assert repeat.diagnostic_players()[0, 1, 0] == 7
    assert repeat.hp_damage == 4 and repeat.automatic_gift_count == 2
    assert repeat.complex_weapon_snapshot()[0, 5:].tolist() == [1, 2, 0]


def test_counter_amulet_restores_original_source_before_second_strike():
    batch = game(refill=True)
    load(batch, hp=5)
    seed(batch, [14, 208])
    seed(batch, [184], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 0, 0):
        step(batch, [choice])
    assert batch.revival_count == 1 and batch.automatic_gift_count == 0
    assert batch.diagnostic_players()[0, 0, 0] == 10
    assert batch.episode_snapshot()[0, 2:4].tolist() == [1, 4]
    step(batch, [0])
    assert batch.hp_damage == 11 and batch.automatic_gift_count == 3
    assert batch.complex_weapon_snapshot()[0, 5:].tolist() == [1, 2, 0]


def test_hidden_paid_boost_on_magical_stick_rolls_back_all_mp_on_actual_cost_failure():
    batch = game()
    load(batch, mp=2)
    batch.seed_hand(0, 0, ids([[1, 58, 0, 0], [2, 231, 210, 0]]))
    batch.start_environments(ids([0]))
    for choice in (1, 2, 0):
        step(batch, [choice])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="unaffordable"):
        step(batch, [20])
    same(snapshot(batch), before)
    assert batch.mp_spent == 0


@pytest.mark.parametrize("failure", ["stale", "duplicate", "dead-target"])
def test_late_dynamic_cast_failure_preserves_all_costs_hands_and_pending_sequences(failure):
    first, reference = game(size=2), game(size=2)
    for batch in (first, reference):
        for env in (0, 1):
            seed(batch, [58], env=env)
        if failure == "dead-target":
            load(batch, hp=0, owner=1, env=1)
        batch.start_environments(ids([0, 1]))
        step(batch, [1, 1])
        step(batch, [0, 0])
    before = snapshot(first)
    rows = first.episode_snapshot()
    commands = ids([[env, *rows[env, :4], 20] for env in (0, 1)])
    if failure == "stale":
        commands[1, 2] += 1
    elif failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        first.step(commands)
    same(snapshot(first), before)
    step(first, [20], [0])
    step(reference, [20], [0])
    same(snapshot(first), snapshot(reference))
    assert first.mp_spent == 10


@pytest.mark.parametrize("model", [14, 53, 58])
@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed_value", [67, 68, 99])
def test_fog_target_is_sampled_once_and_repeated_payload_keeps_same_target(
    model, players, seed_value
):
    batch = game(players=players, seed_value=seed_value)
    load(batch, mask=1)
    seed(batch, [model])
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20):
        step(batch, [choice])
    target = int(batch.pending_observations()[0, 2])
    assert 1 <= target < players
    step(batch, [0])
    if model == 14:
        assert batch.pending_observations()[0, 2] == target
        assert batch.pending_observations()[0, 3] == 3
        step(batch, [0])
    assert batch.resolved_attack_count == 1
    assert batch.diagnostic_players()[0, 0, 5] == 1
