"""Synthetic v3 capture/transport checks, not additional official mechanics evidence."""

import asyncio
import copy
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_acquisition_evidence import FakePage, node, raw_room
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches, audit_acquisition_run
from godfield_bot.acquisition_probe import (
    ACQUISITION_CAPTURE_SCHEMA_VERSION,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionRecorder,
    acquisition_batch_digest,
    acquisition_probe_init_script,
    install_acquisition_probe,
)
from godfield_bot.acquisition_replay import REPLAY_CATALOG_SHA256, audit_acquisition_replay_run
from godfield_bot.acquisition_v3 import AcquisitionEvidenceBatchV3, AcquisitionProbeReadV3
from godfield_bot.acquisition_v4 import AcquisitionProbeReadV4
from godfield_bot.cli import app
from godfield_bot.domain.run import RunMode, RunSpec
from godfield_bot.run_store import RunStore, RunStoreError

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
CLIENT = ACQUISITION_REVIEWED_CLIENT_SHA256


@pytest.fixture(autouse=True)
def avoid_retaining_cli_capture(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)


def read(*rooms, **kwargs):
    raw = node(
        "register({}, () => {}); input.rooms.forEach((room) => emit(room)); return read();",
        rooms=rooms,
        schema_version=3,
        **kwargs,
    )
    return AcquisitionProbeReadV3.model_validate_json(json.dumps(raw))


def batch(capture):
    return AcquisitionEvidenceBatchV3(
        observed_at=datetime.now(UTC),
        client_sha256=CLIENT,
        catalog_sha256=REPLAY_CATALOG_SHA256,
        input_sha256=acquisition_batch_digest(
            CLIENT, REPLAY_CATALOG_SHA256, capture.status, capture.snapshots
        ),
        status=capture.status,
        snapshots=capture.snapshots,
    )


def self_use(*, action="useAttackItems", **fields):
    prefix = [{"action": "advanceGF", "playerId": 1}]
    if action == "useDefenseItems":
        prefix = [
            {"action": "advanceGF", "playerId": 2},
            {"action": "setTargetPlayer", "playerId": 1},
        ]
    return raw_room(events=[*prefix, {"action": action, **fields}])


def store(tmp_path):
    storage = RunStore(tmp_path / "runs.sqlite")
    run = storage.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256=CLIENT,
            policy_id="heuristic-v0",
            config={
                "acquisition_evidence_probe": True,
                "acquisition_evidence_schema_version": 3,
                "acquisition_evidence_catalog_sha256": REPLAY_CATALOG_SHA256,
            },
        )
    )
    recorder = AcquisitionRecorder(
        storage, run.run_id, client_sha256=CLIENT, catalog_sha256=REPLAY_CATALOG_SHA256
    )
    return storage, run, recorder


def test_active_install_uses_v4_and_combined_dream_capture_remains_passive():
    class Context:
        async def add_init_script(self, *, script):
            self.script = script

    context = Context()
    asyncio.run(install_acquisition_probe(context, identity="ロキ-67"))
    assert ACQUISITION_CAPTURE_SCHEMA_VERSION == 4
    assert '"schema_version": 4' in context.script
    captured = AcquisitionProbeReadV4.model_validate_json(
        json.dumps(
            node(
                "register({}, () => {}); emit(input.room); return read();",
                room=raw_room(),
                include_dream=True,
            )
        )
    )
    assert captured.schema_version == 4
    assert captured.status.hook_installed


@pytest.mark.parametrize(
    "fields, kind", [({}, "missing"), ({"items": None}, "null"), ({"items": []}, "array")]
)
def test_missing_null_and_explicit_empty_selections_are_distinct(fields, kind):
    captured = read(self_use(action="useDefenseItems", **fields))
    row = captured.snapshots[0]
    assert row.events[-1].self_item_payload_bound
    assert row.events[-1].items == ()
    assert row.event_item_wire[-1].items_kind == kind
    audit = audit_acquisition_batches((batch(captured),))
    assert audit.self_event_wire_metadata_count == 1
    assert audit.ambiguous_self_selection_event_count == (kind != "array")


