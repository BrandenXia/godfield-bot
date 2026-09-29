"""Synthetic private API transport parity; not official removal rule fixtures."""

import copy
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from godfield import RoomState, TransportError
from pydantic import ValidationError
from test_acquisition_evidence import raw_room, v5_read
from test_acquisition_v4 import prefix
from test_api_runtime import FakeClient, catalog_snapshot, write_api_catalog_snapshot
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import (
    audit_acquisition_batches,
    audit_acquisition_run,
    load_acquisition_run,
)
from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionCollectorSummary,
)
from godfield_bot.acquisition_replay import audit_acquisition_replay_run
from godfield_bot.api_account import PYGODFIELD_REVISION
from godfield_bot.api_acquisition import (
    PrivateAcquisitionEvidenceBatch,
    PrivateAcquisitionRecorder,
    PrivateAcquisitionSummary,
    private_acquisition_digest,
)
from godfield_bot.api_catalog import item_catalog_from_snapshot, read_api_catalog_snapshot
from godfield_bot.api_runtime import (
    ApiPolicyName,
    ApiRuntimeError,
    PrivateApiRunConfig,
    api_environment_fingerprint,
    run_private_api_observer,
)
from godfield_bot.cli import app
from godfield_bot.config import AppSettings
from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.outcome_replay import collect_outcome_replay
from godfield_bot.replay import collect_replay_samples
from godfield_bot.run_store import RunStore, RunStoreError

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
ENVIRONMENT = hashlib.sha256(
    f"pygodfield:{PYGODFIELD_REVISION}:catalog:{ACQUISITION_REVIEWED_CATALOG_SHA256}".encode()
).hexdigest()
USED = {"id": 4, "modelId": 215, "used": True}


def private_room(**fields):
    room = raw_room(**fields)
    room["game"]["players"][0]["userId"] = "loki-user"
    room["game"]["players"][1]["userId"] = "OTHER_USER_SECRET"
    return room


def metadata():
    return {
        "pygodfield_revision": PYGODFIELD_REVISION,
        "catalog_sha256": ACQUISITION_REVIEWED_CATALOG_SHA256,
        "acquisition_evidence_probe": True,
        "acquisition_evidence_schema_version": 5,
        "acquisition_evidence_transport": "api-polling",
        "acquisition_evidence_catalog_sha256": ACQUISITION_REVIEWED_CATALOG_SHA256,
        "acquisition_decoder_client_sha256": ACQUISITION_REVIEWED_CLIENT_SHA256,
        "collection_only": True,
        "training_eligible": False,
        "promotion_eligible": False,
    }


def recorder_at(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.start_run(
        RunSpec(
            mode=RunMode.PRIVATE,
            identity="ロキ-67",
            client_sha256=ENVIRONMENT,
            policy_id=ApiPolicyName.TACTICAL_HEURISTIC.value,
            config=metadata(),
        )
    )
    recorder = PrivateAcquisitionRecorder(
        store, run.run_id, identity="ロキ-67", api_environment_sha256=ENVIRONMENT
    )
    return store, run, recorder


def batches(store, run):
    return tuple(
        PrivateAcquisitionEvidenceBatch.model_validate_json(json.dumps(event.payload))
        for event in store.events(run.run_id)
        if event.payload.get("source_kind") == "private-api-acquisition-evidence-v5"
    )


def comparable(row):
    return row.model_dump(mode="json", exclude={"captured_at"})


@pytest.mark.parametrize("action", ["removeItems", "removeUsedMiracles"])
@pytest.mark.parametrize("reflect", [False, True])
@pytest.mark.parametrize("target_self", [False, True])
def test_ordered_removal_projection_matches_browser_v5(tmp_path, action, reflect, target_self):
    attacker, target = (2, 1) if target_self != reflect else (1, 2)
    rooms = [
        private_room(events=prefix(attacker, target)),
        private_room(
            updateCount=1,
            events=[
                *([{"action": "reflect"}] if reflect else []),
                {"action": action, "playerId": 99, "items": [USED]},
            ],
        ),
        private_room(updateCount=2, events=[{"action": "useDefenseItems", "items": []}]),
    ]
    store, run, recorder = recorder_at(tmp_path)
    for room in rooms:
        assert recorder.capture(room, user_id="loki-user")
    actual = [batch.snapshots[0] for batch in batches(store, run)]
    expected = v5_read(rooms).snapshots
    assert [comparable(row) for row in actual] == [comparable(row) for row in expected]
    assert actual[1].events[-1].self_item_payload_bound is target_self
    assert actual[1].phase_after.turn_player_id is None
    assert not actual[2].events[-1].self_item_payload_bound


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": None},
        {"items": []},
        {"items": "UNTRUSTED_SECRET"},
        {"items": [{"id": None, "modelId": 0, "used": "UNTRUSTED_SECRET"}]},
        {"item": USED, "items": [USED], "overflowItem": {}, "itemModelId": 215},
        {"item": [], "items": [{"id": 4.0, "fakeModelId": 215.0, "used": None}]},
        {"item": {"id": True, "modelId": -1, "fakeModelId": 2**53}},
    ],
)
def test_self_wire_shapes_and_repeat_invalidation_match_v5(tmp_path, payload):
    rooms = [private_room(events=prefix(2, 1))]
    frame = private_room(updateCount=1, events=[{"action": "removeUsedMiracles", **payload}])
    changed = copy.deepcopy(frame)
    changed["game"]["events"][0]["items"] = [USED]
    rooms += [frame, frame, changed]
    store, run, recorder = recorder_at(tmp_path)
    for room in rooms:
        assert recorder.capture(room, user_id="loki-user")
    actual = [batch.snapshots[0] for batch in batches(store, run)]
    assert [comparable(row) for row in actual] == [
        comparable(row) for row in v5_read(rooms).snapshots
    ]
    assert actual[2].phase_input_status == "repeat"
    assert "UNTRUSTED_SECRET" not in json.dumps([row.model_dump(mode="json") for row in actual])


