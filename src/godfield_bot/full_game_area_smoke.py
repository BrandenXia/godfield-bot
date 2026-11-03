"""Bounded six-scenario Mirage replay probe, not full-game learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    AREA_SNAPSHOT_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_area import FULL_GAME_AREA_SHA256

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameAreaSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[7] = 7
    source_kind: Literal["integrated-development-area-smoke-v1"] = (
        "integrated-development-area-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v31"] = FULL_GAME_RULESET_ID
    queue_schema_version: Literal[8] = 8
    scenario: Literal["mirage-fog-repeat-dynamic-recoil-waiver-counter-scripted-not-full-games"] = (
        "mirage-fog-repeat-dynamic-recoil-waiver-counter-scripted-not-full-games"
    )
    area_profile_sha256: Literal[
        "84016251775afdf821b5097e03d58311423f6df583c8cddc15aad2bee107d8e5"
    ] = FULL_GAME_AREA_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    area_fields: tuple[str, ...] = AREA_SNAPSHOT_FIELDS
    area_totals: tuple[Count, ...]
    actions: Count
    completed_turns: Count
    attacks: Count
    resolved_attacks: Count
    area_hp_damage: Count
    incoming_hp_damage: Count
    recoil_hp_damage: Count
    mp_spent: Count
    cost_waivers: Count
    waived_mp: Count
    consumed_cards: Count
    miracle_uses: Count
    counter_casts: Count
    family_enqueued: Count
    family_resolved: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    ready_after_one_turn: Count
    real_terminal_endings: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    chance_casts: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_multiplayer_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameAreaSmokeReport:
        n = tuple((self.batch_size + 5 - i) // 6 for i in range(6))
        recipients = self.player_count - 1
        shots = recipients * (self.batch_size + n[1])
        damage = recipients * (10 * (n[0] + n[4] + n[5]) + 6 * n[1] + 30 * n[2] + 14 * n[3])
        if (
            self.scenario_counts != n
            or self.area_fields != AREA_SNAPSHOT_FIELDS
            or self.area_totals
            != (
                self.batch_size,
                self.batch_size,
                recipients * self.batch_size,
                shots,
                shots,
                0,
                damage,
                self.batch_size,
            )
            or self.actions != 4 * self.batch_size + n[4] + shots + 2 * n[5]
            or self.completed_turns != self.batch_size
            or self.attacks != self.batch_size
            or self.resolved_attacks != self.batch_size
            or self.area_hp_damage != damage
            or self.incoming_hp_damage != damage + 20 * n[5]
            or self.recoil_hp_damage != min(100, 14 * recipients) * n[3]
            or self.mp_spent != 5 * (self.batch_size - n[2] - n[4]) + 20 * n[2]
            or self.cost_waivers != n[4]
            or self.waived_mp != 5 * n[4]
            or self.consumed_cards != self.batch_size + n[4] + n[5]
            or self.miracle_uses != self.batch_size
            or self.counter_casts != n[5]
            or self.family_enqueued != shots + n[5]
            or self.family_resolved != shots + n[5]
            or self.original_owner_ticks != self.batch_size
            or self.ready_after_one_turn != self.batch_size
        ):
            raise ValueError("area smoke scripted accounting differs")
        return self


def run_full_game_area_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameAreaSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("area smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
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
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 6
    for env, scenario in enumerate(scenarios):
        weapon = (35, 14, 58, 53, 35, 35)[scenario]
        models = [weapon, 232] + ([204] if scenario == 4 else [])
        batch.seed_hand(
            env, 0, np.asarray([[i + 1, m, 0, 0] for i, m in enumerate(models)], dtype=np.int64)
        )
        if scenario == 5:
            batch.seed_hand(env, 1, np.asarray([[101, 184, 0, 0]], dtype=np.int64))
        batch.seed_players(
            np.asarray([env], dtype=np.int64),
            np.asarray([0], dtype=np.int64),
            np.asarray([[100, 20, 0, 0]], dtype=np.int64),
            np.asarray([1], dtype=np.int64),
        )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "area_observations",
            "area_snapshot",
            "attack_family_snapshot",
            "counter_snapshot",
            "cost_snapshot",
            "complex_weapon_observations",
            "complex_weapon_snapshot",
            "acquisition_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    def issue(envs: npt.NDArray[np.int64], choice: int) -> None:
        if not len(envs):
            return
        if not batch.choice_masks()[envs, choice].all():
            raise RuntimeError("area smoke expected public choice is unavailable")
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
    issue(environments, 2)
    issue(environments[scenarios == 4], 3)
    issue(environments, 0)
    issue(environments, 19 + player_count - 1)
    for _ in range(2 * player_count + 2):
        episodes = batch.episode_snapshot()
        responses = np.flatnonzero(episodes[:, 3] == 4)
        if not len(responses):
            break
        rings = responses[(scenarios[responses] == 5) & (episodes[responses, 2] == 1)]
        issue(rings, 1)
        issue(responses, 0)
    else:
        raise RuntimeError("area smoke exceeded its bounded response loop")
    episodes = batch.episode_snapshot()
    family = batch.attack_family_snapshot()
    players = batch.diagnostic_players()
    if np.any(episodes[:, 3] != 1) or family[:, 13:].any():
        raise RuntimeError("area smoke left an unfinished family or unexpected ending")
    if players[:, 1:, 5].any() or batch.automatic_gift_count or batch.chance_count:
        raise RuntimeError("area smoke produced an unexpected gift, chance cast or owner tick")
    metadata_sha = hashlib.sha256(
        json.dumps(
            configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return FullGameAreaSmokeReport(
        metadata_sha256=metadata_sha,
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == s)) for s in range(6)),
        area_totals=tuple(int(v) for v in batch.area_snapshot().sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        attacks=batch.attack_count,
        resolved_attacks=batch.resolved_attack_count,
        area_hp_damage=batch.area_hp_damage,
        incoming_hp_damage=batch.hp_damage,
        recoil_hp_damage=batch.recoil_hp_damage,
        mp_spent=batch.mp_spent,
        cost_waivers=batch.cost_waiver_count,
        waived_mp=batch.waived_mp,
        consumed_cards=batch.consumed_count,
        miracle_uses=batch.miracle_use_count,
        counter_casts=batch.counter_count,
        family_enqueued=int(family[:, 0].sum()),
        family_resolved=int(family[:, 2].sum()),
        original_owner_ticks=int(players[:, 0, 5].sum()),
        ready_after_one_turn=batch_size,
    )
