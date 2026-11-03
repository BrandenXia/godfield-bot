"""Pinned ten phenomena and explicitly provisional native control/ownership rules."""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot

PHENOMENON_PROFILES: Final = (
    (287, 1, 2, 0, 100),
    (288, 2, 1, 0, 100),
    (289, 3, 3, 0, 100),
    (290, 4, 1, 0, 100),
    (291, 5, 50, 5, 100),
    (292, 6, 30, 6, 75),
    (293, 7, 50, 0, 100),
    (294, 8, 0, 0, 100),
    (295, 9, 0, 0, 100),
    (296, 10, 0, 0, 100),
)
PHENOMENON_FIELDS: Final = ("model_id", "kind", "value", "element", "hit_rate")
PHENOMENON_SHA256: Final = "600b2314b68a4809797395afcaa2c711b0e8aa705bcd2bdf5f248ffd49645c55"
PHENOMENON_BIBLE_SHA256: Final = "6c622567813dacf552120f190c8c05308b74f016da4bd2781e107887305a352b"


class FullGamePhenomenonPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profiles: tuple[tuple[StrictInt, StrictInt, StrictInt, StrictInt, StrictInt], ...] = (
        PHENOMENON_PROFILES
    )
    profile_fields: tuple[str, ...] = PHENOMENON_FIELDS
    profile_sha256: Literal["600b2314b68a4809797395afcaa2c711b0e8aa705bcd2bdf5f248ffd49645c55"] = (
        PHENOMENON_SHA256
    )
    bible_profile_sha256: Literal[
        "6c622567813dacf552120f190c8c05308b74f016da4bd2781e107887305a352b"
    ] = PHENOMENON_BIBLE_SHA256
    fate_model_ids: tuple[int, ...] = (207,)
    effect_count: Literal[10] = 10
    selection: Literal["native-uniform-all10-at-confirm-not-policy-selected-provisional"] = (
        "native-uniform-all10-at-confirm-not-policy-selected-provisional"
    )
    recipients: Literal["living-only-pinned-client-aG-scope"] = "living-only-pinned-client-aG-scope"
    attacks: Literal[
        "caster-source-generic-origin5-tub-all-living-blackhole-enemy-uniform-family6-provisional"
    ] = "caster-source-generic-origin5-tub-all-living-blackhole-enemy-uniform-family6-provisional"
    automatic_targets: Literal["warm-and-gold-native-uniform-all-living-provisional"] = (
        "warm-and-gold-native-uniform-all-living-provisional"
    )
    fever: Literal["set-stage2-no-infliction-worsening-or-immediate-damage-client-pinned"] = (
        "set-stage2-no-infliction-worsening-or-immediate-damage-client-pinned"
    )
    tornado: Literal["assign1-no-damage-sun-or-departure-event-provisional"] = (
        "assign1-no-damage-sun-or-departure-event-provisional"
    )
    gold: Literal["zero-living-cp-credit-sum-configured-cap-separate-loss-provisional"] = (
        "zero-living-cp-credit-sum-configured-cap-separate-loss-provisional"
    )
    magnetic: Literal[
        "shuffle-all-held-models-preserve-seat-count-fresh-native-ids-clear-performed-refake-by-receiver-provisional"
    ] = (
        "shuffle-all-held-models-preserve-seat-count-fresh-native-ids-"
        "clear-performed-refake-by-receiver-provisional"
    )
    eclipse: Literal["shared-uniform-all10-summons-replace-living-guardians-provisional"] = (
        "shared-uniform-all10-summons-replace-living-guardians-provisional"
    )
    confusion: Literal[
        "add3-before-tick-native-single-play-discard-prayer-controller-consume-before-effect-provisional"
    ] = (
        "add3-before-tick-native-single-play-discard-prayer-controller-"
        "consume-before-effect-provisional"
    )
    forced_actions: Literal[
        "ready-only-choice0-no-selection-loops-native-prestep-policy-gradient-mask-false"
    ] = "ready-only-choice0-no-selection-loops-native-prestep-policy-gradient-mask-false"
    unsupported_roles: Literal[
        "unimplemented-held-role-selected-atomic-error-never-removed-from-pool"
    ] = "unimplemented-held-role-selected-atomic-error-never-removed-from-pool"
    joined_phenomenon_effects_implemented: Literal[True] = True
    complete_guardian_and_trade_dependencies: Literal[False] = False
    complete_training_pipeline_implemented: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGamePhenomenonPlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profiles != PHENOMENON_PROFILES
            or self.profile_fields != PHENOMENON_FIELDS
            or self.fate_model_ids != (207,)
            or hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
        ):
            raise ValueError("full-game phenomenon source contract differs")
        return self


def build_full_game_phenomenon_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGamePhenomenonPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    group = bible.catalog.get("phenomena")
    if group is None or group.notes or len(group.items) != 10:
        raise ValueError("complete phenomenon Bible source scope differs")
    rows = tuple((r.asset, r.image_path, r.detail, r.element_image_paths) for r in group.items)
    if (
        hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        != PHENOMENON_BIBLE_SHA256
    ):
        raise ValueError("complete phenomenon Bible effects differ")
    raw = {item.model_id: item.raw for item in catalog.items}
    fate = raw[207]
    fate_reference = next(
        (r for r in bible.catalog["sundries"].items if r.asset == "string-of-fate"), None
    )
    if (
        fate
        != {
            "imageName": "string-of-fate",
            "category": "sundries",
            "ability": "callPhenomenon",
            "price": 3,
            "giftRate": 1,
            "name": "String of Fate",
        }
        or fate_reference is None
        or fate_reference.detail
        != ("String of Fate", "Cause", "a phenomenon", "$3", "Gift Rate: 1/500")
        or fate_reference.image_path != "/images/items/sundries/string-of-fate.webp"
        or fate_reference.element_image_paths
    ):
        raise ValueError("String of Fate API and Bible identities differ")
    abilities = (
        "setCurseOfEverybody",
        "setCurseOfEverybody",
        "confuseEverybody",
        "setHPOfEverybody",
        "attackSomebody",
        None,
        "boostHP",
        "collectCPOfEverybody",
        "shuffleItemsOfEverybody",
        "setGuardianOfEverybody",
    )
    groups = (
        "mars",
        "mercury",
        "jupiter",
        "saturn",
        None,
        None,
        "neptune",
        "venus",
        "earth",
        "moon",
    )
    for model, kind, value, element, rate in PHENOMENON_PROFILES:
        item, reference = raw[model], group.items[model - 287]
        if (
            item.get("category") != "phenomena"
            or item.get("imageName") != reference.asset
            or item.get("name") != reference.detail[0]
            or item.get("ability") != abilities[kind - 1]
            or item.get("guardian") != groups[kind - 1]
            or item.get("curse") != ({1: "fever", 2: "fog"}.get(kind))
            or int(item.get("atk", 0)) != (value if kind in (5, 6) else 0)
            or int(item.get("abilityValue", 0)) != (value if kind in (4, 7) else 0)
            or int(item.get("hitRate", 100)) != rate
            or item.get("element") != ({5: "light", 6: "darkness"}.get(kind))
            or element != ({5: 5, 6: 6}.get(kind, 0))
        ):
            raise ValueError("phenomenon API and Bible effect identities differ")
    return FullGamePhenomenonPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
