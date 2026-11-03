"""Repeatable native CP diagnostic with strict accounting and readiness gates."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_economy_smoke import (
    FullGameEconomySmokeReport,
    run_full_game_economy_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_economy_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_native_utility_accounting_and_hashes_not_trading_or_training():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (100,) * 7
    assert report.cp_utility_totals == (400, 2500, 2000, 200)
    assert report.actions == 1200
    assert report.completed_turns == report.original_owner_ticks == 700
    assert report.utilities == report.retained_miracle_uses == 500
    assert report.passes == 200 and report.mp_spent == 2700
    assert report.utility_cp_gain == 2500
    assert (
        report.metadata_sha256 == "de5f9d8cd9ae92bb2d4b925da1aac487476706ece495ce7d12cab07911999e65"
    )
    assert (
        report.diagnostic_replay_sha256
        == "f1782ba736b8b12f5c1d4ac8e2c09af24ca113767387dea1174a2948be0353c0"
    )
    assert not report.local_training_eligible and not report.full_game_training_ready
    assert not report.official_credit_cap_and_timing_verified and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 6, 7, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_and_rosters_round_trip(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameEconomySmokeReport.model_validate_json(report.model_dump_json())
    assert report.actions == size + report.utilities


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_bounds_fail_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"actions": 0},
        {"completed_turns": 0},
        {"original_owner_ticks": 0},
        {"cp_utility_fields": ("hidden-model",)},
        {"cp_utility_totals": (1,)},
        {"utilities": 0},
        {"passes": 0},
        {"retained_miracle_uses": 0},
        {"mp_spent": 0},
        {"utility_cp_gain": 0},
        {"consumed_cards": 1},
        {"ready_after_one_turn": 0},
        {"scenario_counts": (1,)},
        {"economy_profile_sha256": "0" * 64},
        {"hp_damage": 1},
        {"automatic_gifts": 1},
        {"other_owner_ticks": 1},
        {"real_terminal_endings": 1},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"official_credit_cap_and_timing_verified": True},
        {"official_fidelity_verified": True},
    ],
)
def test_accounting_and_all_fidelity_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameEconomySmokeReport.model_validate(probe(batch_size=7).model_dump() | change)


def test_cli_exposes_same_bounded_report_and_rejects_bad_input(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-economy-smoke", "--batch-size", "7"])
    assert result.exit_code == 0, result.output
    assert FullGameEconomySmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=7
    )
    assert (
        runner.invoke(app, ["simulation", "full-game-economy-smoke", "--players", "1"]).exit_code
        != 0
    )
