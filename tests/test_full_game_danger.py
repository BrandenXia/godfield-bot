"""Joined random targeting, actual passive ownership and atomic native replay."""

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
    DANGER_FIELDS,
    DANGER_SNAPSHOT_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_danger import FullGameDangerPlan, build_full_game_danger_plan

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
    profiles=PLAN.danger.profiles,
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
        danger_profiles=None if profiles is None else ids(profiles).reshape(-1, 4),
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def hand(batch, models, *, env=0, owner=0, displays=None):
    displays = [0] * len(models) if displays is None else displays
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + slot + 1, model, display, 0]
                for slot, (model, display) in enumerate(zip(models, displays, strict=True))
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=100, mp=20, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    episodes = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids([[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)])
    )


def cast(batch, *, env=0, target=1, additions=()):
    step(batch, [1], [env])
    for slot in additions:
        step(batch, [slot], [env])
    step(batch, [0], [env])
    assert batch.episode_snapshot()[env, 3] == 3
    step(batch, [19 + target], [env])


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
                "danger_observations",
                "danger_snapshot",
                "passive_observations",
                "revival_snapshot",
                "acquisition_snapshot",
                "cost_snapshot",
                "pending_observations",
                "attack_order",
                "chance_snapshot",
                "counter_snapshot",
            )
        ),
        tuple(
            getattr(batch, name)
            for name in (
                "attack_count",
                "resolved_attack_count",
                "danger_count",
                "automatic_danger_hp_damage",
                "consumed_count",
                "miracle_use_count",
                "action_count",
                "mp_spent",
                "hp_damage",
                "automatic_gift_count",
                "suppressed_gift_count",
                "revival_count",
                "counter_count",
            )
        ),
    )


def same(left, right):
    assert left[1] == right[1]
    for a, b in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(a, b)


def rank(seed, env, stream, bound, epoch=1):
    """Independent oracle for the pinned first local SplitMix ticket."""
    mask = 2**64 - 1
    word = seed ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
    word ^= (epoch * 0xBF58476D1CE4E5B9) & mask
    word ^= stream
    word = (word + 0x9E3779B97F4A7C15) & mask
    word = ((word ^ (word >> 30)) * 0xBF58476D1CE4E5B9) & mask
    word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
    word ^= word >> 31
    assert word >= ((-bound) & mask) % bound
    return word % bound


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("mask", [0, 1, 2, 4, 8, 15])
@pytest.mark.parametrize("seed", [67, 68, 999])
def test_any_living_target_including_source_ignore_fog_and_skip_self_response(players, mask, seed):
    batch = game(size=64, players=players, seed=seed)
    for env in range(64):
        hand(batch, [94], env=env)
        load(batch, env=env, mask=mask)
    batch.start_environments(ids(range(64)))
    step(batch, [1] * 64)
    assert np.all(batch.danger_observations() == [1, 30, 5])
    assert not batch.danger_snapshot().any() and batch.hp_damage == 0
    step(batch, [0] * 64)
    assert np.all(batch.episode_snapshot()[:, 3] == 3)
    step(batch, [20] * 64)
    targets = np.asarray([rank(seed, env, 0xA4093822299F31D0, players) for env in range(64)])
    assert set(targets) == set(range(players))
    self_hits = targets == 0
    episodes = batch.episode_snapshot()
    np.testing.assert_array_equal(episodes[:, 3], np.where(self_hits, 1, 4))
    stats = batch.danger_snapshot()
    np.testing.assert_array_equal(stats[:, 2], self_hits)
    np.testing.assert_array_equal(stats[:, 6], self_hits)
    np.testing.assert_array_equal(stats[:, 7], self_hits * 30)
    assert np.all(stats[:, 0:2] == 1) and not stats[:, 3:6].any()
    np.testing.assert_array_equal(batch.pending_observations()[~self_hits, 2], targets[~self_hits])
    assert batch.automatic_danger_hp_damage == int(self_hits.sum()) * 30
    remaining = np.flatnonzero(~self_hits)
    step(batch, [0] * len(remaining), remaining)
    assert batch.hp_damage == 64 * 30 and batch.danger_count == batch.resolved_attack_count == 64
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)
    assert not batch.diagnostic_players()[:, 1:, 5].any()
    assert batch.chance_count == batch.reflection_count == batch.counter_count == 0
    assert batch.consumed_count == 64 and not batch.danger_observations().any()


