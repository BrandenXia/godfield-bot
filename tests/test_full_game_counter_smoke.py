"""One-family probe accounting is reproducible and never enables training."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_counter_smoke import (
    FullGameCounterSmokeReport,
    run_full_game_counter_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_counter_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_probe_all_eight_rings_reproducible_and_not_training_ready():
    report = probe()
    assert report == probe()
    assert report.actions == 3072 and report.completed_turns == report.counter_resolutions == 512
    assert report.original_owner_ticks == 512 and report.other_owner_ticks == 0
    assert report.attack_hp_damage == 7040 and report.counter_hp_damage == 1920
    assert report.mp_gained == 1280 and report.cp_credited == 640
    assert report.consumed_cards == 1024 and report.final_queued_counters == 0
    assert (
        report.metadata_sha256 == "9099e104a19d1ff3b5248b7b23a63c18b01e84d20ed977fd16f6cce504eef7f0"
    )
    assert (
        report.diagnostic_replay_sha256
        == "41a29f765018a6a367b1aa5d687e08ec91068e80eb1bdc8249194b687e8b17ac"
    )
    assert (
        report.defense_effect_profile_sha256
        == "c984180f2027ee4d0899917582509378efd5657e7c94c050274ca7ebaab90044"
    )
    assert not report.teacher_or_reward_dataset_eligible and not report.local_training_eligible
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 8, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_preserve_zero_count_models_and_player_bounds(size, players):
    report = probe(batch_size=size, player_count=players)
    assert len(report.model_results) == 8 and report.counter_resolutions == size
    assert report == FullGameCounterSmokeReport.model_validate_json(report.model_dump_json())


@pytest.mark.parametrize("size", [True, 0, 4097, 2.5])
def test_invalid_batch_bounds_rejected_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"actions": 0},
        {"counter_resolutions": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"mp_gained": 0},
        {"cp_credited": 0},
        {"model_results": ((188, 4, 8),)},
        {"final_queued_counters": 1},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"counter_misses": 1},
        {"real_terminal_endings": 1},
        {"defense_effect_profile_sha256": "0" * 64},
        {"counter_hp_damage": 0},
        {"attack_hp_damage": 0},
    ],
)
def test_accounting_and_readiness_tampering_rejected(change):
    with pytest.raises(ValidationError):
        FullGameCounterSmokeReport.model_validate(probe(batch_size=8).model_dump() | change)


def test_cli_counter_family_command_and_bounds(monkeypatch):
    # Match the existing embedded CLI fixtures: do not leave a global logger
    # pointing at CliRunner's temporary stdout after its stream is closed.
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-counter-smoke", "--batch-size", "8"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["counter_resolutions"] == 8
    assert (
        runner.invoke(app, ["simulation", "full-game-counter-smoke", "--batch-size", "0"]).exit_code
        != 0
    )
