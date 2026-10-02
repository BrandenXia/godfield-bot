"""Pinned attacks, ordered additions and exclusive special defenses."""

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
from godfield_bot.domain.reference import ArtifactRecord, BibleSnapshot
from godfield_bot.elements import COMBAT_ELEMENT_IDS
from godfield_bot.guardian_batch import _guardian_card_profiles
from godfield_bot.reference import plain_attack_booster_cards

FULL_GAME_COMBAT_SHA256: Final = "3fd5d21227b280d9a53405e0e41b1c9f8f0b37d7a08a39ad4a520f0037de1aff"


class FullGameCombatPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[3] = 3
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["3fd5d21227b280d9a53405e0e41b1c9f8f0b37d7a08a39ad4a520f0037de1aff"] = (
        FULL_GAME_COMBAT_SHA256
    )
    attack_profiles: tuple[tuple[int, int, int, int, int], ...]
    armor_profiles: tuple[tuple[int, int, int, int, int], ...]
    boost_profiles: tuple[tuple[int, int, int, int, int, int], ...]
    special_profiles: tuple[tuple[int, int, int, int, int], ...]
    special_fields: tuple[str, ...] = ("model_id", "kind", "origin", "neutral_only", "mp_cost")
    special_kinds: tuple[str, ...] = ("unused-zero", "block", "reflect", "bounce")
    special_defense_count: Literal[23] = 23
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
    ordinary_weapon_count: Literal[45] = 45
    attack_miracle_count: Literal[6] = 6
    ordinary_armor_count: Literal[63] = 63
    additive_weapon_count: Literal[21] = 21
    additive_armor_count: Literal[4] = 4
    additive_sundry_count: Literal[1] = 1
    additive_miracle_count: Literal[3] = 3
    combat_effect_count: Literal[142] = 142
    composition_kinds: tuple[str, ...] = ("add", "set-element-and-add", "double-and-mix-element")
    composition: Literal["ordered-fixed-weapon-additions-or-standalone-positive-weapon-miracle"] = (
        "ordered-fixed-weapon-additions-or-standalone-positive-weapon-miracle"
    )
    excluded_additive_models: tuple[int, ...] = (232,)
    exclusion_reason: Literal["unimplemented-area-attack"] = "unimplemented-area-attack"
    darkness: Literal["positive-post-defense-damage-sets-target-hp-zero"] = (
        "positive-post-defense-damage-sets-target-hp-zero"
    )
    timing_and_hidden_resolution_verified: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameCombatPlan:
        digest = hashlib.sha256(
            json.dumps(
                (
                    self.attack_profiles,
                    self.armor_profiles,
                    self.boost_profiles,
                    self.special_profiles,
                ),
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
            or self.excluded_additive_models != (232,)
            or self.special_fields != ("model_id", "kind", "origin", "neutral_only", "mp_cost")
            or self.special_kinds != ("unused-zero", "block", "reflect", "bounce")
        ):
            raise ValueError(f"full-game combat profiles differ from pinned sources ({digest})")
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
        if raw.get("isPlusAtk") is not True or item.model_id == 232:
            continue
        category, asset = raw.get("category"), raw.get("imageName")
        if not isinstance(category, str) or not isinstance(asset, str):
            raise ValueError("additive identity is absent")
        reference = by_reference.get((category, asset))
        attack, cost = raw.get("atk", 0), raw.get("cost", 0)
        element = raw.get("element", "non-element")
        ability = raw.get("ability")
        kind = {
            None: 0,
            "bounceMiracle": 0,
            "blockMiracle": 0,
            "setElement": 1,
            "doubleAtk": 2,
        }.get(ability)
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
        if ability in ("bounceMiracle", "blockMiracle"):
            if item.model_id not in (34, 56):
                raise ValueError("pinned special additive weapon differs")
            effects.append("Bounce a miracle" if ability == "bounceMiracle" else "Block a miracle")
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
    specials = _special_profiles(catalog, by_reference)
    for item in catalog.items:
        if item.model_id not in {row[0] for row in specials}:
            continue
        raw = item.raw
        if raw["category"] == "weapons" and raw.get("isPlusAtk") is not True:
            attacks.append((item.model_id, raw["atk"], 0, 0, 0))
        elif raw["category"] == "armor" and raw.get("def", 0) > 0:
            defenses.append((item.model_id, raw["def"], 0, 0, 0))
    return FullGameCombatPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        attack_profiles=tuple(sorted(attacks)),
        armor_profiles=tuple(sorted(row for row in defenses if row[3] == 0)),
        boost_profiles=tuple(boosts),
        special_profiles=specials,
    )


