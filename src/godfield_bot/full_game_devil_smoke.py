"""Bounded first-turn devils in complete-pool dealt hands, not full matches."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    DEVIL_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_devils import DEVIL_PROFILE_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameDevilSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[4] = 4
    source_kind: Literal["integrated-firstturn-apocalypse-gift-devils-smoke-v1"] = (
        "integrated-firstturn-apocalypse-gift-devils-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    queue_schema_version: Literal[8] = 8
    scenario: Literal[
        "nine-weighted-starting-cards-first-affordable-public-turn-forgive-responses-not-full-games"
    ] = "nine-weighted-starting-cards-first-affordable-public-turn-forgive-responses-not-full-games"
    devil_profile_sha256: Literal[
        "a6b1927315e0a08937c1d46f995fbe825b9866d9b063440b5bd88097313eeef4"
    ] = DEVIL_PROFILE_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    apocalypse_after_turns: Literal[1] = 1
    statistic_fields: tuple[str, ...] = DEVIL_FIELDS
    statistic_totals: tuple[Count, ...]
    model_ids: tuple[int, ...] = tuple(range(240, 245))
    model_counts: tuple[Count, ...]
    observed_devil_models: int = Field(ge=0, le=5, strict=True)
    commands: Count
    completed_turns: Count
    original_owner_ticks: Count
    automatic_gifts: Count
    initial_gifts: Count
    devil_hp_damage: Count
    devil_removed_cards: Count
    pending_families: Literal[0] = 0
    other_owner_ticks: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameDevilSmokeReport:
        s, n = self.statistic_totals, self.model_counts
        if (
            len(s) != 18
            or len(n) != 5
            or self.statistic_fields != DEVIL_FIELDS
            or self.model_ids != tuple(range(240, 245))
        ):
            raise ValueError("devil smoke layouts differ")
        if (
            s[0] != self.batch_size
            or s[1] != s[15]
            or s[2] != sum(n)
            or s[3] != sum(n[:3])
            or s[5] != n[3]
            or s[8] != n[4]
            or s[13] != n[4]
            or s[14] != s[15] + s[16]
            or s[7] != s[12]
            or s[7] > 2 * n[3]
            or s[6] < s[7]
            or s[2] > s[1]
            or s[4] > sum(value * count for value, count in zip((10, 20, 30), n[:3], strict=True))
            or sum(s[9:12]) > 10 * n[4]
            or s[17] > s[14]
            or s[4] != self.devil_hp_damage
            or s[7] != self.devil_removed_cards
            or self.observed_devil_models != sum(v > 0 for v in n)
            or self.completed_turns != self.batch_size
            or self.original_owner_ticks != self.batch_size
            or self.initial_gifts != 9 * self.player_count * self.batch_size
            or self.automatic_gifts != self.initial_gifts + s[15]
            or self.commands < self.batch_size
        ):
            raise ValueError("devil smoke accounting differs")
        return self


def run_full_game_devil_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 4096,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameDevilSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("devil smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=128,
        initial_hp=100,
        initial_mp=20,
        initial_cp=5,
        acquisition_mode="all-held-weighted",
        apocalypse_after_turns=1,
    )
    batch = configured.batch
    costs = {row[0]: row[4] for row in configured.metadata.plan.combat.attack_profiles}
    costs.update({row[0]: row[3] for row in configured.metadata.plan.effect_profiles})
    costs.update(dict(configured.metadata.plan.guardians.summon_profiles))
    batch.start_environments(np.arange(batch_size, dtype=np.int64))
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "player_observations",
            "attack_family_snapshot",
            "revival_snapshot",
            "devil_snapshot",
            "devil_model_counts",
            "apocalypse_observations",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    fingerprint()
    for _ in range(128):
        episodes = batch.episode_snapshot()
        envs = np.flatnonzero(
            (episodes[:, 3] < 12) & ((episodes[:, 4] == 0) | (episodes[:, 3] == 4))
        )
        if not len(envs):
            break
        masks = batch.choice_masks()
        hands = batch.actor_hands()
        public_players = batch.player_observations()
        choices = []
        for env in envs:
            phase = episodes[env, 3]
            if (phase in (1, 4) and masks[env, 0]) or phase == 2:
                choice = 0
            elif phase == 1:
                affordable = [
                    int(slot) + 1
                    for slot in np.flatnonzero(masks[env, 1:19])
                    if costs.get(int(hands[env, slot, 1]), 0) <= public_players[env, 0, 4]
                ]
                choice = affordable[0] if affordable else 19
            elif phase == 3:
                choice = int(np.flatnonzero(masks[env])[0])
            elif phase == 7:
                choice = 0 if masks[env, 0] else int(np.flatnonzero(masks[env, 1:19])[0]) + 1
            else:
                choice = int(np.flatnonzero(masks[env])[0])
            if not masks[env, choice]:
                raise RuntimeError("devil smoke selected unavailable public choice")
            choices.append(choice)
        batch.step(np.column_stack((envs, episodes[envs, :4], np.asarray(choices, dtype=np.int64))))
        fingerprint()
    else:
        raise RuntimeError("devil smoke first-turn decision bound exceeded")
    episodes = batch.episode_snapshot()
    players = batch.diagnostic_players()
    families = batch.attack_family_snapshot()
    if (
        np.any(episodes[:, 4] != 1)
        or np.any(episodes[:, 3] == 13)
        or families[:, 13:].any()
        or players[:, 1:, 5].any()
    ):
        raise RuntimeError("devil smoke first-turn scheduling or queue accounting differs")
    counts = batch.devil_model_counts().sum(axis=0)
    return FullGameDevilSmokeReport(
        metadata_sha256=hashlib.sha256(configured.metadata.model_dump_json().encode()).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        statistic_totals=tuple(int(v) for v in batch.devil_snapshot().sum(axis=0)),
        model_counts=tuple(int(v) for v in counts),
        observed_devil_models=int(np.count_nonzero(counts)),
        commands=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        original_owner_ticks=int(players[:, 0, 5].sum()),
        automatic_gifts=batch.automatic_gift_count,
        initial_gifts=9 * player_count * batch_size,
        devil_hp_damage=batch.devil_hp_damage,
        devil_removed_cards=batch.devil_removed_count,
    )
