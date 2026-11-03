"""Versioned bounded area probe, strict report validation and CLI parity."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_area_smoke import FullGameAreaSmokeReport, run_full_game_area_smoke

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_area_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_area_probe_is_deterministic_bounded_and_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (86, 86, 85, 85, 85, 85)
    assert report.area_totals == (512, 512, 1024, 1196, 1196, 0, 13632, 512)
    assert report.actions == 3499 and report.completed_turns == report.original_owner_ticks == 512
    assert report.attacks == report.resolved_attacks == 512
    assert report.area_hp_damage == 13632 and report.incoming_hp_damage == 15332
    assert report.recoil_hp_damage == 2380 and report.mp_spent == 3410
    assert report.consumed_cards == 682 and report.miracle_uses == 512
    assert report.family_enqueued == report.family_resolved == 1281 and report.counter_casts == 85
    assert (
        report.metadata_sha256 == "5c45c09197ab843f5511f7ad4ec3fe3a88bd71c1413cc6d179dfbcbd4cbbb984"
    )
    assert (
        report.diagnostic_replay_sha256
        == "4a9bafd47ebdd9a202a82710069786431946b79616f708d98b7b1132b6c7de0f"
    )
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 6, 7, 8, 31, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_scenario_batches_and_rosters_validate_strict_accounting(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameAreaSmokeReport.model_validate_json(report.model_dump_json())
    assert report.completed_turns == size and report.limit_truncations == 0


@pytest.mark.parametrize("seed", [0, 1, 68, 999, 2**64 - 1])
def test_other_seeds_remain_replayable(seed):
    assert probe(batch_size=32, seed=seed) == probe(batch_size=32, seed=seed)


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_size_fails_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"scenario_counts": (8,)},
        {"area_totals": (1,)},
        {"area_fields": ("private-ticket",)},
        {"actions": 0},
        {"completed_turns": 0},
        {"attacks": 0},
        {"resolved_attacks": 0},
        {"area_hp_damage": 0},
        {"incoming_hp_damage": 0},
        {"recoil_hp_damage": 0},
        {"mp_spent": 0},
        {"cost_waivers": 0},
        {"waived_mp": 0},
        {"consumed_cards": 0},
        {"miracle_uses": 0},
        {"counter_casts": 0},
        {"family_enqueued": 0},
        {"family_resolved": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"ready_after_one_turn": 0},
        {"real_terminal_endings": 1},
        {"automatic_gifts": 1},
        {"chance_casts": 1},
        {"limit_truncations": 1},
        {"area_profile_sha256": "0" * 64},
        {"queue_schema_version": 1},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_multiplayer_and_compound_timing_verified": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"hidden_ticket": 1},
    ],
)
def test_forged_counts_and_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameAreaSmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


def test_cli_runs_same_probe_and_rejects_bad_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-area-smoke", "--batch-size", "32"])
    assert result.exit_code == 0, result.output
    assert FullGameAreaSmokeReport.model_validate(json.loads(result.output)) == probe(batch_size=32)
    assert (
        runner.invoke(app, ["simulation", "full-game-area-smoke", "--players", "10"]).exit_code == 2
    )
