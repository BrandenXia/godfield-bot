"""Joined Hat redraw, native randomness, hidden-safe defense and rollback."""

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
    DREAM_DEFENSE_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_dream_defense import (
    FullGameDreamDefensePlan,
    build_full_game_dream_defense_plan,
)

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
    profiles=PLAN.dream_defense.profiles,
    weights=PLAN.gifts.model_weights,
    element=None,
    missing_armor=None,
):
    attacks = PLAN.combat.attack_profiles
    if element is not None:
        # Explicit arithmetic fixture, not a source-verified new weapon.
        attacks = (*(r for r in attacks if r[0] != 57), (57, 30, element, 0, 0))
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
        attack_profiles=ids(attacks),
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
        dream_defense_profiles=None if profiles is None else ids(profiles).reshape(-1, 4),
        gift_profiles=None if weights is None else ids(weights).reshape(-1, 2),
        refill_on_use=refill,
    )


def hand(batch, models, *, env=0, owner=0, displays=None, used=None):
    displays = [0] * len(models) if displays is None else displays
    used = [0] * len(models) if used is None else used
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + slot + 1, model, display, flag]
                for slot, (model, display, flag) in enumerate(
                    zip(models, displays, used, strict=True)
                )
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=1, hp=100, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, 20, 3, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    episodes = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def begin(batch, *, size=1):
    batch.start_environments(ids(range(size)))
    for choice in (1, 0, 20):
        step(batch, [choice] * size)


def held(batch, owner=1, env=0):
    rows = batch.diagnostic_inventory()[env, owner]
    return rows[rows[:, 0] > 0]


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
                "selected_defenses",
                "defense_order",
                "pending_observations",
                "dream_defense_snapshot",
                "acquisition_snapshot",
                "counter_snapshot",
                "revival_snapshot",
                "attack_order",
                "cost_snapshot",
            )
        ),
        tuple(
            getattr(batch, name)
            for name in (
                "action_count",
                "hp_damage",
                "consumed_count",
                "miracle_use_count",
                "mp_spent",
                "automatic_gift_count",
                "suppressed_gift_count",
                "redraw_count",
                "redrawn_count",
                "revival_count",
                "self_curse_count",
                "counter_count",
                "resolved_attack_count",
            )
        ),
    )


def same(a, b):
    assert a[1] == b[1]
    for left, right in zip(a[0], b[0], strict=True):
        np.testing.assert_array_equal(left, right)


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


