"""Differential inventory checks, not official game-fidelity or training gates."""

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_run
from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionEvidenceBatch,
    AcquisitionProbeStatus,
    acquisition_batch_digest,
)
from godfield_bot.acquisition_replay import (
    REPLAY_CATALOG_SHA256,
    AcquisitionReplayUnavailableError,
    audit_acquisition_replay_batches,
    audit_acquisition_replay_run,
)
from godfield_bot.acquisition_v2 import AcquisitionEvidenceBatchV2, AcquisitionSnapshotV2
from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app

pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
FIXTURE = Path("tests/fixtures/acquisition-v2-bc54a888.json")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
STREAM = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def avoid_retaining_cli_capture(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)


def item(identity=1, model=23, *, fake=None, used=None, index=0):
    return {
        "raw_index": index,
        "instance_id": identity,
        "model_id": model,
        "fake_model_id": fake,
        "used": used,
    }


def event(action, *, actor=None, items=(), gift=None, overflow=None):
    return {
        "action": action,
        "event_index": 0,
        "player_id": actor,
        "target_player_id": None,
        "self_item_payload_bound": False,
        "item": gift,
        "items": list(items),
        "overflow_item": overflow,
        "item_model_id": None,
    }


def snapshot(sequence=1, *, owned=None, events=None, previous=None, update=None, over=False):
    """Synthetic mechanics tests with explicitly constructed valid owner proofs."""
    owned = [item()] if owned is None else owned
    events = (
        [event("startGame"), event("gift", actor=2, gift=item()), event("advanceGF", actor=2)]
        if events is None
        else events
    )
    before = previous.phase_after.model_dump(mode="json") if previous is not None else None
    turn = before["turn_player_id"] if before else None
    target = before["target_player_id"] if before else None
    owners = []
    for index, operation in enumerate(events):
        operation["event_index"] = index
        actor = operation["player_id"]
        if operation["action"] == "advanceGF":
            turn, target = actor, None
        elif operation["action"] == "setTargetPlayer":
            target = actor if turn is not None and turn != actor else None
        owner, basis = None, "unresolved"
        if operation["action"] == "gift" and actor in {1, 2}:
            owner, basis = actor, "explicit_gift_player"
        elif operation["action"] == "useAttackItems" and turn is not None:
            owner, basis = turn, "turn_context"
        elif operation["action"] == "useDefenseItems" and target is not None:
            owner, basis = target, "target_context"
        operation["self_item_payload_bound"] = owner == 2 and operation["action"] in {
            "gift",
            "useAttackItems",
            "useDefenseItems",
        }
        owners.append({"event_index": index, "item_owner_player_id": owner, "basis": basis})
        if operation["action"] not in {
            "advanceGF",
            "setTargetPlayer",
            "gift",
            "useAttackItems",
            "useDefenseItems",
        }:
            turn = target = None
    for index, artifact in enumerate(owned):
        artifact["raw_index"] = index
    wire = [
        {
            "raw_index": index,
            "instance_id_kind": "positive_integer" if artifact["instance_id"] else "missing",
            "model_id_kind": "positive_integer" if artifact["model_id"] else "missing",
            "fake_model_id_kind": "positive_integer" if artifact["fake_model_id"] else "missing",
            "used_kind": "boolean" if artifact["used"] is not None else "missing",
        }
        for index, artifact in enumerate(owned)
    ]
    update = sequence - 1 if update is None else update
    value = {
        "source_sequence": sequence,
        "captured_at": "2030-01-01T00:00:00Z",
        "field_number": 1,
        "update_count": update,
        "self_player_id": 2,
        "player_count": 2,
        "is_over": over,
        "attack_turn_player_id": 2,
        "self_items": owned,
        "events": events,
        "unreviewed_event_count": 0,
        "redacted_item_event_count": 0,
        "self_item_wire": wire,
        "event_owners": owners,
        "unreviewed_event_indices": [],
        "phase_input_status": "consecutive" if before else "initial",
        "phase_before": before,
        "phase_after": {
            "source_sequence": sequence,
            "update_count": update,
            "field_number": 1,
            "self_player_id": 2,
            "player_ids": [1, 2],
            "turn_player_id": turn,
            "target_player_id": target,
        },
    }
    return AcquisitionSnapshotV2.model_validate_json(json.dumps(value))


