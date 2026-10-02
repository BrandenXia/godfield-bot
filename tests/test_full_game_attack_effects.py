"""Joined source-pinned effects, provisional chains, and native Dark Cloud tickets."""

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
from godfield_bot.full_game_combat_plan import FullGameCombatPlan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
EFFECTS = PLAN.combat.attack_effect_profiles
ATTACKS = {row[0]: row[1:] for row in PLAN.combat.attack_profiles}


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *,
    size=1,
    players=3,
    hp=40,
    mp=100,
    refill=False,
    gifts=((191, 1),),
    effects=EFFECTS,
    max_turns=1000,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        initial_hp=hp,
        initial_mp=mp,
        max_turns=max_turns,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(effects).reshape(-1, 3),
        gift_profiles=ids(gifts) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, models, *, env=0, owner=0):
    batch.seed_hand(
        env,
        owner,
        ids([(100 * owner + i + 1, model, 0, 0) for i, model in enumerate(models)]).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=40, mp=100, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    envs = range(len(choices)) if envs is None else envs
    episodes = batch.episode_snapshot()
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def begin(batch, model, *, defense=(), size=1):
    for env in range(size):
        seed(batch, [model], env=env)
        for owner in range(1, batch.diagnostic_players().shape[1]):
            seed(batch, defense, env=env, owner=owner)
    batch.start_environments(ids(range(size)))
    step(batch, [1] * size)
    step(batch, [0] * size)
    if np.all(batch.episode_snapshot()[:, 3] == 3):
        step(batch, [20] * size)


def snapshot(batch):
    arrays = [
        getattr(batch, view)()
        for view in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "selected_attacks",
            "attack_order",
            "selected_defenses",
            "attack_effect_observations",
            "attack_effect_snapshot",
            "chance_observations",
            "chance_snapshot",
            "acquisition_snapshot",
        )
    ]
    counters = [
        getattr(batch, name)
        for name in (
            "action_count",
            "hp_damage",
            "mp_spent",
            "consumed_count",
            "miracle_use_count",
            "absorption_count",
            "absorbed_hp",
            "inflicted_curse_count",
            "inflicted_illness_count",
            "illness_effect_damage",
            "dark_cloud_hit_count",
            "chance_count",
            "automatic_gift_count",
        )
    ]
    return arrays, counters


def same(batch, previous):
    arrays, counters = snapshot(batch)
    for actual, expected in zip(arrays, previous[0], strict=True):
        np.testing.assert_array_equal(actual, expected)
    assert counters == previous[1]


@pytest.mark.parametrize("model,kind,value", EFFECTS)
def test_all_20_source_effects_join_costs_inventory_statuses_and_owner_tick(model, kind, value):
    batch = game(size=32, refill=True)
    for env in range(32):
        load(batch, env=env, illness=1)
        for target in (1, 2):
            load(batch, env=env, owner=target, mask=8)  # Isolate effects from chance misses.
    begin(batch, model, size=32)
    attack, _, origin, cost = ATTACKS[model]
    targets = batch.episode_snapshot()[:, 2].copy()
    np.testing.assert_array_equal(
        batch.attack_effect_observations(), np.tile([1, kind, value, 0], (32, 1))
    )
    assert batch.mp_spent == 32 * cost
    assert batch.consumed_count == (0 if origin else 32)
    assert batch.miracle_use_count == (32 if origin else 0)
    assert batch.automatic_gift_count == 0
    step(batch, [0] * 32)
    states = batch.diagnostic_players()
    for env, target in enumerate(targets):
        assert states[env, target, 0] == 40 - attack
        assert states[env, target, 3] == (value if kind in (3, 5) else 0)
        assert states[env, target, 4] == (8 | value if kind in (2, 4) else 8)
        assert states[env, target, 5] == 0 and states[env, 0, 5] == 1
        assert states[env, 0, 0] == 39 + (attack if kind == 1 else 0)
    assert batch.hp_damage == 32 * attack and batch.resolved_attack_count == 32
    assert batch.absorbed_hp == (32 * attack if kind == 1 else 0)
    assert batch.inflicted_curse_count == (32 if kind in (2, 4) else 0)
    assert batch.inflicted_illness_count == (32 if kind in (3, 5) else 0)
    assert batch.automatic_gift_count == 32 and not np.any(batch.attack_effect_observations())


