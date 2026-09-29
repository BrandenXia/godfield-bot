"""Adjacent private API single-use fixtures; not full-game training evidence."""

import json
from pathlib import Path

import pytest

from godfield_bot.acquisition_replay import ORDINARY_MODELS, REPLAY_CATALOG_SHA256
from godfield_bot.api_catalog import read_api_catalog_snapshot

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

FIXTURE_PATH = Path("tests/fixtures/acquisition-private-ordinary-single-use-v1.json")
FIXTURE = json.loads(FIXTURE_PATH.read_text())
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")


def rows(items: list[list[int]]) -> object:
    return np.asarray(items, dtype=np.int64).reshape(-1, 4)


def test_fixture_contains_only_witnessed_single_use_models_and_no_training_labels() -> None:
    catalog = read_api_catalog_snapshot(CATALOG)
    categories = {item.model_id: item.raw.get("category") for item in catalog.items}
    assert FIXTURE["catalog_sha256"] == catalog.content_sha256 == REPLAY_CATALOG_SHA256
    assert FIXTURE["source_kind"] == "private-api-ordinary-single-use-observation-fixture-v1"
    assert not any(
        FIXTURE[key]
        for key in (
            "complete_game_replay",
            "training_eligible",
            "promotion_eligible",
            "acquisition_rule_eligible",
        )
    )
    assert len(FIXTURE["source_runs"]) == 8
    assert len(FIXTURE["cases"]) == 36
    models = {case["selected_model_id"] for case in FIXTURE["cases"]}
    assert len(models) == 28
    assert models == set(FIXTURE["new_model_ids"])
    assert models.issubset(ORDINARY_MODELS)
    assert all(categories[model] in {"weapons", "armor", "sundries"} for model in models)
    for case in FIXTURE["cases"]:
        assert case["run_id"] in FIXTURE["source_runs"]
        assert len(FIXTURE["source_runs"][case["run_id"]]) == 64
        assert len(case["before_batch_input_sha256"]) == 64
        assert len(case["after_batch_input_sha256"]) == 64
        assert case["after_source_sequence"] == case["before_source_sequence"] + 1
        assert case["after_update_count"] == case["before_update_count"] + 1
        assert case["phase_input_status"] == "consecutive"
        assert case["selected_items_wire_kind"] == "array"
        selected = next(
            op for op in case["operations"] if op["event_index"] == case["selected_event_index"]
        )
        assert selected["action"] in {"useAttackItems", "useDefenseItems"}
        assert len(selected["items"]) == 1
        assert selected["items"][0][1] == case["selected_model_id"]


@pytest.mark.parametrize(
    "case",
    FIXTURE["cases"],
    ids=lambda case: f"{case['run_id'][:8]}-{case['after_source_sequence']}",
)
def test_native_replays_each_explicit_private_single_use(case: dict[str, object]) -> None:
    replay = native.OrderedInventoryReplay(
        rows(case["before_items"]), np.asarray(ORDINARY_MODELS, dtype=np.int64)
    )
    for operation in case["operations"]:
        if operation["action"] == "gift":
            replay.gift(np.asarray(operation["item"], dtype=np.int64))
        else:
            replay.consume(rows(operation["items"]))
    np.testing.assert_array_equal(replay.snapshot(), rows(case["after_items"]))
    assert replay.consumed_item_count == 1
    assert replay.gift_item_count == sum(
        operation["action"] == "gift" for operation in case["operations"]
    )
