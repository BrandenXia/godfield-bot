"""Repeatable five-cause native diagnostic and fail-closed report boundary."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_revival_smoke import (
    FullGameRevivalSmokeReport,
    run_full_game_revival_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_revival_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_probe_pins_all_five_causes_with_native_not_forced_worsening():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (100, 100, 100, 100, 100)
    assert report.cause_counts == (100, 100, 100, 100, 5, 0)
    assert report.actions == 1600 and report.completed_turns == 500
    assert report.revivals == 405 and report.hp_granted == 4050
    assert report.consumed_cards == 705 and report.retained_miracle_uses == 100
    assert report.counter_resolutions == 100 and report.original_owner_ticks == 500
    assert (
        report.metadata_sha256 == "f432cf0f544c9a7810c04045e7fc55634269a66c51d944a55f5b114b627525a4"
    )
    assert (
        report.diagnostic_replay_sha256
        == "fdb534f251dfce0c78f0502d93016b7b30bff0e93aa196e2117fa0497f14bb32"
    )
    assert not report.local_training_eligible and not report.promotion_eligible
    assert not report.teacher_or_reward_dataset_eligible and not report.full_game_training_ready


@pytest.mark.parametrize("size", [1, 2, 4, 5, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_small_batches_partial_groups_and_maximum_roster_serialize(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report.completed_turns == size
    assert report == FullGameRevivalSmokeReport.model_validate_json(report.model_dump_json())


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_bounds_fail_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"actions": 0},
        {"revivals": 0},
        {"hp_granted": 0},
        {"consumed_cards": 0},
        {"retained_miracle_uses": 0},
        {"completed_turns": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"counter_resolutions": 0},
        {"final_queued_counters": 1},
        {"scenario_counts": (5, 0, 0, 0, 0)},
        {"cause_counts": (0, 0, 0, 0, 0)},
        {"cause_counts": (1, 1, 1, 1, 2)},
        {"cause_fields": ("x",)},
        {"passive_profile_sha256": "0" * 64},
        {"ready_after_one_turn": 0},
        {"real_terminal_endings": 1},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"teacher_or_reward_dataset_eligible": True},
    ],
)
def test_accounting_pins_and_readiness_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameRevivalSmokeReport.model_validate(probe(batch_size=5).model_dump() | change)


def test_cli_revival_command_and_invalid_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-revival-smoke", "--batch-size", "5"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["cause_counts"][:4] == [1, 1, 1, 1]
    assert (
        runner.invoke(app, ["simulation", "full-game-revival-smoke", "--batch-size", "0"]).exit_code
        != 0
    )
