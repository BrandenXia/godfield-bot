"""Compound utility source contracts, native ownership, RNG isolation and rollback."""

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
    COMPOUND_UTILITY_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_compound_utilities import (
    FullGameCompoundUtilityPlan,
    build_full_game_compound_utility_plan,
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
    decisions=400,
    ordered=True,
    profiles=None,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles if profiles is None else profiles).reshape(-1, 4),
        capacity=8,
        seed=seed,
        max_turns=turns,
        max_decisions=decisions,
        initial_hp=40,
        initial_mp=10,
        initial_cp=7,
        passive_profiles=ids(PLAN.passives.profiles),
        cost_reducer_profiles=ids(PLAN.costs.profiles) if ordered else None,
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, *, env=0, hp=40, mp=10, illness=0, mask=0, model=198, display=0, suns=0):
    batch.seed_players(ids([env]), ids([0]), ids([[hp, mp, 7, illness]]), ids([mask]))
    batch.seed_hand(
        env,
        0,
        ids(
            [
                [1, model, display, 0],
                [2, 191, 0, 0],
                *[[3 + i, 208, 0, 0] for i in range(suns)],
            ]
        ),
    )


def step(batch, choices, envs=None):
    episodes = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(ids([[env, *episodes[env, :4], c] for env, c in zip(envs, choices, strict=True)]))


def use(batch, *, env=0):
    step(batch, [1], [env])
    assert batch.episode_snapshot()[env, 3] == 2
    step(batch, [0], [env])


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
                "compound_utility_snapshot",
                "revival_snapshot",
                "acquisition_snapshot",
                "utility_selection_observations",
                "attack_order",
                "cost_snapshot",
                "chance_snapshot",
                "attack_effect_snapshot",
            )
        ),
        tuple(
            getattr(batch, name)
            for name in (
                "utility_count",
                "utility_hp_damage",
                "mp_spent",
                "miracle_use_count",
                "consumed_count",
                "automatic_gift_count",
                "action_count",
                "revival_count",
                "hp_damage",
                "attack_count",
                "illness_effect_damage",
                "inflicted_illness_count",
            )
        ),
    )


def same(left, right):
    assert left[1] == right[1]
    for a, b in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(a, b)


def random_rank(seed_value, env, stream, bound, epoch=1):
    """Independent test oracle for the documented local first SplitMix ticket."""
    mask = 2**64 - 1
    state = seed_value ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
    state ^= (epoch * 0xBF58476D1CE4E5B9) & mask
    state ^= stream
    word = (state + 0x9E3779B97F4A7C15) & mask
    word = ((word ^ (word >> 30)) * 0xBF58476D1CE4E5B9) & mask
    word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
    word ^= word >> 31
    assert word >= ((-bound) & mask) % bound  # Fixtures need no rejection retry.
    return word % bound


def post_tick(hp, illness, *, env=0, seed_value=67):
    if hp:
        hp = min(100, hp + 5) if illness == 4 else max(0, hp - (0, 1, 2, 5)[illness])
    if hp and illness and random_rank(seed_value, env, 0, 100) < 5:
        if illness == 4:
            hp = 0
        else:
            illness += 1
    return hp, illness


