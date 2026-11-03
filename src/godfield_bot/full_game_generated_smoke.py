"""Weighted guardian direct/fallback first turns, not full-game training evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch
from godfield_bot.full_game_guardians import (
    GUARDIAN_ACTION_PROFILES,
    GUARDIAN_GENERATED_STATS,
)

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameGeneratedSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[2] = 2
    source_kind: Literal["scripted-generated-direct-and-virtual-fallback-v2"] = (
        "scripted-generated-direct-and-virtual-fallback-v2"
    )
    ruleset_id: Literal["integrated-full-game-development-v31"] = FULL_GAME_RULESET_ID
    guardian_kind: Literal["earth", "moon", "mixed"]
    queue_schema_version: Literal[8] = 8
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    model_count_ids: tuple[int, ...] = tuple(range(3, 240))
    model_counts: tuple[Count, ...]
    execution_counts: tuple[Count, ...]
    observed_models: Count
    statistic_fields: tuple[str, ...] = GUARDIAN_GENERATED_STATS
    statistic_totals: tuple[Count, ...]
    commands: Count
    response_commands: Count
    sun_revivals: Count
    attack_hp_damage: Count
    utility_hp_damage: Count
    automatic_danger_resolutions: Count
    phenomenon_responses: Count
    phenomenon_attack_hp_damage: Count
    original_owner_ticks: Count
    pending_families: Literal[0] = 0
    other_owner_ticks: Literal[0] = 0
    consumed_cards: Count
    mp_spent: Count
    automatic_gifts: Literal[0] = 0
    miracle_uses: Literal[0] = 0
    original_attacks: Literal[0] = 0
    full_games_completed: Literal[0] = 0
    all_generated_outcomes_exercised: Literal[False] = False
    official_sampling_verified: Literal[False] = False
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameGeneratedSmokeReport:
        n, s = self.model_counts, self.statistic_totals
        if (
            self.model_count_ids != tuple(range(3, 240))
            or len(n) != 237
            or self.execution_counts != n
            or self.statistic_fields != GUARDIAN_GENERATED_STATS
            or len(s) != 23
        ):
            raise ValueError("generated guardian smoke layout differs")
        routes = tuple(
            sum(n[model - 3] for model, route in GUARDIAN_ACTION_PROFILES if route == kind)
            for kind in range(1, 8)
        )
        entries = (
            routes[0] + routes[5] + routes[6] + n[14 - 3] + n[232 - 3] * (self.player_count - 2)
        )
        if (
            s[0] != sum(n[:207])
            or s[7] != sum(n[207:])
            or s[1] != sum(n)
            or s[8:15] != routes
            or s[2] != s[13]
            or s[3] > s[2]
            or any(s[i] for i in (4, 5, 6, 17, 22))
            or s[15] != entries
            or s[15] != s[16]
            or s[19] > s[16]
            or s[20] != self.mp_spent
            or s[20] != 20 * n[58 - 3]
            or s[21] != s[11]
            or s[18] + self.phenomenon_attack_hp_damage != self.attack_hp_damage
            or s[1] > self.batch_size
            or self.consumed_cards != self.sun_revivals
            or (self.guardian_kind == "earth" and s[7] != 0)
            or (self.guardian_kind == "moon" and s[0] != 0)
            or self.observed_models != sum(value > 0 for value in n)
            or self.commands != self.batch_size + self.response_commands
            or self.response_commands
            != s[15]
            - s[19]
            - self.automatic_danger_resolutions
            + s[11]
            + s[12]
            + self.phenomenon_responses
            or self.original_owner_ticks != self.batch_size
        ):
            raise ValueError("generated guardian smoke accounting or scope differs")
        return self


def run_full_game_generated_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 4096,
    player_count: int = 3,
    seed: int = 67,
    guardian_kind: str = "mixed",
) -> FullGameGeneratedSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("Earth smoke batch size must be1 through4096")
    if guardian_kind not in ("earth", "moon", "mixed"):
        raise ValueError("generated smoke guardian kind must be earth, moon or mixed")
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
        initial_hp=100,
        initial_mp=20,
        initial_cp=20,
    )
    b = c.batch
    envs = np.arange(batch_size, dtype=np.int64)
    seats = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    b.seed_players(
        np.repeat(envs, player_count),
        seats,
        np.tile([100, 20, 20, 0], (len(seats), 1)).astype(np.int64),
        np.full(len(seats), 2, dtype=np.int64),
    )
    for env in range(batch_size):
        for seat in range(player_count):
            b.seed_hand(env, seat, np.asarray([[seat * 100 + 1, 208, 0, 0]], dtype=np.int64))
    groups = (
        envs % 2 + 9
        if guardian_kind == "mixed"
        else np.full(batch_size, 9 if guardian_kind == "earth" else 10, dtype=np.int64)
    )
    b.seed_guardians(envs, np.ones(batch_size, dtype=np.int64), groups)
    b.start_environments(envs)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "choice_masks",
            "player_observations",
            "guardian_observations",
            "guardian_effect_observations",
            "attack_effect_observations",
            "guardian_statistics",
            "guardian_generated_snapshot",
            "guardian_generated_model_counts",
            "guardian_generated_execution_counts",
            "attack_family_snapshot",
            "generated_action_observations",
            "market_observations",
            "market_snapshot",
            "market_escrow_snapshot",
            "trade_snapshot",
            "revival_snapshot",
        ):
            replay.update(getattr(b, name)().astype("<i8", copy=False).tobytes())

    def issue(rows: npt.NDArray[np.int64]) -> None:
        if not len(rows):
            return
        if not b.choice_masks()[rows, 0].all():
            raise RuntimeError("Earth smoke response pass is unavailable")
        b.step(
            np.column_stack(
                (rows, b.episode_snapshot()[rows, :4], np.zeros(len(rows), dtype=np.int64))
            )
        )
        fingerprint()

    fingerprint()
    issue(envs)
    for _ in range(128):
        pending = np.flatnonzero(np.isin(b.episode_snapshot()[:, 3], (4, 6)))
        if not len(pending):
            break
        issue(pending)
    else:
        raise RuntimeError("generated smoke exceeded bounded first-turn response drain")
    episodes, players, families = (
        b.episode_snapshot(),
        b.diagnostic_players(),
        b.attack_family_snapshot(),
    )
    if (
        not (episodes[:, 3] == 1).all()
        or families[:, 13:].any()
        or players[:, 1:, 5].any()
        or b.miracle_use_count
        or b.market_escrow_snapshot()[:, 5].any()
        or b.automatic_gift_count
        or not np.array_equal(families[:, 0], families[:, 2] + families[:, 3])
    ):
        raise RuntimeError("Earth smoke left pending work, extra ticks, costs or uses")
    counts = tuple(int(n) for n in b.guardian_generated_model_counts().sum(axis=0))
    return FullGameGeneratedSmokeReport(
        guardian_kind=cast(Literal["earth", "moon", "mixed"], guardian_kind),
        metadata_sha256=hashlib.sha256(
            json.dumps(
                c.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        model_counts=counts,
        execution_counts=tuple(int(n) for n in b.guardian_generated_execution_counts().sum(axis=0)),
        observed_models=sum(n > 0 for n in counts),
        statistic_totals=tuple(int(n) for n in b.guardian_generated_snapshot().sum(axis=0)),
        commands=b.action_count,
        response_commands=b.action_count - batch_size,
        consumed_cards=b.consumed_count,
        sun_revivals=b.revival_count,
        mp_spent=b.mp_spent,
        attack_hp_damage=b.hp_damage,
        utility_hp_damage=b.utility_hp_damage,
        automatic_danger_resolutions=int(b.danger_snapshot()[:, 6].sum()),
        phenomenon_responses=int(
            (b.phenomenon_snapshot()[:, 4] - b.phenomenon_snapshot()[:, 5]).sum()
        ),
        phenomenon_attack_hp_damage=int(b.phenomenon_snapshot()[:, 7].sum()),
        original_owner_ticks=int(players[:, 0, 5].sum()),
    )
