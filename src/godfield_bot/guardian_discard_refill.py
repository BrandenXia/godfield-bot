"""Separate discard/replacement timing and RNG over the pinned utility pool."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from godfield_bot.guardian_utility_refill import GuardianUtilityRefillPlan


class GuardianDiscardRefillPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["discard-consumption-deferred-weighted-gifts-provisional-v1"] = (
        "discard-consumption-deferred-weighted-gifts-provisional-v1"
    )
    distribution_base: GuardianUtilityRefillPlan
    quantity: Literal["one-gift-per-consumed-or-discarded-slot"] = (
        "one-gift-per-consumed-or-discarded-slot"
    )
    random_stream: Literal["seed-environment-episode-channel-6773-v1"] = (
        "seed-environment-episode-channel-6773-v1"
    )
    base_timing_and_placement_reused: Literal[True] = True
    base_consumption_only_quantity_and_rng_overridden: Literal[True] = True
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @property
    def model_weights(self) -> tuple[tuple[int, int], ...]:
        return self.distribution_base.model_weights
