"""Pinned Mirage addition with explicitly provisional multi-recipient scheduling."""

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

FULL_GAME_AREA_SHA256: Final = "84016251775afdf821b5097e03d58311423f6df583c8cddc15aad2bee107d8e5"


class FullGameAreaPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["84016251775afdf821b5097e03d58311423f6df583c8cddc15aad2bee107d8e5"] = (
        FULL_GAME_AREA_SHA256
    )
    profiles: tuple[tuple[int, int], ...] = ((232, 5),)
    profile_fields: tuple[str, ...] = ("model_id", "mp_cost")
    effect_count: Literal[1] = 1
    selection: Literal["addition-only-nonchance-weapon-no-atk-or-element-change-source-pinned"] = (
        "addition-only-nonchance-weapon-no-atk-or-element-change-source-pinned"
    )
    cost: Literal["each-selected-copy-adjacent-waiver-before-all-mp-weapon-source-pinned"] = (
        "each-selected-copy-adjacent-waiver-before-all-mp-weapon-source-pinned"
    )
    fog: Literal["attack-every-enemy-excluded-from-fog-retargeting-source-pinned"] = (
        "attack-every-enemy-excluded-from-fog-retargeting-source-pinned"
    )
    recipients: Literal["ascending-other-living-seats-at-cast-skip-later-dead-provisional"] = (
        "ascending-other-living-seats-at-cast-skip-later-dead-provisional"
    )
    duplicates: Literal["boolean-fanout-once-all-copies-cost-and-perform-provisional"] = (
        "boolean-fanout-once-all-copies-cost-and-perform-provisional"
    )
    repetition: Literal["consecutive-strikes-per-recipient-nested-reactions-first-provisional"] = (
        "consecutive-strikes-per-recipient-nested-reactions-first-provisional"
    )
    danger: Literal["per-queued-shot-pestle-reroute-after-nominal-liveness-check-provisional"] = (
        "per-queued-shot-pestle-reroute-after-nominal-liveness-check-provisional"
    )
    target_command: Literal["legacy-phase3-placeholder-ignored-by-actual-area-provisional"] = (
        "legacy-phase3-placeholder-ignored-by-actual-area-provisional"
    )
    official_multiplayer_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGameAreaPlan:
        if (
            hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "mp_cost")
        ):
            raise ValueError("Mirage profiles differ from pinned sources")
        return self


def build_full_game_area_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameAreaPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    raw = next((item.raw for item in catalog.items if item.model_id == 232), None)
    miracles = bible.catalog.get("miracles")
    reference = next((r for r in miracles.items if r.asset == "mirage"), None) if miracles else None
    if (
        raw
        != {
            "imageName": "mirage",
            "category": "miracles",
            "isPlusAtk": True,
            "ability": "attackEveryEnemy",
            "cost": 5,
            "giftRate": 1,
            "name": "<Mirage>",
        }
        or reference is None
        or reference.detail
        != ("<Mirage>", "Attack", "all the enemies", "Cost", "5MP", "Gift Rate: 1/500")
        or reference.image_path != "/images/items/miracles/mirage.webp"
        or reference.element_image_paths != ()
    ):
        raise ValueError("Mirage API and Bible contracts differ")
    return FullGameAreaPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