@pytest.mark.parametrize("middle", ["gap", "membership", "unknown", "effect", "multiplayer"])
def test_polling_never_invents_skipped_or_cleared_phase_context(tmp_path, middle):
    first = private_room(events=prefix(2, 1))
    second = private_room(updateCount=1, events=[{"action": "removeUsedMiracles", "items": [USED]}])
    if middle == "gap":
        second["game"]["updateCount"] = 3
    elif middle == "membership":
        second["game"]["players"][1]["id"] = 3
    elif middle in {"unknown", "effect"}:
        first["game"]["events"].append(
            {"action": "UNKNOWN" if middle == "unknown" else "nextAttack"}
        )
    else:
        first["game"]["players"].append({"id": 3, "name": "THIRD_SECRET", "items": []})
        second["game"]["players"].append({"id": 3, "name": "THIRD_SECRET", "items": []})
    store, run, recorder = recorder_at(tmp_path)
    for room in (first, second):
        assert recorder.capture(room, user_id="loki-user")
    rows = [batch.snapshots[0] for batch in batches(store, run)]
    assert [comparable(row) for row in rows] == [
        comparable(row) for row in v5_read([first, second]).snapshots
    ]
    assert not rows[-1].events[-1].self_item_payload_bound
    if middle == "gap":
        report = audit_acquisition_batches(batches(store, run))
        assert report.server_gap_pair_count == 1
        assert report.missing_source_sequence_count == 0


def test_only_authorized_self_payload_is_stored(tmp_path):
    hidden = {"id": 666, "modelId": 777, "secret": "EVENT_SECRET"}
    room = private_room(
        events=[
            {"action": "gift", "playerId": 2, "item": hidden},
            {"action": "gift", "playerId": 1, "item": USED},
            *prefix(1, 2),
            {"action": "removeUsedMiracles", "items": [hidden]},
            {"action": ["UNKNOWN_SECRET"], "items": [hidden]},
        ]
    )
    room["game"]["players"][1]["items"] = [hidden]
    store, run, recorder = recorder_at(tmp_path)
    assert recorder.capture(room, user_id="loki-user")
    recorder.finalize()
    serialized = "".join(event.model_dump_json() for event in store.events(run.run_id))
    for secret in (
        '"instance_id":666',
        '"model_id":777',
        "EVENT_SECRET",
        "OTHER_USER_SECRET",
        "UNKNOWN_SECRET",
        "AUTH_SECRET",
        "ROOM_SECRET",
        "OPPONENT_SECRET",
        "loki-user",
        "ロキ-67",
    ):
        assert secret not in serialized
    row = batches(store, run)[0].snapshots[0]
    assert row.events[1].item.instance_id == 4
    assert not row.events[-1].self_item_payload_bound
    assert row.unreviewed_event_count == 1