def batch(*snapshots, **status_changes):
    status = AcquisitionProbeStatus(
        stream_id=STREAM,
        source_sequence=max((row.source_sequence for row in snapshots), default=0),
        acknowledged_sequence=0,
        pending_snapshot_count=len(snapshots),
        dropped_snapshot_count=0,
        rejected_snapshot_count=0,
        hook_error_count=0,
        hook_installed=True,
        listener_registrations=1,
    ).model_copy(update=status_changes)
    return AcquisitionEvidenceBatchV2(
        observed_at=datetime.now(UTC),
        client_sha256=ACQUISITION_REVIEWED_CLIENT_SHA256,
        catalog_sha256=REPLAY_CATALOG_SHA256,
        input_sha256=acquisition_batch_digest(
            ACQUISITION_REVIEWED_CLIENT_SHA256, REPLAY_CATALOG_SHA256, status, snapshots
        ),
        status=status,
        snapshots=snapshots,
    )


def audit(*batches):
    return audit_acquisition_replay_batches(batches, catalog=read_api_catalog_snapshot(CATALOG))


def fixture_batches():
    return tuple(
        AcquisitionEvidenceBatchV2.model_validate_json(json.dumps(record["payload"]))
        for record in json.loads(FIXTURE.read_text())["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-evidence-v2"
    )


def test_original_official_fixture_matches_every_recorded_inventory_without_labels():
    original = FIXTURE.read_bytes()
    report = audit(*fixture_batches())
    assert report.complete_projection_replay
    assert report.matched_initial_snapshot_count == 1
    assert report.matched_transition_count == 3
    assert report.matched_consumed_item_count == 2
    assert report.matched_gift_item_count == 11
    assert report.matched_retained_miracle_use_count == 0
    assert report.mismatch_count == report.unsupported_snapshot_count == 0
    assert all(result.status == "matched" for result in report.results)
    for flag in (
        "training_eligible",
        "promotion_eligible",
        "acquisition_rule_eligible",
        "combat_replay_verified",
        "gift_schedule_verified",
        "overflow_rule_verified",
        "event_item_wire_metadata_complete",
    ):
        assert report.model_dump()[flag] is False
    assert "passed" not in report.model_dump()
    assert FIXTURE.read_bytes() == original


def test_synthetic_flame_first_use_and_reuse_are_explicit_not_inferred():
    first = snapshot(
        owned=[item(1, 215), item(2, 23)],
        events=[
            event("startGame"),
            event("gift", actor=2, gift=item(1, 215)),
            event("gift", actor=2, gift=item(2, 23)),
            event("advanceGF", actor=2),
        ],
    )
    second = snapshot(
        2,
        previous=first,
        owned=[item(2, 23), item(1, 215, used=True), item(3, 3)],
        events=[
            event("useAttackItems", items=[item(1, 215)]),
            event("gift", actor=2, gift=item(3, 3)),
        ],
    )
    third = snapshot(
        3,
        previous=second,
        owned=[item(2, 23), item(3, 3), item(1, 215, used=True), item(4, 202)],
        events=[
            event("useAttackItems", items=[item(1, 215, used=True)]),
            event("gift", actor=2, gift=item(4, 202)),
        ],
    )
    report = audit(batch(first, second, third))
    assert report.complete_projection_replay
    assert report.matched_retained_miracle_use_count == 2
    assert report.matched_consumed_item_count == 0
    assert report.matched_gift_item_count == 4
    assert not report.training_eligible


def test_missing_consumption_is_a_mismatch_not_recovered_from_inventory():
    first = snapshot()
    second = snapshot(2, previous=first, owned=[], events=[])
    report = audit(batch(first, second))
    assert report.mismatch_count == 1
    assert report.results[-1].reason == "ordered_inventory_differs"
    assert report.results[-1].first_difference_index == 0
    assert report.matched_consumed_item_count == 0
    assert not report.complete_projection_replay


@pytest.mark.parametrize("invalid", ["unknown_id", "wrong_model", "overwrite"])
def test_native_rejections_stay_visible_and_do_not_count_partial_operations(invalid):
    first = snapshot()
    operation = (
        event("gift", actor=2, gift=item(1, 3))
        if invalid == "overwrite"
        else event(
            "useAttackItems",
            items=[
                item(99 if invalid == "unknown_id" else 1, 142 if invalid == "wrong_model" else 23)
            ],
        )
    )
    second = snapshot(2, previous=first, events=[operation])
    report = audit(batch(first, second))
    assert report.mismatch_count == 1
    assert report.results[-1].reason == "native_operation_rejected"
    assert report.results[-1].event_index == 0
    assert report.matched_consumed_item_count == 0
    assert report.matched_gift_item_count == 1


def test_a_failed_update_is_not_hidden_by_a_later_independent_match():
    first = snapshot()
    second = snapshot(2, previous=first, owned=[], events=[])
    third = snapshot(3, previous=second, owned=[], events=[])
    report = audit(batch(first, second, third))
    assert [result.status for result in report.results] == ["matched", "mismatch", "matched"]
    assert report.matched_transition_count == report.mismatch_count == 1
    assert not report.complete_projection_replay
    assert report.results[-1].from_source_sequence == 2


@pytest.mark.parametrize(
    "operation, reason",
    [
        (event("removeItems"), "unsupported_inventory_event"),
        (
            event("useAttackItems", items=[item(1, 10)]),
            "unsupported_selection_model_or_combination",
        ),
        (
            event("useAttackItems", items=[item(1, 215), item(2, 23)]),
            "unsupported_selection_model_or_combination",
        ),
        (event("useAttackItems", items=[item(1, 23, fake=142)]), "unsupported_disguised_selection"),
        (event("gift", actor=2, gift=item(2), overflow=item()), "unsupported_overflow"),
        (event("gift", actor=2), "missing_gift_item"),
    ],
)
def test_unsupported_mechanics_are_not_labeled_as_matches(operation, reason):
    first = snapshot()
    second = snapshot(2, previous=first, events=[operation])
    report = audit(batch(first, second))
    assert report.unsupported_snapshot_count == 1
    assert report.results[-1].reason == reason
    assert report.results[-1].event_index == 0
    assert report.matched_transition_count == report.mismatch_count == 0
    assert not report.complete_projection_replay


def test_redacted_unresolved_item_event_cannot_be_treated_as_an_opponent():
    first = snapshot(events=[event("startGame"), event("gift", actor=2, gift=item())])
    second = snapshot(2, previous=first, events=[event("useAttackItems")])
    report = audit(batch(first, second))
    assert report.reason_counts == {"unresolved_item_owner": 1}
    assert not report.complete_projection_replay


@pytest.mark.parametrize("gap", ["source", "server", "document", "missing_prefix"])
def test_no_comparison_bridges_missing_versions_documents_or_initial_events(gap):
    first = snapshot()
    if gap == "source":
        second = snapshot(3, update=1, previous=first, events=[])
        batches = (batch(first, second),)
    elif gap == "server":
        second = snapshot(2, update=5, events=[])
        batches = (batch(first, second),)
    elif gap == "document":
        second = snapshot(1, events=[])
        batches = (batch(first), batch(second, stream_id="00000000-0000-4000-8000-000000000002"))
    else:
        second = snapshot(2, events=[])
        batches = (batch(second),)
    report = audit(*batches)
    assert report.matched_transition_count == 0
    assert not report.complete_projection_replay


def test_an_invalid_previous_inventory_cannot_seed_a_native_comparison():
    first = snapshot(owned=[item(None, 23)])
    second = snapshot(2, previous=first, events=[])
    report = audit(batch(first, second))
    assert report.reason_counts == {"invalid_item_identity": 2}
    assert report.matched_transition_count == 0


@pytest.mark.parametrize("boundary", ["self", "same_count_membership", "field", "terminal"])
def test_game_boundaries_never_seed_a_cross_game_transition(boundary):
    first = snapshot(over=boundary == "terminal")
    second = snapshot(2, events=[])
    raw = second.model_dump(mode="json")
    if boundary == "self":
        raw["self_player_id"] = raw["phase_after"]["self_player_id"] = 1
    elif boundary == "same_count_membership":
        raw["phase_after"]["player_ids"] = [2, 3]
    elif boundary == "field":
        raw["field_number"] = raw["phase_after"]["field_number"] = 0
    second = AcquisitionSnapshotV2.model_validate_json(json.dumps(raw))
    report = audit(batch(first, second))
    assert report.results[-1].status == "skipped"
    assert report.results[-1].reason == "unsafe_source_server_or_player_boundary"
    assert report.matched_transition_count == 0
    assert not report.complete_projection_replay


def test_structural_empty_placeholders_are_not_owned_items():
    row = snapshot(owned=[item(), item(None, None)], over=True)
    report = audit(batch(row))
    assert report.complete_projection_replay
    assert report.results[0].expected_item_count == report.results[0].replayed_item_count == 1


def test_order_difference_is_not_hidden_by_set_comparison():
    first = snapshot(
        owned=[item(), item(2, 142)],
        events=[
            event("startGame"),
            event("gift", actor=2, gift=item()),
            event("gift", actor=2, gift=item(2, 142)),
            event("advanceGF", actor=2),
        ],
    )
    second = snapshot(2, previous=first, owned=[item(2, 142), item()], events=[])
    report = audit(batch(first, second))
    assert report.results[-1].reason == "ordered_inventory_differs"
    assert report.results[-1].first_difference_index == 0


def test_deliveries_and_consistent_server_repeats_never_replay_gifts_twice():
    first = snapshot()
    repeated = first.model_dump(mode="json")
    repeated["source_sequence"] = 2
    repeated["phase_after"]["source_sequence"] = 2
    repeated["phase_input_status"] = "repeat"
    repeated = AcquisitionSnapshotV2.model_validate_json(json.dumps(repeated))
    report = audit(batch(first, repeated), batch(first, repeated))
    assert report.complete_projection_replay
    assert report.matched_gift_item_count == 1
    assert report.repeated_server_snapshot_count == 1
    assert len(report.results) == 2


def test_inconsistent_server_repeat_also_blocks_the_following_pair():
    first = snapshot()
    repeated = snapshot(2, update=0, owned=[], events=[])
    final = snapshot(3, update=1, previous=repeated, owned=[], events=[])
    report = audit(batch(first, repeated, final))
    assert [result.status for result in report.results] == ["matched", "skipped", "skipped"]
    assert report.matched_transition_count == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"source_sequence": 2},
        {"dropped_snapshot_count": 1},
        {"rejected_snapshot_count": 1},
        {"hook_installed": False},
        {"hook_error_count": 1},
        {"listener_registrations": 0},
    ],
)
def test_transport_failures_prevent_complete_projection_even_if_rows_match(changes):
    report = audit(batch(snapshot(), **changes))
    assert report.matched_initial_snapshot_count == 1
    assert not report.complete_projection_replay


