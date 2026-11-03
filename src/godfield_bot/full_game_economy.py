"""Pinned CP utility and shared wallet contract for the separate game engine."""

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
from godfield_bot.reference import verified_cp_utility_miracle_cards

FULL_GAME_ECONOMY_SHA256: Final = "efc35968f55a511a7c573d015572addddeb3a659f923f82179d1c98212de1918"


class FullGameEconomyPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["efc35968f55a511a7c573d015572addddeb3a659f923f82179d1c98212de1918"] = (
        FULL_GAME_ECONOMY_SHA256
    )
    profiles: tuple[tuple[int, int, int, int], ...] = ((236, 5, 10, 5),)
    profile_fields: tuple[str, ...] = ("model_id", "effect", "value", "mp_cost")
    effect_count: Literal[1] = 1
    payment: Literal["shared-cp-then-mp-then-hp-source-pinned-arithmetic"] = (
        "shared-cp-then-mp-then-hp-source-pinned-arithmetic"
    )
    credit: Literal["shared-credit-requested-amount-up-to-local-configured-cap-provisional"] = (
        "shared-credit-requested-amount-up-to-local-configured-cap-provisional"
    )
    utility_target: Literal["immediate-living-owner-no-defense-window-provisional"] = (
        "immediate-living-owner-no-defense-window-provisional"
    )
    utility_limits: Literal["displayed-cp-below100-mp-affordable-before-use-provisional"] = (
        "displayed-cp-below100-mp-affordable-before-use-provisional"
    )
    utility_retention: Literal["spend-exact-mp-mark-used-and-move-miracle-to-tail"] = (
        "spend-exact-mp-mark-used-and-move-miracle-to-tail"
    )
    timing: Literal["credit-before-original-owner-tick-and-deferred-gifts-provisional"] = (
        "credit-before-original-owner-tick-and-deferred-gifts-provisional"
    )
    trading_implemented: Literal[False] = False
    official_credit_cap_and_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameEconomyPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "effect", "value", "mp_cost")
            or digest != self.profile_sha256
            or len(self.profiles) != self.effect_count
        ):
            raise ValueError("full-game economy profile differs from pinned sources")
        return self


def build_full_game_economy_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameEconomyPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    treasure = next((item for item in catalog.items if item.model_id == 236), None)
    miracles = bible.catalog.get("miracles")
    reference = (
        next((row for row in miracles.items if row.asset == "treasure"), None) if miracles else None
    )
    if (
        treasure is None
        or dict(treasure.raw)
        != {
            "imageName": "treasure",
            "category": "miracles",
            "guardian": "venus",
            "ability": "boostCP",
            "abilityValue": 10,
            "cost": 5,
            "giftRate": 1,
            "name": "<Treasure>",
        }
        or verified_cp_utility_miracle_cards(bible) != {"treasure": (10, 5)}
        or reference is None
        or reference.detail != ("<Treasure>", "$+10", "Cost", "5MP", "Gift Rate: 1/500")
        or reference.image_path != "/images/items/miracles/treasure.webp"
        or reference.element_image_paths != ()
    ):
        raise ValueError("Treasure API and Bible resource contract differs")
    return FullGameEconomyPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
