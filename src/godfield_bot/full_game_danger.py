"""Pinned Pestle/Mortar roles, with explicit provisional multiplayer attraction."""

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
from godfield_bot.reference import verified_random_target_weapon_cards

FULL_GAME_DANGER_SHA256: Final = "ebfd6728c84580fc20ff3729bd39f742e01d4f6b93cdbc9a732bfa788e0540b3"


class FullGameDangerPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["ebfd6728c84580fc20ff3729bd39f742e01d4f6b93cdbc9a732bfa788e0540b3"] = (
        FULL_GAME_DANGER_SHA256
    )
    profiles: tuple[tuple[int, int, int, int], ...] = ((94, 1, 30, 5), (209, 2, 99, 0))
    profile_fields: tuple[str, ...] = ("model_id", "kind", "attack_or_fixed_damage", "element")
    effect_count: Literal[2] = 2
    effect_codes: tuple[str, ...] = ("random-pestle=1", "passive-mortar=2")
    target: Literal["ignore-request-uniform-living-including-owner-exclude-fog-provisional"] = (
        "ignore-request-uniform-living-including-owner-exclude-fog-provisional"
    )
    self_hit: Literal["immediate-composition-provisional-self-no-defense-observed"] = (
        "immediate-composition-provisional-self-no-defense-observed"
    )
    attraction: Literal[
        "actual-living-holders-priority-uniform-owner-first-held-copy-provisional"
    ] = "actual-living-holders-priority-uniform-owner-first-held-copy-provisional"
    mortar_resolution: Literal[
        "consume-one-owned-mortar-fixed99-direct-hp-loss-no-response-provisional"
    ] = "consume-one-owned-mortar-fixed99-direct-hp-loss-no-response-provisional"
    composition: Literal[
        "ordered-weapon-boosts-waivers-source-pinned-general-timing-unverified"
    ] = "ordered-weapon-boosts-waivers-source-pinned-general-timing-unverified"
    attraction_recheck: Literal["initial-cast-only-no-resampling-during-redirects-provisional"] = (
        "initial-cast-only-no-resampling-during-redirects-provisional"
    )
    gifts_and_ticks: Literal["all-uses-deferred-to-one-original-owner-tick-provisional"] = (
        "all-uses-deferred-to-one-original-owner-tick-provisional"
    )
    official_multiplayer_and_attraction_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameDangerPlan:
        if (
            hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "kind", "attack_or_fixed_damage", "element")
            or self.effect_codes != ("random-pestle=1", "passive-mortar=2")
        ):
            raise ValueError("danger family profiles differ from pinned sources")
        return self


def build_full_game_danger_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameDangerPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    specs = (
        (
            94,
            "weapons",
            "dangerous-pestle",
            {
                "imageName": "dangerous-pestle",
                "category": "weapons",
                "element": "light",
                "atk": 30,
                "ability": "danger",
                "price": 5,
                "giftRate": 1,
                "name": "Dangerous Pestle",
            },
            ("Dangerous Pestle", "ATK30", "Attack somebody", "$5", "Gift Rate: 1/500"),
            ("/images/elements/light.webp",),
        ),
        (
            209,
            "sundries",
            "dangerous-mortar",
            {
                "imageName": "dangerous-mortar",
                "category": "sundries",
                "ability": "attractDanger",
                "abilityValue": 99,
                "price": 1,
                "giftRate": 1,
                "name": "Dangerous Mortar",
            },
            ("Dangerous Mortar", "99 damage by a", "Dangerous Pestle", "$1", "Gift Rate: 1/500"),
            (),
        ),
    )
    items = {item.model_id: item for item in catalog.items}
    for model, category, asset, expected, detail, elements in specs:
        group = bible.catalog.get(category)
        reference = next((r for r in group.items if r.asset == asset), None) if group else None
        if (
            model not in items
            or dict(items[model].raw) != expected
            or reference is None
            or reference.detail != detail
            or reference.element_image_paths != elements
            or reference.image_path != f"/images/items/{category}/{asset}.webp"
        ):
            raise ValueError("danger family API and Bible contracts differ")
    if verified_random_target_weapon_cards(bible) != {"dangerous-pestle": (30, "light")}:
        raise ValueError("danger family verified parser contract differs")
    return FullGameDangerPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