@pytest.mark.parametrize(
    "model,kind,value", [row for row in EFFECTS if row[1] <= 3 and ATTACKS[row[0]][1] != 5]
)
@pytest.mark.parametrize("fully_defended", [False, True])
def test_damage_effect_requires_positive_post_armor_hp_loss(model, kind, value, fully_defended):
    batch = game()
    for owner in (1, 2):
        load(batch, owner=owner, mask=8)
    element = ATTACKS[model][1]
    # Select source-pinned ordinary armor, not an exclusive special response.
    defense_model, defense = next(
        (row[0], row[1])
        for row in sorted(PLAN.combat.armor_profiles, key=lambda row: row[1])
        if row[0] not in {s[0] for s in PLAN.combat.special_profiles}
        and row[2] == {1: 2, 2: 1, 3: 4, 4: 3}.get(element, 0)
        and (not fully_defended or row[1] >= ATTACKS[model][0])
    )
    begin(batch, model, defense=[defense_model])
    target = int(batch.episode_snapshot()[0, 2])
    step(batch, [1])
    step(batch, [0])
    damage = max(0, ATTACKS[model][0] - defense)
    assert batch.hp_damage == damage
    assert batch.absorbed_hp == (damage if kind == 1 else 0)
    assert batch.diagnostic_players()[0, target, 3] == (value if damage and kind == 3 else 0)
    assert batch.diagnostic_players()[0, target, 4] == (8 | value if damage and kind == 2 else 8)


@pytest.mark.parametrize("model", [70, 216, 224])
def test_light_damage_effects_cannot_be_stopped_by_numeric_armor(model):
    batch = game()
    for owner in (1, 2):
        load(batch, owner=owner, mask=8)
    armor_models = [113, 115, 116, 117, 119, 148, 180]
    begin(batch, model, defense=armor_models)
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]
    step(batch, [0])
    assert batch.hp_damage == ATTACKS[model][0]


@pytest.mark.parametrize("model", [27, 45, 98, 216])
@pytest.mark.parametrize("source_hp,target_hp", [(40, 40), (98, 40), (40, 2)])
def test_absorption_caps_at_100_and_heals_actual_hp_removed(model, source_hp, target_hp):
    batch = game()
    load(batch, hp=source_hp)
    for owner in (1, 2):
        load(batch, owner=owner, hp=target_hp, mask=8)
    begin(batch, model)
    step(batch, [0])
    removed = min(ATTACKS[model][0], target_hp)
    assert batch.hp_damage == removed
    assert batch.absorbed_hp == min(100 - source_hp, removed)
    assert batch.diagnostic_players()[0, 0, 0] == min(100, source_hp + removed)


@pytest.mark.parametrize("model", [27, 45, 216])
def test_reflection_transfers_absorption_to_reflector_and_preserves_original_turn(model):
    batch = game(refill=True)
    load(batch, illness=1)
    load(batch, owner=1, hp=30)
    begin(batch, model, defense=[190])
    step(batch, [1])
    step(batch, [0])
    assert batch.attack_effect_observations()[0].tolist() == [1, 1, 0, 1]
    assert batch.episode_snapshot()[0, 2:5].tolist() == [0, 4, 0]
    assert batch.automatic_gift_count == batch.absorption_count == 0
    step(batch, [0])
    removed = ATTACKS[model][0]
    assert batch.diagnostic_players()[0, 0, 0] == 39 - removed
    assert batch.diagnostic_players()[0, 1, 0] == 30 + removed
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.absorbed_hp == removed and batch.automatic_gift_count == 2


