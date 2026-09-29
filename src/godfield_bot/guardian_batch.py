"""Catalog-pinned entry point for the provisional native guardian lifecycle batch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.provisional_rules import (
    ProvisionalRuleUnavailableError,
    build_provisional_guardian_plan,
)

if TYPE_CHECKING:
    from godfield_sim import GuardianLifecycleBatch


class GuardianLifecycleMetadata(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["caller-driven-guardian-lifecycle-batch-v1"] = (
        "caller-driven-guardian-lifecycle-batch-v1"
    )
    kernel_schema_version: Literal[1] = 1
    observation_schema_version: Literal[1] = 1
    ruleset_id: Literal["caller-driven-guardian-lifecycle-provisional-v1"] = (
        "caller-driven-guardian-lifecycle-provisional-v1"
    )
    picker_ruleset_id: str
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(gt=0)
    player_count: int = Field(ge=2, le=9)
    slots_per_environment: int = Field(ge=1, le=64)
    weighted_profile_count: Literal[40] = 40
    caller_driven_events_only: Literal[True] = True
    effect_resolution_implemented: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False


@dataclass(frozen=True)
class ProvisionalGuardianBatch:
    batch: GuardianLifecycleBatch
    metadata: GuardianLifecycleMetadata


def create_provisional_guardian_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    slots_per_environment: int = 8,
) -> ProvisionalGuardianBatch:
    """Construct an isolated native state batch from exactly reviewed sources."""

    plan = build_provisional_guardian_plan(
        read_api_catalog_snapshot(catalog_path),
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "guardian lifecycle batch requires the native simulation extra"
        ) from None
    if (
        getattr(native, "GUARDIAN_LIFECYCLE_KERNEL_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_LIFECYCLE_OBSERVATION_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_LIFECYCLE_RULESET_ID", None)
        != "caller-driven-guardian-lifecycle-provisional-v1"
        or not hasattr(native, "GuardianLifecycleBatch")
    ):
        raise ProvisionalRuleUnavailableError("guardian lifecycle native identity differs")
    batch = native.GuardianLifecycleBatch(
        batch_size,
        player_count,
        slots_per_environment,
        np.asarray(plan.weighted_profiles, dtype=np.int64),
    )
    return ProvisionalGuardianBatch(
        batch=batch,
        metadata=GuardianLifecycleMetadata(
            picker_ruleset_id=plan.native_ruleset_id,
            catalog_sha256=plan.catalog_sha256,
            bible_client_sha256=plan.bible_client_sha256,
            batch_size=batch.batch_size,
            player_count=batch.player_count,
            slots_per_environment=batch.slots_per_environment,
        ),
    )
