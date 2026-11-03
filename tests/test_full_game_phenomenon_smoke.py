"""Uniform phenomena probes report dependency failures, never training success."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_phenomenon_smoke import (
    FullGamePhenomenonSmokeReport,
    run_full_game_phenomenon_smoke,
)

pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_phenomenon_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_probe_keeps_all10_outcomes_including_generated_solar_actions():
    report = probe()
    assert report == probe()
    assert report.model_counts == (61, 44, 53, 55, 50, 45, 53, 55, 36, 60)
    assert report.observed_committed_models == 10
    assert report.first_turns_completed == report.original_owner_ticks == 512
    assert report.development_failures == 0
    assert report.failed_environment_ids == ()
    assert report.commands == 1141 and report.incoming_hp_damage == 4865
    assert report.generated_fate_uses == 0
    assert (
        report.metadata_sha256 == "9f0238d6c7a2ff07d33cfe98a9a74af1829702b1f8c433aa19e4c23be26daf66"
    )
    assert (
        report.diagnostic_replay_sha256
        == "bcfbfd4052534c4f15e75661a55767569bc9aca879ceca3cfe7ac245bcfff45e"
    )
    assert not report.local_training_eligible and report.full_games_completed == 0


@pytest.mark.parametrize("size", [1, 2, 8, 32])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_keep_actual_counts_not_assumed_coverage(size, players):
    report = probe(batch_size=size, player_count=players)
    assert report == FullGamePhenomenonSmokeReport.model_validate_json(report.model_dump_json())
    assert report.first_turns_completed + report.development_failures == size


def test_nested_generated_fate_is_an_extra_event_not_an_extra_owner_tick():
    report = probe(batch_size=4096, player_count=9, seed=0)
    assert report.first_turns_completed == report.original_owner_ticks == 4096
    assert report.generated_fate_uses == 1 and report.development_failures == 0
    assert report.statistic_totals[0] == sum(report.model_counts) == 4097
    assert report == FullGamePhenomenonSmokeReport.model_validate_json(report.model_dump_json())


@pytest.mark.parametrize(
    "field,value",
    [
        ("promotion_eligible", True),
        ("full_game_training_ready", True),
        ("official_fidelity_verified", True),
        ("local_training_eligible", True),
        ("teacher_or_reward_dataset_eligible", True),
        ("full_games_completed", 1),
        ("first_turns_completed", 0),
        ("development_failures", 1),
        ("failed_environment_ids", (0,)),
        ("original_owner_ticks", 0),
        ("other_owner_ticks", 1),
        ("active_families_in_completed_rows", 1),
        ("limit_truncations", 1),
        ("automatic_gifts", 1),
        ("model_counts", ()),
        ("model_ids", ()),
        ("statistic_fields", ()),
        ("statistic_totals", ()),
        ("commands", True),
        ("schema_version", 5),
        ("queue_schema_version", 9),
        ("observed_committed_models", 11),
        ("extra", 1),
    ],
)
def test_forged_scope_layout_and_counts_fail_closed(field, value):
    payload = probe(batch_size=8).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        FullGamePhenomenonSmokeReport.model_validate(payload)


@pytest.mark.parametrize("column", range(23))
def test_statistic_algebra_is_checked(column):
    payload = probe(batch_size=8).model_dump()
    stats = list(payload["statistic_totals"])
    stats[column] += 1
    payload["statistic_totals"] = stats
    with pytest.raises(ValidationError):
        FullGamePhenomenonSmokeReport.model_validate(payload)


@pytest.mark.parametrize("size", [0, -1, True, 4097])
def test_probe_rejects_bad_bounds(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


def test_failed_row_checks_do_not_copy_full_diagnostics_for_every_success(monkeypatch):
    calls = 0
    original = native.FullGameBatch.diagnostic_inventory
    constructor = native.FullGameBatch

    def incomplete_constructor(*args, **options):
        # Omit action profiles, Sacrifice and cap arguments for a raw,
        # incomplete configuration. The real source factory remains complete.
        return constructor(*args[:-9], **options)

    def counted(batch):
        nonlocal calls
        calls += 1
        return original(batch)

    monkeypatch.setattr(native.FullGameBatch, "diagnostic_inventory", counted)
    monkeypatch.setattr(native, "FullGameBatch", incomplete_constructor)
    report = probe(batch_size=512, seed=0)
    assert report.development_failures == 6
    assert report.failed_environment_ids == (71, 73, 194, 329, 366, 400)
    assert report.first_turns_completed == 506
    assert calls <= 2 * report.development_failures + 16


def test_cli_reports_development_failures_instead_of_claiming_full_success(monkeypatch):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app, ["simulation", "full-game-phenomenon-smoke", "--batch-size", "32"]
    )
    assert result.exit_code == 0, result.output
    report = FullGamePhenomenonSmokeReport.model_validate(json.loads(result.output))
    assert report.first_turns_completed + report.development_failures == 32
    assert not report.full_game_training_ready
