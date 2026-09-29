"""The new local arena contract must not leak hands or confuse bounce with done."""

import json
from dataclasses import fields
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.guardian_rollout import (  # noqa: E402
    CONFIRM,
    FORGIVE,
    TARGET_START,
    GuardianRolloutArena,
    GuardianRolloutConfig,
    collect_guardian_rollout,
    greedy_guardian_actions,
)

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def arena(**kwargs):
    config = GuardianRolloutConfig(**{"batch_size": 4, "opening": "cards-only", **kwargs})
    return GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=config)


def assert_observations_equal(left, right):
    for field in fields(left):
        np.testing.assert_array_equal(getattr(left, field.name), getattr(right, field.name))


def empty(game):
    game._native.reset_environments(np.arange(game.config.batch_size, dtype=np.int64))


def deal(game, env, player, models, instance=100):
    count = len(models)
    game._native.deal_cards(
        ids([env] * count),
        ids([player] * count),
        ids(range(count)),
        ids(range(instance, instance + count)),
        ids(models),
    )


def test_projection_is_readonly_actor_only_and_matches_full_diagnostic():
    game = arena()
    projection = game._native.actor_hand_snapshot()
    inventory = game._native.inventory_snapshot()
    features = game._native.hand_feature_snapshot()
    assert native.GUARDIAN_ACTOR_HAND_SCHEMA_VERSION == 1
    assert projection.shape == (4, 18, 9)
    assert not projection.flags.writeable
    np.testing.assert_array_equal(projection[:, :, :3], inventory[:, 0])
    np.testing.assert_array_equal(projection[:, :, 3:], features[:, 0])
    before = projection.copy()
    game.step(ids([0] * 4))
    np.testing.assert_array_equal(projection, before)
    np.testing.assert_array_equal(game._native.actor_hand_snapshot()[:, :, :3], inventory[:, 1])


@pytest.mark.parametrize("players", [2, 3, 9])
def test_observation_shapes_relative_player_order_and_no_hidden_hands(players):
    game = arena(player_count=players)
    obs = game.observe()
    assert obs.global_features.shape == (4, 43)
    assert obs.players.shape == (4, 9, 8)
    assert obs.hand_features.shape == (4, 18, 7)
    assert obs.action_mask.shape == (4, 30)
    assert np.all(obs.hand_mask.sum(axis=1) == 9)
    assert np.all(obs.player_mask.sum(axis=1) == players)
    assert np.all(obs.actors == 0)
    for field in fields(obs):
        value = getattr(obs, field.name)
        assert not value.flags.writeable
        if value.dtype == np.float32:
            assert np.all(np.isfinite(value))
    # Add a card to someone else's hidden hand. No policy observation may change.
    game._native.deal_cards(ids([0]), ids([1]), ids([15]), ids([999]), ids([233]))
    assert_observations_equal(game.observe(), obs)
    # Once that seat acts, its own card may be visible; no raw seat identity is a feature.
    moved = game.step(ids([0] * 4)).observation
    assert np.all(moved.actors == 1)
    assert moved.hand_model_ids[0, 15] == 233
    assert moved.hand_mask[0, 15]
    assert np.all(moved.players[:, 0, :3] == obs.players[:, 1, :3])


def test_attack_choice_then_relative_target_spends_once_and_preserves_actor():
    game = arena(player_count=3)
    empty(game)
    deal(game, 0, 0, [211])  # Ice: 4 water ATK, 2MP, reusable
    first = game.step(ids([1, 0, 0, 0]))
    assert first.observation.phases[0] == 5
    assert first.observation.actors[0] == 0
    assert first.observation.hand_features[0, 0, 6] == 1
    assert first.observation.action_mask[0, TARGET_START : TARGET_START + 3].tolist() == [
        False,
        True,
        True,
    ]
    assert not np.any(first.observation.action_mask[0, :TARGET_START])
    assert game._native.resource_snapshot()[0, 0, 1] == 10
    assert game._native.miracle_cast_count == 0
    second = game.step(ids([TARGET_START + 2, 0, 0, 0]))
    assert second.observation.phases[0] == 1
    assert second.observation.actors[0] == 2
    assert game._native.resource_snapshot()[0, 0, 1] == 8
    assert game._native.actor_hand_snapshot()[0, 0, 1] == 0
    assert game._native.inventory_snapshot()[0, 0, 0, 1] == 211
    end = game.step(ids([FORGIVE, 0, 0, 0]))
    assert game._native.resource_snapshot()[0, 2, 0] == 36
    assert end.observation.actors[0] == 1
    assert game._native.miracle_cast_count == 1
    np.testing.assert_allclose(end.rewards.sum(axis=1), 0, atol=1e-7)