@pytest.mark.parametrize(
    "fake, used, fake_kind, used_kind",
    [
        (None, None, "null", "null"),
        (0, False, "zero", "boolean"),
        (142, True, "positive_integer", "boolean"),
        (-1, "PRIVATE_USED", "other", "other"),
    ],
)
def test_self_item_wire_fields_preserve_classification_without_raw_private_values(
    fake, used, fake_kind, used_kind
):
    captured = read(self_use(items=[{"id": 1, "modelId": 23, "fakeModelId": fake, "used": used}]))
    wire = captured.snapshots[0].event_item_wire[-1].items[0]
    assert wire.fake_model_id_kind == fake_kind
    assert wire.used_kind == used_kind
    audit = audit_acquisition_batches((batch(captured),))
    assert audit.malformed_self_event_wire_count == (fake_kind == "other")
    assert "PRIVATE_USED" not in captured.model_dump_json()


def test_compact_defaults_and_full_gift_overflow_wire_metadata_are_self_only():
    captured = read(
        raw_room(
            events=[
                {
                    "action": "gift",
                    "playerId": 1,
                    "item": {"id": 2, "modelId": 215},
                    "overflowItem": {"id": 1, "modelId": 23, "used": True},
                    "itemModelId": 0,
                }
            ]
        )
    )
    row = captured.snapshots[0]
    wire = row.event_item_wire[0]
    assert wire.item_kind == wire.overflow_item_kind == "object"
    assert wire.items_kind == "missing"
    assert wire.item.fake_model_id_kind == wire.item.used_kind == "missing"
    assert wire.overflow_item.used_kind == "boolean"
    assert wire.item_model_id_kind == "zero"
    assert audit_acquisition_batches((batch(captured),)).self_overflow_item_event_count == 1


@pytest.mark.parametrize("action", ["gift", "useAttackItems", "useDefenseItems"])
def test_opponent_and_unresolved_wire_sidecars_do_not_reveal_models_shapes_or_used_flags(action):
    prefix = [{"action": "advanceGF", "playerId": 2}] if action == "useAttackItems" else []
    if action == "useDefenseItems":
        prefix = [
            {"action": "advanceGF", "playerId": 1},
            {"action": "setTargetPlayer", "playerId": 2},
        ]
    room = raw_room(
        events=[
            *prefix,
            {
                "action": action,
                "playerId": 2,
                "item": {"id": 666, "modelId": 777},
                "items": [{"id": 666, "modelId": 777, "fakeModelId": 778, "used": True}],
                "overflowItem": {"id": 666, "modelId": 779},
                "itemModelId": 780,
            },
        ]
    )
    captured = read(room)
    wire = captured.snapshots[0].event_item_wire[-1]
    assert not captured.snapshots[0].events[-1].self_item_payload_bound
    assert wire.item_kind == wire.items_kind == wire.overflow_item_kind == "redacted"
    assert wire.item_model_id_kind == "redacted"
    assert wire.item is wire.overflow_item is None and wire.items == ()
    assert not any(
        secret in captured.model_dump_json() for secret in ("666", "777", "778", "779", "780")
    )
    unresolved = read(
        raw_room(
            events=[{"action": "useAttackItems", "items": room["game"]["events"][-1]["items"]}]
        )
    )
    assert unresolved.snapshots[0].event_item_wire[-1].items_kind == "redacted"


@pytest.mark.parametrize(
    "field, value",
    [
        ("items", "PRIVATE_ARRAY"),
        ("item", "PRIVATE_OBJECT"),
        ("overflowItem", False),
        ("itemModelId", -7),
    ],
)
def test_malformed_bound_container_fields_are_classified_without_echoing_raw_values(field, value):
    room = self_use(**{field: value})
    captured = read(room)
    assert captured.status.rejected_snapshot_count == 0
    audit = audit_acquisition_batches((batch(captured),))
    assert audit.malformed_self_event_wire_count == 1
    assert "PRIVATE_" not in captured.model_dump_json()


