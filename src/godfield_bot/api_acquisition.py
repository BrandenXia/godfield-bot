"""Self-only acquisition evidence from existing private API reads, not policy."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
    MAX_SAFE_INTEGER,
    REVIEWED_EVENT_ACTIONS,
    AcquisitionCollectorError,
    AcquisitionProbeStatus,
    _StrictEvidence,
)
from godfield_bot.acquisition_v2 import PHASE_PRESERVING_ACTIONS, TARGET_REMOVAL_ACTIONS
from godfield_bot.acquisition_v5 import AcquisitionSnapshotV5
from godfield_bot.api_account import PYGODFIELD_REVISION
from godfield_bot.domain.run import EventKind
from godfield_bot.run_store import RunStore


def private_acquisition_digest(
    api_environment_sha256: str,
    status: AcquisitionProbeStatus,
    snapshots: tuple[AcquisitionSnapshotV5, ...],
) -> str:
    material = {
        "source_kind": "private-api-acquisition-evidence-v5",
        "delivery_kind": "api-polling",
        "pygodfield_revision": PYGODFIELD_REVISION,
        "api_environment_sha256": api_environment_sha256,
        "client_sha256": ACQUISITION_REVIEWED_CLIENT_SHA256,
        "catalog_sha256": ACQUISITION_REVIEWED_CATALOG_SHA256,
        "status": status.model_dump(mode="json"),
        "snapshots": [row.model_dump(mode="json") for row in snapshots],
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class PrivateAcquisitionEvidenceBatch(_StrictEvidence):
    schema_version: Literal[5] = 5
    source_kind: Literal["private-api-acquisition-evidence-v5"] = (
        "private-api-acquisition-evidence-v5"
    )
    delivery_kind: Literal["api-polling"] = "api-polling"
    observed_at: datetime
    # This is the reviewed DECODER pin, not an observed browser client.
    client_sha256: str = Field(
        default=ACQUISITION_REVIEWED_CLIENT_SHA256, pattern=r"^[0-9a-f]{64}$"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pygodfield_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    api_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AcquisitionProbeStatus
    snapshots: tuple[AcquisitionSnapshotV5, ...] = Field(max_length=1)
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int or value != 5:
            raise ValueError("private acquisition requires exact capture version 5")
        return value

    @model_validator(mode="after")
    def checked_provenance_and_delivery(self) -> PrivateAcquisitionEvidenceBatch:
        expected_environment = hashlib.sha256(
            f"pygodfield:{PYGODFIELD_REVISION}:catalog:{self.catalog_sha256}".encode()
        ).hexdigest()
        if (
            self.client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.pygodfield_revision != PYGODFIELD_REVISION
            or self.api_environment_sha256 != expected_environment
        ):
            raise ValueError("private acquisition provenance differs from reviewed pins")
        status = self.status
        sequences = [row.source_sequence for row in self.snapshots]
        if (
            status.hook_installed
            or status.listener_registrations != 0
            or status.hook_error_count != 0
            or status.dropped_snapshot_count != 0
            or status.source_sequence < 1
            or status.acknowledged_sequence != status.source_sequence - 1
            or status.rejected_snapshot_count > status.source_sequence
            or (not sequences and status.rejected_snapshot_count < 1)
            or len(sequences) != status.pending_snapshot_count
            or (sequences and sequences != [status.source_sequence])
            or any(seq <= status.acknowledged_sequence for seq in sequences)
        ):
            raise ValueError("invalid private acquisition delivery counters")
        if self.input_sha256 != private_acquisition_digest(
            self.api_environment_sha256, self.status, self.snapshots
        ):
            raise ValueError("private acquisition content digest differs")
        return self


class PrivateAcquisitionSummary(_StrictEvidence):
    source_kind: Literal["private-api-acquisition-collector-summary-v1"] = (
        "private-api-acquisition-collector-summary-v1"
    )
    saved_snapshot_count: int = Field(ge=0)
    detected_source_gap_count: int = Field(ge=0)
    read_error_count: int = Field(ge=0)
    ack_error_count: Literal[0] = 0
    streams: tuple[AcquisitionProbeStatus, ...]
    final_poll_succeeded: None = None
    final_flush_succeeded: Literal[True] = True
    training_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False

    @model_validator(mode="after")
    def honest_flush_counters(self) -> PrivateAcquisitionSummary:
        rejected = sum(status.rejected_snapshot_count for status in self.streams)
        if (
            len({status.stream_id for status in self.streams}) != len(self.streams)
            or any(
                status.source_sequence < 1
                or status.acknowledged_sequence != status.source_sequence - 1
                or status.hook_installed
                or status.listener_registrations != 0
                or status.hook_error_count != 0
                or status.dropped_snapshot_count != 0
                for status in self.streams
            )
            or self.saved_snapshot_count
            != sum(status.source_sequence for status in self.streams) - rejected
            or self.detected_source_gap_count != rejected
            or self.read_error_count < rejected
        ):
            raise ValueError("invalid private acquisition flush counters")
        return self


def _integer(raw: object, *, minimum: int = 1) -> int | None:
    if type(raw) is int:
        return raw if minimum <= raw <= MAX_SAFE_INTEGER else None
    if type(raw) is float and math.isfinite(raw) and raw.is_integer():
        return int(raw) if minimum <= raw <= MAX_SAFE_INTEGER else None
    return None


def _integer_kind(raw: dict[str, Any], key: str) -> str:
    if key not in raw:
        return "missing"
    if raw[key] is None:
        return "null"
    if _integer(raw[key]) is not None:
        return "positive_integer"
    return "zero" if type(raw[key]) in {int, float} and raw[key] == 0 else "other"


def _item(raw: object, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("invalid acquisition item")
    return {
        "raw_index": index,
        "instance_id": _integer(raw.get("id")),
        "model_id": _integer(raw.get("modelId")),
        "fake_model_id": _integer(raw.get("fakeModelId")),
        "used": raw.get("used") if type(raw.get("used")) is bool else None,
    }


def _items(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > 512:
        raise ValueError("invalid acquisition item array")
    return [_item(value, index) for index, value in enumerate(raw)]


def _wire_item(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "raw_index": index,
        "instance_id_kind": _integer_kind(raw, "id"),
        "model_id_kind": _integer_kind(raw, "modelId"),
        "fake_model_id_kind": _integer_kind(raw, "fakeModelId"),
        "used_kind": "missing"
        if "used" not in raw
        else "null"
        if raw["used"] is None
        else "boolean"
        if type(raw["used"]) is bool
        else "other",
    }


def _container(raw: dict[str, Any], key: str, kind: type[object]) -> str:
    if key not in raw:
        return "missing"
    if raw[key] is None:
        return "null"
    return ("array" if kind is list else "object") if isinstance(raw[key], kind) else "other"


def _event_wire(raw: dict[str, Any], index: int, bound: bool) -> dict[str, Any]:
    return {
        "event_index": index,
        "item_kind": _container(raw, "item", dict) if bound else "redacted",
        "items_kind": _container(raw, "items", list) if bound else "redacted",
        "overflow_item_kind": _container(raw, "overflowItem", dict) if bound else "redacted",
        "item_model_id_kind": _integer_kind(raw, "itemModelId") if bound else "redacted",
        "item": _wire_item(raw["item"], 0) if bound and isinstance(raw.get("item"), dict) else None,
        "items": [_wire_item(value, i) for i, value in enumerate(raw["items"])]
        if bound and isinstance(raw.get("items"), list)
        else [],
        "overflow_item": _wire_item(raw["overflowItem"], 0)
        if bound and isinstance(raw.get("overflowItem"), dict)
        else None,
    }


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class PrivateAcquisitionRecorder:
    """Record before policy dispatch; acknowledge locally only after durable save.

    Every successful API read is a delivery, including repeated server versions.
    No .used/.events property defaults, arbitrary raw fields, or opponent items
    enter evidence. The strict v5 model independently checks the projection.
    """

    def __init__(self, store: RunStore, run_id: str, *, identity: str, api_environment_sha256: str):
        self.store, self.run_id, self.identity = store, run_id, identity
        self.environment = api_environment_sha256
        self.stream = str(uuid4())
        self.sequence = self.acknowledged = self.rejected = self.saved = self.read_errors = 0
        self.statuses: dict[str, AcquisitionProbeStatus] = {}
        self.previous: AcquisitionSnapshotV5 | None = None
        self.previous_stamp: str | None = None
        self.finalized = False

    def boundary(self) -> None:
        self.previous = None
        self.previous_stamp = None
        if self.sequence:
            self.stream = str(uuid4())
            self.sequence = self.acknowledged = self.rejected = 0

    def read_failed(self) -> None:
        self.read_errors += 1
        self.store.append_event(
            self.run_id,
            EventKind.EVIDENCE,
            AcquisitionCollectorError(
                phase="read",
                error_type="PrivateApiAcquisitionReadFailure",
                read_error_count=self.read_errors,
                ack_error_count=0,
            ),
        )
        self.boundary()

    def capture(self, raw_room: object, *, user_id: str) -> bool:
        if self.finalized:
            raise ValueError("private acquisition recorder is finalized")
        game = raw_room.get("game") if isinstance(raw_room, dict) else None
        if game is None:
            self.boundary()
            return False
        players = game.get("players") if isinstance(game, dict) else None
        matches = (
            [p for p in players if isinstance(p, dict) and p.get("userId") == user_id]
            if isinstance(players, list)
            else []
        )
        if isinstance(players, list) and not matches:
            self.boundary()
            return False
        if (
            self.previous is not None
            and self.previous.is_over is True
            and isinstance(game, dict)
            and game.get("isOver") is False
        ):
            self.boundary()
        self.sequence += 1
        snapshots: tuple[AcquisitionSnapshotV5, ...]
        try:
            if (
                not isinstance(players, list)
                or len(matches) != 1
                or matches[0].get("name") != self.identity
                or sum(isinstance(p, dict) and p.get("name") == self.identity for p in players) != 1
            ):
                raise ValueError("ambiguous private acquisition self")
            snapshot, stamp = self._project(game, matches[0])
            snapshots = (snapshot,)
        except (ValueError, TypeError, KeyError):
            self.rejected += 1
            self.read_errors += 1
            self.previous = None
            self.previous_stamp = None
            snapshots = ()
        status = AcquisitionProbeStatus(
            stream_id=self.stream,
            source_sequence=self.sequence,
            acknowledged_sequence=self.acknowledged,
            pending_snapshot_count=len(snapshots),
            dropped_snapshot_count=0,
            rejected_snapshot_count=self.rejected,
            hook_error_count=0,
            hook_installed=False,
            listener_registrations=0,
        )
        batch = PrivateAcquisitionEvidenceBatch(
            observed_at=datetime.now(UTC),
            catalog_sha256=ACQUISITION_REVIEWED_CATALOG_SHA256,
            pygodfield_revision=PYGODFIELD_REVISION,
            api_environment_sha256=self.environment,
            input_sha256=private_acquisition_digest(self.environment, status, snapshots),
            status=status,
            snapshots=snapshots,
        )
        self.store.append_event(self.run_id, EventKind.EVIDENCE, batch)
        self.statuses[self.stream] = status
        self.acknowledged = self.sequence
        self.saved += len(snapshots)
        if snapshots:
            self.previous, self.previous_stamp = snapshot, stamp
        return bool(snapshots)

    def _project(
        self, game: dict[str, Any], me: dict[str, Any]
    ) -> tuple[AcquisitionSnapshotV5, str]:
        self_id, gf, update = (
            _integer(me.get("id")),
            _integer(game.get("gf"), minimum=0),
            _integer(game.get("updateCount"), minimum=0),
        )
        players = game["players"]
        ids = [_integer(p.get("id")) if isinstance(p, dict) else None for p in players]
        raw_events = game.get("events")
        if (
            self_id is None
            or gf is None
            or update is None
            or len(players) > 256
            or None in ids
            or len(set(ids)) != len(ids)
            or not isinstance(raw_events, list)
            or len(raw_events) > 512
        ):
            raise ValueError("invalid private acquisition version or players")
        player_ids = sorted(value for value in ids if value is not None)
        owned = _items(me.get("items"))
        wires = [_wire_item(value, i) for i, value in enumerate(me["items"])]
        stamp = _canonical(
            {
                "gf": gf,
                "update": update,
                "selfId": self_id,
                "playerIds": player_ids,
                "selfItems": owned,
                "selfWire": wires,
                "events": [
                    [
                        raw.get("action")
                        if isinstance(raw.get("action"), str)
                        and raw.get("action") in REVIEWED_EVENT_ACTIONS
                        else None,
                        _integer(raw.get("playerId")),
                    ]
                    if isinstance(raw, dict)
                    else None
                    for raw in raw_events
                ],
            }
        )
        before, phase_input = None, "initial"
        previous = self.previous
        if previous is not None:
            last = previous.phase_after
            same = self_id == last.self_player_id and tuple(player_ids) == last.player_ids
            if same and gf == last.field_number and update == last.update_count:
                phase_input = "repeat" if stamp == self.previous_stamp else "inconsistent_repeat"
                if phase_input == "repeat":
                    before = previous.phase_before
            elif (
                same
                and gf >= last.field_number
                and update == last.update_count + 1
                and self.sequence == last.source_sequence + 1
            ):
                before, phase_input = last, "consecutive"
            else:
                phase_input = "gap_or_boundary"

        def events_for(anchor: Any) -> dict[str, Any]:
            turn = anchor.turn_player_id if anchor is not None else None
            target = anchor.target_player_id if anchor is not None else None
            events, owners, unknown, event_wires = [], [], [], []
            redacted = 0
            for index, raw in enumerate(raw_events):
                if (
                    not isinstance(raw, dict)
                    or not isinstance(raw.get("action"), str)
                    or raw.get("action") not in REVIEWED_EVENT_ACTIONS
                ):
                    unknown.append(index)
                    turn = target = None
                    continue
                action, actor = raw["action"], _integer(raw.get("playerId"))
                member = actor if actor in player_ids else None
                if action == "advanceGF":
                    turn, target = member, None
                elif action == "setTargetPlayer":
                    target = member if turn is not None and member != turn else None
                elif action == "reflect":
                    turn, target = (
                        (target, turn)
                        if len(player_ids) == 2 and turn is not None and target is not None
                        else (None, None)
                    )
                owner, basis = None, "unresolved"
                if action == "gift" and member is not None:
                    owner, basis = member, "explicit_gift_player"
                elif action == "useAttackItems" and turn is not None:
                    owner, basis = turn, "turn_context"
                elif (action == "useDefenseItems" and target is not None) or (
                    action in TARGET_REMOVAL_ACTIONS
                    and len(player_ids) == 2
                    and turn is not None
                    and target is not None
                ):
                    owner, basis = target, "target_context"
                bound = (
                    owner == self_id and action in PHASE_PRESERVING_ACTIONS | TARGET_REMOVAL_ACTIONS
                )
                redacted += not bound and any(
                    raw.get(k) is not None for k in ("item", "items", "overflowItem", "itemModelId")
                )
                events.append(
                    {
                        "event_index": index,
                        "action": action,
                        "player_id": actor,
                        "target_player_id": _integer(raw.get("targetPlayerId")),
                        "self_item_payload_bound": bound,
                        "item": _item(raw["item"], 0)
                        if bound and isinstance(raw.get("item"), dict)
                        else None,
                        "items": _items(raw["items"])
                        if bound and isinstance(raw.get("items"), list)
                        else [],
                        "overflow_item": _item(raw["overflowItem"], 0)
                        if bound and isinstance(raw.get("overflowItem"), dict)
                        else None,
                        "item_model_id": _integer(raw.get("itemModelId")) if bound else None,
                    }
                )
                owners.append({"event_index": index, "item_owner_player_id": owner, "basis": basis})
                event_wires.append(_event_wire(raw, index, bound))
                if action not in PHASE_PRESERVING_ACTIONS | {
                    "advanceGF",
                    "setTargetPlayer",
                    "reflect",
                }:
                    turn = target = None
            return {
                "events": events,
                "event_owners": owners,
                "unreviewed_event_indices": unknown,
                "event_item_wire": event_wires,
                "redacted_item_event_count": redacted,
                "unreviewed_event_count": len(unknown),
                "turn": turn,
                "target": target,
            }

        projected = events_for(before)
        if phase_input == "repeat" and previous is not None:
            old = previous.model_dump(
                mode="json",
                include={
                    "events",
                    "event_owners",
                    "unreviewed_event_indices",
                    "event_item_wire",
                    "redacted_item_event_count",
                    "unreviewed_event_count",
                },
            )
            if old != {k: v for k, v in projected.items() if k not in {"turn", "target"}}:
                before, phase_input = None, "inconsistent_repeat"
                projected = events_for(None)
        turn, target = projected.pop("turn"), projected.pop("target")
        payload = {
            "source_sequence": self.sequence,
            "captured_at": datetime.now(UTC).isoformat(),
            "field_number": gf,
            "update_count": update,
            "self_player_id": self_id,
            "player_count": len(players),
            "is_over": game.get("isOver") if type(game.get("isOver")) is bool else None,
            "attack_turn_player_id": _integer(game.get("attackTurnPlayerId")),
            "self_items": owned,
            "self_item_wire": wires,
            "phase_input_status": phase_input,
            "phase_before": before.model_dump(mode="json") if before else None,
            "phase_after": {
                "source_sequence": self.sequence,
                "update_count": update,
                "field_number": gf,
                "self_player_id": self_id,
                "player_ids": player_ids,
                "turn_player_id": turn,
                "target_player_id": target,
            },
            **projected,
        }
        if len(_canonical(payload)) > 262144:
            raise ValueError("private acquisition snapshot budget")
        row = AcquisitionSnapshotV5.model_validate_json(_canonical(payload))
        return row, stamp

    def finalize(self) -> None:
        if self.finalized:
            return
        self.store.append_event(
            self.run_id,
            EventKind.EVIDENCE,
            PrivateAcquisitionSummary(
                saved_snapshot_count=self.saved,
                detected_source_gap_count=sum(
                    s.rejected_snapshot_count for s in self.statuses.values()
                ),
                read_error_count=self.read_errors,
                streams=tuple(self.statuses.values()),
            ),
        )
        self.finalized = True
