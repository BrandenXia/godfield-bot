"""Self-only event wire classifications, without retrofitting older captures."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionItem,
    AcquisitionProbeStatus,
    _StrictEvidence,
    acquisition_batch_digest,
)
from godfield_bot.acquisition_v2 import AcquisitionItemWire, AcquisitionSnapshotV2, WireIntegerKind

ItemContainerKind = Literal["missing", "null", "object", "other", "redacted"]
ItemsContainerKind = Literal["missing", "null", "array", "other", "redacted"]


class AcquisitionEventWire(_StrictEvidence):
    event_index: int = Field(ge=0, le=511)
    item_kind: ItemContainerKind
    items_kind: ItemsContainerKind
    overflow_item_kind: ItemContainerKind
    item_model_id_kind: WireIntegerKind | Literal["redacted"]
    item: AcquisitionItemWire | None
    items: tuple[AcquisitionItemWire, ...] = Field(max_length=512)
    overflow_item: AcquisitionItemWire | None

    @property
    def malformed(self) -> bool:
        return any(
            kind == "other"
            for kind in (
                self.item_kind,
                self.items_kind,
                self.overflow_item_kind,
                self.item_model_id_kind,
            )
        ) or any(
            any(
                kind == "other"
                for kind in (
                    wire.instance_id_kind,
                    wire.model_id_kind,
                    wire.fake_model_id_kind,
                    wire.used_kind,
                )
            )
            for wire in (
                *self.items,
                *((self.item,) if self.item else ()),
                *((self.overflow_item,) if self.overflow_item else ()),
            )
        )


def _validate_item_wire(item: AcquisitionItem, wire: AcquisitionItemWire) -> None:
    if (
        item.raw_index != wire.raw_index
        or any(
            (value is not None) != (kind == "positive_integer")
            for value, kind in (
                (item.instance_id, wire.instance_id_kind),
                (item.model_id, wire.model_id_kind),
                (item.fake_model_id, wire.fake_model_id_kind),
            )
        )
        or (item.used is not None) != (wire.used_kind == "boolean")
    ):
        raise ValueError("event wire classification differs from sanitized item")


class AcquisitionSnapshotV3(AcquisitionSnapshotV2):
    event_item_wire: tuple[AcquisitionEventWire, ...] = Field(max_length=512)

    @model_validator(mode="after")
    def validate_event_wire(self) -> AcquisitionSnapshotV3:
        if [wire.event_index for wire in self.event_item_wire] != [
            event.event_index for event in self.events
        ]:
            raise ValueError("event wire metadata must cover every reviewed event")
        for event, wire in zip(self.events, self.event_item_wire, strict=True):
            kinds = (
                wire.item_kind,
                wire.items_kind,
                wire.overflow_item_kind,
                wire.item_model_id_kind,
            )
            if not event.self_item_payload_bound:
                if kinds != ("redacted",) * 4 or wire.item or wire.items or wire.overflow_item:
                    raise ValueError("unbound event wire metadata must be redacted")
                continue
            if "redacted" in kinds:
                raise ValueError("bound event wire metadata cannot be redacted")
            for payload, sidecar, kind in (
                (event.item, wire.item, wire.item_kind),
                (event.overflow_item, wire.overflow_item, wire.overflow_item_kind),
            ):
                if (payload is not None) != (kind == "object") or (sidecar is not None) != (
                    payload is not None
                ):
                    raise ValueError("event item container classification differs")
                if payload is not None and sidecar is not None:
                    if payload.raw_index != 0:
                        raise ValueError("single event item requires raw index zero")
                    _validate_item_wire(payload, sidecar)
            if len(event.items) != len(wire.items) or (
                wire.items_kind != "array" and (event.items or wire.items)
            ):
                raise ValueError("event selection wire metadata differs from array")
            for index, (payload, sidecar) in enumerate(zip(event.items, wire.items, strict=True)):
                if payload.raw_index != index:
                    raise ValueError("event selection raw indices must preserve order")
                _validate_item_wire(payload, sidecar)
            if (event.item_model_id is not None) != (wire.item_model_id_kind == "positive_integer"):
                raise ValueError("event model classification differs from sanitized ID")
        return self


class AcquisitionProbeReadV3(_StrictEvidence):
    schema_version: Literal[3]
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV3, ...] = Field(max_length=4096)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_capture_version(cls, value: object) -> object:
        if type(value) is not int or value != 3:
            raise ValueError("capture version requires the exact integer 3")
        return value

    @model_validator(mode="after")
    def ordered_queue(self) -> AcquisitionProbeReadV3:
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
            raise ValueError("invalid ordered acquisition v3 queue")
        return self


class AcquisitionEvidenceBatchV3(_StrictEvidence):
    schema_version: Literal[3] = 3
    source_kind: Literal["official-acquisition-evidence-v3"] = "official-acquisition-evidence-v3"
    observed_at: datetime
    client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV3, ...] = Field(max_length=4096)
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_capture_version(cls, value: object) -> object:
        if type(value) is not int or value != 3:
            raise ValueError("capture version requires the exact integer 3")
        return value

    @field_validator("client_sha256")
    @classmethod
    def reviewed_decoder_client(cls, value: str) -> str:
        if value != ACQUISITION_REVIEWED_CLIENT_SHA256:
            raise ValueError("acquisition v3 interpretation requires the reviewed client hash")
        return value

    @model_validator(mode="after")
    def valid_saved_subset(self) -> AcquisitionEvidenceBatchV3:
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
            raise ValueError("invalid saved acquisition v3 subset")
        if self.input_sha256 != acquisition_batch_digest(
            self.client_sha256, self.catalog_sha256, self.status, self.snapshots
        ):
            raise ValueError("acquisition batch content digest differs")
        return self
