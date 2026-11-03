"""Scripted targeting ledger, replay and explicit non-training scope."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_danger_smoke import (
    FullGameDangerSmokeReport,
    run_full_game_danger_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_danger_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_targeting_and_attraction_replay_is_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (64,) * 8
    assert report.danger_totals == (512, 128, 190, 384, 64, 157, 417, 13425)
    assert report.random_target_counts == ((16, 24, 24), (17, 25, 22))
    assert report.multi_holder_target_counts == (29, 35)
    assert report.actions == 1631 and report.normal_defense_responses == 95
    assert report.completed_turns == report.original_owner_ticks == 512
    assert report.attack_hp_damage == 16275 and report.automatic_hp_damage == 13425
    assert report.consumed_cards == 1041 and report.revivals == 145
    assert report.final_actor_deaths == report.final_other_deaths == 64
    assert report.real_terminal_endings == 0 and report.ready_after_one_turn == 512
    assert (
        report.metadata_sha256 == "4fb9d062f597c9fde70601994f08eabfb1bf1074f810435773ddfbd5dc5acc9f"
    )
    assert (
        report.diagnostic_replay_sha256
        == "010ee5679dcbe1f33d064470253fb74028810cec15db720f31eea8544efaf467"
    )
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 6, 7, 8, 9, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_scenario_batches_and_rosters_have_validated_accounting(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameDangerSmokeReport.model_validate_json(report.model_dump_json())
    assert report.completed_turns == size and report.limit_truncations == 0


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_bounds_fail_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"scenario_counts": (8,)},
        {"danger_totals": (1,)},
        {"danger_fields": ("private-holders",)},
        {"random_target_counts": ((1,), (1,))},
        {"multi_holder_target_counts": (1, 1)},
        {"actions": 0},
        {"completed_turns": 0},
        {"attacks": 0},
        {"resolved_attacks": 0},
        {"normal_defense_responses": 0},
        {"attack_hp_damage": 0},
        {"automatic_hp_damage": 0},
        {"consumed_cards": 0},
        {"revivals": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"final_actor_deaths": 0},
        {"final_other_deaths": 0},
        {"ready_after_one_turn": 0},
        {"real_terminal_endings": 1},
        {"automatic_gifts": 1},
        {"mp_spent": 1},
        {"chance_casts": 1},
        {"counter_casts": 1},
        {"limit_truncations": 1},
        {"danger_profile_sha256": "0" * 64},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_multiplayer_and_attraction_verified": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"hidden_ticket": 1},
    ],
)
def test_forged_accounting_and_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameDangerSmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


def test_cli_reports_same_probe_and_rejects_invalid_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-danger-smoke", "--batch-size", "32"])
    assert result.exit_code == 0, result.output
    assert FullGameDangerSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=32
    )
    assert (
        runner.invoke(app, ["simulation", "full-game-danger-smoke", "--players", "10"]).exit_code
        == 2
    )