@pytest.mark.parametrize("target", [1, 2, 8])
def test_requested_target_has_no_influence_on_random_distribution(target):
    first, reference = game(size=64, players=9), game(size=64, players=9)
    for batch in (first, reference):
        for env in range(64):
            hand(batch, [94], env=env)
        batch.start_environments(ids(range(64)))
        step(batch, [1] * 64)
        step(batch, [0] * 64)
    step(first, [19 + target] * 64)
    step(reference, [20] * 64)
    for name in (
        "diagnostic_players",
        "diagnostic_inventory",
        "danger_snapshot",
        "pending_observations",
    ):
        np.testing.assert_array_equal(getattr(first, name)(), getattr(reference, name)())


@pytest.mark.parametrize(
    "holders,copies", [((0,), 1), ((1,), 1), ((2,), 2), ((0, 1), 1), ((0, 1), 3)]
)
def test_attraction_uniform_owners_not_copies_consumes_one_real_mortar_without_defense(
    holders, copies
):
    batch = game(size=64)
    for env in range(64):
        for owner in range(3):
            models = (
                ([94] if owner == 0 else [])
                + ([209] * (copies if owner == 0 else 1) if owner in holders else [])
                + [190, 189, 184]
            )
            hand(batch, models, env=env, owner=owner)
    batch.start_environments(ids(range(64)))
    step(batch, [1] * 64)
    step(batch, [0] * 64)
    step(batch, [20] * 64)
    targets = np.asarray(
        [
            holders[rank(67, e, 0x082EFA98EC4E6C89, len(holders))]
            if len(holders) > 1
            else holders[0]
            for e in range(64)
        ]
    )
    stats = batch.danger_snapshot()
    assert np.all(stats[:, 0] == 1) and not stats[:, 1].any()
    assert np.all(stats[:, 3] == 1) and np.all(stats[:, 4] == int(len(holders) > 1))
    np.testing.assert_array_equal(stats[:, 2], targets == 0)
    np.testing.assert_array_equal(stats[:, 5], targets == 0)
    assert np.all(stats[:, 6] == 1) and np.all(stats[:, 7] == 99)
    assert np.all(batch.episode_snapshot()[:, 3] == 1)
    for env, target in enumerate(targets):
        assert batch.diagnostic_players()[env, target, 0] == 1
        remaining = batch.diagnostic_inventory()[env, target]
        expected = (copies if target == 0 else 1) - 1
        assert np.count_nonzero(remaining[:, 1] == 209) == expected
        assert set(remaining[remaining[:, 0] > 0, 1]) >= {190, 189, 184}
    assert (
        batch.consumed_count == 128 and batch.hp_damage == batch.automatic_danger_hp_damage == 6336
    )
    assert batch.counter_count == batch.reflection_count == batch.defense_toggle_count == 0
    assert not batch.diagnostic_players()[:, 1:, 5].any()


