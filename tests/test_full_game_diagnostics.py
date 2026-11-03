"""Diagnostics preserve evaluation behavior and separate choices from actual effects."""

import json

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load  # noqa: E402
from test_full_game_neural import biased  # noqa: E402
from test_full_game_observation import PATHS, configured  # noqa: E402
from test_full_game_training import trained_candidate as trained_candidate  # noqa: E402

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.full_game_diagnostics import (  # noqa: E402
    NATIVE_VIEWS,
    FullGameDiagnosticCollector,
    FullGameEvaluationDiagnostics,
)
from godfield_bot.full_game_evaluation import (  # noqa: E402
    FullGameFrozenEvaluation,
    evaluate_full_game_candidate,
)
from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyController,
)
from godfield_bot.full_game_rollout import full_game_policy_sha256  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def cpu_runtime():
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(2)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(67)
            yield
    finally:
        torch.set_num_threads(previous)


def test_diagnostics_preserve_frozen_results_and_account_for_each_native_faction(trained_candidate):
    _, _, _, path = trained_candidate
    plain = evaluate_full_game_candidate(
        path, **PATHS, greedy_baseline=True, seed=1230000, games_per_faction=2
    )
    detailed = evaluate_full_game_candidate(
        path, **PATHS, greedy_baseline=True, seed=1230000, games_per_faction=2, diagnostics=True
    )
    copied = detailed.model_dump()
    for f in copied["factions"]:
        f["diagnostics"] = None
    assert FullGameFrozenEvaluation.model_validate(copied) == plain
    for faction in detailed.factions:
        d = faction.diagnostics
        assert d.accepted_decisions == faction.accepted_decisions
        assert d.candidate_decisions < d.accepted_decisions
        assert sum(d.all_seat_phase_counts) == d.accepted_decisions
        assert tuple(row.view for row in d.native) == tuple(NATIVE_VIEWS)
        assert len(d.displayed_model_choice_counts) == 237
        assert not d.full_game_training_ready and not d.training_dataset_eligible
        for change in ["counts", "missing-native", "claimed-ready", "model-counts"]:
            bad = d.model_dump()
            if change == "counts":
                bad["phases"][0]["sampled_teacher_agreements"] += (
                    bad["phases"][0]["voluntary_decisions"] + 1
                )
            elif change == "missing-native":
                bad["native"] = bad["native"][:-1]
            elif change == "claimed-ready":
                bad["full_game_training_ready"] = True
            else:
                bad["displayed_model_choice_counts"] = (0,) * 237
            with pytest.raises(ValueError):
                FullGameEvaluationDiagnostics.model_validate(bad)


def test_forced_choices_have_no_teacher_accuracy_denominator_and_snapshots_are_exact():
    c = configured(player_count=2, max_turns=1, max_decisions=1)
    load(c.batch, hp=1, illness=1, mask=0)
    c.batch.seed_confusion(ids([0]), ids([0]), ids([1]))
    policy = FullGameActorCritic()
    controller = FullGamePolicyController(c, policy)
    collector = FullGameDiagnosticCollector(c.metadata, (0,))
    original = full_game_policy_sha256(policy)
    c.batch.start_environments(ids([0]))
    result = controller.step(ids([0]))
    memory, rng = controller.memory_snapshot(), controller.sampling_state()
    collector.observe(result, policy)
    assert torch.equal(memory, controller.memory_snapshot())
    assert torch.equal(rng, controller.sampling_state())
    assert full_game_policy_sha256(policy) == original
    report = collector.finish(c)
    assert report.candidate_forced_decisions == report.candidate_decisions == 1
    assert report.phases[0].voluntary_decisions == 0
    assert report.phases[0].teacher_probability_sum == 0
    for row in report.native:
        snapshot = getattr(c.batch, row.view)()
        np.testing.assert_array_equal(row.totals, snapshot.reshape(-1, len(row.fields)).sum(0))
    with pytest.raises(ValueError, match="ordered accepted"):
        collector.observe(result, policy)


def test_exchange_amount_choice_is_not_counted_as_a_card_and_truncation_stays_visible():
    c = configured(player_count=2, max_decisions=2, initial_hp=35, initial_cp=20)
    hand(c.batch, [3, 204])
    policy = FullGameActorCritic()
    controller = FullGamePolicyController(c, policy)
    collector = FullGameDiagnosticCollector(c.metadata, (0,))
    c.batch.start_environments(ids([0]))
    with pytest.raises(ValueError, match="all endings"):
        collector.finish(c)
    for action in (1, 8):
        biased(policy, action)
        result = controller.step(ids([0]), deterministic=True)
        collector.observe(result, policy)
    report = collector.finish(c)
    assert c.batch.episode_snapshot()[0, 5] == 4
    assert report.displayed_model_choice_counts[0] == 1  # Exchange reservation
    assert sum(report.displayed_model_choice_counts) == 1
    phase = next(row for row in report.phases if row.phase == 6)
    assert phase.candidate_choice_counts[8] == 1 and phase.displayed_slot_choices == 0
    assert not report.training_dataset_eligible


def test_attack_deselection_is_a_displayed_slot_choice_not_an_effect_execution():
    c = configured(player_count=2, max_decisions=2)
    hand(c.batch, [35])
    policy = FullGameActorCritic()
    biased(policy, 1)
    controller = FullGamePolicyController(c, policy)
    collector = FullGameDiagnosticCollector(c.metadata, (0,))
    c.batch.start_environments(ids([0]))
    for _ in range(2):
        collector.observe(controller.step(ids([0]), deterministic=True), policy)
    report = collector.finish(c)
    assert report.displayed_model_choice_counts[35 - 3] == 2
    phase = next(row for row in report.phases if row.phase == 2)
    assert phase.deselections == phase.displayed_slot_choices == 1
    assert sum(row.totals[0] for row in report.native if row.view == "attack_family_snapshot") == 0


def test_cli_diagnostics_remain_opt_in(trained_candidate, monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    *_, path = trained_candidate
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-evaluate",
            str(path),
            "--greedy-baseline",
            "--diagnostics",
            "--games-per-faction",
            "1",
            "--seed",
            "1240000",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert all(
        f["diagnostics"]["accepted_decisions"] == f["accepted_decisions"]
        for f in report["factions"]
    )
    assert not report["promotion_eligible"]
