"""Status visibility, defense limits, hit tickets, and caller-supplied enemies."""

import gc
from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.curse_decisions import (
    CURSE_DECISION_RULESET_ID,
    HIT_DECISION_FIELDS,
    STATUS_OBSERVATION_FIELDS,
    CurseDecisionMetadata,
    create_provisional_curse_decision_batch,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=2, players=3):
    return native.CurseDynamicsBatch(size, players)


def load(batch, *, env=0, player=0, hp=40, illness=0, mask=0):
    batch.load_players(ids([env]), ids([player]), ids([hp]), ids([illness]), ids([mask]))


def enemies(players, *, actor=0, candidates=None, rows=1):
    candidate_mask = np.zeros((rows, 9), dtype=np.int64)
    if candidates is None:
        candidates = [player for player in range(players) if player != actor]
    candidate_mask[:, candidates] = 1
    return candidate_mask


def state(batch):
    return (
        batch.snapshot(),
        batch.transition_snapshot(),
        (
            batch.illness_count,
            batch.curse_count,
            batch.cure_count,
            batch.tick_count,
            batch.death_count,
        ),
    )


def assert_same(batch, before):
    after = state(batch)
    np.testing.assert_array_equal(after[0], before[0])
    np.testing.assert_array_equal(after[1], before[1])
    assert after[2] == before[2]


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("mask", [0, 1, 2, 4, 8, 15])
def test_actor_first_rotation_explicit_visibility_and_padding(players, mask):
    batch = game(players=players)
    for seat in range(players):
        load(batch, player=seat, hp=seat * 10, illness=seat % 5, mask=mask)
    envs = ids([0] * players)
    actors = ids(range(players))
    before = state(batch)
    view = batch.status_observations(envs, actors)
    assert view.shape == (players, 9, 6)
    assert not view.flags.writeable
    for actor in range(players):
        for relative in range(9):
            if relative >= players:
                expected = [-1, 0, 0, 0, 0, 0]
            else:
                seat = (actor + relative) % players
                visible = relative == 0 or not mask & 1
                expected = [
                    seat,
                    1,
                    int(visible),
                    seat * 10 if visible else 0,
                    seat % 5 if visible else 0,
                    mask if visible else 0,
                ]
            np.testing.assert_array_equal(view[actor, relative], ids(expected))
    assert_same(batch, before)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_fog_view_is_independent_of_all_other_hp_status_and_liveness(players):
    rng = np.random.default_rng(67067 + players)
    batch = game(players=players)
    actor = players - 1
    load(batch, player=actor, hp=71, illness=3, mask=15)
    first = batch.status_observations(ids([0]), ids([actor]))
    for _ in range(100):
        for seat in range(players - 1):
            load(
                batch,
                player=seat,
                hp=int(rng.integers(0, 101)),
                illness=int(rng.integers(0, 5)),
                mask=int(rng.integers(0, 16)),
            )
        np.testing.assert_array_equal(batch.status_observations(ids([0]), ids([actor])), first)
    np.testing.assert_array_equal(first[0, 0], ids([actor, 1, 1, 71, 3, 15]))
    assert np.all(first[0, 1:players, 2:] == 0)


def test_zero_hp_is_not_confused_with_fog_unknown_and_cure_restores_visibility():
    batch = game()
    load(batch, player=1, hp=0, illness=4, mask=10)
    before_fog = batch.status_observations(ids([0]), ids([0]))
    assert before_fog[0, 1, 2] == 1 and before_fog[0, 1, 3] == 0
    batch.apply_curses(ids([0]), ids([0]), ids([1]))
    fog = batch.status_observations(ids([0]), ids([0]))
    np.testing.assert_array_equal(fog[0, 1], ids([1, 1, 0, 0, 0, 0]))
    batch.cure_players(ids([0]), ids([0]), ids([1]))
    np.testing.assert_array_equal(batch.status_observations(ids([0]), ids([0])), before_fog)
    assert fog[0, 1, 2] == 0  # Retained observations do not change on cure.


