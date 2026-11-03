"""Bounded scripted removal turns; no official replay or learning claims."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    FULL_GAME_RULESET_ID,
    REMOVAL_FIELDS,
    create_development_full_game_batch,
)
from godfield_bot.full_game_removal import FULL_GAME_REMOVAL_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameRemovalSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[15] = 15
    source_kind: Literal["integrated-development-sundry-removal-smoke-v1"] = (
        "integrated-development-sundry-removal-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["broom-soap-large-singleton-empty-pools-scripted-not-full-games"] = (
        "broom-soap-large-singleton-empty-pools-scripted-not-full-games"
    )
    removal_profile_sha256: Literal[
        "0889134e85ed8c838ffef89cb76502b9957f08d12af51063e3442a5394ba9f84"
    ] = FULL_GAME_REMOVAL_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    removal_fields: tuple[str, ...] = REMOVAL_FIELDS
    removal_totals: tuple[Count, ...]
    actions: Count
    completed_turns: Count
    removed_cards: Count
    removal_resolutions: Count
    consumed_cards: Count
    retained_miracle_uses: Literal[0] = 0
    hp_damage: Literal[0] = 0
    mp_spent: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    ready_after_one_turn: Count
    real_terminal_endings: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_sampling_and_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameRemovalSmokeReport:
        expected = tuple((self.batch_size + 5 - i) // 6 for i in range(6))
        a, b, c, d, e, f = expected
        totals = (
            a + c + e,
            b + d + f,
            3 * a + c,
            2 * b + d,
            e + f,
            c + d + e + f,
            7 * a + 4 * b + c + d,
            3 * a + 2 * b,
        )
        if (
            self.scenario_counts != expected
            or self.removal_fields != REMOVAL_FIELDS
            or self.removal_totals != totals
            or self.removed_cards != totals[2] + totals[3]
            or self.actions != 4 * self.batch_size
            or any(
                value != self.batch_size
                for value in (
                    self.completed_turns,
                    self.removal_resolutions,
                    self.consumed_cards,
                    self.original_owner_ticks,
                    self.ready_after_one_turn,
                )
            )
        ):
            raise ValueError("removal smoke scripted accounting differs")
        return self


def run_full_game_removal_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 600,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameRemovalSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("removal smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=10,
        seed=seed,
        max_turns=2,
        max_decisions=8,
        initial_hp=100,
        initial_mp=0,
        initial_cp=0,
    )
    batch = configured.batch
    if configured.metadata.plan.removal.profile_sha256 != FULL_GAME_REMOVAL_SHA256:
        raise ValueError("removal smoke profile differs")
    pools = (
        [(101 + i, model, 0, 0) for i, model in enumerate((191, 192, 193, 194, 195, 196))]
        + [(107 + i, model, 0, 1) for i, model in enumerate((211, 212, 213))]
        + [(110, 4, 0, 0)],
        [(101 + i, model, 0, 1) for i, model in enumerate((211, 212, 213, 214))]
        + [(105, 191, 0, 0), (106, 35, 0, 0), (107, 215, 0, 0)],
        [(101, 208, 0, 0)],
        [(101, 211, 0, 1)],
        [(101, 211, 0, 1), (102, 212, 0, 1)],
        [(101, 191, 0, 0), (102, 35, 0, 0), (103, 211, 0, 0)],
    )
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 6
    for env, scenario in enumerate(scenarios):
        model = 205 if scenario % 2 == 0 else 206
        batch.seed_hand(env, 0, np.asarray([[1, model, 0, 0]], dtype=np.int64))
        batch.seed_hand(env, 1, np.asarray(pools[scenario], dtype=np.int64))
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # Hidden victim inventories are diagnostic snapshots, not policy inputs.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
            batch.actor_hands(),
            batch.player_observations(),
            batch.choice_masks(),
            batch.pending_observations(),
            batch.attack_effect_observations(),
            batch.attack_selection_observations(),
            batch.attack_order(),
            batch.defense_order(),
            batch.removal_snapshot(),
            batch.acquisition_snapshot(),
            batch.counter_observations(),
            batch.counter_snapshot(),
            batch.passive_observations(),
            batch.revival_snapshot(),
        ):
            replay.update(view.astype("<i8", copy=False).tobytes())

    fingerprint()
    for choice in (1, 0, 12, 0):
        episodes = batch.episode_snapshot()
        if not np.all(batch.choice_masks()[:, choice]):
            raise RuntimeError("removal smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (environments, episodes[:, :4], np.full(batch_size, choice, dtype=np.int64))
            )
        )
        fingerprint()
    episodes, states = batch.episode_snapshot(), batch.diagnostic_players()
    if any(
        (
            batch.miracle_use_count,
            batch.hp_damage,
            batch.mp_spent,
            batch.automatic_gift_count,
            int(states[:, 1:, 5].sum()),
            int(np.count_nonzero(episodes[:, 3] == 12)),
        )
    ):
        raise RuntimeError("removal smoke produced an unexpected resource/use/tick/ending")
    return FullGameRemovalSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(6)),
        removal_totals=tuple(int(value) for value in batch.removal_snapshot().sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        removed_cards=batch.removal_count,
        removal_resolutions=batch.removal_effect_count,
        consumed_cards=batch.consumed_count,
        original_owner_ticks=int(states[:, 0, 5].sum()),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
    )
