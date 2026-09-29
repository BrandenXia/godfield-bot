"""Read-only native differential checks of a narrow observed inventory projection.

No event is inferred from inventory differences. Unsupported updates are not
successful replays, and native state is never carried across a failed update.
This is not a combat replay, a gift scheduler, or an acquisition training gate.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.acquisition_evidence import (
    AcquisitionBatch,
    audit_acquisition_batches,
    audit_loaded_acquisition_run,
    load_acquisition_run,
)
from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    AcquisitionItem,
    AcquisitionSnapshot,
)
from godfield_bot.acquisition_v2 import AcquisitionSnapshotV2
from godfield_bot.acquisition_v3 import AcquisitionSnapshotV3
from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot

REPLAY_PROJECTION_ID = "observed-inventory-projection-verified-ordinary-wire-aware-v4"
REPLAY_CATALOG_SHA256 = ACQUISITION_REVIEWED_CATALOG_SHA256
NATIVE_REPLAY_RULESET_ID = "explicit-ordinary-retained-miracle-and-observed-three-removal-replay-v3"
# Only explicit single-item consumption witnessed in the official fixtures:
# v2 bc54a888 (23, 142), v3 60fe19b4 and cb9da594 (the remaining models). Catalog
# membership or an ordinary category alone is not sufficient for admission.
ORDINARY_MODELS = (16, 23, 26, 29, 32, 40, 41, 44, 55, 81, 123, 130, 135, 142, 166, 192, 195)
RETAINED_MODELS = (215,)
# Only the handlers reviewed for the existing fixture are admitted. Being in
# the collector's reviewed-action list does NOT establish inventory neutrality.
INVENTORY_NEUTRAL_ACTIONS = frozenset(
    {
        "advanceGF",
        "setTargetPlayer",
        "safe",
        "miss",
        "dealDamage",
        "dealDarkDamage",
        # Reviewed pinned-client handlers update only numeric HP/MP displays.
        # Their combat/resource semantics are NOT simulated by inventory replay.
        "boostHP",
        "boostMP",
        # The pinned reflect handler swaps pending combat roles, not inventory.
        # This does NOT recover the owner of the following reflected defense.
        "reflect",
        "die",
        "endGame",
    }
)
FRAME_METADATA = {
    "source_sequence",
    "captured_at",
    "phase_before",
    "phase_after",
    "phase_input_status",
}
ItemRow = tuple[int, int, int, int]


class AcquisitionReplayUnavailableError(RuntimeError):
    """The optional native replay is unavailable or has a different identity."""


class _UnsupportedReplay(ValueError):
    def __init__(self, reason: str, event_index: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.event_index = event_index


class InventoryReplayResult(BaseModel):
    stream_id: str
    source_sequence: int = Field(ge=1)
    update_count: int = Field(ge=0)
    from_source_sequence: int | None = Field(default=None, ge=1)
    kind: Literal["initial", "transition", "unavailable"]
    status: Literal["matched", "mismatch", "unsupported", "skipped", "repeat"]
    reason: str | None = None
    event_index: int | None = Field(default=None, ge=0)
    expected_item_count: int | None = Field(default=None, ge=0)
    replayed_item_count: int | None = Field(default=None, ge=0)
    first_difference_index: int | None = Field(default=None, ge=0)
    consumed_item_count: int = Field(default=0, ge=0)
    gift_item_count: int = Field(default=0, ge=0)
    retained_miracle_use_count: int = Field(default=0, ge=0)


class AcquisitionReplayAudit(BaseModel):
    schema_version: Literal[2] = 2
    source_kind: Literal["official-acquisition-native-projection-audit-v2"] = (
        "official-acquisition-native-projection-audit-v2"
    )
    replay_projection_id: str = REPLAY_PROJECTION_ID
    native_replay_schema_version: Literal[3] = 3
    native_replay_ruleset_id: str = NATIVE_REPLAY_RULESET_ID
    ordinary_model_ids: tuple[int, ...] = ORDINARY_MODELS
    retained_miracle_model_ids: tuple[int, ...] = RETAINED_MODELS
    interpretation_basis: Literal["pinned-client-sanitized-item-projection"] = (
        "pinned-client-sanitized-item-projection"
    )
    comparison_mode: Literal["independent-adjacent-observed-baselines"] = (
        "independent-adjacent-observed-baselines"
    )
    complete_projection_replay: bool
    matched_initial_snapshot_count: int = Field(ge=0)
    matched_transition_count: int = Field(ge=0)
    mismatch_count: int = Field(ge=0)
    unsupported_snapshot_count: int = Field(ge=0)
    skipped_snapshot_count: int = Field(ge=0)
    repeated_server_snapshot_count: int = Field(ge=0)
    matched_consumed_item_count: int = Field(ge=0)
    matched_gift_item_count: int = Field(ge=0)
    matched_retained_miracle_use_count: int = Field(ge=0)
    reason_counts: dict[str, int]
    results: tuple[InventoryReplayResult, ...]
    event_item_wire_metadata_complete: bool
    event_item_wire_scope: Literal["verified-self-gift-attack-defense-events"] = (
        "verified-self-gift-attack-defense-events"
    )
    combat_replay_verified: Literal[False] = False
    gift_schedule_verified: Literal[False] = False
    overflow_rule_verified: Literal[False] = False
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False


def _require_native_replay() -> None:
    try:
        import godfield_sim as native
        import numpy  # noqa: F401
    except (ImportError, OSError):
        raise AcquisitionReplayUnavailableError(
            "native replay is unavailable; install the simulation extra with uv"
        ) from None
    if (
        getattr(native, "ORDERED_INVENTORY_REPLAY_SCHEMA_VERSION", None) != 3
        or getattr(native, "ORDERED_INVENTORY_REPLAY_RULESET_ID", None) != NATIVE_REPLAY_RULESET_ID
        or not hasattr(native, "OrderedInventoryReplay")
    ):
        raise AcquisitionReplayUnavailableError("native inventory replay identity differs")


def _item_row(item: AcquisitionItem, catalog_ids: set[int]) -> ItemRow:
    if item.instance_id is None or item.model_id is None:
        raise _UnsupportedReplay("invalid_item_identity")
    if item.model_id not in catalog_ids or (
        item.fake_model_id is not None and item.fake_model_id not in catalog_ids
    ):
        raise _UnsupportedReplay("unknown_catalog_model")
    # This is a projection of the saved sanitized payload, not recovery of
    # omitted raw fields. Event item wire sidecars were not captured by v2.
    return (item.instance_id, item.model_id, item.fake_model_id or 0, int(item.used is True))


def _owned_rows(row: AcquisitionSnapshotV2, catalog_ids: set[int]) -> list[ItemRow]:
    owned = []
    for item, wire in zip(row.self_items, row.self_item_wire, strict=True):
        if any(
            kind == "other"
            for kind in (
                wire.instance_id_kind,
                wire.model_id_kind,
                wire.fake_model_id_kind,
                wire.used_kind,
            )
        ):
            raise _UnsupportedReplay("malformed_owned_item_wire")
        if not (wire.client_empty_placeholder and item.used is not True):
            owned.append(_item_row(item, catalog_ids))
    if len({item[0] for item in owned}) != len(owned):
        raise _UnsupportedReplay("duplicate_owned_instance")
    return owned


def _native_check(
    initial: list[ItemRow],
    expected: list[ItemRow],
    row: AcquisitionSnapshotV2,
    *,
    catalog_ids: set[int],
    stream_id: str,
    previous: AcquisitionSnapshotV2 | None,
) -> InventoryReplayResult:
    import godfield_sim as native
    import numpy as np

    replay = native.OrderedInventoryReplay(
        np.asarray(initial, dtype=np.int64).reshape(-1, 4),
        np.asarray(ORDINARY_MODELS, dtype=np.int64),
    )
    replay.configure_retained_miracles(np.asarray(RETAINED_MODELS, dtype=np.int64))
    event_wires = (
        {wire.event_index: wire for wire in row.event_item_wire}
        if isinstance(row, AcquisitionSnapshotV3)
        else {}
    )
    for event, owner in zip(row.events, row.event_owners, strict=True):
        if event.action == "startGame":
            if previous is not None or event.event_index != 0:
                raise _UnsupportedReplay("restart_boundary", event.event_index)
            continue
        if event.action in INVENTORY_NEUTRAL_ACTIONS:
            continue
        if event.action not in {"gift", "useAttackItems", "useDefenseItems"}:
            raise _UnsupportedReplay("unsupported_inventory_event", event.event_index)
        if owner.item_owner_player_id is None:
            raise _UnsupportedReplay("unresolved_item_owner", event.event_index)
        if owner.item_owner_player_id != row.self_player_id:
            continue  # Opponent item bodies remain redacted; never simulate them.
        if not event.self_item_payload_bound:
            raise _UnsupportedReplay("missing_self_item_binding", event.event_index)
        if event.event_index in event_wires:
            wire = event_wires[event.event_index]
            if wire.malformed:
                raise _UnsupportedReplay("malformed_self_event_wire", event.event_index)
            if event.action in {"useAttackItems", "useDefenseItems"} and wire.items_kind != "array":
                raise _UnsupportedReplay("ambiguous_self_selection_array", event.event_index)
        if event.overflow_item is not None:
            raise _UnsupportedReplay("unsupported_overflow", event.event_index)
        if (
            event.item_model_id is not None
            or (event.action == "gift" and event.items)
            or (event.action != "gift" and event.item is not None)
        ):
            raise _UnsupportedReplay("unsupported_event_payload_shape", event.event_index)
        try:
            if event.action == "gift":
                if event.item is None:
                    raise _UnsupportedReplay("missing_gift_item")
                replay.gift(np.asarray(_item_row(event.item, catalog_ids), dtype=np.int64))
            else:
                selected = [_item_row(item, catalog_ids) for item in event.items]
                if any(item[2] != 0 for item in selected):
                    raise _UnsupportedReplay("unsupported_disguised_selection")
                if len(selected) == 1 and selected[0][1] in RETAINED_MODELS:
                    replay.perform_retained_miracle(np.asarray(selected[0], dtype=np.int64))
                elif len(selected) <= 1 and all(item[1] in ORDINARY_MODELS for item in selected):
                    replay.consume(np.asarray(selected, dtype=np.int64).reshape(-1, 4))
                else:
                    raise _UnsupportedReplay("unsupported_selection_model_or_combination")
        except _UnsupportedReplay as error:
            raise _UnsupportedReplay(error.reason, event.event_index) from None
        except ValueError:
            # A stale ID/model or unexplained overwrite is a diagnostic mismatch,
            # not an invitation to repair state from the resulting snapshot.
            return InventoryReplayResult(
                stream_id=stream_id,
                source_sequence=row.source_sequence,
                update_count=row.update_count,
                from_source_sequence=previous.source_sequence if previous else None,
                kind="transition" if previous else "initial",
                status="mismatch",
                reason="native_operation_rejected",
                event_index=event.event_index,
                expected_item_count=len(expected),
                replayed_item_count=replay.size,
            )
    actual = replay.snapshot().tolist()
    expected_lists = [list(item) for item in expected]
    first_difference = next(
        (index for index, (a, b) in enumerate(zip(actual, expected_lists, strict=False)) if a != b),
        min(len(actual), len(expected)) if len(actual) != len(expected) else None,
    )
    return InventoryReplayResult(
        stream_id=stream_id,
        source_sequence=row.source_sequence,
        update_count=row.update_count,
        from_source_sequence=previous.source_sequence if previous else None,
        kind="transition" if previous else "initial",
        status="matched" if first_difference is None else "mismatch",
        reason=None if first_difference is None else "ordered_inventory_differs",
        expected_item_count=len(expected),
        replayed_item_count=len(actual),
        first_difference_index=first_difference,
        consumed_item_count=replay.consumed_item_count,
        gift_item_count=replay.gift_item_count,
        retained_miracle_use_count=replay.retained_miracle_use_count,
    )


def audit_acquisition_replay_batches(
    batches: tuple[AcquisitionBatch, ...], *, catalog: ApiCatalogSnapshot
) -> AcquisitionReplayAudit:
    """Compare explicit event projections, never infer a missing operation.

    Each transition has its own native object seeded from its recorded previous
    inventory. A mismatch is counted and abandoned, not silently patched. A
    later comparison can use a new observed baseline without hiding the failure.
    """

    _require_native_replay()
    # Also validate queue order, source anchors, duplicate deliveries, and
    # consistent provenance before constructing any native comparison.
    transport = audit_acquisition_batches(batches)
    if catalog.content_sha256 != REPLAY_CATALOG_SHA256 or any(
        batch.catalog_sha256 != catalog.content_sha256 for batch in batches
    ):
        raise ValueError("native projection requires the reviewed acquisition catalog")
    catalog_ids = {item.model_id for item in catalog.items}
    streams: dict[str, dict[int, AcquisitionSnapshot]] = {}
    for batch in batches:
        rows = streams.setdefault(batch.status.stream_id, {})
        for row in batch.snapshots:
            rows[row.source_sequence] = row
    results = []
    for stream_id, rows in streams.items():
        previous: AcquisitionSnapshotV2 | None = None
        previous_consistent = False
        versions: dict[int, dict[str, object]] = {}
        for row in rows.values():
            if not isinstance(row, AcquisitionSnapshotV2):
                results.append(
                    InventoryReplayResult(
                        stream_id=stream_id,
                        source_sequence=row.source_sequence,
                        update_count=row.update_count,
                        kind="unavailable",
                        status="unsupported",
                        reason="capture_v1_missing_consumption_ownership",
                    )
                )
                previous = None
                previous_consistent = False
                versions = {}
                continue
            frame = row.model_dump(exclude=FRAME_METADATA)
            boundary = previous is not None and (
                row.self_player_id != previous.self_player_id
                or row.phase_after.player_ids != previous.phase_after.player_ids
                or row.field_number < previous.field_number
                or row.update_count < previous.update_count
            )
            if boundary:
                versions = {}
            repeated = row.update_count in versions
            consistent = not repeated or frame == versions[row.update_count]
            versions.setdefault(row.update_count, frame)
            try:
                expected = _owned_rows(row, catalog_ids)
                if row.unreviewed_event_count:
                    raise _UnsupportedReplay("unreviewed_event")
                if repeated:
                    results.append(
                        InventoryReplayResult(
                            stream_id=stream_id,
                            source_sequence=row.source_sequence,
                            update_count=row.update_count,
                            kind="unavailable",
                            status="repeat" if consistent else "skipped",
                            reason="repeated_server_version"
                            if consistent
                            else "inconsistent_server_version",
                        )
                    )
                elif previous is None:
                    if (
                        row.source_sequence != 1
                        or row.phase_input_status != "initial"
                        or not (row.events and row.events[0].action == "startGame")
                    ):
                        raise _UnsupportedReplay("missing_initial_event_boundary")
                    results.append(
                        _native_check(
                            [],
                            expected,
                            row,
                            catalog_ids=catalog_ids,
                            stream_id=stream_id,
                            previous=None,
                        )
                    )
                elif (
                    boundary
                    or not previous_consistent
                    or previous.is_over is True
                    or (
                        row.source_sequence != previous.source_sequence + 1
                        or row.update_count != previous.update_count + 1
                    )
                ):
                    results.append(
                        InventoryReplayResult(
                            stream_id=stream_id,
                            source_sequence=row.source_sequence,
                            update_count=row.update_count,
                            kind="unavailable",
                            status="skipped",
                            reason="unsafe_source_server_or_player_boundary",
                        )
                    )
                else:
                    if row.phase_before is not None and row.phase_before != previous.phase_after:
                        raise _UnsupportedReplay("unverified_phase_anchor")
                    results.append(
                        _native_check(
                            _owned_rows(previous, catalog_ids),
                            expected,
                            row,
                            catalog_ids=catalog_ids,
                            stream_id=stream_id,
                            previous=previous,
                        )
                    )
            except _UnsupportedReplay as error:
                results.append(
                    InventoryReplayResult(
                        stream_id=stream_id,
                        source_sequence=row.source_sequence,
                        update_count=row.update_count,
                        kind="unavailable",
                        status="unsupported",
                        reason=error.reason,
                        event_index=error.event_index,
                    )
                )
            previous = row
            previous_consistent = consistent
    matched = [result for result in results if result.status == "matched"]
    return AcquisitionReplayAudit(
        event_item_wire_metadata_complete=bool(results)
        and transport.unresolved_item_owner_event_count == 0
        and transport.unverified_phase_context_count == 0
        and transport.unreviewed_event_count == 0
        and all(
            isinstance(row, AcquisitionSnapshotV3)
            for rows in streams.values()
            for row in rows.values()
        ),
        complete_projection_replay=bool(results)
        and all(result.status in {"matched", "repeat"} for result in results)
        and not (
            set(transport.collection_issues)
            - {"missing_collector_summary", "no_terminal_snapshot_observed"}
        ),
        matched_initial_snapshot_count=sum(result.kind == "initial" for result in matched),
        matched_transition_count=sum(result.kind == "transition" for result in matched),
        mismatch_count=sum(result.status == "mismatch" for result in results),
        unsupported_snapshot_count=sum(result.status == "unsupported" for result in results),
        skipped_snapshot_count=sum(result.status == "skipped" for result in results),
        repeated_server_snapshot_count=sum(result.status == "repeat" for result in results),
        matched_consumed_item_count=sum(result.consumed_item_count for result in matched),
        matched_gift_item_count=sum(result.gift_item_count for result in matched),
        matched_retained_miracle_use_count=sum(
            result.retained_miracle_use_count for result in matched
        ),
        reason_counts=dict(
            sorted(
                Counter(result.reason for result in results if result.reason is not None).items()
            )
        ),
        results=tuple(results),
    )


def audit_acquisition_replay_run(
    database: Path, run_id: str, *, catalog_path: Path
) -> dict[str, object]:
    loaded = load_acquisition_run(database, run_id)
    transport = audit_loaded_acquisition_run(loaded)
    report = audit_acquisition_replay_batches(
        loaded.batches, catalog=read_api_catalog_snapshot(catalog_path)
    ).model_dump(mode="json")
    report["complete_projection_replay"] = (
        report["complete_projection_replay"] and not transport["collection_issues"]
    )
    return {
        "run_id": loaded.run_id,
        "input_sha256": loaded.input_sha256,
        "client_sha256": loaded.client_sha256,
        "catalog_sha256": transport["catalog_sha256"],
        "transport_audit": transport,
        **report,
    }