def test_status_view_excludes_tick_transition_and_lifetime_counter_information():
    batch = game()
    load(batch, mask=1)
    before = batch.status_observations(ids([0]), ids([0]))
    batch.finish_turns(ids([0]), ids([0]), ids([0]), ids([99]))
    assert batch.tick_count == 1 and batch.snapshot()[0, 0, 3] == 1
    assert batch.transition_snapshot()[0, 0, 0] == 5
    np.testing.assert_array_equal(batch.status_observations(ids([0]), ids([0])), before)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_flash_limits_all_masks_and_dead_defenders(players):
    batch = game(players=players)
    for mask in range(16):
        load(batch, player=players - 1, mask=mask)
        before = state(batch)
        actual = batch.defense_card_limits(
            ids([0, 0, 0]), ids([players - 1] * 3), ids([1, 18, 512])
        )
        np.testing.assert_array_equal(actual, ids([1, 1, 1] if mask & 4 else [1, 18, 512]))
        assert not actual.flags.writeable
        assert_same(batch, before)
    load(batch, player=players - 1, hp=0, mask=15)
    np.testing.assert_array_equal(
        batch.defense_card_limits(ids([0]), ids([players - 1]), ids([18])), ids([0])
    )


def test_dark_cloud_all_masks_rates_and_hundred_tickets_with_rng_requirement():
    batch = game()
    cases = [(rate, ticket) for rate in (1, 25, 50, 99, 100) for ticket in range(100)]
    for mask in range(16):
        load(batch, player=1, mask=mask)
        before = state(batch)
        hits = batch.hit_decisions(
            ids([0] * len(cases)),
            ids([1] * len(cases)),
            ids([rate for rate, _ in cases]),
            ids([ticket for _, ticket in cases]),
        )
        expected = [
            [int(bool(mask & 8) or ticket < rate), int(not mask & 8 and rate < 100)]
            for rate, ticket in cases
        ]
        np.testing.assert_array_equal(hits, ids(expected))
        assert not hits.flags.writeable
        assert_same(batch, before)


def test_dark_cloud_uses_the_actual_target_not_attacker_and_full_cure_restores_roll():
    batch = game()
    load(batch, mask=8)
    np.testing.assert_array_equal(
        batch.hit_decisions(ids([0]), ids([1]), ids([25]), ids([99])), ids([[0, 1]])
    )
    load(batch, player=1, mask=8)
    np.testing.assert_array_equal(
        batch.hit_decisions(ids([0]), ids([1]), ids([25]), ids([99])), ids([[1, 0]])
    )
    # Documented mild cure doesn't affect an isolated Dark Cloud.
    with pytest.raises(ValueError, match="does not affect"):
        batch.cure_players(ids([0]), ids([1]), ids([1]))
    batch.cure_players(ids([0]), ids([1]), ids([2]))
    np.testing.assert_array_equal(
        batch.hit_decisions(ids([0]), ids([1]), ids([25]), ids([99])), ids([[0, 1]])
    )


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("fog", [False, True])
def test_all_nonempty_enemy_subsets_intended_targets_and_rank_tickets(players, fog):
    actor = players // 2
    seats = [seat for seat in range(players) if seat != actor]
    batch = game(players=players)
    load(batch, player=actor, mask=1 if fog else 0)
    candidate_rows, intendeds, tickets, expected = [], [], [], []
    for subset in range(1, 1 << len(seats)):
        candidates = [seat for index, seat in enumerate(seats) if subset & (1 << index)]
        mask = enemies(players, actor=actor, candidates=candidates)[0]
        for intended in candidates:
            for ticket in range(len(candidates)):
                candidate_rows.append(mask)
                intendeds.append(intended)
                tickets.append(ticket)
                expected.append(candidates[ticket] if fog else intended)
    count = len(tickets)
    before = state(batch)
    result = batch.enemy_targets(
        ids([0] * count), ids([actor] * count), ids(intendeds), ids(candidate_rows), ids(tickets)
    )
    np.testing.assert_array_equal(result, ids(expected))
    assert not result.flags.writeable
    assert_same(batch, before)