@pytest.mark.parametrize("model,kind,value", [row for row in EFFECTS if row[1] >= 4])
def test_direct_curse_masks_numeric_defense_and_reflects_to_current_source(model, kind, value):
    batch = game()
    begin(batch, model, defense=[113, 190, 165, 233, 234])
    assert not batch.choice_masks()[0, 1]  # Ordinary DEF cannot stop a zero-ATK curse.
    assert batch.choice_masks()[0, 2] and batch.choice_masks()[0, 3]
    assert not batch.choice_masks()[0, 4]  # Weapon-only Wall cannot stop miracles.
    assert batch.choice_masks()[0, 5]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [1])
    same(batch, before)
    step(batch, [2])
    step(batch, [0])
    assert batch.attack_effect_observations()[0].tolist() == [1, kind, value, 1]
    step(batch, [0])
    assert batch.hp_damage == 0 and batch.darkness_finish_count == 0
    assert batch.diagnostic_players()[0, 0, 3] == (value if kind == 5 else 0)
    assert batch.diagnostic_players()[0, 0, 4] == (value if kind == 4 else 0)
    assert batch.diagnostic_players()[0, 1, 3:6].tolist() == [0, 0, 0]


@pytest.mark.parametrize("model,kind,value", [row for row in EFFECTS if row[1] >= 4])
def test_blocked_direct_curse_pays_cost_but_does_not_inflict(model, kind, value):
    batch = game()
    begin(batch, model, defense=[165])
    step(batch, [1])
    step(batch, [0])
    assert batch.mp_spent == ATTACKS[model][3] and batch.miracle_use_count == 1
    assert not np.any(batch.attack_effect_snapshot())
    assert batch.block_count == 1 and batch.hp_damage == 0


@pytest.mark.parametrize("model", [30, 33, 48, 62, 219, 220])
@pytest.mark.parametrize("existing", range(5))
def test_illness_infliction_worsens_existing_disease_without_ticking_defender(model, existing):
    batch = game()
    load(batch, owner=1, illness=existing)
    begin(batch, model)
    step(batch, [0])
    incoming = dict((row[0], row[2]) for row in EFFECTS)[model]
    expected_stage = incoming if existing == 0 else min(existing + 1, 4)
    remaining = 40 - ATTACKS[model][0]
    assert batch.diagnostic_players()[0, 1, 3:6].tolist() == [expected_stage, 0, 0]
    assert batch.diagnostic_players()[0, 1, 0] == (0 if existing == 4 else remaining)
    assert batch.illness_effect_damage == (remaining if existing == 4 else 0)
    assert batch.hp_damage == ATTACKS[model][0]  # Disease death is separately accounted.


def test_dream_infliction_preserves_existing_disguises_and_affects_only_future_gifts():
    batch = game(size=256, refill=True)
    for env in range(256):
        seed(batch, [222], env=env)
        batch.seed_hand(env, 1, ids([[101, 191, 192, 0], [102, 194, 0, 0]]))
    batch.start_environments(ids(range(256)))
    for choice in (1, 0, 20, 0):
        step(batch, [choice] * 256)
    np.testing.assert_array_equal(
        batch.diagnostic_inventory()[:, 1, :2],
        np.tile([[101, 191, 192, 0], [102, 194, 0, 0]], (256, 1, 1)),
    )
    step(batch, [2] * 256)  # Owner uses the real HP utility and receives a native replacement.
    np.testing.assert_array_equal(
        batch.diagnostic_inventory()[:, 1, 0], np.tile([101, 191, 192, 0], (256, 1))
    )
    gifts = batch.diagnostic_inventory()[:, 1, 1]
    assert np.all(gifts[:, 1] == 191) and 70 < np.count_nonzero(gifts[:, 2]) < 185
    assert np.all(batch.diagnostic_players()[:, 1, 4] == 2)


