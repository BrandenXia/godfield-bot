"""Complete native startup draw probe, NOT gameplay, learning or strength evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch
from godfield_bot.full_game_acquisition import FULL_GAME_GIFT_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]
Positive = Annotated[int, Field(ge=1, strict=True)]


class FullGameAcquisitionSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[3] = 3
    source_kind: Literal["integrated-development-all-held-acquisition-smoke-v3"] = (
        "integrated-development-all-held-acquisition-smoke-v3"
    )
    ruleset_id: Literal["integrated-full-game-development-v5"] = FULL_GAME_RULESET_ID
    scenario: Literal["native-nine-per-seat-complete-pool-startup-not-gameplay"] = (
        "native-nine-per-seat-complete-pool-startup-not-gameplay"
    )
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gift_profile_sha256: Literal[
        "70905153bedfb92f216afc791132e0bc190f457245e59e4a563256297551b182"
    ] = FULL_GAME_GIFT_SHA256
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    initial_cards_per_seat: Literal[9] = 9
    local_hand_limit: Literal[18] = 18
    overflow_policy: Literal["oldest-held-provisional"] = "oldest-held-provisional"
    giftable_models: Literal[237] = 237
    integrated_effect_models: Literal[154] = 154
    giftable_without_integrated_effect: Literal[83] = 83
    total_weight: Literal[500] = 500
    model_distribution: tuple[tuple[Positive, Positive, Count], ...]
    observed_model_count: int = Field(ge=1, le=237, strict=True)
    automatic_gifts: Positive
    unsupported_effect_draws: Count
    initial_actors_without_implemented_choice: Count
    accepted_commands: Literal[0] = 0
    games_completed: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_draw_accounting(self) -> FullGameAcquisitionSmokeReport:
        weights = tuple((model, weight) for model, weight, _ in self.model_distribution)
        weights_sha = hashlib.sha256(
            json.dumps(weights, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            weights_sha != self.gift_profile_sha256
            or len(self.model_distribution) != 237
            or self.automatic_gifts != self.batch_size * self.player_count * 9
            or sum(count for _, _, count in self.model_distribution) != self.automatic_gifts
            or sum(count > 0 for _, _, count in self.model_distribution)
            != self.observed_model_count
            or self.unsupported_effect_draws > self.automatic_gifts
            or self.initial_actors_without_implemented_choice > self.batch_size
        ):
            raise ValueError("full-game acquisition probe weights or draw accounting differs")
        return self


def run_full_game_acquisition_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 9,
    seed: int = 67,
) -> FullGameAcquisitionSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("acquisition smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        acquisition_mode="all-held-weighted",
    )
    batch = configured.batch
    batch.start_environments(np.arange(batch_size, dtype=np.int64))
    plan = configured.metadata.plan
    # True inventory is used only for diagnostic counts, never to select actions.
    inventory = batch.diagnostic_inventory()
    model_ids, counts = np.unique(inventory[:, :, :9, 1], return_counts=True)
    histogram = {int(model): int(count) for model, count in zip(model_ids, counts, strict=True)}
    supported = (
        {row[0] for row in plan.effect_profiles}
        | {row[0] for row in plan.combat.attack_profiles}
        | {row[0] for row in plan.combat.armor_profiles}
        | {row[0] for row in plan.combat.boost_profiles}
        | {row[0] for row in plan.combat.special_profiles}
    )
    if len(supported) != 154 or not histogram.keys() <= dict(plan.gifts.model_weights).keys():
        raise RuntimeError("acquisition smoke native inventory or integrated effect scope differs")
    digest = hashlib.sha256()
    for view in (
        batch.episode_snapshot(),
        batch.diagnostic_players(),
        inventory,
        batch.actor_hands(),
        batch.player_observations(),
        batch.choice_masks(),
        batch.acquisition_snapshot(),
    ):
        digest.update(view.astype("<i8", copy=False).tobytes())
    metadata_sha = hashlib.sha256(
        json.dumps(
            configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return FullGameAcquisitionSmokeReport(
        metadata_sha256=metadata_sha,
        diagnostic_replay_sha256=digest.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        model_distribution=tuple(
            (model, weight, histogram.get(model, 0)) for model, weight in plan.gifts.model_weights
        ),
        observed_model_count=len(histogram),
        automatic_gifts=batch.automatic_gift_count,
        unsupported_effect_draws=sum(
            count for model, count in histogram.items() if model not in supported
        ),
        initial_actors_without_implemented_choice=int(
            np.count_nonzero(~np.any(batch.choice_masks(), axis=1))
        ),
    )
