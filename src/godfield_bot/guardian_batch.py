"""Catalog-pinned entry point for the provisional native guardian lifecycle batch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import COMBAT_ELEMENT_IDS
from godfield_bot.provisional_rules import (
    ProvisionalGuardianPlan,
    ProvisionalRuleUnavailableError,
    build_provisional_guardian_plan,
)
from godfield_bot.reference import plain_defense_armor_cards

if TYPE_CHECKING:
    from godfield_sim import GuardianCombatBatch, GuardianLifecycleBatch, GuardianTurnBatch


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
    schema_version: Literal[2] = 2
    kernel_schema_version: Literal[2] = 2
    observation_schema_version: Literal[2] = 2
    ruleset_id: Literal["caller-driven-guardian-resource-curse-combat-provisional-v2"] = (
        "caller-driven-guardian-resource-curse-combat-provisional-v2"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(gt=0)
    player_count: int = Field(ge=2, le=9)
    slots_per_environment: int = Field(ge=1, le=64)
    initial_hp: int = Field(ge=1, le=100)
    initial_mp: int = Field(ge=0, le=100)
    initial_cp: int = Field(ge=0, le=100)
    basic_attack_model_ids: tuple[int, ...]
    supported_effect_model_ids: tuple[int, ...]
    unsupported_weighted_model_ids: tuple[int, ...]
    unsupported_special_model_ids: tuple[int, ...] = (285, 286)
    phase_fields: tuple[str, ...] = (
        "phase",
        "model_id",
        "owner",
        "target",
        "resolved_attack",
        "element",
        "last_hp_lost",
        "effect_code",
        "utility_value",
        "curse_bit",
    )
    resource_fields: tuple[str, ...] = ("hp", "mp", "cp", "curse_mask")
    event_and_randomness_policy: Literal["caller-supplied"] = "caller-supplied"
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False


@dataclass(frozen=True)
class ProvisionalGuardianCombatBatch:
    batch: GuardianCombatBatch
    metadata: GuardianCombatMetadata


def _guardian_effect_profiles(
    catalog: ApiCatalogSnapshot, plan: ProvisionalGuardianPlan
) -> list[tuple[int, int, int, int, int, int, int]]:
    weighted = {model for _group, model, _rate in plan.weighted_profiles}
    effect_ids = {
        None: 0,
        "absorbHP": 1,
        "addCurseOnDamage": 2,
        "addCurse": 3,
        "removeAllCurses": 4,
        "boostHP": 5,
        "boostMP": 6,
        "boostCP": 7,
        "boostCPOfEverybody": 8,
        "boostCPToEnemy": 9,
        "takeCP": 10,
    }
    curse_bits = {"fog": 1, "dream": 2, "flash": 4, "darkcloud": 8}
    profiles: list[tuple[int, int, int, int, int, int, int]] = []
    for item in catalog.items:
        ability = item.raw.get("ability")
        if item.model_id not in weighted or ability not in effect_ids:
            continue
        effect = effect_ids[ability]
        attack = item.raw.get("atk", 0)
        element = item.raw.get("element", "non-element")
        hit_rate = item.raw.get("hitRate", 100)
        utility = item.raw.get("abilityValue", 0)
        curse_name = item.raw.get("curse")
        curse = curse_bits.get(curse_name, 0) if isinstance(curse_name, str) else 0
        if (
            type(attack) is not int
            or not 0 <= attack <= 65535
            or element not in COMBAT_ELEMENT_IDS
            or type(hit_rate) is not int
            or not 1 <= hit_rate <= 100
            or type(utility) is not int
            or not 0 <= utility <= 100
            or ((effect in (2, 3)) != (curse != 0))
        ):
            raise ValueError("pinned guardian effect profile differs")
        profiles.append(
            (item.model_id, attack, COMBAT_ELEMENT_IDS[element], hit_rate, effect, utility, curse)
        )
    if len(profiles) != 39:
        raise ValueError("pinned guardian combat catalog must have 39 supported effects")
    return profiles


def create_provisional_guardian_combat_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    slots_per_environment: int = 8,
    initial_hp: int = 40,
    initial_mp: int = 10,
    initial_cp: int = 0,
) -> ProvisionalGuardianCombatBatch:
    """Configure 39 provisional guardian combat, resource, and curse effects."""

    catalog = read_api_catalog_snapshot(catalog_path)
    plan = build_provisional_guardian_plan(
        catalog,
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    profiles = _guardian_effect_profiles(catalog, plan)
    weighted = {model for _group, model, _rate in plan.weighted_profiles}
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "guardian combat batch requires the native simulation extra"
        ) from None
    if (
        getattr(native, "GUARDIAN_COMBAT_KERNEL_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_COMBAT_OBSERVATION_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_COMBAT_RULESET_ID", None)
        != "caller-driven-guardian-resource-curse-combat-provisional-v2"
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
        initial_mp,
        initial_cp,
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
            initial_mp=initial_mp,
            initial_cp=initial_cp,
            basic_attack_model_ids=tuple(row[0] for row in profiles if row[4] == 0),
            supported_effect_model_ids=tuple(row[0] for row in profiles),
            unsupported_weighted_model_ids=tuple(sorted(weighted - {row[0] for row in profiles})),
        ),
    )


class GuardianTurnMetadata(BaseModel):
    schema_version: Literal[1] = 1
    kernel_schema_version: Literal[1] = 1
    observation_schema_version: Literal[1] = 1
    ruleset_id: Literal["round-robin-guardian-armor-turns-provisional-v1"] = (
        "round-robin-guardian-armor-turns-provisional-v1"
    )
    combat_kernel_schema_version: Literal[2] = 2
    combat_observation_schema_version: Literal[2] = 2
    combat_ruleset_id: Literal["caller-driven-guardian-resource-curse-combat-provisional-v2"] = (
        "caller-driven-guardian-resource-curse-combat-provisional-v2"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(gt=0)
    player_count: int = Field(ge=2, le=9)
    slots_per_environment: int = Field(ge=1, le=64)
    hand_slots: int = Field(ge=1, le=18)
    max_turns: int = Field(ge=1, le=1_000_000_000)
    max_defense_actions: Literal[64] = 64
    initial_hp: int = Field(ge=1, le=100)
    initial_mp: int = Field(ge=0, le=100)
    initial_cp: int = Field(ge=0, le=100)
    defense_model_ids: tuple[int, ...]
    supported_effect_model_ids: tuple[int, ...]
    unsupported_weighted_model_ids: tuple[int, ...] = (264,)
    unsupported_special_model_ids: tuple[int, ...] = (285, 286)
    action_count: int
    forgive_action: int
    confirm_action: int
    turn_fields: tuple[str, ...] = (
        "phase",
        "turn_owner",
        "actor",
        "completed_turns",
        "winner",
        "truncated",
        "selected_defense",
        "defense_actions",
    )
    inventory_fields: tuple[str, ...] = ("instance_id", "model_id", "selected")
    scheduling_policy: Literal["one-caller-selected-effect-or-pass-per-living-player-turn"] = (
        "one-caller-selected-effect-or-pass-per-living-player-turn"
    )
    randomness_policy: Literal["caller-supplied-tickets"] = "caller-supplied-tickets"
    acquisition_policy: Literal["caller-dealt-armor-no-redraw"] = "caller-dealt-armor-no-redraw"
    official_fidelity_verified: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False


@dataclass(frozen=True)
class ProvisionalGuardianTurnBatch:
    batch: GuardianTurnBatch
    metadata: GuardianTurnMetadata


def create_provisional_guardian_turn_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    slots_per_environment: int = 8,
    hand_slots: int = 18,
    max_turns: int = 1000,
    initial_hp: int = 40,
    initial_mp: int = 10,
    initial_cp: int = 0,
) -> ProvisionalGuardianTurnBatch:
    """Compose legal armor choices with explicitly provisional turn scheduling."""

    catalog = read_api_catalog_snapshot(catalog_path)
    bible = BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8"))
    plan = build_provisional_guardian_plan(catalog, bible)
    profiles = _guardian_effect_profiles(catalog, plan)
    armor = plain_defense_armor_cards(bible)
    defenses: list[tuple[int, int, int]] = []
    for item in catalog.items:
        asset = item.raw.get("imageName")
        if not isinstance(asset, str) or asset not in armor:
            continue
        value, element = armor[asset]
        if (
            item.raw.get("category") != "armor"
            or item.raw.get("def") != value
            or item.raw.get("element", "non-element") != element
            or item.raw.get("ability") is not None
        ):
            raise ValueError("pinned guardian defense armor differs between sources")
        defenses.append((item.model_id, value, COMBAT_ELEMENT_IDS[element]))
    if len(defenses) != 47 or len(armor) != 47:
        raise ValueError("pinned guardian defense catalog is incomplete")
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "guardian turn batch requires the native simulation extra"
        ) from None
    if (
        getattr(native, "GUARDIAN_TURN_KERNEL_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_TURN_OBSERVATION_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_TURN_RULESET_ID", None)
        != "round-robin-guardian-armor-turns-provisional-v1"
        or getattr(native, "GUARDIAN_COMBAT_KERNEL_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_COMBAT_OBSERVATION_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_COMBAT_RULESET_ID", None)
        != "caller-driven-guardian-resource-curse-combat-provisional-v2"
        or not hasattr(native, "GuardianTurnBatch")
    ):
        raise ProvisionalRuleUnavailableError("guardian turn native identity differs")
    batch = native.GuardianTurnBatch(
        batch_size,
        player_count,
        slots_per_environment,
        np.asarray(plan.weighted_profiles, dtype=np.int64),
        np.asarray(profiles, dtype=np.int64),
        np.asarray(defenses, dtype=np.int64),
        hand_slots,
        max_turns,
        initial_hp,
        initial_mp,
        initial_cp,
    )
    return ProvisionalGuardianTurnBatch(
        batch=batch,
        metadata=GuardianTurnMetadata(
            catalog_sha256=plan.catalog_sha256,
            bible_client_sha256=plan.bible_client_sha256,
            batch_size=batch_size,
            player_count=player_count,
            slots_per_environment=slots_per_environment,
            hand_slots=hand_slots,
            max_turns=max_turns,
            initial_hp=initial_hp,
            initial_mp=initial_mp,
            initial_cp=initial_cp,
            defense_model_ids=tuple(row[0] for row in defenses),
            supported_effect_model_ids=tuple(row[0] for row in profiles),
            action_count=batch.action_count,
            forgive_action=hand_slots,
            confirm_action=hand_slots + 1,
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
