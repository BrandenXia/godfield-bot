"""Observable pass-only witnesses, historical defaults, and unchanged policies."""

from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from godfield_bot.guardian_rollout import (  # noqa: E402
    GuardianRolloutArena,
    GuardianRolloutConfig,
    greedy_guardian_actions,
)
from godfield_bot.guardian_training import (  # noqa: E402
    GuardianArenaManifest,
    GuardianEvaluation,
    GuardianPlayStatistics,
    GuardianTrainingConfig,
    _GuardianPlayTracker,
    _runtime,
    evaluate_guardian_policy,
    load_guardian_checkpoint,
    train_guardian_candidate,
)

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def arena():
    game = GuardianRolloutArena(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        config=GuardianRolloutConfig(
            batch_size=2,
            max_turns=4,
            max_decisions=8,
            inventory_utilities=True,
            opening="cards-only",
        ),
    )
    game._native.reset_environments(np.array([0, 1], dtype=np.int64))
    return game


def test_mutual_forced_passes_measured_without_early_termination_or_action_changes():
    game = arena()
    tracker = _GuardianPlayTracker(2)
    before = game._native.resource_snapshot().copy()
    for tick in range(4):
        obs = game.observe()
        actions = greedy_guardian_actions(obs)
        np.testing.assert_array_equal(actions, [0, 0])
        tracker.observe(obs, actions, 0)
        np.testing.assert_array_equal(game._native.resource_snapshot(), before)
        transition = game.step(actions)
        tracker.finish(transition)
        stats = tracker.statistics()
        assert stats.ready_actions.forced_passes == (tick + 1) * 2
        assert stats.mutual_forced_pass_games == (0 if tick == 0 else 2)
        if tick < 3:
            assert not transition.truncated.any() and stats.mutual_forced_pass_truncations == 0
    assert stats.mutual_forced_pass_truncations == 2
    assert stats.learner_ready_actions.forced_passes == 4
    assert stats.decisions_by_phase == (8, 0, 0, 0, 0, 0)
    np.testing.assert_array_equal(game._native.resource_snapshot(), before)


def test_repeated_same_actor_and_inactive_rows_cannot_claim_mutual_stalls():
    obs = arena().observe()
    tracker = _GuardianPlayTracker(2)
    actions = np.array([0, 0], dtype=np.int64)
    tracker.observe(obs, actions, 0)
    tracker.observe(obs, actions, 0)
    assert tracker.statistics().mutual_forced_pass_games == 0
    inactive = replace(obs, active=np.array([False, False]), actors=np.array([-1, -1]))
    tracker.observe(inactive, np.array([-1, -1], dtype=np.int64), 0)
    assert tracker.statistics().ready_actions.forced_passes == 4


@pytest.mark.parametrize("interruption", ["voluntary-pass", "utility", "attack", "defense"])
def test_nonforced_decisions_break_the_consecutive_witness(interruption):
    tracker = _GuardianPlayTracker(2)
    obs = arena().observe()
    tracker.observe(obs, np.array([0, 0], dtype=np.int64), 0)
    hand, mask = obs.hand_features.copy(), obs.action_mask.copy()
    mask[:, 1] = True
    action, phase = 0, 0
    if interruption == "utility":
        hand[:, 0, 7], action = 0.1, 1
    elif interruption == "attack":
        hand[:, 0, 1], action = 0.1, 1
    elif interruption == "defense":
        phase, action = 1, 28
    changed = replace(
        obs,
        actors=np.array([1, 1]),
        phases=np.array([phase, phase]),
        hand_features=hand,
        action_mask=mask,
    )
    tracker.observe(changed, np.array([action, action], dtype=np.int64), 0)
    tracker.observe(replace(obs, actors=np.array([1, 1])), np.array([0, 0], dtype=np.int64), 0)
    assert tracker.statistics().mutual_forced_pass_games == 0
    if interruption == "utility":
        assert tracker.statistics().ready_actions.utilities == 2
    if interruption == "attack":
        assert tracker.statistics().ready_actions.attacks == 2


