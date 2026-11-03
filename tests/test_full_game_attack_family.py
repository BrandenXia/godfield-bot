"""Shared original/counter/death queue, deterministic tickets and atomic rollback."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import (
    ApiCatalogItem,
    ApiCatalogSnapshot,
    api_catalog_digest,
    read_api_catalog_snapshot,
)
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    ATTACK_FAMILY_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_attack_family import (
    FullGameAttackFamilyPlan,
    build_full_game_attack_family_plan,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

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
    seed=67,
    refill=False,
    turns=100,
    decisions=1000,
    profiles=PLAN.attack_family.profiles,
    missing_armor=None,
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
        armor_profiles=ids(tuple(r for r in PLAN.combat.armor_profiles if r[0] != missing_armor)),
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
        ascension_profiles=None if profiles is None else ids(profiles).reshape(-1, 6),
        gift_profiles=ids([[191, 1]]),
        refill_on_use=refill,
    )


def hand(batch, models, *, env=0, owner=0, displays=None):
    displays = [0] * len(models) if displays is None else displays
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + i + 1, m, f, 0]
                for i, (m, f) in enumerate(zip(models, displays, strict=True))
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=1, hp=100, mp=20, cp=3, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids(
            [[env, *rows[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )
    conserved(batch)


def conserved(batch):
    stats = batch.attack_family_snapshot()
    np.testing.assert_array_equal(
        stats[:, 0], stats[:, 2] + stats[:, 3] + stats[:, 13] + (stats[:, 14] > 0)
    )
    np.testing.assert_array_equal(stats[:, 1], stats[:, 2] + (stats[:, 14] > 0))
    assert np.all(stats[:, 8] >= stats[:, 9] + stats[:, 10] + stats[:, 11])
    complete = (stats[:, 13] == 0) & (stats[:, 14] == 0)
    np.testing.assert_array_equal(stats[complete, 8], stats[complete, 9:12].sum(axis=1))


def cast(batch, *, size=1, target=1):
    batch.start_environments(ids(range(size)))
    for choice in (1, 0, 19 + target):
        step(batch, [choice] * size)


def drain(batch, limit=100):
    for _ in range(limit):
        envs = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4)
        if not len(envs):
            return
        assert batch.choice_masks()[envs, 0].all()
        step(batch, [0] * len(envs), envs)
    raise AssertionError("attack-family drain exceeded its scripted response bound")


def tickets(seed, env, stream, epoch=1):
    mask = 2**64 - 1
    state = (
        seed
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ stream
    )
    while True:
        state = (state + 0x9E3779B97F4A7C15) & mask
        value = state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        yield value ^ (value >> 31)


def snapshot(batch):
    return (
        tuple(
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
                "attack_family_snapshot",
                "acquisition_snapshot",
                "counter_snapshot",
                "revival_snapshot",
                "dream_defense_snapshot",
                "complex_weapon_snapshot",
            )
        ),
        tuple(
            getattr(batch, name)
            for name in (
                "action_count",
                "hp_damage",
                "consumed_count",
                "automatic_gift_count",
                "suppressed_gift_count",
                "ascension_count",
                "ascension_hp_damage",
                "counter_count",
                "resolved_counter_count",
                "revival_count",
                "attack_count",
                "resolved_attack_count",
                "redraw_count",
            )
        ),
    )


def same(left, right):
    assert left[1] == right[1]
    for a, b in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed", [67, 68, 999])
@pytest.mark.parametrize("mask", range(16))
def test_post_death_owned_bow_independent_recipient_oracle_and_one_original_tick(
    players, seed, mask
):
    batch = game(size=16, players=players, seed=seed)
    for env in range(16):
        hand(batch, [57], env=env)
        hand(batch, [112, 35], env=env, owner=1, displays=[35, 0])
        for owner in range(players):
            load(
                batch,
                env=env,
                owner=owner,
                hp=1 if owner == 1 else 100,
                mask=mask & ~1 if owner == 0 else mask,
            )
    cast(batch, size=16)
    step(batch, [0] * 16)  # Original attack kills seat1, but ending/tick must wait.
    hits = []
    for env in range(16):
        stream = tickets(seed, env, 0xC0AC29B7C97C50DD)
        expected = []
        for owner in range(players):
            if owner == 1:
                expected.append(0)
                continue
            hit = bool(mask & 8) or next(stream) % 100 < 75
            expected.append(int(hit))
        hits.append(expected)
    pending = batch.episode_snapshot()[:, 3] == 4
    assert np.all(batch.diagnostic_players()[pending, :, 5] == 0)
    drain(batch)
    players_state = batch.diagnostic_players()
    expected_hp = 100 - 30 * np.asarray(hits)
    expected_hp[:, 1] = 0
    np.testing.assert_array_equal(players_state[:, :, 0], expected_hp)
    np.testing.assert_array_equal(
        players_state[:, :, 5], np.tile([1] + [0] * (players - 1), (16, 1))
    )
    stats = batch.attack_family_snapshot()
    np.testing.assert_array_equal(stats[:, 7], np.ones(16, dtype=np.int64))
    np.testing.assert_array_equal(stats[:, 8], np.full(16, players - 1))
    np.testing.assert_array_equal(stats[:, 9], np.asarray(hits).sum(axis=1))
    np.testing.assert_array_equal(stats[:, 10], players - 1 - np.asarray(hits).sum(axis=1))
    assert not stats[:, 11].any() and not stats[:, 13:].any()
    assert batch.ascension_count == 16 and batch.ascension_hp_damage == 30 * sum(map(sum, hits))
    assert batch.hp_damage == 16 + batch.ascension_hp_damage and batch.consumed_count == 32
    assert batch.attack_count == batch.resolved_attack_count == 16 and batch.counter_count == 0
    assert np.all(batch.episode_snapshot()[:, 3] == (12 if players == 2 else 1))


@pytest.mark.parametrize("count", [1, 2, 3, 18])
def test_actual_held_copies_consume_once_even_without_any_living_recipient(count):
    batch = game(players=2)
    hand(batch, [57, 112])
    hand(batch, [112] * count, owner=1)
    load(batch, owner=0, hp=1, mask=8)
    load(batch, hp=1)
    cast(batch)
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 4  # Last survivor must defend.
    assert batch.diagnostic_players()[0, :, 5].sum() == 0
    step(batch, [0])
    assert batch.episode_snapshot()[0, [3, 5, 6]].tolist() == [12, 2, -1]
    stats = batch.attack_family_snapshot()[0]
    assert stats[6:13].tolist() == [2, count + 1, count, 1, 0, count - 1, 1]
    assert batch.ascension_count == count + 1 and batch.consumed_count == count + 2
    assert batch.ascension_hp_damage == 1 and batch.hp_damage == 2
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert not stats[13:].any()


def test_nested_death_shots_precede_remaining_recipient_siblings():
    batch = game(players=3, refill=True)
    hand(batch, [57, 112])
    hand(batch, [112], owner=1)
    load(batch, owner=0, hp=1, mask=8)
    load(batch, hp=1)
    load(batch, owner=2, mask=8)
    cast(batch)
    step(batch, [0])
    assert batch.pending_observations()[0, :3].tolist() == [1, 0, 0]
    assert batch.special_defense_observations()[0, 1] == 1
    step(batch, [0])
    # Seat0's nested Bow precedes seat1's remaining shot against seat2.
    assert batch.pending_observations()[0, 1:3].tolist() == [0, 2]
    assert batch.automatic_gift_count == 0 and batch.diagnostic_players()[0, :, 5].sum() == 0
    step(batch, [0])
    assert batch.pending_observations()[0, 1:3].tolist() == [0, 2]
    assert batch.special_defense_observations()[0, 1] == 1
    step(batch, [0])
    assert batch.episode_snapshot()[0, [3, 5, 6]].tolist() == [12, 1, 2]
    assert batch.diagnostic_players()[0, :, 0].tolist() == [0, 0, 40]
    assert batch.ascension_hp_damage == 61 and batch.hp_damage == 62
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 3
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("source,owner", [(0, 1), (0, 0)])
def test_sun_priority_prevents_final_death_trigger_and_preserves_held_bow(source, owner):
    batch = game(players=2)
    if owner == 1:
        hand(batch, [57])
        hand(batch, [112, 208], owner=1)
        load(batch, hp=1)
        cast(batch)
        step(batch, [0])
    else:
        hand(batch, [112, 208])
        load(batch, owner=0, hp=1, illness=1)
        batch.start_environments(ids([0]))
        step(batch, [0])
    assert batch.revival_count == 1 and batch.ascension_count == 0
    assert batch.attack_family_snapshot()[0, 6:13].sum() == 0
    held = batch.diagnostic_inventory()[0, owner]
    assert held[held[:, 0] > 0][:, 1].tolist() == [112]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]


@pytest.mark.parametrize("actual,display,expected", [(112, 35, 1), (35, 112, 0)])
def test_dying_bow_ownership_uses_actual_identity_not_display(actual, display, expected):
    batch = game(players=2)
    hand(batch, [57])
    hand(batch, [actual], owner=1, displays=[display])
    load(batch, hp=1)
    load(batch, owner=0, mask=8)
    cast(batch)
    step(batch, [0])
    drain(batch)
    assert batch.ascension_count == expected
    assert batch.diagnostic_players()[0, 0, 0] == 100 - 30 * expected


@pytest.mark.parametrize("players", [2, 3, 9])
def test_deaths_seeded_in_setup_never_generate_bows_or_resurrect(players):
    batch = game(players=players)
    hand(batch, [112], owner=1)
    load(batch, hp=0)
    batch.start_environments(ids([0]))
    assert batch.ascension_count == 0 and not batch.attack_family_snapshot().any()
    if players > 2:
        step(batch, [0])
        assert batch.diagnostic_players()[0, 1, 0] == 0


@pytest.mark.parametrize("players", [2, 3])
def test_periodic_death_drains_after_single_tick_before_turn_limit_and_ending(players):
    batch = game(players=players, turns=1, refill=True)
    hand(batch, [112])
    load(batch, owner=0, hp=1, illness=1)
    for owner in range(1, players):
        load(batch, owner=owner, mask=8)
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 4
    assert batch.attack_family_snapshot()[0, 14:16].tolist() == [3, 1]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)
    assert batch.automatic_gift_count == batch.suppressed_gift_count == 0
    drain(batch)
    assert batch.episode_snapshot()[0, 3] == (12 if players == 2 else 13)
    assert batch.episode_snapshot()[0, 5] == (1 if players == 2 else 3)
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)
    assert batch.suppressed_gift_count == 1 and batch.resolved_attack_count == 0


def test_decision_limit_during_post_tick_response_is_not_mislabeled_turn_limit():
    batch = game(players=2, turns=1, decisions=2)
    hand(batch, [112])
    hand(batch, [190], owner=1)
    load(batch, owner=0, hp=1, illness=1)
    load(batch, mask=8)
    batch.start_environments(ids([0]))
    step(batch, [0])
    step(batch, [1])
    assert batch.episode_snapshot()[0, [3, 5]].tolist() == [13, 4]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert batch.attack_family_snapshot()[0, 14] == 3


@pytest.mark.parametrize("defense", [233, 190, 189, 187, 184])
def test_last_survivor_can_block_reflect_filter_or_counter_without_dead_actor_hang(defense):
    batch = game(players=2, refill=True)
    filtered = defense in (233, 187, 184)
    hand(batch, [57, *([189] if filtered else []), defense])
    hand(batch, [112], owner=1)
    load(batch, hp=1)
    load(batch, owner=0, mask=8)
    cast(batch)
    step(batch, [0])
    assert batch.choice_masks()[0, 1]
    step(batch, [1])
    if filtered:
        step(batch, [2])
    step(batch, [0])
    drain(batch)
    assert batch.episode_snapshot()[0, 3] == 12
    assert batch.diagnostic_players()[0, 1, 0] == 0
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert batch.ascension_count == 1 and batch.resolved_attack_count == 1
    assert not batch.attack_family_snapshot()[0, 13:].any()
    assert batch.ascension_hp_damage == (0 if defense in (233, 190) else 30)
    assert batch.resolved_counter_count == int(defense == 187)
    assert batch.counter_snapshot()[0, 4] == int(defense == 184)


def test_repeated_primary_strike_is_suppressed_only_after_nested_death_family():
    batch = game(players=3)
    hand(batch, [14])
    hand(batch, [112], owner=1)
    load(batch, hp=1)
    load(batch, owner=0, mask=8)
    load(batch, owner=2, mask=8)
    cast(batch)
    step(batch, [0])
    assert batch.resolved_attack_count == 0 and batch.diagnostic_players()[0, :, 5].sum() == 0
    drain(batch)
    assert batch.resolved_attack_count == 1 and batch.ascension_count == 1
    assert batch.complex_weapon_snapshot()[0, 5:8].tolist() == [1, 1, 1]
    assert batch.diagnostic_players()[0, :, 0].tolist() == [70, 0, 70]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("failure", ["stale", "duplicate", "late-hidden-defense"])
def test_late_batch_failure_restores_queue_tickets_death_consumption_and_retry(failure):
    options = {"missing_armor": 113} if failure == "late-hidden-defense" else {}
    attempted, reference = (
        game(size=2, refill=True, **options),
        game(size=2, refill=True, **options),
    )
    for batch in (attempted, reference):
        for env in range(2):
            hand(batch, [57, 189, 178], env=env)
            hand(batch, [112], owner=1, env=env)
            load(batch, env=env, hp=1)
            load(batch, env=env, owner=0, mask=8)
            if failure == "late-hidden-defense" and env == 1:
                hand(batch, [57, 189, 113], env=env, displays=[0, 0, 178])
        cast(batch, size=2)
        step(batch, [0, 0])
        step(batch, [1, 1])
        step(batch, [2, 2])
    before = snapshot(attempted)
    rows = attempted.episode_snapshot()
    commands = ids([[env, *rows[env, :4], 0] for env in range(2)])
    if failure == "stale":
        commands[1, 2] += 1
    if failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        attempted.step(commands)
    same(snapshot(attempted), before)
    step(attempted, [0], [0])
    step(reference, [0], [0])
    same(snapshot(attempted), snapshot(reference))


def test_owned_snapshot_reset_clears_queue_and_epoch_rng_not_lifetime_counters():
    batch = game(players=2, turns=1)
    hand(batch, [112])
    load(batch, owner=0, hp=1, illness=1)
    load(batch, mask=8)
    batch.start_environments(ids([0]))
    old = batch.attack_family_snapshot()
    assert old.shape == (1, 16) and not old.flags.writeable
    step(batch, [0])
    drain(batch)
    assert not old.any() and batch.ascension_count == 1 and batch.ascension_hp_damage == 30
    batch.reset_environments(ids([0]))
    assert not batch.attack_family_snapshot().any()
    assert batch.ascension_count == 1 and batch.ascension_hp_damage == 30


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(112, 0, 25, 30, 75, 5)],
        [(112, 1, 0, 30, 75, 5)],
        [(112, 1, 100, 30, 75, 5)],
        [(112, 1, 25, 0, 75, 5)],
        [(112, 1, 25, 65536, 75, 5)],
        [(112, 1, 25, 30, 0, 5)],
        [(112, 1, 25, 30, 100, 5)],
        [(112, 1, 25, 30, 75, 7)],
        [(113, 1, 25, 30, 75, 5)],
        [(35, 1, 25, 30, 75, 5)],
        [(112, 1, 25, 30, 75, 5)] * 2,
    ],
)
def test_raw_profiles_reject_bad_bounds_roles_categories_duplicates(profiles):
    with pytest.raises(ValueError):
        game(profiles=profiles)


def test_optional_omission_preserves_unsupported_bow_without_death_effect():
    batch = game(players=2, profiles=None)
    hand(batch, [112])
    hand(batch, [112], owner=1)
    load(batch, owner=0, hp=1, illness=1)
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 1]
    step(batch, [0])
    assert batch.ascension_count == 0 and batch.episode_snapshot()[0, 3] == 12


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((112, 1, 25, 31, 75, 5),)},
        {"profile_fields": ("private-ticket",)},
        {"family_kinds": ("dead-source-everywhere",)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"promotion_eligible": True},
        {"official_multiplayer_and_compound_timing_verified": True},
        {"official_fidelity_verified": True},
        {"death_trigger": "low-hp"},
        {"recipients": "learner-selected"},
    ],
)
def test_source_contract_and_gates_cannot_be_relabelled(change):
    with pytest.raises(ValidationError):
        FullGameAttackFamilyPlan.model_validate(PLAN.attack_family.model_dump() | change)


@pytest.mark.parametrize(
    "change", [{"atk": 2}, {"hitRate": 30}, {"abilityValue": 31}, {"price": 11}, {"giftRate": 2}]
)
def test_rehashed_source_drift_rejected(change):
    catalog = read_api_catalog_snapshot(CATALOG)
    items = tuple(
        ApiCatalogItem(model_id=i.model_id, raw=dict(i.raw) | change) if i.model_id == 112 else i
        for i in catalog.items
    )
    altered = ApiCatalogSnapshot.model_validate(
        catalog.model_dump()
        | {"items": [i.model_dump() for i in items], "content_sha256": api_catalog_digest(items)}
    )
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_attack_family_plan(
            altered, BibleSnapshot.model_validate_json(BIBLE.read_text())
        )


def test_factory_metadata_exports_queue_version_without_declaring_full_game_ready():
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    assert native.FULL_GAME_ATTACK_FAMILY_SCHEMA_VERSION == 8
    assert configured.metadata.kernel_schema_version == 33
    assert configured.metadata.attack_family_snapshot_fields == ATTACK_FAMILY_FIELDS
    assert PLAN.integrated_artifact_effect_count == 237
    assert (
        not configured.metadata.full_game_training_ready
        and not configured.metadata.promotion_eligible
    )
    assert (
        FullGameMetadata.model_validate_json(configured.metadata.model_dump_json())
        == configured.metadata
    )


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed", [67, 68, 999])
@pytest.mark.parametrize("mask", [0, 8, 15])
def test_manual_bow_base_chance_uses_existing_provisional_target_first_stream(players, seed, mask):
    batch = game(size=32, players=players, seed=seed)
    targets, hits = [], []
    for env in range(32):
        hand(batch, [112, 35], env=env)
        for owner in range(1, players):
            load(batch, env=env, owner=owner, mask=mask)
        target = 1 + next(tickets(seed, env, 0xC6BC279692B5C323)) % (players - 1)
        targets.append(target)
        hits.append(bool(mask & 8) or next(tickets(seed, env, 0xE19B01AA9D42C633)) % 100 < 25)
    batch.start_environments(ids(range(32)))
    assert np.all(batch.passive_observations()[:, 0] == [3, 30])
    step(batch, [1] * 32)
    assert not batch.choice_masks()[:, 2].any()  # No ATK additions to percentage weapons.
    before = snapshot(batch)
    assert batch.ascension_count == 0 and batch.consumed_count == 0
    assert not batch.attack_family_snapshot().any()
    step(batch, [0] * 32)
    pending = np.flatnonzero(hits)
    np.testing.assert_array_equal(
        batch.pending_observations()[pending, 2], np.asarray(targets)[pending]
    )
    drain(batch)
    assert batch.chance_count == batch.resolved_attack_count == batch.attack_count == 32
    assert batch.chance_hit_count == sum(hits) and batch.chance_miss_count == 32 - sum(hits)
    assert batch.hp_damage == sum(hits) and batch.ascension_count == 0
    assert batch.consumed_count == 32 and batch.mp_spent == 0
    assert before[1][2] == 0
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)


@pytest.mark.parametrize("cause", ["infliction", "payment", "recoil", "worsening", "utility"])
def test_all_additional_hp_zero_paths_share_owned_death_hook(cause):
    seed = 67
    if cause == "worsening":
        seed = next(s for s in range(1000) if next(tickets(s, 0, 0)) % 100 < 5)
    elif cause == "utility":
        seed = next(s for s in range(1000) if next(tickets(s, 0, 0x13198A2E03707344)) % 2 == 1)
    batch = game(players=2, seed=seed)
    dying = 1 if cause == "infliction" else 0
    if cause == "infliction":
        hand(batch, [219])
        hand(batch, [112], owner=1)
        load(batch, hp=9, illness=4)
        load(batch, owner=0, mask=8)
        cast(batch)
        step(batch, [0])
    elif cause == "payment":
        hand(batch, [35, 112])
        hand(batch, [188], owner=1)
        load(batch, owner=0, hp=1, mp=0, cp=0)
        load(batch, mask=8)
        cast(batch)
        step(batch, [1])
        step(batch, [0])
        step(batch, [0])
        assert batch.counter_snapshot()[0, 8] == 1
    elif cause == "recoil":
        hand(batch, [53, 112])
        load(batch, owner=0, hp=1)
        load(batch, mask=8)
        cast(batch)
        step(batch, [0])
        assert batch.recoil_hp_damage == 1
    elif cause == "worsening":
        hand(batch, [112])
        load(batch, owner=0, illness=4)
        load(batch, mask=8)
        batch.start_environments(ids([0]))
        step(batch, [0])
    else:
        hand(batch, [202, 112])
        load(batch, owner=0, hp=1)
        load(batch, mask=8)
        batch.start_environments(ids([0]))
        step(batch, [1])
        step(batch, [0])
        assert batch.utility_hp_damage == 1
    assert batch.episode_snapshot()[0, 3] == 4
    assert batch.diagnostic_players()[0, dying, 0] == 0 and batch.ascension_count == 1
    drain(batch)
    assert batch.episode_snapshot()[0, 3] == 12
    assert batch.ascension_hp_damage == 30 and batch.ascension_count == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]


@pytest.mark.parametrize("failure", ["stale", "duplicate", "unsupported-defense"])
def test_rejected_death_creating_batch_preserves_bows_rng_and_family_for_exact_retry(failure):
    options = {"missing_armor": 113} if failure == "unsupported-defense" else {}
    attempted, reference = game(size=2, **options), game(size=2, **options)
    for batch in (attempted, reference):
        for env in range(2):
            hand(batch, [57], env=env)
            actual = 113 if env == 1 and failure == "unsupported-defense" else 178
            hand(batch, [actual, 112], env=env, owner=1, displays=[178, 35])
            load(batch, env=env, hp=1)
        cast(batch, size=2)
        step(batch, [1, 1])
    before = snapshot(attempted)
    episodes = attempted.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in range(2)])
    if failure == "stale":
        commands[1, 2] += 1
    elif failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        attempted.step(commands)
    same(snapshot(attempted), before)
    assert attempted.ascension_count == 0
    step(attempted, [0], [0])
    step(reference, [0], [0])
    same(snapshot(attempted), snapshot(reference))


@pytest.mark.parametrize("failure", ["stale", "duplicate"])
def test_rejected_periodic_death_batch_cannot_partially_tick_or_consume_bow(failure):
    attempted, reference = game(size=2), game(size=2)
    for batch in (attempted, reference):
        for env in range(2):
            hand(batch, [112], env=env)
            load(batch, env=env, owner=0, hp=1, illness=1)
        batch.start_environments(ids([0, 1]))
    before = snapshot(attempted)
    episodes = attempted.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in range(2)])
    if failure == "stale":
        commands[1, 2] += 1
    else:
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        attempted.step(commands)
    same(snapshot(attempted), before)
    step(attempted, [0], [0])
    step(reference, [0], [0])
    same(snapshot(attempted), snapshot(reference))
    assert attempted.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_native_queue_schema_drift_blocks_factory(monkeypatch):
    monkeypatch.setattr(native, "FULL_GAME_ATTACK_FAMILY_SCHEMA_VERSION", 9)
    with pytest.raises(ProvisionalRuleUnavailableError, match="contract differs"):
        create_development_full_game_batch(
            resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
        )


@pytest.mark.parametrize("field", ["attack_family_snapshot_fields", "passive_effect_codes"])
def test_metadata_rejects_private_feature_layout_relabeling(field):
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(
            configured.metadata.model_dump() | {field: ("future-ticket",)}
        )
