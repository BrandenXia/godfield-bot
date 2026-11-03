"""Scripted Sell/Buy custody/payment turns, not full games or learning evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch
from godfield_bot.full_game_trade import MARKET_STATS

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameMarketSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[1] = 1
    source_kind: Literal["scripted-sell-buy-custody-current-source-payment-v1"] = (
        "scripted-sell-buy-custody-current-source-payment-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v33"] = FULL_GAME_RULESET_ID
    trade_choice_schema_version: Literal[2] = 2
    queue_schema_version: Literal[8] = 8
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    statistic_fields: tuple[str, ...] = MARKET_STATS
    statistic_totals: tuple[Count, ...]
    commands: Count
    original_owner_ticks: Count
    sun_revivals: Count
    bow_shots: Count
    attack_hp_damage: Count
    consumed_cards: Count
    pending_families: Literal[0] = 0
    escrow_remaining: Literal[0] = 0
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
    def accounting(self) -> FullGameMarketSmokeReport:
        n, s = self.scenario_counts, self.statistic_totals
        if (
            n != tuple((self.batch_size + 9 - i) // 10 for i in range(10))
            or self.statistic_fields != MARKET_STATS
            or len(s) != 25
        ):
            raise ValueError("market smoke layout differs")
        sells, buys = sum(n[:5]), sum(n[5:])
        mirrors, purchases, offers = n[2] + n[8], n[5] + n[8] + n[9], n[5] + n[6] + n[8] + n[9]
        cp, mp = (
            5 * (n[0] + n[2] + n[5] + n[8]) + 2 * n[1],
            5 * (n[0] + n[2] + n[5] + n[8]) + 3 * n[1],
        )
        hp, unpaid = 5 * n[1] + n[3] + n[4] + n[9], 9 * (n[3] + n[4] + n[9])
        credit = 10 * (sells + purchases)
        expected = (
            sells,
            buys,
            sells,
            sells,
            buys,
            0,
            mirrors,
            0,
            sells,
            offers,
            n[7],
            purchases,
            n[6],
            sells + purchases,
            n[6],
            cp,
            mp,
            hp,
            unpaid,
            credit,
            0,
            offers,
            0,
            0,
            0,
        )
        shots = n[4] * (self.player_count - 1)
        if (
            s != expected
            or self.original_owner_ticks != self.batch_size
            or self.sun_revivals != n[3] + n[9]
            or self.bow_shots != shots
            or self.attack_hp_damage != 30 * shots
            or self.consumed_cards != self.batch_size + mirrors + n[3] + n[9] + n[4]
            or self.commands != 5 * sells + 2 * mirrors + 4 * (buys - n[7]) + 3 * n[7] + shots
        ):
            raise ValueError("market smoke accounting differs")
        return self


def run_full_game_market_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameMarketSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("market smoke batch size must be 1 through 4096")
    c = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=64,
        initial_hp=50,
        initial_mp=20,
        initial_cp=5,
    )
    if {m: p for m, _, p in c.metadata.plan.trade.price_profiles if m in (7, 112, 208)} != {
        7: 10,
        112: 10,
        208: 10,
    }:
        raise RuntimeError("market smoke fixture prices differ from pinned source")
    b, scenarios = c.batch, np.arange(batch_size) % 10
    for env in range(batch_size):
        scenario = int(scenarios[env])
        attacker = (
            [4, 208]
            if scenario == 3
            else [4, 112]
            if scenario == 4
            else [4, 7]
            if scenario < 5
            else [5, 7]
            if scenario == 8
            else [5]
        )
        defender = (
            [190, 6]
            if scenario in (2, 8)
            else [237]
            if scenario == 7
            else [208]
            if scenario == 9
            else [7]
            if scenario in (5, 6)
            else []
        )
        for owner, cards in ((0, attacker), (1, defender)):
            b.seed_hand(
                env,
                owner,
                np.asarray(
                    [
                        [owner * 100 + i + 1, m, 0, int(scenario == 7 and m == 237)]
                        for i, m in enumerate(cards)
                    ],
                    dtype=np.int64,
                ).reshape(-1, 4),
            )
    envs = np.repeat(np.arange(batch_size, dtype=np.int64), player_count)
    owners = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    resources = np.tile(np.asarray([50, 20, 5, 0], dtype=np.int64), (len(envs), 1))
    resources[(owners == 1) & (scenarios[envs] == 1), :3] = (50, 3, 2)
    resources[
        ((owners == 1) & np.isin(scenarios[envs], (3, 4)))
        | ((owners == 0) & (scenarios[envs] == 9)),
        :3,
    ] = (1, 0, 0)
    b.seed_players(envs, owners, resources, np.full(len(envs), 8, dtype=np.int64))
    b.start_environments(np.arange(batch_size, dtype=np.int64))
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "market_observations",
            "market_snapshot",
            "market_escrow_snapshot",
            "trade_observations",
            "attack_family_snapshot",
            "revival_snapshot",
        ):
            replay.update(getattr(b, name)().astype("<i8", copy=False).tobytes())

    fingerprint()
    for _ in range(32):
        episodes = b.episode_snapshot()
        active = np.flatnonzero(
            (episodes[:, 3] < 12) & ((episodes[:, 4] == 0) | (episodes[:, 3] == 4))
        )
        if not len(active):
            break
        masks, market, trade = b.choice_masks(), b.market_observations(), b.trade_observations()
        selected = b.selected_defenses()
        choices = []
        for active_env in active:
            env = int(active_env)
            phase = int(episodes[env, 3])
            if phase == 1:
                choice = 1
            elif phase == 3:
                choice = 20
            elif phase == 6 and trade[env, 1] == 2:
                choice = 2 if market[env, 5] == 0 else 0
            elif phase == 6 and trade[env, 1] == 3:
                choice = int(scenarios[env] != 6)
            elif phase == 4:
                mirror = (
                    scenarios[env] in (2, 8)
                    and market[env, 0]
                    and market[env, 3:5].tolist() == [0, 1]
                )
                choice = 1 if mirror and not selected[env].any() else 0
            else:
                raise RuntimeError("market smoke encountered unexpected public phase")
            if not masks[env, choice]:
                raise RuntimeError("market smoke selected an unavailable public action")
            choices.append(choice)
        b.step(np.column_stack((active, episodes[active, :4], np.asarray(choices, dtype=np.int64))))
        fingerprint()
    else:
        raise RuntimeError("market smoke exceeded bounded first-turn commands")
    players = b.diagnostic_players()
    if (
        np.any(b.episode_snapshot()[:, 4] != 1)
        or np.any(b.episode_snapshot()[:, 3] == 13)
        or b.attack_family_snapshot()[:, 13:].any()
        or b.market_escrow_snapshot().any()
        or b.market_observations().any()
        or players[:, 1:, 5].any()
    ):
        raise RuntimeError("market smoke did not drain custody/reactions with exactly one tick")
    return FullGameMarketSmokeReport(
        metadata_sha256=hashlib.sha256(c.metadata.model_dump_json().encode()).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(10)),
        statistic_totals=tuple(int(v) for v in b.market_snapshot().sum(axis=0)),
        commands=b.action_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        sun_revivals=b.revival_count,
        bow_shots=int(b.attack_family_snapshot()[:, 8].sum()),
        attack_hp_damage=b.hp_damage,
        consumed_cards=b.consumed_count,
    )