@pytest.mark.parametrize(
    "hp,sun", [(1, False), (30, False), (99, False), (100, False), (1, True), (99, True)]
)
@pytest.mark.parametrize("holder", [0, 1])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_attracted_hp_edges_revive_real_owned_copy_before_endings_and_defer_receipts(
    hp, sun, holder, players
):
    batch = game(players=players, refill=True)
    hand(batch, [94, *([209] if holder == 0 else []), *([208] if sun and holder == 0 else [])])
    if holder:
        hand(batch, [209, *([208] if sun else [])], owner=holder)
    load(batch, owner=holder, hp=hp)
    batch.start_environments(ids([0]))
    cast(batch)
    lethal = hp <= 99
    revived = int(lethal and sun)
    expected = 10 if revived else max(0, hp - 99)
    assert batch.diagnostic_players()[0, holder, 0] == expected
    assert batch.revival_snapshot()[0, :3].tolist() == [revived, 10 * revived, revived]
    assert batch.hp_damage == min(hp, 99)
    assert batch.consumed_count == 2 + revived
    # Terminal games suppress all receipts; otherwise only living owners refill.
    gifts = 3 if revived else (2 if not lethal else int(players > 2 and holder != 0))
    assert batch.automatic_gift_count == gifts
    assert not batch.acquisition_snapshot()[0, :, 0].any()
    assert batch.acquisition_snapshot()[0, :, 1].sum() == gifts
    assert batch.suppressed_gift_count == 2 + revived - gifts
    if players == 2 and lethal and not sun:
        assert batch.episode_snapshot()[0, 5:7].tolist() == [1, 1 - holder]
    assert batch.diagnostic_players()[0, 0, 5] == 1
    assert not batch.diagnostic_players()[0, 1:, 5].any()


def test_attracted_fixed99_is_not_composed_attack_or_numeric_defense():
    batch = game()
    hand(batch, [94, 203, 231, 231])
    hand(batch, [209, 190, 113, 184], owner=1)
    batch.start_environments(ids([0]))
    cast(batch, additions=(2, 3, 4))
    assert batch.hp_damage == 99 and batch.diagnostic_players()[0, 1, 0] == 1
    assert batch.mp_spent == 12 and batch.diagnostic_players()[0, 0, 1] == 8
    assert batch.miracle_use_count == 2 and batch.consumed_count == 3
    assert batch.counter_count == batch.reflection_count == 0
    assert batch.diagnostic_inventory()[0, 0, :2, 1:4].tolist() == [[231, 0, 1], [231, 0, 1]]


@pytest.mark.parametrize(
    "actual,display,attracted", [(209, 208, True), (208, 209, False), (198, 209, False)]
)
def test_public_passive_disguise_and_actual_attraction_never_share_eligibility(
    actual, display, attracted
):
    batch = game()
    hand(batch, [94])
    hand(batch, [actual], owner=1, displays=[display])
    # Seat1's private passive display is not visible to actor0.
    batch.start_environments(ids([0]))
    assert not batch.passive_observations().any()
    cast(batch)
    assert batch.danger_snapshot()[0, 3] == int(attracted)
    if attracted:
        assert batch.diagnostic_players()[0, 1, 0] == 1
    else:
        assert np.any(batch.diagnostic_inventory()[0, 1, :, 1] == actual)


@pytest.mark.parametrize("actual,display,kind", [(209, 209, 2), (209, 208, 1), (208, 209, 2)])
def test_mortar_is_displayed_passive_but_never_a_manual_ready_use(actual, display, kind):
    batch = game()
    hand(batch, [actual], displays=[display])
    batch.start_environments(ids([0]))
    assert batch.passive_observations()[0, 0].tolist() == [kind, 99 if kind == 2 else 10]
    assert not batch.choice_masks()[0, 1]
    before = snapshot(batch)
    with pytest.raises(ValueError, match="unavailable"):
        step(batch, [1])
    same(snapshot(batch), before)


@pytest.mark.parametrize(
    "failure", ["hidden-cost", "unsupported", "decision", "duplicate", "dead-target"]
)
def test_late_cast_failure_rolls_back_attraction_inventory_payment_rng_revive_and_retry(failure):
    attempted, reference = game(size=2, refill=True), game(size=2, refill=True)
    for batch in (attempted, reference):
        hand(batch, [94, 209, 208], env=0)
        load(batch, env=0, hp=1)
        hand(batch, [94], env=1)
        if failure == "hidden-cost":
            hand(batch, [94, 231], env=1, displays=[0, 210])
            load(batch, env=1, mp=2)
        elif failure == "unsupported":
            hand(batch, [112], env=1, displays=[94])
        elif failure == "dead-target":
            load(batch, env=1, owner=1, hp=0)
        batch.start_environments(ids([0, 1]))
        step(batch, [1, 1])
        if failure == "hidden-cost":
            step(batch, [2], [1])
        step(batch, [0, 0])
    before = snapshot(attempted)
    episodes = attempted.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 20] for env in (0, 1)])
    if failure == "decision":
        commands[1, 2] += 1
    elif failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        attempted.step(commands)
    same(snapshot(attempted), before)
    for batch in (attempted, reference):
        step(batch, [20], [0])
    same(snapshot(attempted), snapshot(reference))
    assert attempted.revival_count == 1 and attempted.automatic_gift_count == 3


