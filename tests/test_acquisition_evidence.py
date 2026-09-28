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


def node(exercise, *, before=False, include_dream=False, **kwargs):
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node is required for synthetic passive-hook verification")
    init = acquisition_probe_init_script("ロキ-67", capacity=8)
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
def test_actual_script_saves_ordered_queue_and_only_acknowledges_read_prefix(before):
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
        room=raw_room(),
    )
    assert result["first"] == result["second"]
    assert [r["source_sequence"] for r in result["first"]["snapshots"]] == list(range(3, 11))
    assert result["first"]["status"]["dropped_snapshot_count"] == 2
    assert not result["wrong"] and result["accepted"]
    assert [r["source_sequence"] for r in result["remaining"]["snapshots"]] == [11]
    AcquisitionProbeRead.model_validate_json(json.dumps(result["remaining"]))


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
                if isinstance(self.read, AcquisitionProbeRead)
                else self.read
            )
        assert script == ACQUISITION_ACK_SCRIPT
        self.trace.append("ack")
        if self.fail_ack:
            raise PlaywrightError("ACK_SECRET")
        if self.ack_result:
            self.read = AcquisitionProbeRead(
                schema_version=1,
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
    "probe,scenario",
    [
        (False, "menu"),
        (True, "menu"),
        (True, "setup_error"),
        (True, "interrupt"),
        (True, "telemetry_error_terminal"),
    ],
)
def test_runner_installs_before_session_and_flushes_before_context_closes(
    tmp_path, monkeypatch, probe, scenario
):
    trace = []
    page = FakePage(probe_read(snapshot()), trace=trace)
    page.fail_read = scenario == "telemetry_error_terminal"

    class Context:
        def __init__(self):
            self.pages = [page]

        async def add_init_script(self, *, script):
            assert "__godfieldAcquisitionEvidenceV1" in script
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
    if probe:
        assert trace.index("installed") < trace.index("session")
        report = audit_acquisition_run(database, run_id)
        assert report["collector_summary_count"] == 1
        if scenario == "telemetry_error_terminal":
            assert report["read_error_count"] == 2 and report["snapshot_count"] == 0
        else:
            assert trace.index("ack") < trace.index("closed")
            assert report["snapshot_count"] == 1
    else:
        assert trace == ["opened", "fingerprint", "session", "closed"]
