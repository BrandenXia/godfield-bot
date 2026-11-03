"""Bounded native waiver diagnostics are reproducible, never training evidence."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_cost_smoke import FullGameCostSmokeReport, run_full_game_cost_smoke

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_cost_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_native_zero_mp_waivers_accounting_and_replay_pins():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (40,) * 15
    assert report.cost_totals == (600, 3200, 200, 200, 200)
    assert report.actions == 2800
    assert report.completed_turns == report.original_owner_ticks == report.cost_waivers == 600
    assert report.utility_turns == report.attack_turns == report.defense_waiver_turns == 200
    assert report.waived_mp == 3200 and report.mp_spent == 0
    assert report.utility_cp_gain == report.hp_damage == 2000
    assert report.consumed_cards == 800 and report.retained_miracle_uses == 600
    assert (
        report.metadata_sha256 == "6a616c908823e82e19a57918cb9771c994fcc9c70853a2868dc8797b5d3a0992"
    )
    assert (
        report.diagnostic_replay_sha256
        == "1d3bec33d7acbd5c1a99b4b8954773226eb6695ac8befbf6ce4bd62adfd6578e"
    )
    assert not report.local_training_eligible and not report.full_game_training_ready
    assert not report.official_compound_timing_verified and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 5, 6, 10, 11, 14, 15, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_and_rosters_round_trip(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameCostSmokeReport.model_validate_json(report.model_dump_json())
    assert report.cost_waivers == size
    assert (
        report.actions
        == 3 * report.utility_turns + 5 * report.attack_turns + 6 * report.defense_waiver_turns
    )


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
        {"cost_fields": ("hidden-model",)},
        {"cost_totals": (1,)},
        {"utility_turns": 0},
        {"attack_turns": 0},
        {"defense_waiver_turns": 0},
        {"waived_mp": 0},
        {"cost_waivers": 0},
        {"retained_miracle_uses": 0},
        {"mp_spent": 1},
        {"utility_cp_gain": 0},
        {"consumed_cards": 0},
        {"ready_after_one_turn": 0},
        {"scenario_counts": (1,)},
        {"cost_profile_sha256": "0" * 64},
        {"hp_damage": 0},
        {"automatic_gifts": 1},
        {"other_owner_ticks": 1},
        {"real_terminal_endings": 1},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"official_compound_timing_verified": True},
        {"official_fidelity_verified": True},
        {"metadata_sha256": "not-a-hash"},
        {"diagnostic_replay_sha256": "not-a-hash"},
        {"ruleset_id": "integrated-full-game-development-v11"},
        {"hidden_victim_ids": [1]},
    ],
)
def test_accounting_and_all_fidelity_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameCostSmokeReport.model_validate(probe(batch_size=15).model_dump() | change)


def test_cli_exposes_same_bounded_report_and_rejects_bad_input(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-cost-smoke", "--batch-size", "15"])
    assert result.exit_code == 0, result.output
    assert FullGameCostSmokeReport.model_validate(json.loads(result.output)) == probe(batch_size=15)
    assert (
        runner.invoke(app, ["simulation", "full-game-cost-smoke", "--players", "1"]).exit_code != 0
    )
