"""All-held startup counts are diagnostic evidence, not successful full games."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_acquisition_smoke import (
    FullGameAcquisitionSmokeReport,
    run_full_game_acquisition_smoke,
)

pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def probe(**options):
    return run_full_game_acquisition_smoke(catalog_path=CATALOG, bible_path=BIBLE, **options)


def test_default_complete_pool_startup_is_reproducible_and_not_full_game_success():
    report = probe()
    assert report == probe()
    assert report.automatic_gifts == 41472
    assert report.observed_model_count == 237
    assert report.unsupported_effect_draws == 16964
    assert report.initial_actors_without_implemented_choice == 12
    assert (
        report.diagnostic_replay_sha256
        == "822adf9d6574278726852b54b4f973e10246866c5ca71cc7cc38276f71ccfbc1"
    )
    assert (
        report.metadata_sha256 == "d3e9d0e23b83d7b8922c52b356fb4cb278e01512f2d1e308292d35e88fc8c1f9"
    )
    assert report.accepted_commands == report.games_completed == 0
    assert not report.local_training_eligible and not report.full_game_training_ready
    assert not report.teacher_or_reward_dataset_eligible and not report.promotion_eligible


@pytest.mark.parametrize("players", [2, 3, 9])
def test_small_draw_probe_records_absent_models_instead_of_claiming_full_coverage(players):
    report = probe(batch_size=1, player_count=players)
    assert report.automatic_gifts == players * 9
    assert report.observed_model_count <= players * 9
    assert len(report.model_distribution) == 237
    assert any(count == 0 for _, _, count in report.model_distribution)


def test_acquisition_cli_exposes_same_source_checked_report(monkeypatch):
    # Don't leave a closed CliRunner capture stream in process-global loggers.
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-acquisition-smoke",
            "--batch-size",
            "2",
            "--players",
            "3",
        ],
    )
    assert result.exit_code == 0, result.output
    report = FullGameAcquisitionSmokeReport.model_validate(json.loads(result.output))
    assert report == probe(batch_size=2, player_count=3)
    assert report.automatic_gifts == 54


@pytest.mark.parametrize(
    "changes",
    [
        {"automatic_gifts": 1},
        {"observed_model_count": 237},
        {"model_distribution": ()},
        {"gift_profile_sha256": "0" * 64},
        {"initial_actors_without_implemented_choice": 3},
        {"unsupported_effect_draws": 1000},
        {"accepted_commands": 1},
        {"games_completed": 1},
        {"total_weight": 295},
        {"full_game_training_ready": True},
        {"local_training_eligible": True},
        {"teacher_or_reward_dataset_eligible": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"overflow_policy": "player-choice"},
    ],
)
def test_report_fails_closed_on_broken_draw_accounting_and_forged_readiness(changes):
    with pytest.raises(ValidationError):
        FullGameAcquisitionSmokeReport.model_validate(
            {
                **probe(batch_size=2, player_count=3).model_dump(),
                **changes,
            }
        )


@pytest.mark.parametrize("batch_size", [True, 0, -1, 4097, 1.5])
def test_probe_rejects_out_of_bounds_batches_before_allocation(batch_size):
    with pytest.raises(ValueError):
        probe(batch_size=batch_size)