@pytest.mark.parametrize("illness", range(5))
@pytest.mark.parametrize("mp", [0, 79, 80, 95, 99, 100])
@pytest.mark.parametrize("hp", [1, 40, 100])
def test_herb_gains_mp_then_inflicts_heaven_or_worsens_then_ticks(hp, mp, illness):
    batch = game()
    seed(batch, hp=hp, mp=mp, illness=illness, mask=15)
    batch.start_environments(ids([0]))
    assert batch.choice_masks()[0, 1]  # Full MP and lethal use remain legal.
    before = batch.diagnostic_players().copy()
    step(batch, [1])
    np.testing.assert_array_equal(before, batch.diagnostic_players())
    assert batch.utility_selection_observations()[0].tolist() == [1, 6, 20, 0]
    assert not batch.compound_utility_snapshot().any()
    step(batch, [0])
    expected_hp = 0 if illness == 4 else hp
    expected_stage = 4 if illness == 0 else min(4, illness + 1)
    expected_hp, expected_stage = post_tick(expected_hp, expected_stage)
    assert batch.diagnostic_players()[0, 0].tolist() == [
        expected_hp,
        min(100, mp + 20),
        7,
        expected_stage,
        15,
        1,
    ]
    assert batch.compound_utility_snapshot()[0].tolist() == [
        1,
        min(20, 100 - mp),
        int(mp > 80),
        1,
        hp if illness == 4 else 0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert batch.utility_hp_damage == (hp if illness == 4 else 0)
    assert batch.consumed_count == batch.utility_count == 1
    assert batch.attack_count == batch.hp_damage == batch.mp_spent == 0
    assert not batch.attack_effect_snapshot().any()
    assert batch.inflicted_illness_count == 1
    assert batch.diagnostic_inventory()[0, 0, 0].tolist() == [2, 191, 0, 0]
    assert not batch.diagnostic_players()[0, 1:, 5].any()


@pytest.mark.parametrize("hp", [1, 10, 40, 95, 99, 100])
@pytest.mark.parametrize("mask", [0, 1, 2, 4, 8, 15])
def test_tear_native_stream_hits_both_outcomes_without_target_or_dark_cloud_override(hp, mask):
    batch = game(size=32)
    for env in range(32):
        seed(batch, env=env, model=202, hp=hp, mask=mask)
    batch.start_environments(ids(range(32)))
    assert batch.choice_masks()[:, 1].all()
    step(batch, [1] * 32)
    assert np.all(batch.utility_selection_observations()[:, 1] == 7)
    assert not batch.compound_utility_snapshot().any()
    step(batch, [0] * 32)
    healed = np.asarray([random_rank(67, env, 0x13198A2E03707344, 2) == 0 for env in range(32)])
    assert healed.any() and not healed.all()
    expected = np.where(healed, min(100, hp + 10), max(0, hp - 10))
    np.testing.assert_array_equal(batch.diagnostic_players()[:, 0, 0], expected)
    stats = batch.compound_utility_snapshot()
    assert not stats[:, :5].any()
    assert np.all(stats[:, 5] == 1)
    np.testing.assert_array_equal(stats[:, 6], healed)
    np.testing.assert_array_equal(stats[:, 7], healed * min(10, 100 - hp))
    np.testing.assert_array_equal(stats[:, 8], ~healed)
    np.testing.assert_array_equal(stats[:, 9], (~healed) * min(10, hp))
    assert batch.utility_hp_damage == int(stats[:, 9].sum())
    assert batch.consumed_count == batch.utility_count == 32
    assert batch.attack_count == batch.hp_damage == batch.chance_count == 0
    assert np.all(batch.diagnostic_players()[:, 0, 4] == mask)
    assert not batch.diagnostic_players()[:, 1:, 5].any()


@pytest.mark.parametrize("model,stage,hp", [(198, 4, 1), (202, 0, 1)])
@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("suns", [0, 1, 2])
def test_lethal_utility_uses_owned_sun_before_periodic_and_endings(model, stage, hp, players, suns):
    # Pick an environment whose first utility ticket is damage and illness
    # ticket does not worsen; do not supply caller tickets to the native API.
    env = next(
        e
        for e in range(32)
        if random_rank(67, e, 0x13198A2E03707344, 2) == 1 and random_rank(67, e, 0, 100) >= 5
    )
    batch = game(size=env + 1, players=players, refill=True)
    seed(batch, env=env, model=model, illness=stage, hp=hp, suns=suns)
    batch.start_environments(ids([env]))
    use(batch, env=env)
    revived = int(suns > 0)
    assert batch.diagnostic_players()[env, 0, 0] == ((15 if model == 198 else 10) if suns else 0)
    assert batch.revival_snapshot()[env].tolist() == [
        revived,
        10 * revived,
        0,
        revived if model == 198 else 0,
        0,
        0,
        0,
        revived if model == 202 else 0,
        0,
        0,
    ]
    assert batch.consumed_count == 1 + revived
    assert batch.automatic_gift_count == (2 if suns else 0)
    assert batch.utility_hp_damage == hp
    assert batch.hp_damage == 0
    assert batch.episode_snapshot()[env, 5] == (1 if not suns and players == 2 else 0)
    assert batch.diagnostic_players()[env, 0, 5] == 1
    assert not batch.diagnostic_players()[env, 1:, 5].any()


@pytest.mark.parametrize("model", [198, 202])
def test_cancelled_or_truncated_reservation_has_no_effect_and_does_not_draw_rng(model):
    attempted, reference = game(), game()
    for batch in (attempted, reference):
        seed(batch, model=model)
        batch.start_environments(ids([0]))
    step(attempted, [1])
    step(attempted, [1])  # Undo leader.
    assert attempted.episode_snapshot()[0, 3] == 1
    assert not attempted.compound_utility_snapshot().any()
    for batch in (attempted, reference):
        use(batch)
    np.testing.assert_array_equal(
        attempted.compound_utility_snapshot(), reference.compound_utility_snapshot()
    )
    np.testing.assert_array_equal(attempted.diagnostic_players(), reference.diagnostic_players())
    truncated = game(decisions=1, refill=True)
    seed(truncated, model=model)
    truncated.start_environments(ids([0]))
    step(truncated, [1])
    assert truncated.episode_snapshot()[0, 3] == 13
    assert not truncated.compound_utility_snapshot().any()
    assert truncated.utility_count == truncated.consumed_count == truncated.utility_hp_damage == 0


@pytest.mark.parametrize("failure", ["unsupported", "cost", "decision", "duplicate"])
@pytest.mark.parametrize("model", [198, 202])
def test_late_rejection_rolls_back_rng_infection_revive_consumption_tick_and_receipts(
    failure, model
):
    attempted, reference = game(size=2, refill=True), game(size=2, refill=True)
    for batch in (attempted, reference):
        seed(batch, model=model, hp=1, illness=4, suns=2)
        if failure == "unsupported":
            seed(batch, env=1, model=201, display=202)
        elif failure == "cost":
            seed(batch, env=1, model=238, display=237, mp=2, illness=1)
        else:
            seed(batch, env=1, model=model)
        batch.start_environments(ids([0, 1]))
        step(batch, [1, 1])
    before = snapshot(attempted)
    episodes = attempted.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in (0, 1)])
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


