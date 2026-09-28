"""Pinned, seeded duel reflection ownership; no historical evidence upgrades."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import Field, field_validator, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    AcquisitionProbeStatus,
    _StrictEvidence,
    acquisition_batch_digest,
)
from godfield_bot.acquisition_v3 import AcquisitionSnapshotV3


class AcquisitionSnapshotV4(AcquisitionSnapshotV3):
    reflection_duel_context: ClassVar[bool] = True


class AcquisitionProbeReadV4(_StrictEvidence):
    schema_version: Literal[4]
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV4, ...] = Field(max_length=4096)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_capture_version(cls, value: object) -> object:
        if type(value) is not int or value != 4:
            raise ValueError("capture version requires the exact integer 4")
        return value

    @model_validator(mode="after")
    def ordered_queue(self) -> AcquisitionProbeReadV4:
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
            raise ValueError("invalid ordered acquisition v4 queue")
        return self


class AcquisitionEvidenceBatchV4(_StrictEvidence):
    schema_version: Literal[4] = 4
    source_kind: Literal["official-acquisition-evidence-v4"] = "official-acquisition-evidence-v4"
    observed_at: datetime
    client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV4, ...] = Field(max_length=4096)
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_capture_version(cls, value: object) -> object:
        if type(value) is not int or value != 4:
            raise ValueError("capture version requires the exact integer 4")
        return value

    @field_validator("client_sha256")
    @classmethod
    def reviewed_decoder_client(cls, value: str) -> str:
        if value != ACQUISITION_REVIEWED_CLIENT_SHA256:
            raise ValueError("acquisition v4 interpretation requires the reviewed client hash")
        return value

    @model_validator(mode="after")
    def valid_saved_subset(self) -> AcquisitionEvidenceBatchV4:
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
            raise ValueError("invalid saved acquisition v4 subset")
        if self.input_sha256 != acquisition_batch_digest(
            self.client_sha256, self.catalog_sha256, self.status, self.snapshots
        ):
            raise ValueError("acquisition batch content digest differs")
        return self