def test_caller_enemy_mask_constrains_fog_targets_and_does_not_reinfer_teams():
    batch = game(players=9)
    load(batch, player=3, mask=1)
    selected = batch.enemy_targets(
        ids([0, 0, 0]),
        ids([3, 3, 3]),
        ids([6, 6, 6]),
        enemies(9, actor=3, candidates=[0, 6, 7], rows=3),
        ids([0, 1, 2]),
    )
    np.testing.assert_array_equal(selected, ids([0, 6, 7]))
    # No other living seat enters the candidate set automatically.
    batch.cure_players(ids([0]), ids([3]), ids([1]))
    np.testing.assert_array_equal(
        batch.enemy_targets(
            ids([0]), ids([3]), ids([6]), enemies(9, actor=3, candidates=[0, 6, 7]), ids([0])
        ),
        ids([6]),
    )


@pytest.mark.parametrize(
    "change",
    [
        "self",
        "dead",
        "padding",
        "nonbinary",
        "negative-mask",
        "empty",
        "intended",
        "negative-target",
        "padded-target",
        "negative-ticket",
        "large-ticket",
        "dead-actor",
        "short-rows",
        "wrong-width",
        "wrong-dtype",
    ],
)
def test_invalid_enemy_decisions_reject_later_rows_without_state_changes(change):
    batch = game()
    envs, actors = ids([0, 1]), ids([0, 0])
    intendeds, tickets = ids([1, 1]), ids([0, 0])
    mask = enemies(3, rows=2)
    if change == "self":
        mask[1, 0] = 1
    elif change == "dead":
        load(batch, env=1, player=2, hp=0)
    elif change == "padding":
        mask[1, 3] = 1
    elif change == "nonbinary":
        mask[1, 2] = 2
    elif change == "negative-mask":
        mask[1, 2] = -1
    elif change == "empty":
        mask[1] = 0
    elif change == "intended":
        mask[1, 1] = 0
    elif change == "negative-target":
        intendeds[1] = -1
    elif change == "padded-target":
        intendeds[1] = 3
    elif change == "negative-ticket":
        tickets[1] = -1
    elif change == "large-ticket":
        tickets[1] = 2
    elif change == "dead-actor":
        load(batch, env=1, hp=0)
    elif change == "short-rows":
        mask = mask[:1]
    elif change == "wrong-width":
        mask = mask[:, :8].copy()
    else:
        mask = mask.astype(np.float64)
    before = state(batch)
    with pytest.raises((ValueError, TypeError)):
        batch.enemy_targets(envs, actors, intendeds, mask, tickets)
    assert_same(batch, before)


@pytest.mark.parametrize(
    "method,change",
    [
        ("view", "environment"),
        ("view", "actor"),
        ("view", "length"),
        ("limits", "zero"),
        ("limits", "over-capacity"),
        ("limits", "length"),
        ("hits", "rate-zero"),
        ("hits", "rate-over-100"),
        ("hits", "ticket-negative"),
        ("hits", "ticket-100"),
        ("hits", "dead"),
        ("hits", "length"),
    ],
)
def test_invalid_status_limit_and_hit_queries_are_nonmutating(method, change):
    batch = game()
    envs, actors = ids([0, 1]), ids([0, 0])
    values = ids([18, 18]) if method == "limits" else ids([50, 50])
    tickets = ids([99, 99])
    if change == "environment":
        envs[1] = 2
    elif change == "actor":
        actors[1] = 3
    elif change in ("zero", "rate-zero"):
        values[1] = 0
    elif change == "over-capacity":
        values[1] = 513
    elif change == "rate-over-100":
        values[1] = 101
    elif change == "ticket-negative":
        tickets[1] = -1
    elif change == "ticket-100":
        tickets[1] = 100
    elif change == "dead":
        load(batch, env=1, hp=0)
    elif change == "length":
        actors = actors[:1]
    before = state(batch)
    with pytest.raises(ValueError):
        if method == "view":
            batch.status_observations(envs, actors)
        elif method == "limits":
            batch.defense_card_limits(envs, actors, values)
        else:
            batch.hit_decisions(envs, actors, values, tickets)
    assert_same(batch, before)


