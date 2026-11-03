"""Pinned adjacent-miracle cost reducers for the separate full-game engine."""

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

FULL_GAME_COST_SHA256: Final = "d880c010d37efd2d2d3d81d1e4830286a236dfdf40c417526b527f867544d2a0"


class FullGameCostPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["d880c010d37efd2d2d3d81d1e4830286a236dfdf40c417526b527f867544d2a0"] = (
        FULL_GAME_COST_SHA256
    )
    profiles: tuple[tuple[int, int, int, int], ...] = (
        (46, 1, 12, 0),
        (143, 2, 0, 6),
        (163, 2, 0, 9),
        (173, 2, 0, 12),
        (204, 3, 0, 0),
    )
    profile_fields: tuple[str, ...] = (
        "model_id",
        "category",
        "standalone_attack",
        "standalone_defense",
    )
    effect_count: Literal[5] = 5
    waiver: Literal["immediately-preceding-miracle-only-entire-cost-source-pinned"] = (
        "immediately-preceding-miracle-only-entire-cost-source-pinned"
    )
    attachment: Literal["attack-utility-and-defense-ordered-follow-miracle-source-pinned"] = (
        "attack-utility-and-defense-ordered-follow-miracle-source-pinned"
    )
    attachment_stats: Literal["no-attached-atk-or-attack-element-special-response-unchanged"] = (
        "no-attached-atk-or-attack-element-special-response-unchanged"
    )
    scheduling: Literal["reserve-select-confirm-before-payment-provisional"] = (
        "reserve-select-confirm-before-payment-provisional"
    )
    official_compound_timing_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profile(self) -> FullGameCostPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            digest != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields
            != ("model_id", "category", "standalone_attack", "standalone_defense")
        ):
            raise ValueError("full-game cost reducer profiles differ from pinned sources")
        return self


def build_full_game_cost_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameCostPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    specs = (
        (46, "spiritual-staff", "Spiritual Staff", "weapons", "ATK12", 20, 1),
        (143, "spiritual-socks", "Spiritual Socks", "armor", "DEF6", 20, 1),
        (163, "spiritual-hood", "Spiritual Hood", "armor", "DEF9", 20, 1),
        (173, "spiritual-sash", "Spiritual Sash", "armor", "DEF12", 20, 1),
        (204, "spiritual-doll", "Spiritual Doll", "sundries", "", 5, 2),
    )
    items = {item.model_id: item for item in catalog.items}
    for model, asset, name, category, statistic, price, weight in specs:
        group = bible.catalog.get(category)
        reference = (
            next((row for row in group.items if row.asset == asset), None) if group else None
        )
        expected = {
            "imageName": asset,
            "category": category,
            "ability": "cutCost",
            "price": price,
            "giftRate": weight,
            "name": name,
        }
        if statistic:
            expected["atk" if category == "weapons" else "def"] = int(statistic[3:])
        details = (
            name,
            *((statistic,) if statistic else ()),
            "Do a miracle w/o cost",
            f"${price}",
            f"Gift Rate: {weight}/500",
        )
        if (
            model not in items
            or dict(items[model].raw) != expected
            or reference is None
            or reference.detail != details
            or reference.element_image_paths != ()
            or reference.image_path != f"/images/items/{category}/{asset}.webp"
        ):
            raise ValueError("cost reducer API and Bible contracts differ")
    return FullGameCostPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
