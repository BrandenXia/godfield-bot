"""Complete generated pools, explicit dispatch counts and strict non-training scope."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_generated_smoke import (
    FullGameGeneratedSmokeReport,
    run_full_game_generated_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_generated_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


@pytest.mark.parametrize("kind", ["earth", "moon", "mixed"])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_weighted_pools_dispatch_all_draws_and_complete_only_one_turn(kind, players):
    r = probe(guardian_kind=kind, player_count=players)
    assert r == probe(guardian_kind=kind, player_count=players)
    assert r.execution_counts == r.model_counts
    assert r.original_owner_ticks == 4096 and r.full_games_completed == 0
    assert not r.full_game_training_ready and not r.promotion_eligible
    if kind == "moon":
        assert r.observed_models == 30 and not any(r.model_counts[:207])
    elif kind == "earth":
        assert not any(r.model_counts[207:])


@pytest.mark.parametrize("size", [1, 2, 32])
@pytest.mark.parametrize("kind", ["earth", "moon", "mixed"])
def test_partial_batches_roundtrip_without_claiming_all_outcomes(size, kind):
    r = probe(batch_size=size, guardian_kind=kind)
    assert r == FullGameGeneratedSmokeReport.model_validate_json(r.model_dump_json())
    assert not r.all_generated_outcomes_exercised


@pytest.mark.parametrize(
    "change",
    [
        {"execution_counts": ()},
        {"execution_counts": (0,) * 237},
        {"miracle_uses": 1},
        {"original_attacks": 1},
        {"response_commands": 0},
        {"attack_hp_damage": 0},
        {"sun_revivals": 999},
        {"phenomenon_attack_hp_damage": 999},
        {"automatic_danger_resolutions": 999},
        {"queue_schema_version": 9},
        {"schema_version": 3},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"official_fidelity_verified": True},
        {"local_training_eligible": True},
        {"teacher_or_reward_dataset_eligible": True},
    ],
)
def test_forged_dispatch_accounting_and_readiness_rejected(change):
    with pytest.raises(ValidationError):
        FullGameGeneratedSmokeReport.model_validate(probe(batch_size=256).model_dump() | change)


@pytest.mark.parametrize("size", [True, 0, -1, 4097])
def test_bad_size_rejected(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


def test_unknown_guardian_and_cli_fail_closed(monkeypatch):
    from godfield_bot.cli import app

    with pytest.raises(ValueError, match="guardian kind"):
        probe(guardian_kind="unknown")
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        ["simulation", "full-game-generated-smoke", "--guardian", "moon", "--batch-size", "32"],
    )
    assert result.exit_code == 0, result.output
    r = FullGameGeneratedSmokeReport.model_validate(json.loads(result.output))
    assert r.guardian_kind == "moon" and r.original_owner_ticks == 32