def test_v1_is_never_upgraded_to_recovered_consumption_labels():
    fixture = json.loads(Path("tests/fixtures/acquisition-v1-retained-flame.json").read_text())
    batches = tuple(
        AcquisitionEvidenceBatch.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
    )
    report = audit(*batches)
    assert report.unsupported_snapshot_count == 3
    assert report.reason_counts == {"capture_v1_missing_consumption_ownership": 3}
    assert report.matched_retained_miracle_use_count == 0


def test_missing_and_wrong_native_identity_fail_without_importing_a_fallback(monkeypatch):
    monkeypatch.setattr(native, "ORDERED_INVENTORY_REPLAY_SCHEMA_VERSION", 1)
    with pytest.raises(AcquisitionReplayUnavailableError, match="identity differs"):
        audit(batch(snapshot()))


def test_missing_native_package_reports_a_clear_optional_dependency_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "godfield_sim", None)
    with pytest.raises(AcquisitionReplayUnavailableError, match="simulation extra with uv"):
        audit(batch(snapshot()))


@pytest.mark.parametrize(
    "case, reason",
    [
        ("malformed_fake", "malformed_owned_item_wire"),
        ("malformed_used", "malformed_owned_item_wire"),
        ("unknown_model", "unknown_catalog_model"),
        ("duplicate_id", "duplicate_owned_instance"),
    ],
)
def test_unsafe_owned_projections_are_not_normalized_into_success(case, reason):
    owned = [item(1, 999)] if case == "unknown_model" else [item()]
    if case == "duplicate_id":
        owned.append(item(1, 142))
    raw = snapshot(owned=owned).model_dump(mode="json")
    if case == "malformed_fake":
        raw["self_item_wire"][0]["fake_model_id_kind"] = "other"
    elif case == "malformed_used":
        raw["self_item_wire"][0]["used_kind"] = "other"
    row = AcquisitionSnapshotV2.model_validate_json(json.dumps(raw))
    report = audit(batch(row))
    assert report.reason_counts == {reason: 1}
    assert not report.complete_projection_replay


