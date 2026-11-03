"""Held-out local candidate evaluation with one assignment per native faction."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import create_development_full_game_batch
from godfield_bot.full_game_greedy import GREEDY_POLICY_SHA256, FullGameGreedyPolicy
from godfield_bot.full_game_neural import (
    FullGameActorCritic,
    FullGamePolicyController,
    transfer_full_game_attack_history,
)
from godfield_bot.full_game_rollout import full_game_policy_sha256
from godfield_bot.full_game_training import load_full_game_candidate

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameFactionEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    candidate_seats: tuple[int, ...]
    wins: Count
    losses: Count
    draws: Count
    turn_limits: Count
    decision_limits: Count
    accepted_decisions: Count


class FullGameFrozenEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    evaluation: Literal[
        "held-out-native-each-faction-vs-initial-policy-v1",
        "held-out-native-each-faction-vs-checkpoint-v1",
        "held-out-native-each-faction-vs-public-greedy-v1",
    ] = "held-out-native-each-faction-vs-initial-policy-v1"
    candidate_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_seed: int
    sampling_seed: int
    games_per_faction: int = Field(ge=1, le=64, strict=True)
    factions: tuple[FullGameFactionEvaluation, ...]
    wins: Count
    losses: Count
    draws: Count
    truncations: Count
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def account_for_games(self) -> FullGameFrozenEvaluation:
        seats = [seat for faction in self.factions for seat in faction.candidate_seats]
        if (
            len(self.factions) < 2
            or (
                self.evaluation == "held-out-native-each-faction-vs-public-greedy-v1"
                and self.baseline_policy_sha256 != GREEDY_POLICY_SHA256
            )
            or sorted(seats) != list(range(len(seats)))
            or any(
                not faction.candidate_seats
                or (
                    faction.wins
                    + faction.losses
                    + faction.draws
                    + faction.turn_limits
                    + faction.decision_limits
                    != self.games_per_faction
                )
                for faction in self.factions
            )
            or self.wins != sum(f.wins for f in self.factions)
            or self.losses != sum(f.losses for f in self.factions)
            or self.draws != sum(f.draws for f in self.factions)
            or self.truncations != sum(f.turn_limits + f.decision_limits for f in self.factions)
        ):
            raise ValueError("full-game frozen evaluation accounting differs")
        return self


def evaluate_full_game_candidate(
    directory: Path,
    *,
    catalog_path: Path,
    bible_path: Path,
    seed: int = 100_000,
    games_per_faction: int = 16,
    baseline_directory: Path | None = None,
    greedy_baseline: bool = False,
) -> FullGameFrozenEvaluation:
    if (
        type(seed) is not int
        or not 0 <= seed < 2**63 - 1
        or type(games_per_faction) is not int
        or not 1 <= games_per_faction <= 64
        or type(greedy_baseline) is not bool
        or (greedy_baseline and baseline_directory is not None)
    ):
        raise ValueError(
            "full-game frozen evaluation seed, batch size or baseline selection differs"
        )
    manifest, candidate = load_full_game_candidate(directory)
    training = manifest.training
    config = training.config
    exclude = {"batch_size", "seed"}
    environment = training.initial_collection.environment.model_dump(exclude=exclude)
    baseline = None
    baseline_source_hash = None
    used_seeds = training.used_seeds()
    if baseline_directory is not None:
        baseline_manifest, baseline = load_full_game_candidate(baseline_directory)
        baseline_training = baseline_manifest.training
        baseline_source_hash = baseline_training.final_policy_sha256
        if candidate.architecture.schema_version == 2 and baseline.architecture.schema_version == 1:
            baseline = transfer_full_game_attack_history(baseline)
        if (
            baseline.architecture != candidate.architecture
            or baseline_training.initial_collection.environment.model_dump(exclude=exclude)
            != environment
        ):
            raise ValueError("full-game evaluation baseline architecture or ruleset differs")
        used_seeds.update(baseline_training.used_seeds())
    elif training.initialization is not None and not greedy_baseline:
        raise ValueError(
            "full-game transferred candidate requires an explicit --baseline checkpoint"
        )
    if used_seeds.intersection((seed, seed + 1)):
        raise ValueError("full-game frozen evaluation requires held-out seeds")
    teams = config.teams or (0,) * config.player_count
    factions: dict[tuple[str, int], list[int]] = {}
    for seat, team in enumerate(teams):
        key = ("team", team) if team else ("solo", seat)
        factions.setdefault(key, []).append(seat)
    if len(factions) < 2:
        raise ValueError("full-game frozen evaluation requires at least two factions")
    previous_threads = torch.get_num_threads()
    results = []
    try:
        torch.set_num_threads(config.cpu_threads)
        if baseline is None and not greedy_baseline:
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(config.seed)
                baseline = FullGameActorCritic(config.architecture).float().cpu().eval()
            if (
                full_game_policy_sha256(baseline)
                != training.initial_collection.behavior_policy_sha256
            ):
                raise ValueError(
                    "full-game evaluation could not reproduce the frozen initial weights"
                )
        baseline_hash = (
            full_game_policy_sha256(baseline) if baseline is not None else GREEDY_POLICY_SHA256
        )
        for candidate_seats in factions.values():
            configured = create_development_full_game_batch(
                catalog_path=catalog_path,
                bible_path=bible_path,
                batch_size=games_per_faction,
                player_count=config.player_count,
                teams=teams,
                capacity=18,
                acquisition_mode="all-held-weighted",
                seed=seed,
                max_turns=config.max_turns,
                max_decisions=config.max_decisions,
                apocalypse_after_turns=config.apocalypse_after_turns,
            )
            if configured.metadata.model_dump(exclude=exclude) != environment:
                raise ValueError("full-game evaluation source or ruleset differs from training")
            controller = FullGamePolicyController(
                configured,
                candidate,
                seed=seed + 1,
                opponent=baseline
                if baseline is not None
                else FullGameGreedyPolicy(configured.metadata),
                opponent_seats=tuple(
                    i for i in range(config.player_count) if i not in candidate_seats
                ),
            )
            batch = configured.batch
            batch.start_environments(np.arange(games_per_faction, dtype=np.int64))
            for _ in range(config.max_decisions):
                active = np.flatnonzero(batch.choice_masks().any(axis=1)).astype(np.int64)
                if not len(active):
                    break
                controller.step(active)
            controller.poll_rewards()
            state = batch.episode_snapshot()
            if not np.isin(state[:, 3], (12, 13)).all():
                raise RuntimeError("full-game frozen evaluation ended with active episodes")
            wins = int(batch.winning_seats()[:, candidate_seats].any(axis=1).sum())
            results.append(
                FullGameFactionEvaluation(
                    candidate_seats=tuple(candidate_seats),
                    wins=wins,
                    losses=int((state[:, 5] == 1).sum()) - wins,
                    draws=int((state[:, 5] == 2).sum()),
                    turn_limits=int((state[:, 5] == 3).sum()),
                    decision_limits=int((state[:, 5] == 4).sum()),
                    accepted_decisions=int(state[:, 7].sum()),
                )
            )
        candidate_hash = full_game_policy_sha256(candidate)
        if candidate_hash != training.final_policy_sha256 or (
            baseline is not None and full_game_policy_sha256(baseline) != baseline_hash
        ):
            raise RuntimeError("full-game evaluation changed a frozen policy")
    finally:
        torch.set_num_threads(previous_threads)
    return FullGameFrozenEvaluation(
        evaluation=(
            "held-out-native-each-faction-vs-public-greedy-v1"
            if greedy_baseline
            else "held-out-native-each-faction-vs-checkpoint-v1"
            if baseline_directory is not None
            else "held-out-native-each-faction-vs-initial-policy-v1"
        ),
        candidate_policy_sha256=candidate_hash,
        baseline_policy_sha256=baseline_source_hash or baseline_hash,
        training_environment_sha256=training.initial_collection.encoder.environment_metadata_sha256,
        environment_seed=seed,
        sampling_seed=seed + 1,
        games_per_faction=games_per_faction,
        factions=tuple(results),
        wins=sum(r.wins for r in results),
        losses=sum(r.losses for r in results),
        draws=sum(r.draws for r in results),
        truncations=sum(r.turn_limits + r.decision_limits for r in results),
    )
