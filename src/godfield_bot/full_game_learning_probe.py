"""Reproducible roster-wide collection, replay and terminal-PPO integration probes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Annotated, Any, Literal

import numpy as np
import numpy.typing as npt
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import DevelopmentFullGameBatch, create_development_full_game_batch
from godfield_bot.full_game_diagnostics import NATIVE_VIEWS, PHASES, FullGameNativeDiagnostic
from godfield_bot.full_game_neural import FullGameActorCritic, FullGamePolicyArchitecture
from godfield_bot.full_game_observation import CARD_PROPERTIES_OBSERVATION_ID
from godfield_bot.full_game_replay import verify_full_game_behavior
from godfield_bot.full_game_rollout import (
    FullGameEpisodeCollection,
    collect_full_game_episodes,
    full_game_policy_sha256,
)
from godfield_bot.full_game_training import (
    FullGameTrainingConfig,
    FullGameTrainingReport,
    FullGameTrainingUpdate,
    train_full_game_ppo,
)

Layout = Literal["solo", "two-teams", "mixed-solo", "four-teams"]
LAYOUTS: tuple[Layout, ...] = ("solo", "two-teams", "mixed-solo", "four-teams")
Count = Annotated[int, Field(ge=0, strict=True)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def probe_teams(players: int, layout: Layout) -> tuple[int, ...]:
    return tuple(
        {
            "solo": 0,
            "two-teams": 1 + seat % 2,
            "mixed-solo": 0 if seat % 2 else 1,
            "four-teams": 1 + seat % 4,
        }[layout]
        for seat in range(players)
    )


class FullGameLearningProbeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    player_counts: tuple[Annotated[int, Field(ge=2, le=9, strict=True)], ...] = tuple(range(2, 10))
    layouts: tuple[Layout, ...] = LAYOUTS
    games_per_batch: int = Field(default=4, ge=1, le=16, strict=True)
    seed: int = Field(default=1400000, ge=0, lt=2**63 - 1024, strict=True)
    max_turns: int = Field(default=256, ge=1, le=1000, strict=True)
    max_decisions: int = Field(default=2048, ge=1, le=2048, strict=True)
    apocalypse_after_turns: int = Field(default=64, ge=0, le=1000, strict=True)

    @model_validator(mode="after")
    def unique_cases(self) -> FullGameLearningProbeConfig:
        if (
            not self.player_counts
            or tuple(sorted(set(self.player_counts))) != self.player_counts
            or not self.layouts
            or len(set(self.layouts)) != len(self.layouts)
        ):
            raise ValueError("learning probe requires distinct ordered player counts and layouts")
        return self

    def training_config(self, players: int, layout: Layout) -> FullGameTrainingConfig:
        # Stable seeds even when running a subset or reordering layouts.
        case = (players - 2) * len(LAYOUTS) + LAYOUTS.index(layout)
        return FullGameTrainingConfig(
            batch_size=self.games_per_batch,
            player_count=players,
            teams=probe_teams(players, layout),
            updates=2,
            seed=self.seed + 4 * case,
            max_turns=self.max_turns,
            max_decisions=self.max_decisions,
            apocalypse_after_turns=self.apocalypse_after_turns,
            architecture=FullGamePolicyArchitecture(
                schema_version=3, observation_id=CARD_PROPERTIES_OBSERVATION_ID
            ),
        )


class FullGameLearningProbeBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    collection_sha256: Digest
    repeated_collection_sha256: Digest
    terminal_phase_counts: tuple[Count, ...]
    native: tuple[FullGameNativeDiagnostic, ...]

    @model_validator(mode="after")
    def layouts(self) -> FullGameLearningProbeBatch:
        if (
            len(self.terminal_phase_counts) != 14
            or any(self.terminal_phase_counts[i] for i in range(14) if i not in PHASES)
            or tuple(row.view for row in self.native) != tuple(NATIVE_VIEWS)
        ):
            raise ValueError("learning probe phase or native diagnostic layout differs")
        return self


class FullGameLearningProbeCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    layout: Layout
    training: FullGameTrainingReport
    batches: tuple[FullGameLearningProbeBatch, ...]
    passed: bool = Field(strict=True)

    @model_validator(mode="after")
    def accounting(self) -> FullGameLearningProbeCase:
        config = self.training.config
        if (
            config.updates != 2
            or config.teams != probe_teams(config.player_count, self.layout)
            or len(self.batches) != len(self.training.updates)
            or self.passed != _case_passed(self.training, self.batches)
            or any(
                sum(batch.terminal_phase_counts) != update.terminal_target_decisions
                for batch, update in zip(self.batches, self.training.updates, strict=True)
            )
        ):
            raise ValueError("learning probe roster or terminal sample accounting differs")
        return self


def _case_passed(
    training: FullGameTrainingReport, batches: tuple[FullGameLearningProbeBatch, ...]
) -> bool:
    return len(batches) == 2 and all(
        batch.collection_sha256 == batch.repeated_collection_sha256
        and update.collection_error is None
        and update.metrics is not None
        and update.metrics.gradient_norm > 0
        and update.actor_decisions > 0
        and update.policy_sha256 != update.behavior_policy_sha256
        for batch, update in zip(batches, training.updates, strict=True)
    )


class FullGameLearningProbeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    scope: Literal["roster-replay-and-optimization-not-strength-or-complete-mechanic-coverage"] = (
        "roster-replay-and-optimization-not-strength-or-complete-mechanic-coverage"
    )
    native_scope: Literal["all-seats-final-collection-rows-including-excluded-episodes"] = (
        "all-seats-final-collection-rows-including-excluded-episodes"
    )
    repetition: Literal["fresh-native-state-identical-frozen-policy-and-seeds-no-second-update"] = (
        "fresh-native-state-identical-frozen-policy-and-seeds-no-second-update"
    )
    config: FullGameLearningProbeConfig
    cases: tuple[FullGameLearningProbeCase, ...]
    passed: bool = Field(strict=True)
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def case_matrix(self) -> FullGameLearningProbeReport:
        expected = [
            (n, layout) for n in self.config.player_counts for layout in self.config.layouts
        ]
        if (
            self.passed != all(case.passed for case in self.cases)
            or len(self.cases) != len(expected)
            or any(
                case.layout != layout
                or case.training.config != self.config.training_config(n, layout)
                for case, (n, layout) in zip(self.cases, expected, strict=True)
            )
        ):
            raise ValueError("learning probe case matrix differs from its configuration")
        return self


def _final_native(configured: DevelopmentFullGameBatch) -> tuple[FullGameNativeDiagnostic, ...]:
    result = []
    for getter, columns in NATIVE_VIEWS.items():
        values = getattr(configured.batch, getter)()
        shape = (
            (configured.metadata.batch_size, configured.metadata.player_count, len(columns))
            if getter == "acquisition_snapshot"
            else (configured.metadata.batch_size, len(columns))
        )
        if values.shape != shape or values.dtype != np.int64 or np.any(values < 0):
            raise ValueError(f"learning probe native diagnostic layout differs: {getter}")
        result.append(
            FullGameNativeDiagnostic(
                view=getter,
                fields=columns,
                totals=tuple(int(v) for v in values.reshape(-1, len(columns)).sum(0)),
            )
        )
    return tuple(result)


def _collection_digest(
    collection: FullGameEpisodeCollection, configured: DevelopmentFullGameBatch
) -> str:
    """Include every retained public row plus final private state, never policy input."""
    digest = hashlib.sha256(collection.metadata.model_dump_json().encode())

    def array(name: str, value: npt.NDArray[Any]) -> None:
        digest.update(json.dumps((name, value.shape, value.dtype.str)).encode())
        digest.update(value.tobytes(order="C"))

    digest.update(json.dumps(collection.collection_error).encode())
    array("rejected", collection.rejected_commands)
    for episode in collection.episodes:
        digest.update(episode.outcome.model_dump_json().encode())
        if episode.samples is not None:
            for field in fields(episode.samples.observation):
                array(field.name, getattr(episode.samples.observation, field.name))
            for field in fields(episode.samples):
                if field.name != "observation":
                    array(field.name, getattr(episode.samples, field.name))
    for getter in (
        "episode_snapshot",
        "diagnostic_players",
        "diagnostic_inventory",
        "guardian_snapshot",
        "team_ids",
        "winning_seats",
        "attack_history_observations",
        *NATIVE_VIEWS,
    ):
        array(getter, getattr(configured.batch, getter)())
    return digest.hexdigest()


def _run_case(
    catalog_path: Path, bible_path: Path, config: FullGameTrainingConfig, layout: Layout
) -> FullGameLearningProbeCase:
    torch.manual_seed(config.seed)
    policy = FullGameActorCritic(config.architecture).float().cpu()
    optimizer = torch.optim.Adam(policy.parameters(), lr=config.ppo.learning_rate)
    initial = None
    updates, batches = [], []
    for index in range(config.updates):
        seed = config.seed + 2 * index

        def create(seed: int = seed) -> DevelopmentFullGameBatch:
            return create_development_full_game_batch(
                catalog_path=catalog_path,
                bible_path=bible_path,
                batch_size=config.batch_size,
                player_count=config.player_count,
                teams=config.teams,
                capacity=18,
                acquisition_mode="all-held-weighted",
                seed=seed,
                max_turns=config.max_turns,
                max_decisions=config.max_decisions,
                apocalypse_after_turns=config.apocalypse_after_turns,
            )

        configured = create()
        collection = collect_full_game_episodes(configured, policy, sampling_seed=seed + 1)
        verify_full_game_behavior(collection, policy)
        first_digest = _collection_digest(collection, configured)
        native = _final_native(configured)
        repeated = create()
        again = collect_full_game_episodes(repeated, policy, sampling_seed=seed + 1)
        verify_full_game_behavior(again, policy)
        repeated_digest = _collection_digest(again, repeated)
        del again, repeated
        if initial is None:
            initial = collection.metadata
        phase_counts = np.zeros(14, dtype=np.int64)
        for episode in collection.episodes:
            if episode.samples is not None:
                phase_counts += np.bincount(episode.samples.commands[:, 4], minlength=14)
        metrics = None
        if collection.collection_error is None and collection.eligible_decisions:
            metrics = train_full_game_ppo(policy, optimizer, collection, config.ppo)
        updates.append(
            FullGameTrainingUpdate(
                environment_seed=seed,
                sampling_seed=seed + 1,
                outcomes=tuple(e.outcome for e in collection.episodes),
                accepted_decisions=collection.accepted_decisions,
                terminal_target_decisions=collection.eligible_decisions,
                actor_decisions=collection.eligible_policy_decisions,
                behavior_policy_sha256=collection.metadata.behavior_policy_sha256,
                initial_state_sha256=collection.metadata.initial_state_sha256,
                policy_sha256=full_game_policy_sha256(policy),
                metrics=metrics,
                collection_error=collection.collection_error,
                rejected_commands=tuple(
                    tuple(int(v) for v in row) for row in collection.rejected_commands
                ),
            )
        )
        batches.append(
            FullGameLearningProbeBatch(
                collection_sha256=first_digest,
                repeated_collection_sha256=repeated_digest,
                terminal_phase_counts=tuple(int(v) for v in phase_counts),
                native=native,
            )
        )
        if collection.collection_error is not None:
            break
    assert initial is not None
    training = FullGameTrainingReport(
        config=config,
        initial_collection=initial,
        updates=tuple(updates),
        final_policy_sha256=full_game_policy_sha256(policy),
    )
    return FullGameLearningProbeCase(
        layout=layout,
        batches=tuple(batches),
        training=training,
        passed=_case_passed(training, tuple(batches)),
    )


def run_full_game_learning_probe(
    *,
    catalog_path: Path,
    bible_path: Path,
    config: FullGameLearningProbeConfig | None = None,
    on_case: Callable[[FullGameLearningProbeCase], None] | None = None,
) -> FullGameLearningProbeReport:
    config = FullGameLearningProbeConfig.model_validate(
        config.model_dump() if config is not None else {}
    )
    previous_threads = torch.get_num_threads()
    cases = []
    try:
        torch.set_num_threads(2)
        with torch.random.fork_rng(devices=[]):
            for players in config.player_counts:
                for layout in config.layouts:
                    case = _run_case(
                        catalog_path, bible_path, config.training_config(players, layout), layout
                    )
                    cases.append(case)
                    if on_case is not None:
                        on_case(case)
    finally:
        torch.set_num_threads(previous_threads)
    return FullGameLearningProbeReport(
        config=config, cases=tuple(cases), passed=all(case.passed for case in cases)
    )
