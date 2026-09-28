"""Offline inventory observations, never acquisition rules or training labels."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.dream_probe import DreamProbeSample


class InventoryObservedChange(BaseModel):
    before_source_sequence: int
    after_source_sequence: int
    before_update_count: int
    after_update_count: int
    added_instance_ids: tuple[int, ...]
    removed_instance_ids: tuple[int, ...]
    newly_used_retained_instance_ids: tuple[int, ...]
    no_longer_used_retained_instance_ids: tuple[int, ...]
    changed_known_model_instance_ids: tuple[int, ...]


class InventoryEvidenceAudit(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["official-inventory-observation-audit"] = (
        "official-inventory-observation-audit"
    )
    sample_count: int = Field(ge=0)
    invalid_instance_sample_count: int = Field(ge=0)
    max_distinct_instances: int = Field(ge=0)
    max_unused_distinct_instances: int = Field(ge=0)
    max_known_unused_distinct_instances: int = Field(ge=0)
    max_used_distinct_instances: int = Field(ge=0)
    overflow_observation_count: int = Field(ge=0)
    repeated_version_observation_count: int = Field(ge=0)
    inconsistent_version_pair_count: int = Field(ge=0)
    boundary_pair_count: int = Field(ge=0)
    gap_pair_count: int = Field(ge=0)
    adjacent_pair_count: int = Field(ge=0)
    changed_adjacent_pair_count: int = Field(ge=0)
    changes: tuple[InventoryObservedChange, ...]
    changes_truncated: bool
    promotion_eligible: Literal[False] = False
    acquisition_rule_eligible: Literal[False] = False


def _instances(sample: DreamProbeSample) -> dict[int, tuple[bool, int | None]] | None:
    instances: dict[int, tuple[bool, int | None]] = {}
    for item in sample.items:
        identity = item.instance_id
        if identity is None or identity in instances:
            return None
        instances[identity] = (
            item.used,
            item.true_identity.model_id if item.true_identity is not None else None,
        )
    return instances


def audit_inventory_samples(
    samples: tuple[DreamProbeSample, ...], *, maximum_changes: int = 32
) -> InventoryEvidenceAudit:
    """Count identified items and describe only consecutive observed versions.

    An added item is not automatically a gift, a removed item is not necessarily
    consumed, and an unused item is not necessarily selectable. No transition
    inference crosses missing versions, invalid IDs, or game/probe boundaries.
    """

    if not 0 <= maximum_changes <= 1024:
        raise ValueError("maximum_changes must be between zero and 1024")
    invalid = maximum = unused_max = known_unused_max = used_max = overflow = 0
    repeated = inconsistent = boundaries = gaps = adjacent = changed = 0
    changes: list[InventoryObservedChange] = []
    previous: DreamProbeSample | None = None
    previous_instances: dict[int, tuple[bool, int | None]] = {}
    for sample in samples:
        instances = _instances(sample)
        if instances is None:
            invalid += 1
            previous = None
            continue
        unused = sum(not used for used, _ in instances.values())
        maximum = max(maximum, len(instances))
        unused_max = max(unused_max, unused)
        used_max = max(used_max, len(instances) - unused)
        known_unused_max = max(
            known_unused_max,
            sum(not item.used and item.true_identity is not None for item in sample.items),
        )
        overflow += int(len(instances) > 9)
        if previous is not None:
            if (
                sample.self_player_id != previous.self_player_id
                or sample.field_number < previous.field_number
                or sample.source_sequence < previous.source_sequence
                or sample.update_count < previous.update_count
            ):
                boundaries += 1
            elif sample.update_count == previous.update_count:
                if instances == previous_instances:
                    repeated += 1
                else:
                    inconsistent += 1
                    previous = None
                    continue
            elif (
                sample.source_sequence != previous.source_sequence + 1
                or sample.update_count != previous.update_count + 1
            ):
                gaps += 1
            else:
                adjacent += 1
                before, after = set(previous_instances), set(instances)
                retained = before & after
                row = InventoryObservedChange(
                    before_source_sequence=previous.source_sequence,
                    after_source_sequence=sample.source_sequence,
                    before_update_count=previous.update_count,
                    after_update_count=sample.update_count,
                    added_instance_ids=tuple(sorted(after - before)),
                    removed_instance_ids=tuple(sorted(before - after)),
                    newly_used_retained_instance_ids=tuple(
                        sorted(
                            i for i in retained if not previous_instances[i][0] and instances[i][0]
                        )
                    ),
                    no_longer_used_retained_instance_ids=tuple(
                        sorted(
                            i for i in retained if previous_instances[i][0] and not instances[i][0]
                        )
                    ),
                    changed_known_model_instance_ids=tuple(
                        sorted(
                            i
                            for i in retained
                            if previous_instances[i][1] is not None
                            and instances[i][1] is not None
                            and previous_instances[i][1] != instances[i][1]
                        )
                    ),
                )
                if instances != previous_instances:
                    changed += 1
                    if len(changes) < maximum_changes:
                        changes.append(row)
        previous = sample
        previous_instances = instances
    return InventoryEvidenceAudit(
        sample_count=len(samples),
        invalid_instance_sample_count=invalid,
        max_distinct_instances=maximum,
        max_unused_distinct_instances=unused_max,
        max_known_unused_distinct_instances=known_unused_max,
        max_used_distinct_instances=used_max,
        overflow_observation_count=overflow,
        repeated_version_observation_count=repeated,
        inconsistent_version_pair_count=inconsistent,
        boundary_pair_count=boundaries,
        gap_pair_count=gaps,
        adjacent_pair_count=adjacent,
        changed_adjacent_pair_count=changed,
        changes=tuple(changes),
        changes_truncated=changed > len(changes),
    )


def audit_inventory_run(database: Path, run_id: str) -> dict[str, object]:
    """Read existing SQLite evidence without creating or changing run history."""

    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute(
            "SELECT mode, client_sha256 FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise ValueError("unknown run")
        payloads = connection.execute(
            "SELECT sequence, payload_json FROM events "
            "WHERE run_id = ? AND kind = 'evidence' ORDER BY sequence",
            (run_id,),
        ).fetchall()
    samples: list[DreamProbeSample] = []
    evidence: list[dict[str, object]] = []
    for row in payloads:
        payload = json.loads(row["payload_json"])
        if isinstance(payload, dict) and "dream_active" in payload and "items" in payload:
            samples.append(DreamProbeSample.model_validate(payload))
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
        "input_sha256": hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        **audit_inventory_samples(tuple(samples)).model_dump(mode="json"),
    }