def test_empty_and_duplicate_readonly_query_rows_and_output_lifetime():
    batch = game()
    before = state(batch)
    assert batch.status_observations(ids([]), ids([])).shape == (0, 9, 6)
    assert batch.defense_card_limits(ids([]), ids([]), ids([])).shape == (0,)
    assert batch.hit_decisions(*[ids([]) for _ in range(4)]).shape == (0, 2)
    assert batch.enemy_targets(
        ids([]), ids([]), ids([]), np.zeros((0, 9), dtype=np.int64), ids([])
    ).shape == (0,)
    view = batch.status_observations(ids([0, 0]), ids([0, 0]))
    limits = batch.defense_card_limits(ids([0, 0]), ids([0, 0]), ids([18, 18]))
    hits = batch.hit_decisions(ids([0, 0]), ids([1, 1]), ids([25, 25]), ids([0, 0]))
    selected = batch.enemy_targets(
        ids([0, 0]), ids([0, 0]), ids([1, 1]), enemies(3, rows=2), ids([0, 0])
    )
    assert_same(batch, before)
    batch.apply_curses(ids([0]), ids([0]), ids([1]))
    assert view[0, 1, 2] == 1
    del batch
    gc.collect()
    np.testing.assert_array_equal(view[0], view[1])
    np.testing.assert_array_equal(limits, ids([18, 18]))
    np.testing.assert_array_equal(hits, ids([[1, 1], [1, 1]]))
    np.testing.assert_array_equal(selected, ids([1, 1]))
    assert all(not value.flags.writeable for value in (view, limits, hits, selected))


@pytest.mark.parametrize(
    "method,rows",
    [("view", 222_223), ("limits", 1_000_001), ("hits", 1_000_001), ("targets", 1_000_001)],
)
def test_query_allocation_is_bounded_before_processing_inputs(method, rows):
    batch = game()
    envs, actors = np.zeros(rows, dtype=np.int64), ids([])
    before = state(batch)
    with pytest.raises(ValueError, match="capacity"):
        if method == "view":
            batch.status_observations(envs, actors)
        elif method == "limits":
            batch.defense_card_limits(envs, actors, ids([]))
        elif method == "hits":
            batch.hit_decisions(envs, actors, ids([]), ids([]))
        else:
            batch.enemy_targets(envs, actors, ids([]), np.zeros((0, 9), dtype=np.int64), ids([]))
    assert_same(batch, before)


def configured():
    return create_provisional_curse_decision_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, player_count=9
    )


def test_factory_is_source_pinned_shared_state_and_explicitly_not_full_game_ready():
    result = configured()
    metadata = result.metadata
    assert metadata.ruleset_id == CURSE_DECISION_RULESET_ID
    assert metadata.status_observation_fields == STATUS_OBSERVATION_FIELDS
    assert metadata.hit_decision_fields == HIT_DECISION_FIELDS
    assert metadata.status_projection_implemented
    assert not metadata.complete_policy_projection_implemented
    assert not metadata.complete_team_rules_implemented
    assert not metadata.dream_disguise_implemented
    assert not metadata.item_legality_and_costs_implemented
    assert not metadata.local_training_eligible and not metadata.full_game_training_ready
    assert not metadata.official_fidelity_verified and not metadata.promotion_eligible
    assert not metadata.action_observation_checkpoint_compatible
    assert not metadata.queries_mutate_state
    assert CurseDecisionMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    result.batch.apply_curses(ids([0]), ids([0]), ids([1]))
    assert result.batch.status_observations(ids([0]), ids([0]))[0, 1, 2] == 0
    result.batch.cure_players(ids([0]), ids([0]), ids([1]))
    assert result.batch.status_observations(ids([0]), ids([0]))[0, 1, 2] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("status_observation_fields", ("seat",)),
        ("hit_decision_fields", ("hit",)),
        ("observation_exclusions", ("inventory",)),
        ("padded_players", 8),
        ("fog_visibility", "show-all"),
        ("queries_mutate_state", True),
        ("complete_team_rules_implemented", True),
        ("complete_policy_projection_implemented", True),
        ("local_training_eligible", True),
        ("full_game_training_ready", True),
        ("official_fidelity_verified", True),
        ("promotion_eligible", True),
        ("action_observation_checkpoint_compatible", True),
    ],
)
def test_projection_drift_and_false_fidelity_training_claims_are_rejected(field, value):
    raw = configured().metadata.model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        CurseDecisionMetadata.model_validate(raw)


def test_old_native_decision_contract_is_rejected(monkeypatch):
    monkeypatch.setattr(native, "CURSE_DECISION_SCHEMA_VERSION", 0)
    with pytest.raises(ProvisionalRuleUnavailableError, match="decision contract"):
        configured()