@pytest.mark.parametrize("ambiguity", ["duplicate_user", "duplicate_name", "wrong_name"])
def test_ambiguous_self_is_rejected_and_clears_phase(tmp_path, ambiguity):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(events=prefix(2, 1)), user_id="loki-user")
    bad = private_room(updateCount=1)
    if ambiguity == "duplicate_user":
        bad["game"]["players"][1]["userId"] = "loki-user"
    elif ambiguity == "duplicate_name":
        bad["game"]["players"][1]["name"] = "ロキ-67"
    else:
        bad["game"]["players"][0]["name"] = "FORGED_SECRET"
    assert not recorder.capture(bad, user_id="loki-user")
    assert recorder.capture(
        private_room(updateCount=2, events=[{"action": "removeItems", "items": [USED]}]),
        user_id="loki-user",
    )
    recorder.finalize()
    saved = batches(store, run)
    assert len(saved[1].snapshots) == 0
    assert saved[1].status.rejected_snapshot_count == 1
    assert saved[-1].snapshots[0].phase_input_status == "initial"
    assert not saved[-1].snapshots[0].events[-1].self_item_payload_bound
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["missing_source_sequence_count"] == 1
    assert report["rejected_snapshot_count"] == report["read_error_count"] == 1
    assert "FORGED_SECRET" not in json.dumps(report)


@pytest.mark.parametrize("boundary", ["lobby", "absent_self", "read_failure"])
def test_boundaries_rotate_stream_without_reusing_owner(tmp_path, boundary):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(events=prefix(2, 1)), user_id="loki-user")
    first_stream = recorder.stream
    if boundary == "read_failure":
        recorder.read_failed()
    else:
        room = {"game": None} if boundary == "lobby" else private_room()
        if boundary == "absent_self":
            room["game"]["players"][0]["userId"] = "ANOTHER_ACCOUNT_SECRET"
        assert not recorder.capture(room, user_id="loki-user")
    recorder.capture(
        private_room(updateCount=1, events=[{"action": "removeUsedMiracles", "items": [USED]}]),
        user_id="loki-user",
    )
    recorder.finalize()
    assert recorder.stream != first_stream
    saved = batches(store, run)
    assert [batch.status.source_sequence for batch in saved] == [1, 1]
    assert saved[-1].snapshots[0].phase_input_status == "initial"
    assert not saved[-1].snapshots[0].events[-1].self_item_payload_bound
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["api_polled_stream_count"] == 2
    assert report["read_error_count"] == (boundary == "read_failure")


@pytest.mark.parametrize(
    "field,value",
    [
        ("events", None),
        ("events", [None] * 513),
        ("gf", -1),
        ("gf", True),
        ("updateCount", 2**53),
        ("players", None),
    ],
)
def test_invalid_raw_frames_have_bounded_sanitized_rejection(tmp_path, field, value):
    store, run, recorder = recorder_at(tmp_path)
    room = private_room()
    room["game"][field] = value
    assert not recorder.capture(room, user_id="loki-user")
    recorder.finalize()
    saved = batches(store, run)
    assert saved[0].snapshots == ()
    assert saved[0].status.source_sequence == saved[0].status.rejected_snapshot_count == 1
    assert recorder.acknowledged == 1


def test_invalid_self_items_reject_without_defaults_or_large_payload(tmp_path):
    store, run, recorder = recorder_at(tmp_path)
    for value in (None, "ITEM_SECRET", [{}] * 513, ["ITEM_SECRET"]):
        room = private_room()
        room["game"]["players"][0]["items"] = value
        assert not recorder.capture(room, user_id="loki-user")
    recorder.finalize()
    assert recorder.saved == 0 and recorder.rejected == 4
    assert "ITEM_SECRET" not in "".join(
        event.model_dump_json() for event in store.events(run.run_id)
    )


def test_new_match_cannot_carry_terminal_owner_context(tmp_path):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(isOver=True, events=prefix(2, 1)), user_id="loki-user")
    first_stream = recorder.stream
    recorder.capture(
        private_room(updateCount=1, events=[{"action": "removeItems", "items": [USED]}]),
        user_id="loki-user",
    )
    assert recorder.stream != first_stream
    row = batches(store, run)[-1].snapshots[0]
    assert row.phase_input_status == "initial" and row.source_sequence == 1
    assert not row.events[-1].self_item_payload_bound


