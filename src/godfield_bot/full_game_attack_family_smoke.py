"""Bounded original/counter/death scheduling probe; not full-game learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    ATTACK_FAMILY_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_attack_family import FULL_GAME_ASCENSION_SHA256

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameAttackFamilySmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[8] = 8
    source_kind: Literal["integrated-development-attack-family-smoke-v1"] = (
        "integrated-development-attack-family-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v31"] = FULL_GAME_RULESET_ID
    queue_schema_version: Literal[8] = 8
    scenario: Literal["owned-bow-sun-periodic-chain-hat-repeat-scripted-not-full-games"] = (
        "owned-bow-sun-periodic-chain-hat-repeat-scripted-not-full-games"
    )
    ascension_profile_sha256: Literal[
        "d20664fab4740f69ea2a039a502dba71bbb8bd0744e0c47563edec271b3b7264"
    ] = FULL_GAME_ASCENSION_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    family_fields: tuple[str, ...] = ATTACK_FAMILY_FIELDS
    family_totals: tuple[Count, ...]
    actions: Count
    completed_turns: Count
    attacks: Count
    resolved_attacks: Count
    attack_hp_damage: Count
    ascension_hp_damage: Count
    consumed_cards: Count
    revivals: Count
    redraws: Count
    redrawn_cards: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
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
    official_multiplayer_and_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameAttackFamilySmokeReport:
        n = tuple((self.batch_size + 5 - i) // 6 for i in range(6))
        p = self.player_count
        bows = n[0] + n[2] + 2 * n[3] + n[4] + n[5]
        recipients = (p - 1) * (n[0] + n[2] + n[4] + n[5]) + (2 * p - 3) * n[3]
        damage = (
            30 * (p - 1) * (n[0] + n[2] + n[5])
            + (1 + 60 * (p - 2)) * n[3]
            + (16 + 30 * (p - 2)) * n[4]
        )
        attacks = self.batch_size - n[2]
        enqueued = attacks + n[5] + recipients
        resolved = enqueued - n[5]
        peak = (p - 1) * (n[0] + n[2] + n[4]) + n[1] + max(p - 1, 2 * p - 4) * n[3] + p * n[5]
        endings = self.batch_size - n[1] if p == 2 else (n[3] if p == 3 else 0)
        if (
            self.scenario_counts != n
            or self.family_fields != ATTACK_FAMILY_FIELDS
            or self.family_totals
            != (
                enqueued,
                resolved,
                resolved,
                n[5],
                0,
                peak,
                bows,
                bows,
                recipients,
                recipients,
                0,
                0,
                damage,
                0,
                0,
                0,
            )
            or self.actions
            != (p + 3) * (n[0] + n[5]) + 4 * n[1] + p * n[2] + (2 * p + 1) * n[3] + (p + 5) * n[4]
            or self.attacks != attacks
            or self.resolved_attacks != attacks
            or self.attack_hp_damage != attacks + damage
            or self.ascension_hp_damage != damage
            or self.consumed_cards != 2 * (n[0] + n[1] + n[5]) + n[2] + 3 * n[3] + 4 * n[4]
            or self.revivals != n[1]
            or self.redraws != n[4]
            or self.redrawn_cards != 2 * n[4]
            or self.completed_turns != self.batch_size
            or self.original_owner_ticks != self.batch_size
            or self.real_terminal_endings != endings
            or self.ready_after_one_turn != self.batch_size - endings
        ):
            raise ValueError("attack-family smoke scripted accounting differs")
        return self


def run_full_game_attack_family_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameAttackFamilySmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("attack-family smoke batch size must be 1 through 4096")
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
        initial_hp=100,
        initial_mp=20,
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 6
    for env, scenario in enumerate(scenarios):
        own = [112] if scenario == 2 else ([14] if scenario == 5 else [57])
        enemy = [112]
        if scenario == 1:
            enemy.append(208)
        if scenario == 3:
            own.append(112)
        if scenario == 4:
            own.extend([189, 178, 35, 237])
        for owner, models in ((0, own), (1, enemy if scenario != 2 else [])):
            batch.seed_hand(
                env,
                owner,
                np.asarray(
                    [[owner * 100 + i + 1, m, 0, int(m == 237)] for i, m in enumerate(models)],
                    dtype=np.int64,
                ).reshape(-1, 4),
            )
        for owner in range(player_count):
            hp = 1 if (owner == 0 and scenario in (2, 3)) or (owner == 1 and scenario != 2) else 100
            batch.seed_players(
                np.asarray([env], dtype=np.int64),
                np.asarray([owner], dtype=np.int64),
                np.asarray([[hp, 20, 0, int(owner == 0 and scenario == 2)]], dtype=np.int64),
                np.asarray([8], dtype=np.int64),
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
            "special_defense_observations",
            "attack_family_snapshot",
            "counter_snapshot",
            "revival_snapshot",
            "dream_defense_snapshot",
            "complex_weapon_snapshot",
            "acquisition_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    def issue(envs: npt.NDArray[np.int64], choice: int) -> None:
        if len(envs) == 0:
            return
        if not batch.choice_masks()[envs, choice].all():
            raise RuntimeError("attack-family smoke expected public choice is unavailable")
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
    casts = environments[scenarios != 2]
    issue(casts, 1)
    issue(casts, 0)
    issue(casts, 20)
    issue(environments[scenarios == 2], 0)
    for _ in range(2 * player_count + 2):
        episodes = batch.episode_snapshot()
        responses = np.flatnonzero(episodes[:, 3] == 4)
        if not len(responses):
            break
        # Select only public scripted Hat-defense slots after seat0's revealed
        # response. True identity/RNG never drives the command selection.
        hat = responses[(scenarios[responses] == 4) & (episodes[responses, 2] == 0)]
        issue(hat, 1)
        issue(hat, 2)
        issue(responses, 0)
    else:
        raise RuntimeError("attack-family smoke exceeded its bounded response loop")
    episodes, players, stats = (
        batch.episode_snapshot(),
        batch.diagnostic_players(),
        batch.attack_family_snapshot(),
    )
    if np.any(stats[:, 13:]) or np.any(episodes[:, 3] == 13):
        raise RuntimeError("attack-family smoke left a queue, active response or limit truncation")
    if any(
        (
            batch.automatic_gift_count,
            batch.mp_spent,
            batch.chance_count,
            batch.counter_count,
            int(players[:, 1:, 5].sum()),
        )
    ):
        raise RuntimeError(
            "attack-family smoke produced an unexpected gift, cost, counter or owner tick"
        )
    return FullGameAttackFamilySmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(6)),
        family_totals=tuple(int(v) for v in stats.sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        attacks=batch.attack_count,
        resolved_attacks=batch.resolved_attack_count,
        attack_hp_damage=batch.hp_damage,
        ascension_hp_damage=batch.ascension_hp_damage,
        consumed_cards=batch.consumed_count,
        revivals=batch.revival_count,
        redraws=batch.redraw_count,
        redrawn_cards=batch.redrawn_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
        real_terminal_endings=int(np.count_nonzero(episodes[:, 3] == 12)),
    )
