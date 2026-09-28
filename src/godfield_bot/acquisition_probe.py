"""Passive acquisition transport; no policy authority or inferred rule labels."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from importlib.resources import files
from typing import Literal

from playwright.async_api import BrowserContext, Page
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from godfield_bot.domain.run import EventKind
from godfield_bot.dream_probe import _dream_probe_init_script
from godfield_bot.run_store import RunStore

ACQUISITION_REVIEWED_CLIENT_SHA256 = (
    "764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd"
)
# Unknown action bodies are not retained; runner pins this reviewed client.
REVIEWED_EVENT_ACTIONS = frozenset(
    [
        "addCurse",
        "addItem",
        "advanceGF",
        "attackByGuardian",
        "attackDyingly",
        "attractDanger",
        "block",
        "boostCP",
        "boostCPOfEverybody",
        "boostHP",
        "boostMP",
        "bounce",
        "buy",
        "canNotBuy",
        "counterAttack",
        "danger",
        "dealDamage",
        "dealDarkDamage",
        "die",
        "discard",
        "disease",
        "endGame",
        "exchange",
        "gift",
        "hit",
        "miss",
        "nextAttack",
        "phenomenon",
        "pray",
        "redraw",
        "reflect",
        "removeCurses",
        "removeGuardian",
        "removeItems",
        "removeSomething",
        "removeUsedMiracles",
        "replaceItems",
        "revive",
        "safe",
        "selfCurse",
        "sell",
        "setBought",
        "setCurseOfEverybody",
        "setGuardian",
        "setTargetPlayer",
        "startGame",
        "takeCP",
        "upgradeDisease",
        "upgradeHeaven",
        "useAttackItems",
        "useDefenseItems",
        "useDevilItem",
    ]
)
SELF_ITEM_ACTIONS = frozenset({"gift", "useAttackItems", "useDefenseItems"})
MAX_SAFE_INTEGER = (1 << 53) - 1
ACQUISITION_IO_TIMEOUT_SECONDS = 5.0
ACQUISITION_CAPTURE_SCHEMA_VERSION: Literal[5] = 5


class _StrictEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AcquisitionItem(_StrictEvidence):
    raw_index: int = Field(ge=0, le=511)
    instance_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    model_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    fake_model_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    used: bool | None


class AcquisitionEvent(_StrictEvidence):
    event_index: int = Field(ge=0, le=511)
    action: str
    player_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    target_player_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    self_item_payload_bound: bool
    item: AcquisitionItem | None
    items: tuple[AcquisitionItem, ...] = Field(max_length=512)
    overflow_item: AcquisitionItem | None
    item_model_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)

    @field_validator("action")
    @classmethod
    def reviewed_action(cls, value: str) -> str:
        if value not in REVIEWED_EVENT_ACTIONS:
            raise ValueError("unreviewed acquisition event action")
        return value

    @model_validator(mode="after")
    def unbound_items_are_redacted(self) -> AcquisitionEvent:
        if not self.self_item_payload_bound and (
            self.item is not None
            or self.items
            or self.overflow_item is not None
            or self.item_model_id is not None
        ):
            raise ValueError("unbound event item payload must be redacted")
        return self


class AcquisitionSnapshot(_StrictEvidence):
    source_sequence: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    captured_at: datetime
    field_number: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    update_count: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    self_player_id: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    player_count: int = Field(ge=1, le=256)
    is_over: bool | None
    attack_turn_player_id: int | None = Field(ge=1, le=MAX_SAFE_INTEGER)
    self_items: tuple[AcquisitionItem, ...] = Field(max_length=512)
    events: tuple[AcquisitionEvent, ...] = Field(max_length=512)
    unreviewed_event_count: int = Field(ge=0, le=512)
    redacted_item_event_count: int = Field(ge=0, le=512)

    @model_validator(mode="after")
    def enforce_self_binding(self) -> AcquisitionSnapshot:
        if self.captured_at.utcoffset() is None:
            raise ValueError("acquisition capture timestamp requires a timezone")
        if [item.raw_index for item in self.self_items] != list(range(len(self.self_items))):
            raise ValueError("owned-item raw indices must preserve array order")
        indices = [event.event_index for event in self.events]
        if indices != sorted(set(indices)):
            raise ValueError("acquisition events must preserve distinct array order")
        for event in self.events:
            if event.self_item_payload_bound and (
                event.player_id != self.self_player_id or event.action not in SELF_ITEM_ACTIONS
            ):
                raise ValueError("event items are not bound to a reviewed self-owner action")
        return self


class AcquisitionProbeStatus(_StrictEvidence):
    stream_id: str = Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    source_sequence: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    acknowledged_sequence: int = Field(ge=0, le=MAX_SAFE_INTEGER)
    pending_snapshot_count: int = Field(ge=0, le=4096)
    dropped_snapshot_count: int = Field(ge=0)
    rejected_snapshot_count: int = Field(ge=0)
    hook_error_count: int = Field(ge=0)
    hook_installed: bool
    listener_registrations: int = Field(ge=0)


class AcquisitionProbeRead(_StrictEvidence):
    schema_version: Literal[1]
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshot, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def ordered_queue(self) -> AcquisitionProbeRead:
        sequences = [row.source_sequence for row in self.snapshots]
        if self.status.acknowledged_sequence > self.status.source_sequence:
            raise ValueError("acquisition acknowledgement exceeds the source sequence")
        if sequences != sorted(set(sequences)):
            raise ValueError("acquisition queue is not strictly ordered")
        if len(sequences) != self.status.pending_snapshot_count:
            raise ValueError("acquisition queue length differs from status")
        if sequences and (
            sequences[0] <= self.status.acknowledged_sequence
            or sequences[-1] > self.status.source_sequence
        ):
            raise ValueError("acquisition queue lies outside acknowledged/source versions")
        return self


class AcquisitionEvidenceBatch(_StrictEvidence):
    schema_version: Literal[1] = 1
    source_kind: Literal["official-acquisition-evidence-v1"] = "official-acquisition-evidence-v1"
    observed_at: datetime
    client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshot, ...] = Field(max_length=4096)
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False

    @model_validator(mode="after")
    def valid_saved_subset(self) -> AcquisitionEvidenceBatch:
        sequences = [row.source_sequence for row in self.snapshots]
        if (
            sequences != sorted(set(sequences))
            or len(sequences) > self.status.pending_snapshot_count
        ):
            raise ValueError("saved acquisition subset is not an ordered queue subset")
        if self.status.acknowledged_sequence > self.status.source_sequence or (
            sequences
            and (
                sequences[0] <= self.status.acknowledged_sequence
                or sequences[-1] > self.status.source_sequence
            )
        ):
            raise ValueError("saved acquisition subset lies outside source versions")
        if self.input_sha256 != acquisition_batch_digest(
            self.client_sha256, self.catalog_sha256, self.status, self.snapshots
        ):
            raise ValueError("acquisition batch content digest differs")
        return self


def acquisition_batch_digest(
    client_sha256: str,
    catalog_sha256: str,
    status: AcquisitionProbeStatus,
    snapshots: tuple[AcquisitionSnapshot, ...],
) -> str:
    inputs = {
        "client_sha256": client_sha256,
        "catalog_sha256": catalog_sha256,
        "status": status.model_dump(mode="json"),
        "snapshots": [row.model_dump(mode="json") for row in snapshots],
    }
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def acquisition_probe_init_script(
    identity: str, *, capacity: int = 256, schema_version: Literal[1, 2, 3, 4, 5] = 1
) -> str:
    if not 8 <= capacity <= 4096:
        raise ValueError("acquisition queue capacity must be between 8 and 4096")
    if type(schema_version) is not int or schema_version not in {1, 2, 3, 4, 5}:
        raise ValueError("unsupported acquisition capture schema")
    config = json.dumps(
        {
            "identity": identity,
            "capacity": capacity,
            "event_actions": sorted(REVIEWED_EVENT_ACTIONS),
            "self_item_actions": sorted(SELF_ITEM_ACTIONS),
            "schema_version": schema_version,
        },
        ensure_ascii=False,
    )
    script = files("godfield_bot").joinpath("browser/acquisition_probe.js").read_text("utf-8")
    return script.replace("__GODFIELD_ACQUISITION_CONFIG__", config, 1)


async def install_acquisition_probe(
    context: BrowserContext, *, identity: str, capacity: int = 256, include_dream: bool = False
) -> None:
    script = acquisition_probe_init_script(
        identity, capacity=capacity, schema_version=ACQUISITION_CAPTURE_SCHEMA_VERSION
    )
    if include_dream:
        # Separate Playwright init scripts have no promised execution order.
        script = _dream_probe_init_script(identity) + "\n" + script
    await context.add_init_script(script=script)


ACQUISITION_READ_SCRIPT = """
() => {
  const state = window.__godfieldAcquisitionEvidenceV5 || window.__godfieldAcquisitionEvidenceV4 ||
    window.__godfieldAcquisitionEvidenceV3 ||
    window.__godfieldAcquisitionEvidenceV2 || window.__godfieldAcquisitionEvidenceV1;
  if (!state) return null;
  return {
    schema_version: state.schemaVersion || 1,
    status: {
      stream_id: state.streamId, source_sequence: state.sequence,
      acknowledged_sequence: state.acknowledged, pending_snapshot_count: state.queue.length,
      dropped_snapshot_count: state.dropped, rejected_snapshot_count: state.rejected,
      hook_error_count: state.hookErrors, hook_installed: state.hookInstalled,
      listener_registrations: state.registrations,
    },
    snapshots: state.queue.slice(),
  };
}
"""

ACQUISITION_ACK_SCRIPT = """
(ack) => {
  const state = window.__godfieldAcquisitionEvidenceV5 || window.__godfieldAcquisitionEvidenceV4 ||
    window.__godfieldAcquisitionEvidenceV3 ||
    window.__godfieldAcquisitionEvidenceV2 || window.__godfieldAcquisitionEvidenceV1;
  if (!state || state.streamId !== ack.stream_id ||
      !Number.isSafeInteger(ack.sequence) || ack.sequence < state.acknowledged ||
      ack.sequence > state.sequence) return false;
  state.queue = state.queue.filter((row) => row.source_sequence > ack.sequence);
  state.acknowledged = ack.sequence;
  return true;
}
"""


class AcquisitionCollectorError(_StrictEvidence):
    source_kind: Literal["official-acquisition-collector-error-v1"] = (
        "official-acquisition-collector-error-v1"
    )
    phase: Literal["read", "ack"]
    error_type: str
    read_error_count: int = Field(ge=0)
    ack_error_count: int = Field(ge=0)
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False


class AcquisitionCollectorSummary(_StrictEvidence):
    source_kind: Literal["official-acquisition-collector-summary-v1"] = (
        "official-acquisition-collector-summary-v1"
    )
    saved_snapshot_count: int = Field(ge=0)
    detected_source_gap_count: int = Field(ge=0)
    read_error_count: int = Field(ge=0)
    ack_error_count: int = Field(ge=0)
    streams: tuple[AcquisitionProbeStatus, ...]
    final_poll_succeeded: bool
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False


class AcquisitionRecorder:
    """Save before acknowledgement; telemetry errors never advance policy state."""

    def __init__(
        self, store: RunStore, run_id: str, *, client_sha256: str, catalog_sha256: str
    ) -> None:
        self.store, self.run_id = store, run_id
        self.client_sha256, self.catalog_sha256 = client_sha256, catalog_sha256
        self.last_seen: dict[str, int] = {}
        self.last_status: dict[str, AcquisitionProbeStatus] = {}
        self.last_digest: dict[str, str] = {}
        self.saved_snapshots = self.source_gaps = self.read_errors = self.ack_errors = 0

    def _record_error(self, phase: Literal["read", "ack"], error_type: str) -> None:
        if phase == "read":
            self.read_errors += 1
        else:
            self.ack_errors += 1
        self.store.append_event(
            self.run_id,
            EventKind.EVIDENCE,
            AcquisitionCollectorError(
                phase=phase,
                error_type=error_type,
                read_error_count=self.read_errors,
                ack_error_count=self.ack_errors,
            ),
        )

    async def poll(self, page: Page) -> bool:
        from godfield_bot.acquisition_v2 import AcquisitionEvidenceBatchV2, AcquisitionProbeReadV2
        from godfield_bot.acquisition_v3 import AcquisitionEvidenceBatchV3, AcquisitionProbeReadV3
        from godfield_bot.acquisition_v4 import AcquisitionEvidenceBatchV4, AcquisitionProbeReadV4
        from godfield_bot.acquisition_v5 import AcquisitionEvidenceBatchV5, AcquisitionProbeReadV5

        try:
            async with asyncio.timeout(ACQUISITION_IO_TIMEOUT_SECONDS):
                raw = await page.evaluate(ACQUISITION_READ_SCRIPT)
            evidence: (
                AcquisitionProbeRead
                | AcquisitionProbeReadV2
                | AcquisitionProbeReadV3
                | AcquisitionProbeReadV4
                | AcquisitionProbeReadV5
            )
            if (
                not isinstance(raw, dict)
                or type(raw.get("schema_version")) is not int
                or raw["schema_version"] not in {1, 2, 3, 4, 5}
            ):
                raise ValueError("unsupported acquisition capture schema")
            if raw["schema_version"] == 5:
                evidence = AcquisitionProbeReadV5.model_validate_json(json.dumps(raw))
            elif raw["schema_version"] == 4:
                evidence = AcquisitionProbeReadV4.model_validate_json(json.dumps(raw))
            elif raw["schema_version"] == 3:
                evidence = AcquisitionProbeReadV3.model_validate_json(json.dumps(raw))
            elif raw["schema_version"] == 2:
                evidence = AcquisitionProbeReadV2.model_validate_json(json.dumps(raw))
            else:
                evidence = AcquisitionProbeRead.model_validate_json(json.dumps(raw))
        except (PlaywrightError, ValueError, TypeError, TimeoutError) as error:
            self._record_error("read", type(error).__name__)
            return False
        stream = evidence.status.stream_id
        last = self.last_seen.get(stream, 0)
        snapshots = tuple(row for row in evidence.snapshots if row.source_sequence > last)
        digest = acquisition_batch_digest(
            self.client_sha256, self.catalog_sha256, evidence.status, snapshots
        )
        if self.last_digest.get(stream) != digest:
            batch: (
                AcquisitionEvidenceBatch
                | AcquisitionEvidenceBatchV2
                | AcquisitionEvidenceBatchV3
                | AcquisitionEvidenceBatchV4
                | AcquisitionEvidenceBatchV5
            )
            if isinstance(evidence, AcquisitionProbeReadV5):
                batch = AcquisitionEvidenceBatchV5(
                    observed_at=datetime.now(UTC),
                    client_sha256=self.client_sha256,
                    catalog_sha256=self.catalog_sha256,
                    input_sha256=digest,
                    status=evidence.status,
                    snapshots=tuple(
                        row for row in evidence.snapshots if row.source_sequence > last
                    ),
                )
            elif isinstance(evidence, AcquisitionProbeReadV4):
                batch = AcquisitionEvidenceBatchV4(
                    observed_at=datetime.now(UTC),
                    client_sha256=self.client_sha256,
                    catalog_sha256=self.catalog_sha256,
                    input_sha256=digest,
                    status=evidence.status,
                    snapshots=tuple(
                        row for row in evidence.snapshots if row.source_sequence > last
                    ),
                )
            elif isinstance(evidence, AcquisitionProbeReadV3):
                batch = AcquisitionEvidenceBatchV3(
                    observed_at=datetime.now(UTC),
                    client_sha256=self.client_sha256,
                    catalog_sha256=self.catalog_sha256,
                    input_sha256=digest,
                    status=evidence.status,
                    snapshots=tuple(
                        row for row in evidence.snapshots if row.source_sequence > last
                    ),
                )
            elif isinstance(evidence, AcquisitionProbeReadV2):
                batch = AcquisitionEvidenceBatchV2(
                    observed_at=datetime.now(UTC),
                    client_sha256=self.client_sha256,
                    catalog_sha256=self.catalog_sha256,
                    input_sha256=digest,
                    status=evidence.status,
                    snapshots=tuple(
                        row for row in evidence.snapshots if row.source_sequence > last
                    ),
                )
            else:
                batch = AcquisitionEvidenceBatch(
                    observed_at=datetime.now(UTC),
                    client_sha256=self.client_sha256,
                    catalog_sha256=self.catalog_sha256,
                    input_sha256=digest,
                    status=evidence.status,
                    snapshots=snapshots,
                )
            # Storage failures propagate: acknowledgement must never precede a
            # durable commit, and a broken trajectory store is not a probe fault.
            self.store.append_event(self.run_id, EventKind.EVIDENCE, batch)
            self.last_digest[stream] = digest
            for row in snapshots:
                self.source_gaps += max(0, row.source_sequence - last - 1)
                last = row.source_sequence
            self.last_seen[stream] = last
            self.saved_snapshots += len(snapshots)
        self.last_status[stream] = evidence.status
        try:
            async with asyncio.timeout(ACQUISITION_IO_TIMEOUT_SECONDS):
                acknowledged = await page.evaluate(
                    ACQUISITION_ACK_SCRIPT,
                    {"stream_id": stream, "sequence": evidence.status.source_sequence},
                )
        except (PlaywrightError, ValueError, TypeError, TimeoutError) as error:
            self._record_error("ack", type(error).__name__)
            return False
        if acknowledged is not True:
            self._record_error("ack", "StreamChangedOrInvalidAcknowledgement")
            return False
        return True

    async def finalize(self, page: Page) -> None:
        succeeded = await self.poll(page)
        self.store.append_event(
            self.run_id,
            EventKind.EVIDENCE,
            AcquisitionCollectorSummary(
                saved_snapshot_count=self.saved_snapshots,
                detected_source_gap_count=self.source_gaps,
                read_error_count=self.read_errors,
                ack_error_count=self.ack_errors,
                streams=tuple(self.last_status.values()),
                final_poll_succeeded=succeeded,
            ),
        )
