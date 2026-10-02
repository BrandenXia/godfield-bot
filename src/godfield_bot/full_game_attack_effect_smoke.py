"""Bounded, intentionally forced-hit effect probe; never full games or training."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch

Count = Annotated[int, Field(ge=0, strict=True)]
Positive = Annotated[int, Field(ge=1, strict=True)]
ATTACK_EFFECT_SHA256: Final = "643e097f239903060e7b022a5367467c03199de895fd4439c2b74cc25f74a781"


class FullGameAttackEffectSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["integrated-development-one-turn-attack-effect-smoke-v1"] = (
        "integrated-development-one-turn-attack-effect-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v7"] = FULL_GAME_RULESET_ID
    scenario: Literal["one-effect-per-environment-cloud-forced-hits-forgiven-not-full-matches"] = (
        "one-effect-per-environment-cloud-forced-hits-forgiven-not-full-matches"
    )
    attack_effect_profile_sha256: Literal[
        "643e097f239903060e7b022a5367467c03199de895fd4439c2b74cc25f74a781"
    ] = ATTACK_EFFECT_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    result_fields: tuple[str, ...] = ("model", "kind", "value", "casts")
    model_results: tuple[tuple[Positive, Positive, Count, Count], ...]
    observed_model_count: int = Field(ge=1, le=20, strict=True)
    actions: Count
    completed_turns: Count
    attacks_cast: Count
    resolved_attacks: Count
    ready_after_one_turn: Count
    real_terminal_endings: Literal[0] = 0
    chance_casts: Count
    dark_cloud_hits: Count
    absorption_count: Count
    absorbed_hp: Count
    inflicted_curses: Count
    inflicted_illnesses: Count
    illness_effect_damage: Literal[0] = 0
    hp_damage: Count
    mp_spent: Count
    consumed_cards: Count
    retained_miracle_uses: Count
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def source_and_count_accounting(self) -> FullGameAttackEffectSmokeReport:
        profiles = tuple(row[:3] for row in self.model_results)
        digest = hashlib.sha256(json.dumps(profiles, separators=(",", ":")).encode()).hexdigest()
        if (
            digest != self.attack_effect_profile_sha256
            or self.result_fields != ("model", "kind", "value", "casts")
            or len(profiles) != 20
            or sum(row[3] for row in self.model_results) != self.batch_size
            or sum(row[3] > 0 for row in self.model_results) != self.observed_model_count
            or self.completed_turns != self.batch_size
            or self.attacks_cast != self.batch_size
            or self.resolved_attacks != self.batch_size
            or self.ready_after_one_turn != self.batch_size
            or self.actions != 4 * self.batch_size - self.chance_casts
            or self.chance_casts != self.dark_cloud_hits
            or self.absorption_count + self.inflicted_curses + self.inflicted_illnesses
            != self.batch_size
            or self.absorption_count != sum(n for _, kind, _, n in self.model_results if kind == 1)
            or self.inflicted_curses
            != sum(n for _, kind, _, n in self.model_results if kind in (2, 4))
            or self.inflicted_illnesses
            != sum(n for _, kind, _, n in self.model_results if kind in (3, 5))
            or self.chance_casts
            != sum(n for model, _, _, n in self.model_results if model in (97, 98, 224))
            or self.consumed_cards + self.retained_miracle_uses != self.batch_size
            or self.consumed_cards != sum(n for model, _, _, n in self.model_results if model < 210)
            or self.retained_miracle_uses
            != sum(n for model, _, _, n in self.model_results if model >= 210)
            or self.absorbed_hp > self.hp_damage
            or self.absorbed_hp > 100 * self.absorption_count
            or self.mp_spent > 100 * self.retained_miracle_uses
        ):
            raise ValueError("attack effect smoke source profiles or one-turn accounting differs")
        return self


def run_full_game_attack_effect_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 640,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameAttackEffectSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("attack effect smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=2,
        seed=seed,
        max_turns=2,
        max_decisions=8,
        initial_mp=100,
    )
    batch = configured.batch
    profiles = configured.metadata.plan.combat.attack_effect_profiles
    models = [profiles[env % len(profiles)][0] for env in range(batch_size)]
    for env, model in enumerate(models):
        batch.seed_hand(env, 0, np.asarray([(1, model, 0, 0)], dtype=np.int64))
    envs = np.repeat(np.arange(batch_size, dtype=np.int64), player_count)
    owners = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    resources = np.tile((40, 100, 0, 0), (len(envs), 1)).astype(np.int64)
    resources[owners == 0, 3] = 1
    batch.seed_players(envs, owners, resources, np.where(owners == 0, 0, 8).astype(np.int64))
    batch.start_environments(np.arange(batch_size, dtype=np.int64))
    replay = hashlib.sha256()

    def fingerprint() -> None:
        # Diagnostics are replay checks only, never chosen actions or a learning dataset.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
            batch.choice_masks(),
            batch.pending_observations(),
            batch.chance_snapshot(),
            batch.attack_effect_observations(),
            batch.attack_effect_snapshot(),
        ):
            replay.update(view.astype("<i8", copy=False).tobytes())

    def command(environments: list[int], choice: int) -> None:
        episodes = batch.episode_snapshot()
        batch.step(
            np.asarray(
                [(env, *episodes[env, :4], choice) for env in environments], dtype=np.int64
            ).reshape(-1, 6)
        )
        fingerprint()

    fingerprint()
    command(list(range(batch_size)), 1)
    command(list(range(batch_size)), 0)
    targeted = np.flatnonzero(batch.episode_snapshot()[:, 3] == 3).tolist()
    command(targeted, 4)  # First living opponent, public fixed target choice only.
    if not np.all(batch.episode_snapshot()[:, 3] == 4):
        raise RuntimeError("forced-hit attack effect probe did not reach defense")
    command(list(range(batch_size)), 0)
    episodes = batch.episode_snapshot()
    if (
        not np.all(episodes[:, 3] == 1)
        or not np.all(episodes[:, 4] == 1)
        or batch.illness_effect_damage != 0
    ):
        raise RuntimeError("attack effect probe did not finish one turn per environment")
    counts = {model: models.count(model) for model, _, _ in profiles}
    return FullGameAttackEffectSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        model_results=tuple((model, kind, value, counts[model]) for model, kind, value in profiles),
        observed_model_count=sum(n > 0 for n in counts.values()),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        attacks_cast=batch.attack_count,
        resolved_attacks=batch.resolved_attack_count,
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
        chance_casts=batch.chance_count,
        dark_cloud_hits=batch.dark_cloud_hit_count,
        absorption_count=batch.absorption_count,
        absorbed_hp=batch.absorbed_hp,
        inflicted_curses=batch.inflicted_curse_count,
        inflicted_illnesses=batch.inflicted_illness_count,
        hp_damage=batch.hp_damage,
        mp_spent=batch.mp_spent,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
    )