def test_bounce_is_active_and_target_rotation_redirects_to_original_caster():
    game = arena(batch_size=1, player_count=3)
    empty(game)
    deal(game, 0, 0, [211])
    deal(game, 0, 1, [234], instance=200)
    game.step(ids([1]))
    game.step(ids([TARGET_START + 1]))
    game.step(ids([1]))
    bounce = game.step(ids([CONFIRM]))
    assert not bounce.terminated[0] and not bounce.truncated[0]
    assert bounce.observation.phases[0] == 4
    assert bounce.observation.active[0] and bounce.observation.actors[0] == 1
    assert bounce.observation.hand_model_ids[0, 0] == 234
    assert bounce.observation.action_mask[0, 19:22].tolist() == [False, True, True]
    assert game._native.resource_snapshot()[0, 1, 1] == 10
    redirected = game.step(ids([TARGET_START + 2]))  # relative 2 from seat 1 -> seat 0
    assert redirected.observation.actors[0] == 0
    assert redirected.observation.hand_model_ids[0, 0] == 211
    assert game._native.resource_snapshot()[0, 1, 1] == 5
    game.step(ids([FORGIVE]))
    assert game.observe().actors[0] == 1
    assert game._native.resource_snapshot()[0, 0, 0] == 36


def test_invalid_action_mixed_batch_is_atomic():
    game = arena()
    baseline = game.observe()
    before = game._native.inventory_snapshot()
    with pytest.raises(ValueError, match="illegal"):
        game.step(ids([0, 0, CONFIRM, 0]))
    assert_observations_equal(game.observe(), baseline)
    np.testing.assert_array_equal(game._native.inventory_snapshot(), before)
    assert game._native.resolved_effect_count == 0


@pytest.mark.parametrize(
    "actions",
    [
        [0] * 4,
        np.zeros(4, dtype=np.int32),
        np.zeros((4, 1), dtype=np.int64),
        np.zeros(8, dtype=np.int64)[::2],
    ],
)
def test_invalid_input_dtype_shape_or_stride_is_rejected(actions):
    game = arena()
    before = game.observe()
    with pytest.raises(ValueError, match="contiguous int64"):
        game.step(actions)
    assert_observations_equal(game.observe(), before)


def test_finite_passing_and_explicit_reset_no_repeat_reward():
    game = arena(max_turns=2)
    game.step(ids([0] * 4))
    terminal = game.step(ids([0] * 4))
    assert np.all(terminal.truncated) and not np.any(terminal.terminated)
    assert game.finish_reasons() == ("turn_limit",) * 4
    assert not np.any(terminal.observation.active)
    assert not np.any(terminal.observation.action_mask)
    assert not np.any(terminal.observation.hand_model_ids)
    assert not np.any(game._native.actor_hand_snapshot())
    with pytest.raises(ValueError, match="finished"):
        game.step(ids([0] * 4))
    repeat = game.step(ids([-1] * 4))
    assert not np.any(repeat.newly_finished)
    assert not np.any(repeat.rewards)
    fresh = game.reset_done()
    assert np.all(fresh.active) and np.all(fresh.episode_ids == 1)
    assert np.all(fresh.decisions == 0)
    assert np.all(fresh.hand_mask.sum(axis=1) == 9)


def test_decision_limit_catches_attack_target_and_toggle_stalls():
    game = arena(batch_size=1, max_decisions=1)
    empty(game)
    deal(game, 0, 0, [211])
    stop = game.step(ids([1]))
    assert stop.truncated[0] and not stop.terminated[0]
    assert game.finish_reasons() == ("decision_limit",)
    assert not stop.observation.active[0]
    assert game._native.resource_snapshot()[0, 0, 1] == 10
    assert game._native.miracle_cast_count == 0
    assert game._native.turn_snapshot()[0, 0] == 0  # native forensics retained


def test_native_toggle_bound_and_selected_projection_are_retained():
    game = arena(batch_size=1, max_decisions=1000)
    empty(game)
    deal(game, 0, 0, [211])
    armor = game.metadata.native.armor_model_ids[0]
    # Native compatibility is authoritative; pick a legal armor model for this water attack.
    for model in game.metadata.native.armor_model_ids:
        candidate = arena(batch_size=1)
        empty(candidate)
        deal(candidate, 0, 0, [211])
        deal(candidate, 0, 1, [model], instance=200)
        candidate.step(ids([1]))
        obs = candidate.step(ids([TARGET_START + 1])).observation
        if obs.action_mask[0, 1]:
            armor = model
            break
    deal(game, 0, 1, [armor], instance=200)
    game.step(ids([1]))
    game.step(ids([TARGET_START + 1]))
    projection = game._native.actor_hand_snapshot()
    assert projection[0, 0, 1] == armor and projection[0, 0, 2] == 0
    selected = game.step(ids([1]))
    assert selected.observation.hand_features[0, 0, 6] == 1
    assert game._native.actor_hand_snapshot()[0, 0, 2] == 1
    assert projection[0, 0, 2] == 0  # copied, not a mutable alias
    for _ in range(63):
        stop = game.step(ids([1]))
    assert stop.truncated[0] and not stop.terminated[0]
    assert game._native.turn_snapshot()[0, 0] == 3
    assert game.finish_reasons() == ("defense_selection_limit",)
    assert not np.any(game._native.actor_hand_snapshot())


