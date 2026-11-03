"""Bounded recurrent PPO on complete local full-game episodes."""

from __future__ import annotations

import copy
import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from uuid import uuid4

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator
from torch import Tensor, nn

from godfield_bot.full_game import create_development_full_game_batch
from godfield_bot.full_game_neural import (
    FullGameActorCritic,
    FullGamePolicyArchitecture,
    FullGamePolicyInputs,
    full_game_policy_inputs,
)
from godfield_bot.full_game_observation import FullGameObservation
from godfield_bot.full_game_replay import full_game_seat_sequences, verify_full_game_behavior
from godfield_bot.full_game_rollout import (
    FullGameCollectedOutcome,
    FullGameCollectionMetadata,
    FullGameEpisodeCollection,
    collect_full_game_episodes,
    full_game_policy_sha256,
)
from godfield_bot.simulation_training import PpoTrainingMetrics


class FullGamePpoConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    epochs: int = Field(default=2, ge=1, le=8, strict=True)
    sequence_length: int = Field(default=32, ge=1, le=128, strict=True)
    sequences_per_group: int = Field(default=16, ge=1, le=64, strict=True)
    learning_rate: float = Field(default=3e-4, gt=0, le=0.01, allow_inf_nan=False)
    clip_range: float = Field(default=0.2, gt=0, le=0.5, allow_inf_nan=False)
    value_weight: float = Field(default=0.5, gt=0, le=2, allow_inf_nan=False)
    entropy_weight: float = Field(default=0.01, ge=0, le=1, allow_inf_nan=False)
    max_gradient_norm: float = Field(default=0.5, gt=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_graph(self) -> FullGamePpoConfig:
        if self.sequence_length * self.sequences_per_group > 2048:
            raise ValueError("full-game PPO groups may contain at most 2048 decisions")
        return self


@dataclass(frozen=True)
class _TrainingTable:
    inputs: FullGamePolicyInputs
    actions: Tensor
    old_logs: Tensor
    old_values: Tensor
    memory: Tensor
    targets: Tensor
    actor_mask: Tensor
    windows: tuple[Tensor, ...]


def _training_table(collection: FullGameEpisodeCollection, length: int) -> _TrainingTable:
    complete = [e for e in collection.episodes if e.samples is not None]
    samples = [e.samples for e in complete if e.samples is not None]
    offsets = {}
    offset = 0
    for episode, table in zip(complete, samples, strict=True):
        offsets[episode.outcome.environment] = offset
        offset += len(table.commands)
    observation = FullGameObservation(
        **{
            field.name: np.concatenate([getattr(s.observation, field.name) for s in samples])
            for field in fields(FullGameObservation)
        }
    )
    windows = []
    for sequence in full_game_seat_sequences(collection):
        rows = sequence.rows + offsets[sequence.environment]
        for start in range(0, len(rows), length):
            windows.append(torch.from_numpy(rows[start : start + length]))
    return _TrainingTable(
        inputs=full_game_policy_inputs(observation),
        actions=torch.from_numpy(np.concatenate([s.commands[:, 5] for s in samples])),
        old_logs=torch.from_numpy(np.concatenate([s.behavior_log_probabilities for s in samples])),
        old_values=torch.from_numpy(np.concatenate([s.behavior_values for s in samples])),
        memory=torch.from_numpy(np.concatenate([s.previous_memory for s in samples])),
        targets=torch.from_numpy(np.concatenate([s.terminal_targets for s in samples])),
        actor_mask=torch.from_numpy(observation.policy_gradient_mask),
        windows=tuple(windows),
    )


def _unroll_group(
    policy: FullGameActorCritic, table: _TrainingTable, windows: tuple[Tensor, ...]
) -> tuple[Tensor, Tensor, Tensor]:
    # Each window starts at its stored behavior memory. Inside a window, the
    # current policy's differentiable GRU output feeds the next decision.
    state = table.memory[torch.stack([window[0] for window in windows])]
    rows_history, logits_history, value_history = [], [], []
    for time in range(max(len(window) for window in windows)):
        active = [i for i, window in enumerate(windows) if time < len(window)]
        positions = torch.tensor(active, dtype=torch.int64)
        rows = torch.stack([windows[i][time] for i in active])
        inputs = FullGamePolicyInputs(
            **{
                field.name: getattr(table.inputs, field.name)[rows]
                for field in fields(table.inputs)
            }
        )
        logits, values, memory = policy(inputs, state[positions])
        state = state.index_copy(0, positions, memory)
        rows_history.append(rows)
        logits_history.append(logits)
        value_history.append(values)
    return torch.cat(rows_history), torch.cat(logits_history), torch.cat(value_history)


def train_full_game_ppo(
    policy: FullGameActorCritic,
    optimizer: torch.optim.Adam,
    collection: FullGameEpisodeCollection,
    config: FullGamePpoConfig,
) -> PpoTrainingMetrics:
    """Apply one verified collection. Roll back policy and Adam on update failure."""
    verify_full_game_behavior(collection, policy)
    if not collection.eligible_decisions:
        raise ValueError("full-game PPO requires accepted decisions with real terminal targets")
    parameters = list(policy.parameters())
    owned = [p for group in optimizer.param_groups for p in group["params"]]
    if len(owned) != len(parameters) or {id(p) for p in owned} != {id(p) for p in parameters}:
        raise ValueError("full-game optimizer must own the current policy parameters")
    table = _training_table(collection, config.sequence_length)
    actor_count = max(1, collection.eligible_policy_decisions)
    value_count = collection.eligible_decisions
    advantages = table.targets - table.old_values
    previous_policy = copy.deepcopy(policy.state_dict())
    previous_optimizer = copy.deepcopy(optimizer.state_dict())
    totals = dict.fromkeys(PpoTrainingMetrics.model_fields, 0.0)
    try:
        for _ in range(config.epochs):
            optimizer.zero_grad(set_to_none=True)
            for start in range(0, len(table.windows), config.sequences_per_group):
                rows, logits, values = _unroll_group(
                    policy, table, table.windows[start : start + config.sequences_per_group]
                )
                old_values, targets = table.old_values[rows], table.targets[rows]
                clipped = old_values + (values - old_values).clamp(
                    -config.clip_range, config.clip_range
                )
                value_loss = (
                    0.5
                    * torch.maximum((values - targets).square(), (clipped - targets).square()).sum()
                    / value_count
                )
                actor_rows = table.actor_mask[rows]
                policy_loss, entropy, kl, clipped_fraction = (
                    values.new_zeros(()) for _ in range(4)
                )
                if bool(actor_rows.any()):
                    selected = rows[actor_rows]
                    logs = torch.log_softmax(logits[actor_rows], dim=1)
                    log_ratio = (
                        logs.gather(1, table.actions[selected, None])[:, 0]
                        - table.old_logs[selected]
                    )
                    ratio = log_ratio.exp()
                    adv = advantages[selected]
                    policy_loss = (
                        torch.maximum(
                            -ratio * adv,
                            -ratio.clamp(1 - config.clip_range, 1 + config.clip_range) * adv,
                        ).sum()
                        / actor_count
                    )
                    entropy = -(logs.exp() * logs).sum() / actor_count
                    kl = (ratio - 1 - log_ratio).sum() / actor_count
                    clipped_fraction = ((ratio - 1).abs() > config.clip_range).sum() / actor_count
                loss = (
                    policy_loss + config.value_weight * value_loss - config.entropy_weight * entropy
                )
                measured = dict(
                    total_loss=loss,
                    policy_loss=policy_loss,
                    value_loss=value_loss,
                    entropy=entropy,
                    approximate_kl=kl,
                    clip_fraction=clipped_fraction,
                )
                if any(not bool(torch.isfinite(value)) for value in measured.values()):
                    raise RuntimeError("full-game PPO produced non-finite loss or metrics")
                loss.backward()  # type: ignore[no-untyped-call]
                for key, value in measured.items():
                    totals[key] += float(value.detach())
            norm = nn.utils.clip_grad_norm_(
                parameters, config.max_gradient_norm, error_if_nonfinite=True
            )
            optimizer.step()
            full_game_policy_sha256(
                policy
            )  # Reject non-finite parameters before publishing an update.
            totals["gradient_norm"] += float(norm)
    except Exception:
        policy.load_state_dict(previous_policy)
        optimizer.load_state_dict(previous_optimizer)
        optimizer.zero_grad(set_to_none=True)
        raise
    return PpoTrainingMetrics(**{key: value / config.epochs for key, value in totals.items()})


class FullGameTrainingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    batch_size: int = Field(default=8, ge=1, le=64, strict=True)
    player_count: int = Field(default=3, ge=2, le=9, strict=True)
    teams: tuple[Annotated[int, Field(ge=0, le=4, strict=True)], ...] = ()
    updates: int = Field(default=4, ge=1, le=256, strict=True)
    seed: int = Field(default=67, ge=0, lt=2**63 - 1024, strict=True)
    max_turns: int = Field(default=256, ge=1, le=1000, strict=True)
    max_decisions: int = Field(default=2048, ge=1, le=8000, strict=True)
    apocalypse_after_turns: int = Field(default=64, ge=0, le=1000, strict=True)
    cpu_threads: int = Field(default=2, ge=1, le=16, strict=True)
    ppo: FullGamePpoConfig = Field(default_factory=FullGamePpoConfig)
    architecture: FullGamePolicyArchitecture = Field(default_factory=FullGamePolicyArchitecture)

    @model_validator(mode="after")
    def bounded_collection(self) -> FullGameTrainingConfig:
        if self.batch_size * self.max_decisions > 32768:
            raise ValueError("full-game training batch exceeds the complete-episode storage bound")
        if self.teams and len(self.teams) != self.player_count:
            raise ValueError("full-game training requires one team ID per player")
        return self


class FullGameTrainingUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    environment_seed: int
    sampling_seed: int
    outcomes: tuple[FullGameCollectedOutcome, ...]
    accepted_decisions: int
    terminal_target_decisions: int
    actor_decisions: int
    behavior_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: PpoTrainingMetrics | None
    collection_error: str | None
    rejected_commands: tuple[tuple[int, ...], ...]


class FullGameTrainingReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    algorithm: Literal["full-game-complete-terminal-recurrent-ppo-v1"] = (
        "full-game-complete-terminal-recurrent-ppo-v1"
    )
    recurrent_boundary: Literal["same-seat-windows-starting-at-frozen-behavior-memory"] = (
        "same-seat-windows-starting-at-frozen-behavior-memory"
    )
    config: FullGameTrainingConfig
    initial_collection: FullGameCollectionMetadata
    updates: tuple[FullGameTrainingUpdate, ...]
    final_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def update_chain(self) -> FullGameTrainingReport:
        initial = self.initial_collection
        expected_environment = dict(
            batch_size=self.config.batch_size,
            player_count=self.config.player_count,
            initial_teams=self.config.teams or (0,) * self.config.player_count,
            seed=self.config.seed,
            max_turns=self.config.max_turns,
            max_decisions=self.config.max_decisions,
            apocalypse_after_turns=self.config.apocalypse_after_turns,
            capacity=18,
            resource_cap=99,
            acquisition_mode="all-held-weighted",
            hidden_cost_policy="fizzle-provisional",
        )
        if (
            not self.updates
            or len(self.updates) > self.config.updates
            or (
                len(self.updates) < self.config.updates
                and self.updates[-1].collection_error is None
            )
            or initial.architecture != self.config.architecture
            or initial.sampling_seed != self.config.seed + 1
            or initial.environment.model_dump(include=set(expected_environment))
            != expected_environment
            or self.updates[0].initial_state_sha256 != initial.initial_state_sha256
            or self.updates[-1].policy_sha256 != self.final_policy_sha256
        ):
            raise ValueError("full-game training report contract differs")
        previous = initial.behavior_policy_sha256
        for index, update in enumerate(self.updates):
            terminal = sum(
                o.accepted_commands for o in update.outcomes if o.status in ("winner", "draw")
            )
            if (
                update.behavior_policy_sha256 != previous
                or update.environment_seed != self.config.seed + 2 * index
                or update.sampling_seed != update.environment_seed + 1
                or len(update.outcomes) != self.config.batch_size
                or update.accepted_decisions != sum(o.accepted_commands for o in update.outcomes)
                or update.terminal_target_decisions != terminal
                or not 0 <= update.actor_decisions <= terminal
                or (update.metrics is not None)
                != (terminal > 0 and update.collection_error is None)
                or (update.metrics is None and update.policy_sha256 != previous)
                or (update.collection_error is not None and index != len(self.updates) - 1)
                or (
                    update.metrics is not None
                    and not all(
                        math.isfinite(value) for value in update.metrics.model_dump().values()
                    )
                )
            ):
                raise ValueError("full-game training update accounting differs")
            previous = update.policy_sha256
        return self


def train_full_game(
    *,
    catalog_path: Path,
    bible_path: Path,
    config: FullGameTrainingConfig,
    on_update: Callable[[int, FullGameTrainingUpdate], None] | None = None,
) -> tuple[FullGameTrainingReport, FullGameActorCritic]:
    """Fresh local full-pool self-play with one frozen behavior batch per update."""
    config = FullGameTrainingConfig.model_validate(config.model_dump())
    previous_threads = torch.get_num_threads()
    try:
        torch.set_num_threads(config.cpu_threads)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(config.seed)
            policy = FullGameActorCritic(config.architecture).float().cpu()
            optimizer = torch.optim.Adam(policy.parameters(), lr=config.ppo.learning_rate)
            initial = None
            updates = []
            for i in range(config.updates):
                environment_seed = config.seed + 2 * i
                sampling_seed = environment_seed + 1
                configured = create_development_full_game_batch(
                    catalog_path=catalog_path,
                    bible_path=bible_path,
                    batch_size=config.batch_size,
                    player_count=config.player_count,
                    teams=config.teams or None,
                    capacity=18,
                    acquisition_mode="all-held-weighted",
                    seed=environment_seed,
                    max_turns=config.max_turns,
                    max_decisions=config.max_decisions,
                    apocalypse_after_turns=config.apocalypse_after_turns,
                )
                if initial is not None and configured.metadata.model_dump(
                    exclude={"seed"}
                ) != initial.environment.model_dump(exclude={"seed"}):
                    raise RuntimeError(
                        "full-game training source or ruleset changed between updates"
                    )
                collection = collect_full_game_episodes(
                    configured, policy, sampling_seed=sampling_seed
                )
                if initial is None:
                    initial = collection.metadata
                metrics = None
                if collection.collection_error is None and collection.eligible_decisions:
                    metrics = train_full_game_ppo(policy, optimizer, collection, config.ppo)
                    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
                        raise RuntimeError("full-game PPO report metrics are not finite")
                updates.append(
                    FullGameTrainingUpdate(
                        environment_seed=environment_seed,
                        sampling_seed=sampling_seed,
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
                del collection
                if on_update is not None:
                    on_update(i + 1, updates[-1])
                if updates[-1].collection_error is not None:
                    break
            assert initial is not None
            return FullGameTrainingReport(
                config=config,
                initial_collection=initial,
                updates=tuple(updates),
                final_policy_sha256=full_game_policy_sha256(policy),
            ), policy
    finally:
        torch.set_num_threads(previous_threads)


class FullGameCandidateManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(ge=1, le=1, strict=True)
    source_kind: Literal["local-full-game-ppo-candidate-v1"]
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training: FullGameTrainingReport
    promotion_eligible: Literal[False] = False


def save_full_game_candidate(
    root: Path, report: FullGameTrainingReport, policy: FullGameActorCritic
) -> Path:
    report = FullGameTrainingReport.model_validate(report.model_dump())
    if (
        not any(update.metrics is not None for update in report.updates)
        or report.updates[-1].collection_error is not None
        or full_game_policy_sha256(policy) != report.final_policy_sha256
    ):
        raise ValueError("full-game candidate requires a successful matching training run")
    root.mkdir(parents=True, exist_ok=True)
    directory = root / str(uuid4())
    with TemporaryDirectory(prefix=".full-game-", dir=root) as temporary:
        stage = Path(temporary)
        weights = stage / "weights.pt"
        torch.save(policy.state_dict(), weights)
        manifest = FullGameCandidateManifest(
            schema_version=1,
            source_kind="local-full-game-ppo-candidate-v1",
            weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
            training=report,
        )
        (stage / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        stage.rename(directory)
    return directory


def load_full_game_candidate(
    directory: Path,
) -> tuple[FullGameCandidateManifest, FullGameActorCritic]:
    manifest = FullGameCandidateManifest.model_validate_json(
        (directory / "manifest.json").read_bytes()
    )
    weights = directory / "weights.pt"
    if (
        weights.stat().st_size > 32 * 1024 * 1024
        or hashlib.sha256(weights.read_bytes()).hexdigest() != manifest.weights_sha256
    ):
        raise ValueError("full-game candidate weight size or checksum differs")
    with torch.random.fork_rng(devices=[]):
        policy = FullGameActorCritic(manifest.training.config.architecture).float().cpu()
    tensors = torch.load(weights, map_location="cpu", weights_only=True)
    expected = policy.state_dict()
    if (
        not isinstance(tensors, dict)
        or tensors.keys() != expected.keys()
        or any(
            not isinstance(tensors[key], Tensor)
            or tensors[key].dtype != value.dtype
            or tensors[key].shape != value.shape
            for key, value in expected.items()
        )
    ):
        raise ValueError("full-game candidate parameter layout differs")
    policy.load_state_dict(tensors, strict=True)
    if full_game_policy_sha256(policy) != manifest.training.final_policy_sha256:
        raise ValueError("full-game candidate tensor content differs from training report")
    return manifest, policy.eval()
