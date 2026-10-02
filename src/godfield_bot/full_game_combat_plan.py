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
from godfield_bot.elements import COMBAT_ELEMENT_IDS, CombatElement
from godfield_bot.guardian_batch import _guardian_card_profiles
from godfield_bot.reference import (
    plain_attack_booster_cards,
    plain_chance_dual_role_weapon_cards,
    plain_chance_weapon_cards,
    verified_chance_attack_miracle_cards,
)

FULL_GAME_COMBAT_SHA256: Final = "9440a09fe928fbb6c4c1b2a58e3d6703a530230dc2baa4edec927a623dd6833c"


class FullGameCombatPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[5] = 5
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["9440a09fe928fbb6c4c1b2a58e3d6703a530230dc2baa4edec927a623dd6833c"] = (
        FULL_GAME_COMBAT_SHA256
    )
    attack_profiles: tuple[tuple[int, int, int, int, int], ...]
    armor_profiles: tuple[tuple[int, int, int, int, int], ...]
    boost_profiles: tuple[tuple[int, int, int, int, int, int], ...]
    special_profiles: tuple[tuple[int, int, int, int, int], ...]
    chance_profiles: tuple[tuple[int, int], ...]
    attack_effect_profiles: tuple[tuple[int, int, int], ...]
    attack_effect_fields: tuple[str, ...] = ("model_id", "kind", "value")
    attack_effect_kinds: tuple[str, ...] = (
        "unused-zero",
        "absorb-hp",
        "mask-on-damage",
        "illness-on-damage",
        "direct-mask",
        "direct-illness",
    )
    damage_effect_count: Literal[15] = 15
    direct_curse_count: Literal[5] = 5
    chance_fields: tuple[str, ...] = ("model_id", "hit_rate")
    chance_weapon_count: Literal[17] = 17
    chance_miracle_count: Literal[7] = 7
    dual_role_chance_defense_count: Literal[1] = 1
    numeric_defense_count: Literal[64] = 64
    excluded_chance_models: tuple[int, ...] = (112,)
    chance_exclusion_reason: Literal["ascension-variant-not-yet-integrated"] = (
        "ascension-variant-not-yet-integrated"
    )
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
    ordinary_weapon_count: Literal[56] = 56
    attack_miracle_count: Literal[7] = 7
    ordinary_armor_count: Literal[63] = 63
    additive_weapon_count: Literal[21] = 21
    additive_armor_count: Literal[4] = 4
    additive_sundry_count: Literal[1] = 1
    additive_miracle_count: Literal[3] = 3
    combat_effect_count: Literal[183] = 183
    composition_kinds: tuple[str, ...] = ("add", "set-element-and-add", "double-and-mix-element")
    composition: Literal[
        "ordered-fixed-weapon-additions-or-standalone-weapon-miracle-chance-direct-curse"
    ] = "ordered-fixed-weapon-additions-or-standalone-weapon-miracle-chance-direct-curse"
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
                    self.chance_profiles,
                    self.attack_effect_profiles,
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
            or self.chance_fields != ("model_id", "hit_rate")
            or self.excluded_chance_models != (112,)
            or self.attack_effect_fields != ("model_id", "kind", "value")
            or self.attack_effect_kinds
            != (
                "unused-zero",
                "absorb-hp",
                "mask-on-damage",
                "illness-on-damage",
                "direct-mask",
                "direct-illness",
            )
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
    chances, chance_attacks, chance_defenses = _chance_profiles(catalog, bible, by_reference)
    attacks.extend(chance_attacks)
    defenses.extend(chance_defenses)
    attack_effects, effect_attacks, effect_chances = _attack_effect_profiles(catalog, by_reference)
    attacks.extend(effect_attacks)
    return FullGameCombatPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        attack_profiles=tuple(sorted(attacks)),
        armor_profiles=tuple(sorted(row for row in defenses if row[3] == 0)),
        boost_profiles=tuple(boosts),
        special_profiles=specials,
        chance_profiles=tuple(sorted((*chances, *effect_chances))),
        attack_effect_profiles=attack_effects,
    )


def _chance_profiles(
    catalog: ApiCatalogSnapshot,
    bible: BibleSnapshot,
    by_reference: dict[tuple[str, str], ArtifactRecord],
) -> tuple[
    tuple[tuple[int, int], ...],
    list[tuple[int, int, int, int, int]],
    list[tuple[int, int, int, int, int]],
]:
    weapons = plain_chance_weapon_cards(bible)
    dual = plain_chance_dual_role_weapon_cards(bible)
    miracles = verified_chance_attack_miracle_cards(bible)
    if len(weapons) != 14 or len(dual) != 1 or len(miracles) != 6:
        raise ValueError("pinned chance family is incomplete")
    chances, attacks, defenses = [], [], []
    for item in catalog.items:
        raw = item.raw
        category, asset = raw.get("category"), raw.get("imageName")
        if category == "weapons" and asset in weapons:
            rate, attack, element = weapons[asset]
            defense, cost, origin = 0, 0, 0
        elif category == "weapons" and asset in dual:
            rate, attack, defense, element = dual[asset]
            cost, origin = 0, 0
            if item.model_id != 108:
                raise ValueError("pinned chance dual-role weapon differs")
        elif category == "miracles" and asset in miracles:
            rate, attack, cost, element = miracles[asset]
            defense, origin = 0, 1
        else:
            continue
        reference = by_reference[(category, asset)]
        numeric = (f"{rate}%ATK{attack}",) + ((f"DEF{defense}",) if defense else ())
        tail = ("Cost", f"{cost}MP") if origin else (f"${raw.get('price')}",)
        if (
            raw.get("atk") != attack
            or raw.get("def", 0) != defense
            or raw.get("hitRate") != rate
            or raw.get("cost", 0) != cost
            or raw.get("element") != element
            or raw.get("ability") is not None
            or raw.get("isPlusAtk", False) is not False
            or reference.element_image_paths != (f"/images/elements/{element}.webp",)
            or reference.detail
            != (raw.get("name"), *numeric, *tail, f"Gift Rate: {raw.get('giftRate')}/500")
        ):
            raise ValueError("chance API and Bible identity or numeric values differ")
        chances.append((item.model_id, rate))
        attacks.append((item.model_id, attack, COMBAT_ELEMENT_IDS[element], origin, cost))
        if defense:
            defenses.append((item.model_id, defense, COMBAT_ELEMENT_IDS[element], 0, 0))
    if len(chances) != 21:
        raise ValueError("pinned chance models are incomplete")
    return tuple(chances), attacks, defenses


