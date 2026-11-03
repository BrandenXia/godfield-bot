"""Strict report scope and replay/CLI parity for the multi-card discard loop."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_discard_smoke import (
    FullGameDiscardSmokeReport,
    run_full_game_discard_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_discard_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_discard_probe_is_reproducible_bounded_and_not_full_games():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (86, 86, 85, 85, 85, 85)
    assert report.discard_totals == (597, 1022, 85, 512, 767, 171)
    assert report.actions == 2386
    assert report.completed_turns == report.discard_turns == report.original_owner_ticks == 512
    assert report.discarded_cards == 767 and report.consumed_cards == 170
    assert report.revivals == report.bows_consumed == 85
    assert report.bow_recipients == report.family_enqueued == report.family_resolved == 170
    assert report.bow_hp_damage == 5100
    assert (
        report.metadata_sha256 == "5c45c09197ab843f5511f7ad4ec3fe3a88bd71c1413cc6d179dfbcbd4cbbb984"
    )
    assert (
        report.diagnostic_replay_sha256
        == "420581f8be9eea61f9ce7fc8049020e8eba178051fc657982889ea5e538a4b03"
    )
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 6, 7, 8, 31, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_scenarios_and_rosters_validate_strict_turn_and_family_counts(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameDiscardSmokeReport.model_validate_json(report.model_dump_json())
    assert report.completed_turns == size and report.limit_truncations == 0


@pytest.mark.parametrize("seed", [0, 1, 68, 999, 2**64 - 1])
def test_other_periodic_ticket_seeds_remain_replayable(seed):
    assert probe(batch_size=32, seed=seed) == probe(batch_size=32, seed=seed)


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_invalid_batch_size_rejects_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"scenario_counts": (1,)},
        {"discard_fields": ("true-victim",)},
        {"discard_totals": (1,)},
        {"actions": 0},
        {"discard_turns": 0},
        {"discarded_cards": 0},
        {"completed_turns": 0},
        {"original_owner_ticks": 0},
        {"other_owner_ticks": 1},
        {"consumed_cards": 0},
        {"revivals": 0},
        {"bows_consumed": 0},
        {"bow_recipients": 0},
        {"bow_hp_damage": 0},
        {"family_enqueued": 0},
        {"family_resolved": 0},
        {"ready_after_one_turn": 0},
        {"real_terminal_endings": 1},
        {"automatic_gifts": 1},
        {"mp_spent": 1},
        {"miracle_uses": 1},
        {"original_attacks": 1},
        {"removal_attack_cards": 1},
        {"limit_truncations": 1},
        {"discard_profile_sha256": "0" * 64},
        {"apocalypse_and_sacrifice_exercised": True},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"schema_version": 8},
        {"hidden_ticket": 1},
    ],
)
def test_forged_accounting_and_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameDiscardSmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


def test_cli_matches_same_probe_and_rejects_bad_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    result = runner.invoke(app, ["simulation", "full-game-discard-smoke", "--batch-size", "32"])
    assert result.exit_code == 0, result.output
    assert FullGameDiscardSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=32
    )
    assert (
        runner.invoke(app, ["simulation", "full-game-discard-smoke", "--players", "10"]).exit_code
        == 2
    )
