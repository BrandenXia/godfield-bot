"""Three-card Sacrifice and complete-pool/devil receipts, not full-game training."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    DEVIL_FIELDS,
    FULL_GAME_RULESET_ID,
    SACRIFICE_SNAPSHOT_FIELDS,
    create_development_full_game_batch,
)

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameSacrificeSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    queue_schema_version: Literal[8] = 8
    resource_cap: Literal[99] = 99
    source_kind: Literal["three-card-sacrifice-complete-pool-devil-firstturn-probe-v1"] = (
        "three-card-sacrifice-complete-pool-devil-firstturn-probe-v1"
    )
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    statistic_fields: tuple[str, ...] = SACRIFICE_SNAPSHOT_FIELDS
    statistic_totals: tuple[Count, ...]
    model_ids: tuple[int, ...] = tuple(range(3, 240))
    model_counts: tuple[Count, ...]
    observed_models: Count
    devil_fields: tuple[str, ...] = DEVIL_FIELDS
    devil_totals: tuple[Count, ...]
    devil_model_ids: tuple[int, ...] = tuple(range(240, 245))
    devil_model_counts: tuple[Count, ...]
    observed_devil_models: Count
    commands: Count
    preparation_turns: Count
    sacrifice_turns: Count
    preparation_owner_ticks: Count
    sacrifice_owner_ticks: Count
    automatic_gifts: Count
    remaining_owner_cards: Count
    remaining_owner_hp: Count
    remaining_owner_mp: Count
    remaining_owner_cp: Count
    devil_removed_cards: Count
    devil_hp_damage: Count
    family_enqueued: Count
    family_resolved: Count
    family_suppressed: Literal[0] = 0
    pending_families: Literal[0] = 0
    other_owner_ticks: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    real_terminal_endings: Literal[0] = 0
    consumed_cards: Literal[0] = 0
    miracle_uses: Literal[0] = 0
    original_attacks: Literal[0] = 0
    mp_spent: Literal[0] = 0
    full_games_completed: Literal[0] = 0
    official_apocalypse_threshold_verified: Literal[False] = False
    official_sacrifice_cardinality_and_timing_verified: Literal[False] = False
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameSacrificeSmokeReport:
        b, s, d, n = (
            self.batch_size,
            self.statistic_totals,
            self.devil_totals,
            self.devil_model_counts,
        )
        if (
            self.statistic_fields != SACRIFICE_SNAPSHOT_FIELDS
            or s != (b, 3 * b, 0, b, 3 * b, b, 3 * b, 3 * b, 0)
            or self.model_ids != tuple(range(3, 240))
            or len(self.model_counts) != 237
            or sum(self.model_counts) != 3 * b
            or self.observed_models != sum(c > 0 for c in self.model_counts)
            or self.devil_fields != DEVIL_FIELDS
            or len(d) != 18
            or self.devil_model_ids != tuple(range(240, 245))
            or len(n) != 5
        ):
            raise ValueError("Sacrifice smoke layout or replacement accounting differs")
        if (
            d[0:2] != (b, 3 * b)
            or d[2] != sum(n)
            or d[2] > d[1]
            or d[3] != sum(n[:3])
            or d[4] != 10 * n[0] + 20 * n[1] + 30 * n[2]
            or d[5] != n[3]
            or d[6] > 5 * n[3]
            or d[7] > min(d[6], 2 * n[3])
            or d[7] != self.devil_removed_cards
            or d[8] != n[4]
            or any(d[i] > 10 * n[4] for i in (9, 10, 11))
            or d[12] != d[7]
            or d[13] != n[4]
            or d[14:18] != (3 * b, 3 * b, 0, b)
            or self.observed_devil_models != sum(c > 0 for c in n)
            or self.commands != 6 * b
            or self.preparation_turns != b
            or self.sacrifice_turns != b
            or self.preparation_owner_ticks != b
            or self.sacrifice_owner_ticks != b
            or self.automatic_gifts != 3 * b
            or self.remaining_owner_cards != 5 * b - d[7]
            or self.remaining_owner_hp != 99 * b - d[4] + d[9]
            or self.remaining_owner_mp != 20 * b + d[10]
            or self.remaining_owner_cp != 20 * b + d[11]
            or self.devil_hp_damage != d[4]
            or self.family_enqueued != 3 * b
            or self.family_resolved != 3 * b
        ):
            raise ValueError("Sacrifice smoke event, queue or turn accounting differs")
        return self


def run_full_game_sacrifice_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 4096,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameSacrificeSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("Sacrifice smoke batch size must be 1 through 4096")
    c = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=3,
        max_decisions=16,
        initial_hp=99,
        initial_mp=20,
        initial_cp=20,
        apocalypse_after_turns=1,
    )
    b = c.batch
    envs = np.arange(batch_size, dtype=np.int64)
    seats = np.ones(batch_size, dtype=np.int64)
    b.seed_players(
        envs,
        seats,
        np.tile([99, 20, 20, 0], (batch_size, 1)).astype(np.int64),
        np.full(batch_size, 2, dtype=np.int64),
    )
    for env in range(batch_size):
        b.seed_hand(
            env,
            1,
            np.asarray(
                [
                    [101, 127, 0, 0],
                    [102, 237, 235, 1],
                    [103, 191, 0, 0],
                    [104, 208, 0, 0],
                    [105, 112, 0, 0],
                ],
                dtype=np.int64,
            ),
        )
    b.start_environments(envs)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "discard_observations",
            "discard_order",
            "discard_snapshot",
            "sacrifice_snapshot",
            "sacrifice_model_counts",
            "apocalypse_observations",
            "acquisition_snapshot",
            "devil_snapshot",
            "devil_model_counts",
            "attack_family_snapshot",
            "revival_snapshot",
        ):
            replay.update(getattr(b, name)().astype("<i8", copy=False).tobytes())

    fingerprint()
    for choice in (0, 19, 1, 2, 3, 0):
        if not b.choice_masks()[:, choice].all():
            raise RuntimeError("Sacrifice smoke public scripted choice unavailable")
        b.step(
            np.column_stack(
                (
                    envs,
                    b.episode_snapshot()[:, :4],
                    np.full(batch_size, choice, dtype=np.int64),
                )
            )
        )
        fingerprint()
    episodes, players, family = (
        b.episode_snapshot(),
        b.diagnostic_players(),
        b.attack_family_snapshot(),
    )
    if (
        not (episodes[:, 3] == 1).all()
        or not (episodes[:, 4] == 2).all()
        or family[:, 13:].any()
        or players[:, 2:, 5].any()
        or b.consumed_count
        or b.miracle_use_count
        or b.attack_count
        or b.mp_spent
        or b.hp_damage
        or b.utility_hp_damage
        or b.overflow_count
    ):
        raise RuntimeError("Sacrifice smoke left pending work, extra ticks, uses or limits")
    counts = tuple(int(n) for n in b.sacrifice_model_counts().sum(axis=0))
    devils = tuple(int(n) for n in b.devil_model_counts().sum(axis=0))
    inventory = b.diagnostic_inventory()
    return FullGameSacrificeSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                c.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        statistic_totals=tuple(int(n) for n in b.sacrifice_snapshot().sum(axis=0)),
        model_counts=counts,
        observed_models=sum(n > 0 for n in counts),
        devil_totals=tuple(int(n) for n in b.devil_snapshot().sum(axis=0)),
        devil_model_counts=devils,
        observed_devil_models=sum(n > 0 for n in devils),
        commands=b.action_count,
        preparation_turns=batch_size,
        sacrifice_turns=batch_size,
        preparation_owner_ticks=int(players[:, 0, 5].sum()),
        sacrifice_owner_ticks=int(players[:, 1, 5].sum()),
        automatic_gifts=b.automatic_gift_count,
        remaining_owner_cards=int(np.count_nonzero(inventory[:, 1, :, 0])),
        remaining_owner_hp=int(players[:, 1, 0].sum()),
        remaining_owner_mp=int(players[:, 1, 1].sum()),
        remaining_owner_cp=int(players[:, 1, 2].sum()),
        devil_removed_cards=b.devil_removed_count,
        devil_hp_damage=b.devil_hp_damage,
        family_enqueued=int(family[:, 0].sum()),
        family_resolved=int(family[:, 2].sum()),
    )
