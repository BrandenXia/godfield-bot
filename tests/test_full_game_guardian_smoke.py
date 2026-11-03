"""Strict standard-guardian report scope, replay pins, roster coverage and CLI."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_guardian_smoke import (
    FullGameGuardianSmokeReport,
    run_full_game_guardian_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_guardian_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_probe_observes_all40_standard_effects_without_claiming_specials_or_full_games():
    r = probe()
    assert r == probe() and r.observed_effect_models == 40
    assert r.statistic_totals == (
        0,
        0,
        4096,
        1045,
        1045,
        832,
        1045,
        1045,
        0,
        0,
        0,
        0,
        0,
        12748,
        427,
        305,
        753,
        0,
        52,
    )
    assert r.actions == 4928 and r.completed_turns == r.original_owner_ticks == 4096
    assert r.revivals == r.consumed_cards == 106 and r.hp_absorbed == 102
    assert r.metadata_sha256 == "3063d992fef14945612d35a251e8d59ee316eb3f928a3f080acc5149af125c08"
    assert (
        r.diagnostic_replay_sha256
        == "62cc41d1964b18f5eef26631332f0d2c8b9b53b346e2cb857ad67c1afaa4ee4b"
    )
    assert r.unimplemented_special_models == () and not r.full_game_training_ready


@pytest.mark.parametrize("size", [1, 2, 7, 8, 31, 32, 256])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_group_batches_and_rosters_preserve_exact_accounting(size, players):
    r = probe(batch_size=size, player_count=players)
    assert r == FullGameGuardianSmokeReport.model_validate_json(r.model_dump_json())
    assert r.completed_turns == size


@pytest.mark.parametrize("seed", [0, 1, 68, 999, 2**64 - 1])
def test_other_unforced_activation_and_weight_stream_seeds_are_deterministic(seed):
    assert probe(batch_size=256, seed=seed) == probe(batch_size=256, seed=seed)


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_bad_batch_size_rejects_before_allocating(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"model_counts": (1,)},
        {"model_counts": (True,) * 40},
        {"model_counts": ("1",) * 40},
        {"model_ids": (245,)},
        {"statistic_totals": (1,)},
        {"statistic_fields": ("future-rng",)},
        {"observed_effect_models": 40},
        {"actions": 0},
        {"completed_turns": 0},
        {"original_owner_ticks": 0},
        {"revivals": 1000},
        {"consumed_cards": 1000},
        {"restored_disguises": 1000},
        {"incoming_hp_damage": 1000},
        {"hp_absorbed": 1000},
        {"other_owner_ticks": 1},
        {"limit_truncations": 1},
        {"original_attacks": 1},
        {"mp_spent": 1},
        {"automatic_gifts": 1},
        {"unimplemented_special_models": (285,)},
        {"guardian_profile_sha256": "0" * 64},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"schema_version": 6},
        {"private_queue": 1},
    ],
)
def test_forged_counts_or_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameGuardianSmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


def test_cli_matches_the_same_probe_and_rejects_bad_bounds(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    r = runner.invoke(app, ["simulation", "full-game-guardian-smoke", "--batch-size", "32"])
    assert r.exit_code == 0, r.output
    assert FullGameGuardianSmokeReport.model_validate(json.loads(r.output)) == probe(batch_size=32)
    assert (
        runner.invoke(app, ["simulation", "full-game-guardian-smoke", "--players", "10"]).exit_code
        == 2
    )