def test_new_dream_affects_deferred_defense_receipt_under_provisional_same_hit_timing():
    batch = game(size=256, refill=True)
    for env in range(256):
        seed(batch, [80], env=env)
        batch.seed_hand(env, 1, ids([[101, 117, 0, 0], [102, 191, 192, 0]]))
    batch.start_environments(ids(range(256)))
    for choice in (1, 0, 20, 1, 0):
        step(batch, [choice] * 256)
    hands = batch.diagnostic_inventory()[:, 1, :2]
    np.testing.assert_array_equal(hands[:, 0], np.tile([102, 191, 192, 0], (256, 1)))
    assert np.all(hands[:, 1, 1] == 191) and 70 < np.count_nonzero(hands[:, 1, 2]) < 185
    assert batch.hp_damage == 256 * 3 and batch.automatic_gift_count == 512


@pytest.mark.parametrize("model", [27, 33, 36, 41, 45, 48])
def test_fixed_damage_leader_effect_uses_entire_ordered_composed_attack(model):
    batch = game(refill=True)
    seed(batch, [model, 9, 231])
    load(batch, illness=1)
    batch.start_environments(ids([0]))
    for choice in (1, 2, 3, 0, 20, 0):
        step(batch, [choice])
    attack = 2 * (ATTACKS[model][0] + 1)
    kind, value = next(row[1:] for row in EFFECTS if row[0] == model)
    assert batch.hp_damage == attack and batch.attack_component_count == 3
    assert batch.automatic_gift_count == 3 and batch.mp_spent == 6
    assert batch.absorbed_hp == (attack if kind == 1 else 0)
    assert batch.diagnostic_players()[0, 1, 3] == (value if kind == 3 else 0)
    assert batch.diagnostic_players()[0, 1, 4] == (value if kind == 2 else 0)


def test_all_dark_cloud_targets_force_hits_without_leaking_status_before_cast():
    cloud, plain = game(size=128), game(size=128)
    for env in range(128):
        for batch in (cloud, plain):
            seed(batch, [99], env=env)
            load(batch, env=env, mask=1)  # Fog hides the opponents' status.
        for owner in (1, 2):
            load(cloud, env=env, owner=owner, mask=8)
    for batch in (cloud, plain):
        batch.start_environments(ids(range(128)))
        step(batch, [1] * 128)
    for view in (
        "actor_hands",
        "choice_masks",
        "player_observations",
        "chance_observations",
        "attack_effect_observations",
    ):
        np.testing.assert_array_equal(getattr(cloud, view)(), getattr(plain, view)())
    step(cloud, [0] * 128)
    step(plain, [0] * 128)
    assert cloud.chance_hit_count == cloud.dark_cloud_hit_count == 128
    assert plain.dark_cloud_hit_count == 0 and plain.chance_miss_count > 0
    assert np.all(cloud.attack_effect_snapshot()[:, 5] == 1)


def test_mixed_dark_cloud_targets_are_chosen_before_roll_and_only_target_status_matters():
    batch = game(size=256)
    for env in range(256):
        seed(batch, [99], env=env)
        load(batch, env=env, mask=8)  # Source's Cloud must not guarantee its outgoing attacks.
        load(batch, env=env, owner=1, mask=8)
    batch.start_environments(ids(range(256)))
    step(batch, [1] * 256)
    step(batch, [0] * 256)
    # Independent source-pinned probability probe (not a claimed server RNG).
    mask = (1 << 64) - 1

    def rank(env, stream, bound):
        state = (67 ^ ((env + 1) * 0x9E3779B97F4A7C15) ^ 0xBF58476D1CE4E5B9 ^ stream) & mask
        state = (state + 0x9E3779B97F4A7C15) & mask
        word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
        word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
        return (word ^ (word >> 31)) % bound

    targets = np.asarray([1 + rank(env, 0xC6BC279692B5C323, 2) for env in range(256)])
    hits = np.asarray(
        [
            target == 1 or rank(env, 0xE19B01AA9D42C633, 100) < 25
            for env, target in enumerate(targets)
        ]
    )
    np.testing.assert_array_equal(batch.chance_snapshot()[:, 1], hits)
    assert batch.dark_cloud_hit_count == int(np.count_nonzero(targets == 1))
    np.testing.assert_array_equal(batch.episode_snapshot()[hits, 2], targets[hits])


