"""Source-restricted discard component; replacement timing remains provisional."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_batch import _guardian_card_profiles, _guardian_effect_profiles
from godfield_bot.guardian_utility import (
    GuardianUtilityTurnMetadata,
    _validate_utility_native_identity,
    build_guardian_utility_plan,
)
from godfield_bot.provisional_rules import (
    ProvisionalRuleUnavailableError,
    build_provisional_guardian_plan,
)

if TYPE_CHECKING:
    from godfield_sim import GuardianDiscardTurnBatch

DISCARD_RULESET_ID: Final = "round-robin-inventory-discard-guardian-turns-provisional-v1"
DISCARD_PROFILE_SHA256: Final = "08f057a83f01bbe4b7a8f8b585f3c00ce6142f0a09165324e04651415701d80f"
DISCARD_RESTRICTIONS: Final = (
    "Weapons, Sun Amulet, and Dangerous Mortar can not be discarded.",
    "After the Apocalypse, Discard is replaced into Sacrifice.",
)


class GuardianDiscardPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["08f057a83f01bbe4b7a8f8b585f3c00ce6142f0a09165324e04651415701d80f"] = (
        DISCARD_PROFILE_SHA256
    )
    discard_model_ids: tuple[int, ...]
    supported_discard_models: Literal[63] = 63
    forbidden_categories: tuple[str, ...] = ("weapons",)
    forbidden_exception_model_ids: tuple[int, int] = (208, 209)
    documented_restrictions: tuple[str, ...] = DISCARD_RESTRICTIONS
    scheduling: Literal["one-self-discard-completes-one-turn-provisional"] = (
        "one-self-discard-completes-one-turn-provisional"
    )
    resource_effects: Literal["none-no-price-payment-or-resource-conversion"] = (
        "none-no-price-payment-or-resource-conversion"
    )
    replacement_policy: Literal["caller-supplied-one-gift-same-slot-provisional"] = (
        "caller-supplied-one-gift-same-slot-provisional"
    )
    apocalypse_policy: Literal["not-modeled-sacrifice-not-implemented"] = (
        "not-modeled-sacrifice-not-implemented"
    )
    miracle_eligibility: Literal[
        "supported-miracles-discardable-provisional-no-used-flag-model"
    ] = "supported-miracles-discardable-provisional-no-used-flag-model"
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned(self) -> GuardianDiscardPlan:
        digest = hashlib.sha256(
            json.dumps(self.discard_model_ids, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or len(self.discard_model_ids) != 63
            or digest != self.profile_sha256
            or self.forbidden_categories != ("weapons",)
            or self.forbidden_exception_model_ids != (208, 209)
            or self.documented_restrictions != DISCARD_RESTRICTIONS
        ):
            raise ValueError("discard requires the pinned profile and documented restrictions")
        return self


def build_guardian_discard_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> GuardianDiscardPlan:
    defenses, attacks = _guardian_card_profiles(catalog, bible)
    utilities = build_guardian_utility_plan(catalog, bible)
    supported = {row[0] for row in defenses + attacks} | {row[0] for row in utilities.profiles}
    if bible.reference_sections.get("trade") != DISCARD_RESTRICTIONS:
        raise ValueError("discard restrictions differ from the pinned Bible")
    by_id = {item.model_id: item for item in catalog.items}
    for model, asset in ((208, "sun-amulet"), (209, "dangerous-mortar")):
        item = by_id.get(model)
        if item is None or item.raw.get("imageName") != asset:
            raise ValueError("discard exception identity differs from the pinned catalog")
    return GuardianDiscardPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        discard_model_ids=tuple(
            item.model_id
            for item in catalog.items
            if item.model_id in supported
            and item.raw.get("category") != "weapons"
            and item.model_id not in (208, 209)
        ),
    )


class GuardianDiscardTurnMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["caller-driven-inventory-discard-guardian-turns-v1"] = (
        "caller-driven-inventory-discard-guardian-turns-v1"
    )
    kernel_schema_version: Literal[1] = 1
    observation_schema_version: Literal[1] = 1
    ruleset_id: Literal["round-robin-inventory-discard-guardian-turns-provisional-v1"] = (
        DISCARD_RULESET_ID
    )
    utility_base: GuardianUtilityTurnMetadata
    discard_plan: GuardianDiscardPlan
    discard_origin_code: Literal[4] = 4
    pending_neural_action_count: Literal[48] = 48
    pending_neural_action_layout: tuple[str, ...] = (
        "0..29:existing-utility-arena-actions-unchanged",
        "30..47:discard-hand-slot-0..17",
    )
    acquisition_policy: Literal["caller-dealt-cards-no-native-redraw"] = (
        "caller-dealt-cards-no-native-redraw"
    )
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def source_and_pending_layout(self) -> GuardianDiscardTurnMetadata:
        base = self.utility_base
        expected = tuple(
            sorted(
                base.defense_model_ids
                + base.attack_miracle_model_ids
                + tuple(row[0] for row in base.utility_plan.profiles)
            )
        )
        if (
            base.catalog_sha256 != self.discard_plan.catalog_sha256
            or base.bible_client_sha256 != self.discard_plan.bible_client_sha256
            or expected != self.discard_plan.discard_model_ids
            or set(base.attack_weapon_model_ids) & set(self.discard_plan.discard_model_ids)
            or self.pending_neural_action_layout
            != (
                "0..29:existing-utility-arena-actions-unchanged",
                "30..47:discard-hand-slot-0..17",
            )
        ):
            raise ValueError("discard metadata source, supported cards, or pending layout differs")
        return self


@dataclass(frozen=True)
class ProvisionalGuardianDiscardTurnBatch:
    batch: GuardianDiscardTurnBatch
    metadata: GuardianDiscardTurnMetadata


def create_provisional_guardian_discard_turn_batch(
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
) -> ProvisionalGuardianDiscardTurnBatch:
    catalog = read_api_catalog_snapshot(catalog_path)
    bible = BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8"))
    guardian_plan = build_provisional_guardian_plan(catalog, bible)
    utilities = build_guardian_utility_plan(catalog, bible)
    discard_plan = build_guardian_discard_plan(catalog, bible)
    effects = _guardian_effect_profiles(catalog, guardian_plan)
    defenses, attacks = _guardian_card_profiles(catalog, bible)
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "discard batch requires the native simulation extra"
        ) from None
    _validate_utility_native_identity(native)
    if (
        getattr(native, "GUARDIAN_DISCARD_TURN_KERNEL_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_DISCARD_TURN_OBSERVATION_SCHEMA_VERSION", None) != 1
        or getattr(native, "GUARDIAN_DISCARD_TURN_RULESET_ID", None) != DISCARD_RULESET_ID
        or not hasattr(native, "GuardianDiscardTurnBatch")
    ):
        raise ProvisionalRuleUnavailableError("guardian discard native identity differs")
    batch = native.GuardianDiscardTurnBatch(
        batch_size,
        player_count,
        slots_per_environment,
        np.asarray(guardian_plan.weighted_profiles, dtype=np.int64),
        np.asarray(effects, dtype=np.int64),
        np.asarray(defenses, dtype=np.int64),
        np.asarray(attacks, dtype=np.int64),
        np.asarray(utilities.profiles, dtype=np.int64),
        np.asarray(discard_plan.discard_model_ids, dtype=np.int64),
        hand_slots,
        max_turns,
        initial_hp,
        initial_mp,
        initial_cp,
    )
    base = GuardianUtilityTurnMetadata(
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
    )
    return ProvisionalGuardianDiscardTurnBatch(
        batch=batch,
        metadata=GuardianDiscardTurnMetadata(utility_base=base, discard_plan=discard_plan),
    )
