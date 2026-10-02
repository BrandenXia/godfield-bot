"""Pinned attacks, ordered additions and dual-role ordinary defenses."""

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
from godfield_bot.elements import COMBAT_ELEMENT_IDS
from godfield_bot.guardian_batch import _guardian_card_profiles
from godfield_bot.reference import plain_attack_booster_cards

FULL_GAME_COMBAT_SHA256: Final = "0848b37812c513cc42839b549c0c46ab37195599417a36f694a87d554b954565"


class FullGameCombatPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["0848b37812c513cc42839b549c0c46ab37195599417a36f694a87d554b954565"] = (
        FULL_GAME_COMBAT_SHA256
    )
    attack_profiles: tuple[tuple[int, int, int, int, int], ...]
    armor_profiles: tuple[tuple[int, int, int, int, int], ...]
    boost_profiles: tuple[tuple[int, int, int, int, int, int], ...]
    attack_fields: tuple[str, ...] = ("model_id", "attack", "element", "origin", "mp_cost")
    armor_fields: tuple[str, ...] = ("model_id", "defense", "element", "kind", "mp_cost")
    boost_fields: tuple[str, ...] = (
        "model_id",
        "attack",
        "element",
        "mp_cost",
        "composition_kind",
        "can_lead",
    )
    ordinary_weapon_count: Literal[39] = 39
    attack_miracle_count: Literal[6] = 6
    ordinary_armor_count: Literal[51] = 51
    additive_weapon_count: Literal[19] = 19
    additive_armor_count: Literal[4] = 4
    additive_sundry_count: Literal[1] = 1
    additive_miracle_count: Literal[3] = 3
    combat_effect_count: Literal[119] = 119
    composition_kinds: tuple[str, ...] = ("add", "set-element-and-add", "double-and-mix-element")
    composition: Literal["ordered-fixed-weapon-additions-or-standalone-positive-weapon-miracle"] = (
        "ordered-fixed-weapon-additions-or-standalone-positive-weapon-miracle"
    )
    excluded_additive_models: tuple[int, ...] = (34, 56, 232)
    exclusion_reason: Literal["unimplemented-bounce-block-defense-and-area-attack"] = (
        "unimplemented-bounce-block-defense-and-area-attack"
    )
    darkness: Literal["positive-post-defense-damage-sets-target-hp-zero"] = (
        "positive-post-defense-damage-sets-target-hp-zero"
    )
    timing_and_hidden_resolution_verified: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameCombatPlan:
        digest = hashlib.sha256(
            json.dumps(
                (self.attack_profiles, self.armor_profiles, self.boost_profiles),
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or digest != self.profile_sha256
            or self.attack_fields != ("model_id", "attack", "element", "origin", "mp_cost")
            or self.armor_fields != ("model_id", "defense", "element", "kind", "mp_cost")
            or self.boost_fields
            != ("model_id", "attack", "element", "mp_cost", "composition_kind", "can_lead")
            or self.composition_kinds != ("add", "set-element-and-add", "double-and-mix-element")
            or self.excluded_additive_models != (34, 56, 232)
        ):
            raise ValueError("full-game ordinary combat profiles differ from pinned sources")
        return self


def build_full_game_combat_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameCombatPlan:
    # Reuse exact API/Bible cross-checks, not the guardian scheduler or its state.
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    if (
        catalog.content_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
        or bible.client.sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
    ):
        raise ValueError("full-game composition requires pinned catalog and Bible sources")
    defenses, attacks = _guardian_card_profiles(catalog, bible)
    boosts = []
    plain = plain_attack_booster_cards(bible)
    if len(plain) != 17:
        raise ValueError("pinned ordinary additive weapons are incomplete")
    by_reference = {
        (category, row.asset): row
        for category, group in bible.catalog.items()
        for row in group.items
    }
    for item in catalog.items:
        raw = item.raw
        if raw.get("isPlusAtk") is not True or item.model_id in (34, 56, 232):
            continue
        category, asset = raw.get("category"), raw.get("imageName")
        if not isinstance(category, str) or not isinstance(asset, str):
            raise ValueError("additive identity is absent")
        reference = by_reference.get((category, asset))
        attack, cost = raw.get("atk", 0), raw.get("cost", 0)
        element = raw.get("element", "non-element")
        ability = raw.get("ability")
        kind = {None: 0, "setElement": 1, "doubleAtk": 2}.get(ability)
        if (
            reference is None
            or kind is None
            or type(attack) is not int
            or type(cost) is not int
            or element not in COMBAT_ELEMENT_IDS
            or raw.get("hitRate", 100) != 100
        ):
            raise ValueError("pinned additive fields differ")
        effects = []
        if category == "armor":
            defense = raw.get("def")
            if item.model_id not in (124, 136, 150, 162) or type(defense) is not int:
                raise ValueError("pinned dual-role Ogre armor differs")
            effects.append(f"DEF{defense}")
            defenses.append((item.model_id, defense, 0, 0, 0))
        if attack:
            effects.append(f"+ATK{attack}")
        if kind == 1:
            if item.model_id not in (66, 83):
                raise ValueError("pinned element-setting wand differs")
            effects.append(f"Set {element.title()} element")
        elif kind == 2:
            if item.model_id != 231:
                raise ValueError("pinned doubling miracle differs")
            effects.append("Double the ATK")
        if category == "miracles":
            effects += ["Cost", f"{cost}MP"]
        else:
            effects.append(f"${raw.get('price')}")
        effects.append(f"Gift Rate: {raw.get('giftRate')}/500")
        name = raw.get("name")
        if (
            reference.detail != (name, *effects)
            or reference.element_image_paths
            != (() if element == "non-element" else (f"/images/elements/{element}.webp",))
            or (asset in plain and plain[asset] != (attack, element))
        ):
            raise ValueError("additive API and Bible values/descriptions differ")
        boosts.append(
            (
                item.model_id,
                attack,
                COMBAT_ELEMENT_IDS[element],
                cost,
                kind,
                int(category == "weapons" or (category == "miracles" and attack > 0)),
            )
        )
    return FullGameCombatPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        attack_profiles=tuple(sorted(attacks)),
        armor_profiles=tuple(sorted(row for row in defenses if row[3] == 0)),
        boost_profiles=tuple(boosts),
    )
