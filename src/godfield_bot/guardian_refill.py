"""Pinned relative gift weights; replacement timing is an opt-in hypothesis."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot

REFILL_PROFILE_SHA256: Final = "fecd58f31003c6a170cb41e0ef9f68e1659e9e5f0d817c4a0b98e094c32b6423"


def _profile_digest(weights: tuple[tuple[int, int], ...]) -> str:
    return hashlib.sha256(json.dumps(weights, separators=(",", ":")).encode()).hexdigest()


class GuardianRefillPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["supported-consumption-deferred-weighted-gifts-provisional-v1"] = (
        "supported-consumption-deferred-weighted-gifts-provisional-v1"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["fecd58f31003c6a170cb41e0ef9f68e1659e9e5f0d817c4a0b98e094c32b6423"] = (
        REFILL_PROFILE_SHA256
    )
    model_weights: tuple[tuple[int, int], ...]
    supported_models: Literal[94] = 94
    total_weight: Literal[227] = 227
    source_denominator: Literal[500] = 500
    distribution: Literal["relative-weights-conditioned-on-supported-models-only"] = (
        "relative-weights-conditioned-on-supported-models-only"
    )
    timing: Literal["completed-turn-ready-phase-living-owners-only"] = (
        "completed-turn-ready-phase-living-owners-only"
    )
    quantity: Literal["one-gift-per-consumed-weapon-or-confirmed-armor-slot"] = (
        "one-gift-per-consumed-weapon-or-confirmed-armor-slot"
    )
    placement: Literal["same-empty-slot-no-compaction-or-overflow"] = (
        "same-empty-slot-no-compaction-or-overflow"
    )
    terminal_policy: Literal["discard-pending-gifts-without-sampling"] = (
        "discard-pending-gifts-without-sampling"
    )
    random_stream: Literal["seed-environment-episode-channel-6771-v1"] = (
        "seed-environment-episode-channel-6771-v1"
    )
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profile(self) -> GuardianRefillPlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or len(self.model_weights) != self.supported_models
            or sum(weight for _, weight in self.model_weights) != self.total_weight
            or _profile_digest(self.model_weights) != self.profile_sha256
        ):
            raise ValueError("provisional refill requires the pinned supported gift profile")
        return self


def build_guardian_refill_plan(
    catalog: ApiCatalogSnapshot,
    bible: BibleSnapshot,
    supported_model_ids: tuple[int, ...],
) -> GuardianRefillPlan:
    """Cross-check both pinned sources; do not invent or widen supported gifts."""
    if (
        catalog.content_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
        or bible.client.sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
        or len(supported_model_ids) != 94
        or len(set(supported_model_ids)) != 94
    ):
        raise ValueError("provisional refill requires 94 supported models and pinned sources")
    supported = set(supported_model_ids)
    records = [item for category in bible.catalog.values() for item in category.items]
    weights = []
    for item in catalog.items:
        if item.model_id not in supported:
            continue
        matches = [record for record in records if record.asset == item.raw.get("imageName")]
        if len(matches) != 1:
            raise ValueError("missing or duplicate supported refill Bible asset")
        rates = [line for line in matches[0].detail if line.startswith("Gift Rate:")]
        match = re.fullmatch(r"Gift Rate: ([0-9]+)/500", rates[0]) if len(rates) == 1 else None
        if (
            match is None
            or not 0 < int(match[1]) <= 500
            or type(item.raw.get("giftRate")) is not int
            or item.raw["giftRate"] != int(match[1])
        ):
            raise ValueError("missing, invalid, or mismatched supported refill gift rate")
        weights.append((item.model_id, int(match[1])))
    return GuardianRefillPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        model_weights=tuple(weights),
    )
