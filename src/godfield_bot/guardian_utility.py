"""Isolated, source-pinned inventory HP/MP utility extension for guardian turns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_batch import _guardian_card_profiles, _guardian_effect_profiles
from godfield_bot.provisional_rules import (
    ProvisionalRuleUnavailableError,
    build_provisional_guardian_plan,
)
from godfield_bot.reference import (
    plain_hp_utility_sundries,
    plain_mp_utility_sundries,
    verified_hp_utility_miracle_cards,
)

if TYPE_CHECKING:
    from godfield_sim import GuardianUtilityTurnBatch

UTILITY_PROFILE_SHA256: Final = "aea15c13fcb187047bbe3548d37de7994e98b562259ecf4db869d74b3c70b29d"
UTILITY_RULESET_ID: Final = "round-robin-inventory-utility-guardian-turns-provisional-v1"


class GuardianUtilityPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    profile_sha256: Literal["aea15c13fcb187047bbe3548d37de7994e98b562259ecf4db869d74b3c70b29d"] = (
        UTILITY_PROFILE_SHA256
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profiles: tuple[tuple[int, int, int, int, int], ...]
    profile_fields: tuple[str, ...] = ("model_id", "resource_code", "gain", "reusable", "mp_cost")
    supported_models: Literal[8] = 8
    resource_codes: tuple[str, ...] = ("hp", "mp")
    targeting: Literal["immediate-self-only-provisional"] = "immediate-self-only-provisional"
    limits: Literal["living-owner-below-100-affordable-before-use"] = (
        "living-owner-below-100-affordable-before-use"
    )
    consumption: Literal["consume-sundry-retain-miracle-spend-exact-mp"] = (
        "consume-sundry-retain-miracle-spend-exact-mp"
    )
    scheduling: Literal["one-utility-completes-one-turn-no-defense-window"] = (
        "one-utility-completes-one-turn-no-defense-window"
    )
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profile(self) -> GuardianUtilityPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or len(self.profiles) != self.supported_models
            or digest != self.profile_sha256
        ):
            raise ValueError("guardian inventory utility requires the pinned eight-card profile")
        return self


def build_guardian_utility_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> GuardianUtilityPlan:
    """Amounts/costs agree in both sources; target/timing remain provisional."""
    hp = plain_hp_utility_sundries(bible)
    mp = plain_mp_utility_sundries(bible)
    miracles = verified_hp_utility_miracle_cards(bible)
    if len(hp) != 4 or len(mp) != 3 or len(miracles) != 1:
        raise ValueError("pinned HP/MP utility Bible subset is incomplete")
    profiles = []
    for item in catalog.items:
        asset = item.raw.get("imageName")
        if not isinstance(asset, str) or (
            asset not in hp and asset not in mp and asset not in miracles
        ):
            continue
        resource = 1 if asset in mp else 0
        reusable = 1 if asset in miracles else 0
        if reusable:
            gain, cost = miracles[asset]
        else:
            gain, cost = (mp if resource else hp)[asset], 0
        if (
            item.raw.get("category") != ("miracles" if reusable else "sundries")
            or item.raw.get("ability") != ("boostMP" if resource else "boostHP")
            or type(item.raw.get("abilityValue")) is not int
            or item.raw.get("abilityValue") != gain
            or type(item.raw.get("cost", 0)) is not int
            or item.raw.get("cost", 0) != cost
            or item.raw.get("element") is not None
            or item.raw.get("atk") is not None
            or item.raw.get("def") is not None
        ):
            raise ValueError("pinned HP/MP utility differs between sources")
        profiles.append((item.model_id, resource, gain, reusable, cost))
    return GuardianUtilityPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        profiles=tuple(profiles),
    )


class GuardianUtilityTurnMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["caller-driven-inventory-utility-guardian-turns-v1"] = (
        "caller-driven-inventory-utility-guardian-turns-v1"
    )
    kernel_schema_version: Literal[1] = 1
    observation_schema_version: Literal[1] = 1
    actor_hand_schema_version: Literal[1] = 1
    ruleset_id: Literal["round-robin-inventory-utility-guardian-turns-provisional-v1"] = (
        UTILITY_RULESET_ID
    )
    base_turn_ruleset_id: Literal["round-robin-card-guardian-resource-turns-provisional-v2"] = (
        "round-robin-card-guardian-resource-turns-provisional-v2"
    )
    utility_plan: GuardianUtilityPlan
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
    armor_model_ids: tuple[int, ...]
    defense_miracle_model_ids: tuple[int, ...]
    attack_weapon_model_ids: tuple[int, ...]
    attack_miracle_model_ids: tuple[int, ...]
    supported_effect_model_ids: tuple[int, ...]
    total_inventory_models: Literal[102] = 102
    actor_hand_fields: tuple[str, ...] = (
        "instance_id",
        "model_id",
        "selected",
        "role",
        "attack",
        "defense",
        "element",
        "mp_cost",
        "reusable",
        "hp_gain",
        "mp_gain",
    )
    hand_roles: tuple[str, ...] = (
        "empty",
        "armor",
        "weapon",
        "attack-miracle",
        "wall",
        "turbulence",
        "hp-utility",
        "mp-utility",
    )
    utility_attack_origin_code: Literal[3] = 3
    acquisition_policy: Literal["caller-dealt-cards-no-redraw"] = "caller-dealt-cards-no-redraw"
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @property
    def catalog_sha256(self) -> str:
        return self.utility_plan.catalog_sha256

    @property
    def bible_client_sha256(self) -> str:
        return self.utility_plan.bible_client_sha256


@dataclass(frozen=True)
class ProvisionalGuardianUtilityTurnBatch:
    batch: GuardianUtilityTurnBatch
    metadata: GuardianUtilityTurnMetadata


def _validate_utility_native_identity(native: ModuleType) -> None:
    if (
        getattr(native, "GUARDIAN_UTILITY_TURN_KERNEL_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_UTILITY_TURN_OBSERVATION_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_UTILITY_ACTOR_HAND_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_UTILITY_TURN_RULESET_ID", None) != UTILITY_RULESET_ID
        or getattr(native, "GUARDIAN_TURN_KERNEL_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_TURN_OBSERVATION_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_TURN_RULESET_ID", None)
        != "round-robin-card-guardian-resource-turns-provisional-v2"
        or getattr(native, "GUARDIAN_TURN_MAX_DEFENSE_ACTIONS", None) != 64
        or getattr(native, "GUARDIAN_COMBAT_KERNEL_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_COMBAT_OBSERVATION_SCHEMA_VERSION", None) != 2
        or getattr(native, "GUARDIAN_COMBAT_RULESET_ID", None)
        != "caller-driven-guardian-resource-curse-combat-provisional-v2"
        or not hasattr(native, "GuardianUtilityTurnBatch")
    ):
        raise ProvisionalRuleUnavailableError("guardian inventory utility native identity differs")


def create_provisional_guardian_utility_turn_batch(
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
) -> ProvisionalGuardianUtilityTurnBatch:
    """New native contract; never widen old arenas or silently migrate their models."""
    catalog = read_api_catalog_snapshot(catalog_path)
    bible = BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8"))
    guardian_plan = build_provisional_guardian_plan(catalog, bible)
    utilities = build_guardian_utility_plan(catalog, bible)
    effects = _guardian_effect_profiles(catalog, guardian_plan)
    defenses, attacks = _guardian_card_profiles(catalog, bible)
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "guardian inventory utility batch requires the native simulation extra"
        ) from None
    _validate_utility_native_identity(native)
    batch = native.GuardianUtilityTurnBatch(
        batch_size,
        player_count,
        slots_per_environment,
        np.asarray(guardian_plan.weighted_profiles, dtype=np.int64),
        np.asarray(effects, dtype=np.int64),
        np.asarray(defenses, dtype=np.int64),
        np.asarray(attacks, dtype=np.int64),
        np.asarray(utilities.profiles, dtype=np.int64),
        hand_slots,
        max_turns,
        initial_hp,
        initial_mp,
        initial_cp,
    )
    return ProvisionalGuardianUtilityTurnBatch(
        batch=batch,
        metadata=GuardianUtilityTurnMetadata(
            utility_plan=utilities,
            batch_size=batch_size,
            player_count=player_count,
            slots_per_environment=slots_per_environment,
            hand_slots=hand_slots,
            max_turns=max_turns,
            initial_hp=initial_hp,
            initial_mp=initial_mp,
            initial_cp=initial_cp,
            defense_model_ids=tuple(row[0] for row in defenses),
            armor_model_ids=tuple(row[0] for row in defenses if row[3] == 0),
            defense_miracle_model_ids=tuple(row[0] for row in defenses if row[3] != 0),
            attack_weapon_model_ids=tuple(row[0] for row in attacks if row[3] == 0),
            attack_miracle_model_ids=tuple(row[0] for row in attacks if row[3] == 1),
            supported_effect_model_ids=tuple(row[0] for row in effects),
        ),
    )