def test_unreviewed_event_blocks_comparison_even_when_inventory_does_not_change():
    first = snapshot()
    raw = snapshot(2, previous=first, events=[event("endGame")]).model_dump(mode="json")
    raw.update(events=[], event_owners=[], unreviewed_event_indices=[0], unreviewed_event_count=1)
    second = AcquisitionSnapshotV2.model_validate_json(json.dumps(raw))
    report = audit(batch(first, second))
    assert report.reason_counts == {"unreviewed_event": 1}
    assert report.matched_transition_count == 0


def test_conflicting_persisted_phase_anchor_is_rejected_before_native_replay():
    first = snapshot()
    raw = snapshot(2, previous=first, events=[]).model_dump(mode="json")
    raw["phase_before"]["field_number"] = 0
    second = AcquisitionSnapshotV2.model_validate_json(json.dumps(raw))
    with pytest.raises(ValueError, match="recorded source anchor"):
        audit(batch(first, second))


def test_conflicting_delivery_is_not_silently_replaced_by_latest_input():
    first = snapshot()
    other = snapshot(owned=[item(1, 142)])
    with pytest.raises(ValueError, match="conflicting acquisition source snapshot"):
        audit(batch(first), batch(other))


def test_restart_event_does_not_erase_an_existing_inventory_or_hide_a_boundary():
    first = snapshot()
    second = snapshot(2, previous=first, events=[event("startGame")])
    report = audit(batch(first, second))
    assert report.reason_counts == {"restart_boundary": 1}
    assert report.matched_transition_count == 0