def test_no_ack_or_phase_commit_before_durable_save(tmp_path, monkeypatch):
    store, run, recorder = recorder_at(tmp_path)

    def fail(*_args, **_kwargs):
        raise RunStoreError("storage unavailable")

    monkeypatch.setattr(store, "append_event", fail)
    with pytest.raises(RunStoreError):
        recorder.capture(private_room(events=prefix(2, 1)), user_id="loki-user")
    assert recorder.acknowledged == recorder.saved == 0
    assert recorder.previous is recorder.previous_stamp is None
    assert store.events(run.run_id) == ()


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 5.0},
        {"schema_version": True},
        {"client_sha256": "a" * 64},
        {"catalog_sha256": "a" * 64},
        {"api_environment_sha256": "a" * 64},
        {"pygodfield_revision": "a" * 40},
        {"input_sha256": "a" * 64},
        {"delivery_kind": "browser-snapshot"},
        {"training_eligible": True},
        {"promotion_eligible": True},
        {"acquisition_rule_eligible": True},
    ],
)
def test_private_envelope_provenance_and_eligibility_are_strict(tmp_path, change):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(), user_id="loki-user")
    payload = batches(store, run)[0].model_dump(mode="json") | change
    with pytest.raises(ValidationError):
        PrivateAcquisitionEvidenceBatch.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "counter,value",
    [
        ("hook_installed", True),
        ("listener_registrations", 1),
        ("dropped_snapshot_count", 1),
        ("hook_error_count", 1),
        ("acknowledged_sequence", 1),
    ],
)
def test_api_envelope_cannot_claim_browser_hook_or_early_ack(tmp_path, counter, value):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(), user_id="loki-user")
    saved = batches(store, run)[0]
    status = saved.status.model_copy(update={counter: value})
    payload = saved.model_dump(mode="json") | {
        "status": status.model_dump(mode="json"),
        "input_sha256": private_acquisition_digest(ENVIRONMENT, status, saved.snapshots),
    }
    with pytest.raises(ValidationError, match="delivery counters"):
        PrivateAcquisitionEvidenceBatch.model_validate_json(json.dumps(payload))


def test_private_summary_is_not_a_successful_browser_final_poll(tmp_path):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(events=[{"action": "startGame"}]), user_id="loki-user")
    recorder.capture(
        private_room(updateCount=1, isOver=True, events=[{"action": "endGame"}]),
        user_id="loki-user",
    )
    recorder.finalize()
    recorder.finalize()
    summaries = [
        event for event in store.events(run.run_id) if "summary" in event.payload["source_kind"]
    ]
    assert len(summaries) == 1
    summary = PrivateAcquisitionSummary.model_validate_json(json.dumps(summaries[0].payload))
    report = audit_acquisition_batches(batches(store, run), summaries=(summary,))
    assert report.api_polled_stream_count == 1 and report.evidence_delivery_kinds == (
        "api-polling",
    )
    assert report.hooked_stream_count == report.listening_stream_count == 0
    assert report.final_poll_succeeded is None and report.final_flush_succeeded is True
    assert report.collection_issues == ()
    with pytest.raises(ValueError, match="delivery kind"):
        audit_acquisition_batches(
            batches(store, run),
            summaries=(
                AcquisitionCollectorSummary(
                    saved_snapshot_count=2,
                    detected_source_gap_count=0,
                    read_error_count=0,
                    ack_error_count=0,
                    streams=summary.streams,
                    final_poll_succeeded=True,
                ),
            ),
        )
    with pytest.raises(ValueError, match="finalized"):
        recorder.capture(private_room(), user_id="loki-user")


@pytest.mark.parametrize(
    "field,value",
    [
        ("collection_only", False),
        ("training_eligible", True),
        ("pygodfield_revision", "a" * 40),
        ("acquisition_decoder_client_sha256", "a" * 64),
    ],
)
def test_loader_checks_api_run_provenance(tmp_path, field, value):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(), user_id="loki-user")
    recorder.finalize()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE runs SET config_json=? WHERE run_id=?",
            (json.dumps(metadata() | {field: value}), run.run_id),
        )
    with pytest.raises(ValueError, match="provenance"):
        load_acquisition_run(store.path, run.run_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"final_poll_succeeded": True},
        {"final_flush_succeeded": False},
        {"saved_snapshot_count": 2},
        {"detected_source_gap_count": 1},
    ],
)
def test_private_flush_summary_cannot_claim_wrong_delivery_or_counts(tmp_path, changes):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(), user_id="loki-user")
    recorder.finalize()
    payload = store.events(run.run_id)[-1].payload | changes
    with pytest.raises(ValidationError):
        PrivateAcquisitionSummary.model_validate_json(json.dumps(payload))


