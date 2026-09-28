"""Read-only acquisition transport audit, not mechanics or learning labels."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionCollectorError,
    AcquisitionCollectorSummary,
    AcquisitionEvidenceBatch,
    AcquisitionItem,
    AcquisitionProbeStatus,
    AcquisitionSnapshot,
)
from godfield_bot.acquisition_v2 import AcquisitionEvidenceBatchV2, AcquisitionSnapshotV2
from godfield_bot.acquisition_v3 import AcquisitionEvidenceBatchV3, AcquisitionSnapshotV3
from godfield_bot.acquisition_v4 import AcquisitionEvidenceBatchV4

AcquisitionBatch = (
    AcquisitionEvidenceBatch
    | AcquisitionEvidenceBatchV2
    | AcquisitionEvidenceBatchV3
    | AcquisitionEvidenceBatchV4
)


class AcquisitionEvidenceAudit(BaseModel):
    schema_version: Literal[2] = 2
    source_kind: Literal["official-acquisition-transport-audit-v2"] = (
        "official-acquisition-transport-audit-v2"
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
    capture_schema_versions: tuple[int, ...]
    pinned_client_interpretation_applied: bool
    max_client_unused_distinct_instances: int = Field(ge=0)
    raw_used_true_observation_count: int = Field(ge=0)
    owned_inventory_growth_pair_count: int = Field(ge=0)
    client_interpreted_used_activation_count: int = Field(ge=0)
    client_empty_placeholder_observation_count: int = Field(ge=0)
    malformed_wire_item_observation_count: int = Field(ge=0)
    unverified_phase_context_count: int = Field(ge=0)
    self_bound_attack_event_count: int = Field(ge=0)
    self_bound_defense_event_count: int = Field(ge=0)
    self_bound_attack_item_count: int = Field(ge=0)
    self_bound_defense_item_count: int = Field(ge=0)
    unresolved_item_owner_event_count: int = Field(ge=0)
    self_overflow_item_event_count: int = Field(ge=0)
    self_event_wire_metadata_count: int = Field(ge=0)
    legacy_self_bound_event_without_wire_count: int = Field(ge=0)
    malformed_self_event_wire_count: int = Field(ge=0)
    ambiguous_self_selection_event_count: int = Field(ge=0)
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
    batches: tuple[AcquisitionBatch, ...],
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
    client_interpretation = bool(provenance) and all(
        client == ACQUISITION_REVIEWED_CLIENT_SHA256 for client, _ in provenance
    )
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
    client_unused_max = placeholders = malformed_wire = unverified_phase = 0
    raw_used_true = growth_pairs = used_activations = 0
    bound_attacks = bound_defenses = attack_items = defense_items = unresolved_owners = overflow = 0
    event_wire_count = legacy_event_wire = malformed_event_wire = ambiguous_selections = 0
    event_counts: Counter[str] = Counter()
    start_seen = zero_seen = terminal_seen = False
    for stream_rows in rows.values():
        previous: AcquisitionSnapshot | None = None
        previous_valid = False
        previous_owned: tuple[AcquisitionItem, ...] = ()
        versions: dict[int, dict[str, object]] = {}
        for row in stream_rows.values():
            owned = list(row.self_items)
            if isinstance(row, AcquisitionSnapshotV2):
                owned = []
                for item, wire in zip(row.self_items, row.self_item_wire, strict=True):
                    if wire.client_empty_placeholder and item.used is not True:
                        placeholders += 1
                    else:
                        owned.append(item)
                    malformed_wire += any(
                        kind == "other"
                        for kind in (
                            wire.instance_id_kind,
                            wire.model_id_kind,
                            wire.fake_model_id_kind,
                            wire.used_kind,
                        )
                    )
                before = row.phase_before
                if before is not None:
                    anchor = stream_rows.get(before.source_sequence)
                    if anchor is None:
                        unverified_phase += 1
                    elif (
                        not isinstance(anchor, AcquisitionSnapshotV2)
                        or anchor.phase_after != before
                    ):
                        raise ValueError("phase input differs from its recorded source anchor")
            identities = [item.instance_id for item in owned]
            valid_ids = None not in identities and len(set(identities)) == len(identities)
            invalid += not valid_ids
            unknown_used += sum(item.used is None for item in row.self_items)
            raw_used_true += sum(item.used is True for item in row.self_items)
            if valid_ids:
                maximum = max(maximum, len(identities))
                unused_maximum = max(unused_maximum, sum(item.used is False for item in owned))
                if client_interpretation:
                    # A.kY maps every non-boolean `used` value to false. Preserve
                    # the raw unknown count; this is a separate client interpretation.
                    client_unused_max = max(
                        client_unused_max, sum(item.used is not True for item in owned)
                    )
            zero_seen |= row.update_count == 0
            terminal_seen |= row.is_over is True
            # Ignore capture sequence/time when comparing repeated server versions.
            frame = row.model_dump(
                exclude={
                    "source_sequence",
                    "captured_at",
                    "phase_before",
                    "phase_after",
                    "phase_input_status",
                }
            )
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
                    if row.player_count == previous.player_count:
                        growth_pairs += len(owned) > len(previous_owned)
                        if client_interpretation:
                            prior = {item.instance_id: item for item in previous_owned}
                            gifted_ids = {
                                event.item.instance_id
                                for event in row.events
                                if event.action == "gift"
                                and event.self_item_payload_bound
                                and event.item is not None
                            }
                            for item in owned:
                                old = prior.get(item.instance_id)
                                used_activations += (
                                    old is not None
                                    and item.instance_id not in gifted_ids
                                    and item.model_id is not None
                                    and (item.model_id, item.fake_model_id)
                                    == (old.model_id, old.fake_model_id)
                                    and old.used is not True
                                    and item.used is True
                                )
            if not repeated_version:
                event_counts.update(event.action for event in row.events)
                start_seen |= any(event.action == "startGame" for event in row.events)
                unreviewed += row.unreviewed_event_count
                redacted += row.redacted_item_event_count
                for index, event in enumerate(row.events):
                    owner = (
                        row.event_owners[index].item_owner_player_id
                        if isinstance(row, AcquisitionSnapshotV2)
                        else event.player_id
                    )
                    unresolved_owners += (
                        event.action in {"useAttackItems", "useDefenseItems"} and owner is None
                    )
                    if event.self_item_payload_bound:
                        if isinstance(row, AcquisitionSnapshotV3):
                            event_wire = row.event_item_wire[index]
                            event_wire_count += 1
                            malformed_event_wire += event_wire.malformed
                            ambiguous_selections += (
                                event.action in {"useAttackItems", "useDefenseItems"}
                                and event_wire.items_kind != "array"
                            )
                        else:
                            legacy_event_wire += 1
                        bound_attacks += event.action == "useAttackItems"
                        bound_defenses += event.action == "useDefenseItems"
                        attack_items += len(event.items) if event.action == "useAttackItems" else 0
                        defense_items += (
                            len(event.items) if event.action == "useDefenseItems" else 0
                        )
                        overflow += event.action == "gift" and event.overflow_item is not None
            previous = row
            previous_valid = valid_ids and consistent
            previous_owned = tuple(owned)
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
        "unknown_used_flags": unknown_used > 0 and not client_interpretation,
        "unresolved_item_ownership": unresolved_owners > 0,
        "malformed_wire_items": malformed_wire > 0,
        "malformed_self_event_wire": malformed_event_wire > 0,
        "ambiguous_self_selections": ambiguous_selections > 0,
        "unverified_phase_context": unverified_phase > 0,
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
        capture_schema_versions=tuple(sorted({batch.schema_version for batch in batches})),
        pinned_client_interpretation_applied=client_interpretation,
        max_client_unused_distinct_instances=client_unused_max,
        raw_used_true_observation_count=raw_used_true,
        owned_inventory_growth_pair_count=growth_pairs,
        client_interpreted_used_activation_count=used_activations,
        client_empty_placeholder_observation_count=placeholders,
        malformed_wire_item_observation_count=malformed_wire,
        unverified_phase_context_count=unverified_phase,
        self_bound_attack_event_count=bound_attacks,
        self_bound_defense_event_count=bound_defenses,
        self_bound_attack_item_count=attack_items,
        self_bound_defense_item_count=defense_items,
        unresolved_item_owner_event_count=unresolved_owners,
        self_overflow_item_event_count=overflow,
        self_event_wire_metadata_count=event_wire_count,
        legacy_self_bound_event_without_wire_count=legacy_event_wire,
        malformed_self_event_wire_count=malformed_event_wire,
        ambiguous_self_selection_event_count=ambiguous_selections,
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


@dataclass(frozen=True)
class LoadedAcquisitionRun:
    """One read-only SQLite snapshot, shared by transport and native diagnostics."""

    run_id: str
    mode: str
    client_sha256: str
    declared_capture_schema_version: int | None
    input_sha256: str
    batches: tuple[AcquisitionBatch, ...]
    errors: tuple[AcquisitionCollectorError, ...]
    summaries: tuple[AcquisitionCollectorSummary, ...]


def load_acquisition_run(database: Path, run_id: str) -> LoadedAcquisitionRun:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        # Keep run metadata and evidence in one read transaction even if an
        # operator is collecting more evidence concurrently. No writer is opened.
        connection.execute("BEGIN")
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
    batches: list[AcquisitionBatch] = []
    errors: list[AcquisitionCollectorError] = []
    summaries: list[AcquisitionCollectorSummary] = []
    evidence: list[dict[str, object]] = []
    config = json.loads(run["config_json"])
    for row in payloads:
        payload = json.loads(row["payload_json"])
        source = payload.get("source_kind") if isinstance(payload, dict) else None
        if source in {
            "official-acquisition-evidence-v1",
            "official-acquisition-evidence-v2",
            "official-acquisition-evidence-v3",
            "official-acquisition-evidence-v4",
        }:
            batch: AcquisitionBatch
            if source == "official-acquisition-evidence-v4":
                batch = AcquisitionEvidenceBatchV4.model_validate_json(row["payload_json"])
            elif source == "official-acquisition-evidence-v3":
                batch = AcquisitionEvidenceBatchV3.model_validate_json(row["payload_json"])
            elif source == "official-acquisition-evidence-v2":
                batch = AcquisitionEvidenceBatchV2.model_validate_json(row["payload_json"])
            else:
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
    declared_schema = (
        config.get("acquisition_evidence_schema_version") if isinstance(config, dict) else None
    )
    if type(declared_schema) is not int or declared_schema not in {1, 2, 3, 4}:
        declared_schema = None
    return LoadedAcquisitionRun(
        run_id=run_id,
        mode=run["mode"],
        client_sha256=run["client_sha256"],
        declared_capture_schema_version=declared_schema,
        input_sha256=hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        batches=tuple(batches),
        errors=tuple(errors),
        summaries=tuple(summaries),
    )


def audit_loaded_acquisition_run(loaded: LoadedAcquisitionRun) -> dict[str, object]:
    report = audit_acquisition_batches(
        loaded.batches, errors=loaded.errors, summaries=loaded.summaries
    ).model_dump(mode="json")
    declared_schema = loaded.declared_capture_schema_version
    schema_match = (
        set(batch.schema_version for batch in loaded.batches) == {declared_schema}
        if declared_schema is not None
        else None
    )
    if schema_match is False:
        report["collection_issues"].append("capture_schema_mismatch")
    return {
        "run_id": loaded.run_id,
        "mode": loaded.mode,
        "client_sha256": loaded.client_sha256,
        "catalog_sha256": loaded.batches[0].catalog_sha256 if loaded.batches else None,
        "declared_capture_schema_version": declared_schema,
        "capture_schema_matches_run_config": schema_match,
        "input_sha256": loaded.input_sha256,
        **report,
    }


def audit_acquisition_run(database: Path, run_id: str) -> dict[str, object]:
    return audit_loaded_acquisition_run(load_acquisition_run(database, run_id))
