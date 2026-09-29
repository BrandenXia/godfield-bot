"""Catalog-derived guardian ticket mapping, not observed combat fidelity."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.provisional_rules import (
    ProvisionalRuleUnavailableError,
    build_provisional_guardian_plan,
)

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def profiles(rows: list[list[int]]) -> object:
    return np.asarray(rows, dtype=np.int64).reshape(-1, 3)


def plan() -> object:
    return build_provisional_guardian_plan(
        read_api_catalog_snapshot(CATALOG),
        BibleSnapshot.model_validate_json(BIBLE.read_text(encoding="utf-8")),
    )


def test_native_picker_maps_exact_ticket_boundaries() -> None:
    picker = native.ProvisionalGuardianPicker(profiles([[0, 101, 2], [0, 102, 3], [1, 201, 1]]))
    assert picker.profile_count == 3 and picker.group_count == 2
    assert picker.total_weight(0) == 5 and picker.total_weight(1) == 1
    assert [picker.model_for_ticket(0, ticket) for ticket in range(5)] == [
        101,
        101,
        102,
        102,
        102,
    ]
    assert picker.model_for_ticket(1, 0) == 201
    for group, ticket in ((0, -1), (0, 5), (1, 1), (2, 0)):
        with pytest.raises(ValueError):
            picker.model_for_ticket(group, ticket)
    with pytest.raises(ValueError, match="unknown"):
        picker.total_weight(2)


@pytest.mark.parametrize(
    "rows, message",
    [
        ([], "1..512"),
        ([[0, 101, 1], [1, 101, 2]], "distinct"),
        ([[-1, 101, 1]], "bounded group"),
        ([[32, 101, 1]], "bounded group"),
        ([[0, 0, 1]], "safe model ID"),
        ([[0, 101, 0]], "positive safe weight"),
        ([[0, 101, 9007199254740991], [0, 102, 1]], "overflow"),
    ],
)
def test_native_picker_rejects_invalid_profiles(rows: list[list[int]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        native.ProvisionalGuardianPicker(profiles(rows))


def test_pinned_plan_keeps_activation_and_training_out_of_scope(monkeypatch) -> None:
    guardian_plan = plan()
    assert native.PROVISIONAL_GUARDIAN_SCHEMA_VERSION == 1
    assert guardian_plan.native_ruleset_id == native.PROVISIONAL_GUARDIAN_RULESET_ID
    assert guardian_plan.group_names == (
        "mars",
        "mercury",
        "jupiter",
        "saturn",
        "uranus",
        "pluto",
        "neptune",
        "venus",
    )
    assert len(guardian_plan.weighted_profiles) == 40
    assert guardian_plan.excluded_special_model_ids == (285, 286)
    assert guardian_plan.ticket_interpretation == "hypothetical-relative-weights"
    assert guardian_plan.official_weight_selection_traces == 0
    assert not guardian_plan.effect_resolution_implemented
    assert not guardian_plan.local_training_eligible
    assert not guardian_plan.full_game_training_ready
    assert not guardian_plan.promotion_eligible
    assert not hasattr(native.ProvisionalGuardianPicker, "step")
    assert not hasattr(native.ProvisionalGuardianPicker, "reset")

    picker = native.ProvisionalGuardianPicker(
        np.asarray(guardian_plan.weighted_profiles, dtype=np.int64)
    )
    assert picker.group_count == 8 and picker.profile_count == 40
    assert {picker.total_weight(group) for group in range(8)} == {20}
    tickets = (0, 5, 6, 10, 11, 14, 15, 17, 18, 19)
    assert [picker.model_for_ticket(0, ticket) for ticket in tickets] == [
        245,
        245,
        246,
        246,
        247,
        247,
        248,
        248,
        249,
        249,
    ]
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(app, ["simulation", "provisional-guardian-plan"])
    assert result.exit_code == 0, result.output
    assert '"local_training_eligible": false' in result.output


def test_plan_rejects_catalog_bible_or_native_identity_drift(monkeypatch) -> None:
    catalog = read_api_catalog_snapshot(CATALOG)
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="pinned reviewed catalog"):
        build_provisional_guardian_plan(
            catalog.model_copy(update={"content_sha256": "0" * 64}), bible
        )
    with pytest.raises(ValueError, match="pinned reviewed Bible"):
        wrong_client = bible.client.model_copy(update={"sha256": "0" * 64})
        build_provisional_guardian_plan(
            catalog, bible.model_copy(update={"client": wrong_client})
        )
    monkeypatch.setattr(native, "PROVISIONAL_GUARDIAN_SCHEMA_VERSION", 2)
    with pytest.raises(ProvisionalRuleUnavailableError, match="identity differs"):
        build_provisional_guardian_plan(catalog, bible)