@pytest.mark.parametrize("actual,display", [(198, 202), (202, 198), (191, 202), (201, 198)])
def test_public_projection_uses_displayed_family_and_actual_effect_only_on_confirm(actual, display):
    hidden, reference = game(), game()
    seed(hidden, model=actual, display=display)
    seed(reference, model=display, display=display)
    for batch in (hidden, reference):
        batch.start_environments(ids([0]))
        step(batch, [1])
    for name in (
        "actor_hands",
        "choice_masks",
        "utility_selection_observations",
        "player_observations",
    ):
        np.testing.assert_array_equal(getattr(hidden, name)(), getattr(reference, name)())
    if actual == 201:
        before = snapshot(hidden)
        with pytest.raises(ValueError, match="not implemented"):
            step(hidden, [0])
        same(snapshot(hidden), before)
    else:
        step(hidden, [0])
        stats = hidden.compound_utility_snapshot()[0]
        assert stats[0] == int(actual == 198) and stats[5] == int(actual == 202)


@pytest.mark.parametrize("model", [198, 202])
def test_raw_optional_reservation_omission_has_same_actual_effect_in_one_command(model):
    old, new = game(ordered=False), game()
    for batch in (old, new):
        seed(batch, model=model)
        batch.start_environments(ids([0]))
    step(old, [1])
    use(new)
    for name in ("diagnostic_players", "diagnostic_inventory", "compound_utility_snapshot"):
        np.testing.assert_array_equal(getattr(old, name)(), getattr(new, name)())


def test_diagnostics_are_owned_readonly_episode_reset_preserves_lifetime_damage():
    batch = game(size=32, turns=1)
    for env in range(32):
        seed(batch, env=env, model=202)
    batch.start_environments(ids(range(32)))
    view = batch.compound_utility_snapshot()
    assert view.shape == (32, 10) and not view.flags.writeable
    with pytest.raises(ValueError):
        view[0, 0] = 1
    step(batch, [1] * 32)
    step(batch, [0] * 32)
    assert not view.any()
    damage = batch.utility_hp_damage
    assert damage > 0
    batch.reset_environments(ids(range(32)))
    assert not batch.compound_utility_snapshot().any()
    assert batch.utility_hp_damage == damage
    assert batch.utility_count == 32
    assert batch.revival_snapshot().shape == (32, 10)


