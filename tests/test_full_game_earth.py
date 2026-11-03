"""Provisional Drop receipts: complete category pool, native RNG and custody."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import drain

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan, create_development_full_game_batch
from godfield_bot.full_game_guardians import FullGameGuardianPlan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
EARTH = tuple(row for row in PLAN.guardians.generated_profiles if row[0] == 9)
EARTH_DROP = tuple(row for row in EARTH if dict(PLAN.guardians.action_profiles)[row[1]] == 6)


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


def seed_hand(b, models, owner=0, env=0):
    b.seed_hand(
        env,
        owner,
        ids([[owner * 100 + i + 1, m, 0, 0] for i, m in enumerate(models)]).reshape(-1, 4),
    )


def commands(b, choices, envs=None):
    envs = range(len(choices)) if envs is None else envs
    rows = b.episode_snapshot()
    return ids([[env, *rows[env, :4], c] for env, c in zip(envs, choices, strict=True)])


def step(b, choices, envs=None):
    b.step(commands(b, choices, envs))
    q = b.attack_family_snapshot()
    np.testing.assert_array_equal(q[:, 0], q[:, 2] + q[:, 3] + q[:, 13] + (q[:, 14] > 0))


def start(b, size=1, group=9):
    b.seed_guardians(ids(range(size)), ids([1] * size), ids([group] * size))
    b.start_environments(ids(range(size)))


def snapshot(b):
    return tuple(
        getattr(b, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "guardian_snapshot",
            "guardian_statistics",
            "guardian_model_counts",
            "guardian_generated_snapshot",
            "guardian_generated_model_counts",
            "attack_family_snapshot",
            "acquisition_snapshot",
            "attack_effect_observations",
            "guardian_effect_observations",
        )
    )


def same(first, second):
    for a, b in zip(first, second, strict=True):
        np.testing.assert_array_equal(a, b)


def test_source_pools_cover_every_held_card_with_pinned_not_uniform_weights():
    rows = PLAN.guardians.generated_profiles
    assert len(rows) == 237 and len(EARTH) == 207
    assert sum(row[3] for row in EARTH) == 470
    moon = tuple(r for r in rows if r[0] == 10)
    assert len(moon) == sum(r[3] for r in moon) == 30
    assert {r[1] for r in rows} == {r[0] for r in PLAN.inventory.profiles}
    assert hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest() == (
        PLAN.guardians.generated_sha256
    )
    assert PLAN.guardians.unsupported_special_model_ids == ()
    assert not PLAN.full_game_training_ready and not PLAN.guardians.promotion_eligible


@pytest.mark.parametrize("profile", EARTH_DROP, ids=lambda row: str(row[1]))
@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("dream", [False, True])
def test_every82_drop_models_are_fresh_receipts_not_owned_uses(profile, players, dream):
    b = game(players=players, pool=(profile,))
    for owner in range(players):
        seed_hand(b, [6], owner)
    target = [p for p in range(players) if p != 1][
        next(tickets(SEED, 0, 0x2FFD72DBD01ADFB7)) % (players - 1)
    ]
    if dream:
        b.seed_players(ids([0]), ids([target]), ids([[50, 0, 0, 0]]), ids([2]))
    start(b)
    before = b.diagnostic_inventory().copy()
    step(b, [0])
    assert int(b.episode_snapshot()[0, 2]) == target
    assert b.guardian_effect_observations()[0].tolist() == [1, 285, 1, target]
    assert b.guardian_generated_snapshot()[0, :7].tolist() == [1, 1, 0, 0, 0, 0, 0]
    np.testing.assert_array_equal(before, b.diagnostic_inventory())
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0]
    step(b, [0])
    received = b.diagnostic_inventory()[0, target, 1]
    assert received[0] == (players - 1) * 100 + 2
    assert received[1] == profile[1] and received[3] == 0
    disguised = dream and next(tickets(SEED, 0, 0xCE5C3E169B87931E)) % 100 < 50
    assert bool(received[2]) == disguised
    if disguised:
        assert dict(PLAN.inventory.profiles)[int(received[2])] == profile[2]
    assert b.guardian_generated_snapshot()[0, :7].tolist() == [1, 1, 1, int(disguised), 0, 0, 0]
    assert b.guardian_generated_model_counts()[0, profile[1] - 3] == 1
    np.testing.assert_array_equal(before[0, :, 0], b.diagnostic_inventory()[0, :, 0])
    assert b.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)
    assert b.episode_snapshot()[0, 2:5].tolist() == [1, 1, 1]
    assert b.mp_spent == b.consumed_count == b.miracle_use_count == b.gift_count == 0
    assert b.hp_damage == b.attack_count == b.resolved_attack_count == 0


@pytest.mark.parametrize("players", [2, 3, 9])
def test_native_category_weighted_draws_match_independent_tickets_without_forcing_activation(
    players,
):
    size = 4096
    b = game(size=size, players=players, seed=67)
    for env in range(size):
        for owner in range(players):
            seed_hand(b, [208], owner, env)
    start(b, size)
    step(b, [0] * size)
    activated = []
    counts = b.guardian_generated_model_counts()
    for env in range(size):
        active = next(tickets(67, env, 0x9216D5D98979FB1B)) % 100 < 25
        if not active:
            assert not b.guardian_generated_snapshot()[env].any()
            continue
        activated.append(env)
        rank = next(tickets(67, env, 0x2BA9C55D741831F6)) % 470
        total = 0
        for _, drawn_model, _, weight in EARTH:
            total += weight
            if rank < total:
                model = drawn_model
                break
        assert counts[env, model - 3] == 1
    assert 850 < len(activated) < 1200
    drain(b)
    assert np.all(b.episode_snapshot()[:, 3] == 1)
    assert b.guardian_generated_snapshot()[:, 1].sum() == len(activated)
    assert b.diagnostic_players()[:, :, 5].sum() == size


@pytest.mark.parametrize("oldest", [False, True])
def test_drop_cap_is_explicit_and_rejected_receipt_rolls_back_rng_and_state(oldest):
    b = game(players=2, capacity=2, hand_limit=2, oldest_overflow=oldest, pool=((9, 127, 2, 2),))
    seed_hand(b, [6, 7])
    start(b)
    step(b, [0])
    before = snapshot(b)
    if oldest:
        step(b, [0])
        assert b.diagnostic_inventory()[0, 0, :, 1].tolist() == [7, 127]
        assert b.guardian_generated_snapshot()[0, 4] == b.overflow_count == 1
    else:
        with pytest.raises(ValueError, match="overflow"):
            step(b, [0])
        same(before, snapshot(b))


def test_super_mirror_redirects_drop_receipt_without_consuming_guardian_owner_hand():
    b = game(players=2, pool=((9, 127, 2, 2),))
    seed_hand(b, [190])
    seed_hand(b, [6], 1)
    start(b)
    step(b, [0])
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0, 1]
    step(b, [1])
    step(b, [0])
    assert b.guardian_effect_observations()[0].tolist() == [1, 285, 0, 1]
    step(b, [0])
    assert b.diagnostic_inventory()[0, 1, :2, 1].tolist() == [6, 127]
    assert b.consumed_count == b.reflection_count == 1 and b.mp_spent == 0
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0]


def test_late_receipt_failure_rolls_back_other_environment_and_disguise_stream():
    seed = next(
        s
        for s in range(10000)
        if all(next(tickets(s, env, 0x9216D5D98979FB1B)) % 100 < 25 for env in (0, 1))
    )
    b, reference = [
        game(size=2, players=2, seed=seed, capacity=1, pool=(EARTH_DROP[0],)) for _ in range(2)
    ]
    for current in (b, reference):
        seed_hand(current, [6], env=1)
        current.seed_players(ids([0, 1]), ids([0, 0]), ids([[50, 0, 0, 0]] * 2), ids([2, 2]))
        start(current, 2)
        step(current, [0, 0])
    before = snapshot(b)
    with pytest.raises(ValueError, match="overflow"):
        step(b, [0, 0])
    same(before, snapshot(b))
    step(b, [0], [0])
    step(reference, [0], [0])
    same(snapshot(b), snapshot(reference))


def test_dead_earth_owner_suppresses_queued_drop_after_nested_postdeath_bow():
    seed = next(
        s
        for s in range(10000)
        if (
            [next_value % 100 < 25 for next_value in take(tickets(s, 0, 0x9216D5D98979FB1B), 2)]
            == [True, True]
            and next(tickets(s, 0, 0x2FFD72DBD01ADFB7)) % 2 == 1
        )
    )
    diamond = next(p for p in PLAN.guardians.profiles if p[0] == 264)
    b = game(
        seed=seed,
        guardian_profiles=ids([(*diamond[:2], 20, *diamond[3:])]),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        summon_profiles=None,
        phenomenon_profiles=None,
        fate_model_ids=None,
    )
    seed_hand(b, [112], owner=2)
    b.seed_players(ids([0]), ids([2]), ids([[1, 0, 0, 0]]), ids([0]))
    b.seed_guardians(ids([0, 0]), ids([1, 2]), ids([4, 9]))
    b.start_environments(ids([0]))
    step(b, [0])
    for _ in range(10):
        if b.episode_snapshot()[0, 3] != 4:
            break
        step(b, [0])
    else:
        raise AssertionError("nested Bow/guardian family exceeded bound")
    assert b.guardian_generated_snapshot()[0, :7].tolist() == [1, 1, 0, 0, 0, 0, 1]
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert b.ascension_count == 1 and b.guardian_statistics()[0, 9] == 1


def take(iterator, count):
    return [next(iterator) for _ in range(count)]


def test_unrevealed_generated_card_pool_is_not_a_policy_feature_and_terminal_views_are_empty():
    first, second = [game(players=2, pool=(row,), max_turns=1) for row in EARTH_DROP[:2]]
    for b in (first, second):
        start(b)
    for name in (
        "actor_hands",
        "choice_masks",
        "player_observations",
        "guardian_effect_observations",
        "attack_effect_observations",
    ):
        np.testing.assert_array_equal(getattr(first, name)(), getattr(second, name)())
    for b in (first, second):
        step(b, [0])
        step(b, [0])
        assert b.episode_snapshot()[0, 3] == 13
        assert not b.guardian_effect_observations().any()
        assert not b.attack_effect_observations().any()


def test_unconfigured_special_guardian_still_rejects_atomically_without_filtering_outcomes():
    b = game(pool=None, guardian_action_profiles=None)
    start(b, group=10)
    before = snapshot(b)
    with pytest.raises(ValueError, match="requires generated action profiles"):
        step(b, [0])
    same(before, snapshot(b))


@pytest.mark.parametrize(
    "change",
    [
        {"generated_profiles": ()},
        {"generated_fields": ()},
        {"generated_sampling": "uniform"},
        {"earth_pool_weight": 207},
        {"unsupported_special_model_ids": (286,)},
        {"joined_guardian_models": 43},
        {"promotion_eligible": True},
        {"official_fidelity_verified": True},
    ],
)
def test_generated_source_contract_cannot_be_relabelled(change):
    with pytest.raises(ValidationError):
        FullGameGuardianPlan.model_validate(PLAN.guardians.model_dump() | change)


@pytest.mark.parametrize(
    "pool",
    [
        (),
        ((8, 6, 1, 1),),
        ((9, 210, 4, 1),),
        ((10, 6, 1, 1),),
        ((9, 6, 2, 1),),
        ((9, 6, 1, 0),),
        ((9, 6, 1, 501),),
        ((9, 6, 1, 1), (9, 6, 1, 1)),
        ((9, 6, 1, 500), (9, 7, 1, 1)),
        ((9, 1, 1, 1),),
        ((9, 240, 1, 1),),
    ],
)
def test_raw_generated_profiles_reject_wrong_categories_duplicates_and_bounds(pool):
    with pytest.raises(ValueError, match=r"generated profile|generated pool"):
        game(pool=pool)


def test_factory_pins_pool_and_readonly_diagnostics_reset_without_enabling_training():
    c = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=1,
        capacity=18,
        player_count=2,
        seed=SEED,
    )
    b = c.batch
    start(b)
    step(b, [0])
    drain(b)
    old = b.guardian_generated_snapshot()
    counts = b.guardian_generated_model_counts()
    assert not old.flags.writeable and not counts.flags.writeable
    assert old[0, 1] == counts.sum() == 1
    assert c.metadata.guardian_generated_model_count_ids == tuple(range(3, 240))
    b.reset_environments(ids([0]))
    assert not b.guardian_generated_snapshot().any()
    assert not b.guardian_generated_model_counts().any()
    assert old[0, 1] == counts.sum() == 1
    assert not c.metadata.local_training_eligible and not c.metadata.promotion_eligible
