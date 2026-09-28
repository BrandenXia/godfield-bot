"""Versioned, pinned-client acquisition interpretation; never training labels."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import Field, field_validator, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    MAX_SAFE_INTEGER,
    AcquisitionProbeStatus,
    AcquisitionSnapshot,
    _StrictEvidence,
    acquisition_batch_digest,
)

WireIntegerKind = Literal["positive_integer", "zero", "missing", "null", "other"]
PHASE_PRESERVING_ACTIONS = frozenset({"gift", "useAttackItems", "useDefenseItems"})


class AcquisitionItemWire(_StrictEvidence):
    raw_index: int = Field(ge=0, le=511)
    instance_id_kind: WireIntegerKind
    model_id_kind: WireIntegerKind
    fake_model_id_kind: WireIntegerKind
    used_kind: Literal["boolean", "missing", "null", "other"]

    @property
    def client_empty_placeholder(self) -> bool:
        default_zero = {"zero", "missing", "null"}
        return (
            self.instance_id_kind in default_zero
            and self.model_id_kind in default_zero
            and self.fake_model_id_kind in default_zero
        )


class AcquisitionPhaseState(_StrictEvidence):
    source_sequence: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    update_count: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    field_number: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    self_player_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    player_ids: tuple[int, ...] = Field(min_length=1, max_length=256)
    turn_player_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    target_player_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)

    @model_validator(mode="after")
    def valid_players(self) -> AcquisitionPhaseState:
        if list(self.player_ids) != sorted(set(self.player_ids)) or any(
            not 1 <= player <= MAX_SAFE_INTEGER for player in self.player_ids
        ):
            raise ValueError("phase player IDs must be distinct positive safe integers")
        if self.self_player_id not in self.player_ids or any(
            player is not None and player not in self.player_ids
            for player in (self.turn_player_id, self.target_player_id)
        ):
            raise ValueError("phase actor lies outside the observed players")
        if self.target_player_id is not None and (
            self.turn_player_id is None or self.target_player_id == self.turn_player_id
        ):
            raise ValueError("phase defender requires a known distinct attacker")
        return self


class AcquisitionEventOwner(_StrictEvidence):
    event_index: int = Field(ge=0, le=511)
    item_owner_player_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    basis: Literal["explicit_gift_player", "turn_context", "target_context", "unresolved"]


class AcquisitionSnapshotV2(AcquisitionSnapshot):
    # Interpretation is versioned by snapshot type, never supplied by JSON.
    # V2/v3 retain their original default-deny reflection behavior and digests.
    reflection_duel_context: ClassVar[bool] = False
    self_item_wire: tuple[AcquisitionItemWire, ...] = Field(max_length=512)
    event_owners: tuple[AcquisitionEventOwner, ...] = Field(max_length=512)
    unreviewed_event_indices: tuple[int, ...] = Field(max_length=512)
    phase_input_status: Literal[
        "initial", "consecutive", "repeat", "gap_or_boundary", "inconsistent_repeat"
    ]
    phase_before: AcquisitionPhaseState | None
    phase_after: AcquisitionPhaseState

    @model_validator(mode="after")
    def enforce_self_binding(self) -> AcquisitionSnapshotV2:
        # Override v1's explicit-player-only check, retaining its ordering checks.
        if self.captured_at.utcoffset() is None:
            raise ValueError("acquisition capture timestamp requires a timezone")
        if [item.raw_index for item in self.self_items] != list(range(len(self.self_items))):
            raise ValueError("owned-item raw indices must preserve array order")
        indices = [event.event_index for event in self.events]
        if indices != sorted(set(indices)):
            raise ValueError("acquisition events must preserve distinct array order")
        if [wire.raw_index for wire in self.self_item_wire] != list(range(len(self.self_items))):
            raise ValueError("wire metadata must cover the owned-item array exactly")
        for item, wire in zip(self.self_items, self.self_item_wire, strict=True):
            for value, kind in (
                (item.instance_id, wire.instance_id_kind),
                (item.model_id, wire.model_id_kind),
                (item.fake_model_id, wire.fake_model_id_kind),
            ):
                if (value is not None) != (kind == "positive_integer"):
                    raise ValueError("wire integer classification differs from sanitized item")
            if (item.used is not None) != (wire.used_kind == "boolean"):
                raise ValueError("wire used classification differs from sanitized flag")
        if [owner.event_index for owner in self.event_owners] != indices:
            raise ValueError("event ownership metadata must cover every reviewed event")
        unknown = list(self.unreviewed_event_indices)
        if (
            unknown != sorted(set(unknown))
            or set(unknown) & set(indices)
            or any(not 0 <= index <= 511 for index in unknown)
            or len(unknown) != self.unreviewed_event_count
        ):
            raise ValueError("unreviewed event positions differ from the omission count")
        after = self.phase_after
        if (
            after.source_sequence != self.source_sequence
            or after.update_count != self.update_count
            or after.field_number != self.field_number
            or after.self_player_id != self.self_player_id
            or len(after.player_ids) != self.player_count
        ):
            raise ValueError("phase output metadata differs from snapshot")
        before = self.phase_before
        if before is not None and (
            self.phase_input_status not in {"consecutive", "repeat"}
            or before.source_sequence >= self.source_sequence
            or before.update_count + 1 != self.update_count
            or before.field_number > self.field_number
            or before.self_player_id != self.self_player_id
            or before.player_ids != after.player_ids
        ):
            raise ValueError("phase input cannot bridge a version/player boundary")
        turn = before.turn_player_id if before is not None else None
        target = before.target_player_id if before is not None else None
        reviewed = dict(zip(indices, zip(self.events, self.event_owners, strict=True), strict=True))
        for index in sorted([*indices, *unknown]):
            if index not in reviewed:
                turn = target = None
                continue
            event, owner = reviewed[index]
            actor = event.player_id if event.player_id in after.player_ids else None
            if event.action == "advanceGF":
                turn, target = actor, None
            elif event.action == "setTargetPlayer":
                target = actor if turn is not None and actor != turn else None
            elif event.action == "reflect" and self.reflection_duel_context:
                # Pinned reflect -> cZ flips roles, then aT targets the original
                # attacker. Only admit the reviewed, fully seeded duel case.
                turn, target = (
                    (target, turn)
                    if len(after.player_ids) == 2 and turn is not None and target is not None
                    else (None, None)
                )
            expected_owner, basis = None, "unresolved"
            if event.action == "gift" and actor is not None:
                expected_owner, basis = actor, "explicit_gift_player"
            elif event.action == "useAttackItems" and turn is not None:
                expected_owner, basis = turn, "turn_context"
            elif event.action == "useDefenseItems" and target is not None:
                expected_owner, basis = target, "target_context"
            if owner.item_owner_player_id != expected_owner or owner.basis != basis:
                raise ValueError("event ownership differs from the reviewed phase replay")
            bound = (
                expected_owner == self.self_player_id and event.action in PHASE_PRESERVING_ACTIONS
            )
            if event.self_item_payload_bound != bound:
                raise ValueError("event item binding differs from the resolved self owner")
            if event.action not in PHASE_PRESERVING_ACTIONS | {
                "advanceGF",
                "setTargetPlayer",
            } and not (self.reflection_duel_context and event.action == "reflect"):
                # Default deny: even reviewed effects clear context unless their
                # phase preservation has been explicitly checked above.
                turn = target = None
        if (after.turn_player_id, after.target_player_id) != (turn, target):
            raise ValueError("phase output differs from ordered event replay")
        return self


class AcquisitionProbeReadV2(_StrictEvidence):
    schema_version: Literal[2]
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV2, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def ordered_queue(self) -> AcquisitionProbeReadV2:
        sequences = [row.source_sequence for row in self.snapshots]
        if (
            self.status.acknowledged_sequence > self.status.source_sequence
            or sequences != sorted(set(sequences))
            or len(sequences) != self.status.pending_snapshot_count
            or (
                sequences
                and (
                    sequences[0] <= self.status.acknowledged_sequence
                    or sequences[-1] > self.status.source_sequence
                )
            )
        ):
            raise ValueError("invalid ordered acquisition v2 queue")
        return self


class AcquisitionEvidenceBatchV2(_StrictEvidence):
    schema_version: Literal[2] = 2
    source_kind: Literal["official-acquisition-evidence-v2"] = "official-acquisition-evidence-v2"
    observed_at: datetime
    client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV2, ...] = Field(max_length=4096)
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False

    @field_validator("client_sha256")
    @classmethod
    def reviewed_decoder_client(cls, value: str) -> str:
        if value != ACQUISITION_REVIEWED_CLIENT_SHA256:
            raise ValueError("acquisition v2 interpretation requires the reviewed client hash")
        return value

    @model_validator(mode="after")
    def valid_saved_subset(self) -> AcquisitionEvidenceBatchV2:
        sequences = [row.source_sequence for row in self.snapshots]
        if (
            sequences != sorted(set(sequences))
            or len(sequences) > self.status.pending_snapshot_count
            or self.status.acknowledged_sequence > self.status.source_sequence
            or (
                sequences
                and (
                    sequences[0] <= self.status.acknowledged_sequence
                    or sequences[-1] > self.status.source_sequence
                )
            )
        ):
            raise ValueError("invalid saved acquisition v2 subset")
        if self.input_sha256 != acquisition_batch_digest(
            self.client_sha256, self.catalog_sha256, self.status, self.snapshots
        ):
            raise ValueError("acquisition batch content digest differs")
        return self
