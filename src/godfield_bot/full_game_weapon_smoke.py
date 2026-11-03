"""Scripted complex-weapon turns, not full games, strength or learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    COMPLEX_WEAPON_SNAPSHOT_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_weapons import FULL_GAME_WEAPON_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameWeaponSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[12] = 12
    source_kind: Literal["integrated-development-complex-weapon-smoke-v1"] = (
        "integrated-development-complex-weapon-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["twelve-scripted-mp-recoil-double-strike-cases-not-full-games"] = (
        "twelve-scripted-mp-recoil-double-strike-cases-not-full-games"
    )
    weapon_profile_sha256: Literal[
        "f74d9d6a875d8dac98b66926fe202c20d558254dcb035879b05605673c1baa4d"
    ] = FULL_GAME_WEAPON_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    weapon_fields: tuple[str, ...] = COMPLEX_WEAPON_SNAPSHOT_FIELDS
    weapon_totals: tuple[Count, ...]
    actions: Count
    completed_turns: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    incoming_hp_damage: Count
    recoil_hp_damage: Count
    mp_spent: Count
    consumed_cards: Count
    retained_miracle_uses: Count
    cost_waivers: Count
    waived_mp: Count
    counters: Count
    reflections: Count
    real_terminal_endings: Count
    automatic_gifts: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    compound_rules_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameWeaponSmokeReport:
        counts = tuple((self.batch_size + 11 - i) // 12 for i in range(12))

        def total(values: tuple[int, ...]) -> int:
            return sum(a * b for a, b in zip(values, counts, strict=True))

        mp = 10 * (counts[1] + counts[2])
        recoil = 14 * counts[3] + 9 * counts[4] + counts[11]
        double = sum(counts[6:11])
        if (
            self.scenario_counts != counts
            or self.weapon_fields != COMPLEX_WEAPON_SNAPSHOT_FIELDS
            or self.weapon_totals
            != (
                sum(counts[:3]),
                mp,
                counts[3] + counts[4] + counts[5] + counts[11],
                counts[3] + counts[4] + counts[11],
                recoil,
                double,
                2 * sum(counts[6:10]) + counts[10],
                counts[10],
            )
            or self.actions != total((4, 5, 6, 4, 5, 4, 5, 7, 7, 7, 4, 4))
            or self.incoming_hp_damage != total((0, 18, 22, 14, 9, 5, 6, 4, 6, 12, 2, 14))
            or self.recoil_hp_damage != recoil
            or self.mp_spent != mp
            or self.consumed_cards != total((1, 1, 2, 1, 2, 1, 1, 3, 2, 2, 1, 1))
            or self.retained_miracle_uses != counts[1] + counts[2]
            or self.cost_waivers != counts[2]
            or self.waived_mp != 2 * counts[2]
            or self.counters != counts[9]
            or self.reflections != counts[8]
            or self.real_terminal_endings
            != (counts[5] + counts[10] + counts[11] if self.player_count == 2 else 0)
            or self.completed_turns != self.batch_size
            or self.original_owner_ticks != self.batch_size
        ):
            raise ValueError("complex weapon smoke scripted accounting differs")
        return self


def run_full_game_weapon_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 720,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameWeaponSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("weapon smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=3,
        seed=seed,
        max_turns=2,
        max_decisions=9,
        initial_hp=100,
        initial_mp=10,
        initial_cp=0,
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 12
    for env, raw_scenario in enumerate(scenarios):
        scenario = int(raw_scenario)
        weapon = 58 if scenario < 3 else 14 if 6 <= scenario <= 10 else 53
        additions = [210, 204] if scenario == 2 else [210] if scenario == 1 else []
        defense_cards = {4: [135], 7: [113, 113], 8: [190], 9: [184]}.get(int(scenario), [])
        for owner, models in ((0, [weapon, *additions]), (1, defense_cards)):
            batch.seed_hand(
                env,
                owner,
                np.asarray(
                    [[100 * owner + i + 1, model, 0, 0] for i, model in enumerate(models)],
                    dtype=np.int64,
                ).reshape(-1, 4),
            )
        if scenario in (0, 5, 10, 11):
            owner = 1 if scenario in (5, 10) else 0
            hp = {5: 5, 10: 2, 11: 1}.get(int(scenario), 100)
            batch.seed_players(
                np.asarray([env], dtype=np.int64),
                np.asarray([owner], dtype=np.int64),
                np.asarray([[hp, 0 if scenario == 0 else 10, 0, 0]], dtype=np.int64),
                np.asarray([0], dtype=np.int64),
            )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # Full inventories are diagnostic only; choices below use public masks/selections.
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "attack_order",
            "defense_order",
            "attack_effect_observations",
            "complex_weapon_observations",
            "complex_weapon_snapshot",
            "cost_snapshot",
            "counter_snapshot",
            "revival_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    fingerprint()
    for _ in range(8):
        episodes = batch.episode_snapshot()
        active = np.flatnonzero((episodes[:, 4] == 0) & np.isin(episodes[:, 3], [1, 2, 3, 4]))
        if not len(active):
            break
        masks, attacks, defenses = (
            batch.choice_masks(),
            batch.selected_attacks(),
            batch.selected_defenses(),
        )
        commands = []
        for env_index in active:
            env = int(env_index)
            scenario, phase = int(scenarios[env]), int(episodes[env, 3])
            choice = 0
            if phase == 1:
                choice = 1
            elif phase == 2:
                if scenario in (1, 2) and not attacks[env, 1]:
                    choice = 2
                elif scenario == 2 and not attacks[env, 2]:
                    choice = 3
            elif phase == 3:
                choice = 5
            elif scenario in (4, 7, 8, 9) and masks[env, 1] and not defenses[env, 0]:
                choice = 1
            if not masks[env, choice]:
                raise RuntimeError("weapon smoke expected public choice is unavailable")
            commands.append([env, *episodes[env, :4], choice])
        batch.step(np.asarray(commands, dtype=np.int64))
        fingerprint()
    episodes, states = batch.episode_snapshot(), batch.diagnostic_players()
    if int(states[:, 1:, 5].sum()) or batch.automatic_gift_count or np.any(episodes[:, 3] == 13):
        raise RuntimeError("weapon smoke produced unexpected tick, gift or truncation")
    return FullGameWeaponSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(12)),
        weapon_totals=tuple(int(value) for value in batch.complex_weapon_snapshot().sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        original_owner_ticks=int(states[:, 0, 5].sum()),
        incoming_hp_damage=batch.hp_damage,
        recoil_hp_damage=batch.recoil_hp_damage,
        mp_spent=batch.mp_spent,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
        cost_waivers=batch.cost_waiver_count,
        waived_mp=batch.waived_mp,
        counters=batch.counter_count,
        reflections=batch.reflection_count,
        real_terminal_endings=int(np.count_nonzero(episodes[:, 3] == 12)),
    )