def test_dark_cloud_forced_hit_skips_ticket_so_next_uncursed_cast_uses_first_roll():
    batch = game(size=256, players=2)
    for env in range(256):
        seed(batch, [99, 99], env=env)
        seed(batch, [238], env=env, owner=1)  # Source-pinned full cure, no manual state injection.
        load(batch, env=env, owner=1, mask=8)
    batch.start_environments(ids(range(256)))
    for choice in (1, 0, 0, 1, 1, 0):
        step(batch, [choice] * 256)
    # First three commands force/resolve the hit, fourth clears Cloud, last two cast again.
    assert batch.dark_cloud_hit_count == 256
    assert np.all(batch.chance_snapshot()[:, 0] == 2)
    mask = (1 << 64) - 1
    expected = []
    for env in range(256):
        state = (
            67 ^ ((env + 1) * 0x9E3779B97F4A7C15) ^ 0xBF58476D1CE4E5B9 ^ 0xE19B01AA9D42C633
        ) & mask
        state = (state + 0x9E3779B97F4A7C15) & mask
        word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
        word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
        expected.append((word ^ (word >> 31)) % 100 < 25)
    np.testing.assert_array_equal(
        batch.chance_snapshot()[:, 1], 1 + np.asarray(expected, dtype=int)
    )


@pytest.mark.parametrize("model", [27, 216, 221, 222, 223])
def test_bounce_preserves_effect_source_until_final_target_resolution(model):
    # Reflect once to seat zero, then seat zero bounces if the origin is a miracle.
    # For the NE absorption weapon, give the source a Bouncing Sword response.
    batch = game(size=128, refill=True)
    response = 21 if ATTACKS[model][2] == 0 else 234
    for env in range(128):
        seed(batch, [model, response], env=env)
        seed(batch, [190], env=env, owner=1)
    batch.start_environments(ids(range(128)))
    for choice in (1, 0, 20, 1, 0, 1, 0):
        step(batch, [choice] * 128)
    assert batch.reflection_count == batch.bounce_count == 128
    assert np.all(batch.attack_effect_observations()[:, 3] == 1)  # Reflector remains source.
    assert batch.automatic_gift_count == batch.absorption_count == batch.inflicted_curse_count == 0
    targets = batch.episode_snapshot()[:, 2].copy()
    assert set(targets) == {0, 1, 2}
    step(batch, [0] * 128)
    attack = ATTACKS[model][0]
    kind, value = next(row[1:] for row in EFFECTS if row[0] == model)
    for env, target in enumerate(targets):
        states = batch.diagnostic_players()[env]
        if kind == 1:
            assert states[1, 0] == (40 if target == 1 else 40 + attack)
            assert batch.attack_effect_snapshot()[env, 1] == attack
        else:
            assert states[target, 4] == value
        assert states[:, 5].tolist() == [1, 0, 0]
    assert batch.automatic_gift_count == 128 * 3


def test_lethal_self_bounce_does_not_resurrect_absorption_source():
    batch = game(size=128)
    for env in range(128):
        seed(batch, [27, 21], env=env)
        seed(batch, [190], env=env, owner=1)
        load(batch, env=env, owner=1, hp=2)
    batch.start_environments(ids(range(128)))
    for choice in (1, 0, 20, 1, 0, 1, 0):
        step(batch, [choice] * 128)
    targets = batch.episode_snapshot()[:, 2].copy()
    step(batch, [0] * 128)
    assert np.any(targets == 1)
    for env in np.flatnonzero(targets == 1):
        assert batch.diagnostic_players()[env, 1, 0] == 0
        assert batch.attack_effect_snapshot()[env, :2].tolist() == [0, 0]


def test_damage_curse_does_not_afflict_a_target_killed_by_the_attack():
    batch = game()
    load(batch, owner=1, hp=2)
    begin(batch, 36)
    step(batch, [0])
    assert batch.hp_damage == 2 and batch.inflicted_curse_count == 0
    assert batch.diagnostic_players()[0, 1, 0] == 0
    assert batch.diagnostic_players()[0, 1, 4] == 0


