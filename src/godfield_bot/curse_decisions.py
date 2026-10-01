"""Versioned status decisions sharing the portable native curse state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from godfield_bot.curse_dynamics import (
    CurseDynamicsMetadata,
    create_provisional_curse_dynamics_batch,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

if TYPE_CHECKING:
    from godfield_sim import CurseDynamicsBatch

CURSE_DECISION_RULESET_ID: Final = "caller-driven-fog-flash-darkcloud-decisions-provisional-v1"
STATUS_OBSERVATION_FIELDS: Final = (
    "seat",
    "present",
    "visible",
    "hp",
    "illness_stage",
    "curse_mask",
)
HIT_DECISION_FIELDS: Final = ("hit", "randomness_required")


class CurseDecisionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["caller-driven-fog-flash-darkcloud-decisions-provisional-v1"] = (
        CURSE_DECISION_RULESET_ID
    )
    dynamics: CurseDynamicsMetadata
    status_observation_fields: tuple[str, ...] = STATUS_OBSERVATION_FIELDS
    hit_decision_fields: tuple[str, ...] = HIT_DECISION_FIELDS
    padded_players: Literal[9] = 9
    player_ordering: Literal["actor-first-cyclic-with-absolute-seat-map"] = (
        "actor-first-cyclic-with-absolute-seat-map"
    )
    padding: Literal["seat-minus-one-all-other-fields-zero"] = (
        "seat-minus-one-all-other-fields-zero"
    )
    fog_visibility: Literal["hide-other-hp-illness-mask-conservative-provisional"] = (
        "hide-other-hp-illness-mask-conservative-provisional"
    )
    unknown_values: Literal["zero-data-with-visible-zero-not-zero-hp-claim"] = (
        "zero-data-with-visible-zero-not-zero-hp-claim"
    )
    observation_exclusions: tuple[str, ...] = (
        "inventory",
        "mp",
        "cp",
        "tick-counts",
        "transitions",
        "random-tickets",
        "lifetime-counters",
    )
    defense_limit: Literal["dead-zero-flash-one-otherwise-caller-limit-1-through-512"] = (
        "dead-zero-flash-one-otherwise-caller-limit-1-through-512"
    )
    chance_hits: Literal["clouded-or-rate-100-hit-otherwise-ticket-below-rate"] = (
        "clouded-or-rate-100-hit-otherwise-ticket-below-rate"
    )
    enemy_candidates: Literal["caller-binary-nine-seat-mask-living-other-players-only"] = (
        "caller-binary-nine-seat-mask-living-other-players-only"
    )
    fog_targeting: Literal["caller-eligible-rank-ticket-provisional-no-internal-rng"] = (
        "caller-eligible-rank-ticket-provisional-no-internal-rng"
    )
    queries_mutate_state: Literal[False] = False
    decision_consumer: Literal["trusted-scheduler-not-policy-feature"] = (
        "trusted-scheduler-not-policy-feature"
    )
    team_legality_supplied_by_caller: Literal[True] = True
    complete_team_rules_implemented: Literal[False] = False
    status_projection_implemented: Literal[True] = True
    complete_policy_projection_implemented: Literal[False] = False
    dream_disguise_implemented: Literal[False] = False
    item_legality_and_costs_implemented: Literal[False] = False
    action_observation_checkpoint_compatible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def fixed_projection_contract(self) -> CurseDecisionMetadata:
        if (
            self.status_observation_fields != STATUS_OBSERVATION_FIELDS
            or self.hit_decision_fields != HIT_DECISION_FIELDS
            or self.observation_exclusions
            != (
                "inventory",
                "mp",
                "cp",
                "tick-counts",
                "transitions",
                "random-tickets",
                "lifetime-counters",
            )
        ):
            raise ValueError("curse status decision projection contract differs")
        return self


@dataclass(frozen=True)
class ProvisionalCurseDecisionBatch:
    batch: CurseDynamicsBatch
    metadata: CurseDecisionMetadata


def create_provisional_curse_decision_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    initial_hp: int = 40,
) -> ProvisionalCurseDecisionBatch:
    """Share one status state; neither queries nor this factory start a rollout."""
    configured = create_provisional_curse_dynamics_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        initial_hp=initial_hp,
    )
    import godfield_sim as native

    if (
        getattr(native, "CURSE_DECISION_SCHEMA_VERSION", None) != 1
        or getattr(native, "CURSE_DECISION_RULESET_ID", None) != CURSE_DECISION_RULESET_ID
        or any(
            not hasattr(configured.batch, method)
            for method in (
                "status_observations",
                "defense_card_limits",
                "hit_decisions",
                "enemy_targets",
            )
        )
    ):
        raise ProvisionalRuleUnavailableError("native curse decision contract differs")
    return ProvisionalCurseDecisionBatch(
        configured.batch, CurseDecisionMetadata(dynamics=configured.metadata)
    )