@pytest.mark.parametrize("field, value", [("items", [None]), ("items", [{}] * 513)])
def test_unrepresentable_selections_are_rejected_boundedly_without_breaking_delivery(field, value):
    result = node(
        "let delivered=0; register({}, () => {delivered++;}); emit(input.room); "
        "return {capture:read(), delivered};",
        schema_version=3,
        room=self_use(**{field: value}),
    )
    captured = AcquisitionProbeReadV3.model_validate_json(json.dumps(result["capture"]))
    assert captured.status.rejected_snapshot_count == 1
    assert captured.snapshots == ()
    assert result["delivered"] == 1


@pytest.mark.parametrize("change", ["fake", "used", "items_missing", "item_model", "overflow"])
def test_changed_self_event_payload_invalidates_repeat_context_even_if_inventory_is_unchanged(
    change,
):
    first = raw_room(events=[{"action": "advanceGF", "playerId": 1}])
    second = raw_room(
        updateCount=1,
        events=[
            {"action": "useAttackItems", "items": [{"id": 1, "modelId": 23}]},
        ],
    )
    changed = copy.deepcopy(second)
    operation = changed["game"]["events"][0]
    if change == "fake":
        operation["items"][0]["fakeModelId"] = 142
    elif change == "used":
        operation["items"][0]["used"] = True
    elif change == "items_missing":
        del operation["items"]
    elif change == "item_model":
        operation["itemModelId"] = 23
    else:
        operation["overflowItem"] = {"id": 1, "modelId": 23}
    captured = read(first, second, changed)
    last = captured.snapshots[-1]
    assert last.phase_input_status == "inconsistent_repeat"
    assert last.phase_before is None
    assert not last.events[0].self_item_payload_bound
    assert last.event_item_wire[0].items_kind == "redacted"
    assert last.phase_after.turn_player_id is None
    assert audit_acquisition_batches((batch(captured),)).inconsistent_server_version_count == 1


def test_consistent_repeat_uses_original_before_context_without_replaying_counts():
    first = raw_room(events=[{"action": "advanceGF", "playerId": 1}])
    second = raw_room(
        updateCount=1,
        events=[
            {"action": "useAttackItems", "items": [{"id": 1, "modelId": 23}]},
            {"action": "advanceGF", "playerId": 2},
        ],
    )
    captured = read(first, second, second)
    assert captured.snapshots[-1].phase_input_status == "repeat"
    assert captured.snapshots[-1].phase_before == captured.snapshots[1].phase_before
    audit = audit_acquisition_batches((batch(captured),))
    assert audit.repeated_server_version_count == 1
    assert audit.self_event_wire_metadata_count == audit.self_bound_attack_item_count == 1


@pytest.mark.parametrize(
    "change", ["empty_to_missing", "missing_fake_to_negative", "missing_used_to_other"]
)
def test_repeat_wire_only_changes_invalidate_context_even_when_sanitized_items_are_identical(
    change,
):
    first = raw_room(events=[{"action": "advanceGF", "playerId": 1}])
    selection = [] if change == "empty_to_missing" else [{"id": 1, "modelId": 23}]
    second = raw_room(updateCount=1, events=[{"action": "useAttackItems", "items": selection}])
    changed = copy.deepcopy(second)
    operation = changed["game"]["events"][0]
    if change == "empty_to_missing":
        del operation["items"]
    elif change == "missing_fake_to_negative":
        operation["items"][0]["fakeModelId"] = -1
    else:
        operation["items"][0]["used"] = "PRIVATE_INVALID_USED"
    captured = read(first, second, changed)
    assert captured.snapshots[-1].phase_input_status == "inconsistent_repeat"
    assert captured.snapshots[-1].phase_before is None
    assert captured.snapshots[-1].event_item_wire[0].items_kind == "redacted"
    assert "PRIVATE_INVALID_USED" not in captured.model_dump_json()


def test_changes_to_opponent_item_payload_do_not_enter_repeat_stamp():
    first = raw_room(events=[{"action": "advanceGF", "playerId": 2}])
    second = raw_room(
        updateCount=1,
        events=[
            {"action": "useAttackItems", "items": [{"id": 666, "modelId": 777}]},
        ],
    )
    changed = copy.deepcopy(second)
    changed["game"]["events"][0]["items"][0]["modelId"] = 888
    captured = read(first, second, changed)
    assert captured.snapshots[-1].phase_input_status == "repeat"
    assert captured.snapshots[-1].event_item_wire[0].items_kind == "redacted"
    assert "777" not in captured.model_dump_json() and "888" not in captured.model_dump_json()