@pytest.mark.parametrize(
    "profile",
    [
        (198, 6, 0, 0),
        (198, 6, 101, 0),
        (198, 6, 20, 1),
        (202, 7, -1, 0),
        (202, 8, 10, 0),
        (236, 6, 20, 5),
    ],
)
def test_native_bad_compound_profile_rejected_before_construction(profile):
    with pytest.raises(ValueError, match="utility profile"):
        game(profiles=[profile])


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((198, 6, 21, 0), (202, 7, 10, 0))},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profile_fields": ("hidden-ticket",)},
        {"effect_codes": ("ordinary-heal",)},
        {"tear_heal_probability_percent": 100},
        {"herb_illness_stage": 3},
        {"probability_and_compound_timing_verified": True},
        {"promotion_eligible": True},
    ],
)
def test_plan_probability_sources_and_provisional_scope_cannot_be_relabelled(change):
    with pytest.raises(ValidationError):
        FullGameCompoundUtilityPlan.model_validate(PLAN.compound_utilities.model_dump() | change)


def test_factory_joins_new_profiles_and_preserves_training_and_live_gates():
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=8
    )
    assert PLAN.compound_utilities.profiles == ((198, 6, 20, 0), (202, 7, 10, 0))
    assert configured.metadata.kernel_schema_version == 31
    assert configured.metadata.compound_utility_snapshot_fields == COMPOUND_UTILITY_FIELDS
    assert PLAN.integrated_artifact_effect_count == 237
    assert (
        not configured.metadata.full_game_training_ready
        and not configured.metadata.promotion_eligible
    )
    assert (
        FullGameMetadata.model_validate_json(configured.metadata.model_dump_json())
        == configured.metadata
    )
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(
            configured.metadata.model_dump()
            | {
                "compound_utility_snapshot_fields": ("private-rng",),
            }
        )


@pytest.mark.parametrize("model", [198, 202])
@pytest.mark.parametrize(
    "change",
    [
        {"abilityValue": 21},
        {"ability": "boostHP"},
        {"category": "armor"},
        {"curse": "hell"},
        {"price": 99},
        {"giftRate": 3},
        {"cost": 1},
        {"element": "light"},
        {"name": "Changed utility"},
        {"hitRate": 100},
    ],
)
def test_source_builder_rejects_rehashed_catalog_drift_not_just_bad_checksums(model, change):
    catalog = read_api_catalog_snapshot(CATALOG)
    items = tuple(
        ApiCatalogItem(model_id=i.model_id, raw=dict(i.raw) | change) if i.model_id == model else i
        for i in catalog.items
    )
    changed = ApiCatalogSnapshot.model_validate(
        catalog.model_dump()
        | {
            "items": [i.model_dump() for i in items],
            "content_sha256": api_catalog_digest(items),
        }
    )
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_compound_utility_plan(
            changed, BibleSnapshot.model_validate_json(BIBLE.read_text())
        )


@pytest.mark.parametrize("asset", ["heaven-herb", "thump-thump-tear"])
@pytest.mark.parametrize("field", ["detail", "image_path", "element_image_paths"])
def test_source_builder_revalidates_exact_bible_effects_and_images(asset, field):
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    dumped = bible.model_dump()
    reference = next(r for r in dumped["catalog"]["sundries"]["items"] if r["asset"] == asset)
    reference[field] = {
        "detail": ("Changed utility", "HP+100", "always heal", "$0", "Gift Rate: 2/500"),
        "image_path": "/images/items/sundries/wrong.webp",
        "element_image_paths": ("/images/elements/light.webp",),
    }[field]
    changed = BibleSnapshot.model_validate(dumped)
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_compound_utility_plan(read_api_catalog_snapshot(CATALOG), changed)


def test_source_builder_revalidates_unchecked_catalog_copies():
    catalog = read_api_catalog_snapshot(CATALOG)
    item = catalog.items[197]
    changed = item.model_copy(update={"raw": dict(item.raw) | {"abilityValue": 21}})
    copied = catalog.model_copy(
        update={"items": tuple(changed if i.model_id == 198 else i for i in catalog.items)}
    )
    with pytest.raises(ValueError, match="checksum"):
        build_full_game_compound_utility_plan(
            copied, BibleSnapshot.model_validate_json(BIBLE.read_text())
        )
