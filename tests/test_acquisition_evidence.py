import asyncio
import json
import shutil
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from playwright.async_api import Error as PlaywrightError
from pydantic import ValidationError
from typer.main import get_command
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches, audit_acquisition_run
from godfield_bot.acquisition_policy import ACQUISITION_POLICY_ID
from godfield_bot.acquisition_probe import (
    ACQUISITION_ACK_SCRIPT,
    ACQUISITION_READ_SCRIPT,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionEvidenceBatch,
    AcquisitionProbeRead,
    AcquisitionProbeStatus,
    AcquisitionRecorder,
    AcquisitionSnapshot,
    acquisition_batch_digest,
    acquisition_probe_init_script,
    install_acquisition_probe,
)
from godfield_bot.acquisition_v2 import (
    AcquisitionEvidenceBatchV2,
    AcquisitionProbeReadV2,
)
from godfield_bot.acquisition_v3 import AcquisitionProbeReadV3
from godfield_bot.acquisition_v4 import AcquisitionProbeReadV4
from godfield_bot.cli import app
from godfield_bot.config import AppSettings
from godfield_bot.domain.game import GameState, PlayerState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation
from godfield_bot.domain.reference import ClientFingerprint
from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.run_store import RunStore, RunStoreError
from godfield_bot.runner import TrainingCampaignSummary, TrainingRunConfig, run_training_observer

STREAM = "00000000-0000-4000-8000-000000000001"
SECOND_STREAM = "00000000-0000-4000-8000-000000000002"
CLIENT = ACQUISITION_REVIEWED_CLIENT_SHA256
CATALOG = "b" * 64
CATALOG_PATH = Path("data/snapshots/2026-09-21/api-catalog-en.json")


@pytest.fixture(autouse=True)
def avoid_retaining_cli_capture(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)


def snapshot(sequence=1, *, update=None, **changes):
    value = {
        "source_sequence": sequence,
        "captured_at": "2030-01-01T00:00:00Z",
        "field_number": 1,
        "update_count": sequence - 1 if update is None else update,
        "self_player_id": 1,
        "player_count": 2,
        "is_over": False,
        "attack_turn_player_id": 1,
        "self_items": [
            {
                "raw_index": 0,
                "instance_id": 1,
                "model_id": 10,
                "fake_model_id": None,
                "used": False,
            }
        ],
        "events": [],
        "unreviewed_event_count": 0,
        "redacted_item_event_count": 0,
    }
    value.update(changes)
    return AcquisitionSnapshot.model_validate_json(json.dumps(value))


def event(action="gift", *, actor=1, bound=False, **changes):
    value = {
        "event_index": 0,
        "action": action,
        "player_id": actor,
        "target_player_id": None,
        "self_item_payload_bound": bound,
        "item": None,
        "items": [],
        "overflow_item": None,
        "item_model_id": None,
    }
    value.update(changes)
    return value


def probe_read(*snapshots, stream=STREAM, acknowledged=0, **status_changes):
    status = AcquisitionProbeStatus(
        stream_id=stream,
        source_sequence=max((row.source_sequence for row in snapshots), default=0),
        acknowledged_sequence=acknowledged,
        pending_snapshot_count=len(snapshots),
        dropped_snapshot_count=0,
        rejected_snapshot_count=0,
        hook_error_count=0,
        hook_installed=True,
        listener_registrations=1,
    ).model_copy(update=status_changes)
    return AcquisitionProbeRead(schema_version=1, status=status, snapshots=tuple(snapshots))


def batch(*snapshots, **status_changes):
    read = probe_read(*snapshots, **status_changes)
    return AcquisitionEvidenceBatch(
        observed_at=datetime.now(UTC),
        client_sha256=CLIENT,
        catalog_sha256=CATALOG,
        input_sha256=acquisition_batch_digest(CLIENT, CATALOG, read.status, read.snapshots),
        status=read.status,
        snapshots=read.snapshots,
    )


NODE_HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const calls = [], unsubscribe = function() {};
const firebase = {onSnapshot: function(...args) {
  calls.push({args, owner: this}); return unsubscribe;
}};
const window = {crypto: {randomUUID: () => input.stream}};
const context = vm.createContext({window});
if (input.before) window.firebase = firebase;
if (input.blocked) Object.defineProperty(firebase, 'onSnapshot', {writable: false});
if (input.fixed) Object.defineProperty(window, 'firebase', {value: firebase, configurable: false});
vm.runInContext(input.init, context);
if (!input.before && !input.fixed) window.firebase = firebase;
const read = () => vm.runInContext('(' + input.read + ')()', context);
const ack = (value) => {context.ackValue = value;
  return vm.runInContext('(' + input.ack + ')(ackValue)', context);};
const register = (...args) => window.firebase.onSnapshot(...args);
const emit = (room, extra) => {
  const observer = calls[calls.length - 1].args.find((arg, index) => index > 0 &&
    (typeof arg === 'function' || arg && typeof arg.next === 'function'));
  const doc = {data: () => room};
  return typeof observer === 'function' ? observer.call(input.owner, doc, extra) :
    observer.next(doc, extra);
};
context.tools = {window, calls, unsubscribe, firebase, read, ack, register, emit, input,
  rerun: () => vm.runInContext(input.init, context)};
const result = vm.runInContext('(function() { const {window, calls, unsubscribe, firebase, ' +
  'read, ack, register, emit, input, rerun} = tools; ' + input.exercise + '})()', context);