def test_dense_reward_exact_mp_cost_and_terminal_potential_correction():
    game = arena(batch_size=1, max_decisions=3, gamma=0.9, shaping_weight=0.1)
    empty(game)
    deal(game, 0, 0, [211])
    selected = game.step(ids([1]))
    np.testing.assert_array_equal(selected.rewards, [[0, 0]])
    cast = game.step(ids([TARGET_START + 1]))
    np.testing.assert_allclose(cast.rewards, [[-0.00009, 0.00009]], atol=1e-8)
    # At the absorbing truncation boundary no future resource value is bootstrapped.
    end = game.step(ids([FORGIVE]))
    assert end.truncated[0]
    np.testing.assert_allclose(end.rewards, [[0.0001, -0.0001]], atol=1e-8)
    discounted = selected.rewards + 0.9 * cast.rewards + 0.9**2 * end.rewards
    np.testing.assert_allclose(discounted, [[0, 0]], atol=1e-8)


def test_completed_rows_can_wait_while_other_environments_continue():
    game = arena(batch_size=2, initial_hp=4, shaping_weight=0)
    empty(game)
    deal(game, 0, 0, [211])
    game.step(ids([1, 0]))
    game.step(ids([TARGET_START + 1, 0]))
    end = game.step(ids([FORGIVE, 0]))
    assert end.terminated.tolist() == [True, False]
    ongoing = game.step(ids([-1, 0]))
    assert ongoing.observation.actors.tolist() == [-1, 0]
    assert ongoing.observation.decisions.tolist() == [3, 4]
    np.testing.assert_array_equal(ongoing.rewards[0], [0, 0])
    reset = game.reset_done()
    assert reset.episode_ids.tolist() == [1, 0]
    assert reset.decisions.tolist() == [0, 4]


def test_winner_takes_precedence_over_decision_boundary_and_rewards_zero_sum():
    game = arena(batch_size=1, initial_hp=4, max_decisions=3, shaping_weight=0)
    empty(game)
    deal(game, 0, 0, [211])
    game.step(ids([1]))
    game.step(ids([TARGET_START + 1]))
    end = game.step(ids([FORGIVE]))
    assert end.terminated[0] and not end.truncated[0]
    assert end.winners[0] == 0
    assert game.finish_reasons() == ("winner",)
    np.testing.assert_array_equal(end.rewards, [[1, -1]])
    assert end.acting_rewards[0] == -1


@pytest.mark.parametrize("players", [2, 3, 9])
def test_every_seeded_baseline_action_is_legal_and_bounded(players):
    game = arena(player_count=players, opening="mixed", max_turns=12, max_decisions=48)
    reward_total = np.zeros(4, dtype=np.float64)
    completions = 0
    for _ in range(150):
        observation = game.reset_done()
        actions = greedy_guardian_actions(observation)
        assert np.all(observation.action_mask[np.arange(4), actions])
        transition = game.step(actions)
        assert np.all(np.isfinite(transition.rewards))
        reward_total += transition.rewards.sum(axis=1)
        completions += np.count_nonzero(transition.newly_finished)
    np.testing.assert_allclose(reward_total, 0, atol=1e-5)
    assert completions >= 12


@pytest.mark.parametrize("opening", ["cards-only", "mars-opening", "mixed"])
def test_seeded_report_and_subset_reset_are_reproducible(opening):
    first, second = arena(opening=opening), arena(opening=opening)
    assert_observations_equal(first.observe(), second.observe())
    a = collect_guardian_rollout(first, steps=80)
    b = collect_guardian_rollout(second, steps=80)
    assert a == b
    assert a.transitions == 320
    assert sum(a.actions_by_index) == sum(a.decisions_by_phase) == 320
    assert not a.learning_performed
    # Per-row episode seeds do not depend on reset order or neighboring resets.
    first._reset(ids([0, 1]))
    second._reset(ids([1]))
    second._reset(ids([0]))
    assert_observations_equal(first.observe(), second.observe())


def test_collection_bound_validation_does_not_mutate_arena():
    game = arena()
    before = game.observe()
    for steps in (0, -1, True, 100001, 300000):
        with pytest.raises(ValueError, match="rollout requires"):
            collect_guardian_rollout(game, steps=steps)
    assert_observations_equal(before, game.observe())


def test_cli_is_offline_provisional_and_not_learning_or_live_promotion(monkeypatch):
    # Do not retain a logger bound to CliRunner's temporary stderr after this test.
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "guardian-rollout",
            "--batch-size",
            "2",
            "--steps",
            "20",
            "--max-turns",
            "4",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["transitions"] == 40 and not report["learning_performed"]
    assert report["metadata"]["local_rollout_ready"]
    assert not report["metadata"]["promotion_eligible"]
    assert not report["metadata"]["full_game_training_ready"]
    assert not report["metadata"]["live_checkpoint_compatible"]
    assert report["metadata"]["observation_schema_id"] != "11"
    invalid = CliRunner().invoke(app, ["simulation", "guardian-rollout", "--opening", "official"])
    assert invalid.exit_code == 1