def test_dead_holder_excluded_and_dead_seat_has_no_target_ticket():
    batch = game(size=32)
    for env in range(32):
        hand(batch, [94], env=env)
        hand(batch, [209], env=env, owner=1)
        load(batch, env=env, owner=1, hp=0)
    batch.start_environments(ids(range(32)))
    step(batch, [1] * 32)
    step(batch, [0] * 32)
    step(batch, [21] * 32)
    targets = [0 if rank(67, e, 0xA4093822299F31D0, 2) == 0 else 2 for e in range(32)]
    assert not batch.danger_snapshot()[:, 3].any()
    for env, target in enumerate(targets):
        assert batch.diagnostic_players()[env, 1, 0] == 0
        assert batch.diagnostic_inventory()[env, 1, 0, 1] == 209
        if target:
            assert batch.pending_observations()[env, 2] == target


@pytest.mark.parametrize("actual,display", [(94, 35), (35, 94), (112, 94)])
def test_public_danger_role_does_not_inspect_hidden_weapon(actual, display):
    hidden, reference = game(), game()
    hand(hidden, [actual], displays=[display])
    hand(reference, [display], displays=[display])
    for batch in (hidden, reference):
        batch.start_environments(ids([0]))
        step(batch, [1])
    for name in (
        "actor_hands",
        "player_observations",
        "choice_masks",
        "danger_observations",
        "attack_selection_observations",
    ):
        np.testing.assert_array_equal(getattr(hidden, name)(), getattr(reference, name)())


def test_cancellation_does_not_sample_and_reset_reseeds_diagnostics_without_resetting_lifetime():
    batch = game(size=32, turns=1)
    for env in range(32):
        hand(batch, [94], env=env)
    batch.start_environments(ids(range(32)))
    before = batch.danger_snapshot()
    role = batch.danger_observations()
    assert before.shape == (32, 8) and not before.flags.writeable and not role.flags.writeable
    step(batch, [1] * 32)
    step(batch, [1] * 32)
    assert not batch.danger_snapshot().any() and batch.danger_count == 0
    step(batch, [1] * 32)
    step(batch, [0] * 32)
    step(batch, [20] * 32)
    remaining = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4)
    step(batch, [0] * len(remaining), remaining)
    assert not before.any() and not role.any()
    damage = batch.automatic_danger_hp_damage
    batch.reset_environments(ids(range(32)))
    assert not batch.danger_snapshot().any() and not batch.danger_observations().any()
    assert batch.danger_count == 32 and batch.automatic_danger_hp_damage == damage


@pytest.mark.parametrize(
    "profile",
    [
        (94, 0, 30, 5),
        (94, 3, 30, 5),
        (94, 1, 0, 5),
        (94, 1, 30, 7),
        (209, 2, 0, 0),
        (209, 2, 101, 0),
        (209, 2, 99, 5),
        (209, 1, 99, 0),
        (94, 2, 99, 0),
        (35, 1, 30, 5),
        (208, 2, 99, 0),
    ],
)
def test_invalid_raw_roles_and_collisions_fail_before_construction(profile):
    with pytest.raises(ValueError, match="danger profile"):
        game(profiles=[profile])


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((94, 1, 31, 5), (209, 2, 99, 0))},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profile_fields": ("hidden-holder",)},
        {"effect_codes": ("chance-miracle",)},
        {"official_multiplayer_and_attraction_verified": True},
        {"promotion_eligible": True},
        {"mortar_resolution": "ATK99-with-defense"},
    ],
)
def test_source_plan_cannot_claim_unverified_attraction_or_probability(change):
    with pytest.raises(ValidationError):
        FullGameDangerPlan.model_validate(PLAN.danger.model_dump() | change)