def test_private_flush_cannot_omit_or_substitute_saved_streams(tmp_path):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(), user_id="loki-user")
    recorder.finalize()
    payload = copy.deepcopy(store.events(run.run_id)[-1].payload)
    payload["streams"][0]["stream_id"] = "00000000-0000-4000-8000-000000000001"
    summary = PrivateAcquisitionSummary.model_validate_json(json.dumps(payload))
    with pytest.raises(ValueError, match="omits saved streams"):
        audit_acquisition_batches(batches(store, run), summaries=(summary,))


def test_private_read_only_audits_keep_removal_native_unsupported(tmp_path, monkeypatch):
    pytest.importorskip("godfield_sim")
    store, run, recorder = recorder_at(tmp_path)
    first = private_room(
        events=[
            {"action": "startGame"},
            {"action": "gift", "playerId": 1, "item": USED},
            *prefix(2, 1),
        ]
    )
    first["game"]["players"][0]["items"] = [USED]
    final = private_room(
        updateCount=1,
        isOver=True,
        events=[{"action": "removeUsedMiracles", "items": [USED]}, {"action": "endGame"}],
    )
    final["game"]["players"][0]["items"] = []
    recorder.capture(first, user_id="loki-user")
    recorder.capture(final, user_id="loki-user")
    recorder.finalize()
    original = store.path.read_bytes()
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["schema_version"] == 4 and report["client_sha256"] == ENVIRONMENT
    assert report["acquisition_decoder_client_sha256"] == ACQUISITION_REVIEWED_CLIENT_SHA256
    assert report["self_bound_removal_event_count"] == report["self_bound_removal_item_count"] == 1
    replay = audit_acquisition_replay_run(store.path, run.run_id, catalog_path=CATALOG)
    assert replay["input_sha256"] == report["input_sha256"]
    assert replay["matched_initial_snapshot_count"] == 1
    assert replay["mismatch_count"] == 0 and replay["unsupported_snapshot_count"] == 1
    assert replay["results"][-1]["reason"] == "unsupported_inventory_event"
    assert not replay["training_eligible"] and not replay["acquisition_rule_eligible"]
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    for command, expected in (("acquisition-evidence", report), ("acquisition-replay", replay)):
        result = CliRunner().invoke(
            app, ["runs", command, run.run_id, "--database", str(store.path)]
        )
        assert result.exit_code == 0, result.stdout
        assert json.loads(result.stdout) == expected
    assert store.path.read_bytes() == original


def api_frame(*, update=0, terminal=False, events=()):
    snapshot = read_api_catalog_snapshot(CATALOG)
    club = next(
        item.model_id for item in snapshot.items if item.raw.get("imageName") == "bronze-club"
    )
    room = private_room(
        updateCount=update, isOver=terminal, attackTurnPlayerId=1, events=list(events)
    )
    room["users"] = [
        {"id": "loki-user", "name": "ロキ-67"},
        {"id": "OTHER_USER_SECRET", "name": "Opponent"},
    ]
    room["entries"] = []
    for player in room["game"]["players"]:
        player.update(hp=30, mp=10, cp=10, team=0)
    room["game"]["players"][0]["items"] = [{"id": 11, "modelId": club}]
    room["game"]["players"][1]["hp"] = 0 if terminal else 30
    room["game"]["attacks"] = []
    return RoomState(room, item_catalog_from_snapshot(snapshot))


def fake_session(monkeypatch, frames):
    class Client(FakeClient):
        def __init__(self):
            super().__init__()
            self.frames = iter(frames)
            self.reads = 0
            self.commands = []

        def state(self):
            self.reads += 1
            value = next(self.frames)
            if isinstance(value, BaseException):
                raise value
            return value

        def submit(self, command):
            self.commands.append(command.to_dict())

    client = Client()

    @contextmanager
    def open_client(*_args, **_kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", open_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda _settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda _seconds: None)
    return client


def run_fake(tmp_path, *, enabled=True):
    return run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runtime.sqlite",
            catalog_snapshot=CATALOG,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=10,
            max_seconds=10,
            no_progress_seconds=10,
            acquisition_evidence_probe=enabled,
        ),
    )


