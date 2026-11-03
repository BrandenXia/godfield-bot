"""Bounded joined standard guardian probe, not full-game learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    FULL_GAME_RULESET_ID,
    GUARDIAN_STATISTIC_FIELDS,
    create_development_full_game_batch,
)
from godfield_bot.full_game_guardians import FULL_GAME_GUARDIAN_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt


class FullGameGuardianSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[5] = 5
    source_kind: Literal["integrated-standard-guardian-postturn-smoke-v1"] = (
        "integrated-standard-guardian-postturn-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["one-enemy-turn-all8-standard-groups-darkcloud-scripted-not-full-games"] = (
        "one-enemy-turn-all8-standard-groups-darkcloud-scripted-not-full-games"
    )
    guardian_profile_sha256: Literal[
        "d5275fde52d4fb421dd387e65a8866d4535216263a534e91d4af595dc468c471"
    ] = FULL_GAME_GUARDIAN_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    statistic_fields: tuple[str, ...] = GUARDIAN_STATISTIC_FIELDS
    statistic_totals: tuple[Count, ...]
    model_ids: tuple[int, ...] = tuple(range(245, 285))
    model_counts: tuple[Count, ...]
    observed_effect_models: int = Field(ge=0, le=40, strict=True)
    actions: int = Field(ge=0, strict=True)
    completed_turns: int = Field(ge=0, strict=True)
    original_owner_ticks: int = Field(ge=0, strict=True)
    revivals: int = Field(ge=0, strict=True)
    consumed_cards: int = Field(ge=0, strict=True)
    restored_disguises: int = Field(ge=0, strict=True)
    incoming_hp_damage: int = Field(ge=0, strict=True)
    hp_absorbed: int = Field(ge=0, strict=True)
    other_owner_ticks: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    original_attacks: Literal[0] = 0
    mp_spent: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    unimplemented_special_models: tuple[int, ...] = ()
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameGuardianSmokeReport:
        if len(self.model_counts) != 40 or any(
            type(n) is not int or n < 0 for n in self.model_counts
        ):
            raise ValueError("guardian model histogram is malformed")
        n = dict(zip(range(245, 285), self.model_counts, strict=True))
        activations = sum(n.values())
        automatic = sum(n[i] for i in range(275, 281)) + n[283] + n[284]
        damage = sum(
            n[i] * value
            for i, value in {
                245: 3,
                246: 4,
                247: 5,
                248: 6,
                249: 7,
                250: 1,
                251: 2,
                252: 3,
                253: 3,
                254: 6,
                255: 1,
                256: 2,
                257: 1,
                259: 2,
                260: 2,
                261: 4,
                262: 6,
                263: 9,
                264: 15,
                265: 2,
                266: 4,
                268: 5,
                269: 10,
                270: 100,
                271: 100,
                273: 100,
                274: 100,
            }.items()
        )
        absorbed = n[257] + 5 * n[268]
        cp = n[280] * self.player_count + 5 * n[281] + 3 * n[282] + 8 * n[283] + 20 * n[284]
        expected = (
            0,
            0,
            self.batch_size,
            activations,
            activations,
            activations - automatic,
            activations,
            activations,
            0,
            0,
            0,
            0,
            0,
            damage,
            absorbed + 5 * n[276] + 10 * n[278],
            5 * n[277] + 10 * n[279],
            cp,
            0,
            n[275],
        )
        if (
            self.model_ids != tuple(range(245, 285))
            or self.statistic_fields != GUARDIAN_STATISTIC_FIELDS
            or self.statistic_totals != expected
            or self.observed_effect_models != sum(v > 0 for v in n.values())
            or self.actions != self.batch_size + activations - automatic
            or self.completed_turns != self.batch_size
            or self.original_owner_ticks != self.batch_size
            or self.revivals != sum(n[i] for i in (270, 271, 273, 274))
            or self.consumed_cards != self.revivals
            or self.restored_disguises != n[275]
            or self.incoming_hp_damage != damage
            or self.hp_absorbed != absorbed
            or self.unimplemented_special_models != ()
        ):
            raise ValueError("guardian smoke scripted accounting differs")
        return self


def run_full_game_guardian_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 4096,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameGuardianSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("guardian smoke batch size must be 1 through 4096")
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
    envs = np.arange(batch_size, dtype=np.int64)
    owners = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    all_envs = np.repeat(envs, player_count)
    resources = np.tile([100, 20, 5, 0], (len(owners), 1)).astype(np.int64)
    guardian_owners = owners == 1
    resources[guardian_owners] = [50, 10, 2, 2]
    masks = np.where(guardian_owners, 15, 8).astype(np.int64)
    batch.seed_players(all_envs, owners, resources, masks)
    for env in range(batch_size):
        for owner in range(player_count):
            rows = [[owner * 100 + 1, 208, 0, 0]]
            if owner == 1:
                rows.append([owner * 100 + 2, 127, 142, 0])
            batch.seed_hand(env, owner, np.asarray(rows, dtype=np.int64))
    batch.seed_guardians(envs, np.ones(batch_size, dtype=np.int64), envs % 8 + 1)
    batch.start_environments(envs)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "guardian_snapshot",
            "guardian_observations",
            "guardian_effect_observations",
            "guardian_statistics",
            "guardian_model_counts",
            "attack_family_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    def issue(rows: npt.NDArray[np.int64]) -> None:
        if not len(rows):
            return
        if not batch.choice_masks()[rows, 0].all():
            raise RuntimeError("guardian smoke public pass unavailable")
        batch.step(
            np.column_stack(
                (rows, batch.episode_snapshot()[rows, :4], np.zeros(len(rows), dtype=np.int64))
            )
        )
        fingerprint()

    fingerprint()
    issue(envs)
    issue(np.flatnonzero(batch.episode_snapshot()[:, 3] == 4))
    episodes, players, family = (
        batch.episode_snapshot(),
        batch.diagnostic_players(),
        batch.attack_family_snapshot(),
    )
    if (
        not (episodes[:, 3] == 1).all()
        or family[:, 13:].any()
        or players[:, 1:, 5].any()
        or batch.attack_count
        or batch.mp_spent
        or batch.automatic_gift_count
    ):
        raise RuntimeError("guardian smoke left unexpected state, tick, attack or receipt")
    counts = tuple(int(n) for n in batch.guardian_model_counts().sum(axis=0))
    return FullGameGuardianSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        model_counts=counts,
        observed_effect_models=sum(n > 0 for n in counts),
        statistic_totals=tuple(int(n) for n in batch.guardian_statistics().sum(axis=0)),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        original_owner_ticks=int(players[:, 0, 5].sum()),
        revivals=batch.revival_count,
        consumed_cards=batch.consumed_count,
        restored_disguises=batch.restored_count,
        incoming_hp_damage=batch.hp_damage,
        hp_absorbed=batch.absorbed_hp,
    )
