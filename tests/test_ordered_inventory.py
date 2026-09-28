"""Explicit native replay, not a full game or a trainable acquisition curriculum."""

import hashlib
import json
from pathlib import Path

import pytest

from godfield_bot.acquisition_evidence import audit_acquisition_batches
from godfield_bot.acquisition_probe import AcquisitionCollectorSummary, AcquisitionItem
from godfield_bot.acquisition_v2 import AcquisitionEvidenceBatchV2
from godfield_bot.api_catalog import read_api_catalog_snapshot

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
FIXTURE = Path("tests/fixtures/acquisition-v2-bc54a888.json")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")


def rows(items: list[list[int]]) -> object:
    return np.asarray(items, dtype=np.int64).reshape(-1, 4)


def item_row(item: AcquisitionItem) -> list[int]:
    # Interpretation stays outside the C++ kernel; the fixture is pinned to
    # the reviewed decoder, and source wire values remain unchanged.
    assert item.instance_id is not None and item.model_id is not None
    return [item.instance_id, item.model_id, item.fake_model_id or 0, int(item.used is True)]


def inventory(
    initial: list[list[int]] | None = None,
    ordinary: list[int] | None = None,
    *,
    capacity: int = 512,
) -> object:
    return native.OrderedInventoryReplay(
        rows(initial or []),
        np.asarray([23, 142] if ordinary is None else ordinary, dtype=np.int64),
        capacity,
    )


def test_replay_has_separate_identity_and_does_not_replace_training_rulesets() -> None:
    assert native.ORDERED_INVENTORY_REPLAY_SCHEMA_VERSION == 1
    assert native.ORDERED_INVENTORY_REPLAY_RULESET_ID == (
        "explicit-ordinary-consumption-ordered-gift-replay-v1"
    )
    assert native.RULESET_ID != native.ORDERED_INVENTORY_REPLAY_RULESET_ID
    assert native.HAND_SLOTS == 9
    assert native.ACTION_COUNT == 21


def test_official_v2_fixture_hashes_and_full_transport_audit() -> None:
    fixture = json.loads(FIXTURE.read_text())
    batches = tuple(
        AcquisitionEvidenceBatchV2.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-evidence-v2"
    )
    summaries = tuple(
        AcquisitionCollectorSummary.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-collector-summary-v1"
    )
    fingerprint = {key: fixture[key] for key in ("run_id", "mode", "client_sha256", "evidence")}
    assert (
        hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == fixture["input_sha256"]
    )
    audit = audit_acquisition_batches(batches, summaries=summaries)
    assert len(batches) == 8
    assert audit.snapshot_count == 4
    assert audit.capture_schema_versions == (2,)
    assert audit.collection_issues == ()
    assert audit.self_bound_attack_item_count == audit.self_bound_defense_item_count == 1
    assert audit.self_bound_attack_event_count == 1
    assert audit.self_bound_defense_event_count == 2
    assert audit.self_overflow_item_event_count == 0
    assert not audit.training_eligible
    assert not audit.promotion_eligible
    assert not audit.acquisition_rule_eligible


def test_native_replays_every_official_ordered_inventory_snapshot() -> None:
    fixture = json.loads(FIXTURE.read_text())
    catalog = read_api_catalog_snapshot(CATALOG)
    by_id = {item.model_id: item.raw for item in catalog.items}
    replay = inventory()
    snapshots = []
    consumed_models = []
    for record in fixture["evidence"]:
        if record["payload"]["source_kind"] != "official-acquisition-evidence-v2":
            continue
        batch = AcquisitionEvidenceBatchV2.model_validate_json(json.dumps(record["payload"]))
        assert batch.model_dump(mode="json") == record["payload"]
        assert batch.catalog_sha256 == catalog.content_sha256
        for snapshot in batch.snapshots:
            for event in snapshot.events:
                if not event.self_item_payload_bound:
                    assert event.item is None and event.items == ()
                    continue
                if event.action == "gift":
                    assert event.item is not None and event.overflow_item is None
                    assert event.item.model_id in by_id
                    replay.gift(np.asarray(item_row(event.item), dtype=np.int64))
                else:
                    assert event.action in {"useAttackItems", "useDefenseItems"}
                    for item in event.items:
                        assert by_id[item.model_id]["category"] in {"weapons", "armor"}
                        consumed_models.append(item.model_id)
                    replay.consume(rows([item_row(item) for item in event.items]))
            np.testing.assert_array_equal(
                replay.snapshot(), rows([item_row(item) for item in snapshot.self_items])
            )
            snapshots.append(replay.snapshot())
    assert consumed_models == [142, 23]
    assert replay.consumed_item_count == 2
    assert replay.gift_item_count == 11
    assert replay.size == 9
    assert [int(snapshot[-1, 0]) for snapshot in snapshots] == [9, 4, 2, 2]
    assert [int(snapshot[-1, 1]) for snapshot in snapshots] == [118, 3, 126, 126]
    assert not snapshots[0].flags.writeable


def test_remove_compacts_survivors_and_gift_reuses_id_only_after_removal() -> None:
    replay = inventory([[1, 23, 0, 0], [2, 142, 0, 0], [3, 23, 0, 0]])
    before = replay.snapshot()
    replay.consume(rows([[2, 142, 0, 0], [1, 23, 0, 0]]))
    np.testing.assert_array_equal(replay.snapshot(), rows([[3, 23, 0, 0]]))
    replay.gift(np.asarray([2, 3, 0, 0], dtype=np.int64))
    np.testing.assert_array_equal(replay.snapshot(), rows([[3, 23, 0, 0], [2, 3, 0, 0]]))
    del replay
    np.testing.assert_array_equal(before, rows([[1, 23, 0, 0], [2, 142, 0, 0], [3, 23, 0, 0]]))


