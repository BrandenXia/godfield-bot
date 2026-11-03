"""Scripted Exchange amounts and zero-HP reactions, never full-match evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch
from godfield_bot.full_game_trade import TRADE_STATS

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameExchangeSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[2] = 2
    source_kind: Literal["scripted-exchange-amounts-and-zero-hp-v1"] = (
        "scripted-exchange-amounts-and-zero-hp-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v33"] = FULL_GAME_RULESET_ID
    trade_choice_schema_version: Literal[2] = 2
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    statistic_fields: tuple[str, ...] = TRADE_STATS
    statistic_totals: tuple[Count, ...]
    commands: Count
    original_owner_ticks: Count
    sun_revivals: Count
    bow_shots: Count
    attack_hp_damage: Count
    consumed_cards: Count
    pending_families: Literal[0] = 0
    other_owner_ticks: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    full_games_completed: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameExchangeSmokeReport:
        n, s = self.scenario_counts, self.statistic_totals
        if (
            n != tuple((self.batch_size + 9 - i) // 10 for i in range(10))
            or self.statistic_fields != TRADE_STATS
            or len(s) != 10
            or s[:4] != (self.batch_size, self.batch_size, 0, self.batch_size)
            or s[4:]
            != (
                10 * n[0] + n[1] + n[8] + n[9],
                n[2] + 10 * n[3],
                10 * n[4] + n[5],
                n[6] + 5 * n[7],
                0,
                0,
            )
            or self.sun_revivals != n[8]
            or self.bow_shots != n[9] * (self.player_count - 1)
            or self.attack_hp_damage != 30 * self.bow_shots
            or self.consumed_cards != self.batch_size + n[8] + n[9]
            or self.commands != 3 * self.batch_size + self.bow_shots
            or self.original_owner_ticks != self.batch_size
        ):
            raise ValueError("Exchange smoke accounting differs")
        return self


def run_full_game_exchange_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameExchangeSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("Exchange smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=32,
        initial_hp=50,
        initial_mp=20,
        initial_cp=5,
    )
    b = configured.batch
    scenarios = np.arange(batch_size) % 10
    for env in range(batch_size):
        scenario = int(scenarios[env])
        cards = [3, 208] if scenario == 8 else [3, 112] if scenario == 9 else [3]
        b.seed_hand(
            env, 0, np.asarray([[i + 1, m, 0, 0] for i, m in enumerate(cards)], dtype=np.int64)
        )
    envs = np.repeat(np.arange(batch_size, dtype=np.int64), player_count)
    owners = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    resources = np.tile(np.asarray([50, 20, 5, 0], dtype=np.int64), (len(envs), 1))
    special = (owners == 0) & (scenarios[envs] >= 8)
    resources[special, :3] = (1, 0, 0)
    b.seed_players(envs, owners, resources, np.full(len(envs), 8, dtype=np.int64))
    b.start_environments(np.arange(batch_size, dtype=np.int64))
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "trade_observations",
            "trade_snapshot",
            "revival_snapshot",
            "attack_family_snapshot",
        ):
            replay.update(getattr(b, name)().astype("<i8", copy=False).tobytes())

    def advance(active: npt.NDArray[np.int64], choices: npt.NDArray[np.int64]) -> None:
        episodes = b.episode_snapshot()
        b.step(np.column_stack((active, episodes[active, :4], choices)).astype(np.int64))
        fingerprint()

    all_envs = np.arange(batch_size, dtype=np.int64)
    fingerprint()
    advance(all_envs, np.ones(batch_size, dtype=np.int64))
    advance(all_envs, np.where(scenarios < 8, scenarios + 1, 2))
    # No actual wallet/card/HP-zero reaction is applied until final confirmation.
    if b.consumed_count or b.revival_count or b.attack_family_snapshot().any():
        raise RuntimeError("Exchange probe applied an uncommitted preview")
    advance(all_envs, np.zeros(batch_size, dtype=np.int64))
    for _ in range(player_count - 1):
        active = np.flatnonzero(b.episode_snapshot()[:, 3] == 4)
        if not len(active):
            break
        advance(active, np.zeros(len(active), dtype=np.int64))
    players = b.diagnostic_players()
    if (
        np.any(b.episode_snapshot()[:, 4] != 1)
        or np.any(b.episode_snapshot()[:, 3] == 13)
        or b.attack_family_snapshot()[:, 13:].any()
        or b.trade_observations().any()
        or players[:, 1:, 5].any()
    ):
        raise RuntimeError("Exchange probe single-turn queue accounting differs")
    return FullGameExchangeSmokeReport(
        metadata_sha256=hashlib.sha256(configured.metadata.model_dump_json().encode()).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(10)),
        statistic_totals=tuple(int(v) for v in b.trade_snapshot().sum(axis=0)),
        commands=b.action_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        sun_revivals=b.revival_count,
        bow_shots=int(b.attack_family_snapshot()[:, 8].sum()),
        attack_hp_damage=b.hp_damage,
        consumed_cards=b.consumed_count,
    )
