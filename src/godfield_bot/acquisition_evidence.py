"""Read-only acquisition transport audit, not mechanics or learning labels."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.acquisition_probe import (
    AcquisitionCollectorError,
    AcquisitionCollectorSummary,
    AcquisitionEvidenceBatch,
    AcquisitionProbeStatus,
    AcquisitionSnapshot,
)


class AcquisitionEvidenceAudit(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["official-acquisition-transport-audit-v1"] = (
        "official-acquisition-transport-audit-v1"
    )
    batch_count: int = Field(ge=0)
    stream_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    duplicate_source_snapshot_count: int = Field(ge=0)
    missing_source_sequence_count: int = Field(ge=0)
    dropped_snapshot_count: int = Field(ge=0)
    rejected_snapshot_count: int = Field(ge=0)
    hook_error_count: int = Field(ge=0)
    hooked_stream_count: int = Field(ge=0)
    listening_stream_count: int = Field(ge=0)
    read_error_count: int = Field(ge=0)
    ack_error_count: int = Field(ge=0)
    repeated_server_version_count: int = Field(ge=0)
    inconsistent_server_version_count: int = Field(ge=0)
    boundary_pair_count: int = Field(ge=0)
    server_gap_pair_count: int = Field(ge=0)
    adjacent_pair_count: int = Field(ge=0)
    invalid_item_identity_snapshot_count: int = Field(ge=0)
    unknown_used_flag_count: int = Field(ge=0)
    max_distinct_owned_instances: int = Field(ge=0)
    max_explicitly_unused_distinct_instances: int = Field(ge=0)
    reviewed_event_counts: dict[str, int]
    unreviewed_event_count: int = Field(ge=0)
    redacted_item_event_count: int = Field(ge=0)
    start_game_event_seen: bool
    update_zero_seen: bool
    terminal_snapshot_seen: bool
    collector_summary_count: int = Field(ge=0)
    final_poll_succeeded: bool | None
    collection_issues: tuple[str, ...]
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False


def audit_acquisition_batches(
    batches: tuple[AcquisitionEvidenceBatch, ...],
    *,
    errors: tuple[AcquisitionCollectorError, ...] = (),
    summaries: tuple[AcquisitionCollectorSummary, ...] = (),
) -> AcquisitionEvidenceAudit:
    """Do not bridge document streams, invalid IDs, or skipped source/server updates.

    Version repeats do not multiply event counts. Even an issue-free transport
    report does not prove gift/consumption semantics or full-game fidelity.
    """

    provenance = {(batch.client_sha256, batch.catalog_sha256) for batch in batches}
    if len(provenance) > 1:
        raise ValueError("acquisition batches mix client/catalog provenance")
    rows: dict[str, dict[int, AcquisitionSnapshot]] = {}
    statuses: dict[str, AcquisitionProbeStatus] = {}
    duplicates = 0
    for batch in batches:
        stream = batch.status.stream_id
        previous_status = statuses.get(stream)
        if previous_status is not None and any(
            getattr(batch.status, name) < getattr(previous_status, name)
            for name in (
                "source_sequence",
                "acknowledged_sequence",
                "dropped_snapshot_count",
                "rejected_snapshot_count",
                "hook_error_count",
                "listener_registrations",
            )
        ):
            raise ValueError("acquisition stream counters regressed")
        statuses[stream] = batch.status
        stream_rows = rows.setdefault(stream, {})
        for row in batch.snapshots:
            if row.source_sequence in stream_rows:
                if stream_rows[row.source_sequence] != row:
                    raise ValueError("conflicting acquisition source snapshot")
                duplicates += 1
            else:
                if stream_rows and row.source_sequence < max(stream_rows):
                    raise ValueError("acquisition source snapshots arrived out of order")
                stream_rows[row.source_sequence] = row
    # The final status is a pre-ack read, not a count of unsaved snapshots.
    for summary in summaries:
        for status in summary.streams:
            if status.stream_id not in statuses or status != statuses[status.stream_id]:
                raise ValueError("collector summary differs from final saved stream status")
    saved = sum(len(stream_rows) for stream_rows in rows.values())
    if summaries and any(summary.saved_snapshot_count != saved for summary in summaries):
        raise ValueError("collector summary differs from saved snapshot count")
    missing = sum(status.source_sequence - len(rows[stream]) for stream, status in statuses.items())
    dropped = sum(status.dropped_snapshot_count for status in statuses.values())
    rejected = sum(status.rejected_snapshot_count for status in statuses.values())
    hook_errors = sum(status.hook_error_count for status in statuses.values())
    hooked = sum(status.hook_installed for status in statuses.values())
    listening = sum(status.listener_registrations > 0 for status in statuses.values())
    collector_events: tuple[AcquisitionCollectorError | AcquisitionCollectorSummary, ...] = (
        *errors,
        *summaries,
    )
    read_errors = max((event.read_error_count for event in collector_events), default=0)
    ack_errors = max((event.ack_error_count for event in collector_events), default=0)
    repeated = inconsistent = boundaries = gaps = adjacent = invalid = unknown_used = 0
    maximum = unused_maximum = unreviewed = redacted = 0
    event_counts: Counter[str] = Counter()
    start_seen = zero_seen = terminal_seen = False
    for stream_rows in rows.values():
        previous: AcquisitionSnapshot | None = None
        previous_valid = False
        versions: dict[int, dict[str, object]] = {}
        for row in stream_rows.values():
            identities = [item.instance_id for item in row.self_items]
            valid_ids = None not in identities and len(set(identities)) == len(identities)
            invalid += not valid_ids
            unknown_used += sum(item.used is None for item in row.self_items)
            if valid_ids:
                maximum = max(maximum, len(identities))
                unused_maximum = max(
                    unused_maximum, sum(item.used is False for item in row.self_items)
                )
            zero_seen |= row.update_count == 0
            terminal_seen |= row.is_over is True
            # Ignore capture sequence/time when comparing repeated server versions.
            frame = row.model_dump(exclude={"source_sequence", "captured_at"})
            if previous is not None and (
                row.self_player_id != previous.self_player_id
                or row.field_number < previous.field_number
                or row.update_count < previous.update_count
            ):
                boundaries += 1
                versions = {}
                previous_valid = False
            repeated_version = row.update_count in versions
            consistent = True
            if repeated_version:
                consistent = frame == versions[row.update_count]
                repeated += consistent
                inconsistent += not consistent
            else:
                versions[row.update_count] = frame
            if previous is not None:
                if row.update_count > previous.update_count and (
                    row.source_sequence != previous.source_sequence + 1
                    or row.update_count != previous.update_count + 1
                ):
                    gaps += 1
                elif row.update_count > previous.update_count and valid_ids and previous_valid:
                    adjacent += 1
            if not repeated_version:
                event_counts.update(event.action for event in row.events)
                start_seen |= any(event.action == "startGame" for event in row.events)
                unreviewed += row.unreviewed_event_count
                redacted += row.redacted_item_event_count
            previous = row
            previous_valid = valid_ids and consistent
    final_poll = summaries[-1].final_poll_succeeded if summaries else None
    issues: list[str] = []
    checks = {
        "no_saved_snapshots": saved == 0,
        "missing_source_sequences": missing > 0,
        "queue_overflow": dropped > 0,
        "rejected_snapshots": rejected > 0,
        "hook_errors": hook_errors > 0,
        "unhooked_stream": hooked < len(statuses),
        "no_listener_in_stream": listening < len(statuses),
        "read_errors": read_errors > 0,
        "ack_errors": ack_errors > 0,
        "inconsistent_server_versions": inconsistent > 0,
        "stream_game_boundaries": boundaries > 0,
        "server_version_gaps": gaps > 0,
        "invalid_item_identities": invalid > 0,
        "unknown_used_flags": unknown_used > 0,
        "unreviewed_events": unreviewed > 0,
        "missing_collector_summary": not summaries,
        "final_poll_failed": final_poll is False,
        "no_start_boundary_observed": not (start_seen or zero_seen),
        "no_terminal_snapshot_observed": not terminal_seen,
    }
    issues.extend(name for name, present in checks.items() if present)
    return AcquisitionEvidenceAudit(
        batch_count=len(batches),
        stream_count=len(statuses),
        snapshot_count=saved,
        duplicate_source_snapshot_count=duplicates,
        missing_source_sequence_count=missing,
        dropped_snapshot_count=dropped,
        rejected_snapshot_count=rejected,
        hook_error_count=hook_errors,
        hooked_stream_count=hooked,
        listening_stream_count=listening,
        read_error_count=read_errors,
        ack_error_count=ack_errors,
        repeated_server_version_count=repeated,
        inconsistent_server_version_count=inconsistent,
        boundary_pair_count=boundaries,
        server_gap_pair_count=gaps,
        adjacent_pair_count=adjacent,
        invalid_item_identity_snapshot_count=invalid,
        unknown_used_flag_count=unknown_used,
        max_distinct_owned_instances=maximum,
        max_explicitly_unused_distinct_instances=unused_maximum,
        reviewed_event_counts=dict(sorted(event_counts.items())),
        unreviewed_event_count=unreviewed,
        redacted_item_event_count=redacted,
        start_game_event_seen=start_seen,
        update_zero_seen=zero_seen,
        terminal_snapshot_seen=terminal_seen,
        collector_summary_count=len(summaries),
        final_poll_succeeded=final_poll,
        collection_issues=tuple(issues),
    )


def audit_acquisition_run(database: Path, run_id: str) -> dict[str, object]:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute(
            "SELECT mode, client_sha256, config_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise ValueError("unknown run")
        payloads = connection.execute(
            "SELECT sequence, payload_json FROM events "
            "WHERE run_id = ? AND kind = 'evidence' ORDER BY sequence",
            (run_id,),
        ).fetchall()
    batches, errors, summaries, evidence = [], [], [], []
    config = json.loads(run["config_json"])
    for row in payloads:
        payload = json.loads(row["payload_json"])
        source = payload.get("source_kind") if isinstance(payload, dict) else None
        if source == "official-acquisition-evidence-v1":
            batch = AcquisitionEvidenceBatch.model_validate_json(row["payload_json"])
            if (
                batch.client_sha256 != run["client_sha256"]
                or run["mode"] != "training"
                or not isinstance(config, dict)
                or config.get("acquisition_evidence_probe") is not True
                or batch.catalog_sha256 != config.get("acquisition_evidence_catalog_sha256")
            ):
                raise ValueError("acquisition provenance differs from Training run")
            batches.append(batch)
        elif source == "official-acquisition-collector-error-v1":
            errors.append(AcquisitionCollectorError.model_validate_json(row["payload_json"]))
        elif source == "official-acquisition-collector-summary-v1":
            summaries.append(AcquisitionCollectorSummary.model_validate_json(row["payload_json"]))
        else:
            continue
        evidence.append({"sequence": row["sequence"], "payload": payload})
    fingerprint = {
        "run_id": run_id,
        "mode": run["mode"],
        "client_sha256": run["client_sha256"],
        "evidence": evidence,
    }
    return {
        "run_id": run_id,
        "mode": run["mode"],
        "client_sha256": run["client_sha256"],
        "catalog_sha256": batches[0].catalog_sha256 if batches else None,
        "input_sha256": hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        **audit_acquisition_batches(
            tuple(batches), errors=tuple(errors), summaries=tuple(summaries)
        ).model_dump(mode="json"),
    }