@pytest.mark.parametrize(
    "defect", ["coverage", "redacted", "missing_item_sidecar", "wire_kind", "indices"]
)
def test_strict_sidecar_validation_rejects_conflicting_or_leaking_metadata(defect):
    raw = read(self_use(items=[{"id": 1, "modelId": 23}])).model_dump(mode="json")
    row = raw["snapshots"][0]
    wire = row["event_item_wire"][-1]
    if defect == "coverage":
        row["event_item_wire"].pop()
    elif defect == "redacted":
        row["event_item_wire"][0]["item_kind"] = "null"
    elif defect == "missing_item_sidecar":
        wire["items"] = []
    elif defect == "wire_kind":
        wire["items"][0]["used_kind"] = "boolean"
    else:
        wire["items"][0]["raw_index"] = 4
    with pytest.raises(ValidationError):
        AcquisitionProbeReadV3.model_validate_json(json.dumps(raw))


def test_saved_v3_batch_requires_reviewed_client_and_content_digest():
    raw = batch(read(self_use(items=[]))).model_dump(mode="json")
    raw["client_sha256"] = "a" * 64
    with pytest.raises(ValidationError, match="reviewed client hash"):
        AcquisitionEvidenceBatchV3.model_validate_json(json.dumps(raw))
    raw = batch(read(self_use(items=[]))).model_dump(mode="json")
    raw["snapshots"][0]["event_item_wire"][-1]["items_kind"] = "missing"
    with pytest.raises(ValidationError, match="digest differs"):
        AcquisitionEvidenceBatchV3.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize("version", [3.0, "3", True])
def test_v3_readers_require_exact_integer_capture_version(version):
    captured = read(self_use(items=[]))
    raw = captured.model_dump(mode="json")
    raw["schema_version"] = version
    with pytest.raises(ValidationError, match="exact integer 3"):
        AcquisitionProbeReadV3.model_validate_json(json.dumps(raw))
    raw = batch(captured).model_dump(mode="json")
    raw["schema_version"] = version
    with pytest.raises(ValidationError, match="exact integer 3"):
        AcquisitionEvidenceBatchV3.model_validate_json(json.dumps(raw))


def test_recorder_v3_saves_before_ack_and_preserves_capture_after_storage_failure(
    tmp_path, monkeypatch
):
    storage, run, recorder = store(tmp_path)
    captured = read(self_use(items=[]))
    page = FakePage(captured)
    append = storage.append_event

    def fail(*_args, **_kwargs):
        raise RunStoreError("synthetic storage failure")

    monkeypatch.setattr(storage, "append_event", fail)
    with pytest.raises(RunStoreError):
        asyncio.run(recorder.poll(page))
    assert "ack" not in page.trace
    assert recorder.last_seen == {}
    monkeypatch.setattr(storage, "append_event", append)
    assert asyncio.run(recorder.poll(page))
    assert page.read.snapshots == ()
    assert recorder.saved_snapshots == 1
    asyncio.run(recorder.finalize(page))
    report = audit_acquisition_run(storage.path, run.run_id)
    assert report["capture_schema_versions"] == [3]
    assert report["declared_capture_schema_version"] == 3
    assert report["capture_schema_matches_run_config"]
    assert report["self_event_wire_metadata_count"] == 1
    assert report["legacy_self_bound_event_without_wire_count"] == 0
    assert report["final_poll_succeeded"]


def initial_room():
    return raw_room(
        events=[
            {"action": "startGame"},
            {"action": "gift", "playerId": 1, "item": {"id": 1, "modelId": 23}},
            {"action": "advanceGF", "playerId": 1},
        ],
        players=[
            {"id": 1, "name": "ロキ-67", "items": [{"id": 1, "modelId": 23}]},
            {"id": 2, "name": "CPU", "items": []},
        ],
    )


