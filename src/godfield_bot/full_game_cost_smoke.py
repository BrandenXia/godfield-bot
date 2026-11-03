"""Scripted adjacent-cost turns, not full matches or learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    COST_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_costs import FULL_GAME_COST_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameCostSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[13] = 13
    source_kind: Literal["integrated-development-adjacent-cost-waiver-smoke-v1"] = (
        "integrated-development-adjacent-cost-waiver-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v33"] = FULL_GAME_RULESET_ID
    scenario: Literal["five-reducers-utility-attack-defense-zero-mp-scripted-not-full-games"] = (
        "five-reducers-utility-attack-defense-zero-mp-scripted-not-full-games"
    )
    cost_profile_sha256: Literal[
        "d880c010d37efd2d2d3d81d1e4830286a236dfdf40c417526b527f867544d2a0"
    ] = FULL_GAME_COST_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    cost_fields: tuple[str, ...] = COST_FIELDS
    cost_totals: tuple[Count, ...]
    actions: Count
    completed_turns: Count
    utility_turns: Count
    attack_turns: Count
    defense_waiver_turns: Count
    waived_mp: Count
    cost_waivers: Count
    mp_spent: Literal[0] = 0
    utility_cp_gain: Count
    consumed_cards: Count
    retained_miracle_uses: Count
    hp_damage: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    ready_after_one_turn: Count
    real_terminal_endings: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameCostSmokeReport:
        expected = tuple((self.batch_size + 14 - i) // 15 for i in range(15))
        utility, attack, defense = (sum(expected[i : i + 5]) for i in (0, 5, 10))
        saved = 5 * (utility + attack) + 6 * defense
        if (
            self.scenario_counts != expected
            or self.cost_fields != COST_FIELDS
            or self.cost_totals != (self.batch_size, saved, utility, attack, defense)
            or (self.utility_turns, self.attack_turns, self.defense_waiver_turns)
            != (utility, attack, defense)
            or self.waived_mp != saved
            or self.actions != 3 * utility + 5 * attack + 6 * defense
            or self.utility_cp_gain != 10 * utility
            or self.consumed_cards != self.batch_size + defense
            or self.hp_damage != 10 * attack
            or any(
                value != self.batch_size
                for value in (
                    self.completed_turns,
                    self.cost_waivers,
                    self.original_owner_ticks,
                    self.retained_miracle_uses,
                    self.ready_after_one_turn,
                )
            )
        ):
            raise ValueError("cost smoke scripted accounting differs")
        return self


def run_full_game_cost_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 600,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameCostSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("cost smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=3,
        seed=seed,
        max_turns=2,
        max_decisions=8,
        initial_hp=100,
        initial_mp=0,
        initial_cp=0,
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 15
    families = scenarios // 5
    reducers = [row[0] for row in configured.metadata.plan.costs.profiles]
    for env, scenario in enumerate(scenarios):
        family, reducer = scenario // 5, reducers[scenario % 5]
        if family == 2:
            batch.seed_hand(env, 0, np.asarray([[1, 35, 0, 0]], dtype=np.int64))
            batch.seed_hand(
                env, 1, np.asarray([[101, 233, 0, 0], [102, reducer, 0, 0]], dtype=np.int64)
            )
        else:
            model = 236 if family == 0 else 215
            batch.seed_hand(
                env, 0, np.asarray([[1, model, 0, 0], [2, reducer, 0, 0]], dtype=np.int64)
            )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # Hidden diagnostic inventories only fingerprint state; decisions read legal masks.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
            batch.actor_hands(),
            batch.player_observations(),
            batch.choice_masks(),
            batch.pending_observations(),
            batch.attack_selection_observations(),
            batch.utility_selection_observations(),
            batch.attack_order(),
            batch.defense_order(),
            batch.special_defense_observations(),
            batch.cost_snapshot(),
            batch.cp_utility_snapshot(),
            batch.revival_snapshot(),
            batch.acquisition_snapshot(),
        ):
            replay.update(view.astype("<i8", copy=False).tobytes())

    def step(indices: np.ndarray, choice: int) -> None:
        if not len(indices):
            return
        if not np.all(batch.choice_masks()[indices, choice]):
            raise RuntimeError("cost smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (
                    indices,
                    batch.episode_snapshot()[indices, :4],
                    np.full(len(indices), choice, dtype=np.int64),
                )
            )
        )
        fingerprint()

    fingerprint()
    step(environments, 1)
    step(environments[families < 2], 2)
    step(environments, 0)
    step(environments[families > 0], 5)
    step(environments[families == 2], 1)
    step(environments[families == 2], 2)
    step(environments[families > 0], 0)
    episodes, states = batch.episode_snapshot(), batch.diagnostic_players()
    if any(
        (
            batch.mp_spent,
            batch.automatic_gift_count,
            int(states[:, 1:, 5].sum()),
            int(np.count_nonzero(episodes[:, 3] == 12)),
        )
    ):
        raise RuntimeError("cost smoke produced unexpected spending, gift, tick or ending")
    counts = tuple(int(np.count_nonzero(scenarios == i)) for i in range(15))
    return FullGameCostSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=counts,
        cost_totals=tuple(int(value) for value in batch.cost_snapshot().sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        utility_turns=batch.utility_count,
        attack_turns=int(np.count_nonzero(families == 1)),
        defense_waiver_turns=int(np.count_nonzero(families == 2)),
        waived_mp=batch.waived_mp,
        cost_waivers=batch.cost_waiver_count,
        utility_cp_gain=batch.utility_cp_gain,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
        hp_damage=batch.hp_damage,
        original_owner_ticks=int(states[:, 0, 5].sum()),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
    )