process.stdout.write(JSON.stringify(result));
"""


def node(exercise, *, before=False, include_dream=False, schema_version=1, **kwargs):
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node is required for synthetic passive-hook verification")
    init = acquisition_probe_init_script("ロキ-67", capacity=8, schema_version=schema_version)
    if include_dream:

        class Context:
            async def add_init_script(self, *, script):
                self.script = script

        context = Context()
        asyncio.run(
            install_acquisition_probe(context, identity="ロキ-67", capacity=8, include_dream=True)
        )
        init = context.script
    inputs = {
        "init": init,
        "read": ACQUISITION_READ_SCRIPT,
        "ack": ACQUISITION_ACK_SCRIPT,
        "stream": STREAM,
        "before": before,
        "owner": {"sentinel": 7},
        "exercise": exercise,
        **kwargs,
    }
    result = subprocess.run(
        [executable, "-e", NODE_HARNESS],
        input=json.dumps(inputs),
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def raw_room(*, events=None, **changes):
    game = {
        "gf": 1,
        "updateCount": 0,
        "isOver": False,
        "attackTurnPlayerId": 1,
        "players": [
            {"id": 1, "name": "ロキ-67", "items": [{"id": 1, "modelId": 10, "used": False}]},
            {"id": 2, "name": "OPPONENT_SECRET", "items": [{"id": 666, "modelId": 777}]},
        ],
        "events": events or [],
        "authToken": "AUTH_SECRET",
    }
    game.update(changes)
    return {"game": game, "privateRoomId": "ROOM_SECRET"}


@pytest.mark.parametrize("before", [False, True])
@pytest.mark.parametrize("schema_version", [1, 2, 3, 4])
def test_actual_script_saves_ordered_queue_and_only_acknowledges_read_prefix(
    before, schema_version
):
    result = node(
        """
      register({}, () => {});
      for (let i=0; i<10; i++) {input.room.game.updateCount=i; emit(input.room);}
      const first = read(), second = read();
      input.room.game.updateCount=10; emit(input.room);
      const wrong = ack({stream_id: 'different', sequence: 10});
      const accepted = ack({stream_id: input.stream, sequence: 10});
      return {first, second, wrong, accepted, remaining: read()};
    """,
        before=before,
        schema_version=schema_version,
        room=raw_room(),
    )
    assert result["first"] == result["second"]
    assert [r["source_sequence"] for r in result["first"]["snapshots"]] == list(range(3, 11))
    assert result["first"]["status"]["dropped_snapshot_count"] == 2
    assert not result["wrong"] and result["accepted"]
    assert [r["source_sequence"] for r in result["remaining"]["snapshots"]] == [11]
    parser = {
        1: AcquisitionProbeRead,
        2: AcquisitionProbeReadV2,
        3: AcquisitionProbeReadV3,
        4: AcquisitionProbeReadV4,
    }[schema_version]
    parser.model_validate_json(json.dumps(result["remaining"]))


def test_actual_script_redacts_opponent_unknown_and_unbound_payloads():
    hidden = {"id": 666, "modelId": 777, "secret": "EVENT_SECRET"}
    result = node(
        "register({}, () => {}); emit(input.room); return read();",
        room=raw_room(
            events=[
                {"action": "gift", "playerId": 2, "item": hidden},
                {"action": "unreviewed", "playerId": 1, "item": hidden},
                {"action": "addItem", "playerId": 1, "item": hidden},
                {
                    "action": "gift",
                    "playerId": 1,
                    "item": {"id": 3, "modelId": 12},
                    "overflowItem": {"id": 4, "fakeModelId": 14, "used": True},
                },
            ]
        ),
    )
    row = AcquisitionProbeRead.model_validate_json(json.dumps(result)).snapshots[0]
    assert row.unreviewed_event_count == 1
    assert row.redacted_item_event_count == 2
    assert row.events[0].item is None and row.events[1].item is None
    assert row.events[2].item.instance_id == 3
    assert row.events[2].item.used is None
    assert row.events[2].overflow_item.fake_model_id == 14
    serialized = json.dumps(result)
    for secret in ("666", "777", "EVENT_SECRET", "AUTH_SECRET", "ROOM_SECRET", "OPPONENT_SECRET"):
        assert secret not in serialized


def test_actual_script_never_guesses_an_ambiguous_self_and_enforces_payload_bounds():
    ambiguous = raw_room()
    ambiguous["game"]["players"][1]["name"] = "ロキ-67"
    too_large = raw_room()
    too_large["game"]["players"][0]["items"] = [{"id": 1}] * 513
    result = node(
        """
      register({}, () => 67);
      const values = input.rooms.map((room) => emit(room));
      return {values, read:read()};
    """,
        rooms=[ambiguous, too_large],
    )
    assert result["values"] == [67, 67]
    assert result["read"]["status"]["rejected_snapshot_count"] == 2
    assert result["read"]["status"]["source_sequence"] == 2
    assert not result["read"]["snapshots"]


def test_actual_script_preserves_function_observer_semantics_and_idempotence():
    result = node(
        """
      let owner, extra, invocations=0;
      const first = window.firebase.onSnapshot;
      rerun();
      const same = first === window.firebase.onSnapshot;
      const returned = register({}, {includeMetadataChanges: true}, function(doc, value) {
        owner=this; extra=value; invocations++; return 67;
      });
      const value = emit(input.room, 'extra');
      return {same, value, invocations, owner, extra, unsub: returned === unsubscribe,
        originalOwner: calls[0].owner === firebase, read: read()};
    """,
        room=raw_room(),
    )
    assert result["same"] and result["unsub"] and result["originalOwner"]
    assert result["owner"] == {"sentinel": 7}
    assert result["extra"] == "extra" and result["value"] == 67 and result["invocations"] == 1
    assert result["read"]["status"]["source_sequence"] == 1


def test_actual_script_preserves_observer_methods_and_original_callback_errors():
    result = node(
        """
      const receiver = {next(doc, value) {this.nextValue=value; return 3;},
        error(value) {this.errorValue=value;}, complete() {this.completed=true;}};
      register({}, {includeMetadataChanges: true}, receiver);
      const value=emit(input.room, 67), wrapped=calls[0].args[2];
      wrapped.error('expected'); wrapped.complete();
      register({}, () => {throw new Error('application callback');});
      let error;
      try {emit(input.room);} catch (caught) {error=caught.message;}
      return {value, receiver, error, read: read()};
    """,
        room=raw_room(),
    )
    assert result["value"] == 3 and result["receiver"]["nextValue"] == 67
    assert result["receiver"]["errorValue"] == "expected" and result["receiver"]["completed"]
    assert result["error"] == "application callback"
    assert result["read"]["status"]["rejected_snapshot_count"] == 0


@pytest.mark.parametrize(
    "changed", [{"updateCount": -1}, {"events": None}, {"updateCount": "1"}, {"gf": 2**53}]
)
def test_actual_script_reports_invalid_snapshots_without_interrupting_callback(changed):
    room = raw_room(**changed)
    room["game"].update(changed)
    result = node(
        "register({}, () => 67); return {value:emit(input.room), read:read()};",
        room=room,
    )
    assert result["value"] == 67
    assert result["read"]["status"]["rejected_snapshot_count"] == 1
    assert result["read"]["status"]["source_sequence"] == 1
    assert not result["read"]["snapshots"]


def test_actual_script_preserves_unknown_flags_and_dream_probe():
    room = raw_room()
    del room["game"]["isOver"]
    del room["game"]["players"][0]["items"][0]["used"]
    result = node(
        """
      register({}, () => {}); emit(input.room);
      return {acquisition:read(), dream:window.__godfieldDreamEvidenceV1};
    """,
        include_dream=True,
        room=room,
    )
    assert result["acquisition"]["snapshots"][0]["is_over"] is None
    assert result["acquisition"]["snapshots"][0]["self_items"][0]["used"] is None
    assert result["dream"]["sequence"] == 1
    assert result["dream"]["latest"]["self"]["player_id"] == 1


@pytest.mark.parametrize("option", ["blocked", "fixed"])
def test_actual_script_records_hook_restrictions_without_breaking_initialization(option):
    result = node("return read();", **{option: True})
    assert result["status"]["hook_error_count"] == 1


class FakePage:
    def __init__(self, read, *, trace=None):
        self.read = read
        self.trace = trace if trace is not None else []
        self.fail_read = self.fail_ack = False
        self.ack_result = True

    async def evaluate(self, script, arg=None):
        if script == ACQUISITION_READ_SCRIPT:
            self.trace.append("read")
            if self.fail_read:
                raise PlaywrightError("READ_SECRET")
            return (
                self.read.model_dump(mode="json")
                if isinstance(
                    self.read,
                    (
                        AcquisitionProbeRead,
                        AcquisitionProbeReadV2,
                        AcquisitionProbeReadV3,
                        AcquisitionProbeReadV4,
                    ),
                )
                else self.read
            )
        assert script == ACQUISITION_ACK_SCRIPT
        self.trace.append("ack")
        if self.fail_ack:
            raise PlaywrightError("ACK_SECRET")
        if self.ack_result:
            self.read = type(self.read)(
                schema_version=self.read.schema_version,
                status=self.read.status.model_copy(
                    update={
                        "pending_snapshot_count": 0,
                        "acknowledged_sequence": arg["sequence"],
                    }
                ),
                snapshots=(),
            )
        return self.ack_result


def make_store(tmp_path):
    database = tmp_path / "runs.sqlite"
    store = RunStore(database)
    run = store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256=CLIENT,
            policy_id="safe-observer-v0",
            config={
                "acquisition_evidence_probe": True,
                "acquisition_evidence_catalog_sha256": CATALOG,
            },
        )
    )
    return store, run


def recorder(store, run):
    return AcquisitionRecorder(store, run.run_id, client_sha256=CLIENT, catalog_sha256=CATALOG)


def test_recorder_durable_save_precedes_ack_and_failed_storage_never_acks(tmp_path, monkeypatch):
    store, run = make_store(tmp_path)
    trace = []
    page = FakePage(probe_read(snapshot()), trace=trace)
    original = store.append_event

    def append(*args, **kwargs):
        result = original(*args, **kwargs)
        trace.append("saved")
        return result

    monkeypatch.setattr(store, "append_event", append)
    assert asyncio.run(recorder(store, run).poll(page))
    assert trace == ["read", "saved", "ack"]

    def fail(*_args, **_kwargs):
        raise RunStoreError("storage failed")

    monkeypatch.setattr(store, "append_event", fail)
    trace.clear()
    page = FakePage(probe_read(snapshot(2)), trace=trace)
    with pytest.raises(RunStoreError):
        asyncio.run(recorder(store, run).poll(page))
    assert trace == ["read"]


@pytest.mark.parametrize("failure", ["fail_ack", "ack_result"])
def test_recorder_ack_retry_does_not_duplicate_saved_rows(tmp_path, failure):
    store, run = make_store(tmp_path)
    writer = recorder(store, run)
    page = FakePage(probe_read(snapshot()))
    setattr(page, failure, failure == "fail_ack")
    assert not asyncio.run(writer.poll(page))
    page.fail_ack, page.ack_result = False, True
    assert asyncio.run(writer.poll(page))
    asyncio.run(writer.finalize(page))
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["snapshot_count"] == 1
    assert report["duplicate_source_snapshot_count"] == 0
    assert report["ack_error_count"] == 1
    assert report["final_poll_succeeded"] is True
    assert "ACK_SECRET" not in json.dumps(report)


def test_recorder_read_failure_is_nonfatal_and_never_acks(tmp_path):
    store, run = make_store(tmp_path)
    page = FakePage(None)
    writer = recorder(store, run)
    assert not asyncio.run(writer.poll(page))
    assert page.trace == ["read"]
    page.fail_read = True
    asyncio.run(writer.finalize(page))
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["read_error_count"] == 2 and report["final_poll_succeeded"] is False
    assert report["snapshot_count"] == 0
    assert "no_saved_snapshots" in report["collection_issues"]


@pytest.mark.parametrize("phase", ["read", "ack"])
def test_recorder_stalled_evaluation_has_bounded_timeout(tmp_path, monkeypatch, phase):
    store, run = make_store(tmp_path)
    writer = recorder(store, run)
    monkeypatch.setattr("godfield_bot.acquisition_probe.ACQUISITION_IO_TIMEOUT_SECONDS", 0.01)

    class StalledPage(FakePage):
        async def evaluate(self, script, arg=None):
            if script == (ACQUISITION_READ_SCRIPT if phase == "read" else ACQUISITION_ACK_SCRIPT):
                await asyncio.Event().wait()
            return await super().evaluate(script, arg)

    assert not asyncio.run(writer.poll(StalledPage(probe_read(snapshot()))))
    report = audit_acquisition_run(store.path, run.run_id)
    assert report[f"{phase}_error_count"] == 1
    assert report["snapshot_count"] == (0 if phase == "read" else 1)


def test_recorder_separates_reload_streams_and_detects_missing_prefix(tmp_path):
    store, run = make_store(tmp_path)
    writer = recorder(store, run)
    page = FakePage(probe_read(snapshot(3), snapshot(4), dropped_snapshot_count=2))
    assert asyncio.run(writer.poll(page))
    page.read = probe_read(snapshot(), stream=SECOND_STREAM)
    assert asyncio.run(writer.poll(page))
    asyncio.run(writer.finalize(page))
    report = audit_acquisition_run(store.path, run.run_id)
    assert report["stream_count"] == 2 and report["snapshot_count"] == 3
    assert report["missing_source_sequence_count"] == report["dropped_snapshot_count"] == 2
    assert report["adjacent_pair_count"] == 1


def test_audit_deduplicates_server_events_and_preserves_unknown_flags():
    first = snapshot(events=[event("startGame")])
    repeated = first.model_copy(update={"source_sequence": 2})
    again = first.model_copy(update={"source_sequence": 3})
    final = snapshot(
        4,
        update=1,
        is_over=True,
        events=[event()],
        self_items=[
            {
                "raw_index": 0,
                "instance_id": 1,
                "model_id": None,
                "fake_model_id": 12,
                "used": None,
            }
        ],
    )
    report = audit_acquisition_batches((batch(first, repeated, again, final),))
    assert report.reviewed_event_counts == {"gift": 1, "startGame": 1}
    assert report.repeated_server_version_count == 2
    assert report.adjacent_pair_count == 1
    assert report.unknown_used_flag_count == 1
    assert report.start_game_event_seen and report.terminal_snapshot_seen
    assert not report.training_eligible and not report.acquisition_rule_eligible
    assert "passed" not in report.model_dump()


@pytest.mark.parametrize(
    "middle",
    [
        snapshot(2, self_player_id=2),
        snapshot(2, field_number=0),
        snapshot(3, update=2),
        snapshot(2, update=4),
        snapshot(
            2,
            self_items=[
                {
                    "raw_index": 0,
                    "instance_id": None,
                    "model_id": 10,
                    "fake_model_id": None,
                    "used": False,
                }
            ],
        ),
    ],
)
def test_audit_never_bridges_boundaries_gaps_or_invalid_ids(middle):
    after = snapshot(middle.source_sequence + 1, update=middle.update_count + 1)
    report = audit_acquisition_batches((batch(snapshot(), middle, after),))
    assert report.adjacent_pair_count <= 1
    assert (
        report.boundary_pair_count
        + report.server_gap_pair_count
        + report.invalid_item_identity_snapshot_count
        > 0
    )


def test_audit_inconsistent_repeated_version_breaks_next_pair():
    report = audit_acquisition_batches(
        (
            batch(
                snapshot(),
                snapshot(2, update=0, is_over=True),
                snapshot(3, update=1),
            ),
        )
    )
    assert report.inconsistent_server_version_count == 1
    assert report.adjacent_pair_count == 0


@pytest.mark.parametrize("boundary", ["source_gap", "server_gap", "self", "players", "invalid"])
def test_lifecycle_observation_counts_do_not_cross_unsafe_pairs(boundary):
    first = snapshot(
        self_items=[
            {"raw_index": 0, "instance_id": 1, "model_id": 215, "fake_model_id": None, "used": None}
        ]
    )
    second = snapshot(
        2,
        self_items=[
            {
                "raw_index": 0,
                "instance_id": 1,
                "model_id": 215,
                "fake_model_id": None,
                "used": True,
            },
            {"raw_index": 1, "instance_id": 2, "model_id": 23, "fake_model_id": None, "used": None},
        ],
    )
    if boundary == "source_gap":
        second = second.model_copy(update={"source_sequence": 3})
    elif boundary == "server_gap":
        second = second.model_copy(update={"update_count": 3})
    elif boundary == "self":
        second = second.model_copy(update={"self_player_id": 2})
    elif boundary == "players":
        second = second.model_copy(update={"player_count": 3})
    else:
        second = second.model_copy(
            update={"self_items": (second.self_items[0].model_copy(update={"instance_id": None}),)}
        )
    report = audit_acquisition_batches((batch(first, second),))
    assert report.raw_used_true_observation_count == 1
    assert report.owned_inventory_growth_pair_count == 0
    assert report.client_interpreted_used_activation_count == 0


@pytest.mark.parametrize("replaced", ["model", "fake_model", "gift"])
def test_used_activation_does_not_treat_replaced_or_changed_identity_as_retained(replaced):
    initial = {
        "raw_index": 0,
        "instance_id": 1,
        "model_id": 215,
        "fake_model_id": None,
        "used": None,
    }
    current = {**initial, "used": True}
    events = []
    if replaced == "model":
        current["model_id"] = 211
    elif replaced == "fake_model":
        current["fake_model_id"] = 211
    else:
        events = [event("gift", bound=True, item=current)]
    report = audit_acquisition_batches(
        (batch(snapshot(self_items=[initial]), snapshot(2, self_items=[current], events=events)),)
    )
    assert report.client_interpreted_used_activation_count == 0


def test_missing_raw_used_flags_remain_unknown_and_unpinned_client_is_not_interpreted():
    first = snapshot(
        self_items=[
            {"raw_index": 0, "instance_id": 1, "model_id": 215, "fake_model_id": None, "used": None}
        ]
    )
    second = snapshot(
        2,
        self_items=[
            {"raw_index": 0, "instance_id": 1, "model_id": 215, "fake_model_id": None, "used": True}
        ],
    )
    saved = batch(first, second)
    report = audit_acquisition_batches((saved,))
    assert report.unknown_used_flag_count == report.raw_used_true_observation_count == 1
    assert report.client_interpreted_used_activation_count == 1
    other_client = "c" * 64
    saved = saved.model_copy(
        update={
            "client_sha256": other_client,
            "input_sha256": acquisition_batch_digest(
                other_client, saved.catalog_sha256, saved.status, saved.snapshots
            ),
        }
    )
    report = audit_acquisition_batches((saved,))
    assert not report.pinned_client_interpretation_applied
    assert report.client_interpreted_used_activation_count == 0
    assert report.unknown_used_flag_count == 1


def test_audit_is_read_only_deterministic_and_rejects_digest_tampering(tmp_path):
    store, run = make_store(tmp_path)
    store.append_event(run.run_id, EventKind.EVIDENCE, batch(snapshot()))
    before = store.path.read_bytes()
    report = audit_acquisition_run(store.path, run.run_id)
    assert report == audit_acquisition_run(store.path, run.run_id)
    assert store.path.read_bytes() == before
    with sqlite3.connect(store.path) as connection:
        row = connection.execute("SELECT payload_json FROM events").fetchone()
        value = json.loads(row[0])
        value["snapshots"][0]["self_items"][0]["model_id"] = 999
        connection.execute("UPDATE events SET payload_json = ?", (json.dumps(value),))
    with pytest.raises(ValidationError, match="digest differs"):
        audit_acquisition_run(store.path, run.run_id)
    result = CliRunner().invoke(
        app, ["runs", "acquisition-evidence", run.run_id, "--database", str(store.path)]
    )
    assert result.exit_code == 1
    assert "schema or content digest mismatch" in result.output
    assert "999" not in result.output
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.Error):
        audit_acquisition_run(missing, run.run_id)
    assert not missing.exists()


@pytest.mark.parametrize(
    "bad",
    [
        {"source_sequence": True},
        {"source_sequence": "1"},
        {"events": [event(bound=True, actor=2)]},
        {"events": [event("unreviewed")]},
        {"captured_at": "2030-01-01T00:00:00"},
    ],
)
def test_strict_schema_rejects_ambiguous_versions_and_unbound_events(bad):
    with pytest.raises(ValidationError):
        snapshot(**bad)


def test_config_and_cli_expose_opt_in_only_and_read_only_audit(tmp_path):
    config = TrainingRunConfig(expected_client_sha256=CLIENT)
    assert not config.acquisition_evidence_probe
    with pytest.raises(ValidationError, match="pinned API catalog"):
        TrainingRunConfig(expected_client_sha256=CLIENT, acquisition_evidence_probe=True)
    with pytest.raises(ValidationError):
        TrainingRunConfig(expected_client_sha256=CLIENT, acquisition_queue_capacity=7)
    store, run = make_store(tmp_path)
    store.append_event(run.run_id, EventKind.EVIDENCE, batch(snapshot()))
    result = CliRunner().invoke(
        app, ["runs", "acquisition-evidence", run.run_id, "--database", str(store.path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["snapshot_count"] == 1
    result = CliRunner().invoke(app, ["play-training", "--help"])
    assert result.exit_code == 0
    params = get_command(app).commands["play-training"].params
    assert any("--acquisition-evidence-probe" in param.opts for param in params)
    with pytest.raises(ValidationError, match="reviewed official client hash"):
        TrainingRunConfig(
            expected_client_sha256="a" * 64,
            acquisition_evidence_probe=True,
            acquisition_evidence_catalog=CATALOG_PATH,
        )


def test_cli_collection_command_preserves_heuristic_control(monkeypatch):
    configs = []

    async def campaign(_settings, config):
        configs.append(config)
        return TrainingCampaignSummary(
            max_games=3,
            games_started=3,
            games_completed=3,
            wins=1,
            losses=2,
            draws=0,
            run_ids=("a", "b", "c"),
            stop_reason="game_limit",
            last_run_status=RunStatus.COMPLETED,
        )

    monkeypatch.setattr("godfield_bot.cli.run_training_campaign", campaign)
    result = CliRunner().invoke(
        app,
        [
            "play-training",
            "--headless",
            "--max-games",
            "3",
            "--max-seconds",
            "0",
            "--max-actions",
            "1000",
            "--no-progress-seconds",
            "120",
            "--acquisition-evidence-probe",
            "--acquisition-queue-capacity",
            "256",
            "--acquisition-evidence-catalog",
            str(CATALOG_PATH),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert configs[0].game.acquisition_evidence_probe
    assert configs[0].game.policy.value == "heuristic-v0"
    assert configs[0].game.model_directory is None
    assert configs[0].game.shadow_model_directory is None
    assert configs[0].game.acquisition_evidence_catalog == CATALOG_PATH
    assert configs[0].max_games == 3 and configs[0].game.max_seconds == 0


@pytest.mark.parametrize(
    "probe,scenario,focus",
    [
        (False, "menu", False),
        (True, "menu", False),
        (True, "setup_error", False),
        (True, "interrupt", False),
        (True, "telemetry_error_terminal", False),
        (True, "telemetry_error_terminal", True),
    ],
)
def test_runner_installs_before_session_and_flushes_before_context_closes(
    tmp_path, monkeypatch, probe, scenario, focus
):
    trace = []
    page = FakePage(v4_read([raw_room()]) if probe else probe_read(snapshot()), trace=trace)
    page.fail_read = scenario == "telemetry_error_terminal"

    class Context:
        def __init__(self):
            self.pages = [page]

        async def add_init_script(self, *, script):
            assert '"schema_version": 4' in script
            assert "__godfieldAcquisitionEvidenceV" in script
            trace.append("installed")

    @asynccontextmanager
    async def open_context(*_args, **_kwargs):
        trace.append("opened")
        try:
            yield Context()
        finally:
            trace.append("closed")

    async def fingerprint(_context):
        trace.append("fingerprint")
        return ClientFingerprint(url="https://godfield.net/main.dart.js", sha256=CLIENT)

    async def session(*_args, **_kwargs):
        trace.append("session")
        if scenario == "setup_error":
            raise ValueError("synthetic setup failure")
        if scenario == "interrupt":
            raise asyncio.CancelledError

    observation = ScreenObservation(
        observed_at=datetime.now(UTC),
        url="https://godfield.net/",
        title="God Field",
        kind=ScreenKind.GAME if scenario == "telemetry_error_terminal" else ScreenKind.MENU,
        viewport_width=960,
        viewport_height=720,
        text=(),
        text_elements=(),
        controls=(),
        images=(),
    )

    async def capture(*_args):
        return observation

    async def reach(*_args):
        return observation

    monkeypatch.setattr("godfield_bot.runner.open_account_context", open_context)
    monkeypatch.setattr("godfield_bot.runner.fingerprint_client", fingerprint)
    monkeypatch.setattr("godfield_bot.runner.start_account_session", session)
    monkeypatch.setattr("godfield_bot.runner.capture_screen", capture)
    monkeypatch.setattr("godfield_bot.runner._reach_training_game", reach)
    terminal = GameState(
        observed_at=datetime.now(UTC),
        field_number=1,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=40, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=0, mp=10, money=20, is_self=False),
        ),
        hand=(),
        scene_layers=(),
    )
    monkeypatch.setattr("godfield_bot.runner.parse_game_state", lambda *_args, **_kwargs: terminal)
    database = tmp_path / "runner.sqlite"
    config = TrainingRunConfig(
        database=database,
        expected_client_sha256=CLIENT,
        acquisition_evidence_probe=probe,
        acquisition_evidence_catalog=CATALOG_PATH if probe else None,
        policy=ACQUISITION_POLICY_ID if focus else "safe-observer-v0",
        acquisition_miracle_focus="flame" if focus else None,
        max_in_match_actions=100 if focus else 0,
        verified_weapon_attacks={"bronze-club": ("ATK1", 1.0)} if focus else {},
        plain_armor_defenses={"iron-shield": 4} if focus else {},
        verified_miracle_attacks={"flame": (10, 5, "fire")} if focus else {},
    )
    if scenario == "interrupt":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_training_observer(AppSettings(), config))
        with sqlite3.connect(database) as connection:
            run_id, status = connection.execute("SELECT run_id, status FROM runs").fetchone()
        assert status == RunStatus.ABORTED.value
    else:
        run = asyncio.run(run_training_observer(AppSettings(), config))
        run_id = run.run_id
        expected = {
            "menu": RunStatus.ABORTED,
            "setup_error": RunStatus.FAILED,
            "telemetry_error_terminal": RunStatus.COMPLETED,
        }
        assert run.status == expected[scenario]
        if focus:
            assert run.policy_id == ACQUISITION_POLICY_ID
            assert run.config["collection_only"] is True
            assert run.config["training_eligible"] is False
            assert run.config["promotion_eligible"] is False
            assert run.config["acquisition_miracle_focus"] == "flame"
            assert run.config["acquisition_max_prioritized_selections"] == 2
    if probe:
        assert trace.index("installed") < trace.index("session")
        report = audit_acquisition_run(database, run_id)
        assert report["collector_summary_count"] == 1
        assert report["declared_capture_schema_version"] == 4
        if scenario == "telemetry_error_terminal":
            assert report["read_error_count"] == 2 and report["snapshot_count"] == 0
        else:
            assert report["capture_schema_versions"] == [4]
            assert report["capture_schema_matches_run_config"]
            assert trace.index("ack") < trace.index("closed")
            assert report["snapshot_count"] == 1
    else:
        assert trace == ["opened", "fingerprint", "session", "closed"]


def v3_read(rooms):
    raw = node(
        "register({}, () => {}); input.rooms.forEach((room) => emit(room)); return read();",
        rooms=rooms,
        schema_version=3,
    )
    return AcquisitionProbeReadV3.model_validate_json(json.dumps(raw))


def v4_read(rooms):
    raw = node(
        "register({}, () => {}); input.rooms.forEach((room) => emit(room)); return read();",
        rooms=rooms,
        schema_version=4,
    )
    return AcquisitionProbeReadV4.model_validate_json(json.dumps(raw))


def v2_read(rooms):
    raw = node(
        """
      register({}, () => {});
      input.rooms.forEach((room) => emit(room));
      return read();
    """,
        rooms=rooms,
        schema_version=2,
    )
    return AcquisitionProbeReadV2.model_validate_json(json.dumps(raw))


def v2_batch(read):
    return AcquisitionEvidenceBatchV2(
        observed_at=datetime.now(UTC),
        client_sha256=CLIENT,
        catalog_sha256=CATALOG,
        input_sha256=acquisition_batch_digest(CLIENT, CATALOG, read.status, read.snapshots),
        status=read.status,
        snapshots=read.snapshots,
    )


def test_v2_captures_actorless_own_actions_but_never_opponent_models():
    first = raw_room(events=[{"action": "startGame"}, {"action": "advanceGF", "playerId": 1}])
    second = raw_room(
        updateCount=1,
        attackTurnPlayerId=2,
        events=[
            {"action": "useAttackItems", "items": [{"id": 1, "modelId": 10}]},
            {"action": "setTargetPlayer", "playerId": 2},
            {"action": "useDefenseItems", "items": [{"id": 1, "modelId": 777}]},
            {"action": "dealDamage"},
            {"action": "gift", "playerId": 1, "item": {"id": 1, "modelId": 12}},
            {"action": "advanceGF", "playerId": 2},
            {"action": "useAttackItems", "items": [{"id": 1, "modelId": 777}]},
            {"action": "setTargetPlayer", "playerId": 1},
            {"action": "useDefenseItems", "items": [{"id": 1, "modelId": 12}]},
        ],
    )
    read = v2_read([first, second])
    row = read.snapshots[1]
    assert row.phase_input_status == "consecutive"
    assert row.events[0].player_id is None and row.events[0].self_item_payload_bound
    assert row.event_owners[0].item_owner_player_id == 1
    assert row.events[2].items == row.events[6].items == ()
    assert row.events[8].self_item_payload_bound
    assert "777" not in read.model_dump_json()
    audit = audit_acquisition_batches((v2_batch(read),))
    assert audit.self_bound_attack_item_count == audit.self_bound_defense_item_count == 1
    assert audit.unresolved_item_owner_event_count == 0
    assert not audit.training_eligible and not audit.acquisition_rule_eligible


@pytest.mark.parametrize(
    "barrier",
    [
        "bounce",
        "reflect",
        "counterAttack",
        "nextAttack",
        "attackByGuardian",
        "attackDyingly",
        "boostHP",
        "unknown",
    ],
)
def test_v2_default_denies_ownership_after_ambiguous_phase_events(barrier):
    read = v2_read(
        [
            raw_room(
                events=[
                    {"action": "advanceGF", "playerId": 1},
                    {"action": barrier},
                    {
                        "action": "useAttackItems",
                        "playerId": 1,
                        "items": [{"id": 1, "modelId": 888}],
                    },
                ]
            )
        ]
    )
    row = read.snapshots[0]
    assert not row.events[-1].self_item_payload_bound
    assert row.event_owners[-1].basis == "unresolved"
    assert "888" not in read.model_dump_json()


@pytest.mark.parametrize("change", [{"updateCount": 2}, {"gf": 0}, {"updateCount": -1}])
def test_v2_never_carries_phase_context_across_source_server_or_game_gaps(change):
    first = raw_room(events=[{"action": "advanceGF", "playerId": 1}])
    second = raw_room(
        updateCount=1,
        events=[
            {
                "action": "useAttackItems",
                "items": [
                    {"id": 1, "modelId": 888},
                ],
            }
        ],
    )
    second["game"].update(change)
    read = v2_read([first, second])
    assert "888" not in read.model_dump_json()
    if change.get("updateCount") == -1:
        assert read.status.rejected_snapshot_count == 1
    else:
        assert read.snapshots[-1].phase_before is None
        assert read.snapshots[-1].phase_input_status == "gap_or_boundary"


def test_v2_wire_classification_retains_omissions_and_recognizes_only_safe_placeholders():
    room = raw_room()
    room["game"]["players"][0]["items"] = [
        {"id": 1, "modelId": 10},
        {"id": 0, "modelId": 0},
        {"id": 2, "modelId": 11, "used": True},
        {"id": 3, "modelId": 12, "used": None},
    ]
    read = v2_read([room])
    row = read.snapshots[0]
    assert row.self_items[0].used is None and row.self_item_wire[0].used_kind == "missing"
    assert row.self_item_wire[1].client_empty_placeholder
    assert row.self_item_wire[3].used_kind == "null"
    audit = audit_acquisition_batches((v2_batch(read),))
    assert audit.client_empty_placeholder_observation_count == 1
    assert audit.invalid_item_identity_snapshot_count == 0
    assert audit.max_distinct_owned_instances == 3
    assert audit.max_client_unused_distinct_instances == 2
    assert audit.unknown_used_flag_count == 3
    assert "unknown_used_flags" not in audit.collection_issues


def test_v2_does_not_reinterpret_malformed_ids_as_empty_slots():
    room = raw_room()
    room["game"]["players"][0]["items"] = [{"id": "not-an-integer", "modelId": 0}]
    audit = audit_acquisition_batches((v2_batch(v2_read([room])),))
    assert audit.client_empty_placeholder_observation_count == 0
    assert audit.invalid_item_identity_snapshot_count == 1
    assert audit.malformed_wire_item_observation_count == 1


def test_v2_repeated_versions_reuse_the_same_input_context_without_recounting_events():
    first = raw_room(events=[{"action": "advanceGF", "playerId": 1}])
    second = raw_room(
        updateCount=1,
        events=[
            {
                "action": "useAttackItems",
                "items": [
                    {"id": 1, "modelId": 10},
                ],
            },
            {"action": "advanceGF", "playerId": 2},
        ],
    )
    read = v2_read([first, second, second])
    assert read.snapshots[-1].phase_input_status == "repeat"
    assert read.snapshots[1].phase_before == read.snapshots[2].phase_before
    audit = audit_acquisition_batches((v2_batch(read),))
    assert audit.repeated_server_version_count == 1
    assert audit.inconsistent_server_version_count == 0
    assert audit.self_bound_attack_item_count == 1


def test_v2_validates_actor_proof_and_preserves_capture_on_storage_retry(tmp_path):
    read = v2_read(
        [
            raw_room(
                events=[
                    {"action": "advanceGF", "playerId": 1},
                    {"action": "useAttackItems", "items": [{"id": 1, "modelId": 10}]},
                ]
            )
        ]
    )
    bad = read.model_dump(mode="json")
    bad["snapshots"][0]["event_owners"][1]["item_owner_player_id"] = 2
    with pytest.raises(ValidationError, match="ownership differs"):
        AcquisitionProbeReadV2.model_validate_json(json.dumps(bad))
    store, run = make_store(tmp_path)
    page = FakePage(read)
    page.fail_ack = True
    writer = recorder(store, run)
    assert not asyncio.run(writer.poll(page))
    page.fail_ack = False
    asyncio.run(writer.finalize(page))
    audit = audit_acquisition_run(store.path, run.run_id)
    assert audit["capture_schema_versions"] == [2]
    assert audit["self_bound_attack_item_count"] == 1
    assert audit["duplicate_source_snapshot_count"] == 0
    assert audit["final_poll_succeeded"] is True


@pytest.mark.parametrize(
    "prefix",
    [
        [],
        [
            {"action": "advanceGF", "playerId": 1},
            {"action": "setTargetPlayer", "playerId": 2},
        ],
    ],
)
def test_v2_self_targets_and_unseeded_targets_never_expose_opponent_items(prefix):
    read = v2_read(
        [
            raw_room(
                events=[
                    *prefix,
                    {"action": "setTargetPlayer", "playerId": 1},
                    {"action": "useDefenseItems", "items": [{"id": 1, "modelId": 777}]},
                ]
            )
        ]
    )
    assert "777" not in read.model_dump_json()
    assert read.snapshots[0].event_owners[-1].basis == "unresolved"


@pytest.mark.parametrize(
    "case",
    [
        "initial_compact_items",
        "unclassified_empty_item",
        "retained_used_item",
        "eighteen_owned_ids",
    ],
)
def test_recorded_v1_cases_remain_byte_shape_compatible_and_keep_their_digests(case):
    fixture = json.loads(Path("tests/fixtures/acquisition-v1-wire-cases.json").read_text())
    selected = next(row for row in fixture["cases"] if row["case"] == case)
    batch = AcquisitionEvidenceBatch.model_validate_json(json.dumps(selected["batch"]))
    assert batch.model_dump(mode="json") == selected["batch"]
    assert (
        acquisition_batch_digest(CLIENT, batch.catalog_sha256, batch.status, batch.snapshots)
        == selected["batch"]["input_sha256"]
    )
    audit = audit_acquisition_batches((batch,))
    assert audit.capture_schema_versions == (1,)
    assert audit.pinned_client_interpretation_applied
    assert not audit.training_eligible and not audit.acquisition_rule_eligible
    if case == "initial_compact_items":
        assert audit.unknown_used_flag_count == 9
        assert audit.max_client_unused_distinct_instances == 9
    elif case == "unclassified_empty_item":
        assert audit.invalid_item_identity_snapshot_count == 1
        assert audit.client_empty_placeholder_observation_count == 0
    elif case == "retained_used_item":
        assert any(item.used is True for row in batch.snapshots for item in row.self_items)
    else:
        assert audit.max_client_unused_distinct_instances == 18


def test_v2_interpretation_rejects_an_unreviewed_client():
    read = v2_read([raw_room()])
    payload = v2_batch(read).model_dump(mode="json")
    payload["client_sha256"] = "c" * 64
    with pytest.raises(ValidationError, match="reviewed client hash"):
        AcquisitionEvidenceBatchV2.model_validate_json(json.dumps(payload))


def test_v2_audit_verifies_persisted_prior_phase_anchors():
    first = raw_room(events=[{"action": "advanceGF", "playerId": 1}])
    second = raw_room(
        updateCount=1,
        events=[
            {
                "action": "useAttackItems",
                "items": [
                    {"id": 1, "modelId": 10},
                ],
            }
        ],
    )
    original = v2_read([first, second])
    forged = original.model_dump(mode="json")
    row = forged["snapshots"][1]
    row["phase_before"]["turn_player_id"] = row["phase_after"]["turn_player_id"] = 2
    row["event_owners"][0]["item_owner_player_id"] = 2
    row["events"][0]["self_item_payload_bound"] = False
    row["events"][0]["items"] = []
    read = AcquisitionProbeReadV2.model_validate_json(json.dumps(forged))
    with pytest.raises(ValueError, match="recorded source anchor"):
        audit_acquisition_batches((v2_batch(read),))
