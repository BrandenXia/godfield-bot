"""Artifact inclusion is a measurable inventory, never a fidelity claim."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.simulation_coverage import build_simulation_coverage_report

pytest.importorskip("godfield_sim")

BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def test_latest_native_catalog_gap_is_explicit_and_non_promotable(monkeypatch) -> None:
    report = build_simulation_coverage_report(BIBLE)
    assert report.scope == "artifact-inclusion-only-not-behavioral-fidelity"
    assert report.bible_artifact_count == 291
    assert report.included_artifact_count == 196
    assert report.missing_artifact_count == 95
    assert report.included_artifact_count + report.missing_artifact_count == 291
    assert {name: len(assets) for name, assets in report.missing_by_category.items()} == {
        "armor": 17,
        "devils": 5,
        "guardians": 42,
        "miracles": 7,
        "phenomena": 10,
        "sundries": 9,
        "weapons": 5,
    }
    assert "goddess-s-soap" in report.missing_by_category["sundries"]
    assert "nocturnal-broom" in report.missing_by_category["sundries"]
    assert not report.full_game_training_ready
    assert not report.official_fidelity_verified
    assert not report.promotion_eligible

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(app, ["simulation", "coverage-report"])
    assert result.exit_code == 0, result.output
    assert '"missing_artifact_count": 95' in result.output
    assert '"full_game_training_ready": false' in result.output
