"""Dream keeps its displayed UI; private targeting never leaks through masks."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import PLAN, game, hand, ids, step, tickets

from godfield_bot.full_game import (
    HIDDEN_TARGETING_FIELDS,
    FullGameMetadata,
    create_development_full_game_batch,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
CHANCE = dict(PLAN.combat.chance_profiles) | {p[0]: p[2] for p in PLAN.attack_family.profiles}
CATEGORIES = dict(PLAN.inventory.profiles)
LEADERS = sorted(
    {r[0] for r in PLAN.combat.attack_profiles} | {r[0] for r in PLAN.combat.boost_profiles if r[5]}
)


def scenario(actual=35, display=95, *, size=1, players=3, seed=67, enabled=True):
    b = game(size=size, players=players, seed=seed, resolve_hidden_targeting=enabled)
    for env in range(size):
        hand(b, [(actual, display, 0)], env=env)
        for seat in range(players):
            b.seed_players(ids([env]), ids([seat]), ids([[99, 99, 0, 0]]), ids([8]))
    b.start_environments(ids(range(size)))
    return b


def cast(b, display, chosen_seat=1):
    size = len(b.episode_snapshot())
    step(b, [1] * size)
    step(b, [0] * size)
    if CHANCE.get(display, 100) == 100:
        step(b, [19 + chosen_seat] * size)


def snapshots(b):
    return tuple(
        getattr(b, key)().copy()
        for key in (
            "episode_snapshot",
            "diagnostic_inventory",
            "diagnostic_players",
            "choice_masks",
            "attack_order",
            "attack_family_snapshot",
            "hidden_targeting_snapshot",
            "chance_snapshot",
        )
    )


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed", [0, 1, 67, 2**64 - 1])
@pytest.mark.parametrize("actual,display", [(16, 96), (35, 95), (95, 35), (112, 35)])
def test_both_targeting_directions_match_independent_private_streams(
    actual, display, players, seed
):
    size = 32
    b = scenario(actual, display, size=size, players=players, seed=seed)
    cast(b, display)
    chance = CHANCE.get(actual, 100) < 100
    for env in range(size):
        stream = 0xC6BC279692B5C323 if chance else 0x6C9E0E8BB01E8A3E
        expected = 1 + next(tickets(seed, env, stream)) % (players - 1)
        assert b.episode_snapshot()[env, 2] == expected
        assert b.pending_observations()[env, 2] == expected
    assert (
        b.hidden_targeting_snapshot().tolist()
        == [[1, int(chance), int(not chance), int(not chance)]] * size
    )
    assert b.chance_count == (size if chance else 0)


@pytest.mark.parametrize("actual,display", [(35, 95), (95, 35), (112, 35)])
def test_precast_masks_and_actor_views_depend_only_on_displays(actual, display):
    real, disguised = scenario(display, display), scenario(actual, display)
    for b in (real, disguised):
        step(b, [1])
        if CHANCE.get(display, 100) == 100:
            step(b, [0])
    for key in (
        "actor_hands",
        "choice_masks",
        "pending_observations",
        "chance_observations",
        "attack_selection_observations",
    ):
        np.testing.assert_array_equal(getattr(real, key)(), getattr(disguised, key)())
    assert not disguised.hidden_targeting_snapshot().any()


@pytest.mark.parametrize("chosen", [1, 2, 8])
def test_supplied_target_cannot_control_hidden_actual_chance(chosen):
    b = scenario(95, 35, size=32, players=9)
    cast(b, 35, chosen)
    expected = [1 + next(tickets(67, env, 0xC6BC279692B5C323)) % 8 for env in range(32)]
    assert b.episode_snapshot()[:, 2].tolist() == expected


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("model", [m for m in LEADERS if CATEGORIES[m] in (1, 4)])
def test_every_same_category_leader_crossing_target_modes_has_a_real_native_route(model, players):
    chance = CHANCE.get(model, 100) < 100
    display = next(
        m
        for m in LEADERS
        if CATEGORIES[m] == CATEGORIES[model] and (CHANCE.get(m, 100) < 100) != chance
    )
    b = scenario(model, display, players=players)
    cast(b, display)
    assert b.hidden_targeting_snapshot()[0, :3].tolist() == [1, int(chance), int(not chance)]
    assert b.attack_count == 1 and b.consumed_count + b.miracle_use_count == 1
    assert b.attack_family_snapshot()[0, 3] == 0
    if model not in {p[0] for p in PLAN.danger.profiles if p[1] == 1}:
        stream = 0xC6BC279692B5C323 if chance else 0x6C9E0E8BB01E8A3E
        assert b.pending_observations()[0, 2] == 1 + next(tickets(67, 0, stream)) % (players - 1)


def test_dead_opponents_are_excluded_from_fallback_pool():
    # Setup cannot be reopened after start; prepare the trusted state separately.
    b = game(size=32, players=9, seed=67, resolve_hidden_targeting=True)
    for env in range(32):
        hand(b, [(35, 95, 0)], env=env)
        for seat in range(1, 9):
            b.seed_players(
                ids([env]), ids([seat]), ids([[0 if seat in (1, 3, 6) else 99, 20, 0, 0]]), ids([8])
            )
    b.start_environments(ids(range(32)))
    cast(b, 95)
    living = [2, 4, 5, 7, 8]
    assert b.episode_snapshot()[:, 2].tolist() == [
        living[next(tickets(67, env, 0x6C9E0E8BB01E8A3E)) % 5] for env in range(32)
    ]


def test_raw_default_retains_explicit_target_mode_errors_and_atomic_state():
    b = scenario(enabled=False)
    assert not b.resolve_hidden_targeting
    step(b, [1])
    before = snapshots(b)
    with pytest.raises(ValueError, match="targeting mode"):
        step(b, [0])
    for old, now in zip(before, snapshots(b), strict=True):
        np.testing.assert_array_equal(old, now)


def test_late_invalid_hidden_cost_rolls_back_fallback_rng_and_stats():
    # Replace setup in a new pair to include a legal-looking but unaffordable true miracle.
    batches = [game(size=2, seed=67, resolve_hidden_targeting=True) for _ in range(2)]
    for b in batches:
        hand(b, [(35, 95, 0)], env=0)
        hand(b, [(230, 225, 0)], env=1)
        b.seed_players(ids([1]), ids([0]), ids([[99, 4, 0, 0]]), ids([0]))
        b.start_environments(ids([0, 1]))
        step(b, [1, 1])
    b, ref = batches
    before = snapshots(b)
    with pytest.raises(ValueError, match="unaffordable"):
        step(b, [0, 0])
    for old, now in zip(before, snapshots(b), strict=True):
        np.testing.assert_array_equal(old, now)
    step(b, [0], [0])
    step(ref, [0], [0])
    for left, right in zip(snapshots(b), snapshots(ref), strict=True):
        np.testing.assert_array_equal(left, right)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_dangerous_pestle_uses_its_own_native_recipient_not_an_invalid_placeholder(players):
    model = next(p[0] for p in PLAN.danger.profiles if p[1] == 1)
    b = scenario(model, 95, size=128, players=players)
    cast(b, 95)
    stats = b.danger_snapshot()
    assert (stats[:, 0] == 1).all() and (stats[:, 1] == 1).all()
    assert b.hidden_targeting_snapshot().tolist() == [[1, 0, 1, 0]] * 128
    assert not b.attack_family_snapshot()[:, 3].any()


def test_snapshot_owned_readonly_private_and_reset_epoch_streams():
    b = scenario(size=32)
    cast(b, 95)
    saved = b.hidden_targeting_snapshot()
    assert not saved.flags.writeable
    with pytest.raises(ValueError):
        saved[0, 0] = 42
    with pytest.raises(AttributeError):
        b.resolve_hidden_targeting = False
    b.reset_environments(ids(range(32)))
    assert not b.hidden_targeting_snapshot().any()
    assert saved[:, 0].sum() == 32
    for env in range(32):
        hand(b, [(35, 95, 0)], env=env)
    b.start_environments(ids(range(32)))
    cast(b, 95)
    assert b.episode_snapshot()[:, 2].tolist() == [
        1 + next(tickets(67, env, 0x6C9E0E8BB01E8A3E, epoch=2)) % 2 for env in range(32)
    ]


def test_factory_enables_approved_rule_and_metadata_cannot_claim_complete_hidden_support():
    c = create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=1,
        capacity=18,
    )
    assert c.batch.resolve_hidden_targeting and c.metadata.resolve_hidden_targeting
    assert c.metadata.hidden_targeting_snapshot_fields == HIDDEN_TARGETING_FIELDS
    for change in (
        {"resolve_hidden_targeting": False},
        {"hidden_targeting_snapshot_fields": ()},
        {"complete_hidden_cross_role_resolution": True},
        {"full_game_training_ready": True},
    ):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate(c.metadata.model_dump() | change)