def _attack_effect_profiles(
    catalog: ApiCatalogSnapshot, by_reference: dict[tuple[str, str], ArtifactRecord]
) -> tuple[
    tuple[tuple[int, int, int], ...],
    list[tuple[int, int, int, int, int]],
    list[tuple[int, int]],
]:
    # Exact reviewed identities, descriptions, costs, elements, weights and API abilities.
    # Kinds distinguish positive-damage triggers from zero-ATK direct curses.
    specs: tuple[tuple[int, str, int, CombatElement, int, int, int, int, str], ...] = (
        (27, "Ghost Sword", 7, "non-element", 100, 10, 1, 0, "Absorb HP"),
        (30, "Hell Scissors", 8, "non-element", 100, 15, 3, 3, "Hell on damage"),
        (33, "Gale Sword", 9, "non-element", 100, 10, 3, 1, "Cold on damage"),
        (36, "Bogus Spear", 10, "non-element", 100, 10, 2, 2, "Dream on damage"),
        (41, "Hexagon Doom", 11, "non-element", 100, 15, 2, 8, "Dark Cloud on damage"),
        (45, "Real Ghost Sword", 12, "non-element", 100, 15, 1, 0, "Absorb HP"),
        (48, "Severe Gale Sword", 13, "non-element", 100, 15, 3, 1, "Cold on damage"),
        (62, "Wind Talons", 1, "stone", 100, 10, 3, 1, "Cold on damage"),
        (70, "Flash Dagger", 2, "light", 100, 15, 2, 4, "Flash on damage"),
        (72, "Fog Gun", 3, "water", 100, 10, 2, 1, "Fog on damage"),
        (80, "Dream Mallet", 4, "wood", 100, 15, 2, 2, "Dream on damage"),
        (97, "Fog Fan", 3, "water", 50, 8, 2, 1, "Fog on damage"),
        (98, "Vine Shoot", 3, "wood", 75, 10, 1, 0, "Absorb HP"),
        (216, "<Absorption>", 10, "light", 100, 10, 1, 0, "Absorb HP"),
        (219, "<Wind>", 0, "non-element", 100, 6, 5, 1, "Cold"),
        (220, "<Heaven Wind>", 0, "non-element", 100, 15, 5, 4, "Heaven"),
        (221, "<Fog>", 0, "water", 100, 3, 4, 1, "Fog"),
        (222, "<Dream>", 0, "wood", 100, 6, 4, 2, "Dream"),
        (223, "<Dark Cloud>", 0, "darkness", 100, 5, 4, 8, "Dark Cloud"),
        (224, "<Flash>", 1, "light", 25, 3, 2, 4, "Flash on damage"),
    )
    items = {item.model_id: item for item in catalog.items}
    masks = {1: "fog", 2: "dream", 4: "flash", 8: "darkcloud"}
    illnesses = {1: "cold", 3: "hell", 4: "heaven"}
    profiles, attacks, chances = [], [], []
    for model, name, attack, element, rate, price_or_cost, kind, value, description in specs:
        raw = items[model].raw
        category = "miracles" if model >= 210 else "weapons"
        reference = by_reference.get((category, str(raw.get("imageName"))))
        ability = "absorbHP" if kind == 1 else "addCurseOnDamage" if kind <= 3 else "addCurse"
        numeric = ((f"{rate}%" if rate < 100 else "") + f"ATK{attack}",) if attack else ()
        tail = ("Cost", f"{price_or_cost}MP") if category == "miracles" else (f"${price_or_cost}",)
        if (
            reference is None
            or raw.get("name") != name
            or raw.get("category") != category
            or raw.get("atk", 0) != attack
            or raw.get("element", "non-element") != element
            or raw.get("hitRate", 100) != rate
            or raw.get("isPlusAtk", False) is not False
            or raw.get("ability") != ability
            or raw.get("giftRate") != 1
            or raw.get("cost" if category == "miracles" else "price") != price_or_cost
            or raw.get("curse")
            != (None if kind == 1 else (masks if kind in (2, 4) else illnesses)[value])
            or reference.element_image_paths
            != (() if element == "non-element" else (f"/images/elements/{element}.webp",))
            or reference.detail != (name, *numeric, description, *tail, "Gift Rate: 1/500")
        ):
            raise ValueError(
                f"attack effect API and Bible identity or description differs ({model})"
            )
        profiles.append((model, kind, value))
        attacks.append(
            (
                model,
                attack,
                COMBAT_ELEMENT_IDS[element],
                int(category == "miracles"),
                price_or_cost if category == "miracles" else 0,
            )
        )
        if rate < 100:
            chances.append((model, rate))
    return tuple(profiles), attacks, chances


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