@pytest.mark.parametrize("utilities", [False, True])
def test_paired_evaluation_measures_ready_actions_and_preserves_calibration(utilities):
    cfg = GuardianRolloutConfig(
        batch_size=4, max_turns=8, max_decisions=32, inventory_utilities=utilities
    )
    with _runtime(67, 1):
        first = evaluate_guardian_policy(
            None, catalog_path=CATALOG, bible_path=BIBLE, config=cfg, games=8, seed=1000070
        )
        second = evaluate_guardian_policy(
            None, catalog_path=CATALOG, bible_path=BIBLE, config=cfg, games=8, seed=1000070
        )
    assert first == second and first.wins == first.losses
    stats = first.play_statistics
    assert stats is not None
    assert stats.ready_actions.total == stats.decisions_by_phase[0]
    assert stats.ready_actions.voluntary_passes == 0
    assert stats.mutual_forced_pass_truncations <= first.truncations
    assert stats.ready_actions.utilities == (first.utility_statistics.uses if utilities else 0)
    assert sum(stats.decisions_by_phase) <= 8 * 32
    for field in type(stats.ready_actions).model_fields:
        assert getattr(stats.ready_actions, field) == 2 * getattr(
            stats.learner_ready_actions, field
        )


@pytest.fixture
def checkpoint(tmp_path):
    config = GuardianTrainingConfig(
        arena=GuardianRolloutConfig(batch_size=4, max_turns=4, max_decisions=8),
        hidden_size=32,
        embedding_size=8,
        rollout_steps=4,
        teacher_updates=0,
        updates=1,
        ppo_epochs=1,
        environment_minibatch_size=2,
        evaluation_games=4,
        cpu_threads=1,
    )
    return train_guardian_candidate(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        checkpoint_root=tmp_path / "models",
        config=config,
    )


def test_new_checkpoint_diagnostics_and_historical_missing_values(checkpoint):
    directory, manifest = checkpoint
    loaded, _ = load_guardian_checkpoint(directory)
    assert loaded == manifest
    for evaluation in (
        loaded.evaluation_before,
        loaded.evaluation_after,
        loaded.evaluation_baseline,
    ):
        assert evaluation.play_statistics is not None
        raw = evaluation.model_dump(exclude={"play_statistics"})
        historical = GuardianEvaluation.model_validate(raw)
        assert historical.play_statistics is None
        assert (
            historical.wins == evaluation.wins and historical.truncations == evaluation.truncations
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("decisions_by_phase", (1, 0)),
        ("decisions_by_phase", (-1, 0, 0, 0, 0, 0)),
        ("decisions_by_phase", (5, 0, 0, 0, 0, 0)),
        ("decisions_by_phase", (4, 0, 1, 0, 0, 0)),
        ("mutual_forced_pass_games", 3),
        ("mutual_forced_pass_truncations", 3),
        ("learner_ready_actions", {"forced_passes": 10}),
    ],
)
def test_impossible_diagnostics_rejected(field, value):
    raw = {
        "decisions_by_phase": (4, 0, 0, 0, 0, 0),
        "ready_actions": {"forced_passes": 4},
        "learner_ready_actions": {"forced_passes": 2},
        "mutual_forced_pass_games": 2,
        "mutual_forced_pass_truncations": 2,
        field: value,
    }
    with pytest.raises(ValueError):
        GuardianPlayStatistics.model_validate(raw)


def test_evaluation_rejects_utility_accounting_mismatch(checkpoint):
    raw = checkpoint[1].evaluation_before.model_dump()
    raw["play_statistics"] = {
        "decisions_by_phase": (2, 0, 0, 0, 0, 0),
        "ready_actions": {"utilities": 2},
        "learner_ready_actions": {"utilities": 1},
        "mutual_forced_pass_games": 0,
        "mutual_forced_pass_truncations": 0,
    }
    with pytest.raises(ValueError, match="play diagnostics"):
        GuardianEvaluation.model_validate(raw)


def test_manifest_rejects_more_diagnostic_decisions_than_its_bound(checkpoint):
    raw = checkpoint[1].model_dump()
    raw["evaluation_before"]["play_statistics"]["decisions_by_phase"] = (0, 1000, 0, 0, 0, 0)
    raw["evaluation_before"]["play_statistics"]["ready_actions"] = {}
    raw["evaluation_before"]["play_statistics"]["learner_ready_actions"] = {}
    raw["evaluation_before"]["play_statistics"]["mutual_forced_pass_games"] = 0
    raw["evaluation_before"]["play_statistics"]["mutual_forced_pass_truncations"] = 0
    with pytest.raises(ValueError, match="bounded evaluation"):
        GuardianArenaManifest.model_validate(raw)
