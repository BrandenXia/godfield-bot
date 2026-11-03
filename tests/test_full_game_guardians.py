"""Joined guardian timing/effects, independent tickets, hidden-safe views and rollback."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan, create_development_full_game_batch
from godfield_bot.full_game_guardians import FullGameGuardianPlan, build_full_game_guardian_plan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def tickets(seed, env, stream, epoch=1):
    mask = 2**64 - 1
    word = (
        seed
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ stream
    )
    while True:
        word = (word + 0x9E3779B97F4A7C15) & mask
        value = word
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        yield value ^ (value >> 31)


ACTIVATING_SEED = next(
    seed for seed in range(1000) if next(tickets(seed, 0, 0x9216D5D98979FB1B)) % 100 < 25
)


def game(
    *,
    size=1,
    players=3,
    seed=ACTIVATING_SEED,
    profiles=PLAN.guardians.profiles,
    turns=100,
    decisions=1000,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        seed=seed,
        max_turns=turns,
        max_decisions=decisions,
        initial_hp=100,
        initial_mp=20,
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
        guardian_profiles=None if profiles is None else ids(profiles).reshape(-1, 10),
        gift_profiles=ids(PLAN.gifts.model_weights),
    )


def deterministic(model, **options):
    profile = next(p for p in PLAN.guardians.profiles if p[0] == model)
    return game(profiles=((*profile[:2], 20, *profile[3:]),), **options)


def hand(batch, values, *, env=0, owner=0):
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + i + 1, *(v if isinstance(v, tuple) else (v, 0, 0))]
                for i, v in enumerate(values)
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=100, mp=20, cp=5, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids([[e, *rows[e, :4], c] for e, c in zip(envs, choices, strict=True)]).reshape(-1, 6)
    )
    stats = batch.attack_family_snapshot()
    np.testing.assert_array_equal(
        stats[:, 0], stats[:, 2] + stats[:, 3] + stats[:, 13] + (stats[:, 14] > 0)
    )


def drain(batch):
    for _ in range(200):
        envs = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4)
        if not len(envs):
            return
        step(batch, [0] * len(envs), envs)
    raise AssertionError("guardian family drain exceeded bound")


def snapshot(batch):
    return tuple(
        getattr(batch, n)()
        for n in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "player_observations",
            "guardian_snapshot",
            "guardian_statistics",
            "guardian_model_counts",
            "guardian_observations",
            "guardian_effect_observations",
            "attack_family_snapshot",
            "revival_snapshot",
        )
    )


def same(left, right):
    for a, b in zip(left, right, strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("profile", PLAN.guardians.profiles, ids=lambda p: str(p[0]))
@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("target_mask", [0, 8])
def test_all40_standard_effects_and_diamond_origin_against_independent_oracles(
    profile, players, target_mask
):
    model, group, _, attack, element, rate, kind, value, curse, origin = profile
    batch = deterministic(model, players=players)
    for owner in range(players):
        hand(batch, [208], owner=owner)
        load(batch, owner=owner, mask=target_mask)
    hand(batch, [(127, 142, 0)], owner=1)
    load(batch, owner=1, hp=50, mp=10, cp=2, illness=2, mask=15)
    batch.seed_guardians(ids([0]), ids([1]), ids([group + 1]))
    batch.start_environments(ids([0]))
    before = batch.diagnostic_players()[0].copy()
    step(batch, [0])
    auto = 4 <= kind <= 8
    target = (
        1
        if auto
        else [p for p in range(players) if p != 1][
            next(tickets(ACTIVATING_SEED, 0, 0x2FFD72DBD01ADFB7)) % (players - 1)
        ]
    )
    hit = target_mask == 8 or next(tickets(ACTIVATING_SEED, 0, 0xB8E1AFED6A267E96)) % 100 < rate
    if not auto and hit:
        assert batch.guardian_effect_observations().tolist() == [[1, model, 1, target]]
        assert batch.pending_observations()[0, 5] == origin
    expected = before.copy()
    expected[0, 5] += 1
    damage = 0
    if auto:
        if kind == 4:
            expected[1, 3:5] = 0
        elif kind == 5:
            expected[1, 0] += value
        elif kind == 6:
            expected[1, 1] += value
        elif kind == 7:
            expected[1, 2] += value
        else:
            expected[:, 2] += value
    elif hit:
        if attack:
            damage = 100 if element == 6 else attack
            expected[target, 0] = 10 if element == 6 else 100 - attack
        if kind == 1:
            expected[1, 0] += damage
        elif kind in (2, 3):
            expected[target, 4] |= curse
        elif kind == 9:
            expected[target, 2] += value
        elif kind == 10:
            expected[target, 2] -= value
            expected[1, 2] += value
    drain(batch)
    np.testing.assert_array_equal(batch.diagnostic_players()[0], expected)
    stats = batch.guardian_statistics()[0]
    assert stats[2:5].tolist() == [1, 1, 1] and stats[6:8].tolist() == [1, 1]
    assert stats[8] == int(not auto and not hit) and stats[13] == damage
    assert batch.attack_count == batch.resolved_attack_count == batch.chance_count == 0
    assert batch.ascension_hp_damage == 0 and not batch.guardian_effect_observations().any()
    assert batch.episode_snapshot()[0, 3] == 1
    if kind == 4:
        assert batch.diagnostic_inventory()[0, 1, 0, 2] == 0


@pytest.mark.parametrize("seed", [0, 67, 68, 999])
def test_regular_activation_and_model_distribution_with_independent_batched_tickets(seed):
    batch = game(size=64, seed=seed)
    for env in range(64):
        load(batch, env=env, owner=1, hp=50, mp=10)
    batch.seed_guardians(
        ids(range(64)), ids([1] * 64), ids([7] * 64)
    )  # Neptune's five automatic effects.
    batch.start_environments(ids(range(64)))
    step(batch, [0] * 64)
    for env in range(64):
        active = next(tickets(seed, env, 0x9216D5D98979FB1B)) % 100 < 25
        stats = batch.guardian_statistics()[env]
        assert stats[2] == 1 and stats[3] == int(active)
        if active:
            rank = next(tickets(seed, env, 0xD1310BA698DFB5AC)) % 20
            model = 275 + next(i for i, bound in enumerate((6, 11, 15, 18, 20)) if rank < bound)
            state = batch.diagnostic_players()[env, 1]
            assert state[0] == 50 + ({276: 5, 278: 10}.get(model, 0))
            assert state[1] == 10 + ({277: 5, 279: 10}.get(model, 0))
    assert (
        np.all(batch.diagnostic_players()[:, 0, 5] == 1)
        and not batch.diagnostic_players()[:, 1:, 5].any()
    )


@pytest.mark.parametrize("seed", [0, 67, 999])
def test_damage_departure_native25_trigger_and_separate10_stream(seed):
    batch = game(size=64, seed=seed)
    for env in range(64):
        hand(batch, [35], env=env)
    batch.seed_guardians(ids(range(64)), ids([1] * 64), ids([7] * 64))
    batch.start_environments(ids(range(64)))
    for c in (1, 0, 20, 0):
        step(batch, [c] * 64)
    for env in range(64):
        leaves = next(tickets(seed, env, 0xBA7C9045F12C7F99)) % 100 < 10
        stats = batch.guardian_statistics()[env]
        assert stats[10:12].tolist() == [1, int(leaves)]
        assert batch.guardian_snapshot()[env, 1, 0] == (0 if leaves else 7)
        assert stats[2] == int(not leaves)


def test_same_owner_turn_does_not_trigger_guardian_and_counter_responses_do_not_recurse():
    batch = deterministic(264, players=2)
    hand(batch, [189, 184], owner=0)
    load(batch, owner=1, mask=8)
    batch.seed_guardians(ids([0, 0]), ids([0, 1]), ids([4, 4]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.guardian_statistics()[0, 2] == 1
    assert batch.guardian_effect_observations()[0, 1] == 264
    step(batch, [1])
    step(batch, [2])
    step(batch, [0])
    drain(batch)
    assert batch.guardian_statistics()[0, 2] == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]


def test_super_mirror_changes_current_source_of_guardian_absorption():
    batch = deterministic(268, players=2)
    hand(batch, [190], owner=0)
    load(batch, owner=0, hp=40)
    load(batch, owner=1, hp=50)
    batch.seed_guardians(ids([0]), ids([1]), ids([5]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    step(batch, [1])
    step(batch, [0])
    assert batch.guardian_effect_observations().tolist() == [[1, 268, 0, 1]]
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [45, 45]
    assert batch.absorbed_hp == 5 and batch.guardian_statistics()[0, 13] == 5


def test_final_death_clears_guardian_and_owned_sun_precedes_stochastic_departure():
    for sun in (False, True):
        batch = game(seed=67)
        hand(batch, [57])
        hand(batch, [208] if sun else [], owner=1)
        load(batch, owner=1, hp=1)
        batch.seed_guardians(ids([0]), ids([1]), ids([7]))
        batch.start_environments(ids([0]))
        for c in (1, 0, 20, 0):
            step(batch, [c])
        stats = batch.guardian_statistics()[0]
        assert stats[12] == int(not sun) and stats[10] == int(sun)
        assert batch.revival_count == int(sun)


def test_fine_reuses_payment_waterfall_and_can_revive_before_guardian_damage_check():
    batch = deterministic(282, players=2)
    hand(batch, [208])
    load(batch, hp=1, mp=0, cp=0)
    load(batch, owner=1, cp=99)
    batch.seed_guardians(ids([0]), ids([1]), ids([8]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    step(batch, [0])
    assert batch.diagnostic_players()[0, 0, :3].tolist() == [10, 0, 0]
    assert batch.diagnostic_players()[0, 1, 2] == 100
    assert batch.guardian_statistics()[0, 16:18].tolist() == [1, 1]
    assert batch.revival_count == 1 and not batch.counter_snapshot()[0, 7:9].any()


def test_guardian_effect_family_waits_before_turn_limit_without_ticking_twice():
    batch = deterministic(264, players=2, turns=1)
    batch.seed_guardians(ids([0]), ids([1]), ids([4]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 4 and batch.attack_family_snapshot()[0, 15] == 1
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 13
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]


@pytest.mark.parametrize("group", [9, 10])
def test_special_guardians_are_not_silently_dropped_or_modeled_as_noops(group):
    batch = game()
    batch.seed_guardians(ids([0]), ids([1]), ids([group]))
    batch.start_environments(ids([0]))
    before = snapshot(batch)
    with pytest.raises(ValueError, match="Earth/Moon"):
        step(batch, [0])
    same(before, snapshot(batch))


def test_late_special_guardian_error_rolls_back_earlier_effects_and_rng():
    batch, reference = game(size=2), game(size=2)
    # Pick a seed for which both environments activate on their first check.
    seed = next(
        s
        for s in range(10000)
        if all(next(tickets(s, e, 0x9216D5D98979FB1B)) % 100 < 25 for e in (0, 1))
    )
    batch, reference = game(size=2, seed=seed), game(size=2, seed=seed)
    for b in (batch, reference):
        load(b, owner=1, hp=50)
        b.seed_guardians(ids([0, 1]), ids([1, 1]), ids([7, 9]))
        b.start_environments(ids([0, 1]))
    before = snapshot(batch)
    with pytest.raises(ValueError, match="Earth/Moon"):
        step(batch, [0, 0])
    same(before, snapshot(batch))
    step(batch, [0], [0])
    step(reference, [0], [0])
    same(snapshot(batch), snapshot(reference))


def test_fog_hides_other_guardian_portraits_and_never_exposes_instance_ids_or_future_effects():
    first, second = game(), game()
    for i, b in enumerate((first, second)):
        load(b, mask=1)
        b.seed_guardians(ids([0]), ids([1]), ids([1 + i]))
        b.start_environments(ids([0]))
    assert first.guardian_snapshot()[0, 1, 0] != second.guardian_snapshot()[0, 1, 0]
    np.testing.assert_array_equal(first.guardian_observations(), second.guardian_observations())
    assert not first.guardian_effect_observations().any()


def test_seed_guardians_only_trusted_setup_atomic_owned_views_and_reset():
    batch = game(size=2)
    before = batch.guardian_snapshot()
    assert not before.flags.writeable
    with pytest.raises(ValueError):
        batch.seed_guardians(ids([0, 1]), ids([1, 1]), ids([1, 11]))
    np.testing.assert_array_equal(before, batch.guardian_snapshot())
    batch.seed_guardians(ids([0, 1]), ids([1, 1]), ids([1, 2]))
    old = batch.guardian_snapshot()
    batch.start_environments(ids([0, 1]))
    with pytest.raises(ValueError):
        batch.seed_guardians(ids([0]), ids([1]), ids([3]))
    batch.reset_environments(ids([0]))
    assert old[0, 1, 0] == 1 and not batch.guardian_snapshot()[0].any()
    assert batch.guardian_snapshot()[1, 1, 0] == 2


@pytest.mark.parametrize("model,cost", [(201, 0), (239, 15)])
def test_summon_uses_all10_outcomes_once_per_confirm_not_per_reservation(model, cost):
    c = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=128,
        capacity=18,
        initial_hp=100,
        initial_mp=20,
    )
    batch = c.batch
    for env in range(128):
        hand(batch, [model], env=env)
    batch.start_environments(ids(range(128)))
    step(batch, [1] * 128)
    assert not batch.guardian_snapshot().any()
    step(batch, [0] * 128)
    expected = [1 + next(tickets(67, e, 0x3F84D5B5B5470917)) % 10 for e in range(128)]
    np.testing.assert_array_equal(batch.guardian_snapshot()[:, 0, 0], expected)
    assert set(expected) == set(range(1, 11))
    assert batch.mp_spent == 128 * cost and np.all(batch.guardian_statistics()[:, 0] == 1)
    assert batch.consumed_count == (128 if model == 201 else 0)
    assert batch.miracle_use_count == (128 if model == 239 else 0)


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ()},
        {"notes": ()},
        {"group_names": ("mars",)},
        {"unsupported_special_model_ids": (285,)},
        {"complete_guardian_effects_implemented": True},
        {"official_fidelity_verified": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
    ],
)
def test_guardian_source_coverage_and_gates_cannot_be_relabelled(change):
    with pytest.raises(ValidationError):
        FullGameGuardianPlan.model_validate(PLAN.guardians.model_dump() | change)


def test_nested_bow_finishes_and_dead_later_guardian_is_suppressed_without_new_tick():
    seed = next(
        s
        for s in range(10000)
        if [v % 100 < 25 for v in take(tickets(s, 0, 0x9216D5D98979FB1B), 2)] == [True, True]
        and next(tickets(s, 0, 0x2FFD72DBD01ADFB7)) % 2 == 1
    )
    batch = deterministic(264, seed=seed)
    hand(batch, [112], owner=2)
    load(batch, mask=8)
    load(batch, owner=1, mask=8)
    load(batch, owner=2, hp=1)
    batch.seed_guardians(ids([0, 0]), ids([1, 2]), ids([4, 4]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.episode_snapshot()[0, 2] == 2
    step(batch, [0])
    assert batch.attack_family_snapshot()[0, 14] == 3
    drain(batch)
    assert batch.guardian_statistics()[0, 6:10].tolist() == [2, 1, 0, 1]
    assert batch.guardian_statistics()[0, 13] == 1 and batch.guardian_resolved_count == 1
    assert batch.ascension_hp_damage == 60
    assert batch.diagnostic_players()[0, :, 0].tolist() == [70, 70, 0]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def take(stream, count):
    return [next(stream) for _ in range(count)]


@pytest.mark.parametrize("cause", ["periodic", "recoil", "utility", "infliction"])
def test_positive_hp_debit_paths_share_departure_hook_not_just_defended_attacks(cause):
    seed = ACTIVATING_SEED
    if cause == "utility":
        seed = next(s for s in range(1000) if next(tickets(s, 0, 0x13198A2E03707344)) % 2 == 1)
    batch = game(seed=seed)
    model = {"periodic": 127, "recoil": 53, "utility": 202, "infliction": 198}[cause]
    hand(batch, [model, 208])
    load(
        batch,
        hp=10 if cause == "utility" else 40,
        illness=1 if cause == "periodic" else 4 if cause == "infliction" else 0,
    )
    batch.seed_guardians(ids([0]), ids([0]), ids([7]))
    batch.start_environments(ids([0]))
    if cause == "periodic":
        for c in (19, 1, 0):
            step(batch, [c])
    else:
        step(batch, [1])
        step(batch, [0])
        if cause == "recoil":
            step(batch, [20])
            step(batch, [0])
    assert batch.guardian_statistics()[0, 10] >= 1


@pytest.mark.parametrize("model", [201, 239])
def test_summon_replaces_owned_identity_and_waived_release_works_at_zero_mp(model):
    c = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=1,
        capacity=18,
        initial_mp=0,
    )
    batch = c.batch
    hand(batch, [model, 204])
    batch.seed_guardians(ids([0]), ids([0]), ids([7]))
    old = batch.guardian_snapshot()
    batch.start_environments(ids([0]))
    step(batch, [1])
    if model == 239:
        assert not batch.choice_masks()[0, 0]
        step(batch, [2])
    step(batch, [0])
    assert batch.guardian_summon_count == 1 and batch.guardian_statistics()[0, 1] == 1
    assert batch.guardian_snapshot()[0, 0, 1] > old[0, 0, 1]
    assert batch.mp_spent == 0
    if model == 239:
        assert batch.waived_mp == 15 and batch.miracle_use_count == 1


def test_late_hidden_summon_failure_rolls_back_identity_rng_and_lifetime_counters():
    from test_full_game_generated import game as complete_raw_game

    # Raw strict mode retains the atomic error; the source factory explicitly
    # opts into the separately reviewed ineffective-component rule.
    batch = complete_raw_game(size=2, seed=67, initial_hp=40, initial_mp=10, initial_cp=0)
    hand(batch, [201], env=0)
    hand(batch, [(208, 201, 0)], env=1)
    batch.start_environments(ids([0, 1]))
    step(batch, [1, 1])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [0, 0])
    same(before, snapshot(batch))
    assert batch.guardian_summon_count == 0
    step(batch, [0], [0])
    assert batch.guardian_summon_count == 1


@pytest.mark.parametrize(
    "change",
    [{"detail": ("Wrong ATK",)}, {"image_path": "/images/wrong.webp"}, {"element_image_paths": ()}],
)
def test_complete_bible_guardian_profile_digest_rejects_drift(change):
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    group = bible.catalog["guardians"]
    altered = bible.model_copy(
        update={
            "catalog": bible.catalog
            | {
                "guardians": group.model_copy(
                    update={"items": (group.items[0].model_copy(update=change), *group.items[1:])}
                )
            }
        }
    )
    with pytest.raises(ValueError, match="Bible effect contracts"):
        build_full_game_guardian_plan(read_api_catalog_snapshot(CATALOG), altered)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: (),
        lambda p: (p[0], p[0]),
        lambda p: ((*p[0][:2], 0, *p[0][3:]),),
        lambda p: ((*p[0][:4], 7, *p[0][5:]),),
        lambda p: ((*p[0][:6], 11, *p[0][7:]),),
        lambda p: ((239, *p[0][1:]),),
    ],
)
def test_raw_guardian_profiles_reject_empty_duplicate_invalid_bound_or_category(change):
    with pytest.raises(ValueError, match="guardian profile"):
        game(profiles=change(PLAN.guardians.profiles))


def test_guardian_statistics_lifetime_and_readonly_views_survive_only_the_right_reset_scope():
    batch = deterministic(264, players=2)
    batch.seed_guardians(ids([0]), ids([1]), ids([4]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    step(batch, [0])
    assert batch.guardian_activation_count == batch.guardian_resolved_count == 1
    assert batch.guardian_hp_damage == 15
    views = (batch.guardian_snapshot(), batch.guardian_statistics(), batch.guardian_model_counts())
    for view in views:
        assert not view.flags.writeable
        with pytest.raises(ValueError):
            view.flat[0] = 9
    batch.reset_environments(ids([0]))
    assert not batch.guardian_statistics().any() and not batch.guardian_model_counts().any()
    assert batch.guardian_hp_damage == 15 and views[1][0, 13] == 15


@pytest.mark.parametrize("players", [2, 3, 9])
def test_bounded_mixed_episode_liveness_with_standard_guardians_inventory_and_illness(players):
    size, turns = 16, 48
    batch = game(size=size, players=players, seed=67, turns=turns, decisions=32 * turns)
    for env in range(size):
        for owner in range(players):
            hand(batch, [35, 127, 208, 237], env=env, owner=owner)
            load(batch, env=env, owner=owner, hp=30, mp=10, cp=0, illness=owner % 4)
    envs = np.repeat(np.arange(size, dtype=np.int64), players)
    owners = np.tile(np.arange(players, dtype=np.int64), size)
    batch.seed_guardians(envs, owners, (envs + owners) % 8 + 1)
    batch.start_environments(ids(range(size)))
    for _ in range(32 * turns):
        rows = batch.episode_snapshot()
        active = np.flatnonzero(np.isin(rows[:, 3], (1, 2, 3, 4)))
        if not len(active):
            break
        masks, hands, observations = (
            batch.choice_masks(),
            batch.actor_hands(),
            batch.player_observations(),
        )
        choices = []
        for env in active:
            phase = rows[env, 3]
            if phase == 1:
                legal = [
                    slot + 1
                    for slot in range(18)
                    if masks[env, slot + 1]
                    and (
                        hands[env, slot, 1] == 35
                        or (hands[env, slot, 1] == 237 and observations[env, 0, 4] >= 3)
                    )
                ]
                choice = legal[0] if legal else 0
            elif phase == 3:
                choice = int(np.flatnonzero(masks[env])[0])
            elif phase == 2 and not masks[env, 0]:
                choice = int(batch.attack_order()[env, 0])
            else:
                choice = 0
            choices.append(choice)
        step(batch, choices, active)
    else:
        raise AssertionError("standard guardian episode driver exceeded explicit decision bound")
    rows = batch.episode_snapshot()
    assert np.isin(rows[:, 3], (12, 13)).all()
    assert (batch.diagnostic_players()[:, :, 5].sum(axis=1) == rows[:, 4]).all()
    assert batch.guardian_activation_count > 0 and batch.guardian_resolved_count > 0
    assert not batch.choice_masks().any()