@pytest.mark.parametrize(
    "fields, status",
    [
        ({"items": []}, "matched"),
        ({}, "unsupported"),
        ({"items": None}, "unsupported"),
        ({"items": "PRIVATE_ARRAY"}, "unsupported"),
    ],
)
def test_replay_requires_explicit_v3_selection_array_and_cli_reports_are_read_only(
    tmp_path, fields, status
):
    pytest.importorskip("godfield_sim")
    storage, run, recorder = store(tmp_path)
    first = initial_room()
    final = copy.deepcopy(first)
    final["game"].update(
        updateCount=1,
        isOver=True,
        events=[{"action": "useAttackItems", **fields}, {"action": "endGame"}],
    )
    page = FakePage(read(first, final))
    asyncio.run(recorder.finalize(page))
    original = storage.path.read_bytes()
    report = audit_acquisition_replay_run(storage.path, run.run_id, catalog_path=CATALOG)
    assert report["schema_version"] == 2
    assert report["event_item_wire_metadata_complete"]
    assert report["results"][-1]["status"] == status
    assert report["complete_projection_replay"] == (status == "matched")
    assert report["training_eligible"] is False
    result = CliRunner().invoke(
        app, ["runs", "acquisition-replay", run.run_id, "--database", str(storage.path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == report
    assert "PRIVATE_ARRAY" not in result.stdout
    assert storage.path.read_bytes() == original


def test_v3_malformed_event_fake_is_not_silently_treated_as_undisguised(tmp_path):
    pytest.importorskip("godfield_sim")
    storage, run, recorder = store(tmp_path)
    first = initial_room()
    final = copy.deepcopy(first)
    final["game"].update(
        updateCount=1,
        isOver=True,
        events=[
            {"action": "useAttackItems", "items": [{"id": 1, "modelId": 23, "fakeModelId": -1}]},
            {"action": "endGame"},
        ],
    )
    final["game"]["players"][0]["items"] = []
    asyncio.run(recorder.finalize(FakePage(read(first, final))))
    report = audit_acquisition_replay_run(storage.path, run.run_id, catalog_path=CATALOG)
    assert report["results"][-1]["reason"] == "malformed_self_event_wire"
    assert report["matched_consumed_item_count"] == 0
    assert not report["complete_projection_replay"]


def test_synthetic_full_v3_event_wire_replay_handles_id_reuse_and_flame_first_use_reuse(tmp_path):
    pytest.importorskip("godfield_sim")
    storage, run, recorder = store(tmp_path)
    first = initial_room()
    first["game"]["players"][0]["items"] = [
        {"id": 1, "modelId": 23},
        {"id": 2, "modelId": 215},
        {"id": 3, "modelId": 142},
    ]
    first["game"]["events"] = [
        {"action": "startGame"},
        *[
            {"action": "gift", "playerId": 1, "item": copy.deepcopy(item)}
            for item in first["game"]["players"][0]["items"]
        ],
        {"action": "advanceGF", "playerId": 1},
    ]
    second = copy.deepcopy(first)
    second["game"].update(
        updateCount=1,
        events=[
            {"action": "useAttackItems", "items": [{"id": 1, "modelId": 23}]},
            {"action": "gift", "playerId": 1, "item": {"id": 1, "modelId": 3}},
        ],
    )
    second["game"]["players"][0]["items"] = [
        {"id": 2, "modelId": 215},
        {"id": 3, "modelId": 142},
        {"id": 1, "modelId": 3},
    ]
    third = copy.deepcopy(second)
    third["game"].update(
        updateCount=2,
        events=[
            {"action": "useAttackItems", "items": [{"id": 2, "modelId": 215}]},
            {"action": "gift", "playerId": 1, "item": {"id": 4, "modelId": 126}},
        ],
    )
    third["game"]["players"][0]["items"] = [
        {"id": 3, "modelId": 142},
        {"id": 1, "modelId": 3},
        {"id": 2, "modelId": 215, "used": True},
        {"id": 4, "modelId": 126},
    ]
    final = copy.deepcopy(third)
    final["game"].update(
        updateCount=3,
        isOver=True,
        events=[
            {"action": "useAttackItems", "items": [{"id": 2, "modelId": 215, "used": True}]},
            {"action": "gift", "playerId": 1, "item": {"id": 5, "modelId": 202}},
            {"action": "endGame"},
        ],
    )
    final["game"]["players"][0]["items"] = [
        {"id": 3, "modelId": 142},
        {"id": 1, "modelId": 3},
        {"id": 4, "modelId": 126},
        {"id": 2, "modelId": 215, "used": True},
        {"id": 5, "modelId": 202},
    ]
    asyncio.run(recorder.finalize(FakePage(read(first, second, third, final))))
    report = audit_acquisition_replay_run(storage.path, run.run_id, catalog_path=CATALOG)
    assert report["complete_projection_replay"]
    assert report["event_item_wire_metadata_complete"]
    assert report["matched_consumed_item_count"] == 1
    assert report["matched_gift_item_count"] == 6
    assert report["matched_retained_miracle_use_count"] == 2
    assert report["combat_replay_verified"] is False
    assert report["acquisition_rule_eligible"] is False


def test_synthetic_v3_explicit_empty_defense_retains_inventory_without_inferring_selection(
    tmp_path,
):
    pytest.importorskip("godfield_sim")
    storage, run, recorder = store(tmp_path)
    first = initial_room()
    final = copy.deepcopy(first)
    final["game"].update(
        updateCount=1,
        isOver=True,
        events=[
            {"action": "advanceGF", "playerId": 2},
            {"action": "setTargetPlayer", "playerId": 1},
            {"action": "useDefenseItems", "items": []},
            {"action": "endGame"},
        ],
    )
    asyncio.run(recorder.finalize(FakePage(read(first, final))))
    report = audit_acquisition_replay_run(storage.path, run.run_id, catalog_path=CATALOG)
    assert report["complete_projection_replay"]
    assert report["transport_audit"]["self_bound_defense_event_count"] == 1
    assert report["transport_audit"]["self_bound_defense_item_count"] == 0
    assert report["transport_audit"]["ambiguous_self_selection_event_count"] == 0
    assert report["matched_consumed_item_count"] == 0


def test_v3_unresolved_owner_prevents_complete_self_event_metadata_claim(tmp_path):
    pytest.importorskip("godfield_sim")
    storage, run, recorder = store(tmp_path)
    room = initial_room()
    room["game"]["events"][-1] = {"action": "useAttackItems", "items": []}
    asyncio.run(recorder.finalize(FakePage(read(room))))
    report = audit_acquisition_replay_run(storage.path, run.run_id, catalog_path=CATALOG)
    assert report["transport_audit"]["capture_schema_versions"] == [3]
    assert report["transport_audit"]["unresolved_item_owner_event_count"] == 1
    assert not report["event_item_wire_metadata_complete"]
    assert not report["complete_projection_replay"]


@pytest.mark.parametrize("version", [True, 0, 5, "3"])
def test_capture_version_is_an_exact_supported_integer(version):
    with pytest.raises(ValueError, match="unsupported acquisition capture schema"):
        acquisition_probe_init_script("ロキ-67", schema_version=version)


def test_unknown_run_and_private_payload_errors_are_sanitized(tmp_path):
    storage, run, recorder = store(tmp_path)
    asyncio.run(recorder.finalize(FakePage(read(initial_room()))))
    with sqlite3.connect(storage.path) as connection:
        row = connection.execute("SELECT payload_json FROM events WHERE sequence=0").fetchone()
        payload = json.loads(row[0])
        payload["snapshots"][0]["event_item_wire"][0]["PRIVATE_SECRET"] = "DO_NOT_PRINT"
        connection.execute(
            "UPDATE events SET payload_json=? WHERE sequence=0", (json.dumps(payload),)
        )
    result = CliRunner().invoke(
        app, ["runs", "acquisition-evidence", run.run_id, "--database", str(storage.path)]
    )
    assert result.exit_code == 1
    assert "schema or content digest mismatch" in result.output
    assert "PRIVATE_SECRET" not in result.output and "DO_NOT_PRINT" not in result.output
