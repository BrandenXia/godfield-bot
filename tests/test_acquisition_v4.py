"""Synthetic ownership/transport checks, not an official v4 mechanics oracle."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_acquisition_evidence import raw_room, v2_read, v3_read, v4_read
from test_acquisition_replay import fixture_database
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches, audit_acquisition_run
from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionCollectorSummary,
    acquisition_batch_digest,
)
from godfield_bot.acquisition_replay import REPLAY_CATALOG_SHA256, audit_acquisition_replay_run
from godfield_bot.acquisition_v4 import AcquisitionEvidenceBatchV4, AcquisitionProbeReadV4
from godfield_bot.cli import app

FIXTURE = Path("tests/fixtures/acquisition-v4-1d87e285.json")
INPUT_SHA256 = "ed1426edd95483b6a5c9052989b91d6883dc0776e8e23f42d5d7064ec846f7fc"


def prefix(attacker=1, defender=2):
    return [
        {"action": "advanceGF", "playerId": attacker},
        {"action": "setTargetPlayer", "playerId": defender},
    ]


def reflection_room(attacker=1, defender=2):
    return raw_room(
        events=[
            *prefix(attacker, defender),
            {"action": "reflect"},
            {"action": "useDefenseItems", "items": [{"id": 1, "modelId": 130}]},
        ]
    )


@pytest.mark.parametrize("attacker,defender,self_bound", [(1, 2, True), (2, 1, False)])
def test_seeded_duel_reflect_swaps_ownership_without_leaking_opponent(
    attacker, defender, self_bound
):
    capture = v4_read([reflection_room(attacker, defender)])
    row = capture.snapshots[0]
    assert (row.phase_after.turn_player_id, row.phase_after.target_player_id) == (
        defender,
        attacker,
    )
    assert row.event_owners[-1].item_owner_player_id == attacker
    assert row.event_owners[-1].basis == "target_context"
    assert row.events[-1].self_item_payload_bound is self_bound
    assert len(row.events[-1].items) == int(self_bound)
    assert (row.event_item_wire[-1].items_kind == "array") is self_bound
    if not self_bound:
        assert '"model_id":130' not in row.model_dump_json()


def test_reflected_context_carries_only_across_consecutive_updates():
    first = raw_room(events=[*prefix(), {"action": "reflect"}])
    second = raw_room(events=[{"action": "useDefenseItems", "items": []}])
    second["game"]["updateCount"] = 1
    capture = v4_read([first, second])
    assert capture.snapshots[-1].events[-1].self_item_payload_bound
    second["game"]["updateCount"] = 2
    gap = v4_read([first, second]).snapshots[-1]
    assert gap.phase_input_status == "gap_or_boundary"
    assert not gap.events[-1].self_item_payload_bound


@pytest.mark.parametrize("reset", ["bounce", "damage", "nextAttack", "UNKNOWN_EFFECT"])
def test_other_effects_remain_default_deny(reset):
    row = v4_read(
        [
            raw_room(
                events=[
                    *prefix(),
                    {"action": "reflect"},
                    {"action": reset},
                    {"action": "useDefenseItems", "items": []},
                ]
            )
        ]
    ).snapshots[0]
    assert row.event_owners[-1].basis == "unresolved"
    assert not row.events[-1].self_item_payload_bound


@pytest.mark.parametrize("seed", [[], prefix(1, 1), prefix(1, 99)])
def test_unseeded_or_invalid_duel_never_binds_reflected_defense(seed):
    row = v4_read(
        [
            raw_room(
                events=[
                    *seed,
                    {"action": "reflect"},
                    {"action": "useDefenseItems", "items": []},
                ]
            )
        ]
    ).snapshots[0]
    assert row.event_owners[-1].basis == "unresolved"


@pytest.mark.parametrize("read", [v2_read, v3_read])
def test_historical_capture_keeps_reflection_unresolved(read):
    row = read([reflection_room()]).snapshots[0]
    assert not row.events[-1].self_item_payload_bound
    assert row.event_owners[-1].basis == "unresolved"


def test_multiplayer_reflect_stays_unresolved_and_membership_change_clears_context():
    room = reflection_room()
    room["game"]["players"].append({"id": 3, "name": "THIRD_SECRET", "items": []})
    row = v4_read([room]).snapshots[0]
    assert row.event_owners[-1].basis == "unresolved"
    assert row.phase_after.turn_player_id is None
    first = raw_room(events=[*prefix(), {"action": "reflect"}])
    second = raw_room(events=[{"action": "useDefenseItems", "items": []}])
    second["game"]["updateCount"] = 1
    second["game"]["players"][1]["id"] = 3
    row = v4_read([first, second]).snapshots[-1]
    assert row.phase_input_status == "gap_or_boundary"
    assert not row.events[-1].self_item_payload_bound


def test_old_redacted_v3_capture_cannot_be_upgraded_by_changing_only_version():
    payload = v3_read([reflection_room()]).model_dump(mode="json")
    payload["schema_version"] = 4
    with pytest.raises(ValidationError, match="ownership"):
        AcquisitionProbeReadV4.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("mutation", ["owner", "bound", "phase", "classvar", "version"])
def test_validator_rejects_forged_interpretation(mutation):
    payload = v4_read([reflection_room()]).model_dump(mode="json")
    row = payload["snapshots"][0]
    if mutation == "owner":
        row["event_owners"][-1]["item_owner_player_id"] = 2
    elif mutation == "bound":
        row["events"][-1]["self_item_payload_bound"] = False
    elif mutation == "phase":
        row["phase_after"]["target_player_id"] = 2
    elif mutation == "classvar":
        row["reflection_duel_context"] = False
    else:
        payload["schema_version"] = 4.0
    with pytest.raises(ValidationError):
        AcquisitionProbeReadV4.model_validate_json(json.dumps(payload))


def test_v4_batch_digest_and_pinned_client_are_enforced():
    capture = v4_read([reflection_room()])
    payload = dict(
        observed_at=datetime.now(UTC),
        client_sha256=ACQUISITION_REVIEWED_CLIENT_SHA256,
        catalog_sha256=REPLAY_CATALOG_SHA256,
        status=capture.status,
        snapshots=capture.snapshots,
        input_sha256=acquisition_batch_digest(
            ACQUISITION_REVIEWED_CLIENT_SHA256,
            REPLAY_CATALOG_SHA256,
            capture.status,
            capture.snapshots,
        ),
    )
    batch = AcquisitionEvidenceBatchV4(**payload)
    assert audit_acquisition_batches((batch,)).capture_schema_versions == (4,)
    assert not batch.training_eligible and not batch.acquisition_rule_eligible
    for change in ({"client_sha256": "a" * 64}, {"input_sha256": "a" * 64}):
        with pytest.raises(ValidationError):
            AcquisitionEvidenceBatchV4(**(payload | change))


def test_v4_retains_v3_inconsistent_repeat_detection():
    first = reflection_room()
    second = copy.deepcopy(first)
    second["game"]["events"][-1]["items"][0]["modelId"] = 142
    capture = v4_read([first, second])
    assert capture.snapshots[-1].phase_input_status == "inconsistent_repeat"


def test_real_v4_collection_fixture_preserves_provenance_and_non_miracle_boundary():
    fixture = json.loads(FIXTURE.read_text())
    fingerprint = {key: fixture[key] for key in ("run_id", "mode", "client_sha256", "evidence")}
    assert (
        hashlib.sha256(
            json.dumps(
                fingerprint,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        == fixture["input_sha256"]
        == INPUT_SHA256
    )
    assert len(fixture["evidence"]) == 67
    assert fixture["collection_only"] and fixture["run_status"] == "aborted"
    assert not fixture["training_eligible"] and not fixture["promotion_eligible"]
    batches = tuple(
        AcquisitionEvidenceBatchV4.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-evidence-v4"
    )
    summaries = tuple(
        AcquisitionCollectorSummary.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-collector-summary-v1"
    )
    audit = audit_acquisition_batches(batches, summaries=summaries)
    assert audit.capture_schema_versions == (4,)
    assert audit.batch_count == 66 and audit.snapshot_count == 34
    assert audit.adjacent_pair_count == 33 and audit.max_distinct_owned_instances == 14
    assert audit.final_poll_succeeded and not audit.terminal_snapshot_seen
    assert audit.unresolved_item_owner_event_count == 3
    assert audit.ambiguous_self_selection_event_count == 10
    assert audit.owned_inventory_growth_pair_count == 8
    assert audit.client_interpreted_used_activation_count == 0
    assert all(
        item.model_id != 215
        for batch in batches
        for row in batch.snapshots
        for item in row.self_items
    )
    assert not any(
        event.action == "reflect"
        for batch in batches
        for row in batch.snapshots
        for event in row.events
    )
    for field in (
        "missing_source_sequence_count",
        "server_gap_pair_count",
        "dropped_snapshot_count",
        "rejected_snapshot_count",
        "hook_error_count",
        "read_error_count",
        "ack_error_count",
        "malformed_self_event_wire_count",
        "inconsistent_server_version_count",
    ):
        assert getattr(audit, field) == 0


def test_real_v4_projection_and_cli_keep_unsupported_updates_and_database_unchanged(
    tmp_path, monkeypatch
):
    database, run_id, input_hash = fixture_database(tmp_path, FIXTURE)
    original = database.read_bytes()
    catalog = Path("data/snapshots/2026-09-21/api-catalog-en.json")
    audit = audit_acquisition_run(database, run_id)
    replay = audit_acquisition_replay_run(database, run_id, catalog_path=catalog)
    assert audit["input_sha256"] == replay["input_sha256"] == INPUT_SHA256
    assert input_hash == INPUT_SHA256
    assert audit["declared_capture_schema_version"] == 4
    assert audit["capture_schema_matches_run_config"]
    assert replay["matched_initial_snapshot_count"] == 1
    assert replay["matched_transition_count"] == 5
    assert replay["mismatch_count"] == 0 and replay["unsupported_snapshot_count"] == 28
    assert (
        not replay["complete_projection_replay"] and not replay["event_item_wire_metadata_complete"]
    )
    assert not replay["training_eligible"] and not replay["acquisition_rule_eligible"]
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    for command in ("acquisition-evidence", "acquisition-replay"):
        result = CliRunner().invoke(app, ["runs", command, run_id, "--database", str(database)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["input_sha256"] == INPUT_SHA256
    assert database.read_bytes() == original
