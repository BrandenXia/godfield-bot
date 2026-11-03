"""Native scripted utility ledger and explicit non-training report boundary."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_compound_utility_smoke import (
    FullGameCompoundUtilitySmokeReport,
    run_full_game_compound_utility_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_compound_utility_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_compound_utility_accounting_and_replay_are_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (64,) * 12
    assert report.utility_totals == (512, 8000, 128, 512, 128, 256, 123, 900, 133, 727)
    assert report.tear_outcome_counts == ((29, 35), (33, 31), (29, 35), (32, 32))
    assert report.actions == 1536
    assert report.completed_turns == report.utilities == report.original_owner_ticks == 768
    assert report.revivals == 96 and report.consumed_cards == 864
    assert report.utility_hp_damage == 855 and report.incoming_attack_hp_damage == 0
    assert report.final_actor_deaths == 113 and report.real_terminal_endings == 0
    assert (
        report.metadata_sha256 == "29f092cb03652f7a20dc76cc0a6e5f1a13da20e428c6392d2c5a4464b5015553"
    )
    assert (
        report.diagnostic_replay_sha256
        == "11320d237934889169ec6e5b5f2310b9af141e7697f11f318faf781b8904427a"
    )
    assert not report.full_game_training_ready and not report.promotion_eligible
    assert not report.probability_and_compound_timing_verified


@pytest.mark.parametrize("size", [1, 2, 5, 7, 8, 9, 10, 11, 12, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_scenario_batches_and_rosters_have_validated_accounting(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameCompoundUtilitySmokeReport.model_validate_json(
        report.model_dump_json()
    )
    assert report.completed_turns == size and report.limit_truncations == 0


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_bounds_fail_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"scenario_counts": (12,)},
        {"utility_totals": (1,)},
        {"tear_outcome_counts": ((1, 1),)},
        {"utility_fields": ("private-ticket",)},
        {"actions": 0},
        {"utilities": 0},
        {"completed_turns": 0},
        {"consumed_cards": 0},
        {"utility_hp_damage": 0},
        {"revivals": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"incoming_attack_hp_damage": 1},
        {"attack_turns": 1},
        {"retained_miracle_uses": 1},
        {"mp_spent": 1},
        {"automatic_gifts": 1},
        {"final_actor_deaths": 100},
        {"ready_after_one_turn": 0},
        {"real_terminal_endings": 1},
        {"limit_truncations": 1},
        {"compound_utility_profile_sha256": "0" * 64},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"probability_and_compound_timing_verified": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"hidden_ticket": 1},
    ],
)
def test_accounting_and_unverified_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameCompoundUtilitySmokeReport.model_validate(
            probe(batch_size=12).model_dump() | change
        )


def test_cli_reports_same_bounded_probe_and_rejects_invalid_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(
        app, ["simulation", "full-game-compound-utility-smoke", "--batch-size", "12"]
    )
    assert result.exit_code == 0, result.output
    assert FullGameCompoundUtilitySmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=12
    )
    assert (
        runner.invoke(
            app, ["simulation", "full-game-compound-utility-smoke", "--players", "10"]
        ).exit_code
        == 2
    )
