"""Mixed trade probes retain strict accounting and never authorize promotion."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_market_smoke import (
    FullGameMarketSmokeReport,
    run_full_game_market_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_market_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_mixed_trade_probe_is_reproducible_but_not_full_games():
    r = probe()
    assert r == probe()
    assert r.scenario_counts == (52, 52, 51, 51, 51, 51, 51, 51, 51, 51)
    assert r.statistic_totals == (
        257,
        255,
        257,
        257,
        255,
        0,
        102,
        0,
        257,
        204,
        51,
        153,
        51,
        410,
        51,
        1129,
        1181,
        413,
        1377,
        4100,
        0,
        204,
        0,
        0,
        0,
    )
    assert r.commands == 2560 and r.original_owner_ticks == 512
    assert r.sun_revivals == 102 and r.bow_shots == 102
    assert r.attack_hp_damage == 3060 and r.consumed_cards == 767
    assert r.metadata_sha256 == "08abe76b9a5393b7dbdea7a2b667e92b1575b1912389f2bfa8f374bd9b56eede"
    assert (
        r.diagnostic_replay_sha256
        == "97f74a881777329a3f9bcd60ca1a8760037fe27cec8ce82a571aaa6d9d335aaa"
    )
    assert not r.full_game_training_ready and r.full_games_completed == 0


@pytest.mark.parametrize("size", [1, 2, 8, 9, 10, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_do_not_assume_all_scenarios(size, players):
    r = probe(batch_size=size, player_count=players)
    assert r == FullGameMarketSmokeReport.model_validate_json(r.model_dump_json())
    assert r.original_owner_ticks == size


@pytest.mark.parametrize(
    "field,value",
    [
        ("full_games_completed", 1),
        ("teacher_or_reward_dataset_eligible", True),
        ("local_training_eligible", True),
        ("full_game_training_ready", True),
        ("official_fidelity_verified", True),
        ("promotion_eligible", True),
        ("original_owner_ticks", 0),
        ("sun_revivals", 99),
        ("bow_shots", 99),
        ("attack_hp_damage", 0),
        ("consumed_cards", 0),
        ("commands", True),
        ("scenario_counts", ()),
        ("statistic_fields", ()),
        ("statistic_totals", ()),
        ("trade_choice_schema_version", 3),
        ("queue_schema_version", 9),
        ("schema_version", 2),
        ("escrow_remaining", 1),
        ("extra", 1),
    ],
)
def test_forged_counts_scope_or_readiness_fail_closed(field, value):
    payload = probe(batch_size=10).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        FullGameMarketSmokeReport.model_validate(payload)


@pytest.mark.parametrize("column", range(25))
def test_every_statistic_is_validated(column):
    payload = probe(batch_size=10).model_dump()
    values = list(payload["statistic_totals"])
    values[column] += 1
    with pytest.raises(ValidationError):
        FullGameMarketSmokeReport.model_validate(payload | {"statistic_totals": values})


@pytest.mark.parametrize("size", [0, -1, True, 4097])
def test_invalid_probe_bounds_reject(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


def test_cli_reports_same_mixed_probe_without_logging_capture_leak(monkeypatch):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app, ["simulation", "full-game-market-smoke", "--batch-size", "10", "--players", "9"]
    )
    assert result.exit_code == 0, result.output
    assert FullGameMarketSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=10, player_count=9
    )
