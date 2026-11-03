"""Whole-selection provisional fizzles, custody, incoming effects and atomicity."""

import gc
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import hand, ids, load, step
from test_full_game_ineffective import enabled, state

from godfield_bot.full_game import (
    HIDDEN_COST_FIELDS,
    FullGameMetadata,
    create_development_full_game_batch,
)
from godfield_bot.full_game_episode_probe import (
    FullGameEpisodeProbeReport,
    run_full_game_episode_probe,
)
from godfield_bot.full_game_rewards import FullGameRewardAdapter

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
PATHS = dict(
    catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
    bible_path=Path("data/snapshots/2026-09-20/bible.json"),
)


def game(**options):
    return enabled(resolve_hidden_costs=True, **options)


@pytest.mark.parametrize("mp", [2, 5, 10, 29])
def test_hidden_expensive_chance_attack_fizzles_before_targets_rolls_or_effects(mp):
    b = game()
    hand(b, [(230, 211, 0)])  # Displayed fixed MP2; actual chance MP30.
    load(b, hp=40, mp=mp, cp=8, mask=0)
    b.start_environments(ids([0]))
    for choice in (1, 0, 20):
        step(b, [choice])
    assert b.hidden_cost_snapshot()[0].tolist() == [1, 0, 0, 1, 0, 1, 30, mp, 30 - mp]
    assert b.diagnostic_players()[0, 0].tolist() == [40, 0, 8, 0, 0, 1]
    assert b.mp_spent == mp and b.miracle_use_count == 1
    assert b.attack_count == b.chance_count == b.hp_damage == 0
    assert not b.hidden_targeting_snapshot().any()
    assert not b.ineffective_snapshot().any() and not b.cost_snapshot().any()
    assert b.diagnostic_inventory()[0, 0, 0, 1:4].tolist() == [230, 211, 1]
    assert b.episode_snapshot()[0, 2:5].tolist() == [1, 1, 1]


@pytest.mark.parametrize("mp", range(2, 7))
def test_hidden_expensive_utility_does_not_heal_cure_or_leave_a_free_partial_effect(mp):
    b = game()
    hand(b, [(235, 237, 0), 191])  # Healing MP7 disguised as cure MP2.
    load(b, hp=40, mp=mp, cp=8, mask=4)
    b.start_environments(ids([0]))
    step(b, [1])
    assert b.choice_masks()[0, 0]
    step(b, [0])
    assert b.hidden_cost_snapshot()[0].tolist() == [0, 1, 0, 1, 0, 1, 7, mp, 7 - mp]
    assert b.diagnostic_players()[0, 0].tolist() == [40, 0, 8, 0, 4, 1]
    assert b.utility_count == b.restored_count == 0
    assert b.diagnostic_inventory()[0, 0, :2, 1].tolist() == [191, 235]
    assert b.diagnostic_inventory()[0, 0, 1, 3] == 1


def test_fizzle_suppresses_an_affordable_weapon_and_nominal_true_waiver_too():
    b = game(refill_on_use=True)
    hand(b, [35, (215, 210, 0), 46, (217, 210, 0)])
    load(b, hp=40, mp=2, mask=0)
    b.start_environments(ids([0]))
    for choice in (1, 2, 3, 4, 0, 20):
        step(b, [choice])
    assert b.hidden_cost_snapshot()[0].tolist() == [1, 0, 0, 4, 2, 2, 7, 2, 5]
    assert b.mp_spent == 2 and b.attack_count == b.hp_damage == 0
    assert b.consumed_count == b.miracle_use_count == 2
    assert b.automatic_gift_count == 4
    assert b.cost_waiver_count == b.waived_mp == 0
    assert not b.cost_snapshot().any() and not b.ineffective_snapshot().any()


@pytest.mark.parametrize("actual_reducer", [130, 168, 178, 181])
def test_failed_defense_cannot_filter_block_counter_self_curse_or_redraw(actual_reducer):
    b = game()
    hand(b, [89])  # Fire8; displayed filter enables neutral-only Wall.
    hand(b, [189, 233, (actual_reducer, 163, 0)], owner=1)
    load(b, owner=0, hp=40, mp=0, mask=0)
    load(b, owner=1, hp=40, mp=0, mask=0)
    b.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 2, 3):
        step(b, [choice])
    assert b.choice_masks()[0, 0]  # Public cost is waived; actual cost is not.
    step(b, [0])
    assert b.hidden_cost_snapshot()[0].tolist() == [0, 0, 1, 3, 2, 1, 6, 0, 6]
    assert b.diagnostic_players()[0, 1].tolist() == [32, 0, 20, 0, 0, 0]
    assert b.diagnostic_players()[0, 0, 5] == 1
    assert b.hp_damage == 8
    assert b.filtered_attack_count == b.counter_count == b.self_curse_count == 0
    assert b.redraw_count == b.bounce_count == 0
    assert not b.ineffective_snapshot().any() and not b.cost_snapshot().any()
    assert b.diagnostic_inventory()[0, 1, 0, [1, 3]].tolist() == [233, 1]


