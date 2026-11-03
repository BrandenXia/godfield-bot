"""Strict first-turn reports and CLI; never full-match or learning evidence."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_devil_smoke import FullGameDevilSmokeReport, run_full_game_devil_smoke

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_devil_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_dealt_hand_probe_observes_all5_without_claiming_full_matches():
    report = probe()
    assert report == probe()
    assert report.model_counts == (272, 202, 108, 192, 224)
    assert report.statistic_totals == (
        4096,
        4097,
        998,
        582,
        10000,
        192,
        1629,
        384,
        224,
        0,
        690,
        910,
        384,
        224,
        4099,
        4097,
        2,
        4096,
    )
    assert report.observed_devil_models == 5
    assert report.commands == 14644
    assert report.completed_turns == report.original_owner_ticks == 4096
    assert (
        report.metadata_sha256 == "2dc5316e38add40cf26c47cf258808f584c2f5f1919f07d5ccfaa583f519ceb1"
    )
    assert (
        report.diagnostic_replay_sha256
        == "4022609504d888b24969ae0e10366cbae2510b8339c3ff156ed5fdcb7da35616"
    )
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 2, 7, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_small_complete_pool_batches_do_not_require_all_rare_events(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGameDevilSmokeReport.model_validate_json(report.model_dump_json())
    assert report.completed_turns == size
    assert not report.teacher_or_reward_dataset_eligible


@pytest.mark.parametrize(
    "field,value",
    [
        ("promotion_eligible", True),
        ("full_game_training_ready", True),
        ("local_training_eligible", True),
        ("official_fidelity_verified", True),
        ("teacher_or_reward_dataset_eligible", True),
        ("completed_turns", 0),
        ("original_owner_ticks", 0),
        ("other_owner_ticks", 1),
        ("limit_truncations", 1),
        ("pending_families", 1),
        ("queue_schema_version", 9),
        ("schema_version", 5),
        ("model_counts", ()),
        ("model_ids", ()),
        ("statistic_totals", ()),
        ("statistic_fields", ()),
        ("observed_devil_models", 6),
        ("automatic_gifts", 0),
        ("initial_gifts", 0),
        ("commands", True),
        ("devil_hp_damage", -1),
        ("unexpected", 1),
    ],
)
def test_forged_report_fails_closed(field, value):
    payload = probe(batch_size=8).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        FullGameDevilSmokeReport.model_validate(payload)


@pytest.mark.parametrize("column", [0, 1, 2, 3, 5, 7, 8, 12, 13, 14, 15, 16])
def test_stats_algebra_cannot_be_relabelled(column):
    payload = probe(batch_size=8).model_dump()
    stats = list(payload["statistic_totals"])
    stats[column] += 1
    payload["statistic_totals"] = stats
    with pytest.raises(ValidationError):
        FullGameDevilSmokeReport.model_validate(payload)


@pytest.mark.parametrize("size", [0, -1, 4097, True])
def test_probe_bounds(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


def test_cli_offline_probe(monkeypatch):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(app, ["simulation", "full-game-devil-smoke", "--batch-size", "8"])
    assert result.exit_code == 0, result.output
    report = FullGameDevilSmokeReport.model_validate(json.loads(result.output))
    assert report.completed_turns == 8 and report.apocalypse_after_turns == 1
