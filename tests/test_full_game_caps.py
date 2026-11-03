"""Client99 defaults, explicit legacy100, and joined resource-changing families."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import (
    PLAN,
    SEED,
    drain,
    hand,
    ids,
    profile,
    step,
    tickets,
)
from test_full_game_generated import (
    game as raw_game,
)

from godfield_bot.full_game import FullGameMetadata, create_development_full_game_batch

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
SAFE_SEED = next(s for s in range(100) if next(tickets(s, 0, 0)) % 100 >= 5)


def game(cap=99, **options):
    return raw_game(**(dict(resource_cap=cap, initial_hp=cap) | options))


def load(b, owner=0, hp=98, mp=98, cp=98, illness=0):
    b.seed_players(ids([0]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([0]))


def bounded(b):
    values = b.diagnostic_players()[:, :, :3]
    assert (values >= 0).all() and (values <= b.resource_cap).all()


def use(b):
    b.start_environments(ids([0]))
    step(b, [1])
    step(b, [0])
    bounded(b)


def attack(b):
    use(b)
    step(b, [20])


def factory(**options):
    return create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=1,
        capacity=18,
        **options,
    )


def test_factory_defaults99_and_legacy100_requires_an_explicit_option():
    c = factory()
    assert c.metadata.resource_cap == c.batch.resource_cap == 99
    assert not c.metadata.full_game_training_ready and not c.metadata.promotion_eligible
    old = factory(resource_cap=100, initial_hp=100, initial_mp=100, initial_cp=100)
    assert old.metadata.resource_cap == old.batch.resource_cap == 100
    assert old.metadata.ruleset_id == "integrated-full-game-development-v31"
    with pytest.raises(AttributeError):
        c.batch.resource_cap = 100
    with pytest.raises(ValueError):
        factory(initial_hp=100)


@pytest.mark.parametrize("cap", [0, 1, 98, 101, True, -1])
def test_unknown_caps_rejected_not_clipped_or_guessed(cap):
    with pytest.raises((ValueError, TypeError)):
        game(cap)


@pytest.mark.parametrize("column", [0, 1, 2])
def test_late_invalid_setup_row_is_atomic_at_selected_cap(column):
    b = game(size=2)
    old = b.diagnostic_players().copy()
    states = np.asarray([[99, 99, 99, 0], [99, 99, 99, 0]], dtype=np.int64)
    states[1, column] = 100
    with pytest.raises(ValueError):
        b.seed_players(ids([0, 1]), ids([0, 0]), states, ids([0, 0]))
    np.testing.assert_array_equal(old, b.diagnostic_players())


@pytest.mark.parametrize("field", ["initial_hp", "initial_mp", "initial_cp"])
def test_metadata_rejects100_at99_without_silent_migration(field):
    payload = factory().metadata.model_dump() | {field: 100}
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(payload)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("row", [r for r in PLAN.effect_profiles if r[1] in (1, 2, 5, 6, 7)])
def test_all_resource_utilities_share_the_selected_ceiling(cap, row):
    model, kind, value, cost = row
    b = game(cap, seed=SAFE_SEED)
    load(b)
    hand(b, [model])
    use(b)
    bounded(b)
    actual = b.diagnostic_players()[0, 0, :3].tolist()
    expected = [98, 98 - cost, 98]
    if kind == 1:
        expected[0] = min(cap, 98 + value)
    elif kind == 2:
        expected[1] = min(cap, 98 - cost + value)
    elif kind == 5:
        expected[2] = min(cap, 98 + value)
    elif kind == 6:
        expected[:2] = [cap, min(cap, 98 + value)]
    else:
        positive = next(tickets(SAFE_SEED, 0, 0x13198A2E03707344)) % 2 == 0
        assert bool(b.compound_utility_snapshot()[0, 6]) == positive
        expected[0] = min(cap, 98 + value) if positive else 98 - value
    assert actual == expected


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("kind", [1, 2, 5])
def test_full_resource_ordinary_utility_is_masked_at_the_selected_cap(cap, kind):
    model = next(r[0] for r in PLAN.effect_profiles if r[1] == kind)
    b = game(cap)
    load(b, hp=cap, mp=cap, cp=cap)
    hand(b, [model])
    b.start_environments(ids([0]))
    assert not b.choice_masks()[0, 1]


@pytest.mark.parametrize("cap", [99, 100])
def test_heaven_periodic_effect_does_not_restore_the_shared_100_cap(cap):
    b = game(cap, seed=SAFE_SEED)
    load(b, illness=4)
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.diagnostic_players()[0, 0, 0] == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("positive", [False, True])
def test_thump_thump_both_branches_respect_selected_cap(cap, positive):
    seed = next(
        s for s in range(100) if (next(tickets(s, 0, 0x13198A2E03707344)) % 2 == 0) == positive
    )
    row = next(r for r in PLAN.effect_profiles if r[1] == 7)
    b = game(cap, seed=seed)
    load(b)
    hand(b, [row[0]])
    use(b)
    assert b.diagnostic_players()[0, 0, 0] == (cap if positive else 98 - row[2])
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
def test_passive_revival_is_capped_even_for_a_raw_large_revive_profile(cap):
    b = game(cap, passive_profiles=ids([[208, 100]]), seed=SAFE_SEED)
    load(b, hp=1, illness=3)
    hand(b, [208])
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.diagnostic_players()[0, 0, 0] == b.revived_hp == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
def test_absorption_credits_current_source_only_up_to_selected_cap(cap):
    model = next(r[0] for r in PLAN.combat.attack_effect_profiles if r[1] == 1)
    b = game(cap)
    load(b)
    hand(b, [model])
    attack(b)
    step(b, [0])
    assert b.absorbed_hp == cap - 98
    assert b.diagnostic_players()[0, 0, 0] == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("kind,column", [(3, 1), (4, 2)])
def test_neptune_and_venus_credit_caps_survive_nested_response(cap, kind, column):
    ring = next(r[0] for r in PLAN.combat.defense_effect_profiles if r[1] == kind)
    b = game(cap)
    load(b, owner=1)
    hand(b, [35])
    hand(b, [ring], 1)
    attack(b)
    step(b, [1])
    step(b, [0])
    drain(b)
    assert b.diagnostic_players()[0, 1, column] == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("kind,column", [(5, 0), (6, 1), (7, 2), (8, 2)])
def test_guardian_resource_effects_use_the_selected_cap(cap, kind, column):
    row = next(r for r in PLAN.guardians.profiles if r[6] == kind)
    b = game(
        cap,
        guardian_profiles=ids([row]),
        seed=SEED,
        summon_profiles=None,
        phenomenon_profiles=None,
        fate_model_ids=None,
    )
    load(b, owner=1, hp=cap - 1, mp=cap - 1, cp=cap - 1)
    b.seed_guardians(ids([0]), ids([1]), ids([row[1] + 1]))
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.diagnostic_players()[0, 1, column] == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("resource", [0, 1, 2])
def test_devil_charity_respects_cap_for_all_three_resources(cap, resource):
    seed = next(s for s in range(100) if next(tickets(s, 0, 0x636920D871574E69)) % 3 == resource)
    b = game(
        cap,
        seed=seed,
        apocalypse_after_turns=1,
        prayer_gifts=True,
        devil_profiles=ids([[244, 100, 3, 10]]),
        gift_profiles=ids([[191, 1]]),
    )
    load(b)
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.diagnostic_players()[0, 0, resource] == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("kind", [7, 8])
def test_phenomenon_healing_and_gold_collection_use_selected_cap(cap, kind):
    row = next(r for r in PLAN.phenomena.profiles if r[1] == kind)
    b = game(cap, phenomenon_profiles=ids([row]))
    for seat in range(3):
        load(b, owner=seat)
    hand(b, [207])
    use(b)
    assert b.phenomenon_snapshot()[0, 13 if kind == 7 else 15] == (cap - 98 if kind == 7 else cap)
    if kind == 8:
        assert b.diagnostic_players()[0, :, 2].sum() == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("trade", [4, 5])
def test_sell_and_buy_credit_price_only_up_to_current_sellers_cap(cap, trade):
    b = game(cap)
    if trade == 4:
        load(b)
        hand(b, [4, 8])
    else:
        load(b, owner=1)
        hand(b, [5])
        hand(b, [8], 1)
    b.start_environments(ids([0]))
    step(b, [1])
    if trade == 4:
        step(b, [2])
        step(b, [0])
    step(b, [20])
    step(b, [0])
    if trade == 5:
        step(b, [1])
    assert b.diagnostic_players()[0, 0 if trade == 4 else 1, 2] == cap
    bounded(b)


@pytest.mark.parametrize("cap", [99, 100])
def test_exchange_menu_clips_and_disables_edits_at_selected_cap(cap):
    b = game(cap)
    load(b, hp=10, mp=98, cp=0)
    hand(b, [3])
    b.start_environments(ids([0]))
    step(b, [1])
    step(b, [1])
    assert not b.choice_masks()[0, 1]
    step(b, [0])
    assert b.diagnostic_players()[0, 0, :3].tolist() == [10 - (cap - 98), cap, 0]
    bounded(b)


def test_generated_exchange_does_not_sample_legacy100_allocations_at99():
    b = game(99, pool=(profile(3),), seed=SEED)
    load(b, owner=1, hp=99, mp=99, cp=99)
    b.seed_guardians(ids([0]), ids([1]), ids([9]))
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.diagnostic_players()[0, 1, :3].tolist() == [99, 99, 99]
    assert b.guardian_generated_snapshot()[0, 10] == 1


@pytest.mark.parametrize("wallet", [(1, 0, 0), (50, 20, 5), (99, 99, 99)])
def test_confused_exchange_uses_only99_bounded_allocations_and_no_policy_gradient(wallet):
    size, seed = 128, 67
    b = game(99, size=size, seed=seed)
    envs = ids(range(size))
    for env in range(size):
        hand(b, [3], env=env)
    b.seed_players(envs, envs * 0, ids([[*wallet, 0]] * size), envs * 0)
    b.seed_confusion(envs, envs * 0, ids([1] * size))
    b.start_environments(envs)
    assert not b.policy_gradient_masks().any()
    step(b, [0] * size)
    allocations = [
        (sum(wallet) - mp - cp, mp, cp)
        for mp in range(100)
        for cp in range(100)
        if 0 <= sum(wallet) - mp - cp <= 99
    ]
    for env in range(size):
        # The complete setup admits Exchange, Discard and Prayer, in that order.
        traded = next(tickets(seed, env, 0xC5D1B023286085F0)) % 3 == 0
        assert bool(b.trade_snapshot()[env, 3]) == traded
        expected = wallet
        if traded:
            expected = allocations[next(tickets(seed, env, 0xB8E1AFED6A267E96)) % len(allocations)]
        assert b.diagnostic_players()[env, 0, :3].tolist() == list(expected)
    bounded(b)


@pytest.mark.parametrize("row", PLAN.guardians.generated_profiles, ids=lambda r: str(r[1]))
@pytest.mark.parametrize("players", [2, 3, 9])
def test_all237_generated_routes_execute_within99_at_every_supported_roster(row, players):
    b = game(99, players=players, pool=(row,), seed=SEED)
    for seat in range(players):
        hand(b, [208], seat)
    b.seed_guardians(ids([0]), ids([1]), ids([row[0]]))
    b.start_environments(ids([0]))
    step(b, [0])
    drain(b)
    bounded(b)
    assert b.guardian_generated_execution_counts()[0, row[1] - 3] == 1
