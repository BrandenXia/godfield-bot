"""Catalog-derived Soap hypothesis; never an official mechanics oracle."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.provisional_rules import (
    ProvisionalRuleUnavailableError,
    build_provisional_soap_plan,
)

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def bible() -> BibleSnapshot:
    return BibleSnapshot.model_validate_json(BIBLE.read_text(encoding="utf-8"))


def rows(items: list[list[int]]) -> object:
    return np.asarray(items, dtype=np.int64).reshape(-1, 4)


def miracle_models() -> object:
    catalog = read_api_catalog_snapshot(CATALOG)
    models = [item.model_id for item in catalog.items if item.raw.get("category") == "miracles"]
    assert len(models) == 30
    return np.asarray(models, dtype=np.int64)


def projection() -> object:
    return native.ProvisionalSoapProjection(
        rows([[1, 215, 0, 1], [2, 216, 0, 1], [3, 23, 0, 0], [4, 215, 0, 0]]),
        miracle_models(),
    )


def test_provisional_identity_is_separate_from_observed_replay_and_training_batches() -> None:
    assert native.PROVISIONAL_SOAP_SCHEMA_VERSION == 1
    assert native.PROVISIONAL_SOAP_RULESET_ID == (
        "catalog-derived-selected-two-used-miracles-provisional-v1"
    )
    assert native.PROVISIONAL_SOAP_RULESET_ID != native.ORDERED_INVENTORY_REPLAY_RULESET_ID
    assert native.PROVISIONAL_SOAP_RULESET_ID != native.RULESET_ID
    assert not hasattr(native.ProvisionalSoapProjection, "step")
    assert not hasattr(native.ProvisionalSoapProjection, "reset")


def test_catalog_pinned_provisional_plan_has_explicit_false_eligibility(monkeypatch) -> None:
    catalog = read_api_catalog_snapshot(CATALOG)
    plan = build_provisional_soap_plan(catalog, bible())
    assert plan.native_ruleset_id == native.PROVISIONAL_SOAP_RULESET_ID
    assert plan.catalog_sha256 == catalog.content_sha256
    assert plan.bible_client_sha256 == bible().client.sha256
    assert plan.soap_model_id == 206 and plan.action == "removeUsedMiracles"
    assert plan.selected_item_count == 2
    assert plan.selection_policy == "caller-provided-only"
    assert tuple(miracle_models()) == plan.miracle_model_ids
    assert plan.status == "provisional-unvalidated"
    assert not plan.complete_game_replay
    assert not plan.local_training_eligible
    assert not plan.official_validation_eligible
    assert not plan.promotion_eligible
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(app, ["simulation", "provisional-soap-plan"])
    assert result.exit_code == 0, result.output
    assert "provisional-unvalidated" in result.output
    assert '"promotion_eligible": false' in result.output


def test_provisional_plan_rejects_catalog_or_native_identity_drift(monkeypatch) -> None:
    catalog = read_api_catalog_snapshot(CATALOG)
    with pytest.raises(ValueError, match="pinned"):
        build_provisional_soap_plan(
            catalog.model_copy(update={"content_sha256": "0" * 64}), bible()
        )
    with pytest.raises(ValueError, match="Bible"):
        build_provisional_soap_plan(
            catalog,
            bible().model_copy(
                update={"client": bible().client.model_copy(update={"sha256": "0" * 64})}
            ),
        )
    monkeypatch.setattr(native, "PROVISIONAL_SOAP_SCHEMA_VERSION", 2)
    with pytest.raises(ProvisionalRuleUnavailableError, match="identity differs"):
        build_provisional_soap_plan(catalog, bible())


def test_selected_two_used_miracles_are_removed_without_reordering_survivors() -> None:
    replay = projection()
    before = replay.snapshot()
    replay.wash_selected_two(rows([[2, 216, 0, 1], [1, 215, 0, 1]]))
    np.testing.assert_array_equal(replay.snapshot(), rows([[3, 23, 0, 0], [4, 215, 0, 0]]))
    np.testing.assert_array_equal(
        before, rows([[1, 215, 0, 1], [2, 216, 0, 1], [3, 23, 0, 0], [4, 215, 0, 0]])
    )
    assert not before.flags.writeable
    assert replay.size == 2 and replay.removed_item_count == 2


@pytest.mark.parametrize(
    "selected, message",
    [
        ([[1, 215, 0, 1]], "exactly two"),
        ([[1, 215, 0, 1], [1, 215, 0, 1]], "duplicate"),
        ([[1, 215, 0, 1], [3, 23, 0, 0]], "used undisguised"),
        ([[1, 215, 0, 1], [4, 215, 0, 0]], "used undisguised"),
        ([[1, 215, 0, 1], [2, 216, 215, 1]], "used undisguised"),
        ([[1, 215, 0, 1], [2, 215, 0, 1]], "differs from owned"),
        ([[1, 215, 0, 1], [9, 216, 0, 1]], "differs from owned"),
        ([[1, 215, 0, 1], [2, 216, 0, 2]], "boolean"),
    ],
)
def test_invalid_provisional_selection_is_atomic(selected: list[list[int]], message: str) -> None:
    replay = projection()
    before = replay.snapshot()
    with pytest.raises(ValueError, match=message):
        replay.wash_selected_two(rows(selected))
    np.testing.assert_array_equal(replay.snapshot(), before)
    assert replay.removed_item_count == 0


def test_constructor_and_array_contract_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        native.ProvisionalSoapProjection(rows([[1, 215, 0, 1], [1, 216, 0, 1]]), miracle_models())
    with pytest.raises(ValueError, match="distinct"):
        native.ProvisionalSoapProjection(rows([]), np.asarray([215, 215], dtype=np.int64))
    with pytest.raises(ValueError, match="capacity"):
        native.ProvisionalSoapProjection(rows([[1, 215, 0, 1]]), miracle_models(), 0)
    with pytest.raises(TypeError):
        native.ProvisionalSoapProjection(rows([]), np.asarray([215], dtype=np.float64))
    replay = projection()
    with pytest.raises(TypeError):
        replay.wash_selected_two(np.asarray([[1, 215, 0, 1]], dtype=np.float64))
