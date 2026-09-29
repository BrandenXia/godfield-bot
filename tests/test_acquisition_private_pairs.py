"""Exact paired ordinary uses observed in private API transitions only."""

import json
from pathlib import Path

import pytest

from godfield_bot.acquisition_replay import (
    NATIVE_CONSUMABLE_MODELS,
    ORDINARY_MODELS,
    REPLAY_CATALOG_SHA256,
    WITNESSED_ORDINARY_PAIRS,
)
from godfield_bot.api_catalog import read_api_catalog_snapshot

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

FIXTURE = json.loads(
    Path("tests/fixtures/acquisition-private-ordinary-paired-use-v1.json").read_text()
)
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")


def rows(items: list[list[int]]) -> object:
    return np.asarray(items, dtype=np.int64).reshape(-1, 4)


def test_paired_allowlist_is_exactly_witnessed_and_separate_from_single_use() -> None:
    catalog = read_api_catalog_snapshot(CATALOG)
    category = {item.model_id: item.raw.get("category") for item in catalog.items}
    assert FIXTURE["source_kind"] == "private-api-ordinary-paired-use-observation-fixture-v1"
    assert FIXTURE["catalog_sha256"] == catalog.content_sha256 == REPLAY_CATALOG_SHA256
    assert len(FIXTURE["source_runs"]) == 6
    assert len(FIXTURE["cases"]) == 9
    assert tuple(tuple(pair) for pair in FIXTURE["witnessed_ordered_model_pairs"]) == (
        WITNESSED_ORDINARY_PAIRS
    )
    assert {model for pair in WITNESSED_ORDINARY_PAIRS for model in pair} - set(
        ORDINARY_MODELS
    ) == {12, 15, 22, 25, 54, 74, 90, 134, 149, 154, 157, 161}
    assert set(NATIVE_CONSUMABLE_MODELS) == set(ORDINARY_MODELS) | {
        model for pair in WITNESSED_ORDINARY_PAIRS for model in pair
    }
    assert all(
        category[model] in {"weapons", "armor", "sundries"}
        for pair in WITNESSED_ORDINARY_PAIRS
        for model in pair
    )
    assert not any(
        FIXTURE[key]
        for key in (
            "complete_game_replay",
            "training_eligible",
            "promotion_eligible",
            "acquisition_rule_eligible",
        )
    )
    for case in FIXTURE["cases"]:
        assert case["run_id"] in FIXTURE["source_runs"]
        assert len(FIXTURE["source_runs"][case["run_id"]]) == 64
        assert case["after_source_sequence"] == case["before_source_sequence"] + 1
        assert case["after_update_count"] == case["before_update_count"] + 1
        assert case["phase_input_status"] == "consecutive"
        assert case["selected_items_wire_kind"] == "array"
        selected = next(
            op for op in case["operations"] if op["event_index"] == case["selected_event_index"]
        )
        assert selected["action"] in {"useAttackItems", "useDefenseItems"}
        assert [item[1] for item in selected["items"]] == case["selected_model_ids"]


@pytest.mark.parametrize(
    "case",
    FIXTURE["cases"],
    ids=lambda case: f"{case['run_id'][:8]}-{case['after_source_sequence']}",
)
def test_native_replays_each_witnessed_pair(case: dict[str, object]) -> None:
    replay = native.OrderedInventoryReplay(
        rows(case["before_items"]), np.asarray(NATIVE_CONSUMABLE_MODELS, dtype=np.int64)
    )
    for operation in case["operations"]:
        if operation["action"] == "gift":
            replay.gift(np.asarray(operation["item"], dtype=np.int64))
        else:
            replay.consume(rows(operation["items"]))
    np.testing.assert_array_equal(replay.snapshot(), rows(case["after_items"]))
    assert replay.consumed_item_count == 2
    assert replay.gift_item_count == sum(
        operation["action"] == "gift" for operation in case["operations"]
    )
