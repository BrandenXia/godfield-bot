"""Separate 102-card gift pool; the existing 94-card refill remains unchanged."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_refill import _profile_digest, _supported_refill_weights

UTILITY_REFILL_PROFILE_SHA256: Final = (
    "c325f7ed4134a3feb6ff69948fbd6827d98f070b70951297601670902e56d9e3"
)


class GuardianUtilityRefillPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["utility-consumption-deferred-weighted-gifts-provisional-v1"] = (
        "utility-consumption-deferred-weighted-gifts-provisional-v1"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["c325f7ed4134a3feb6ff69948fbd6827d98f070b70951297601670902e56d9e3"] = (
        UTILITY_REFILL_PROFILE_SHA256
    )
    model_weights: tuple[tuple[int, int], ...]
    supported_models: Literal[102] = 102
    total_weight: Literal[277] = 277
    source_denominator: Literal[500] = 500
    distribution: Literal["relative-weights-conditioned-on-supported-models-only"] = (
        "relative-weights-conditioned-on-supported-models-only"
    )
    timing: Literal["completed-turn-ready-phase-living-owners-only"] = (
        "completed-turn-ready-phase-living-owners-only"
    )
    quantity: Literal["one-gift-per-consumed-weapon-armor-or-utility-slot"] = (
        "one-gift-per-consumed-weapon-armor-or-utility-slot"
    )
    placement: Literal["same-empty-slot-no-compaction-or-overflow"] = (
        "same-empty-slot-no-compaction-or-overflow"
    )
    terminal_policy: Literal["discard-pending-gifts-without-sampling"] = (
        "discard-pending-gifts-without-sampling"
    )
    random_stream: Literal["seed-environment-episode-channel-6772-v1"] = (
        "seed-environment-episode-channel-6772-v1"
    )
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profile(self) -> GuardianUtilityRefillPlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or len(self.model_weights) != self.supported_models
            or sum(weight for _, weight in self.model_weights) != self.total_weight
            or _profile_digest(self.model_weights) != self.profile_sha256
        ):
            raise ValueError("utility refill requires the pinned 102-card gift profile")
        return self


def build_guardian_utility_refill_plan(
    catalog: ApiCatalogSnapshot,
    bible: BibleSnapshot,
    supported_model_ids: tuple[int, ...],
) -> GuardianUtilityRefillPlan:
    return GuardianUtilityRefillPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        model_weights=_supported_refill_weights(catalog, bible, supported_model_ids, 102),
    )
