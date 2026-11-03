"""Pinned Dreaming Hat defense, with explicitly provisional whole-hand redraw."""

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

FULL_GAME_DREAM_DEFENSE_SHA256: Final = (
    "d635aa3250b0d358ede00401a1cadaf1a3c3872bf924425d5d25a35f89a909ff"
)


class FullGameDreamDefensePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["d635aa3250b0d358ede00401a1cadaf1a3c3872bf924425d5d25a35f89a909ff"] = (
        FULL_GAME_DREAM_DEFENSE_SHA256
    )
    profiles: tuple[tuple[int, int, int, int], ...] = ((178, 14, 3, 2),)
    profile_fields: tuple[str, ...] = ("model_id", "defense", "element", "self_curse_mask")
    effect_count: Literal[1] = 1
    defense_kind: Literal[7] = 7
    trigger: Literal["actual-selected-hat-living-after-incoming-effect-and-revival-provisional"] = (
        "actual-selected-hat-living-after-incoming-effect-and-revival-provisional"
    )
    redraw: Literal["replace-all-remaining-held-rows-same-count-fresh-identities-provisional"] = (
        "replace-all-remaining-held-rows-same-count-fresh-identities-provisional"
    )
    redraw_models: Literal["dedicated-native-pinned-held-gift-weights-provisional"] = (
        "dedicated-native-pinned-held-gift-weights-provisional"
    )
    redraw_disguises: Literal["dream-first-fresh-independent50-same-category-provisional"] = (
        "dream-first-fresh-independent50-same-category-provisional"
    )
    performed_miracles: Literal["old-rows-replaced-new-miracles-unused-provisional"] = (
        "old-rows-replaced-new-miracles-unused-provisional"
    )
    duplicate_hats: Literal["one-redraw-per-actual-used-hat-in-click-order-provisional"] = (
        "one-redraw-per-actual-used-hat-in-click-order-provisional"
    )
    gifts: Literal["redraw-not-gifts-hat-use-receipt-deferred-to-family-end-provisional"] = (
        "redraw-not-gifts-hat-use-receipt-deferred-to-family-end-provisional"
    )
    official_redraw_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameDreamDefensePlan:
        if (
            hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "defense", "element", "self_curse_mask")
        ):
            raise ValueError("Dream defense profiles differ from pinned sources")
        return self


def build_full_game_dream_defense_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameDreamDefensePlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    raw = next((item.raw for item in catalog.items if item.model_id == 178), None)
    armor = bible.catalog.get("armor")
    reference = next((r for r in armor.items if r.asset == "dreaming-hat"), None) if armor else None
    if (
        raw
        != {
            "imageName": "dreaming-hat",
            "category": "armor",
            "element": "wood",
            "def": 14,
            "ability": "selfCurseAndRedraw",
            "curse": "dream",
            "price": 15,
            "giftRate": 1,
            "name": "Dreaming Hat",
        }
        or reference is None
        or reference.detail
        != ("Dreaming Hat", "DEF14", "Catch Dream & Redraw", "$15", "Gift Rate: 1/500")
        or reference.image_path != "/images/items/armor/dreaming-hat.webp"
        or reference.element_image_paths != ("/images/elements/wood.webp",)
    ):
        raise ValueError("Dream defense API and Bible contracts differ")
    return FullGameDreamDefensePlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
