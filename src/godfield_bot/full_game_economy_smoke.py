"""Bounded CP utility checks, not trading, full matches or a learning dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    CP_UTILITY_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_economy import FULL_GAME_ECONOMY_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameEconomySmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[14] = 14
    source_kind: Literal["integrated-development-cp-utility-smoke-v1"] = (
        "integrated-development-cp-utility-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v31"] = FULL_GAME_RULESET_ID
    scenario: Literal["fresh-capped-full-poor-reused-disguised-utility-scripted-not-full-games"] = (
        "fresh-capped-full-poor-reused-disguised-utility-scripted-not-full-games"
    )
    economy_profile_sha256: Literal[
        "efc35968f55a511a7c573d015572addddeb3a659f923f82179d1c98212de1918"
    ] = FULL_GAME_ECONOMY_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    cp_utility_fields: tuple[str, ...] = CP_UTILITY_FIELDS
    cp_utility_totals: tuple[Count, ...]
    actions: Count
    completed_turns: Count
    utilities: Count
    passes: Count
    retained_miracle_uses: Count
    consumed_cards: Literal[0] = 0
    utility_cp_gain: Count
    mp_spent: Count
    hp_damage: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    ready_after_one_turn: Count
    real_terminal_endings: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_credit_cap_and_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameEconomySmokeReport:
        expected = tuple((self.batch_size + 6 - i) // 7 for i in range(7))
        a, b, c, d, e, f, g = expected
        cp_uses = a + b + e + f
        totals = (cp_uses, 10 * a + 5 * b + 10 * e, 5 * cp_uses, b + f)
        if (
            self.scenario_counts != expected
            or self.cp_utility_fields != CP_UTILITY_FIELDS
            or self.cp_utility_totals != totals
            or self.utilities != cp_uses + g
            or self.retained_miracle_uses != self.utilities
            or self.passes != c + d
            or self.utility_cp_gain != totals[1]
            or self.mp_spent != totals[2] + 7 * g
            or any(
                value != self.batch_size
                for value in (
                    self.completed_turns,
                    self.original_owner_ticks,
                    self.ready_after_one_turn,
                )
            )
            or self.actions != self.batch_size + self.utilities
        ):
            raise ValueError("CP utility smoke scripted accounting differs")
        return self


def run_full_game_economy_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 700,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameEconomySmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("CP utility smoke batch size must be 1 through 4096")
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
        initial_hp=40,
        initial_mp=10,
        initial_cp=0,
    )
    batch = configured.batch
    # MP, CP, actual model, display model, used. Setup is trusted, not policy input.
    cases = (
        (10, 0, 236, 0, 0),
        (5, 95, 236, 0, 0),
        (10, 100, 236, 0, 0),
        (4, 0, 236, 0, 0),
        (10, 30, 236, 0, 1),
        (10, 100, 236, 235, 0),
        (10, 0, 235, 236, 0),
    )
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % len(cases)
    for env, scenario in enumerate(scenarios):
        mp, cp, model, display, used = cases[scenario]
        batch.seed_players(
            np.asarray([env], dtype=np.int64),
            np.asarray([0], dtype=np.int64),
            np.asarray([[40, mp, cp, 0]], dtype=np.int64),
            np.asarray([0], dtype=np.int64),
        )
        batch.seed_hand(
            env, 0, np.asarray([[1, model, display, used], [2, 191, 0, 0]], dtype=np.int64)
        )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
            batch.actor_hands(),
            batch.player_observations(),
            batch.choice_masks(),
            batch.cp_utility_snapshot(),
            batch.acquisition_snapshot(),
            batch.revival_snapshot(),
            batch.utility_selection_observations(),
            batch.cost_snapshot(),
        ):
            replay.update(view.astype("<i8", copy=False).tobytes())

    fingerprint()
    # Displayed legal slot and public own MP only, never actual identity.
    choices = (batch.choice_masks()[:, 1] & (batch.player_observations()[:, 0, 4] >= 5)).astype(
        np.int64
    )
    expected_choices = ~np.isin(scenarios, (2, 3))
    if not np.array_equal(choices, expected_choices.astype(np.int64)):
        raise RuntimeError("CP utility smoke expected displayed legal choices differ")
    batch.step(np.column_stack((environments, batch.episode_snapshot()[:, :4], choices)))
    fingerprint()
    selected = np.flatnonzero(batch.episode_snapshot()[:, 3] == 2)
    if not np.all(batch.choice_masks()[selected, 0]):
        raise RuntimeError("CP utility smoke expected confirmation is unavailable")
    batch.step(
        np.column_stack(
            (
                selected,
                batch.episode_snapshot()[selected, :4],
                np.zeros(len(selected), dtype=np.int64),
            )
        )
    )
    fingerprint()
    episodes, states = batch.episode_snapshot(), batch.diagnostic_players()
    if any(
        (
            batch.consumed_count,
            batch.hp_damage,
            batch.automatic_gift_count,
            int(states[:, 1:, 5].sum()),
            int(np.count_nonzero(episodes[:, 3] == 12)),
        )
    ):
        raise RuntimeError("CP utility smoke produced unexpected consumption, damage or ending")
    return FullGameEconomySmokeReport(
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
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(7)),
        cp_utility_totals=tuple(int(value) for value in batch.cp_utility_snapshot().sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        utilities=batch.utility_count,
        passes=batch.pass_count,
        retained_miracle_uses=batch.miracle_use_count,
        utility_cp_gain=batch.utility_cp_gain,
        mp_spent=batch.mp_spent,
        original_owner_ticks=int(states[:, 0, 5].sum()),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
    )