def _special_profiles(
    catalog: ApiCatalogSnapshot, by_reference: dict[tuple[str, str], ArtifactRecord]
) -> tuple[tuple[int, int, int, int, int], ...]:
    # Identity, complete description, price/cost, gift weight and category are checked.
    specifications = (
        (21, "Bouncing Sword", "weapons", 5, "bounceWeapon", 10, 7, False),
        (34, "Sky Harpoon", "weapons", 9, "bounceMiracle", 5, 1, True),
        (38, "Reflection Sword", "weapons", 10, "reflectWeapon", 5, 3, False),
        (39, "Moonlight Axe", "weapons", 10, "reflectMiracle", 10, 1, False),
        (42, "Angel Knife", "weapons", 11, "blockMiracle", 15, 1, False),
        (50, "Angel Sword", "weapons", 13, "blockMiracle", 15, 1, False),
        (55, "Angel Axe", "weapons", 15, "blockMiracle", 15, 1, False),
        (56, "Angel Bow", "weapons", 15, "blockMiracle", 15, 1, True),
        (114, "Sky Boots", "armor", 1, "bounceMiracle", 5, 1, False),
        (125, "Sky Gauntlet", "armor", 3, "bounceMiracle", 5, 1, False),
        (137, "Sky Helm", "armor", 5, "bounceMiracle", 5, 1, False),
        (151, "Sky Shield", "armor", 7, "bounceMiracle", 5, 1, False),
        (156, "Moonlight Helm", "armor", 8, "reflectMiracle", 10, 1, False),
        (164, "Sky Armor", "armor", 9, "bounceMiracle", 5, 1, False),
        (165, "Angel Gauntlet", "armor", 9, "blockMiracle", 15, 1, False),
        (167, "Moonlight Shield", "armor", 10, "reflectMiracle", 10, 1, False),
        (171, "Angel Cap", "armor", 11, "blockMiracle", 15, 1, False),
        (174, "Moonlight Armor", "armor", 12, "reflectMiracle", 10, 1, False),
        (177, "Angel Shield", "armor", 13, "blockMiracle", 15, 1, False),
        (179, "Angel Armor", "armor", 15, "blockMiracle", 15, 1, False),
        (190, "Super Mirror", "armor", 0, "reflectAnything", 10, 1, False),
        (233, "<Wall>", "miracles", 0, "blockWeapon", 6, 1, False),
        (234, "<Turbulence>", "miracles", 0, "bounceMiracle", 5, 1, False),
    )
    descriptions = {
        "bounceWeapon": "Bounce a NE weapon",
        "reflectWeapon": "Reflect a NE weapon",
        "blockWeapon": "Block a NE weapon",
        "bounceMiracle": "Bounce a miracle",
        "reflectMiracle": "Reflect a miracle",
        "blockMiracle": "Block a miracle",
        "reflectAnything": "Reflect anything",
    }
    items = {item.model_id: item for item in catalog.items}
    profiles = []
    for model, name, category, value, ability, price_or_cost, weight, additive in specifications:
        raw = items[model].raw
        reference = by_reference.get((category, str(raw.get("imageName"))))
        field = "def" if category == "armor" else "atk"
        numeric = (f"{'+' if additive else ''}{field.upper()}{value}",) if value else ()
        tail = ("Cost", f"{price_or_cost}MP") if category == "miracles" else (f"${price_or_cost}",)
        if (
            reference is None
            or raw.get("name") != name
            or raw.get("category") != category
            or raw.get(field, 0) != value
            or raw.get("ability") != ability
            or raw.get("element", "non-element") != "non-element"
            or raw.get("isPlusAtk", False) is not additive
            or raw.get("hitRate", 100) != 100
            or raw.get("cost" if category == "miracles" else "price") != price_or_cost
            or raw.get("giftRate") != weight
            or reference.element_image_paths != ()
            or reference.detail
            != (name, *numeric, descriptions[ability], *tail, f"Gift Rate: {weight}/500")
        ):
            raise ValueError("special defense API and Bible identity or descriptions differ")
        kind = 1 if ability.startswith("block") else 3 if ability.startswith("bounce") else 2
        origin = -1 if ability == "reflectAnything" else 0 if ability.endswith("Weapon") else 1
        profiles.append(
            (model, kind, origin, int(origin == 0), price_or_cost if category == "miracles" else 0)
        )
    return tuple(profiles)
