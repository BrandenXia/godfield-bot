"""Synthetic removal transport tests; not an official removal mechanics oracle."""

import asyncio
import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_acquisition_evidence import FakePage, node, raw_room, v2_read, v3_read, v4_read, v5_read
from test_acquisition_v4 import prefix
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches, audit_acquisition_run
from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionProbeRead,
    AcquisitionRecorder,
    acquisition_batch_digest,
)
from godfield_bot.acquisition_replay import REPLAY_CATALOG_SHA256, audit_acquisition_replay_run
from godfield_bot.acquisition_v5 import AcquisitionEvidenceBatchV5, AcquisitionProbeReadV5
from godfield_bot.cli import app
from godfield_bot.domain.run import RunMode, RunSpec
from godfield_bot.run_store import RunStore, RunStoreError

REMOVALS = ("removeItems", "removeUsedMiracles")
CLIENT = ACQUISITION_REVIEWED_CLIENT_SHA256
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")


def removal_room(action="removeUsedMiracles", *, attacker=2, defender=1, **fields):
    return raw_room(events=[*prefix(attacker, defender), {"action": action, **fields}])


def batch(capture):
    return AcquisitionEvidenceBatchV5(
        observed_at=datetime.now(UTC),
        client_sha256=CLIENT,
        catalog_sha256=REPLAY_CATALOG_SHA256,
        input_sha256=acquisition_batch_digest(
            CLIENT, REPLAY_CATALOG_SHA256, capture.status, capture.snapshots
        ),
        status=capture.status,
        snapshots=capture.snapshots,
    )


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
                "acquisition_evidence_schema_version": 5,
                "acquisition_evidence_catalog_sha256": REPLAY_CATALOG_SHA256,
            },
        )
    )
    recorder = AcquisitionRecorder(
        storage, run.run_id, client_sha256=CLIENT, catalog_sha256=REPLAY_CATALOG_SHA256
    )
    return storage, run, recorder


@pytest.mark.parametrize("action", REMOVALS)
@pytest.mark.parametrize("actor", [None, 1, 2, 99])
def test_recipient_is_seeded_target_not_explicit_event_player(action, actor):
    row = v5_read(
        [
            removal_room(
                action,
                playerId=actor,
                items=[{"id": 4, "modelId": 215, "used": True}, {"id": 7, "modelId": 23}],
            )
        ]
    ).snapshots[0]
    assert row.event_owners[-1].item_owner_player_id == 1
    assert row.event_owners[-1].basis == "target_context"
    assert row.events[-1].self_item_payload_bound
    assert [item.instance_id for item in row.events[-1].items] == [4, 7]
    assert [wire.raw_index for wire in row.event_item_wire[-1].items] == [0, 1]
    assert row.event_item_wire[-1].items[0].used_kind == "boolean"
    assert row.event_item_wire[-1].items[1].used_kind == "missing"
    assert row.phase_after.turn_player_id is row.phase_after.target_player_id is None


@pytest.mark.parametrize("action", REMOVALS)
def test_opponent_removal_body_and_wire_shapes_remain_redacted(action):
    row = v5_read(
        [
            removal_room(
                action,
                attacker=1,
                defender=2,
                playerId=1,
                item={"id": 666, "modelId": 777},
                items=[{"id": 666, "modelId": 778, "used": True}],
                overflowItem={"id": 667, "modelId": 779},
                itemModelId=780,
            )
        ]
    ).snapshots[0]
    assert row.event_owners[-1].item_owner_player_id == 2
    assert not row.events[-1].self_item_payload_bound
    wire = row.event_item_wire[-1]
    assert wire.item_kind == wire.items_kind == wire.overflow_item_kind == "redacted"
    assert wire.item_model_id_kind == "redacted"
    assert not any(secret in row.model_dump_json() for secret in ("666", "777", "778", "779"))


