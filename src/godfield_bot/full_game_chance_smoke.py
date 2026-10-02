"""One source-pinned chance cast per environment; not learning or full matches."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch

Count = Annotated[int, Field(ge=0, strict=True)]
Positive = Annotated[int, Field(ge=1, strict=True)]
CHANCE_SHA256: Final = "fed7e6d50a4761ffff8e81c338b42abb27e4423482c58dbd9395393028e8e3e1"


class FullGameChanceSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    source_kind: Literal["integrated-development-one-turn-chance-smoke-v2"] = (
        "integrated-development-one-turn-chance-smoke-v2"
    )
    ruleset_id: Literal["integrated-full-game-development-v7"] = FULL_GAME_RULESET_ID
    scenario: Literal["one-standalone-chance-per-environment-forgive-hits-not-full-matches"] = (
        "one-standalone-chance-per-environment-forgive-hits-not-full-matches"
    )
    chance_profile_sha256: Literal[
        "fed7e6d50a4761ffff8e81c338b42abb27e4423482c58dbd9395393028e8e3e1"
    ] = CHANCE_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    result_fields: tuple[str, ...] = ("model", "hit_rate", "casts", "hits", "misses")
    model_results: tuple[tuple[Positive, Positive, Count, Count, Count], ...]
    observed_model_count: int = Field(ge=1, le=24, strict=True)
    chance_casts: Count
    hits: Count
    misses: Count
    actions: Count
    completed_turns: Count
    resolved_attacks: Count
    real_terminal_endings: Count
    ready_after_one_turn: Count
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
    def source_and_count_accounting(self) -> FullGameChanceSmokeReport:
        profiles = tuple((model, rate) for model, rate, *_ in self.model_results)
        profile_sha = hashlib.sha256(
            json.dumps(profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            profile_sha != self.chance_profile_sha256
            or len(profiles) != 24
            or self.result_fields != ("model", "hit_rate", "casts", "hits", "misses")
            or any(casts != hits + misses for _, _, casts, hits, misses in self.model_results)
            or sum(casts for _, _, casts, _, _ in self.model_results) != self.chance_casts
            or sum(hits for _, _, _, hits, _ in self.model_results) != self.hits
            or sum(misses for _, _, _, _, misses in self.model_results) != self.misses
            or sum(casts > 0 for _, _, casts, _, _ in self.model_results)
            != self.observed_model_count
            or self.chance_casts != self.batch_size
            or self.hits + self.misses != self.batch_size
            or self.resolved_attacks != self.batch_size
            or self.completed_turns != self.batch_size
            or self.actions != 2 * self.batch_size + self.hits
            or self.consumed_cards + self.retained_miracle_uses != self.batch_size
            or self.real_terminal_endings + self.ready_after_one_turn != self.batch_size
        ):
            raise ValueError("chance smoke source profiles or one-turn accounting differs")
        return self


def run_full_game_chance_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 504,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameChanceSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("chance smoke batch size must be 1 through 4096")
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
    profiles = configured.metadata.plan.combat.chance_profiles
    models = [profiles[env % len(profiles)][0] for env in range(batch_size)]
    for env, model in enumerate(models):
        batch.seed_hand(env, 0, np.asarray([(1, model, 0, 0)], dtype=np.int64))
    batch.start_environments(np.arange(batch_size, dtype=np.int64))
    digest = hashlib.sha256()

    def fingerprint() -> None:
        # Diagnostics prove replay; action selection below never reads true hands/resources.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_inventory(),
            batch.diagnostic_players(),
            batch.choice_masks(),
            batch.pending_observations(),
            batch.chance_observations(),
            batch.chance_snapshot(),
            batch.attack_effect_observations(),
            batch.attack_effect_snapshot(),
        ):
            digest.update(view.astype("<i8", copy=False).tobytes())

    def command(envs: list[int], choice: int) -> None:
        episodes = batch.episode_snapshot()
        batch.step(
            np.asarray([(env, *episodes[env, :4], choice) for env in envs], dtype=np.int64).reshape(
                -1, 6
            )
        )
        fingerprint()

    fingerprint()
    command(list(range(batch_size)), 1)  # Reserve the only owned card.
    command(list(range(batch_size)), 0)  # Native chance cast; no caller target or roll.
    responders = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
    command(responders, 0)  # Real defense confirmation on hits only, not fabricated miss defense.
    episodes = batch.episode_snapshot()
    if not np.all(np.isin(episodes[:, 3], (1, 12))) or not np.all(episodes[:, 4] == 1):
        raise RuntimeError("chance smoke did not finish exactly one turn per environment")
    results = batch.chance_snapshot()
    totals = {model: np.zeros(3, dtype=np.int64) for model, _ in profiles}
    for model, result in zip(models, results, strict=True):
        totals[model] += result
    metadata_sha = hashlib.sha256(
        json.dumps(
            configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return FullGameChanceSmokeReport(
        metadata_sha256=metadata_sha,
        diagnostic_replay_sha256=digest.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        model_results=tuple(
            (model, rate, int(totals[model][0]), int(totals[model][1]), int(totals[model][2]))
            for model, rate in profiles
        ),
        observed_model_count=int(sum(value[0] > 0 for value in totals.values())),
        chance_casts=batch.chance_count,
        hits=batch.chance_hit_count,
        misses=batch.chance_miss_count,
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        resolved_attacks=batch.resolved_attack_count,
        real_terminal_endings=int(np.count_nonzero(episodes[:, 3] == 12)),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
        hp_damage=batch.hp_damage,
        mp_spent=batch.mp_spent,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
    )