def oracle(seed, env, count, weights=PLAN.gifts.model_weights, epoch=1):
    model_stream = tickets(seed, env, 0x452821E638D01377, epoch)
    fake_stream = tickets(seed, env, 0xBE5466CF34E90C6C, epoch)
    categories = dict(PLAN.inventory.profiles)
    pools = {
        category: [m for m, c in PLAN.inventory.profiles if c == category]
        for category in range(1, 6)
    }
    total = sum(w for _, w in weights)
    result = []
    for _ in range(count):
        word = next(model_stream)
        assert word >= ((-total) & (2**64 - 1)) % total
        rank = word % total
        model = 0
        for candidate, weight in weights:
            if rank < weight:
                model = candidate
                break
            rank -= weight
        assert model in categories
        word = next(fake_stream)
        assert word >= ((-100) & (2**64 - 1)) % 100
        fake = 0
        if word % 100 < 50:
            pool = pools[categories[model]]
            word = next(fake_stream)
            assert word >= ((-len(pool)) & (2**64 - 1)) % len(pool)
            fake = pool[word % len(pool)]
        result.append((model, fake, 0))
    return result


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed", [67, 68, 999])
@pytest.mark.parametrize("mask", [0, 1, 2, 4, 8, 15])
def test_native_full_weighted_redraw_applies_dream_first_replaces_all_rows_without_extra_ticks(
    players, seed, mask
):
    batch = game(size=32, players=players, seed=seed)
    for env in range(32):
        hand(batch, [57], env=env)
        hand(
            batch,
            [178, 35, 194, 237, 3, 209, 208],
            env=env,
            owner=1,
            displays=[0, 112, 195, 210, 0, 0, 0],
            used=[0, 0, 0, 1, 0, 0, 0],
        )
        load(batch, env=env, mask=mask)
    begin(batch, size=32)
    before = snapshot(batch)
    step(batch, [1] * 32)
    assert not batch.dream_defense_snapshot().any() and batch.redraw_count == 0
    assert batch.diagnostic_inventory().tolist() == before[0][2].tolist()
    step(batch, [0] * 32)
    stats = batch.dream_defense_snapshot()
    assert np.all(stats[:, :4] == [1, 1, 1, 6]) and not stats[:, 6:].any()
    for env in range(32):
        expected = oracle(seed, env, 6)
        np.testing.assert_array_equal(held(batch, env=env)[:, 1:], expected)
        assert np.all(held(batch, env=env)[:, 0] > 107)
        assert stats[env, 4] == sum(fake > 0 for _, fake, _ in expected)
        assert stats[env, 5] == sum(fake > 0 and fake != model for model, fake, _ in expected)
    assert batch.redraw_count == 32 and batch.redrawn_count == 192
    assert batch.hp_damage == 512 and batch.consumed_count == 64
    assert np.all(batch.diagnostic_players()[:, 1, 4] == mask | 2)
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)
    assert not batch.diagnostic_players()[:, 1:, 5].any()
    assert batch.miracle_use_count == batch.automatic_gift_count == batch.counter_count == 0
    assert batch.self_curse_count == 32 and not batch.counter_snapshot()[:, 10].any()


@pytest.mark.parametrize("element", range(7))
@pytest.mark.parametrize("mask", [0, 4])
def test_public_wood_defense_compatibility_and_flash_use_displayed_hat(element, mask):
    batch = game(element=element)
    hand(batch, [57])
    hand(batch, [178, 189], owner=1)
    load(batch, mask=mask)
    begin(batch)
    legal = element in (0, 4, 6)
    assert bool(batch.choice_masks()[0, 1]) == legal
    if not legal:
        before = snapshot(batch)
        with pytest.raises(ValueError):
            step(batch, [1])
        same(snapshot(batch), before)
        step(batch, [2])
        assert bool(batch.choice_masks()[0, 1]) == (not bool(mask & 4))
    else:
        step(batch, [1])
        assert batch.pending_observations()[0, 6] == 14


@pytest.mark.parametrize(
    "hp,sun", [(1, False), (1, True), (16, False), (16, True), (17, False), (100, False)]
)
@pytest.mark.parametrize("players", [2, 3, 9])
def test_lethal_damage_revives_before_redraw_or_suppresses_dead_owner(hp, sun, players):
    batch = game(players=players, refill=True, weights=((191, 1),))
    hand(batch, [57])
    hand(batch, [178, 35, *([208] if sun else [])], owner=1)
    load(batch, hp=hp)
    begin(batch)
    step(batch, [1])
    step(batch, [0])
    lethal = hp <= 16
    revived = int(lethal and sun)
    dead = int(lethal and not sun)
    remaining = 1 + int(sun) - revived
    assert batch.revival_count == revived
    assert batch.redraw_count == 1 - dead and batch.redrawn_count == remaining * (1 - dead)
    assert batch.dream_defense_snapshot()[0, :4].tolist() == [
        1,
        1 - dead,
        1 - dead,
        remaining * (1 - dead),
    ]
    assert batch.dream_defense_snapshot()[0, 6] == dead
    assert batch.diagnostic_players()[0, 1, 0] == (10 if revived else max(0, hp - 16))
    gifts = (2 + revived) if not dead else (0 if players == 2 else 1)
    assert batch.automatic_gift_count == gifts
    assert batch.suppressed_gift_count == 2 + revived - gifts
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_duplicate_hats_each_redraw_remaining_hand_and_empty_pool_stays_bounded(count):
    batch = game(weights=((237, 1),))
    hand(batch, [57])
    hand(batch, [178] * count, owner=1)
    begin(batch)
    for choice in range(1, count + 1):
        step(batch, [choice])
    step(batch, [0])
    assert batch.dream_defense_snapshot()[0].tolist() == [count, count, count, 0, 0, 0, 0, count]
    assert batch.redraw_count == count and batch.redrawn_count == 0
    assert batch.hp_damage == max(0, 30 - 14 * count)
    assert batch.consumed_count == count + 1 and not held(batch).size


