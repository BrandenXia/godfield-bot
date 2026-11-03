"""Current client team relation; local ending and visibility remain provisional."""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

TeamId = Annotated[int, Field(ge=0, le=4, strict=True)]
TEAM_FIELDS: Final = ("absolute_seat", "present", "team_id", "relation")
TEAM_CLIENT_SHA256: Final = "5ece06c224b6a7a5d877eb45d22ea18b82a03aaf1b7161cbbdf6a1e23ceab2cd"


class FullGameTeamPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    reviewed_at: Literal["2026-11-03"] = "2026-11-03"
    client_sha256: Literal["5ece06c224b6a7a5d877eb45d22ea18b82a03aaf1b7161cbbdf6a1e23ceab2cd"] = (
        TEAM_CLIENT_SHA256
    )
    enemy_relation: Literal["different-seats-and-either-source-solo-or-different-team"] = (
        "different-seats-and-either-source-solo-or-different-team"
    )
    guardian_trigger: Literal["living-owned-guardian-after-enemy-turn-only"] = (
        "living-owned-guardian-after-enemy-turn-only"
    )
    endings: Literal["last-living-faction-after-queued-reactions-and-original-tick-provisional"] = (
        "last-living-faction-after-queued-reactions-and-original-tick-provisional"
    )
    winners: Literal["all-shared-team-members-including-dead-or-one-solo-representative"] = (
        "all-shared-team-members-including-dead-or-one-solo-representative"
    )
    reset: Literal["clear-episode-team-seeds-to-solo-explicit-reseed-required"] = (
        "clear-episode-team-seeds-to-solo-explicit-reseed-required"
    )
    exceptions: Literal[
        "bounce-danger-global-effects-and-directed-reactions-not-enemy-filtered"
    ] = "bounce-danger-global-effects-and-directed-reactions-not-enemy-filtered"
    observation: Literal[
        "actor-cyclic-public-team-relation-no-liveness-or-hidden-resources-provisional"
    ] = "actor-cyclic-public-team-relation-no-liveness-or-hidden-resources-provisional"
    enemy_relation_client_verified: Literal[True] = True
    complete_reward_pipeline_implemented: Literal[False] = False
    official_ending_and_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False
