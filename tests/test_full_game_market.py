"""Joined Sell/Buy custody, current-source decisions, and atomic shared reactions."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan, create_development_full_game_batch

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
PRICES = {model: price for model, _, price in PLAN.trade.price_profiles}


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=1, players=3, prices=PLAN.trade.price_profiles, **options):
    kwargs = dict(
        capacity=18,
        initial_hp=50,
        initial_mp=20,
        initial_cp=5,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        passive_profiles=ids(PLAN.passives.profiles),
        cost_reducer_profiles=ids(PLAN.costs.profiles),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        gift_profiles=ids(PLAN.gifts.model_weights),
        exchange_model_ids=ids([3]),
        market_profiles=None if prices is None else ids(prices).reshape(-1, 3),
    )
    kwargs.update(options)
    return native.FullGameBatch(
        size, players, ids(PLAN.inventory.profiles), ids(PLAN.effect_profiles), **kwargs
    )


def hand(b, cards, *, env=0, owner=0):
    b.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + i + 1, *(card if isinstance(card, tuple) else (card, 0, 0))]
                for i, card in enumerate(cards)
            ]
        ).reshape(-1, 4),
    )


def load(b, *, env=0, owner=0, hp=50, mp=20, cp=5, illness=0, mask=0):
    b.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def commands(b, choices, envs=None):
    envs = range(len(choices)) if envs is None else envs
    rows = b.episode_snapshot()
    return ids([[env, *rows[env, :4], c] for env, c in zip(envs, choices, strict=True)])


def step(b, choice, env=0):
    b.step(commands(b, [choice], [env]))
    families = b.attack_family_snapshot()
    np.testing.assert_array_equal(
        families[:, 0], families[:, 2] + families[:, 3] + families[:, 13] + (families[:, 14] > 0)
    )


def sell(b, *, env=0, choice=2, target=1):
    for c in (1, choice, 0, b.choice_masks().shape[1] - 9 + target):
        step(b, c, env)


def buy(b, *, env=0, target=1):
    for c in (1, b.choice_masks().shape[1] - 9 + target):
        step(b, c, env)


def models(b, owner=0, env=0):
    return [int(row[1]) for row in b.diagnostic_inventory()[env, owner] if row[0]]


def snapshot(b):
    return tuple(
        getattr(b, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "choice_masks",
            "market_observations",
            "market_snapshot",
            "market_escrow_snapshot",
            "trade_observations",
            "trade_snapshot",
            "attack_family_snapshot",
            "revival_snapshot",
            "acquisition_snapshot",
            "confusion_snapshot",
            "policy_gradient_masks",
        )
    )


def same(a, b):
    for left, right in zip(a, b, strict=True):
        np.testing.assert_array_equal(left, right)


@pytest.mark.parametrize("model", range(3, 240))
def test_every_unused_held_model_can_be_sold_at_pinned_price_without_being_used(model):
    b = game()
    hand(b, [4, model])
    load(b, owner=1, cp=100)
    b.start_environments(ids([0]))
    sell(b)
    assert b.market_observations()[0, 6:8].tolist() == [model, PRICES[model]]
    assert b.market_escrow_snapshot()[0].tolist() == [0, 2, model, 0, 0, 1]
    assert models(b) == [] and b.consumed_count == 1
    step(b, 0)
    assert models(b, 1) == [model]
    assert b.diagnostic_players()[0, 1, 2] == 100 - PRICES[model]
    assert b.diagnostic_players()[0, 0, 2] == min(100, 5 + PRICES[model])
    assert b.market_snapshot()[0, [3, 8, 13]].tolist() == [1, 1, 1]
    assert b.consumed_count == 1 and b.miracle_use_count == b.gift_count == 0
    assert not b.market_escrow_snapshot().any()
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("model", range(3, 240))
@pytest.mark.parametrize("bought", [False, True])
def test_every_unused_held_model_can_be_offered_and_purchased_or_returned(model, bought):
    b = game()
    hand(b, [5])
    hand(b, [(model, 0, 0)], owner=1)
    load(b, cp=100)
    b.start_environments(ids([0]))
    buy(b)
    assert b.market_observations()[0].tolist() == [1, 2, 3, 0, 1, 0, 0, 0, 0]
    step(b, 0)
    assert b.episode_snapshot()[0, 2:5].tolist() == [0, 6, 0]
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0, 1]
    assert b.trade_observations()[0].tolist() == [1, 3, 0, 0, 0, 0, 0]
    assert b.market_observations()[0, 6:8].tolist() == [model, PRICES[model]]
    assert models(b, 1) == []
    step(b, int(bought))
    assert models(b) == ([model] if bought else [])
    assert models(b, 1) == ([] if bought else [model])
    assert b.diagnostic_players()[0, 0, 2] == 100 - (PRICES[model] if bought else 0)
    assert b.diagnostic_players()[0, 1, 2] == min(100, 5 + (PRICES[model] if bought else 0))
    assert b.market_snapshot()[0, [9, 11, 12, 13, 14, 21]].tolist() == [
        1,
        int(bought),
        int(not bought),
        int(bought),
        int(not bought),
        1,
    ]
    assert not b.market_escrow_snapshot().any()
    assert b.consumed_count == 1 and b.miracle_use_count == b.gift_count == 0
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("players", [2, 3, 9])
def test_performed_miracles_cannot_be_sold_or_bought_but_unused_miracles_can(players):
    b = game(players=players)
    hand(b, [4, (237, 0, 1), 238])
    hand(b, [(237, 0, 1), (238, 0, 1)], owner=1)
    b.start_environments(ids([0]))
    step(b, 1)
    assert not b.choice_masks()[0, 2] and b.choice_masks()[0, 3]
    before = snapshot(b)
    with pytest.raises(ValueError, match="unavailable"):
        step(b, 2)
    same(before, snapshot(b))
    step(b, 19)  # Cancel selection; no use, tick or pay.
    assert b.consumed_count == 0 and b.diagnostic_players()[0, :, 5].sum() == 0
    b.reset_environments(ids([0]))
    hand(b, [5])
    hand(b, [(237, 0, 1), (238, 0, 1)], owner=1)
    b.start_environments(ids([0]))
    buy(b)
    step(b, 0)
    assert b.market_snapshot()[0, 10] == 1
    assert b.market_snapshot()[0, 9] == 0
    assert models(b, 1) == [237, 238]
    assert b.diagnostic_players()[0, 0, 5] == 1


@pytest.mark.parametrize("mirror_count", [1, 2, 3])
def test_sell_reflections_preserve_one_escrow_and_pay_current_source(mirror_count):
    b = game()
    hand(b, [4, 190] + [190] * mirror_count)
    hand(b, [190] * mirror_count, owner=1)
    load(b, cp=100)
    load(b, owner=1, cp=100)
    b.start_environments(ids([0]))
    sell(b)
    assert b.market_escrow_snapshot()[0, 2] == 190
    for _ in range(mirror_count):
        step(b, 1)
        step(b, 0)
    actor = int(b.episode_snapshot()[0, 2])
    source = int(b.market_observations()[0, 3])
    assert actor != source
    assert b.market_snapshot()[0, 6] == mirror_count
    assert sum(models(b, owner).count(190) for owner in (0, 1)) == 2 * mirror_count - mirror_count
    step(b, 0)
    assert b.market_snapshot()[0, 13] == 1
    assert b.market_snapshot()[0, 15] == PRICES[190]
    assert b.diagnostic_players()[0, actor, 2] == 100 - PRICES[190]
    assert b.diagnostic_players()[0, source, 2] == 100
    assert not b.market_escrow_snapshot().any()
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_sell_escrow_supermirror_cannot_itself_be_used_after_reflection():
    b = game()
    hand(b, [4, 190])
    hand(b, [190], owner=1)
    b.start_environments(ids([0]))
    sell(b)
    step(b, 1)
    step(b, 0)
    assert models(b) == []
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0]
    step(b, 0)
    assert models(b) == [190]
    assert b.consumed_count == 2


def test_reflected_buy_asks_current_source_not_original_owner_or_defender():
    b = game()
    hand(b, [5, 7])
    hand(b, [190, 6], owner=1)
    load(b, owner=1, cp=100)
    b.start_environments(ids([0]))
    buy(b)
    step(b, 1)
    step(b, 0)
    assert b.episode_snapshot()[0, 2] == 0
    step(b, 0)
    assert b.episode_snapshot()[0, 2:4].tolist() == [1, 6]
    assert b.market_observations()[0].tolist() == [1, 2, 4, 1, 0, 0, 7, PRICES[7], 0]
    step(b, 1)
    assert models(b, 1) == [6, 7] and models(b) == []
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("kind", [4, 5])
def test_only_supermirror_not_weapon_miracle_specials_numeric_armor_or_counters_can_answer(kind):
    b = game()
    hand(b, [kind, 7] if kind == 4 else [kind])
    hand(b, [190, 189, 127, 165, 233, 179], owner=1)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0, 1]
    assert b.pending_observations()[0, 3:6].tolist() == [0, 0, 6]


@pytest.mark.parametrize("bought", [False, True])
def test_purchased_miracle_is_unperformed_and_can_be_cast_later_not_used_by_transfer(bought):
    b = game(players=2)
    hand(b, [5])
    hand(b, [237], owner=1)
    b.start_environments(ids([0]))
    buy(b)
    step(b, 0)
    step(b, int(bought))
    assert b.miracle_use_count == 0
    recipient = 0 if bought else 1
    row = next(row for row in b.diagnostic_inventory()[0, recipient] if row[0])
    assert row[1:].tolist() == [237, 0, 0]


@pytest.mark.parametrize("cp,mp,hp", [(10, 5, 50), (2, 4, 50), (0, 0, 1)])
@pytest.mark.parametrize("kind", [4, 5])
def test_payment_waterfall_and_requested_credit_are_not_numeric_attack_damage(cp, mp, hp, kind):
    b = game()
    hand(b, [kind, 7] if kind == 4 else [kind])
    if kind == 5:
        hand(b, [7], owner=1)
    payer, seller = (1, 0) if kind == 4 else (0, 1)
    load(b, owner=payer, hp=hp, mp=mp, cp=cp)
    load(b, owner=seller, cp=98)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    step(b, 0)
    if kind == 5:
        step(b, 1)
    price = PRICES[7]
    paidcp, paidmp = min(cp, price), min(mp, max(0, price - cp))
    paid_hp = min(hp, max(0, price - cp - mp))
    assert b.market_snapshot()[0, 15:21].tolist() == [
        paidcp,
        paidmp,
        paid_hp,
        max(0, price - cp - mp - hp),
        2,
        price - 2,
    ]
    assert b.hp_damage == b.mp_spent == 0
    assert b.diagnostic_players()[0, payer, :3].tolist() == [hp - paid_hp, mp - paidmp, cp - paidcp]


@pytest.mark.parametrize("kind", [4, 5])
@pytest.mark.parametrize("model", [208, 112])
def test_received_sun_or_bow_participates_in_provisional_payment_death_order(kind, model):
    b = game()
    hand(b, [kind, model] if kind == 4 else [kind])
    if kind == 5:
        hand(b, [model], owner=1)
    payer = 1 if kind == 4 else 0
    load(b, owner=payer, hp=1, mp=0, cp=0)
    for owner in range(3):
        if owner != payer:
            load(b, owner=owner, mask=8)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    step(b, 0)
    if kind == 5:
        step(b, 1)
    if model == 208:
        assert b.revival_snapshot()[0, 4] == 1
        assert b.diagnostic_players()[0, payer, 0] == 10
    else:
        assert b.episode_snapshot()[0, 3] == 4
        assert b.diagnostic_players()[0, 0, 5] == 0
        for _ in range(2):
            step(b, 0)
        assert b.ascension_count == 1 and b.ascension_hp_damage == 60
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert not b.market_escrow_snapshot().any()


@pytest.mark.parametrize("oldest", [False, True])
def test_market_receipt_uses_explicit_local_overflow_policy_atomically(oldest):
    b = game(capacity=2, hand_limit=2, oldest_overflow=oldest)
    hand(b, [4, 7])
    hand(b, [6, 8], owner=1)
    b.start_environments(ids([0]))
    sell(b)
    if oldest:
        step(b, 0)
        assert models(b, 1) == [8, 7]
        assert b.market_snapshot()[0, 24] == b.overflow_count == 1
        assert b.automatic_gift_count == 0
    else:
        before = snapshot(b)
        with pytest.raises(ValueError, match="overflow"):
            step(b, 0)
        same(before, snapshot(b))


@pytest.mark.parametrize("failure", ["stale", "duplicate", "overflow", "hidden"])
def test_late_failure_preserves_escrow_payments_queue_rng_and_all_earlier_rows(failure):
    b, reference = game(size=2, seed=67), game(size=2, seed=67)
    for current in (b, reference):
        for env in range(2):
            hand(current, [4, 7], env=env)
            hand(current, [6] * (18 if env == 1 and failure == "overflow" else 1), env=env, owner=1)
            load(current, env=env, owner=1, mask=2)
        if failure == "hidden":
            hand(current, [(5, 4, 0), 7], env=1)
        current.start_environments(ids([0, 1]))
        for choice in (1, 2, 0):
            current.step(commands(current, [choice, choice]))
        if failure != "hidden":
            current.step(commands(current, [20, 20]))
    before = snapshot(b)
    rows = commands(b, [20, 20] if failure == "hidden" else [0, 0])
    if failure == "stale":
        rows[1, 2] += 1
    elif failure == "duplicate":
        rows[1] = rows[0]
    with pytest.raises(ValueError):
        b.step(rows)
    same(before, snapshot(b))
    choice = 20 if failure == "hidden" else 0
    step(b, choice)
    step(reference, choice)
    same(snapshot(b), snapshot(reference))


def test_return_preserves_original_disguise_identity_and_is_not_a_gift():
    b = game()
    hand(b, [5])
    hand(b, [(7, 6, 0)], owner=1)
    b.start_environments(ids([0]))
    buy(b)
    step(b, 0)
    assert b.market_escrow_snapshot()[0].tolist() == [1, 101, 7, 6, 0, 1]
    step(b, 0)
    assert b.diagnostic_inventory()[0, 1, 0].tolist() == [101, 7, 6, 0]
    assert b.gift_count == 0 and b.market_snapshot()[0, 14] == 1


@pytest.mark.parametrize("model", [4, 5])
def test_hidden_actual_trade_leader_does_not_change_reservation_or_target_masks(model):
    a, b = game(), game()
    for current, actual in ((a, model), (b, 9 - model)):
        hand(current, [(actual, model, 0), 7])
        current.start_environments(ids([0]))
        step(current, 1)
        if model == 4:
            step(current, 2)
            step(current, 0)
    for name in ("choice_masks", "actor_hands", "market_observations", "trade_observations"):
        np.testing.assert_array_equal(getattr(a, name)(), getattr(b, name)())
    before = snapshot(b)
    with pytest.raises(ValueError, match="hidden actual Sell/Buy"):
        step(b, 20)
    same(before, snapshot(b))


@pytest.mark.parametrize(
    "field", ["market_observation_fields", "market_snapshot_fields", "market_escrow_fields"]
)
def test_metadata_rejects_forged_market_layouts(field):
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    with pytest.raises(ValidationError):
        type(configured.metadata).model_validate(
            configured.metadata.model_dump() | {field: ("policy-leak",)}
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "kind", "price", "unregistered"])
def test_native_price_contract_requires_complete_unique_registered_model_coverage(mutation):
    rows = [list(row) for row in PLAN.trade.price_profiles]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = rows[0]
    elif mutation == "kind":
        rows[1][1] = 3
    elif mutation == "price":
        rows[0][2] = -1
    else:
        rows[-1][0] = 296
    with pytest.raises(ValueError):
        game(prices=rows)


def test_omission_preserves_unsupported_sell_buy_fixtures():
    b = game(prices=None)
    hand(b, [4, 5, 7])
    b.start_environments(ids([0]))
    assert not b.choice_masks()[0, 1:3].any()


def ticket(env, stream, seed=67, epoch=1, index=0):
    mask = 2**64 - 1
    v = (
        seed
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ stream
    )
    word = v
    for _ in range(index + 1):
        word = (word + 0x9E3779B97F4A7C15) & mask
        v = ((word ^ (word >> 30)) * 0xBF58476D1CE4E5B9) & mask
        v = ((v ^ (v >> 27)) * 0x94D049BB133111EB) & mask
    return v ^ (v >> 31)


@pytest.mark.parametrize("kind", [4, 5])
def test_fog_targets_are_native_uniform_enemies_and_ignore_requested_seat(kind):
    b = game(size=128, players=9)
    for env in range(128):
        hand(b, [kind, 7] if kind == 4 else [kind], env=env)
        load(b, env=env, mask=1)
    b.start_environments(ids(range(128)))
    for choice in (1, 2, 0, 20) if kind == 4 else (1, 20):
        b.step(commands(b, [choice] * 128))
    for env in range(128):
        assert b.market_observations()[env, 4] == 1 + ticket(env, 0xBA7C9045F12C7F99) % 8
    assert np.all(b.market_snapshot()[:, 5] == 1)
    assert not b.diagnostic_players()[:, 0, 5].any()


def test_offer_draws_include_all_unused_roles_exclude_performed_and_match_independent_rng():
    b = game(size=128)
    for env in range(128):
        hand(b, [5], env=env)
        hand(b, [6, (237, 0, 1), 7, 238, 208, 112], env=env, owner=1)
    b.start_environments(ids(range(128)))
    for choice in (1, 20, 0):
        b.step(commands(b, [choice] * 128))
    pool = [6, 7, 238, 208, 112]
    for env in range(128):
        assert b.market_observations()[env, 6] == pool[ticket(env, 0x24A19947B3916CF7) % 5]
    assert np.all(b.market_snapshot()[:, 21] == 1)


@pytest.mark.parametrize("kind", [4, 5])
def test_native_forced_market_does_not_create_learner_amount_or_purchase_loops(kind):
    b = game(size=128)
    for env in range(128):
        hand(b, [kind, 6] if kind == 4 else [kind], env=env)
        hand(b, [7], env=env, owner=1)
        hand(b, [7], env=env, owner=2)
    b.seed_confusion(ids(range(128)), ids([0] * 128), ids([1] * 128))
    b.start_environments(ids(range(128)))
    assert not b.policy_gradient_masks().any()
    b.step(commands(b, [0] * 128))
    started = np.flatnonzero(b.market_snapshot()[:, 3 if kind == 4 else 4])
    assert len(started) > 20
    for env in started:
        assert b.episode_snapshot()[env, 3] == 4
        assert b.policy_gradient_masks()[env, 0]  # Voluntary defensive responses.
        if kind == 4:
            assert b.market_escrow_snapshot()[env, 2] == 6
    b.step(commands(b, [0] * len(started), started))
    for env in started:
        assert b.episode_snapshot()[env, 3] in (1, 12)
        if kind == 5:
            assert b.market_snapshot()[env, 23] == 1
            assert b.market_snapshot()[env, 11] == ticket(int(env), 0x636920D871574E69) % 2
        assert b.diagnostic_players()[env, 0, 5] == 1


@pytest.mark.parametrize("escape", [0, 19])
def test_sale_edit_bound_always_retains_cancel_and_never_consumes_unconfirmed_items(escape):
    b = game()
    hand(b, [4, 7, 6])
    b.start_environments(ids([0]))
    step(b, 1)
    for i in range(64):
        step(b, 2 if i % 2 == 0 else 3)
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0, 19]
    step(b, escape)
    assert b.consumed_count == 0 and models(b) == [4, 7, 6]
    assert b.diagnostic_players()[0, 0, 5] == 0


@pytest.mark.parametrize("kind", [4, 5])
def test_decision_limit_with_escrow_retains_diagnostic_custody_until_reset(kind):
    limit = 4 if kind == 4 else 3
    b = game(max_decisions=limit)
    hand(b, [kind, 7] if kind == 4 else [kind])
    hand(b, [7], owner=1)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    if kind == 5:
        step(b, 0)
    assert b.episode_snapshot()[0, 3] == 13
    assert not b.market_observations().any() and not b.trade_observations().any()
    assert b.market_escrow_snapshot()[0, 5] == 1
    assert b.market_snapshot()[0, 13] == b.market_snapshot()[0, 14] == 0
    old = b.market_escrow_snapshot()
    assert not old.flags.writeable
    b.reset_environments(ids([0]))
    assert not b.market_snapshot().any() and not b.market_escrow_snapshot().any()
    assert old[0, 5] == 1


@pytest.mark.parametrize("kind", [1, 3])
def test_native_does_not_invent_all_origin_block_or_bounce(kind):
    specials = [list(row) for row in PLAN.combat.special_profiles]
    for row in specials:
        if row[0] == 190:
            row[1] = kind
    with pytest.raises(ValueError, match="special defense"):
        game(special_profiles=ids(specials))


def test_received_dream_uses_dedicated_native_disguise_stream_and_category_pool():
    b = game(size=256)
    for env in range(256):
        hand(b, [4, 7], env=env)
        load(b, env=env, owner=1, mask=2)
    b.start_environments(ids(range(256)))
    for choice in (1, 2, 0, 20, 0):
        b.step(commands(b, [choice] * 256))
    pool = [model for model, category in PLAN.inventory.profiles if category == 1]
    expected = []
    for env in range(256):
        disguised = ticket(env, 0x0801F2E2858EFC16) % 100 < 50
        fake = pool[ticket(env, 0x0801F2E2858EFC16, index=1) % len(pool)] if disguised else 0
        expected.append(fake)
    np.testing.assert_array_equal(b.diagnostic_inventory()[:, 1, 0, 2], expected)
    assert b.market_snapshot()[:, 22].sum() == sum(value != 0 for value in expected)
    assert b.gift_count == 0


def test_ready_buy_and_pre_response_views_do_not_peek_at_enemy_inventory():
    batches = [game() for _ in range(3)]
    for b, cards in zip(batches, ([], [7], [(237, 0, 1), 208, 112]), strict=True):
        hand(b, [5])
        hand(b, cards, owner=1)
        b.start_environments(ids([0]))
    for choice in (1, 20):
        for b in batches:
            for name in (
                "choice_masks",
                "actor_hands",
                "market_observations",
                "trade_observations",
            ):
                np.testing.assert_array_equal(getattr(batches[0], name)(), getattr(b, name)())
        for b in batches:
            step(b, choice)
    for b in batches:
        assert b.market_observations()[0, 6] == 0
        assert b.market_snapshot()[0, 21] == 0


@pytest.mark.parametrize("kind", [4, 5])
def test_market_policy_getters_are_owned_readonly_and_reset_clears_episode_state(kind):
    b = game()
    hand(b, [kind, 7] if kind == 4 else [kind])
    hand(b, [7], owner=1)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    if kind == 5:
        step(b, 0)
    old_observation, old_escrow, old_stats = (
        b.market_observations(),
        b.market_escrow_snapshot(),
        b.market_snapshot(),
    )
    for array in (old_observation, old_escrow, old_stats):
        assert not array.flags.writeable
    b.reset_environments(ids([0]))
    assert old_observation[0, 0] == old_escrow[0, 5] == 1
    assert not b.market_observations().any() and not b.market_snapshot().any()


@pytest.mark.parametrize("kind,bought", [(4, True), (5, True), (5, False)])
def test_trades_only_replace_used_leaders_not_transferred_or_refunded_parcels(kind, bought):
    b = game(refill_on_use=True, gift_profiles=ids([[191, 1]]))
    hand(b, [kind, 7] if kind == 4 else [kind])
    if kind == 5:
        hand(b, [7], owner=1)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    assert b.automatic_gift_count == 0
    step(b, 0)
    if kind == 5:
        assert b.automatic_gift_count == 0
        step(b, int(bought))
    assert b.automatic_gift_count == b.consumed_count == 1
    assert models(b) == ([7, 191] if kind == 5 and bought else [191])
    assert models(b, 1) == ([7] if kind == 4 or not bought else [])


def test_reflected_purchase_defers_both_players_replacement_gifts_until_settlement():
    b = game(refill_on_use=True, gift_profiles=ids([[191, 1]]))
    hand(b, [5, 7])
    hand(b, [190, 6], owner=1)
    b.start_environments(ids([0]))
    buy(b)
    for choice in (1, 0, 0):
        step(b, choice)
    assert b.episode_snapshot()[0, 2:4].tolist() == [1, 6]
    assert b.automatic_gift_count == 0
    assert b.acquisition_snapshot()[0, :, 0].tolist() == [1, 1, 0]
    step(b, 1)
    assert models(b) == [191] and models(b, 1) == [6, 7, 191]
    assert b.automatic_gift_count == b.consumed_count == 2
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("kind", [4, 5])
def test_newly_transferred_sun_only_produces_its_real_consumption_receipt(kind):
    b = game(refill_on_use=True, gift_profiles=ids([[191, 1]]))
    hand(b, [kind, 208] if kind == 4 else [kind])
    if kind == 5:
        hand(b, [208], owner=1)
    load(b, owner=1 if kind == 4 else 0, hp=1, mp=0, cp=0)
    b.start_environments(ids([0]))
    sell(b) if kind == 4 else buy(b)
    step(b, 0)
    if kind == 5:
        step(b, 1)
    assert b.revival_count == 1
    assert b.automatic_gift_count == b.consumed_count == 2
    assert models(b) == ([191] if kind == 4 else [191, 191])
    assert models(b, 1) == ([191] if kind == 4 else [])