def test_catalog_provenance_mismatch_is_rejected():
    saved = batch(snapshot())
    saved = saved.model_copy(update={"catalog_sha256": "a" * 64})
    with pytest.raises(ValueError, match="reviewed acquisition catalog"):
        audit(saved)


def fixture_database(tmp_path):
    fixture = json.loads(FIXTURE.read_text())
    path = tmp_path / "runs.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE runs (run_id TEXT, mode TEXT, client_sha256 TEXT, config_json TEXT)"
        )
        connection.execute(
            "CREATE TABLE events (run_id TEXT, sequence INTEGER, kind TEXT, payload_json TEXT)"
        )
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            (
                fixture["run_id"],
                fixture["mode"],
                fixture["client_sha256"],
                json.dumps(
                    {
                        "acquisition_evidence_probe": True,
                        "acquisition_evidence_schema_version": 2,
                        "acquisition_evidence_catalog_sha256": REPLAY_CATALOG_SHA256,
                    }
                ),
            ),
        )
        connection.executemany(
            "INSERT INTO events VALUES (?, ?, 'evidence', ?)",
            [
                (fixture["run_id"], record["sequence"], json.dumps(record["payload"]))
                for record in fixture["evidence"]
            ],
        )
    return path, fixture["run_id"], fixture["input_sha256"]