@pytest.mark.parametrize("action", REMOVALS)
@pytest.mark.parametrize("seed", [[], prefix(1, 1), prefix(2, 99), prefix(99, 1)])
def test_unseeded_invalid_or_self_target_cannot_bind_even_with_self_player_id(action, seed):
    row = v5_read(
        [
            raw_room(
                events=[
                    *seed,
                    {"action": action, "playerId": 1, "items": [{"id": 666, "modelId": 777}]},
                ]
            )
        ]
    ).snapshots[0]
    assert row.event_owners[-1].basis == "unresolved"
    assert not row.events[-1].self_item_payload_bound
    assert row.event_item_wire[-1].items_kind == "redacted"
    assert "777" not in row.model_dump_json()


@pytest.mark.parametrize("action", REMOVALS)
def test_multiplayer_removal_and_changed_membership_stay_unresolved(action):
    room = removal_room(action, items=[])
    room["game"]["players"].append({"id": 3, "name": "THIRD_SECRET", "items": []})
    row = v5_read([room]).snapshots[0]
    assert row.event_owners[-1].basis == "unresolved"
    first = raw_room(events=prefix(2, 1))
    second = raw_room(events=[{"action": action, "items": []}], updateCount=1)
    second["game"]["players"][1]["id"] = 3
    row = v5_read([first, second]).snapshots[-1]
    assert row.phase_input_status == "gap_or_boundary"
    assert not row.events[-1].self_item_payload_bound


@pytest.mark.parametrize("action", REMOVALS)
def test_consecutive_owner_context_is_consumed_not_preserved_by_removal(action):
    first = raw_room(events=prefix(2, 1))
    second = raw_room(events=[{"action": action, "items": []}], updateCount=1)
    third = raw_room(events=[{"action": "useDefenseItems", "items": []}], updateCount=2)
    capture = v5_read([first, second, third])
    assert capture.snapshots[1].events[-1].self_item_payload_bound
    assert not capture.snapshots[2].events[-1].self_item_payload_bound
    assert capture.snapshots[2].event_owners[-1].basis == "unresolved"
    second["game"]["updateCount"] = 2
    row = v5_read([first, second]).snapshots[-1]
    assert row.phase_input_status == "gap_or_boundary"
    assert not row.events[-1].self_item_payload_bound


@pytest.mark.parametrize("action", REMOVALS)
def test_removal_uses_reviewed_reflected_duel_target(action):
    row = v5_read(
        [raw_room(events=[*prefix(1, 2), {"action": "reflect"}, {"action": action, "items": []}])]
    ).snapshots[0]
    assert row.event_owners[-1].item_owner_player_id == 1
    assert row.events[-1].self_item_payload_bound
    assert row.phase_after.turn_player_id is None


@pytest.mark.parametrize(
    "effect", ["bounce", "nextAttack", "removeSomething", "discard", "UNKNOWN"]
)
def test_other_effects_clear_context_and_do_not_acquire_new_payload_authority(effect):
    row = v5_read(
        [
            raw_room(
                events=[
                    *prefix(2, 1),
                    {"action": effect, "playerId": 1, "items": [{"id": 666, "modelId": 777}]},
                    {"action": "removeUsedMiracles", "items": []},
                ]
            )
        ]
    ).snapshots[0]
    assert not any(event.self_item_payload_bound for event in row.events)
    assert row.event_owners[-1].basis == "unresolved"
    assert "777" not in row.model_dump_json()


@pytest.mark.parametrize("read", [v2_read, v3_read, v4_read])
def test_historical_versions_keep_removal_redacted_and_unresolved(read):
    row = read([removal_room(items=[{"id": 4, "modelId": 215, "used": True}])]).snapshots[0]
    assert not row.events[-1].self_item_payload_bound
    assert row.event_owners[-1].basis == "unresolved"


