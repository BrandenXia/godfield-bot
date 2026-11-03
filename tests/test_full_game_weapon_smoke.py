"""Strict native diagnostic accounting, replay identity and readiness boundary."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_weapon_smoke import (
    FullGameWeaponSmokeReport,
    run_full_game_weapon_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_weapon_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_native_complex_weapon_turns_and_pinned_replay_are_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (60,) * 12
    assert report.weapon_totals == (180, 1200, 240, 180, 1440, 300, 540, 60)
    assert report.actions == 3720
    assert report.completed_turns == report.original_owner_ticks == 720
    assert report.incoming_hp_damage == 6720 and report.recoil_hp_damage == 1440
    assert report.mp_spent == 1200 and report.consumed_cards == 1080
    assert report.retained_miracle_uses == report.waived_mp == 120
    assert report.cost_waivers == report.counters == report.reflections == 60
    assert (
        report.metadata_sha256 == "f6ac8fb467ac749ea8331d9795ed40720234cb7737ef00426224e2fcf6809481"
    )
    assert (
        report.diagnostic_replay_sha256
        == "783087cad4d2aaacb8de08e7bd7245380bdff0c0212f15c303476ebd25e08903"
    )
    assert not report.local_training_eligible and not report.full_game_training_ready
    assert not report.compound_rules_verified and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 3, 6, 7, 8, 9, 11, 12, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_and_rosters_have_exact_validated_accounting(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameWeaponSmokeReport.model_validate_json(report.model_dump_json())
    assert report.completed_turns == size and report.limit_truncations == 0


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
        {"scenario_counts": (1,)},
        {"weapon_fields": ("true-model",)},
        {"weapon_totals": (1,)},
        {"incoming_hp_damage": 0},
        {"recoil_hp_damage": 0},
        {"mp_spent": 0},
        {"consumed_cards": 0},
        {"retained_miracle_uses": 0},
        {"cost_waivers": 0},
        {"waived_mp": 0},
        {"counters": 0},
        {"reflections": 0},
        {"real_terminal_endings": 1},
        {"automatic_gifts": 1},
        {"other_owner_ticks": 1},
        {"limit_truncations": 1},
        {"weapon_profile_sha256": "0" * 64},
        {"metadata_sha256": "invalid"},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"compound_rules_verified": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"hidden_sequence_target": 1},
    ],
)
def test_accounting_and_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameWeaponSmokeReport.model_validate(probe(batch_size=12).model_dump() | change)


def test_cli_reports_same_bounded_probe_and_rejects_invalid_roster(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-weapon-smoke", "--batch-size", "12"])
    assert result.exit_code == 0, result.output
    assert FullGameWeaponSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=12
    )
    assert (
        runner.invoke(app, ["simulation", "full-game-weapon-smoke", "--players", "1"]).exit_code
        != 0
    )
