"""Catalog-pinned entry point for the provisional native guardian lifecycle batch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import COMBAT_ELEMENT_IDS
from godfield_bot.provisional_rules import (
    ProvisionalRuleUnavailableError,
    build_provisional_guardian_plan,
)

if TYPE_CHECKING:
    from godfield_sim import GuardianCombatBatch, GuardianLifecycleBatch


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


class GuardianCombatMetadata(BaseModel):
    schema_version: Literal[1] = 1
    kernel_schema_version: Literal[1] = 1
    observation_schema_version: Literal[1] = 1
    ruleset_id: Literal["caller-driven-basic-guardian-combat-provisional-v1"] = (
        "caller-driven-basic-guardian-combat-provisional-v1"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(gt=0)
    player_count: int = Field(ge=2, le=9)
    slots_per_environment: int = Field(ge=1, le=64)
    initial_hp: int = Field(ge=1, le=100)
    basic_attack_model_ids: tuple[int, ...]
    unsupported_weighted_model_ids: tuple[int, ...]
    phase_fields: tuple[str, ...] = (
        "phase",
        "model_id",
        "owner",
        "target",
        "resolved_attack",
        "element",
        "last_hp_lost",
    )
    event_and_randomness_policy: Literal["caller-supplied"] = "caller-supplied"
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False


@dataclass(frozen=True)
class ProvisionalGuardianCombatBatch:
    batch: GuardianCombatBatch
    metadata: GuardianCombatMetadata


def create_provisional_guardian_combat_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    slots_per_environment: int = 8,
    initial_hp: int = 40,
) -> ProvisionalGuardianCombatBatch:
    """Configure the 21 catalog attacks with no additional ability."""

    catalog = read_api_catalog_snapshot(catalog_path)
    plan = build_provisional_guardian_plan(
        catalog,
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    weighted = {model for _group, model, _rate in plan.weighted_profiles}
    profiles: list[tuple[int, int, int, int]] = []
    for item in catalog.items:
        if item.model_id not in weighted or item.raw.get("ability") is not None:
            continue
        attack = item.raw.get("atk")
        element = item.raw.get("element", "non-element")
        hit_rate = item.raw.get("hitRate", 100)
        if (
            type(attack) is not int
            or not 1 <= attack <= 65535
            or element not in COMBAT_ELEMENT_IDS
            or type(hit_rate) is not int
            or not 1 <= hit_rate <= 100
        ):
            raise ValueError("pinned basic guardian attack profile differs")
        profiles.append((item.model_id, attack, COMBAT_ELEMENT_IDS[element], hit_rate))
    if len(profiles) != 21:
        raise ValueError("pinned guardian combat catalog must have 21 basic attacks")
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "guardian combat batch requires the native simulation extra"
        ) from None
    if (
        getattr(native, "GUARDIAN_COMBAT_KERNEL_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_COMBAT_OBSERVATION_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_COMBAT_RULESET_ID", None)
        != "caller-driven-basic-guardian-combat-provisional-v1"
        or not hasattr(native, "GuardianCombatBatch")
    ):
        raise ProvisionalRuleUnavailableError("guardian combat native identity differs")
    batch = native.GuardianCombatBatch(
        batch_size,
        player_count,
        slots_per_environment,
        np.asarray(plan.weighted_profiles, dtype=np.int64),
        np.asarray(profiles, dtype=np.int64),
        initial_hp,
    )
    return ProvisionalGuardianCombatBatch(
        batch=batch,
        metadata=GuardianCombatMetadata(
            catalog_sha256=plan.catalog_sha256,
            bible_client_sha256=plan.bible_client_sha256,
            batch_size=batch_size,
            player_count=player_count,
            slots_per_environment=slots_per_environment,
            initial_hp=initial_hp,
            basic_attack_model_ids=tuple(row[0] for row in profiles),
            unsupported_weighted_model_ids=tuple(sorted(weighted - {row[0] for row in profiles})),
        ),
    )


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
