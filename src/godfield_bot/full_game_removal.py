"""Pinned removal sundries; native victim sampling remains provisional."""

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

FULL_GAME_REMOVAL_SHA256: Final = "0889134e85ed8c838ffef89cb76502b9957f08d12af51063e3442a5394ba9f84"


class FullGameRemovalPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["0889134e85ed8c838ffef89cb76502b9957f08d12af51063e3442a5394ba9f84"] = (
        FULL_GAME_REMOVAL_SHA256
    )
    profiles: tuple[tuple[int, int, int], ...] = ((205, 1, 3), (206, 2, 2))
    profile_fields: tuple[str, ...] = ("model_id", "kind", "maximum_removed")
    effect_count: Literal[2] = 2
    origin: Literal["sundry-not-weapon-or-miracle"] = "sundry-not-weapon-or-miracle"
    targeting: Literal["living-enemy-only-pinned-client"] = "living-enemy-only-pinned-client"
    broom_pool: Literal["all-actual-held-except-performed-miracles-trade-included-provisional"] = (
        "all-actual-held-except-performed-miracles-trade-included-provisional"
    )
    soap_pool: Literal["actual-performed-miracles-only"] = "actual-performed-miracles-only"
    victim_selection: Literal["native-uniform-without-replacement-provisional"] = (
        "native-uniform-without-replacement-provisional"
    )
    short_pool: Literal["remove-minimum-of-limit-and-eligible-count-provisional"] = (
        "remove-minimum-of-limit-and-eligible-count-provisional"
    )
    victim_receipts: Literal["no-per-victim-replacement-provisional"] = (
        "no-per-victim-replacement-provisional"
    )
    official_sampling_and_timing_verified: Literal[False] = False
    official_soap_event_observed: Literal[False] = False
    official_broom_trade_eligibility_verified: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameRemovalPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            digest != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "kind", "maximum_removed")
        ):
            raise ValueError("full-game removal profiles differ from pinned sources")
        return self


def build_full_game_removal_plan(
    catalog: ApiCatalogSnapshot,
    bible: BibleSnapshot,
) -> FullGameRemovalPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    # Includes the exact pinned help restriction on performed miracles.
    build_dream_inventory_plan(catalog, bible)
    group = bible.catalog.get("sundries")
    for model, asset, name, ability, description in (
        (205, "nocturnal-broom", "Nocturnal Broom", "removeItems", ("Sweep away", "3 artifacts")),
        (
            206,
            "goddess-s-soap",
            "Goddess's Soap",
            "removeUsedMiracles",
            ("Wash away 2", "performed miracles"),
        ),
    ):
        item = next((row for row in catalog.items if row.model_id == model), None)
        reference = (
            next((row for row in group.items if row.asset == asset), None) if group else None
        )
        if (
            item is None
            or dict(item.raw)
            != {
                "imageName": asset,
                "category": "sundries",
                "ability": ability,
                "price": 10,
                "giftRate": 1,
                "name": name,
            }
            or reference is None
            or reference.detail != (name, *description, "$10", "Gift Rate: 1/500")
            or reference.element_image_paths != ()
            or reference.image_path != f"/images/items/sundries/{asset}.webp"
        ):
            raise ValueError("Broom/Soap API and Bible removal contract differs")
    return FullGameRemovalPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