def test_failed_defense_still_applies_incoming_curse_and_real_terminal_reward():
    c = create_development_full_game_batch(**PATHS, batch_size=1, capacity=18, initial_mp=0)
    b = c.batch
    hand(b, [92])  # Darkness10: positive damage finishes the target.
    hand(b, [189, 233, (130, 163, 0)], owner=1)
    b.start_environments(ids([0]))
    adapter = FullGameRewardAdapter(c)
    for choice in (1, 0, 20, 1, 2, 3, 0):
        row = b.episode_snapshot()[0]
        result = adapter.step(ids([[0, *row[:4], choice]]))
    assert b.hidden_cost_snapshot()[0, 2] == 1
    assert b.diagnostic_players()[0, 1, 0] == 0
    assert result.rewards.terminated.tolist() == [True]
    assert result.rewards.values[0, :2].tolist() == [1, -1]
    assert result.rewards.valid[0, :2].all()
    assert not adapter.poll().valid.any()


def test_fizzle_is_staged_and_rolled_back_when_another_row_is_rejected():
    b = game(size=2)
    for env in (0, 1):
        hand(b, [(235, 237, 0)], env=env)
        load(b, env=env, hp=40, mp=2, mask=4)
    b.start_environments(ids([0, 1]))
    step(b, [1, 1])
    before = state(b)
    with pytest.raises(ValueError):
        step(b, [0, 999])
    assert not b.hidden_cost_snapshot().any()
    for a, c in zip(before, state(b), strict=True):
        np.testing.assert_array_equal(a, c)
    assert b.mp_spent == b.miracle_use_count == 0
    step(b, [0, 0])
    assert b.hidden_cost_snapshot()[:, 1].tolist() == [1, 1]


def test_native_rule_requires_complete_components_and_readonly_diagnostics_survive_reset():
    from test_full_game_generated import game as raw

    assert not raw().resolve_hidden_costs
    with pytest.raises(ValueError, match="hidden cost fizzle requires"):
        raw(resolve_hidden_costs=True)
    b = game()
    hand(b, [(235, 237, 0)])
    load(b, mp=2, mask=4)
    b.start_environments(ids([0]))
    step(b, [1])
    step(b, [0])
    snapshot = b.hidden_cost_snapshot()
    assert not snapshot.flags.writeable and snapshot[0, 1] == 1
    b.reset_environments(ids([0]))
    assert not b.hidden_cost_snapshot().any()
    del b
    gc.collect()
    assert snapshot[0, 1] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"hidden_cost_policy": "forgive"},
        {"resolve_hidden_costs": False},
        {"resolve_hidden_costs": 1},
        {"hidden_cost_snapshot_fields": ()},
        {"hidden_cost_effects": "partial"},
        {"schema_version": 32},
    ],
)
def test_source_metadata_rejects_unapproved_policy_or_mismatched_flag(change):
    c = create_development_full_game_batch(**PATHS, batch_size=1, capacity=18)
    assert c.metadata.hidden_cost_snapshot_fields == HIDDEN_COST_FIELDS
    assert c.batch.resolve_hidden_costs and not c.metadata.full_game_training_ready
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(c.metadata.model_dump() | change)


@pytest.mark.parametrize("policy", ["strict-error", "fizzle-provisional"])
def test_full_episode_reproduction_records_the_rule_and_real_outcomes(policy):
    r = run_full_game_episode_probe(
        **PATHS,
        batch_size=32,
        player_count=2,
        seed=0,
        hidden_cost_policy=policy,
        terminal_rewards=True,
    )
    assert r.hidden_cost_policy == policy
    assert r.engine_errors == (1 if policy == "strict-error" else 0)
    assert r.games_completed == (31 if policy == "strict-error" else 32)
    assert not r.turn_limit_games and not r.decision_limit_games
    assert bool(sum(r.hidden_cost_totals)) == (policy == "fizzle-provisional")
    assert r.terminal_reward_valid_counts[:2] == (r.games_completed,) * 2
    assert r == FullGameEpisodeProbeReport.model_validate_json(r.model_dump_json())


@pytest.mark.parametrize(
    "change",
    [
        {"hidden_cost_fields": ()},
        {"hidden_cost_totals": (1, 0, 0, 1, 0, 1, 7, 2, 4)},
        {"hidden_cost_policy": "strict-error", "hidden_cost_totals": (1, 0, 0, 1, 0, 1, 7, 2, 5)},
    ],
)
def test_report_rejects_inconsistent_cost_diagnostics(change):
    r = run_full_game_episode_probe(**PATHS, batch_size=1, max_turns=1)
    with pytest.raises(ValidationError):
        FullGameEpisodeProbeReport.model_validate(r.model_dump() | change)
