"""Bounded family replay report with strict non-training/promotion gates."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_attack_family_smoke import (
    FullGameAttackFamilySmokeReport,
    run_full_game_attack_family_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_attack_family_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_family_probe_is_deterministic_bounded_and_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (86, 86, 85, 85, 85, 85)
    assert report.family_totals == (
        1449,
        1364,
        1364,
        85,
        0,
        1023,
        511,
        511,
        937,
        937,
        0,
        0,
        24455,
        0,
        0,
        0,
    )
    assert report.actions == 2900 and report.completed_turns == report.original_owner_ticks == 512
    assert report.attacks == report.resolved_attacks == 427
    assert report.attack_hp_damage == 24882 and report.ascension_hp_damage == 24455
    assert report.revivals == 86 and report.redraws == 85 and report.redrawn_cards == 170
    assert report.consumed_cards == 1194
    assert (
        report.metadata_sha256 == "d67ff24ca4d8290f2867b7e224317ea0d8cb4892ad3e0fa8f86d4f813500f4be"
    )
    assert (
        report.diagnostic_replay_sha256
        == "bbe7b1b92170c5ea671bc9c1ddb5f9438562100fca80b341912e9b72eac2ff49"
    )
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 6, 7, 8, 31, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_scenario_batches_and_rosters_validate_strict_accounting(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameAttackFamilySmokeReport.model_validate_json(report.model_dump_json())
    assert report.completed_turns == size and report.limit_truncations == 0


@pytest.mark.parametrize("seed", [0, 1, 68, 999, 2**64 - 1])
def test_other_redraw_seeds_remain_replayable(seed):
    assert probe(batch_size=32, seed=seed) == probe(batch_size=32, seed=seed)


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_size_fails_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"scenario_counts": (8,)},
        {"family_totals": (1,)},
        {"family_fields": ("private-ticket",)},
        {"actions": 0},
        {"completed_turns": 0},
        {"attacks": 0},
        {"resolved_attacks": 0},
        {"attack_hp_damage": 0},
        {"ascension_hp_damage": 0},
        {"consumed_cards": 0},
        {"revivals": 0},
        {"redraws": 0},
        {"redrawn_cards": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"ready_after_one_turn": 0},
        {"real_terminal_endings": 0},
        {"automatic_gifts": 1},
        {"mp_spent": 1},
        {"chance_casts": 1},
        {"counter_casts": 1},
        {"limit_truncations": 1},
        {"ascension_profile_sha256": "0" * 64},
        {"queue_schema_version": 9},
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
        FullGameAttackFamilySmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


def test_cli_runs_same_probe_and_rejects_bad_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(
        app, ["simulation", "full-game-attack-family-smoke", "--batch-size", "32"]
    )
    assert result.exit_code == 0, result.output
    assert FullGameAttackFamilySmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=32
    )
    assert (
        runner.invoke(
            app, ["simulation", "full-game-attack-family-smoke", "--players", "10"]
        ).exit_code
        == 2
    )
