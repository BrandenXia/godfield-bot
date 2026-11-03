"""Bounded scripted compound utility turns, not full games or learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    COMPOUND_UTILITY_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_compound_utilities import FULL_GAME_COMPOUND_UTILITY_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameCompoundUtilitySmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[11] = 11
    source_kind: Literal["integrated-development-compound-utility-smoke-v1"] = (
        "integrated-development-compound-utility-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["illness-cap-stochastic-self-damage-revival-scripted-not-full-games"] = (
        "illness-cap-stochastic-self-damage-revival-scripted-not-full-games"
    )
    compound_utility_profile_sha256: Literal[
        "144effaeeaaf78e5c8d60b5f6fcef04ce272ec7b6bf6c89a5a9f3f32817ee0f7"
    ] = FULL_GAME_COMPOUND_UTILITY_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    utility_fields: tuple[str, ...] = COMPOUND_UTILITY_FIELDS
    utility_totals: tuple[Count, ...]
    tear_outcome_counts: tuple[tuple[Count, Count], ...]
    actions: Count
    completed_turns: Count
    utilities: Count
    consumed_cards: Count
    utility_hp_damage: Count
    revivals: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    incoming_attack_hp_damage: Literal[0] = 0
    attack_turns: Literal[0] = 0
    retained_miracle_uses: Literal[0] = 0
    mp_spent: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    final_actor_deaths: Count
    ready_after_one_turn: Count
    real_terminal_endings: Count
    limit_truncations: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    probability_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameCompoundUtilitySmokeReport:
        expected = tuple((self.batch_size + 11 - i) // 12 for i in range(12))
        if (
            self.scenario_counts != expected
            or len(self.tear_outcome_counts) != 4
            or any(
                sum(pair) != n
                for pair, n in zip(self.tear_outcome_counts, expected[8:], strict=True)
            )
        ):
            raise ValueError("compound utility smoke scenario or outcome accounting differs")
        h, d = zip(*self.tear_outcome_counts, strict=True)
        herb = sum(expected[:8])
        herb_damage = expected[4] + expected[5]
        tear_damage = 10 * (d[0] + d[1]) + d[2] + d[3]
        totals = (
            herb,
            20 * sum(expected[:6]) + 5 * expected[6],
            expected[6] + expected[7],
            herb,
            herb_damage,
            sum(expected[8:]),
            sum(h),
            10 * (h[0] + h[2] + h[3]),
            sum(d),
            tear_damage,
        )
        revivals = expected[5] + d[3]
        endings = self.final_actor_deaths if self.player_count == 2 else 0
        if (
            self.utility_fields != COMPOUND_UTILITY_FIELDS
            or self.utility_totals != totals
            or self.actions != 2 * self.batch_size
            or self.revivals != revivals
            or self.consumed_cards != self.batch_size + revivals
            or self.utility_hp_damage != herb_damage + tear_damage
            or self.final_actor_deaths > self.batch_size
            or self.real_terminal_endings != endings
            or self.ready_after_one_turn != self.batch_size - endings
            or any(
                value != self.batch_size
                for value in (
                    self.completed_turns,
                    self.utilities,
                    self.original_owner_ticks,
                )
            )
        ):
            raise ValueError("compound utility smoke scripted accounting differs")
        return self


def run_full_game_compound_utility_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 768,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameCompoundUtilitySmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("compound utility smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        capacity=2,
        max_turns=2,
        max_decisions=3,
        initial_hp=100,
        initial_mp=10,
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 12
    for env, scenario in enumerate(scenarios):
        herb = scenario < 8
        stage = int(scenario) if scenario < 5 else (4 if scenario == 5 else 0)
        hp = 1 if scenario in (4, 5, 10, 11) else (100 if scenario == 9 else 40)
        mp = 95 if scenario == 6 else (100 if scenario == 7 else 10)
        batch.seed_players(
            np.asarray([env], dtype=np.int64),
            np.asarray([0], dtype=np.int64),
            np.asarray([[hp, mp, 0, stage]], dtype=np.int64),
            np.asarray([0], dtype=np.int64),
        )
        batch.seed_hand(
            env,
            0,
            np.asarray(
                [
                    [1, 198 if herb else 202, 0, 0],
                    *([[2, 208, 0, 0]] if scenario in (5, 11) else []),
                ],
                dtype=np.int64,
            ),
        )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # Diagnostics fingerprint outcomes only; commands use public phase and masks.
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "utility_selection_observations",
            "compound_utility_snapshot",
            "revival_snapshot",
            "acquisition_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    fingerprint()
    for choice in (1, 0):
        if not batch.choice_masks()[:, choice].all():
            raise RuntimeError("compound utility smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (
                    environments,
                    batch.episode_snapshot()[:, :4],
                    np.full(batch_size, choice, dtype=np.int64),
                )
            )
        )
        fingerprint()
    stats, episodes, states = (
        batch.compound_utility_snapshot(),
        batch.episode_snapshot(),
        batch.diagnostic_players(),
    )
    if any(
        (
            batch.hp_damage,
            batch.attack_count,
            batch.miracle_use_count,
            batch.mp_spent,
            batch.automatic_gift_count,
            int(states[:, 1:, 5].sum()),
            int(np.count_nonzero(episodes[:, 3] == 13)),
        )
    ):
        raise RuntimeError(
            "compound utility smoke produced an unexpected attack, gift, tick or limit"
        )
    return FullGameCompoundUtilitySmokeReport(
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
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(12)),
        utility_totals=tuple(int(value) for value in stats.sum(axis=0)),
        tear_outcome_counts=tuple(
            (
                int(stats[scenarios == i, 6].sum()),
                int(stats[scenarios == i, 8].sum()),
            )
            for i in range(8, 12)
        ),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        utilities=batch.utility_count,
        consumed_cards=batch.consumed_count,
        utility_hp_damage=batch.utility_hp_damage,
        revivals=batch.revival_count,
        original_owner_ticks=int(states[:, 0, 5].sum()),
        final_actor_deaths=int(np.count_nonzero(states[:, 0, 0] == 0)),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
        real_terminal_endings=int(np.count_nonzero(episodes[:, 3] == 12)),
    )