def test_cli_and_database_audits_are_read_only_deterministic_and_preserve_original_hash(tmp_path):
    database, run_id, original_hash = fixture_database(tmp_path)
    original = database.read_bytes()
    report = audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report == audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report["transport_audit"] == audit_acquisition_run(database, run_id)
    assert report["input_sha256"] == original_hash
    assert report["complete_projection_replay"]
    result = CliRunner().invoke(
        app,
        [
            "runs",
            "acquisition-replay",
            run_id,
            "--database",
            str(database),
            "--catalog",
            str(CATALOG),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == report
    assert database.read_bytes() == original


def test_cli_fails_safely_on_bad_hashes_without_echoing_corrupt_private_payloads(tmp_path):
    database, run_id, _ = fixture_database(tmp_path)
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT payload_json FROM events LIMIT 1").fetchone()
        payload = json.loads(row[0])
        payload["PRIVATE_SECRET"] = "DO_NOT_PRINT_ME"
        connection.execute(
            "UPDATE events SET payload_json=? WHERE sequence=0", (json.dumps(payload),)
        )
    result = CliRunner().invoke(
        app, ["runs", "acquisition-replay", run_id, "--database", str(database)]
    )
    assert result.exit_code == 1
    assert "schema or content digest mismatch" in result.output
    assert "PRIVATE_SECRET" not in result.output and "DO_NOT_PRINT_ME" not in result.output


def test_no_database_is_created_for_missing_run_storage(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.Error):
        audit_acquisition_replay_run(path, "missing", catalog_path=CATALOG)
    assert not path.exists()


@pytest.mark.parametrize("defect", ["final_poll", "declared_schema"])
def test_run_transport_failure_prevents_completion_even_when_all_native_rows_match(
    tmp_path, defect
):
    database, run_id, _ = fixture_database(tmp_path)
    with sqlite3.connect(database) as connection:
        if defect == "final_poll":
            row = connection.execute(
                "SELECT sequence, payload_json FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            payload = json.loads(row[1])
            assert payload["source_kind"] == "official-acquisition-collector-summary-v1"
            payload["final_poll_succeeded"] = False
            connection.execute(
                "UPDATE events SET payload_json=? WHERE sequence=?", (json.dumps(payload), row[0])
            )
        else:
            row = connection.execute("SELECT config_json FROM runs").fetchone()
            config = json.loads(row[0])
            config["acquisition_evidence_schema_version"] = 1
            connection.execute("UPDATE runs SET config_json=?", (json.dumps(config),))
    report = audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report["matched_transition_count"] == 3
    assert report["mismatch_count"] == 0
    assert not report["complete_projection_replay"]


def test_cli_missing_native_error_is_sanitized_and_not_a_traceback(tmp_path, monkeypatch):
    database, run_id, _ = fixture_database(tmp_path)
    monkeypatch.setitem(sys.modules, "godfield_sim", None)
    result = CliRunner().invoke(
        app,
        [
            "runs",
            "acquisition-replay",
            run_id,
            "--database",
            str(database),
        ],
    )
    assert result.exit_code == 1
    assert "installed simulation extra" in result.output
    assert "Traceback" not in result.output
