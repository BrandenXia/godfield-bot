"""Pinned passive ownership effects for the separate native game loop."""

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

FULL_GAME_PASSIVE_SHA256: Final = "108e08cd030d7b3bbde6f6ec4b1bce640aef17ee2a1bc7086c6fe5623b1e70ba"


class FullGamePassivePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["108e08cd030d7b3bbde6f6ec4b1bce640aef17ee2a1bc7086c6fe5623b1e70ba"] = (
        FULL_GAME_PASSIVE_SHA256
    )
    profiles: tuple[tuple[int, int], ...] = ((208, 10),)
    profile_fields: tuple[str, ...] = ("model_id", "revive_hp")
    effect_count: Literal[1] = 1
    behavior: Literal["passive-owned-real-item-on-positive-to-zero-hp-edge-provisional"] = (
        "passive-owned-real-item-on-positive-to-zero-hp-edge-provisional"
    )
    official_timing_verified: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGamePassivePlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            digest != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "revive_hp")
        ):
            raise ValueError("full-game passive profiles differ from pinned sources")
        return self


def build_full_game_passive_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGamePassivePlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    sun = next((item for item in catalog.items if item.model_id == 208), None)
    sundries = bible.catalog.get("sundries")
    reference = (
        next((row for row in sundries.items if row.asset == "sun-amulet"), None)
        if sundries
        else None
    )
    expected = {
        "imageName": "sun-amulet",
        "category": "sundries",
        "ability": "revive",
        "abilityValue": 10,
        "price": 10,
        "giftRate": 1,
        "name": "Sun Amulet",
    }
    if (
        sun is None
        or dict(sun.raw) != expected
        or reference is None
        or reference.detail
        != ("Sun Amulet", "HP+10 when the", "HP becomes 0", "$10", "Gift Rate: 1/500")
        or reference.element_image_paths != ()
        or reference.image_path != "/images/items/sundries/sun-amulet.webp"
    ):
        raise ValueError("Sun Amulet API and Bible passive contract differs")
    return FullGamePassivePlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