def test_opt_in_capture_adds_no_reads_or_commands_and_excludes_exports(tmp_path, monkeypatch):
    commands = []
    for enabled in (False, True):
        directory = tmp_path / str(enabled)
        client = fake_session(monkeypatch, [api_frame(), api_frame(update=1, terminal=True)])
        run = run_fake(directory, enabled=enabled)
        assert run.status is RunStatus.COMPLETED and client.left
        assert client.reads == 2
        commands.append(client.commands)
        store = RunStore(directory / "runtime.sqlite")
        evidence = [event for event in store.events(run.run_id) if event.kind is EventKind.EVIDENCE]
        if not enabled:
            assert not evidence and "collection_only" not in run.config
            continue
        assert len(evidence) == 3
        assert run.config["collection_only"] is True
        assert run.config["training_eligible"] is run.config["promotion_eligible"] is False
        assert run.client_sha256 == api_environment_fingerprint(read_api_catalog_snapshot(CATALOG))
        events = store.events(run.run_id)
        first_capture = next(event.sequence for event in events if event.kind is EventKind.EVIDENCE)
        first_decision = next(
            event.sequence for event in events if event.kind is EventKind.DECISION
        )
        assert first_capture < first_decision
        summary = next(
            event for event in events if "summary" in str(event.payload.get("source_kind"))
        )
        assert summary.payload["final_flush_succeeded"] is True
        assert summary.payload["final_poll_succeeded"] is None
        samples, replay = collect_replay_samples(store)
        episodes, outcome = collect_outcome_replay(store)
        assert samples == episodes == ()
        assert replay.skipped["collection_only_run"] == outcome.skipped["collection_only_run"] == 1
    assert commands[0] == commands[1] and len(commands[0]) == 1


def test_capture_precedes_normalized_state_deduplication(tmp_path, monkeypatch):
    first = api_frame(events=prefix(2, 1))
    first.raw["game"]["attackTurnPlayerId"] = 2
    changed = copy.deepcopy(first.raw)
    changed["game"]["events"][-1]["items"] = [USED]
    repeat = RoomState(changed, item_catalog_from_snapshot(read_api_catalog_snapshot(CATALOG)))
    client = fake_session(monkeypatch, [first, repeat, api_frame(update=1, terminal=True)])
    run = run_fake(tmp_path)
    assert run.status is RunStatus.COMPLETED and client.reads == 3
    store = RunStore(tmp_path / "runtime.sqlite")
    assert len(batches(store, run)) == 3
    assert (
        len([event for event in store.events(run.run_id) if event.kind is EventKind.GAME_STATE])
        == 2
    )
    assert batches(store, run)[1].snapshots[0].phase_input_status == "inconsistent_repeat"


def test_collection_enters_next_match_instead_of_finishing_a_stale_terminal(tmp_path, monkeypatch):
    client = fake_session(
        monkeypatch,
        [api_frame(update=17, terminal=True), api_frame(), api_frame(update=1, terminal=True)],
    )
    run = run_fake(tmp_path)
    assert run.status is RunStatus.COMPLETED and client.reads == 3
    assert client.entry_teams == [0] and len(client.commands) == 1
    store = RunStore(tmp_path / "runtime.sqlite")
    assert [batch.snapshots[0].update_count for batch in batches(store, run)] == [0, 1]
    assert run.outcome["in_match_actions"] == 1


def test_runtime_storage_failure_prevents_policy_dispatch_and_cleans_up(tmp_path, monkeypatch):
    client = fake_session(monkeypatch, [api_frame()])
    append = RunStore.append_event

    def fail_batch(store, run_id, kind, payload, **kwargs):
        if isinstance(payload, PrivateAcquisitionEvidenceBatch):
            raise RunStoreError("storage unavailable")
        return append(store, run_id, kind, payload, **kwargs)

    monkeypatch.setattr(RunStore, "append_event", fail_batch)
    run = run_fake(tmp_path)
    assert run.status is RunStatus.FAILED
    assert client.commands == [] and client.left and client.reads == 1


