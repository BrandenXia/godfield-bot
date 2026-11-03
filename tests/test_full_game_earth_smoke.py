"""Weighted Earth direct/fallback diagnostics are not full-game training evidence."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_earth_smoke import FullGameEarthSmokeReport, run_full_game_earth_smoke

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_earth_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_native_tickets_and_receipts_are_reproducible_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.statistic_totals == (
        1045,
        1045,
        356,
        173,
        0,
        0,
        0,
        0,
        417,
        158,
        39,
        31,
        44,
        356,
        0,
        777,
        777,
        0,
        4044,
        20,
        40,
        31,
        0,
    )
    assert report.commands == 4930 and report.original_owner_ticks == 4096
    assert report.observed_models == 194
    assert (
        report.metadata_sha256 == "e83dc27e753d56aa0999a5b00832c0b51439b1ec5be61cd32d6f8a95dcbcedad"
    )
    assert (
        report.diagnostic_replay_sha256
        == "09613fafd3ea60206713e2a81aaa78d5eebbbe1c1d1ca3e2f3df9b047186b663"
    )
    assert not report.full_game_training_ready and not report.all_generated_outcomes_exercised


@pytest.mark.parametrize("size", [1, 2, 32, 256])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_and_rosters_keep_observed_counts(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameEarthSmokeReport.model_validate_json(report.model_dump_json())
    assert report.original_owner_ticks == size and report.statistic_totals[2] <= size


@pytest.mark.parametrize("size", [True, 0, -1, 4097])
def test_invalid_batch_bounds_reject_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"model_counts": ()},
        {"model_count_ids": ()},
        {"statistic_fields": ()},
        {"statistic_totals": ()},
        {"original_owner_ticks": 0},
        {"commands": 0},
        {"observed_models": 237},
        {"full_games_completed": 1},
        {"consumed_cards": 1},
        {"pending_families": 1},
        {"automatic_gifts": 1},
        {"mp_spent": 1},
        {"other_owner_ticks": 1},
        {"official_sampling_verified": True},
        {"all_generated_outcomes_exercised": True},
        {"teacher_or_reward_dataset_eligible": True},
        {"promotion_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"local_training_eligible": True},
    ],
)
def test_forged_scope_and_accounting_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameEarthSmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


@pytest.mark.parametrize("column", range(23))
def test_each_statistic_column_is_checked(column):
    payload = probe(batch_size=32).model_dump()
    stats = list(payload["statistic_totals"])
    stats[column] += 1 if column != 3 else 100
    payload["statistic_totals"] = stats
    with pytest.raises(ValidationError):
        FullGameEarthSmokeReport.model_validate(payload)


def test_miracle_histogram_cannot_be_inserted_into_earth_pool():
    payload = probe(batch_size=32).model_dump()
    counts = list(payload["model_counts"])
    counts[207] = 1
    payload["model_counts"] = counts
    with pytest.raises(ValidationError):
        FullGameEarthSmokeReport.model_validate(payload)


def test_cli_runs_offline_and_preserves_readiness_gates(monkeypatch):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(app, ["simulation", "full-game-earth-smoke", "--batch-size", "32"])
    assert result.exit_code == 0, result.output
    report = FullGameEarthSmokeReport.model_validate(json.loads(result.output))
    assert report.batch_size == 32 and not report.promotion_eligible
