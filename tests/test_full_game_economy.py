"""CP utility, shared wallet regression, hidden resolution and batch rollback."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    CP_UTILITY_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_economy import FullGameEconomyPlan, build_full_game_economy_plan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=1, players=3, refill=False, turns=100, decisions=400, profiles=None):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles if profiles is None else profiles).reshape(-1, 4),
        capacity=8,
        initial_hp=40,
        initial_mp=10,
        initial_cp=0,
        max_turns=turns,
        max_decisions=decisions,
        passive_profiles=ids(PLAN.passives.profiles),
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, *, env=0, hp=40, mp=10, cp=0, illness=0, model=236, display=0, used=0, sun=False):
    batch.seed_players(ids([env]), ids([0]), ids([[hp, mp, cp, illness]]), ids([0]))
    cards = [[1, model, display, used], [2, 191, 0, 0]]
    if sun:
        cards.append([3, 208, 0, 0])
    batch.seed_hand(env, 0, ids(cards))


def step(batch, choices, envs=None):
    episodes = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(ids([[env, *episodes[env, :4], c] for env, c in zip(envs, choices, strict=True)]))


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
                "cp_utility_snapshot",
                "revival_snapshot",
                "acquisition_snapshot",
            )
        ),
        (
            batch.utility_count,
            batch.cp_utility_count,
            batch.utility_cp_gain,
            batch.mp_spent,
            batch.miracle_use_count,
            batch.consumed_count,
            batch.automatic_gift_count,
            batch.action_count,
            batch.revival_count,
        ),
    )


def same(left, right):
    assert left[1] == right[1]
    for a, b in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("mp", [0, 4, 5, 6, 100])
@pytest.mark.parametrize("cp", [0, 89, 90, 95, 99, 100])
@pytest.mark.parametrize("used", [0, 1])
def test_exact_affordability_cap_and_retained_tail_do_not_charge_cp(mp, cp, used):
    batch = game()
    seed(batch, mp=mp, cp=cp, used=used)
    batch.start_environments(ids([0]))
    legal = mp >= 5 and cp < 100
    assert bool(batch.choice_masks()[0, 1]) == legal
    if not legal:
        before = snapshot(batch)
        with pytest.raises(ValueError, match="unavailable"):
            step(batch, [1])
        same(snapshot(batch), before)
        return
    step(batch, [1])
    gain = min(10, 100 - cp)
    assert batch.diagnostic_players()[0, 0].tolist() == [40, mp - 5, cp + gain, 0, 0, 1]
    assert batch.cp_utility_snapshot()[0].tolist() == [1, gain, 5, int(gain < 10)]
    assert batch.cp_utility_count == batch.utility_count == batch.miracle_use_count == 1
    assert batch.utility_cp_gain == gain and batch.mp_spent == 5
    assert batch.consumed_count == batch.automatic_gift_count == 0
    assert batch.diagnostic_inventory()[0, 0, :2].tolist() == [[2, 191, 0, 0], [1, 236, 0, 1]]
    assert batch.episode_snapshot()[0, 2:5].tolist() == [1, 1, 1]
    assert np.count_nonzero(batch.diagnostic_players()[0, 1:, 5]) == 0


@pytest.mark.parametrize("players", [2, 3, 9])
def test_two_uses_of_the_same_instance_each_charge_mp_and_grant_cp(players):
    batch = game(players=players)
    seed(batch, mp=10)
    batch.start_environments(ids([0]))
    step(batch, [1])
    for _ in range(players - 1):
        step(batch, [0])
    step(batch, [2])  # Reusable miracle is now at the tail.
    assert batch.diagnostic_players()[0, 0, :3].tolist() == [40, 0, 20]
    assert batch.cp_utility_snapshot()[0].tolist() == [2, 20, 10, 0]
    assert batch.cp_utility_count == batch.miracle_use_count == 2
    assert not batch.choice_masks()[0, 2]  # Actor changed; no own-card assumptions.


@pytest.mark.parametrize(
    "actual,display,mp,cp,expected",
    [
        (236, 235, 10, 100, (40, 5, 100, 1, 0, 5, 1)),
        (235, 236, 10, 0, (50, 3, 0, 0, 0, 0, 0)),
        (238, 236, 10, 0, (40, 5, 0, 0, 0, 0, 0)),
    ],
)
def test_same_family_dream_resolves_actual_resource_cost_and_cap(actual, display, mp, cp, expected):
    batch = game()
    seed(batch, model=actual, display=display, mp=mp, cp=cp)
    batch.start_environments(ids([0]))
    assert batch.choice_masks()[0, 1]
    step(batch, [1])
    assert tuple(batch.diagnostic_players()[0, 0, :3]) == expected[:3]
    assert tuple(batch.cp_utility_snapshot()[0]) == expected[3:]
    assert batch.diagnostic_inventory()[0, 0, 1].tolist() == [1, actual, display, 1]
    assert batch.utility_count == batch.miracle_use_count == 1


@pytest.mark.parametrize("actual", [235, 236, 238, 215])
def test_public_projection_and_mask_do_not_consult_actual_hidden_effect(actual):
    reference, hidden = game(), game()
    seed(reference, model=236, display=236)
    seed(hidden, model=actual, display=236)
    for batch in (reference, hidden):
        batch.start_environments(ids([0]))
    for name in ("actor_hands", "player_observations", "choice_masks", "episode_snapshot"):
        np.testing.assert_array_equal(getattr(reference, name)(), getattr(hidden, name)())
    assert np.count_nonzero(hidden.cp_utility_snapshot()) == 0


@pytest.mark.parametrize("failure", ["hidden-cost", "hidden-family", "decision", "duplicate"])
def test_late_rejection_rolls_back_prepared_credit_use_tick_receipt_and_retry(failure):
    reference, attempted = game(size=2, refill=True), game(size=2, refill=True)
    for batch in (reference, attempted):
        seed(batch, env=0, cp=95)
        if failure == "hidden-cost":
            seed(batch, env=1, mp=2, model=236, display=237, illness=1)
        elif failure == "hidden-family":
            seed(batch, env=1, model=215, display=236)
        else:
            seed(batch, env=1)
        batch.start_environments(ids([0, 1]))
    before = snapshot(attempted)
    episodes = attempted.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 1] for env in (0, 1)])
    if failure == "decision":
        commands[1, 2] += 1
    if failure == "duplicate":
        commands[1] = commands[0]
    with pytest.raises(ValueError):
        attempted.step(commands)
    same(snapshot(attempted), before)
    step(attempted, [1], [0])
    step(reference, [1], [0])
    same(snapshot(attempted), snapshot(reference))
    assert attempted.cp_utility_snapshot()[0].tolist() == [1, 5, 5, 1]
    assert attempted.automatic_gift_count == 1


@pytest.mark.parametrize("sun", [False, True])
@pytest.mark.parametrize("players", [2, 3])
def test_credit_precedes_lethal_owner_tick_revival_and_real_outcome(sun, players):
    batch = game(players=players, refill=True)
    seed(batch, hp=1, illness=1, sun=sun)
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.diagnostic_players()[0, 0, :3].tolist() == [10 if sun else 0, 5, 10]
    assert batch.cp_utility_snapshot()[0].tolist() == [1, 10, 5, 0]
    assert batch.revival_count == int(sun)
    assert batch.consumed_count == int(sun)
    assert batch.automatic_gift_count == (2 if sun else 0)
    if not sun and players == 2:
        assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]
    else:
        assert batch.episode_snapshot()[0, 3] == 1


@pytest.mark.parametrize("turns,decisions,outcome", [(1, 400, 3), (100, 1, 4)])
def test_limits_after_real_credit_keep_effect_but_suppress_pending_gift(turns, decisions, outcome):
    batch = game(refill=True, turns=turns, decisions=decisions)
    seed(batch)
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.episode_snapshot()[0, 3:7].tolist() == [13, 1, outcome, -1]
    assert batch.utility_cp_gain == 10 and batch.mp_spent == 5
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 1


def test_diagnostic_snapshot_is_owned_read_only_and_reset_clears_episode_only():
    batch = game(turns=1)
    seed(batch)
    batch.start_environments(ids([0]))
    view = batch.cp_utility_snapshot()
    with pytest.raises(ValueError):
        view[0, 0] = 1
    step(batch, [1])
    assert np.count_nonzero(view) == 0
    batch.reset_environments(ids([0]))
    assert np.count_nonzero(batch.cp_utility_snapshot()) == 0
    assert batch.cp_utility_count == 1 and batch.utility_cp_gain == 10
    seed(batch, cp=99)
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.cp_utility_snapshot()[0].tolist() == [1, 1, 5, 1]
    assert batch.cp_utility_count == 2 and batch.utility_cp_gain == 11


def test_automatic_receipt_overflow_rolls_back_credit_payment_and_retained_hand():
    batch = game(refill=True)
    seed(batch)
    batch.seed_hand(0, 0, ids([[1, 236, 0, 0]] + [[i, 191, 0, 0] for i in range(2, 9)]))
    batch.start_environments(ids([0]))
    before = snapshot(batch)
    with pytest.raises(ValueError, match="hand limit would overflow"):
        step(batch, [1])
    same(snapshot(batch), before)


def test_raw_profiles_without_cp_leave_treasure_unavailable_and_older_utilities_unchanged():
    batch = game(profiles=[row for row in PLAN.effect_profiles if row[1] != 5])
    seed(batch)
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 1]
    assert batch.choice_masks()[0, 2]
    step(batch, [2])
    assert batch.diagnostic_players()[0, 0, :3].tolist() == [45, 10, 0]
    assert batch.cp_utility_count == batch.utility_cp_gain == 0
    assert np.count_nonzero(batch.cp_utility_snapshot()) == 0


@pytest.mark.parametrize(
    "profiles",
    [
        [[236, 5, 0, 5]],
        [[236, 5, 101, 5]],
        [[236, 5, 10, -1]],
        [[236, 5, 10, 101]],
        [[236, 5, 10, 0]],
        [[191, 5, 10, 5]],
        [[4, 5, 10, 5]],
        [[35, 5, 10, 5]],
        [[236, 6, 10, 5]],
        [[236, 5, 10, 5], [236, 5, 10, 5]],
    ],
)
def test_raw_cp_profile_validation_cannot_reclassify_free_sundries_or_trade(profiles):
    with pytest.raises(ValueError, match="utility profile"):
        game(profiles=profiles)


@pytest.mark.parametrize(
    "changes",
    [
        {"profiles": ((236, 5, 9, 5),)},
        {"profile_fields": ("cp",)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"payment": "cp-only"},
        {"effect_count": 2},
        {"trading_implemented": True},
        {"official_credit_cap_and_timing_verified": True},
        {"promotion_eligible": True},
    ],
)
def test_economy_plan_pins_arithmetic_and_does_not_claim_trading_or_validation(changes):
    with pytest.raises(ValidationError):
        FullGameEconomyPlan.model_validate(PLAN.economy.model_dump() | changes)


def test_source_revalidation_and_factory_new_effect_does_not_mutate_guardian_profile():
    catalog = read_api_catalog_snapshot(CATALOG)
    item = next(item for item in catalog.items if item.model_id == 236)
    altered = item.model_copy(update={"raw": dict(item.raw) | {"cost": 4}})
    tampered = catalog.model_copy(
        update={"items": tuple(altered if row.model_id == 236 else row for row in catalog.items)}
    )
    with pytest.raises(ValueError):
        build_full_game_economy_plan(tampered, BibleSnapshot.model_validate_json(BIBLE.read_text()))
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=8
    )
    assert len(PLAN.utilities.profiles) == 8
    assert configured.metadata.plan.economy.profiles == ((236, 5, 10, 5),)
    assert configured.metadata.cp_utility_snapshot_fields == CP_UTILITY_FIELDS
    assert configured.metadata.kernel_schema_version == 32
    assert PLAN.integrated_artifact_effect_count == 237
    seed(configured.batch)
    configured.batch.start_environments(ids([0]))
    step(configured.batch, [1])
    assert np.count_nonzero(configured.batch.cp_utility_snapshot()) == 0
    step(configured.batch, [0])
    assert configured.batch.cp_utility_snapshot()[0].tolist() == [1, 10, 5, 0]
    assert not configured.metadata.local_training_eligible
    assert not configured.metadata.full_game_training_ready
    assert not configured.metadata.promotion_eligible
    for change in ({"cp_utility_snapshot_fields": ("true-card",)}, {"schema_version": 10}):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate(configured.metadata.model_dump() | change)