@pytest.mark.parametrize(
    "selected, message",
    [
        ([[1, 23, 0, 0], [2, 23, 0, 0]], "differs from owned"),
        ([[1, 23, 0, 0], [1, 23, 0, 0]], "duplicate"),
        ([[1, 23, 0, 0], [8, 142, 0, 0]], "differs from owned"),
        ([[1, 23, 0, 0], [2, 3, 0, 0]], "allowlisted"),
        ([[1, 23, 0, 0], [2, 142, 23, 0]], "undisguised"),
        ([[1, 23, 0, 0], [2, 142, 0, 1]], "unused"),
        ([[0, 23, 0, 0]], "positive safe"),
        ([[1, 23, 0, 2]], "boolean"),
        ([[1, 23, 0, 0]] * 4, "exceeds owned"),
    ],
)
def test_invalid_selection_is_atomic(selected: list[list[int]], message: str) -> None:
    replay = inventory([[1, 23, 0, 0], [2, 142, 0, 0], [3, 3, 0, 0]])
    before = replay.snapshot()
    with pytest.raises(ValueError, match=message):
        replay.consume(rows(selected))
    np.testing.assert_array_equal(replay.snapshot(), before)
    assert replay.consumed_item_count == replay.gift_item_count == 0


def test_opaque_miracle_and_used_artifact_are_not_silently_consumed() -> None:
    replay = inventory([[1, 204, 0, 1], [2, 142, 23, 0]])
    for item in ([1, 204, 0, 1], [2, 142, 23, 0]):
        with pytest.raises(ValueError, match="unsupported"):
            replay.consume(rows([item]))
    assert replay.size == 2


@pytest.mark.parametrize("capacity", [0, 513])
def test_replay_resource_bound_is_not_an_official_maximum(capacity: int) -> None:
    with pytest.raises(ValueError, match="capacity"):
        inventory(capacity=capacity)


def test_gift_does_not_overwrite_or_guess_overflow_removal() -> None:
    replay = inventory([[1, 23, 0, 0]], capacity=2)
    before = replay.snapshot()
    with pytest.raises(ValueError, match="overwrite"):
        replay.gift(np.asarray([1, 3, 0, 0], dtype=np.int64))
    np.testing.assert_array_equal(replay.snapshot(), before)
    replay.gift(np.asarray([2, 3, 0, 0], dtype=np.int64))
    full = replay.snapshot()
    with pytest.raises(ValueError, match="overflow removal is not inferred"):
        replay.gift(np.asarray([3, 23, 0, 0], dtype=np.int64))
    np.testing.assert_array_equal(replay.snapshot(), full)
    assert replay.gift_item_count == 1


@pytest.mark.parametrize(
    "initial, ordinary, message",
    [
        ([[1, 23, 0, 0], [1, 142, 0, 0]], [23], "duplicate"),
        ([[0, 23, 0, 0]], [23], "positive safe"),
        ([[1, 23, -1, 0]], [23], "nonnegative"),
        ([[1, 23, 0, 3]], [23], "boolean"),
        ([[9007199254740992, 23, 0, 0]], [23], "safe"),
        ([], [23, 23], "distinct"),
        ([], [0], "positive"),
        ([], list(range(1, 514)), "allowlist exceeds"),
    ],
)
def test_constructor_rejects_invalid_values(
    initial: list[list[int]], ordinary: list[int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        inventory(initial, ordinary)


def test_empty_inventory_empty_selection_and_snapshot_lifetime() -> None:
    replay = inventory()
    empty = replay.snapshot()
    replay.consume(rows([]))
    assert replay.size == replay.consumed_item_count == replay.gift_item_count == 0
    assert empty.shape == (0, 4)
    replay.gift(np.asarray([1, 23, 0, 0], dtype=np.int64))
    assert empty.shape == (0, 4)


def test_empty_allowlist_cannot_consume_any_opaque_artifact() -> None:
    replay = inventory([[1, 23, 0, 0]], ordinary=[])
    with pytest.raises(ValueError, match="allowlisted"):
        replay.consume(rows([[1, 23, 0, 0]]))
    assert replay.size == 1


@pytest.mark.parametrize(
    "item",
    [[0, 23, 0, 0], [1, 0, 0, 0], [1, 23, -1, 0], [1, 23, 0, 2]],
)
def test_invalid_gift_does_not_mutate_inventory(item: list[int]) -> None:
    replay = inventory()
    with pytest.raises(ValueError):
        replay.gift(np.asarray(item, dtype=np.int64))
    assert replay.size == replay.gift_item_count == 0


def test_constructor_copies_input_and_honors_explicit_capacity() -> None:
    initial = rows([[1, 23, 0, 0]])
    replay = native.OrderedInventoryReplay(initial, np.asarray([23], dtype=np.int64), 1)
    initial[0, 1] = 142
    np.testing.assert_array_equal(replay.snapshot(), rows([[1, 23, 0, 0]]))
    assert replay.capacity == 1
    with pytest.raises(ValueError, match="initial inventory exceeds"):
        inventory([[1, 23, 0, 0], [2, 142, 0, 0]], capacity=1)


def test_array_contract_rejects_lossy_conversions_and_wrong_shapes() -> None:
    with pytest.raises(TypeError):
        native.OrderedInventoryReplay(np.zeros((1, 4)), np.asarray([23], dtype=np.int64))
    with pytest.raises(TypeError):
        native.OrderedInventoryReplay(np.zeros((1, 3), dtype=np.int64), np.array([23]))
    replay = inventory([[1, 23, 0, 0]])
    with pytest.raises(TypeError):
        replay.consume(np.zeros((1, 4)))
    with pytest.raises(TypeError):
        replay.gift(np.zeros(4))
    assert replay.size == 1