@pytest.mark.parametrize("source_hp,source_illness,outcome,winner", [(40, 0, 1, 0), (1, 1, 2, -1)])
def test_direct_illness_death_and_owner_tick_choose_real_ending_before_limits(
    source_hp, source_illness, outcome, winner
):
    batch = game(players=2, max_turns=1)
    load(batch, hp=source_hp, illness=source_illness)
    load(batch, owner=1, hp=2, illness=4)
    begin(batch, 219)
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, outcome, winner]
    assert batch.hp_damage == 0 and batch.illness_effect_damage == 2
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]


@pytest.mark.parametrize("model", [219, 220, 221, 222, 223])
def test_direct_curse_reserves_without_cost_and_has_only_living_enemy_targets(model):
    batch = game()
    seed(batch, [model, 9])
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0, 1]
    step(batch, [0])
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [20, 21]
    assert batch.mp_spent == batch.attack_count == 0
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [19])  # No self-target choice, including Heaven Wind.
    same(batch, before)


def test_late_hidden_defense_failure_rolls_back_absorption_and_all_batch_counters():
    batch = game(size=2, refill=True)
    for env in range(2):
        seed(batch, [27], env=env)
    batch.seed_hand(1, 1, ids([[101, 189, 190, 0]]))
    batch.start_environments(ids([0, 1]))
    for choice in (1, 0, 20):
        step(batch, [choice, choice])
    step(batch, [1], [1])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [0, 0])
    same(batch, before)
    step(batch, [1], [1])  # Undo hidden selection, then retry both actual resolutions.
    step(batch, [0, 0])
    assert batch.absorbed_hp == 14 and batch.absorption_count == 2
    assert batch.automatic_gift_count == 2


def test_effect_views_are_owned_readonly_and_reset_episode_counters_not_lifetime_totals():
    batch = game()
    begin(batch, 27)
    pending = batch.attack_effect_observations()
    assert not pending.flags.writeable
    step(batch, [0])
    previous = batch.attack_effect_snapshot()
    assert not previous.flags.writeable and previous[0, 1] == 7
    batch.reset_environments(ids([0]))
    assert not np.any(batch.attack_effect_observations()) and not np.any(
        batch.attack_effect_snapshot()
    )
    assert previous[0, 1] == 7 and pending[0].tolist() == [1, 1, 0, 0]
    assert batch.absorbed_hp == 7


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(27, 0, 0)],
        [(27, 6, 0)],
        [(27, 1, 1)],
        [(27, 2, 3)],
        [(27, 3, 0)],
        [(27, 3, 5)],
        [(27, 4, 1)],
        [(219, 3, 1)],
        [(219, 5, 0)],
        [(27, 1, 0)] * 2,
        [(191, 1, 0)],
    ],
)
def test_malformed_native_effect_profiles_fail_closed(profiles):
    with pytest.raises(ValueError):
        game(effects=profiles)


def test_source_factory_gates_new_effects_and_cannot_relabel_metadata():
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    assert configured.metadata.kernel_schema_version == 7
    assert len(EFFECTS) == 20 and PLAN.integrated_artifact_effect_count == 195
    assert (
        not configured.metadata.full_game_training_ready
        and not configured.metadata.promotion_eligible
    )
    for change in (
        {"attack_effect_observation_fields": ("true_model",)},
        {"attack_effect_snapshot_fields": ("hidden_roll",)},
        {"absorption": "original-owner"},
        {"full_game_training_ready": True},
    ):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate({**configured.metadata.model_dump(), **change})
    for change in (
        {"attack_effect_profiles": ()},
        {"attack_effect_fields": ("true_id",)},
        {"direct_curse_count": 6},
    ):
        with pytest.raises(ValidationError):
            FullGameCombatPlan.model_validate({**PLAN.combat.model_dump(), **change})
