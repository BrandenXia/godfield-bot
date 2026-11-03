"""Pinned complex weapon roles; joined compound timing remains provisional."""

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
from godfield_bot.reference import (
    verified_attack_twice_weapon_cards,
    verified_dynamic_mp_weapon_cards,
    verified_same_damage_weapon_cards,
)

FULL_GAME_WEAPON_SHA256: Final = "f74d9d6a875d8dac98b66926fe202c20d558254dcb035879b05605673c1baa4d"


class FullGameWeaponPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["f74d9d6a875d8dac98b66926fe202c20d558254dcb035879b05605673c1baa4d"] = (
        FULL_GAME_WEAPON_SHA256
    )
    profiles: tuple[tuple[int, int, int, int], ...] = ((14, 3, 3, 0), (53, 2, 14, 0), (58, 1, 2, 0))
    profile_fields: tuple[str, ...] = ("model_id", "kind", "value_or_mp_coefficient", "element")
    effect_count: Literal[3] = 3
    effect_codes: tuple[str, ...] = ("dynamic-mp=1", "same-damage=2", "two-strikes=3")
    dynamic_mp: Literal["base-from-mp-after-net-miracle-cost-consume-all-mp-source-pinned"] = (
        "base-from-mp-after-net-miracle-cost-consume-all-mp-source-pinned"
    )
    recoil: Literal[
        "actual-hp-loss-living-final-target-current-source-after-revival-provisional"
    ] = "actual-hp-loss-living-final-target-current-source-after-revival-provisional"
    double_attack: Literal[
        "fresh-defense-original-snapshot-source-target-counters-between-strikes-provisional"
    ] = "fresh-defense-original-snapshot-source-target-counters-between-strikes-provisional"
    gifts_and_ticks: Literal["one-owner-tick-gifts-deferred-until-family-end-provisional"] = (
        "one-owner-tick-gifts-deferred-until-family-end-provisional"
    )
    compound_rules_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameWeaponPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            digest != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields != ("model_id", "kind", "value_or_mp_coefficient", "element")
            or self.effect_codes != ("dynamic-mp=1", "same-damage=2", "two-strikes=3")
        ):
            raise ValueError("full-game complex weapon profiles differ from pinned sources")
        return self


def build_full_game_weapon_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameWeaponPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    specs = (
        (14, "saw-boom-boom", "Saw Boom Boom", "attackTwice", "ATK3", "Attack twice", 3, 10),
        (
            53,
            "evil-broadsword",
            "Evil Broadsword",
            "dealSameDamage",
            "ATK14",
            "Get the same damage",
            14,
            1,
        ),
        (
            58,
            "magical-stick",
            "Magical Stick",
            "atkBy2xMP",
            "ATK{2×MP}",  # noqa: RUF001 -- exact pinned Bible spelling
            "Consume all the MP",
            0,
            10,
        ),
    )
    items = {item.model_id: item for item in catalog.items}
    weapons = bible.catalog.get("weapons")
    for model, asset, name, ability, stat, text, attack, price in specs:
        expected = {
            "imageName": asset,
            "category": "weapons",
            "ability": ability,
            "price": price,
            "giftRate": 1,
            "name": name,
        }
        if attack:
            expected["atk"] = attack
        reference = next((r for r in weapons.items if r.asset == asset), None) if weapons else None
        if (
            model not in items
            or dict(items[model].raw) != expected
            or reference is None
            or reference.detail != (name, stat, text, f"${price}", "Gift Rate: 1/500")
            or reference.image_path != f"/images/items/weapons/{asset}.webp"
            or reference.element_image_paths != ()
        ):
            raise ValueError("complex weapon API and Bible contracts differ")
    if (
        verified_dynamic_mp_weapon_cards(bible) != {"magical-stick": (2, "non-element")}
        or verified_same_damage_weapon_cards(bible) != {"evil-broadsword": (14, "non-element")}
        or verified_attack_twice_weapon_cards(bible) != {"saw-boom-boom": (3, 2, "non-element")}
    ):
        raise ValueError("complex weapon verified parser contracts differ")
    return FullGameWeaponPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
