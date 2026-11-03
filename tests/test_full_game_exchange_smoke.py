"""Bounded scripted Exchange probes cannot be relabeled as training evidence."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_exchange_smoke import (
    FullGameExchangeSmokeReport,
    run_full_game_exchange_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_exchange_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_report_is_exactly_reproducible_and_not_full_games():
    report = probe()
    assert report == probe()
    assert report.scenario_counts == (52, 52, 51, 51, 51, 51, 51, 51, 51, 51)
    assert report.statistic_totals == (512, 512, 0, 512, 674, 561, 561, 306, 0, 0)
    assert report.commands == 1638 and report.original_owner_ticks == 512
    assert report.sun_revivals == 51 and report.bow_shots == 102
    assert report.attack_hp_damage == 3060 and report.consumed_cards == 614
    assert (
        report.metadata_sha256 == "48d093ae4ec459d67a806d908a48664dc4ae818784e9fb3d320f6c673266c170"
    )
    assert (
        report.diagnostic_replay_sha256
        == "69a818309aedb9157adcdb28559d23bbc7ae19c87a6f2200a6c7b310fdcea4b4"
    )
    assert not report.full_game_training_ready and report.full_games_completed == 0


@pytest.mark.parametrize("size", [1, 2, 8, 9, 10, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_do_not_assume_coverage(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameExchangeSmokeReport.model_validate_json(report.model_dump_json())
    assert report.original_owner_ticks == size


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
        ("schema_version", 3),
        ("extra", 1),
    ],
)
def test_forged_reports_fail_closed(field, value):
    payload = probe(batch_size=10).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        FullGameExchangeSmokeReport.model_validate(payload)


@pytest.mark.parametrize("column", range(10))
def test_all_statistic_algebra_is_checked(column):
    payload = probe(batch_size=10).model_dump()
    values = list(payload["statistic_totals"])
    values[column] += 1
    with pytest.raises(ValidationError):
        FullGameExchangeSmokeReport.model_validate(payload | {"statistic_totals": values})


@pytest.mark.parametrize("size", [0, -1, True, 4097])
def test_bad_batch_bounds_fail(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


def test_cli_uses_same_report_and_leaves_logging_capture_safe(monkeypatch):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-exchange-smoke",
            "--batch-size",
            "10",
            "--players",
            "9",
        ],
    )
    assert result.exit_code == 0, result.output
    assert FullGameExchangeSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=10, player_count=9
    )