@pytest.mark.parametrize("model", [94, 209])
@pytest.mark.parametrize(
    "change", [{"ability": "boostHP"}, {"giftRate": 3}, {"price": 9}, {"name": "Changed card"}]
)
def test_source_rehash_drift_rejected_by_exact_rows(model, change):
    catalog = read_api_catalog_snapshot(CATALOG)
    items = tuple(
        ApiCatalogItem(model_id=i.model_id, raw=dict(i.raw) | change) if i.model_id == model else i
        for i in catalog.items
    )
    altered = ApiCatalogSnapshot.model_validate(
        catalog.model_dump()
        | {
            "items": [i.model_dump() for i in items],
            "content_sha256": api_catalog_digest(items),
        }
    )
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_danger_plan(altered, BibleSnapshot.model_validate_json(BIBLE.read_text()))


def test_factory_metadata_new_danger_contract_does_not_claim_complete_readiness():
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    assert configured.metadata.kernel_schema_version == 33
    assert configured.metadata.danger_observation_fields == DANGER_FIELDS
    assert configured.metadata.danger_snapshot_fields == DANGER_SNAPSHOT_FIELDS
    assert PLAN.integrated_artifact_effect_count == 237
    assert (
        not configured.metadata.full_game_training_ready
        and not configured.metadata.promotion_eligible
    )
    assert (
        FullGameMetadata.model_validate_json(configured.metadata.model_dump_json())
        == configured.metadata
    )


def enemy_seed():
    return next(seed for seed in range(100) if rank(seed, 0, 0xA4093822299F31D0, 3) == 1)


@pytest.mark.parametrize("response", [(), (189, 135), (190,)])
def test_normal_target_keeps_light_compatibility_filter_or_reflection_and_one_sample(response):
    batch = game(seed=enemy_seed(), refill=True)
    hand(batch, [94, 190])
    hand(batch, list(response), owner=1)
    batch.start_environments(ids([0]))
    cast(batch)
    assert batch.pending_observations()[0, 2:6].tolist() == [1, 30, 5, 0]
    assert batch.danger_observations()[0].tolist() == [1, 30, 5]
    drawn = batch.danger_snapshot().copy()
    for slot in range(1, len(response) + 1):
        step(batch, [slot])
    step(batch, [0])
    if response == (190,):
        # A later redirect to the source is a fresh ordinary defense, not the
        # initial Pestle self-target's automatic hit, and does not re-sample.
        assert batch.episode_snapshot()[0, 2:4].tolist() == [0, 4]
        assert batch.automatic_gift_count == 0
        step(batch, [1])  # Remaining source Super Mirror.
        step(batch, [0])
        assert batch.pending_observations()[0, 2] == 1
        step(batch, [0])
        assert batch.reflection_count == 2 and batch.automatic_gift_count == 3
    else:
        assert batch.automatic_gift_count == 1 + len(response)
    assert batch.hp_damage == (25 if response == (189, 135) else 30)
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.danger_count == batch.resolved_attack_count == 1
    np.testing.assert_array_equal(batch.danger_snapshot(), drawn)
    assert not batch.danger_observations().any()


