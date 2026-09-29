"""Narrow private-room Broom observation, not an event-complete replay."""

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

FIXTURE = Path("tests/fixtures/acquisition-private-broom-34732bcb.json")


def rows(items: list[list[int]]) -> object:
    return np.asarray(items, dtype=np.int64).reshape(-1, 4)


def observed_replay() -> tuple[object, dict[str, object]]:
    fixture = json.loads(FIXTURE.read_text())
    replay = native.OrderedInventoryReplay(
        rows(fixture["before_items"]), np.asarray([], dtype=np.int64)
    )
    replay.configure_observed_removal_models(np.asarray([75, 99, 139], dtype=np.int64))
    return replay, fixture


def test_private_broom_fixture_preserves_explicit_narrow_evidence() -> None:
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["source_run_input_sha256"] == (
        "f9f9f92bec8dad89c9e566f2e0c0489ec657c636214c915e82c6a6295b7b49b0"
    )
    assert fixture["catalog_sha256"] == (
        "df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249"
    )
    assert fixture["after_source_sequence"] == fixture["before_source_sequence"] + 1
    assert fixture["after_update_count"] == fixture["before_update_count"] + 1
    assert fixture["phase_input_status"] == "consecutive"
    assert fixture["self_player_id"] == fixture["removal_owner_player_id"] == 2
    assert fixture["removal_action"] == "removeItems"
    assert fixture["removal_items_wire_kind"] == "array"
    assert fixture["removal_event_payload_explicit"]
    assert fixture["preceding_self_defense_items_wire_kind"] == "missing"
    assert not fixture["complete_projection_replay"]
    assert not fixture["training_eligible"]
    assert not fixture["promotion_eligible"]
    assert not fixture["acquisition_rule_eligible"]
    assert fixture["raw_used_flags_all_missing"]
    selected = fixture["selected_items"]
    assert len(selected) == 3
    assert {item[1] for item in selected} == {75, 99, 139}
    assert all(item[2:] == [0, 0] for item in fixture["before_items"])
    selected_ids = {item[0] for item in selected}
    assert [item for item in fixture["before_items"] if item[0] not in selected_ids] == fixture[
        "after_items"
    ]


def test_native_observed_three_removal_matches_private_snapshot() -> None:
    replay, fixture = observed_replay()
    before = replay.snapshot()
    assert replay.observed_removals_configured
    replay.remove_observed_three(rows(fixture["selected_items"]))
    np.testing.assert_array_equal(replay.snapshot(), rows(fixture["after_items"]))
    np.testing.assert_array_equal(before, rows(fixture["before_items"]))
    assert replay.size == 6
    assert replay.observed_removal_count == 3
    assert replay.consumed_item_count == replay.gift_item_count == 0
    assert replay.retained_miracle_use_count == 0


@pytest.mark.parametrize(
    "selected, message",
    [
        ([[2, 75, 0, 0], [5, 139, 0, 0]], "exactly three"),
        ([[2, 75, 0, 0], [2, 75, 0, 0], [3, 99, 0, 0]], "duplicate"),
        ([[2, 75, 0, 0], [5, 139, 0, 0], [3, 100, 0, 0]], "witnessed"),
        ([[2, 75, 0, 0], [5, 139, 0, 0], [3, 99, 0, 1]], "witnessed"),
        ([[2, 75, 0, 0], [5, 139, 0, 0], [3, 99, 75, 0]], "witnessed"),
        ([[2, 75, 0, 0], [5, 139, 0, 0], [10, 99, 0, 0]], "differs from owned"),
        ([[2, 75, 0, 0], [5, 139, 0, 0], [3, 99, 0, 2]], "boolean"),
    ],
)
def test_failed_observed_removal_is_atomic(selected: list[list[int]], message: str) -> None:
    replay, fixture = observed_replay()
    with pytest.raises(ValueError, match=message):
        replay.remove_observed_three(rows(selected))
    np.testing.assert_array_equal(replay.snapshot(), rows(fixture["before_items"]))
    assert replay.observed_removal_count == 0


def test_observed_removal_needs_explicit_immutable_allowlist() -> None:
    initial = rows([[2, 75, 0, 0], [5, 139, 0, 0], [3, 99, 0, 0]])
    selected = initial.copy()
    replay = native.OrderedInventoryReplay(initial, np.asarray([], dtype=np.int64))
    with pytest.raises(ValueError, match="configured"):
        replay.remove_observed_three(selected)
    for models in ([75, 75, 99], [0], [-1], [9007199254740992]):
        with pytest.raises(ValueError):
            replay.configure_observed_removal_models(np.asarray(models, dtype=np.int64))
        assert not replay.observed_removals_configured
    replay.configure_observed_removal_models(np.asarray([75, 99, 139], dtype=np.int64))
    with pytest.raises(ValueError, match="unconfigured"):
        replay.configure_observed_removal_models(np.asarray([75, 99, 139], dtype=np.int64))
    replay.remove_observed_three(selected)
    with pytest.raises(ValueError, match="unstepped"):
        replay.configure_retained_miracles(np.asarray([215], dtype=np.int64))


def test_observed_removal_rejects_repeated_model_even_with_distinct_instances() -> None:
    before = rows([[1, 75, 0, 0], [2, 75, 0, 0], [3, 139, 0, 0], [4, 99, 0, 0]])
    replay = native.OrderedInventoryReplay(before, np.asarray([], dtype=np.int64))
    replay.configure_observed_removal_models(np.asarray([75, 99, 139], dtype=np.int64))
    with pytest.raises(ValueError, match="each witnessed"):
        replay.remove_observed_three(rows([[1, 75, 0, 0], [2, 75, 0, 0], [3, 139, 0, 0]]))
    np.testing.assert_array_equal(replay.snapshot(), before)
    assert replay.observed_removal_count == 0
