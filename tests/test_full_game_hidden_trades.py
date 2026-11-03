"""All six Dream trade swaps, private parameter oracles and shared settlement."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import game as raw_game
from test_full_game_generated import hand, ids, step, tickets

from godfield_bot.full_game import (
    HIDDEN_TRADE_FIELDS,
    FullGameMetadata,
    create_development_full_game_batch,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
PAIRS = [(actual, display) for actual in (3, 4, 5) for display in (3, 4, 5) if actual != display]


def game(actual, display, *, size=1, players=3, seed=67, fog=False, enabled=True, cards=(8, 11)):
    b = raw_game(
        size=size,
        players=players,
        seed=seed,
        resource_cap=99,
        initial_hp=99,
        resolve_hidden_targeting=True,
        resolve_hidden_trades=enabled,
    )
    for env in range(size):
        hand(b, [(actual, display, 0), *cards], env=env)
        b.seed_players(ids([env]), ids([0]), ids([[40, 20, 10, 0]]), ids([int(fog)]))
        for seat in range(1, players):
            hand(b, [191], seat, env)
    b.start_environments(ids(range(size)))
    return b


def prepare(b, display):
    size = len(b.episode_snapshot())
    step(b, [1] * size)
    if display == 4:
        step(b, [2] * size)
        step(b, [0] * size)


def cast(b, display, *, edit=False):
    size = len(b.episode_snapshot())
    prepare(b, display)
    if display == 3 and edit:
        step(b, [2] * size)
    step(b, [0 if display == 3 else 20] * size)


def snapshot(b):
    return tuple(
        getattr(b, name)().copy()
        for name in (
            "episode_snapshot",
            "diagnostic_inventory",
            "diagnostic_players",
            "actor_hands",
            "choice_masks",
            "trade_observations",
            "trade_snapshot",
            "market_observations",
            "market_snapshot",
            "market_escrow_snapshot",
            "attack_family_snapshot",
            "hidden_trade_snapshot",
            "acquisition_snapshot",
        )
    )


@pytest.mark.parametrize("actual,display", PAIRS)
@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("fog", [False, True])
def test_all_six_swaps_use_real_effects_and_one_original_tick(actual, display, players, fog):
    size = 32
    b = game(actual, display, size=size, players=players, fog=fog)
    cast(b, display, edit=True)
    stats = b.hidden_trade_snapshot()
    assert (stats[:, 0] == 1).all() and (stats[:, actual - 2] == 1).all()
    assert b.consumed_count == size
    if actual == 3:
        allocations = [
            (70 - mp - cp, mp, cp)
            for mp in range(100)
            for cp in range(100)
            if 0 <= 70 - mp - cp <= 99
        ]
        for env in range(size):
            expected = allocations[next(tickets(67, env, 0x7C4A7F8C93C4D7A1)) % len(allocations)]
            assert b.diagnostic_players()[env, 0, :3].tolist() == list(expected)
            assert b.diagnostic_inventory()[env, 0, :2, 1].tolist() == [8, 11]
        assert (stats[:, 4] == 1).all() and not stats[:, 5:8].any()
        assert not b.attack_family_snapshot().any()
    else:
        assert (b.episode_snapshot()[:, 3] == 4).all()
        assert not b.diagnostic_players()[:, 0, 5].any()
        assert (stats[:, 6] == int(display == 3)).all()
        for env in range(size):
            stream = 0x9E87C4D1B62A503F if display == 3 else 0xBA7C9045F12C7F99
            target = (
                1 + next(tickets(67, env, stream)) % (players - 1) if display == 3 or fog else 1
            )
            assert b.pending_observations()[env, 2] == target
            if actual == 4:
                parcel = [8, 11][next(tickets(67, env, 0xB31F2C8E57A04D69)) % 2]
                assert b.market_escrow_snapshot()[env, 2] == parcel
        step(b, [0] * size)
        if actual == 5:
            assert (b.trade_observations()[:, 1] == 3).all()
            assert not b.diagnostic_players()[:, 0, 5].any()
            step(b, [1] * size)
        assert not b.attack_family_snapshot()[:, 13:].any()
        assert (b.market_snapshot()[:, 13] == 1).all()
        assert not b.market_escrow_snapshot()[:, 5].any()
    assert (b.diagnostic_players()[:, 0, 5] == 1).all()
    assert not b.diagnostic_players()[:, 1:, 5].any()
    assert not b.automatic_gift_count and not b.miracle_use_count


@pytest.mark.parametrize("actual,display", PAIRS)
def test_reservation_and_masks_do_not_reveal_actual_trade(actual, display):
    truth, fake = game(display, display), game(actual, display)
    prepare(truth, display)
    prepare(fake, display)
    for key in (
        "choice_masks",
        "actor_hands",
        "player_observations",
        "trade_observations",
        "market_observations",
    ):
        np.testing.assert_array_equal(getattr(truth, key)(), getattr(fake, key)())
    assert not fake.hidden_trade_snapshot().any()


@pytest.mark.parametrize("display", [3, 5])
@pytest.mark.parametrize("cards", [(), ((211, 0, 1),)])
def test_hidden_sell_with_no_unused_parcel_consumes_and_records_empty_sale(display, cards):
    b = game(4, display, cards=cards)
    cast(b, display)
    assert b.hidden_trade_snapshot().tolist() == [[1, 0, 1, 0, 0, 0, 0, 1, int(display == 3)]]
    assert b.consumed_count == 1 and b.market_snapshot()[0, 3] == 1
    assert not b.market_snapshot()[0, 8:].any()
    assert not b.attack_family_snapshot().any()
    assert b.diagnostic_players()[0, 0, :3].tolist() == [40, 20, 10]
    assert b.diagnostic_players()[0, 0, 5] == 1


def test_empty_sale_replacement_uses_shared_receipt_and_not_a_false_transfer():
    b = raw_game(
        resource_cap=99,
        initial_hp=99,
        resolve_hidden_trades=True,
        gift_profiles=ids([[191, 1]]),
        refill_on_use=True,
    )
    hand(b, [(4, 3, 0)])
    b.start_environments(ids([0]))
    step(b, [1])
    step(b, [0])
    assert b.hidden_trade_snapshot()[0, 7] == 1
    assert b.automatic_gift_count == 1 and b.consumed_count == 1
    assert b.diagnostic_inventory()[0, 0, 0, 1] == 191
    assert not b.market_snapshot()[0, 13]


@pytest.mark.parametrize("display", [3, 4])
def test_real_buy_refusal_refunds_and_never_sells_the_ignored_public_parcel(display):
    b = game(5, display)
    cast(b, display)
    assert b.market_observations()[0, 6] == 0  # Not exposed before defense.
    step(b, [0])
    assert b.market_observations()[0, 6] == 191
    step(b, [0])
    assert b.market_snapshot()[0, 12] == b.market_snapshot()[0, 14] == 1
    assert not b.market_snapshot()[0, 13]
    assert b.diagnostic_inventory()[0, 0, :2, 1].tolist() == [8, 11]
    assert b.diagnostic_players()[0, 0, :3].tolist() == [40, 20, 10]


@pytest.mark.parametrize("actual,display", PAIRS)
def test_cancel_and_old_raw_errors_never_sample_or_partially_consume(actual, display):
    b = game(actual, display, enabled=False)
    assert not b.resolve_hidden_trades
    prepare(b, display)
    before = snapshot(b)
    with pytest.raises(ValueError, match="cross-role"):
        step(b, [0 if display == 3 else 20])
    for left, right in zip(before, snapshot(b), strict=True):
        np.testing.assert_array_equal(left, right)
    if display == 3:
        step(b, [9])
        assert b.episode_snapshot()[0, 3] == 1 and not b.hidden_trade_snapshot().any()


@pytest.mark.parametrize("actual,display", [(4, 3), (3, 5), (5, 3)])
def test_late_invalid_row_rolls_back_private_streams_custody_and_payments(actual, display):
    b, ref = game(actual, display, size=2), game(actual, display, size=2)
    for current in (b, ref):
        prepare(current, display)
    before = snapshot(b)
    state = b.episode_snapshot()
    rows = ids([[env, *state[env, :4], 0 if display == 3 else 20] for env in range(2)])
    rows[1, 2] += 1
    with pytest.raises(ValueError):
        b.step(rows)
    for left, right in zip(before, snapshot(b), strict=True):
        np.testing.assert_array_equal(left, right)
    b.step(rows[:1])
    ref.step(rows[:1])
    for left, right in zip(snapshot(b), snapshot(ref), strict=True):
        np.testing.assert_array_equal(left, right)


def test_exchange_wallet_zero_hp_preserves_shared_sun_revival_and_bow_flow():
    # Enumerate independent seeds until the selected allocation has HP zero.
    allocations = [
        (1 - mp - cp, mp, cp) for mp in range(2) for cp in range(2) if 0 <= 1 - mp - cp <= 1
    ]
    seed = next(
        s for s in range(100) if allocations[next(tickets(s, 0, 0x7C4A7F8C93C4D7A1)) % 3][0] == 0
    )
    for cards in ((208,), (112,)):
        b = raw_game(resource_cap=99, initial_hp=99, seed=seed, resolve_hidden_trades=True)
        hand(b, [(3, 5, 0), *cards])
        b.seed_players(ids([0]), ids([0]), ids([[1, 0, 0, 0]]), ids([0]))
        b.start_environments(ids([0]))
        step(b, [1])
        step(b, [20])
        if cards == (208,):
            assert b.revival_count == 1 and b.diagnostic_players()[0, 0, 0] == 10
        else:
            assert b.attack_family_snapshot()[0, 5] == 2
            for _ in range(4):
                if b.episode_snapshot()[0, 3] == 4:
                    step(b, [0])
            assert b.diagnostic_players()[0, 0, 5] == 1


def test_private_snapshot_readonly_reset_and_factory_metadata_remain_gated():
    b = game(4, 3)
    cast(b, 3)
    saved = b.hidden_trade_snapshot()
    assert not saved.flags.writeable
    with pytest.raises(ValueError):
        saved[0, 0] = 42
    with pytest.raises(AttributeError):
        b.resolve_hidden_trades = False
    b.reset_environments(ids([0]))
    assert not b.hidden_trade_snapshot().any() and saved[0, 0] == 1
    c = create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=1,
        capacity=18,
    )
    assert (
        c.batch.resolve_hidden_trades
        and c.metadata.hidden_trade_snapshot_fields == HIDDEN_TRADE_FIELDS
    )
    for change in (
        {"resolve_hidden_trades": False},
        {"hidden_trade_snapshot_fields": ()},
        {"full_game_training_ready": True},
    ):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate(c.metadata.model_dump() | change)
