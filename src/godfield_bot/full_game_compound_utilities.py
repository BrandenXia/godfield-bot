"""Source-pinned compound utilities; probability and joined timing are provisional."""

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
from godfield_bot.reference import verified_heaven_herb_cards, verified_stochastic_hp_sundries

FULL_GAME_COMPOUND_UTILITY_SHA256: Final = (
    "144effaeeaaf78e5c8d60b5f6fcef04ce272ec7b6bf6c89a5a9f3f32817ee0f7"
)


class FullGameCompoundUtilityPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["144effaeeaaf78e5c8d60b5f6fcef04ce272ec7b6bf6c89a5a9f3f32817ee0f7"] = (
        FULL_GAME_COMPOUND_UTILITY_SHA256
    )
    profiles: tuple[tuple[int, int, int, int], ...] = ((198, 6, 20, 0), (202, 7, 10, 0))
    profile_fields: tuple[str, ...] = ("model_id", "effect", "value", "mp_cost")
    effect_count: Literal[2] = 2
    effect_codes: tuple[str, ...] = ("mp-and-heaven=6", "hp-or-self-damage=7")
    herb_illness_stage: Literal[4] = 4
    tear_heal_probability_percent: Literal[50] = 50
    tear_sampling: Literal["dedicated-staged-native-splitmix-uniform-binary-provisional"] = (
        "dedicated-staged-native-splitmix-uniform-binary-provisional"
    )
    herb_order: Literal["consume-gain-mp-inflict-heaven-revive-owner-tick-gifts-provisional"] = (
        "consume-gain-mp-inflict-heaven-revive-owner-tick-gifts-provisional"
    )
    tear_order: Literal["consume-self-heal-or-damage-revive-owner-tick-gifts-provisional"] = (
        "consume-self-heal-or-damage-revive-owner-tick-gifts-provisional"
    )
    resource_cap: Literal["metadata-selected-client99-or-explicit-legacy100"] = (
        "metadata-selected-client99-or-explicit-legacy100"
    )
    probability_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameCompoundUtilityPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            digest != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "effect", "value", "mp_cost")
            or self.effect_codes != ("mp-and-heaven=6", "hp-or-self-damage=7")
        ):
            raise ValueError("compound utility profiles differ from pinned sources")
        return self


def build_full_game_compound_utility_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameCompoundUtilityPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    specs = (
        (
            198,
            "heaven-herb",
            "Heaven Herb",
            "boostMPAndAddCurse",
            20,
            20,
            1,
            ("Heaven Herb", "MP+20", "Heaven", "$20", "Gift Rate: 1/500"),
        ),
        (
            202,
            "thump-thump-tear",
            "Thump-thump Tear",
            "boostHPOrDealDamage",
            10,
            1,
            2,
            ("Thump-thump Tear", "HP+10", "or 10 damage", "$1", "Gift Rate: 2/500"),
        ),
    )
    items = {item.model_id: item for item in catalog.items}
    sundries = bible.catalog.get("sundries")
    for model, asset, name, ability, value, price, gift, detail in specs:
        expected = {
            "imageName": asset,
            "category": "sundries",
            "ability": ability,
            "abilityValue": value,
            "price": price,
            "giftRate": gift,
            "name": name,
        }
        if model == 198:
            expected["curse"] = "heaven"
        reference = (
            next((r for r in sundries.items if r.asset == asset), None) if sundries else None
        )
        if (
            model not in items
            or dict(items[model].raw) != expected
            or reference is None
            or reference.detail != detail
            or reference.image_path != f"/images/items/sundries/{asset}.webp"
            or reference.element_image_paths != ()
        ):
            raise ValueError("compound utility API and Bible contracts differ")
    if verified_heaven_herb_cards(bible) != {"heaven-herb": 20} or verified_stochastic_hp_sundries(
        bible
    ) != {"thump-thump-tear": (10, 10)}:
        raise ValueError("compound utility verified parser contracts differ")
    return FullGameCompoundUtilityPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
