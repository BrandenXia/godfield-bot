"""Pinned Ascension identity and explicitly provisional attack-family scheduling."""

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

FULL_GAME_ASCENSION_SHA256: Final = (
    "d20664fab4740f69ea2a039a502dba71bbb8bd0744e0c47563edec271b3b7264"
)


class FullGameAttackFamilyPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[8] = 8
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["d20664fab4740f69ea2a039a502dba71bbb8bd0744e0c47563edec271b3b7264"] = (
        FULL_GAME_ASCENSION_SHA256
    )
    profiles: tuple[tuple[int, int, int, int, int, int], ...] = ((112, 1, 25, 30, 75, 5),)
    profile_fields: tuple[str, ...] = (
        "model_id",
        "attack",
        "hit_rate",
        "dying_attack",
        "dying_hit_rate",
        "element",
    )
    effect_count: Literal[1] = 1
    family_kinds: tuple[str, ...] = (
        "counter=1",
        "original-recipient=2",
        "post-death=3",
        "guardian=4",
        "postturn-receipt=5",
        "phenomenon=6",
        "market=7",
        "generated-producer=8",
        "generated-attack=9",
    )
    scheduler: Literal["shared-lifo-click-order-depth-first-single-tick-before-ending"] = (
        "shared-lifo-click-order-depth-first-single-tick-before-ending"
    )
    death_trigger: Literal["positive-to-zero-after-owned-sun-never-dead-setup-once-per-owner"] = (
        "positive-to-zero-after-owned-sun-never-dead-setup-once-per-owner"
    )
    bow_ownership: Literal["consume-all-remaining-actual-held-bows-copy-order-provisional"] = (
        "consume-all-remaining-actual-held-bows-copy-order-provisional"
    )
    recipients: Literal["ascending-other-living-seats-at-death-skip-later-dead-provisional"] = (
        "ascending-other-living-seats-at-death-skip-later-dead-provisional"
    )
    dying_source: Literal[
        "dead-source-allowed-only-post-death-shots-reflect-to-dead-resolves-empty"
    ] = "dead-source-allowed-only-post-death-shots-reflect-to-dead-resolves-empty"
    tick_death: Literal[
        "drain-post-tick-family-without-second-tick-before-ending-or-turn-limit"
    ] = "drain-post-tick-family-without-second-tick-before-ending-or-turn-limit"
    random_rule: Literal["dedicated-native-per-recipient-hit-stream-dark-cloud-skips-ticket"] = (
        "dedicated-native-per-recipient-hit-stream-dark-cloud-skips-ticket"
    )
    gifts: Literal[
        "deferred-until-entire-family-and-single-tick-finish-dead-or-ended-suppressed"
    ] = "deferred-until-entire-family-and-single-tick-finish-dead-or-ended-suppressed"
    queue_bound: Literal["player-count-squared-times-capacity-plus-two"] = (
        "player-count-squared-times-capacity-plus-two"
    )
    area_payload: Literal["private-per-shot-danger-flag-and-recipient-local-strike-count-v2"] = (
        "private-per-shot-danger-flag-and-recipient-local-strike-count-v2"
    )
    guardian_payload: Literal["private-instance-model-automatic-flag-family4-posttick-v3"] = (
        "private-instance-model-automatic-flag-family4-posttick-v3"
    )
    receipt_payload: Literal[
        "private-recipient-sacrifice-tag-automatic-family5-posttick-no-extra-owner-tick-v8"
    ] = "private-recipient-sacrifice-tag-automatic-family5-posttick-no-extra-owner-tick-v8"
    phenomenon_payload: Literal["revealed-phenomenon-model-generic-origin5-family6-v5"] = (
        "revealed-phenomenon-model-generic-origin5-family6-v5"
    )
    market_payload: Literal["private-owned-or-generated-escrow-original-auto-buyer-family7-v7"] = (
        "private-owned-or-generated-escrow-original-auto-buyer-family7-v7"
    )
    generated_payload: Literal[
        "private-instance-model-frame8-model-only-attack9-virtual-leader-auto-buyer-v7"
    ] = "private-instance-model-frame8-model-only-attack9-virtual-leader-auto-buyer-v7"
    official_multiplayer_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGameAttackFamilyPlan:
        if (
            hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
            or self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.profile_fields
            != ("model_id", "attack", "hit_rate", "dying_attack", "dying_hit_rate", "element")
            or self.family_kinds
            != (
                "counter=1",
                "original-recipient=2",
                "post-death=3",
                "guardian=4",
                "postturn-receipt=5",
                "phenomenon=6",
                "market=7",
                "generated-producer=8",
                "generated-attack=9",
            )
        ):
            raise ValueError("attack-family profiles or queue contract differ from pinned sources")
        return self


def build_full_game_attack_family_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameAttackFamilyPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    raw = next((item.raw for item in catalog.items if item.model_id == 112), None)
    weapons = bible.catalog.get("weapons")
    reference = (
        next((r for r in weapons.items if r.asset == "ascension-bow"), None) if weapons else None
    )
    if (
        raw
        != {
            "imageName": "ascension-bow",
            "category": "weapons",
            "element": "light",
            "atk": 1,
            "hitRate": 25,
            "ability": "attackDyingly",
            "abilityValue": 30,
            "price": 10,
            "giftRate": 1,
            "name": "Ascension Bow",
        }
        or reference is None
        or reference.detail
        != ("Ascension Bow", "25%ATK1", "75%ATK30 at Ascension", "$10", "Gift Rate: 1/500")
        or reference.image_path != "/images/items/weapons/ascension-bow.webp"
        or reference.element_image_paths != ("/images/elements/light.webp",)
    ):
        raise ValueError("Ascension API and Bible contracts differ")
    return FullGameAttackFamilyPlan(
        catalog_sha256=catalog.content_sha256, bible_client_sha256=bible.client.sha256
    )