@pytest.mark.parametrize(
    "failure",
    [
        KeyboardInterrupt(),
        RuntimeError("PRIVATE_SECRET"),
        TransportError("PRIVATE_SECRET", status=503),
    ],
)
def test_runtime_finalizes_capture_on_interrupt_failure_or_recovery(tmp_path, monkeypatch, failure):
    first = api_frame(events=prefix(2, 1))
    first.raw["game"]["attackTurnPlayerId"] = 2
    frames = [first, failure]
    if isinstance(failure, TransportError):
        frames.append(api_frame(update=2, terminal=True))
    client = fake_session(monkeypatch, frames)
    run = run_fake(tmp_path)
    assert client.left
    expected = (
        RunStatus.COMPLETED
        if isinstance(failure, TransportError)
        else RunStatus.ABORTED
        if isinstance(failure, KeyboardInterrupt)
        else RunStatus.FAILED
    )
    assert run.status is expected
    store = RunStore(tmp_path / "runtime.sqlite")
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["collector_summary_count"] == 1 and report["final_flush_succeeded"] is True
    assert "PRIVATE_SECRET" not in "".join(
        event.model_dump_json() for event in store.events(run.run_id)
    )
    if isinstance(failure, TransportError):
        assert report["api_polled_stream_count"] == 2 and report["read_error_count"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"max_seconds": 0},
        {"entry_team": 1},
        {"policy": ApiPolicyName.HEURISTIC},
        {"policy": ApiPolicyName.NEURAL_SHADOW, "model_directory": Path("models/unused")},
    ],
)
def test_capture_configuration_rejects_unsafe_combinations(changes):
    with pytest.raises(ValidationError, match="private acquisition"):
        PrivateApiRunConfig(
            **{
                "enter_match": True,
                "policy": ApiPolicyName.TACTICAL_HEURISTIC,
                "max_in_match_actions": 10,
                "acquisition_evidence_probe": True,
                **changes,
            }
        )


def test_unreviewed_catalog_rejected_before_credentials_or_network(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), path)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda _settings: pytest.fail("reached credentials"),
    )
    with pytest.raises(ApiRuntimeError, match="reviewed 2026-09-21 catalog"):
        run_private_api_observer(
            AppSettings(state_root=tmp_path / "state"),
            PrivateApiRunConfig(
                room_id="private-room",
                catalog_snapshot=path,
                enter_match=True,
                policy=ApiPolicyName.TACTICAL_HEURISTIC,
                max_in_match_actions=10,
                acquisition_evidence_probe=True,
            ),
        )


def test_cli_forwards_finite_collection_without_model(tmp_path, monkeypatch):
    store, run, _recorder = recorder_at(tmp_path)
    result = store.finish_run(run.run_id, RunStatus.ABORTED, outcome={"reason": "test"})

    def run_private(_settings, config, **_kwargs):
        assert config.acquisition_evidence_probe
        assert config.entry_team == 0 and config.max_seconds == 900
        assert config.policy is ApiPolicyName.TACTICAL_HEURISTIC and config.model_directory is None
        assert config.catalog_snapshot == CATALOG
        return result

    monkeypatch.setattr("godfield_bot.api_runtime.run_private_api_observer", run_private)
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    response = CliRunner().invoke(
        app,
        [
            "api",
            "play-private",
            "--confirm-play",
            "--room-id",
            "private-room",
            "--acquisition-evidence-probe",
            "--catalog-snapshot",
            str(CATALOG),
            "--max-seconds",
            "900",
            "--team",
            "0",
        ],
    )
    assert response.exit_code == 0, response.stdout
    assert json.loads(response.stdout)["run_id"] == run.run_id


def test_browser_summary_cannot_be_injected_into_private_run(tmp_path):
    store, run, recorder = recorder_at(tmp_path)
    recorder.capture(private_room(), user_id="loki-user")
    summary = AcquisitionCollectorSummary(
        saved_snapshot_count=1,
        detected_source_gap_count=0,
        read_error_count=0,
        ack_error_count=0,
        streams=(),
        final_poll_succeeded=True,
    )
    store.append_event(run.run_id, EventKind.EVIDENCE, summary)
    with pytest.raises(ValueError, match="browser acquisition summary"):
        load_acquisition_run(store.path, run.run_id)
