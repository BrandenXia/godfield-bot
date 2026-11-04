"""Real optimizer probes, deterministic repeats, visible limits and fail-closed reports."""

import json
from dataclasses import replace

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_observation import PATHS  # noqa: E402

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.full_game_diagnostics import NATIVE_VIEWS  # noqa: E402
from godfield_bot.full_game_learning_probe import (  # noqa: E402
    LAYOUTS,
    FullGameLearningProbeConfig,
    FullGameLearningProbeReport,
    run_full_game_learning_probe,
)
from godfield_bot.full_game_training import run_full_game_training  # noqa: E402


def test_complete_matrix_has_stable_disjoint_seeds_and_real_opponents():
    config = FullGameLearningProbeConfig()
    seeds = set()
    for players in range(2, 10):
        for layout in LAYOUTS:
            case = config.training_config(players, layout)
            assert len(case.teams) == players
            assert len(set(case.teams)) > 1 or layout == "solo"
            expected = set(range(case.seed, case.seed + 4))
            assert seeds.isdisjoint(expected)
            seeds.update(expected)
            subset = config.model_copy(update={"player_counts": (players,), "layouts": (layout,)})
            assert subset.training_config(players, layout) == case
    assert len(seeds) == 128
    for change in ({"player_counts": ()}, {"player_counts": (3, 2)}, {"layouts": ("solo", "solo")}):
        with pytest.raises(ValueError):
            FullGameLearningProbeConfig.model_validate(config.model_dump() | change)


@pytest.fixture(scope="module")
def probe():
    config = FullGameLearningProbeConfig(
        player_counts=(4,),
        layouts=("two-teams",),
        games_per_batch=2,
    )
    rng = torch.random.get_rng_state().clone()
    threads = torch.get_num_threads()
    progress = []
    report = run_full_game_learning_probe(**PATHS, config=config, on_case=progress.append)
    assert torch.equal(rng, torch.random.get_rng_state())
    assert torch.get_num_threads() == threads
    assert progress == list(report.cases)
    return report


def test_probe_uses_real_terminal_ppo_and_does_not_change_normal_training(probe):
    case = probe.cases[0]
    assert probe.passed and case.passed
    regular = run_full_game_training(**PATHS, config=case.training.config)
    assert case.training == regular.report
    for batch, update in zip(case.batches, case.training.updates, strict=True):
        assert batch.collection_sha256 == batch.repeated_collection_sha256
        assert sum(batch.terminal_phase_counts) == update.terminal_target_decisions > 0
        assert update.metrics.gradient_norm > 0 and update.actor_decisions > 0
        assert update.behavior_policy_sha256 != update.policy_sha256
        assert tuple(row.view for row in batch.native) == tuple(NATIVE_VIEWS)
        assert next(row for row in batch.native if row.view == "acquisition_snapshot").totals[1] > 0
    assert FullGameLearningProbeReport.model_validate_json(probe.model_dump_json()) == probe
    assert not probe.full_game_training_ready and not probe.promotion_eligible


@pytest.mark.parametrize(
    "change", ["case", "config", "phases", "native", "replay", "passed", "ready"]
)
def test_report_rejects_missing_cases_wrong_accounting_or_unearned_success(probe, change):
    bad = probe.model_dump()
    if change == "case":
        bad["cases"] = ()
    elif change == "config":
        bad["config"]["seed"] += 4
    elif change == "phases":
        bad["cases"][0]["batches"][0]["terminal_phase_counts"] = (0,) * 14
    elif change == "native":
        bad["cases"][0]["batches"][0]["native"] = ()
    elif change == "replay":
        bad["cases"][0]["batches"][0]["repeated_collection_sha256"] = "0" * 64
    elif change == "passed":
        bad["passed"] = False
    else:
        bad["full_game_training_ready"] = True
    with pytest.raises(ValueError):
        FullGameLearningProbeReport.model_validate(bad)


def test_cli_truncation_has_a_failed_probe_report_without_synthetic_learning(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-learning-probe",
            "--players",
            "2",
            "--layouts",
            "solo",
            "--games-per-batch",
            "1",
            "--max-decisions",
            "1",
        ],
    )
    assert result.exit_code == 1, result.output
    report = FullGameLearningProbeReport.model_validate(json.loads(result.stdout))
    assert not report.passed
    case = report.cases[0]
    assert len(case.batches) == 2
    for batch, update in zip(case.batches, case.training.updates, strict=True):
        assert update.outcomes[0].status == "decision-limit"
        assert update.metrics is None and update.accepted_decisions == 1
        assert update.terminal_target_decisions == update.actor_decisions == 0
        assert not any(batch.terminal_phase_counts)
        assert batch.collection_sha256 == batch.repeated_collection_sha256


def test_native_error_keeps_rejected_commands_and_does_not_train_or_continue(monkeypatch):
    import godfield_bot.full_game_learning_probe as module

    original = module.create_development_full_game_batch

    class RejectedNative:
        def __init__(self, native):
            self.native = native

        def __getattr__(self, name):
            return getattr(self.native, name)

        def step(self, commands):
            raise RuntimeError("injected native failure")

    def create(**options):
        configured = original(**options)
        return replace(configured, batch=RejectedNative(configured.batch))

    monkeypatch.setattr(module, "create_development_full_game_batch", create)
    report = run_full_game_learning_probe(
        **PATHS,
        config=FullGameLearningProbeConfig(
            player_counts=(2,), layouts=("solo",), games_per_batch=1
        ),
    )
    case = report.cases[0]
    assert not report.passed and len(case.batches) == len(case.training.updates) == 1
    update = case.training.updates[0]
    assert (
        update.collection_error == "injected native failure" and len(update.rejected_commands) == 1
    )
    assert update.outcomes[0].status == "collection-aborted" and update.accepted_decisions == 0
    assert update.metrics is None and update.behavior_policy_sha256 == update.policy_sha256
    assert case.batches[0].collection_sha256 == case.batches[0].repeated_collection_sha256


def test_probe_failure_restores_callers_torch_rng_and_thread_count(monkeypatch):
    import godfield_bot.full_game_learning_probe as module

    def fail(*args, **kwargs):
        torch.rand(7)
        raise RuntimeError("injected probe failure")

    monkeypatch.setattr(module, "_run_case", fail)
    rng, threads = torch.random.get_rng_state().clone(), torch.get_num_threads()
    with pytest.raises(RuntimeError, match="injected probe failure"):
        run_full_game_learning_probe(**PATHS)
    assert torch.equal(rng, torch.random.get_rng_state())
    assert torch.get_num_threads() == threads
