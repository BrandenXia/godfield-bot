"""Repeatable removal diagnostics with explicit non-training boundaries."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_removal_smoke import (
    FullGameRemovalSmokeReport,
    run_full_game_removal_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_removal_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_native_pool_and_sampling_accounting_not_full_game_validation():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (100,) * 6
    assert report.removal_totals == (300, 300, 400, 300, 200, 400, 1300, 500)
    assert report.actions == 2400 and report.completed_turns == 600
    assert report.removed_cards == 700 and report.consumed_cards == 600
    assert report.original_owner_ticks == report.removal_resolutions == 600
    assert (
        report.metadata_sha256 == "8922d83aa8e9c31a8cffe0999bb8b0e3beee7f8e18456f79518317ad0a085f94"
    )
    assert (
        report.diagnostic_replay_sha256
        == "3fb0abe1a64f96cb065d622091597ccf2074c939efe8fc59a694b145828ccb9e"
    )
    assert not report.teacher_or_reward_dataset_eligible and not report.local_training_eligible
    assert not report.full_game_training_ready and not report.promotion_eligible
    assert (
        not report.official_fidelity_verified and not report.official_sampling_and_timing_verified
    )


@pytest.mark.parametrize("size", [1, 2, 5, 6, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_and_maximum_roster_serialize_with_fixed_scenarios(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report.completed_turns == size
    assert report == FullGameRemovalSmokeReport.model_validate_json(report.model_dump_json())


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_bounds_fail_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"actions": 0},
        {"completed_turns": 0},
        {"removed_cards": 0},
        {"removal_resolutions": 0},
        {"consumed_cards": 0},
        {"original_owner_ticks": 0},
        {"ready_after_one_turn": 0},
        {"removal_fields": ("victim-ids",)},
        {"removal_totals": (1,)},
        {"scenario_counts": (6,)},
        {"removal_profile_sha256": "0" * 64},
        {"other_owner_ticks": 1},
        {"mp_spent": 10},
        {"hp_damage": 1},
        {"automatic_gifts": 1},
        {"retained_miracle_uses": 1},
        {"real_terminal_endings": 1},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"official_sampling_and_timing_verified": True},
        {"official_fidelity_verified": True},
    ],
)
def test_report_pins_accounting_and_all_readiness_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameRemovalSmokeReport.model_validate(probe(batch_size=6).model_dump() | change)


def test_cli_removal_diagnostic_and_invalid_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-removal-smoke", "--batch-size", "6"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["removed_cards"] == 7
    assert (
        runner.invoke(app, ["simulation", "full-game-removal-smoke", "--batch-size", "0"]).exit_code
        != 0
    )