@pytest.mark.parametrize("count", [1, 2, 3])
def test_performed_miracles_are_replaced_with_fresh_unused_draws_not_retained(count):
    batch = game(weights=((237, 1),))
    hand(batch, [57])
    hand(batch, [178] + [237] * count, owner=1, used=[0] + [1] * count)
    begin(batch)
    step(batch, [1])
    step(batch, [0])
    rows = held(batch)
    assert np.all(rows[:, 1] == 237) and not rows[:, 3].any()
    assert batch.miracle_use_count == 0 and batch.redrawn_count == count


@pytest.mark.parametrize(
    "actual,display,hat", [(178, 113, True), (113, 178, False), (172, 178, False)]
)
def test_hidden_actual_hat_roles_resolve_only_on_confirm(actual, display, hat):
    batch = game(weights=((191, 1),))
    hand(batch, [57])
    hand(batch, [actual, 35], owner=1, displays=[display, 0])
    begin(batch)
    assert batch.pending_observations()[0, 6] == 0
    step(batch, [1])
    assert batch.pending_observations()[0, 6] == (14 if display == 178 else 1)
    step(batch, [0])
    assert batch.redraw_count == int(hat)
    assert bool(batch.diagnostic_players()[0, 1, 4] & 2) == hat


@pytest.mark.parametrize("order", [(178, 168), (168, 178)])
def test_mixed_hat_and_fever_effects_preserve_click_order_without_defender_tick(order):
    batch = game(weights=((191, 1),))
    hand(batch, [57])
    hand(batch, [*order, 35], owner=1)
    begin(batch)
    step(batch, [1])
    step(batch, [2])
    step(batch, [0])
    assert batch.diagnostic_players()[0, 1, [0, 3, 4, 5]].tolist() == [94, 2, 2, 0]
    assert batch.redraw_count == 1 and batch.counter_snapshot()[0, 10] == 1
    assert batch.self_curse_count == 2


def test_hat_full_block_still_triggers_redraw():
    batch = game(weights=((191, 1),))
    hand(batch, [35])
    hand(batch, [178, 35], owner=1)
    begin(batch)
    step(batch, [1])
    step(batch, [0])
    assert batch.hp_damage == 0 and batch.redraw_count == 1  # Full DEF still triggers Hat.
    assert batch.diagnostic_players()[0, 1, 4] == 2


@pytest.mark.parametrize("failure", ["unsupported", "hidden-element", "decision", "duplicate"])
def test_late_defense_batch_rejection_rolls_back_redraw_rng_receipts_and_retry(failure):
    options = {"missing_armor": 113} if failure == "unsupported" else {}
    if failure == "hidden-element":
        options["element"] = 4
    attempted, reference = (
        game(size=2, refill=True, **options),
        game(size=2, refill=True, **options),
    )
    for batch in (attempted, reference):
        for env in range(2):
            hand(batch, [57], env=env)
            actual = 178 if env == 0 else (113 if failure == "unsupported" else 178)
            hand(batch, [actual, 35, 237], env=env, owner=1, displays=[178, 0, 0])
        # Raw omitted-role fixture permits a same-category disguised model
        # without inventing unsupported armor in the pinned source plan.
        if failure == "hidden-element":
            # Arithmetic fixture: Stone accepts displayed Wood, not actual Fire.
            hand(batch, [119, 35], env=1, owner=1, displays=[178, 0])
        begin(batch, size=2)
        step(batch, [1, 1])
    before = snapshot(attempted)
    episodes = attempted.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in range(2)])
    if failure == "decision":
        commands[1, 2] += 1
    elif failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        attempted.step(commands)
    same(snapshot(attempted), before)
    for batch in (attempted, reference):
        step(batch, [0], [0])
    same(snapshot(attempted), snapshot(reference))


