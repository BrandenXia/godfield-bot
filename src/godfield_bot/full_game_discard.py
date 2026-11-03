"""Shared source-pinned Discard/Sacrifice eligibility and provisional replacements."""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.dream_inventory import build_dream_inventory_plan
from godfield_bot.guardian_discard import DISCARD_RESTRICTIONS

FULL_GAME_DISCARD_SHA256: Final = "2df3973944e31c672893fa041ba24e4cc31ed64a146efcf790dfe1e519332b80"
REMOVAL_ABILITY_NOTES: Final = (
    (
        "texts.reference.discardNote",
        "Weapons, Sun Amulet, and Dangerous Mortar can not be discarded.",
    ),
    ("texts.reference.sacrificeNote", "After the Apocalypse, Discard is replaced into Sacrifice."),
    ("texts.abilities.discard", "Discard artifacts<br>(New artifacts not gifted)"),
    ("texts.abilities.sacrifice", "Sacrifice artifacts<br>(New artifacts gifted)"),
)
REMOVAL_NOTES_SHA256: Final = "aea0050ccb9c39ad3bde328857d8ed6c14011e33851e97bb7b660c5750941070"
REMOVAL_TRANSLATION_SHA256: Final = (
    "bb1b433ba6d336765589aec940cca0bac8b7c0bdcee33969c207a17365509188"
)


class FullGameDiscardPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["2df3973944e31c672893fa041ba24e4cc31ed64a146efcf790dfe1e519332b80"] = (
        FULL_GAME_DISCARD_SHA256
    )
    discard_model_ids: tuple[int, ...]
    discardable_models: Literal[128] = 128
    virtual_model_id: Literal[1] = 1
    sacrifice_virtual_model_id: Literal[2] = 2
    current_ability_notes: tuple[tuple[str, str], ...] = REMOVAL_ABILITY_NOTES
    ability_notes_sha256: Literal[
        "aea0050ccb9c39ad3bde328857d8ed6c14011e33851e97bb7b660c5750941070"
    ] = REMOVAL_NOTES_SHA256
    translation_sha256: Literal[
        "bb1b433ba6d336765589aec940cca0bac8b7c0bdcee33969c207a17365509188"
    ] = REMOVAL_TRANSLATION_SHA256
    forbidden_categories: tuple[str, ...] = ("weapons",)
    forbidden_exception_model_ids: tuple[int, int] = (208, 209)
    documented_restrictions: tuple[str, ...] = DISCARD_RESTRICTIONS
    selection: Literal["multiple-own-displayed-slots-toggle-confirm-nonempty-cancel"] = (
        "multiple-own-displayed-slots-toggle-confirm-nonempty-cancel"
    )
    resolution: Literal["actual-eligibility-atomic-remove-stable-survivors-provisional"] = (
        "actual-eligibility-atomic-remove-stable-survivors-provisional"
    )
    performed_miracles: Literal["eligible-used-flag-no-sell-buy-restriction-inferred"] = (
        "eligible-used-flag-no-sell-buy-restriction-inferred"
    )
    costs: Literal["no-price-or-mp-payment-no-performance-or-consumed-use"] = (
        "no-price-or-mp-payment-no-performance-or-consumed-use"
    )
    replacement: Literal["no-discard-victim-receipts-client-hint-timing-provisional"] = (
        "no-discard-victim-receipts-client-hint-timing-provisional"
    )
    scheduling: Literal["one-owner-tick-after-whole-removal-sun-bow-hooks-provisional"] = (
        "one-owner-tick-after-whole-removal-sun-bow-hooks-provisional"
    )
    apocalypse_policy: Literal["same-phase7-control-discard1-before-sacrifice2-after-threshold"] = (
        "same-phase7-control-discard1-before-sacrifice2-after-threshold"
    )
    sacrifice_replacement: Literal[
        "one-complete-pool-gift-per-removed-card-posttick-guardians-before-receipts-provisional"
    ] = "one-complete-pool-gift-per-removed-card-posttick-guardians-before-receipts-provisional"
    sacrifice_custody: Literal[
        "tagged-family5-receipts-own-dream-cap-devil-sun-bow-dead-ended-suppressed-provisional"
    ] = "tagged-family5-receipts-own-dream-cap-devil-sun-bow-dead-ended-suppressed-provisional"
    sacrifice_implemented: Literal[True] = True
    official_sacrifice_cardinality_and_timing_verified: Literal[False] = False
    official_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGameDiscardPlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or len(self.discard_model_ids) != 128
            or hashlib.sha256(
                json.dumps(self.discard_model_ids, separators=(",", ":")).encode()
            ).hexdigest()
            != self.profile_sha256
            or self.forbidden_categories != ("weapons",)
            or self.forbidden_exception_model_ids != (208, 209)
            or self.documented_restrictions != DISCARD_RESTRICTIONS
            or self.current_ability_notes != REMOVAL_ABILITY_NOTES
        ):
            raise ValueError("full-game discard requires pinned complete held eligibility")
        return self


def build_full_game_discard_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameDiscardPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    inventory = build_dream_inventory_plan(catalog, bible)
    by_id = {item.model_id: item.raw for item in catalog.items}
    if (
        bible.reference_sections.get("trade") != DISCARD_RESTRICTIONS
        or by_id.get(1)
        != {"imageName": "discard", "category": "trade", "ability": "discard", "name": "Discard"}
        or by_id.get(2)
        != {
            "imageName": "sacrifice",
            "category": "trade",
            "ability": "sacrifice",
            "name": "Sacrifice",
        }
        or by_id[208].get("imageName") != "sun-amulet"
        or by_id[208].get("ability") != "revive"
        or by_id[209].get("imageName") != "dangerous-mortar"
        or by_id[209].get("ability") != "attractDanger"
    ):
        raise ValueError("full-game discard source restrictions or protected identities differ")
    return FullGameDiscardPlan(
        catalog_sha256=inventory.catalog_sha256,
        bible_client_sha256=inventory.bible_client_sha256,
        discard_model_ids=tuple(
            model
            for model, category in inventory.profiles
            if category != 1 and model not in (208, 209)
        ),
    )
