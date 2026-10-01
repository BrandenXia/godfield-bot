"""Inventory/episode/component accounting cannot masquerade as full-game fidelity."""

import json
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("godfield_sim")

from godfield_bot.api_catalog import api_catalog_digest
from godfield_bot.cli import app
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game_readiness import (
    FullGameReadinessReport,
    build_full_game_readiness_report,
)

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


@pytest.fixture
def report():
    return build_full_game_readiness_report(catalog_path=CATALOG, bible_path=BIBLE)


def test_current_inventory_opening_components_and_missing_are_separate(report):
    assert report.artifact_count == 291
    assert report.inventory_model_count == 102
    assert report.opening_only_count == 5
    assert report.component_only_count == 34
    assert report.not_integrated_count == 150
    assert Counter(item.integration for item in report.artifacts) == {
        "inventory-usable": 102,
        "opening-only": 5,
        "component-only": 34,
        "not-integrated": 150,
    }
    assert Counter(
        item.category for item in report.artifacts if item.integration == "not-integrated"
    ) == {
        "weapons": 68,
        "armor": 31,
        "miracles": 21,
        "sundries": 12,
        "phenomena": 10,
        "devils": 5,
        "guardians": 3,
    }
    by_asset = {item.asset: item for item in report.artifacts}
    assert by_asset["spring"].integration == "inventory-usable"
    assert by_asset["diamond-axe"].integration == "not-integrated"
    assert by_asset["sky-boots"].integration == "not-integrated"
    assert by_asset["goddess-s-soap"].integration == "not-integrated"
    assert by_asset["nocturnal-broom"].integration == "not-integrated"
    assert by_asset["mars-ring"].integration == "not-integrated"
    assert all(
        item.category == "guardians"
        for item in report.artifacts
        if item.integration in ("opening-only", "component-only")
    )


def test_workflow_gaps_are_explicit_and_duel_subset_is_not_full_game(report):
    assert report.local_duel_subset_training_ready
    assert report.neural_training_player_counts == (2,)
    assert report.rollout_player_counts == tuple(range(2, 10))
    assert report.action_count == 48
    assert not report.full_game_training_ready
    assert not report.official_fidelity_verified
    assert not report.live_checkpoint_compatible
    assert not report.promotion_eligible
    expected = {
        "acquisition-overflow",
        "offensive-combinations",
        "special-defense",
        "utility-targeting-costs",
        "curse-turn-dynamics",
        "guardian-lifecycle-timing",
        "devils",
        "phenomena",
        "economy",
        "removal-revival",
        "apocalypse-terminal-flow",
        "teams-multiplayer-learning",
        "full-action-observation-contract",
        "full-game-validation",
    }
    assert {gap.workflow_id for gap in report.workflow_gaps} == expected
    assert all(Path(file).is_file() for gap in report.workflow_gaps for file in gap.source_files)


def test_portable_curse_component_is_not_counted_as_inventory_integration(report):
    curses = next(gap for gap in report.workflow_gaps if gap.workflow_id == "curse-turn-dynamics")
    assert curses.status == "partial"
    assert "not integrated" in curses.current_behavior
    assert "native/godfield_sim/src/curse_dynamics_batch.cpp" in curses.source_files
    assert "src/godfield_bot/curse_dynamics.py" in curses.source_files
    assert "native/godfield_sim/src/curse_decisions.cpp" in curses.source_files
    assert "src/godfield_bot/curse_decisions.py" in curses.source_files
    by_model = {item.model_id: item for item in report.artifacts}
    assert all(by_model[model].integration == "not-integrated" for model in (199, 200, 237, 238))
    assert report.inventory_model_count == 102
    assert not report.full_game_training_ready


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "duplicates",
        "asset_alias",
        "bucket",
        "gaps",
        "ready",
        "official",
        "promotion",
    ],
)
def test_audit_rejects_false_counts_identity_and_readiness(report, change):
    data = report.model_dump(mode="json")
    if change == "count":
        data["inventory_model_count"] += 1
    elif change == "duplicates":
        data["artifacts"][1]["model_id"] = data["artifacts"][0]["model_id"]
    elif change == "asset_alias":
        data["artifacts"][1]["category"] = data["artifacts"][0]["category"]
        data["artifacts"][1]["asset"] = data["artifacts"][0]["asset"]
    elif change == "bucket":
        data["artifacts"][0]["integration"] = "not-integrated"
    elif change == "gaps":
        data["workflow_gaps"] += [data["workflow_gaps"][0]]
    else:
        key = {
            "ready": "full_game_training_ready",
            "official": "official_fidelity_verified",
            "promotion": "promotion_eligible",
        }[change]
        data[key] = True
    with pytest.raises(ValueError):
        FullGameReadinessReport.model_validate(data)


def test_report_is_reproducible_roundtrips_and_does_not_run_matches(report, monkeypatch):
    monkeypatch.setattr(
        "godfield_bot.guardian_rollout.GuardianRolloutArena.step",
        lambda *_: pytest.fail("audit must not run rollout decisions"),
    )
    assert build_full_game_readiness_report(catalog_path=CATALOG, bible_path=BIBLE) == report
    assert FullGameReadinessReport.model_validate_json(report.model_dump_json()) == report


def test_audit_rejects_relabelled_bible_with_matching_old_client_pin(tmp_path):
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    data = bible.model_dump(mode="json")
    data["catalog"]["weapons"]["items"][0]["asset"] = "new-weapon"
    altered = tmp_path / "bible.json"
    altered.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="catalog"):
        build_full_game_readiness_report(catalog_path=CATALOG, bible_path=altered)


def test_current_catalog_snapshot_has_same_pinned_content(report):
    # The network refresh is a new dated artifact, not a modification of old pins.
    path = Path("data/snapshots/2026-10-01/api-catalog-en.json")
    if not path.exists():
        pytest.skip("optional dated source refresh is absent in this checkout")
    fresh = build_full_game_readiness_report(catalog_path=path, bible_path=BIBLE)
    assert fresh == report


def test_changed_api_content_is_rejected_even_with_a_self_consistent_digest(tmp_path):
    from godfield_bot.api_catalog import ApiCatalogItem

    data = json.loads(CATALOG.read_text())
    data["items"][0]["raw"]["atk"] = 999
    items = tuple(ApiCatalogItem.model_validate(item) for item in data["items"])
    data["content_sha256"] = api_catalog_digest(items)
    altered = tmp_path / "catalog.json"
    altered.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="pinned"):
        build_full_game_readiness_report(catalog_path=altered, bible_path=BIBLE)


def test_cli_emits_a_readonly_integration_audit(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(app, ["simulation", "full-game-readiness"])
    assert result.exit_code == 0, result.output
    report = FullGameReadinessReport.model_validate_json(result.output)
    assert report.inventory_model_count == 102 and not report.full_game_training_ready
