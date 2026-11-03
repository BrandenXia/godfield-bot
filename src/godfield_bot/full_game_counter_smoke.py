"""Deterministic one-family counter diagnostic, not full matches or training."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import FULL_GAME_RULESET_ID, create_development_full_game_batch

Count = Annotated[int, Field(ge=0, strict=True)]
DEFENSE_EFFECT_SHA256: Final = "c984180f2027ee4d0899917582509378efd5657e7c94c050274ca7ebaab90044"


class FullGameCounterSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[17] = 17
    source_kind: Literal["integrated-development-one-family-counter-smoke-v3"] = (
        "integrated-development-one-family-counter-smoke-v3"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["one-ring-per-environment-cloud-forced-hit-forgiven-not-full-matches"] = (
        "one-ring-per-environment-cloud-forced-hit-forgiven-not-full-matches"
    )
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    defense_effect_profile_sha256: Literal[
        "c984180f2027ee4d0899917582509378efd5657e7c94c050274ca7ebaab90044"
    ] = DEFENSE_EFFECT_SHA256
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    model_results: tuple[tuple[int, int, Count], ...]
    actions: Count
    completed_turns: Count
    original_attacks: Count
    original_resolutions: Count
    counters: Count
    counter_resolutions: Count
    counter_misses: Literal[0] = 0
    dead_suppressed_counters: Literal[0] = 0
    final_queued_counters: Literal[0] = 0
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    ready_after_one_family: Count
    attack_hp_damage: Count
    counter_hp_damage: Count
    mp_gained: Count
    cp_credited: Count
    cp_spill_hp_damage: Literal[0] = 0
    consumed_cards: Count
    real_terminal_endings: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def one_family_accounting(self) -> FullGameCounterSmokeReport:
        if (
            tuple((model, kind) for model, kind, _ in self.model_results)
            != ((181, 1), (182, 2), (183, 2), (184, 1), (185, 2), (186, 2), (187, 3), (188, 4))
            or sum(count for _, _, count in self.model_results) != self.batch_size
            or any(
                count != (self.batch_size + 7 - index) // 8
                for index, (_, _, count) in enumerate(self.model_results)
            )
            or any(
                count != self.batch_size
                for count in (
                    self.completed_turns,
                    self.original_attacks,
                    self.original_resolutions,
                    self.counters,
                    self.counter_resolutions,
                    self.original_owner_ticks,
                    self.ready_after_one_family,
                )
            )
            or self.actions != 6 * self.batch_size
            or self.consumed_cards != 2 * self.batch_size
            or self.counter_hp_damage
            != sum(
                (10 if model == 181 else 20 if model == 184 else 0) * count
                for model, _, count in self.model_results
            )
            or self.attack_hp_damage != 10 * self.batch_size + self.counter_hp_damage
            or self.mp_gained != 20 * self.model_results[6][2]
            or self.cp_credited != 10 * self.model_results[7][2]
        ):
            raise ValueError("counter smoke source identities or one-family accounting differs")
        return self


def run_full_game_counter_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameCounterSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("counter smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=2,
        seed=seed,
        max_turns=2,
        max_decisions=8,
        initial_hp=100,
        initial_mp=30,
        initial_cp=3,
    )
    batch = configured.batch
    profiles = configured.metadata.plan.combat.defense_effect_profiles
    rings = tuple(row for row in profiles if row[1] <= 4)
    if (
        hashlib.sha256(json.dumps(profiles, separators=(",", ":")).encode()).hexdigest()
        != DEFENSE_EFFECT_SHA256
    ):
        raise ValueError("counter smoke defense profiles differ from pinned sources")
    environments = np.arange(batch_size, dtype=np.int64)
    batch.seed_players(
        environments,
        np.zeros(batch_size, dtype=np.int64),
        np.tile(np.asarray([100, 30, 3, 1], dtype=np.int64), (batch_size, 1)),
        np.full(batch_size, 8, dtype=np.int64),  # Explicit diagnostic forced Mars hit.
    )
    models = [rings[env % len(rings)][0] for env in range(batch_size)]
    for env, model in enumerate(models):
        batch.seed_hand(env, 0, np.asarray([[1, 35, 0, 0]], dtype=np.int64))
        batch.seed_hand(env, 1, np.asarray([[2, model, 0, 0]], dtype=np.int64))
    batch.start_environments(environments)
    digest = hashlib.sha256()

    def fingerprint() -> None:
        # Replay diagnostics only; the scripted choices never read hidden state.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_inventory(),
            batch.diagnostic_players(),
            batch.actor_hands(),
            batch.player_observations(),
            batch.choice_masks(),
            batch.pending_observations(),
            batch.defense_order(),
            batch.counter_observations(),
            batch.counter_snapshot(),
            batch.attack_effect_snapshot(),
            batch.chance_snapshot(),
        ):
            digest.update(view.astype("<i8", copy=False).tobytes())

    fingerprint()
    for choice in (1, 0, 4, 1, 0, 0):
        episodes = batch.episode_snapshot()
        masks = batch.choice_masks()
        if not np.all(masks[:, choice]):
            raise RuntimeError("counter smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (environments, episodes[:, :4], np.full(batch_size, choice, dtype=np.int64))
            )
        )
        fingerprint()
    episodes = batch.episode_snapshot()
    players = batch.diagnostic_players()
    counters = batch.counter_snapshot()
    if any(
        (
            batch.counter_miss_count,
            batch.suppressed_counter_count,
            int(counters[:, 11].sum()),
            int(players[:, 1:, 5].sum()),
            int(counters[:, 8].sum()),
            int(np.count_nonzero(episodes[:, 3] == 12)),
        )
    ):
        raise RuntimeError(
            "counter smoke produced unexpected miss, suppression, tick, spill or ending"
        )
    return FullGameCounterSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=digest.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        model_results=tuple((model, kind, models.count(model)) for model, kind, *_ in rings),
        actions=batch.action_count,
        completed_turns=int(episodes[:, 4].sum()),
        original_attacks=batch.attack_count,
        original_resolutions=batch.resolved_attack_count,
        counters=batch.counter_count,
        counter_resolutions=batch.resolved_counter_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        ready_after_one_family=int(np.count_nonzero(episodes[:, 3] == 1)),
        attack_hp_damage=batch.hp_damage,
        counter_hp_damage=int(counters[:, 5].sum()),
        mp_gained=int(counters[:, 6].sum()),
        cp_credited=int(counters[:, 7].sum()),
        consumed_cards=batch.consumed_count,
    )
