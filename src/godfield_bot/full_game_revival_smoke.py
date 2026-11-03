"""Scripted native HP-edge diagnostics, not full games or training evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch
from godfield_bot.full_game_passives import FULL_GAME_PASSIVE_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameRevivalSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[16] = 16
    source_kind: Literal["integrated-development-passive-revival-smoke-v2"] = (
        "integrated-development-passive-revival-smoke-v2"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["scripted-hp-zero-edges-native-illness-tickets-not-full-games"] = (
        "scripted-hp-zero-edges-native-illness-tickets-not-full-games"
    )
    passive_profile_sha256: Literal[
        "108e08cd030d7b3bbde6f6ec4b1bce640aef17ee2a1bc7086c6fe5623b1e70ba"
    ] = FULL_GAME_PASSIVE_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, Count, Count, Count, Count]
    cause_fields: tuple[str, ...] = (
        "attack",
        "infliction",
        "payment",
        "periodic",
        "worsening",
        "utility",
    )
    cause_counts: tuple[Count, Count, Count, Count, Count, Count]
    revivals: Count
    hp_granted: Count
    actions: Count
    completed_turns: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    counter_resolutions: Count
    final_queued_counters: Literal[0] = 0
    consumed_cards: Count
    retained_miracle_uses: Count
    ready_after_one_turn: Count
    real_terminal_endings: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameRevivalSmokeReport:
        attack, infliction, payment, periodic, worsening = self.scenario_counts
        if (
            self.cause_fields
            != ("attack", "infliction", "payment", "periodic", "worsening", "utility")
            or self.scenario_counts != tuple((self.batch_size + 4 - i) // 5 for i in range(5))
            or self.cause_counts[:4] != self.scenario_counts[:4]
            or self.cause_counts[4] > worsening
            or self.cause_counts[5] != 0
            or self.revivals != sum(self.cause_counts)
            or self.hp_granted != 10 * self.revivals
            or self.actions != 4 * (attack + infliction) + 6 * payment + periodic + worsening
            or self.consumed_cards != attack + 2 * payment + self.revivals
            or self.retained_miracle_uses != infliction
            or self.counter_resolutions != payment
            or any(
                value != self.batch_size
                for value in (
                    self.completed_turns,
                    self.original_owner_ticks,
                    self.ready_after_one_turn,
                )
            )
        ):
            raise ValueError("passive revival smoke scripted accounting differs")
        return self


def run_full_game_revival_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 500,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameRevivalSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("revival smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=2,
        seed=seed,
        max_turns=2,
        max_decisions=8,
        initial_hp=100,
        initial_mp=30,
        initial_cp=3,
    )
    batch = configured.batch
    if configured.metadata.plan.passives.profile_sha256 != FULL_GAME_PASSIVE_SHA256:
        raise ValueError("revival smoke passive profile differs")
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 5
    for env, scenario in enumerate(scenarios):
        if scenario < 3:
            batch.seed_hand(
                env,
                0,
                np.asarray(
                    [[1, 219 if scenario == 1 else 35, 0, 0]]
                    + ([[2, 208, 0, 0]] if scenario == 2 else []),
                    dtype=np.int64,
                ),
            )
            batch.seed_hand(
                env,
                1,
                np.asarray(
                    [[101, 188 if scenario == 2 else 208, 0, 0]],
                    dtype=np.int64,
                ),
            )
        else:
            batch.seed_hand(env, 0, np.asarray([[1, 208, 0, 0]], dtype=np.int64))
        owner = 1 if scenario < 2 else 0
        state = ([5, 30, 3, 0], [5, 30, 3, 4], [4, 0, 0, 0], [1, 30, 3, 1], [6, 30, 3, 4])[scenario]
        batch.seed_players(
            np.asarray([env], dtype=np.int64),
            np.asarray([owner], dtype=np.int64),
            np.asarray([state], dtype=np.int64),
            np.asarray([0], dtype=np.int64),
        )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # Complete hidden snapshots are diagnostics only, never choose actions.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
            batch.actor_hands(),
            batch.player_observations(),
            batch.choice_masks(),
            batch.pending_observations(),
            batch.passive_observations(),
            batch.revival_snapshot(),
            batch.counter_observations(),
            batch.counter_snapshot(),
            batch.acquisition_snapshot(),
            batch.attack_effect_snapshot(),
            batch.chance_snapshot(),
            batch.defense_order(),
        ):
            replay.update(view.astype("<i8", copy=False).tobytes())

    def step(indices: np.ndarray, choice: int) -> None:
        if len(indices) == 0:
            return
        episodes = batch.episode_snapshot()
        if not np.all(batch.choice_masks()[indices, choice]):
            raise RuntimeError("revival smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (indices, episodes[indices, :4], np.full(len(indices), choice, dtype=np.int64))
            )
        )
        fingerprint()

    fingerprint()
    step(environments[scenarios >= 3], 0)
    attack_envs = environments[scenarios < 3]
    for choice in (1, 0, 4):
        step(attack_envs, choice)
    payment_envs = environments[scenarios == 2]
    step(payment_envs, 1)
    step(attack_envs, 0)
    step(payment_envs, 0)
    episodes, states = batch.episode_snapshot(), batch.diagnostic_players()
    if any(
        (
            int(states[:, 1:, 5].sum()),
            int(batch.counter_snapshot()[:, 11].sum()),
            int(np.count_nonzero(episodes[:, 3] == 12)),
        )
    ):
        raise RuntimeError("revival smoke produced an unexpected tick, queued counter or ending")
    counts = [int(np.count_nonzero(scenarios == i)) for i in range(5)]
    causes = [int(value) for value in batch.revival_snapshot()[:, 2:].sum(axis=0)]
    return FullGameRevivalSmokeReport(
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
        scenario_counts=(counts[0], counts[1], counts[2], counts[3], counts[4]),
        cause_counts=(causes[0], causes[1], causes[2], causes[3], causes[4], causes[5]),
        revivals=batch.revival_count,
        hp_granted=batch.revived_hp,
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        original_owner_ticks=int(states[:, 0, 5].sum()),
        counter_resolutions=batch.resolved_counter_count,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
    )
