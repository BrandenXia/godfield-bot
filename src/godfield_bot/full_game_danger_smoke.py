"""Bounded Pestle/Mortar scripted turns; not full games or training evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    DANGER_SNAPSHOT_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_danger import FULL_GAME_DANGER_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameDangerSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[10] = 10
    source_kind: Literal["integrated-development-danger-smoke-v1"] = (
        "integrated-development-danger-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v33"] = FULL_GAME_RULESET_ID
    scenario: Literal["random-self-and-owned-mortar-revival-scripted-not-full-games"] = (
        "random-self-and-owned-mortar-revival-scripted-not-full-games"
    )
    danger_profile_sha256: Literal[
        "ebfd6728c84580fc20ff3729bd39f742e01d4f6b93cdbc9a732bfa788e0540b3"
    ] = FULL_GAME_DANGER_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    danger_fields: tuple[str, ...] = DANGER_SNAPSHOT_FIELDS
    danger_totals: tuple[Count, ...]
    random_target_counts: tuple[tuple[Count, ...], tuple[Count, ...]]
    multi_holder_target_counts: tuple[Count, Count]
    actions: Count
    completed_turns: Count
    attacks: Count
    resolved_attacks: Count
    normal_defense_responses: Count
    attack_hp_damage: Count
    automatic_hp_damage: Count
    consumed_cards: Count
    revivals: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    final_actor_deaths: Count
    final_other_deaths: Count
    ready_after_one_turn: Count
    real_terminal_endings: Count
    automatic_gifts: Literal[0] = 0
    mp_spent: Literal[0] = 0
    chance_casts: Literal[0] = 0
    counter_casts: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_multiplayer_and_attraction_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameDangerSmokeReport:
        n = tuple((self.batch_size + 7 - i) // 8 for i in range(8))
        if (
            self.scenario_counts != n
            or any(len(row) != self.player_count for row in self.random_target_counts)
            or tuple(map(sum, self.random_target_counts)) != n[:2]
            or sum(self.multi_holder_target_counts) != n[7]
        ):
            raise ValueError("danger smoke scenario or target accounting differs")
        s0, s1 = (row[0] for row in self.random_target_counts)
        attracted = sum(n[2:])
        attracted_self = n[5] + n[6] + self.multi_holder_target_counts[0]
        automatic_loss = 30 * s0 + s1 + 99 * (n[2] + n[7]) + sum(n[3:7])
        response_count = sum(n[:2]) - s0 - s1
        revivals = s1 + n[3] + n[5]
        endings = (n[4] + n[6]) if self.player_count == 2 else 0
        if (
            self.danger_fields != DANGER_SNAPSHOT_FIELDS
            or self.danger_totals
            != (
                self.batch_size,
                sum(n[:2]),
                s0 + s1 + attracted_self,
                attracted,
                n[7],
                attracted_self,
                s0 + s1 + attracted,
                automatic_loss,
            )
            or self.actions != 3 * self.batch_size + response_count
            or self.normal_defense_responses != response_count
            or self.automatic_hp_damage != automatic_loss
            or self.attack_hp_damage != automatic_loss + 30 * response_count
            or self.consumed_cards != self.batch_size + attracted + revivals
            or self.revivals != revivals
            or self.final_actor_deaths != n[6]
            or self.final_other_deaths != n[4]
            or self.real_terminal_endings != endings
            or self.ready_after_one_turn != self.batch_size - endings
            or any(
                count != self.batch_size
                for count in (
                    self.completed_turns,
                    self.attacks,
                    self.resolved_attacks,
                    self.original_owner_ticks,
                )
            )
        ):
            raise ValueError("danger smoke scripted accounting differs")
        return self


def run_full_game_danger_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameDangerSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("danger smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=5,
        initial_hp=100,
        initial_mp=20,
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 8
    for env, scenario in enumerate(scenarios):
        own = [94]
        enemy: list[int] = []
        if scenario in (1, 5):
            own.append(208)
        if scenario in (5, 6, 7):
            own.append(209)
        if scenario in (2, 3, 4, 7):
            enemy.append(209)
        if scenario == 3:
            enemy.append(208)
        for seat, models in ((0, own), (1, enemy)):
            batch.seed_hand(
                env,
                seat,
                np.asarray(
                    [[seat * 100 + i + 1, model, 0, 0] for i, model in enumerate(models)],
                    dtype=np.int64,
                ).reshape(-1, 4),
            )
            hp = (
                1
                if (seat == 0 and scenario in (1, 5, 6)) or (seat == 1 and scenario in (3, 4))
                else 100
            )
            batch.seed_players(
                np.asarray([env], dtype=np.int64),
                np.asarray([seat], dtype=np.int64),
                np.asarray([[hp, 20, 0, 0]], dtype=np.int64),
                np.asarray([1 if seat == 0 else 0], dtype=np.int64),  # Fog is excluded.
            )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # True state fingerprints outcomes only; commands use public phases/masks.
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "danger_observations",
            "danger_snapshot",
            "passive_observations",
            "pending_observations",
            "revival_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    def issue(envs: npt.NDArray[np.int64], choice: int) -> None:
        if len(envs) == 0:
            return
        if not batch.choice_masks()[envs, choice].all():
            raise RuntimeError("danger smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (
                    envs,
                    batch.episode_snapshot()[envs, :4],
                    np.full(len(envs), choice, dtype=np.int64),
                )
            )
        )
        fingerprint()

    fingerprint()
    issue(environments, 1)
    issue(environments, 0)
    issue(environments, 20)  # Legal requested seat1, overridden inside the native cast.
    episodes = batch.episode_snapshot()
    pending = batch.pending_observations()
    normal_responses = np.flatnonzero(episodes[:, 3] == 4)
    # The public response identifies the revealed random target; no hidden holder lookup.
    random_targets = np.where(episodes[:, 3] == 4, pending[:, 2], 0)
    issue(normal_responses, 0)
    stats, episodes, players = (
        batch.danger_snapshot(),
        batch.episode_snapshot(),
        batch.diagnostic_players(),
    )
    if any(
        (
            batch.automatic_gift_count,
            batch.mp_spent,
            batch.chance_count,
            batch.counter_count,
            int(players[:, 1:, 5].sum()),
            int(np.count_nonzero(episodes[:, 3] == 13)),
        )
    ):
        raise RuntimeError("danger smoke produced an unexpected gift, cost, counter or limit")
    multi_self = int(stats[scenarios == 7, 5].sum())
    return FullGameDangerSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(8)),
        danger_totals=tuple(int(value) for value in stats.sum(axis=0)),
        random_target_counts=(
            tuple(
                int(np.count_nonzero(random_targets[scenarios == 0] == seat))
                for seat in range(player_count)
            ),
            tuple(
                int(np.count_nonzero(random_targets[scenarios == 1] == seat))
                for seat in range(player_count)
            ),
        ),
        multi_holder_target_counts=(multi_self, int(np.count_nonzero(scenarios == 7)) - multi_self),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        attacks=batch.attack_count,
        resolved_attacks=batch.resolved_attack_count,
        normal_defense_responses=len(normal_responses),
        attack_hp_damage=batch.hp_damage,
        automatic_hp_damage=batch.automatic_danger_hp_damage,
        consumed_cards=batch.consumed_count,
        revivals=batch.revival_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        final_actor_deaths=int(np.count_nonzero(players[:, 0, 0] == 0)),
        final_other_deaths=int(np.count_nonzero(players[:, 1:, 0] == 0)),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
        real_terminal_endings=int(np.count_nonzero(episodes[:, 3] == 12)),
    )
