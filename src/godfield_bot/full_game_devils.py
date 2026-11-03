"""Pinned devil effects; opt-in Apocalypse scheduling remains provisional."""

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

DEVIL_PROFILES: Final = (
    (240, 7, 1, 10),
    (241, 5, 1, 20),
    (242, 3, 1, 30),
    (243, 5, 2, 2),
    (244, 5, 3, 10),
)
DEVIL_PROFILE_FIELDS: Final = ("model_id", "appearance_percent", "kind", "value")
DEVIL_NOTE: Final = "After the Apocalypse, a devil appears by 25% each time an artifact given."
DEVIL_PROFILE_SHA256: Final = "a6b1927315e0a08937c1d46f995fbe825b9866d9b063440b5bd88097313eeef4"
DEVIL_BIBLE_SHA256: Final = "a52921e10bc30710479184bc3746bce0c873e5817ce3b0d7e3da1c04f42762c3"


class FullGameDevilPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profiles: tuple[tuple[StrictInt, StrictInt, StrictInt, StrictInt], ...] = DEVIL_PROFILES
    profile_fields: tuple[str, ...] = DEVIL_PROFILE_FIELDS
    profile_sha256: Literal["a6b1927315e0a08937c1d46f995fbe825b9866d9b063440b5bd88097313eeef4"] = (
        DEVIL_PROFILE_SHA256
    )
    bible_profile_sha256: Literal[
        "a52921e10bc30710479184bc3746bce0c873e5817ce3b0d7e3da1c04f42762c3"
    ] = DEVIL_BIBLE_SHA256
    appearance_percent: Literal[25] = 25
    effect_count: Literal[5] = 5
    apocalypse: Literal["explicit-opt-in-completed-turn-threshold-zero-disabled-provisional"] = (
        "explicit-opt-in-completed-turn-threshold-zero-disabled-provisional"
    )
    gift_order: Literal[
        "receipt-then-native-devil-before-next-receipt-depth-first-family5-provisional"
    ] = "receipt-then-native-devil-before-next-receipt-depth-first-family5-provisional"
    sampling: Literal["one-independent0to99-ticket-pinned7-5-3-5-5-percent-per-receipt"] = (
        "one-independent0to99-ticket-pinned7-5-3-5-5-percent-per-receipt"
    )
    damage: Literal["direct-hp-no-defense-owned-sun-then-departure-and-bow-provisional"] = (
        "direct-hp-no-defense-owned-sun-then-departure-and-bow-provisional"
    )
    trickster: Literal[
        "up-to-two-uniform-actual-nonmiracles-or-performed-miracles-stable-survivors-no-replacements-provisional"
    ] = (
        "up-to-two-uniform-actual-nonmiracles-or-performed-miracles-"
        "stable-survivors-no-replacements-provisional"
    )
    charity: Literal[
        "uniform-hp-mp-cp-including-capped-resources-no-resurrection-configured-cap-provisional"
    ] = "uniform-hp-mp-cp-including-capped-resources-no-resurrection-configured-cap-provisional"
    automatic_bound: Literal["two-times-players-times-capacity-receipts-per-turn-atomic-error"] = (
        "two-times-players-times-capacity-receipts-per-turn-atomic-error"
    )
    sacrifice: Literal["joined-tagged-replacement-receipts-after-apocalypse-provisional"] = (
        "joined-tagged-replacement-receipts-after-apocalypse-provisional"
    )
    official_apocalypse_threshold_verified: Literal[False] = False
    official_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGameDevilPlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profiles != DEVIL_PROFILES
            or self.profile_fields != DEVIL_PROFILE_FIELDS
            or hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
        ):
            raise ValueError("full-game devil source contract differs")
        return self


def build_full_game_devil_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameDevilPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    group = bible.catalog.get("devils")
    if group is None or group.notes != (DEVIL_NOTE,) or len(group.items) != 5:
        raise ValueError("complete devil Bible source scope differs")
    rows = tuple((r.asset, r.image_path, r.detail, r.element_image_paths) for r in group.items)
    if (
        hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        != DEVIL_BIBLE_SHA256
    ):
        raise ValueError("devil Bible effects or appearance contracts differ")
    profiles = []
    for item in catalog.items:
        if not 240 <= item.model_id <= 244:
            continue
        raw = item.raw
        reference = next((r for r in group.items if r.asset == raw.get("imageName")), None)
        kinds = {"dealDamage": 1, "removeSomething": 2, "boostSomething": 3}
        if (
            raw.get("category") != "devils"
            or reference is None
            or raw.get("ability") not in kinds
            or reference.detail[0] != raw.get("name")
            or reference.image_path != f"/images/items/devils/{raw.get('imageName')}.webp"
        ):
            raise ValueError("devil API and Bible identities differ")
        profiles.append(
            (
                item.model_id,
                int(raw.get("appearanceRate", 0)),
                kinds[str(raw["ability"])],
                int(raw.get("abilityValue", 2)),
            )
        )
    return FullGameDevilPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        profiles=tuple(profiles),
    )