def test_owned_snapshot_is_read_only_reset_clears_rows_but_retains_lifetime_totals():
    batch = game(turns=1, weights=((191, 1),))
    hand(batch, [57])
    hand(batch, [178, 35], owner=1)
    before = batch.dream_defense_snapshot()
    assert before.shape == (1, 8) and not before.flags.writeable
    begin(batch)
    step(batch, [1])
    step(batch, [0])
    assert not before.any()
    assert batch.redraw_count == batch.redrawn_count == 1
    batch.reset_environments(ids([0]))
    assert not batch.dream_defense_snapshot().any()
    assert batch.redraw_count == batch.redrawn_count == 1


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(178, 0, 3, 2)],
        [(178, 65536, 3, 2)],
        [(178, 14, 7, 2)],
        [(178, 14, 3, 1)],
        [(178, 14, 3, 15)],
        [(35, 14, 3, 2)],
        [(113, 14, 3, 2)],
        [(178, 14, 3, 2), (178, 14, 3, 2)],
    ],
)
def test_raw_dream_defense_profiles_reject_bad_bounds_categories_collisions_or_duplicates(profiles):
    with pytest.raises(ValueError):
        game(profiles=profiles)


def test_hat_requires_draw_weights_and_optional_omission_preserves_unsupported_role():
    with pytest.raises(ValueError, match="gift weights"):
        game(weights=None)
    batch = game(profiles=None, weights=None)
    hand(batch, [57])
    hand(batch, [178], owner=1)
    begin(batch)
    assert not batch.choice_masks()[0, 1]


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((178, 15, 3, 2),)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profile_fields": ("private-ticket",)},
        {"official_redraw_and_compound_timing_verified": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"redraw": "display-only"},
    ],
)
def test_source_plan_rejects_drift_or_promotable_scope_relabeling(change):
    with pytest.raises(ValidationError):
        FullGameDreamDefensePlan.model_validate(PLAN.dream_defense.model_dump() | change)


@pytest.mark.parametrize(
    "change", [{"def": 15}, {"curse": "heaven"}, {"giftRate": 3}, {"price": 9}]
)
def test_exact_raw_contract_rejects_rehashed_catalog_drift(change):
    catalog = read_api_catalog_snapshot(CATALOG)
    items = tuple(
        ApiCatalogItem(model_id=i.model_id, raw=dict(i.raw) | change) if i.model_id == 178 else i
        for i in catalog.items
    )
    altered = ApiCatalogSnapshot.model_validate(
        catalog.model_dump()
        | {"items": [i.model_dump() for i in items], "content_sha256": api_catalog_digest(items)}
    )
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_dream_defense_plan(
            altered, BibleSnapshot.model_validate_json(BIBLE.read_text())
        )


def test_factory_contract_declares_provisional_redraw_and_full_game_not_ready():
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    assert configured.metadata.kernel_schema_version == 33
    assert PLAN.integrated_artifact_effect_count == 237
    assert configured.metadata.dream_defense_snapshot_fields == DREAM_DEFENSE_FIELDS
    assert (
        not configured.metadata.full_game_training_ready
        and not configured.metadata.promotion_eligible
    )
    assert (
        FullGameMetadata.model_validate_json(configured.metadata.model_dump_json())
        == configured.metadata
    )
