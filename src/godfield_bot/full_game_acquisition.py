"""Pinned complete held-card gift distribution; scheduling remains provisional."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.dream_inventory import build_dream_inventory_plan

FULL_GAME_GIFT_SHA256: Final = "70905153bedfb92f216afc791132e0bc190f457245e59e4a563256297551b182"


class FullGameAcquisitionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["70905153bedfb92f216afc791132e0bc190f457245e59e4a563256297551b182"] = (
        FULL_GAME_GIFT_SHA256
    )
    model_weights: tuple[
        tuple[
            Annotated[int, Field(ge=1, le=2**53 - 1, strict=True)],
            Annotated[int, Field(ge=1, le=500, strict=True)],
        ],
        ...,
    ]
    giftable_models: Literal[237] = 237
    total_weight: Literal[500] = 500
    source_denominator: Literal[500] = 500
    distribution: Literal["all-held-models-complete-catalog-relative-gift-weights"] = (
        "all-held-models-complete-catalog-relative-gift-weights"
    )
    excluded_virtual_controls: tuple[int, int] = (1, 2)
    excluded_event_models: Literal[57] = 57
    initial_cards: Literal[9] = 9
    initial_deal: Literal["nine-independent-weighted-gifts-per-living-seat-provisional"] = (
        "nine-independent-weighted-gifts-per-living-seat-provisional"
    )
    replacement_quantity: Literal["one-per-used-card-including-retained-miracle-provisional"] = (
        "one-per-used-card-including-retained-miracle-provisional"
    )
    replacement_timing: Literal["completed-turn-living-owners-after-terminal-and-limit-checks"] = (
        "completed-turn-living-owners-after-terminal-and-limit-checks"
    )
    prayer: Literal["one-gift-no-nonused-displayed-weapon-provisional"] = (
        "one-gift-no-nonused-displayed-weapon-provisional"
    )
    instance_ids: Literal["native-monotonic-per-epoch-not-official-id-reuse"] = (
        "native-monotonic-per-epoch-not-official-id-reuse"
    )
    all_gifted_effects_implemented: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_weights(self) -> FullGameAcquisitionPlan:
        digest = hashlib.sha256(
            json.dumps(self.model_weights, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.excluded_virtual_controls != (1, 2)
            or len(self.model_weights) != 237
            or sum(weight for _, weight in self.model_weights) != 500
            or digest != self.profile_sha256
        ):
            raise ValueError("full-game acquisition requires all pinned held gift weights")
        return self


def build_full_game_acquisition_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameAcquisitionPlan:
    inventory = build_dream_inventory_plan(catalog, bible)
    held = {row[0] for row in inventory.profiles}
    records = {
        (category, row.asset): row
        for category, group in bible.catalog.items()
        for row in group.items
    }
    weights = []
    for item in catalog.items:
        if item.model_id not in held:
            continue
        weight = item.raw.get("giftRate")
        if type(weight) is not int or not 1 <= weight <= 500:
            raise ValueError("held-card gift rate is absent or out of bounds")
        if item.model_id in (3, 4, 5):
            expected = {3: "exchange", 4: "sell", 5: "buy"}[item.model_id]
            if (
                item.raw.get("category") != "trade"
                or item.raw.get("imageName") != expected
                or item.raw.get("ability") != expected
                or item.raw.get("price") != 5
                or weight != 20
            ):
                raise ValueError("pinned held trade-card identities or gift rates differ")
        else:
            category = item.raw.get("category")
            asset = item.raw.get("imageName")
            if not isinstance(category, str) or not isinstance(asset, str):
                raise ValueError("held-card gift identity is absent")
            reference = records.get((category, asset))
            rates = (
                []
                if reference is None
                else [line for line in reference.detail if line.startswith("Gift Rate:")]
            )
            match = re.fullmatch(r"Gift Rate: ([0-9]+)/500", rates[0]) if len(rates) == 1 else None
            if match is None or int(match[1]) != weight:
                raise ValueError("held-card API and Bible gift rates differ")
        weights.append((item.model_id, weight))
    return FullGameAcquisitionPlan(
        catalog_sha256=inventory.catalog_sha256,
        bible_client_sha256=inventory.bible_client_sha256,
        model_weights=tuple(weights),
    )