def test_v1_removal_is_redacted_and_old_capture_cannot_be_upgraded_by_version_alone():
    room = removal_room(playerId=1, items=[{"id": 4, "modelId": 215, "used": True}])
    raw = node("register({}, () => {}); emit(input.room); return read();", room=room)
    assert (
        not AcquisitionProbeRead.model_validate_json(json.dumps(raw))
        .snapshots[0]
        .events[-1]
        .self_item_payload_bound
    )
    payload = v4_read([room]).model_dump(mode="json")
    payload["schema_version"] = 5
    with pytest.raises(ValidationError, match="ownership"):
        AcquisitionProbeReadV5.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "fields,kind",
    [
        ({}, "missing"),
        ({"items": None}, "null"),
        ({"items": []}, "array"),
        ({"items": "PRIVATE_REMOVAL"}, "other"),
    ],
)
def test_removal_wire_preserves_omitted_null_and_explicit_empty_arrays(fields, kind):
    capture = v5_read([removal_room(**fields)])
    assert capture.snapshots[0].event_item_wire[-1].items_kind == kind
    audit = audit_acquisition_batches((batch(capture),))
    assert audit.schema_version == 4
    assert audit.capture_schema_versions == (5,)
    assert audit.self_bound_removal_event_count == 1 and audit.self_bound_removal_item_count == 0
    assert audit.ambiguous_self_removal_event_count == (kind != "array")
    assert ("ambiguous_self_removals" in audit.collection_issues) == (kind != "array")
    assert audit.ambiguous_self_selection_event_count == 0
    assert "PRIVATE_REMOVAL" not in capture.model_dump_json()


def test_audit_counts_observations_not_operations_and_deduplicates_repeats():
    room = removal_room(items=[{"id": 4, "modelId": 215, "used": True}])
    capture = v5_read([room, room])
    audit = audit_acquisition_batches((batch(capture),))
    assert audit.self_bound_removal_event_count == audit.self_bound_removal_item_count == 1
    assert audit.repeated_server_version_count == 1
    assert audit.unresolved_removal_owner_event_count == 0
    unresolved = raw_room(events=[{"action": "removeItems", "playerId": 1, "items": []}])
    audit = audit_acquisition_batches((batch(v5_read([unresolved])),))
    assert audit.unresolved_removal_owner_event_count == 1
    assert "unresolved_removal_ownership" in audit.collection_issues
    assert not audit.training_eligible and not audit.promotion_eligible
    assert not audit.acquisition_rule_eligible


def test_inconsistent_removal_repeat_invalidates_carried_phase_without_exposing_private_values():
    seed = raw_room(events=prefix(2, 1))
    first = raw_room(
        events=[{"action": "removeUsedMiracles", "items": [{"id": 4, "modelId": 215}]}],
        updateCount=1,
    )
    changed = copy.deepcopy(first)
    changed["game"]["events"][0]["items"][0]["modelId"] = 23
    capture = v5_read([seed, first, changed])
    row = capture.snapshots[-1]
    assert row.phase_input_status == "inconsistent_repeat" and row.phase_before is None
    assert not row.events[-1].self_item_payload_bound
    assert row.event_item_wire[-1].items_kind == "redacted"


def test_malformed_self_removal_fields_are_classified_without_retaining_raw_strings():
    capture = v5_read([removal_room(items=[{"id": 4, "modelId": 215, "used": "PRIVATE_USED"}])])
    audit = audit_acquisition_batches((batch(capture),))
    assert audit.malformed_self_event_wire_count == 1
    assert "malformed_self_event_wire" in audit.collection_issues
    assert "PRIVATE_USED" not in capture.model_dump_json()


@pytest.mark.parametrize("items", [[{"id": 4, "modelId": 215}] * 513, ["PRIVATE_ITEM"]])
def test_rejected_removal_snapshot_breaks_context_and_cannot_bind_later_items(items):
    seed = raw_room(events=prefix(2, 1))
    invalid = raw_room(events=[{"action": "removeItems", "items": items}], updateCount=1)
    later = raw_room(events=[{"action": "removeUsedMiracles", "items": []}], updateCount=2)
    capture = v5_read([seed, invalid, later])
    assert capture.status.rejected_snapshot_count == 1
    assert [row.source_sequence for row in capture.snapshots] == [1, 3]
    assert capture.snapshots[-1].phase_input_status == "initial"
    assert not capture.snapshots[-1].events[-1].self_item_payload_bound
    assert "PRIVATE_ITEM" not in capture.model_dump_json()
    audit = audit_acquisition_batches((batch(capture),))
    assert audit.missing_source_sequence_count == 1
    assert "rejected_snapshots" in audit.collection_issues


