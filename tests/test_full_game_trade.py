"""Exchange numeric phases, conserved previews, private masks and atomic joins."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    build_full_game_plan,
    create_development_full_game_batch,
    execute_full_game_commands,
    full_game_decision_contexts,
    full_game_policy_gradient_weights,
)
from godfield_bot.full_game_protocol import FullGameCommand
from godfield_bot.full_game_trade import (
    EXCHANGE_CHOICES,
    TRADE_FIELDS,
    TRADE_STATS,
    FullGameTradePlan,
    build_full_game_trade_plan,
)

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
CAT = read_api_catalog_snapshot(CATALOG)
BIB = BibleSnapshot.model_validate_json(BIBLE.read_text())
PLAN = build_full_game_plan(CAT, BIB)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=1, players=3, exchange=(3,), **options):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        exchange_model_ids=None if exchange is None else ids(exchange),
        passive_profiles=ids(PLAN.passives.profiles),
        attack_profiles=ids(PLAN.combat.attack_profiles[:1]),
        armor_profiles=ids([row for row in PLAN.combat.armor_profiles if row[0] == 127]),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        gift_profiles=ids(PLAN.gifts.model_weights),
        **options,
    )


def hand(b, cards=(3,), *, env=0, owner=0):
    b.seed_hand(
        env,
        owner,
        ids(
            [
                [i + 1, *(card if isinstance(card, tuple) else (card, 0, 0))]
                for i, card in enumerate(cards)
            ]
        ).reshape(-1, 4),
    )


def wallet(b, values, *, env=0, owner=0, illness=0, mask=0):
    b.seed_players(ids([env]), ids([owner]), ids([[*values, illness]]), ids([mask]))


def commands(b, choices, envs=None):
    rows = b.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    return ids([[env, *rows[env, :4], c] for env, c in zip(envs, choices, strict=True)])


def step(b, choice, env=0):
    b.step(commands(b, [choice], [env]))


def start(b, values=(50, 20, 5), *, cards=(3,), illness=0):
    for env in range(len(b.episode_snapshot())):
        hand(b, cards, env=env)
        wallet(b, values, env=env, illness=illness)
    b.start_environments(ids(range(len(b.episode_snapshot()))))


def snapshots(b):
    return tuple(
        getattr(b, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "player_observations",
            "trade_observations",
            "trade_snapshot",
            "revival_snapshot",
            "attack_family_snapshot",
            "confusion_snapshot",
            "acquisition_snapshot",
            "policy_gradient_masks",
            "guardian_statistics",
        )
    )


def same(before, after):
    for a, b in zip(before, after, strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize(
    "values", [(50, 20, 5), (1, 0, 0), (100, 100, 100), (1, 99, 99), (99, 1, 1)]
)
@pytest.mark.parametrize(
    "choice,axis,delta",
    [
        (1, 1, 10),
        (2, 1, 1),
        (3, 1, -1),
        (4, 1, -10),
        (5, 2, 10),
        (6, 2, 1),
        (7, 2, -1),
        (8, 2, -10),
    ],
)
def test_all_eight_amount_choices_clip_conserve_and_only_change_preview(
    values, choice, axis, delta
):
    b = game()
    start(b, values)
    before = b.diagnostic_players().copy()
    inventory = b.diagnostic_inventory().copy()
    step(b, 1)
    expected = list(values)
    amount = (
        min(delta, expected[0], 100 - expected[axis])
        if delta > 0
        else -min(-delta, expected[axis], 100 - expected[0])
    )
    assert b.choice_masks()[0, choice] == bool(amount)
    if amount:
        step(b, choice)
        expected[0] -= amount
        expected[axis] += amount
    else:
        image = snapshots(b)
        with pytest.raises(ValueError, match="unavailable"):
            step(b, choice)
        same(image, snapshots(b))
    assert b.trade_observations()[0, 2:5].tolist() == expected
    assert sum(expected) == sum(values)
    np.testing.assert_array_equal(before, b.diagnostic_players())
    np.testing.assert_array_equal(inventory, b.diagnostic_inventory())
    assert b.consumed_count == b.gift_count == b.mp_spent == b.utility_count == 0
    step(b, 9)
    np.testing.assert_array_equal(before, b.diagnostic_players())
    np.testing.assert_array_equal(inventory, b.diagnostic_inventory())
    assert not b.trade_observations().any()
    assert b.episode_snapshot()[0, 2:5].tolist() == [0, 1, 0]


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("refill", [False, True])
def test_commit_once_one_tick_no_price_mp_cost_or_attack_damage(players, refill):
    b = game(players=players, refill_on_use=refill)
    start(b, illness=2)
    step(b, 1)
    step(b, 1)
    step(b, 5)
    step(b, 4)
    old_command = commands(b, [0])
    b.step(old_command)
    assert b.diagnostic_players()[0, 0].tolist() == [38, 20, 15, 2, 0, 1]
    assert b.trade_snapshot()[0].tolist() == [1, 3, 0, 1, 0, 0, 10, 0, 0, 0]
    assert b.consumed_count == 1
    assert b.automatic_gift_count == int(refill)
    assert b.mp_spent == b.hp_damage == b.utility_hp_damage == b.attack_count == 0
    assert not b.diagnostic_players()[0, 1:, 5].any()
    before = snapshots(b)
    with pytest.raises(ValueError, match="stale"):
        b.step(old_command)
    same(before, snapshots(b))


@pytest.mark.parametrize("escape", [0, 9])
def test_edit_bound_keeps_confirm_and_cancel_available(escape):
    b = game()
    start(b)
    step(b, 1)
    for i in range(64):
        step(b, 2 if i % 2 == 0 else 3)
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0, 9]
    assert b.trade_observations()[0, 5] == 64
    before = snapshots(b)
    with pytest.raises(ValueError, match="unavailable"):
        step(b, 1)
    same(before, snapshots(b))
    step(b, escape)
    assert b.consumed_count == int(escape == 0)
    assert b.diagnostic_players()[0, 0, 5] == int(escape == 0)


@pytest.mark.parametrize("failure", ["actor", "epoch", "decision", "phase", "choice", "hidden"])
@pytest.mark.parametrize("commit", [False, True])
def test_late_failed_row_rolls_back_previews_wallets_sun_bow_gifts_and_tokens(failure, commit):
    b = game(size=2, refill_on_use=True)
    start(b, values=(1, 0, 0), cards=(3, 208, 112))
    if failure == "hidden":
        b.reset_environments(ids([1]))
        hand(b, [(4, 3, 0), 208, 112], env=1)
        wallet(b, (1, 0, 0), env=1)
        b.start_environments(ids([1]))
    b.step(commands(b, [1, 1]))
    b.step(commands(b, [2, 2]))
    rows = commands(b, [0 if commit else 3] * 2)
    if failure != "hidden":
        rows[1, {"epoch": 1, "decision": 2, "actor": 3, "phase": 4, "choice": 5}[failure]] += 999
    elif not commit:
        rows[1, 5] = 99
    before = snapshots(b)
    with pytest.raises(ValueError):
        b.step(rows)
    same(before, snapshots(b))
    assert b.consumed_count == b.gift_count == b.revival_count == 0
    step(b, 0, 0)
    assert b.revival_snapshot()[0, 9] == 1
    assert b.trade_snapshot()[0, 3] == 1


@pytest.mark.parametrize("actual", [3, 4, 5])
def test_displayed_trade_reservation_does_not_reveal_actual_role(actual):
    b = game()
    start(b, cards=((actual, 3, 0),))
    step(b, 1)
    assert b.trade_observations()[0].tolist() == [1, 1, 50, 20, 5, 0, 1]
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == list(range(10))
    if actual != 3:
        before = snapshots(b)
        with pytest.raises(ValueError, match="hidden actual Exchange"):
            step(b, 0)
        same(before, snapshots(b))
        step(b, 9)  # Cancelling never inspects the actual role.
    else:
        step(b, 0)


@pytest.mark.parametrize("cards", [(3,), (3, 208), (3, 112)])
def test_zero_hp_is_not_death_until_commit_then_shared_reactions_tick_once(cards):
    b = game(players=2)
    hand(b, cards)
    wallet(b, (1, 0, 0))
    wallet(b, (40, 10, 0), owner=1, mask=8)
    b.start_environments(ids([0]))
    step(b, 1)
    step(b, 2)
    assert b.trade_observations()[0, 2] == 0
    assert b.diagnostic_players()[0, 0, 0] == 1
    assert not b.revival_snapshot().any()
    step(b, 0)
    if 112 in cards:
        assert b.episode_snapshot()[0, 3] == 4
        assert b.diagnostic_players()[0, 0, 5] == 0
        step(b, 0)
        assert b.ascension_count == 1 and b.ascension_hp_damage == 30
    assert b.diagnostic_players()[0, 0, 5] == 1
    assert b.revival_snapshot()[0, 9] == int(208 in cards)
    assert b.diagnostic_players()[0, 0, :3].tolist() == [10 if 208 in cards else 0, 1, 0]
    assert b.hp_damage == (30 if 112 in cards else 0)
    assert b.guardian_statistics()[0, 11] == 0


@pytest.mark.parametrize("values", [(1, 0, 0), (50, 20, 5), (100, 100, 100)])
def test_confusion_resolves_exchange_natively_without_policy_amount_choices(values):
    b = game(size=128, seed=67)
    for env in range(128):
        hand(b, env=env)
        wallet(b, values, env=env)
    b.seed_confusion(ids(range(128)), ids([0] * 128), ids([1] * 128))
    b.start_environments(ids(range(128)))
    assert not b.policy_gradient_masks().any()
    b.step(commands(b, [0] * 128))
    stats = b.trade_snapshot()
    traded = np.flatnonzero(stats[:, 3])
    assert 40 < len(traded) < 90
    # Independent first action ticket: Exchange or Prayer. Independent wallet ticket.
    mask = 2**64 - 1

    def ticket(env, stream):
        v = 67 ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask) ^ 0xBF58476D1CE4E5B9 ^ stream
        v = (v + 0x9E3779B97F4A7C15) & mask
        v = ((v ^ (v >> 30)) * 0xBF58476D1CE4E5B9) & mask
        v = ((v ^ (v >> 27)) * 0x94D049BB133111EB) & mask
        return v ^ (v >> 31)

    total = sum(values)
    allocations = [
        (total - mp - cp, mp, cp)
        for mp in range(101)
        for cp in range(101)
        if 0 <= total - mp - cp <= 100
    ]
    for env in range(128):
        assert bool(stats[env, 3]) == (ticket(env, 0xC5D1B023286085F0) % 2 == 0)
    for env in traded:
        expected = allocations[ticket(int(env), 0xB8E1AFED6A267E96) % len(allocations)]
        assert b.diagnostic_players()[env, 0, :3].tolist() == list(expected)
    np.testing.assert_array_equal(stats[:, 3], stats[:, 8])
    np.testing.assert_array_equal(stats[:, 3], stats[:, 9])
    assert not stats[:, 1].any() and not b.trade_observations().any()
    assert not b.confusion_snapshot()[:, 0].any()
    assert np.all(b.diagnostic_players()[:, 0, 5] == 1)


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_truncation_discards_uncommitted_preview_without_consumption(limit):
    b = game(max_decisions=limit)
    start(b)
    for choice in (1, 1, 5)[:limit]:
        step(b, choice)
    assert b.episode_snapshot()[0, 3] == 13
    assert b.diagnostic_players()[0, 0].tolist() == [50, 20, 5, 0, 0, 0]
    assert b.consumed_count == 0 and not b.trade_observations().any()
    assert not b.choice_masks().any() and not b.policy_gradient_masks().any()


def test_observations_owned_readonly_and_reset_clears_trade_diagnostics():
    b = game()
    start(b)
    step(b, 1)
    old = b.trade_observations()
    oldstats = b.trade_snapshot()
    assert not old.flags.writeable and not oldstats.flags.writeable
    step(b, 1)
    assert old[0].tolist() == [1, 1, 50, 20, 5, 0, 1]
    assert oldstats[0, 1] == 0
    b.reset_environments(ids([0]))
    assert not b.trade_observations().any() and not b.trade_snapshot().any()
    assert b.episode_snapshot()[0, 0] == 2


def test_phase_context_weights_and_six_column_adapter():
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=1,
        capacity=18,
    )
    b = configured.batch
    start(b)
    for choice in (1, 1, 0):
        context = full_game_decision_contexts(configured)[0]
        command = FullGameCommand(
            **context.model_dump(exclude={"legal_choice_ids"}), choice_id=choice
        )
        weights = full_game_policy_gradient_weights(configured, [command])
        assert weights.tolist() == [1.0] and not weights.flags.writeable
        if b.episode_snapshot()[0, 3] == 6:
            assert context.phase == "trade-response"
        execute_full_game_commands(configured, [command])
    assert configured.metadata.trade_choice_schema_version == 2
    assert configured.metadata.trade_observation_fields == TRADE_FIELDS
    assert configured.metadata.trade_snapshot_fields == TRADE_STATS
    assert not configured.metadata.full_game_training_ready


@pytest.mark.parametrize("profiles", [[], [4], [5], [3, 3], [2], [207]])
def test_native_rejects_invalid_or_duplicate_exchange_roles(profiles):
    with pytest.raises(ValueError, match="Exchange"):
        game(exchange=profiles)


def test_raw_optional_omission_preserves_unsupported_trade_fixture():
    b = game(exchange=None)
    start(b)
    assert not b.choice_masks()[0, 1]
    assert not b.trade_observations().any()


def test_source_identity_price_table_and_contract_round_trip():
    plan = build_full_game_trade_plan(CAT, BIB)
    assert len(plan.price_profiles) == 237 and sum(row[2] for row in plan.price_profiles) == 1795
    assert plan.price_profiles[:3] == ((3, 1, 5), (4, 2, 5), (5, 3, 5))
    assert plan.exchange_choices == EXCHANGE_CHOICES
    assert FullGameTradePlan.model_validate_json(plan.model_dump_json()) == plan
    assert PLAN.integrated_artifact_effect_count == 237
    assert native.FULL_GAME_TRADE_CHOICE_SCHEMA_VERSION == 2
    assert native.FULL_GAME_MAX_TRADE_ACTIONS == 64


@pytest.mark.parametrize(
    "change",
    [
        {"exchange_model_ids": (4,)},
        {"pending_trade_model_ids": (4, 5)},
        {"exchange_choices": tuple(reversed(EXCHANGE_CHOICES))},
        {"maximum_amount_edits": 0},
        {"choice_schema_version": 3},
        {"price_profile_fields": ("price",)},
        {"price_profiles": ()},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"official_fidelity_verified": True},
        {"sell_buy_item_transfers_implemented": False},
    ],
)
def test_trade_plan_cannot_forge_source_or_gate_readiness(change):
    with pytest.raises(ValidationError):
        FullGameTradePlan.model_validate(PLAN.trade.model_dump() | change)


def test_client_pin_mutation_rejected_even_from_unchecked_model_copy():
    bad = BIB.model_copy(update={"client": BIB.client.model_copy(update={"sha256": "0" * 64})})
    with pytest.raises(ValueError, match="trade source"):
        build_full_game_trade_plan(CAT, bad)


@pytest.mark.parametrize("values", [(1, 0, 0), (50, 20, 5), (100, 100, 0), (100, 100, 100)])
def test_numeric_controls_reach_every_sampled_conserved_wallet_within_edit_bound(values):
    allocations = [
        (sum(values) - mp - cp, mp, cp)
        for mp in range(101)
        for cp in range(101)
        if 0 <= sum(values) - mp - cp <= 100
    ]
    targets = allocations[:: max(1, len(allocations) // 512)]
    b = game(size=len(targets))
    start(b, values=values)
    b.step(commands(b, [1] * len(targets)))
    for _ in range(64):
        previews = b.trade_observations()[:, 2:5]
        envs, choices = [], []
        for env, target in enumerate(targets):
            if previews[env].tolist() == list(target):
                continue
            for axis in (1, 2):
                delta = target[axis] - previews[env, axis]
                if (delta > 0 and previews[env, 0] > 0) or (delta < 0 and previews[env, 0] < 100):
                    offset = 0 if axis == 1 else 4
                    choice = offset + (
                        (1 if delta >= 10 else 2) if delta > 0 else (4 if delta <= -10 else 3)
                    )
                    assert b.choice_masks()[env, choice]
                    envs.append(env)
                    choices.append(choice)
                    break
            else:
                raise AssertionError("conserved target has no progressing amount choice")
        if not envs:
            break
        b.step(commands(b, choices, envs))
    np.testing.assert_array_equal(b.trade_observations()[:, 2:5], targets)
    assert np.all(b.trade_observations()[:, 5] <= 64)