def test_filter_then_ring_opens_counter_without_pestle_sampling_or_early_gifts():
    batch = game(seed=enemy_seed(), refill=True)
    hand(batch, [94])
    hand(batch, [189, 135, 184], owner=1)
    batch.start_environments(ids([0]))
    cast(batch)
    drawn = batch.danger_snapshot().copy()
    assert not batch.choice_masks()[0, 2:4].any()  # Light excludes numeric DEF.
    for choice in (1, 2, 3, 0):
        step(batch, [choice])
    assert batch.counter_observations()[0, :5].tolist() == [1, 1, 1, 0, 25]
    assert batch.pending_observations()[0, 3:6].tolist() == [50, 4, 2]
    # The active ring counter is not the already-resolved Pestle payload.
    assert not batch.danger_observations().any()
    assert batch.automatic_gift_count == 0
    assert not batch.diagnostic_players()[0, :, 5].any()
    step(batch, [0])
    assert batch.hp_damage == 75 and batch.counter_count == 1
    assert batch.automatic_gift_count == batch.consumed_count == 4
    np.testing.assert_array_equal(batch.danger_snapshot(), drawn)
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("waive", [False, True])
@pytest.mark.parametrize("self_target", [False, True])
def test_general_ordered_boosts_and_adjacent_waivers_apply_to_random_pestle(waive, self_target):
    seed = next(s for s in range(100) if rank(s, 0, 0xA4093822299F31D0, 3) == int(not self_target))
    batch = game(seed=seed)
    hand(batch, [94, 203, 231, *([204] if waive else [])])
    batch.start_environments(ids([0]))
    cast(batch, additions=(2, 3, *([4] if waive else [])))
    if not self_target:
        assert batch.pending_observations()[0, 3] == 80
        step(batch, [0])
    assert batch.hp_damage == 80 and batch.mp_spent == (0 if waive else 6)
    assert batch.danger_snapshot()[0, 6:8].tolist() == ([1, 80] if self_target else [0, 0])
    assert batch.miracle_use_count == 1 and batch.consumed_count == 2 + int(waive)
    assert batch.cost_snapshot()[0, :4].tolist() == ([1, 6, 0, 1] if waive else [0] * 4)


@pytest.mark.parametrize("max_decisions", [2, 3])
def test_limits_do_not_resample_or_add_ticks_or_gifts_to_unresolved_cast(max_decisions):
    batch = game(seed=enemy_seed(), decisions=max_decisions, refill=True)
    hand(batch, [94])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [0])
    if max_decisions == 3:
        step(batch, [20])
    assert batch.episode_snapshot()[0, 3] == 13
    assert batch.danger_count == int(max_decisions == 3)
    assert batch.consumed_count == int(max_decisions == 3)
    assert batch.suppressed_gift_count == int(max_decisions == 3)
    assert batch.resolved_attack_count == batch.hp_damage == batch.automatic_gift_count == 0
    assert not batch.diagnostic_players()[0, :, 5].any()
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [0])
    same(snapshot(batch), before)


def test_real_self_ko_ending_takes_precedence_over_cast_decision_limit():
    seed = next(s for s in range(100) if rank(s, 0, 0xA4093822299F31D0, 2) == 0)
    batch = game(seed=seed, players=2, decisions=3, refill=True)
    hand(batch, [94])
    load(batch, hp=1)
    batch.start_environments(ids([0]))
    cast(batch)
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]
    assert batch.hp_damage == batch.automatic_danger_hp_damage == 1
    assert batch.resolved_attack_count == 1
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 1


def test_atomic_random_cast_failure_retries_same_target_ticket():
    attempted, reference = game(size=2, seed=enemy_seed()), game(size=2, seed=enemy_seed())
    for batch in (attempted, reference):
        hand(batch, [94], env=0)
        hand(batch, [112], env=1, displays=[94])
        batch.start_environments(ids([0, 1]))
        step(batch, [1, 1])
        step(batch, [0, 0])
    before = snapshot(attempted)
    with pytest.raises(ValueError, match="not implemented"):
        step(attempted, [20, 20])
    same(snapshot(attempted), before)
    for batch in (attempted, reference):
        step(batch, [20], [0])
    same(snapshot(attempted), snapshot(reference))


def test_optional_profiles_leave_random_weapon_and_passive_unsupported():
    batch = game(profiles=None)
    hand(batch, [94, 209])
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 1:3].any()
    assert not batch.danger_observations().any() and not batch.passive_observations().any()