@pytest.mark.parametrize("mutation", ["owner", "bound", "phase", "classvar", "wire", "version"])
def test_independent_validator_rejects_forged_removal_interpretation(mutation):
    payload = v5_read([removal_room(items=[])]).model_dump(mode="json")
    row = payload["snapshots"][0]
    if mutation == "owner":
        row["event_owners"][-1]["item_owner_player_id"] = 2
    elif mutation == "bound":
        row["events"][-1]["self_item_payload_bound"] = False
    elif mutation == "phase":
        row["phase_after"]["turn_player_id"] = 2
    elif mutation == "classvar":
        row["target_removal_duel_context"] = False
    elif mutation == "wire":
        row["event_item_wire"][-1]["items_kind"] = "redacted"
    else:
        payload["schema_version"] = 5.0
    with pytest.raises(ValidationError):
        AcquisitionProbeReadV5.model_validate_json(json.dumps(payload))


def test_v5_batch_pins_client_digest_and_exact_schema_integer():
    payload = batch(v5_read([removal_room(items=[])])).model_dump(mode="json")
    for change in (
        {"client_sha256": "a" * 64},
        {"input_sha256": "a" * 64},
        {"schema_version": 5.0},
        {"training_eligible": True},
    ):
        with pytest.raises(ValidationError):
            AcquisitionEvidenceBatchV5.model_validate_json(json.dumps(payload | change))


@pytest.mark.parametrize("action", REMOVALS)
def test_v5_durable_capture_and_read_only_cli_do_not_make_removal_native_or_training_ready(
    tmp_path, monkeypatch, action
):
    pytest.importorskip("godfield_sim")
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    owned = {"id": 4, "modelId": 215, "used": True}
    first = raw_room(
        events=[
            {"action": "startGame"},
            {"action": "gift", "playerId": 1, "item": owned},
            *prefix(2, 1),
        ]
    )
    first["game"]["players"][0]["items"] = [owned]
    final = raw_room(
        events=[{"action": action, "items": [owned]}, {"action": "endGame"}],
        updateCount=1,
        isOver=True,
    )
    final["game"]["players"][0]["items"] = []
    storage, run, recorder = store(tmp_path)
    trace = []
    append = storage.append_event

    def save(*args, **kwargs):
        result = append(*args, **kwargs)
        trace.append("saved")
        return result

    monkeypatch.setattr(storage, "append_event", save)
    asyncio.run(recorder.finalize(FakePage(v5_read([first, final]), trace=trace)))
    assert trace[:3] == ["read", "saved", "ack"]
    original = storage.path.read_bytes()
    report = audit_acquisition_run(storage.path, run.run_id)
    assert report["schema_version"] == 4 and report["declared_capture_schema_version"] == 5
    assert report["capture_schema_versions"] == [5] and report["capture_schema_matches_run_config"]
    assert report["self_bound_removal_item_count"] == 1 and report["final_poll_succeeded"]
    replay = audit_acquisition_replay_run(storage.path, run.run_id, catalog_path=CATALOG)
    assert replay["input_sha256"] == report["input_sha256"]
    assert replay["matched_initial_snapshot_count"] == 1
    assert replay["unsupported_snapshot_count"] == 1 and replay["mismatch_count"] == 0
    assert replay["results"][-1]["reason"] == "unsupported_inventory_event"
    assert not replay["complete_projection_replay"]
    assert not replay["training_eligible"] and not replay["acquisition_rule_eligible"]
    for command, expected in (("acquisition-evidence", report), ("acquisition-replay", replay)):
        result = CliRunner().invoke(
            app, ["runs", command, run.run_id, "--database", str(storage.path)]
        )
        assert result.exit_code == 0, result.stdout
        assert json.loads(result.stdout) == expected
    assert storage.path.read_bytes() == original


def test_v5_storage_failure_never_acknowledges_removal_payload(tmp_path, monkeypatch):
    storage, _run, recorder = store(tmp_path)
    page = FakePage(v5_read([removal_room(items=[])]))

    def fail(*_args, **_kwargs):
        raise RunStoreError("synthetic storage failure")

    monkeypatch.setattr(storage, "append_event", fail)
    with pytest.raises(RunStoreError):
        asyncio.run(recorder.poll(page))
    assert page.trace == ["read"]
