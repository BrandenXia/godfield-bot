from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import structlog
import torch
from pydantic import BaseModel, Field, model_validator
from torch import Tensor, nn
from torch.nn import functional as functional

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import (
    ModelManifest,
    load_model,
    save_candidate,
    vocabulary_digest,
)
from godfield_bot.neural import SLOT_AWARE_POLICY, RecurrentPolicyValueNet
from godfield_bot.simulation import (
    AttackDefenseSimulation,
    create_attack_defense_simulation,
    simulation_feature_tensors,
)
from godfield_bot.simulation_policy import (
    CurriculumHeuristic,
    build_curriculum_heuristic,
    curriculum_heuristic_actions,
)

ALGORITHM = "heuristic-warmstart-recurrent-ppo-self-play-v1"
MAX_ROLLOUT_TRANSITIONS = 2_000_000


class SimulationTrainingError(RuntimeError):
    """Raised when native self-play cannot satisfy the training contract."""


class SimulationTrainingConfig(BaseModel):
    ruleset: Literal[
        "fixed-role",
        "mixed-hand",
        "elemental-hand",
        "combo-hand",
        "resource-hand",
        "stochastic-resource-hand",
    ] = "fixed-role"
    batch_size: int = Field(default=256, ge=1, le=1_000_000)
    rollout_steps: int = Field(default=32, ge=2, le=4096)
    updates: int = Field(default=10, ge=1, le=100_000)
    ppo_epochs: int = Field(default=2, ge=1, le=100)
    environment_minibatch_size: int = Field(default=128, ge=1, le=1_000_000)
    teacher_updates: int = Field(default=16, ge=0, le=10_000)
    teacher_epochs: int = Field(default=2, ge=1, le=100)
    teacher_learning_rate: float = Field(default=1e-3, gt=0, le=1)
    heuristic_opponent_fraction: float = Field(default=0.5, ge=0, le=1)
    learning_rate: float = Field(default=3e-4, gt=0, le=1)
    gamma: float = Field(default=0.99, gt=0, le=1)
    gae_lambda: float = Field(default=0.95, ge=0, le=1)
    clip_range: float = Field(default=0.2, gt=0, le=1)
    value_weight: float = Field(default=0.5, ge=0, le=100)
    entropy_weight: float = Field(default=0.01, ge=0, le=100)
    max_gradient_norm: float = Field(default=0.5, gt=0, le=100)
    seed: int = Field(default=67, ge=0)
    device: Literal["cpu", "mps", "cuda"] = "cpu"

    @model_validator(mode="after")
    def validate_minibatch(self) -> SimulationTrainingConfig:
        if self.environment_minibatch_size > self.batch_size:
            raise ValueError("environment_minibatch_size cannot exceed batch_size")
        if self.batch_size * self.rollout_steps > MAX_ROLLOUT_TRANSITIONS:
            raise ValueError(
                f"one rollout cannot exceed {MAX_ROLLOUT_TRANSITIONS} stored transitions"
            )
        return self


class PpoTrainingMetrics(BaseModel):
    total_loss: float
    policy_loss: float
    value_loss: float
    entropy: float
    approximate_kl: float
    clip_fraction: float
    gradient_norm: float


class TeacherTrainingMetrics(BaseModel):
    loss: float
    accuracy: float
    gradient_norm: float


@dataclass(frozen=True)
class TeacherRollout:
    global_features: Tensor
    player_features: Tensor
    player_mask: Tensor
    hand_token_ids: Tensor
    hand_mask: Tensor
    action_mask: Tensor
    actors: Tensor
    actions: Tensor
    terminated: Tensor
    completed_episodes: int

    @property
    def steps(self) -> int:
        return int(self.actions.shape[0])

    @property
    def batch_size(self) -> int:
        return int(self.actions.shape[1])

    def observations_at(self, step: int, environments: Tensor) -> tuple[Tensor, ...]:
        return (
            self.global_features[step].index_select(0, environments),
            self.player_features[step].index_select(0, environments),
            self.player_mask[step].index_select(0, environments),
            self.hand_token_ids[step].index_select(0, environments),
            self.hand_mask[step].index_select(0, environments),
            self.action_mask[step].index_select(0, environments),
        )


@dataclass(frozen=True)
class SelfPlayRollout:
    global_features: Tensor
    player_features: Tensor
    player_mask: Tensor
    hand_token_ids: Tensor
    hand_mask: Tensor
    action_mask: Tensor
    actors: Tensor
    actions: Tensor
    policy_trainable: Tensor
    old_log_probabilities: Tensor
    old_values: Tensor
    rewards: Tensor
    terminated: Tensor
    advantages: Tensor
    returns: Tensor
    completed_episodes: int

    @property
    def steps(self) -> int:
        return int(self.actions.shape[0])

    @property
    def batch_size(self) -> int:
        return int(self.actions.shape[1])

    def observations_at(self, step: int, environments: Tensor) -> tuple[Tensor, ...]:
        return (
            self.global_features[step].index_select(0, environments),
            self.player_features[step].index_select(0, environments),
            self.player_mask[step].index_select(0, environments),
            self.hand_token_ids[step].index_select(0, environments),
            self.hand_mask[step].index_select(0, environments),
            self.action_mask[step].index_select(0, environments),
        )


def _resolve_device(name: str) -> torch.device:
    device = torch.device(name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise SimulationTrainingError("CUDA was requested but is unavailable")
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise SimulationTrainingError("MPS was requested but is unavailable")
    return device


def _active_seat_states(seat_states: Tensor, actors: Tensor) -> Tensor:
    environments = torch.arange(actors.shape[0], device=actors.device)
    return seat_states[environments, actors]


def _replace_active_seat_states(
    seat_states: Tensor,
    actors: Tensor,
    active_states: Tensor,
) -> Tensor:
    seat_selector = functional.one_hot(actors, num_classes=2).unsqueeze(-1).to(seat_states.dtype)
    return seat_states * (1.0 - seat_selector) + active_states.unsqueeze(1) * seat_selector


def collect_heuristic_rollout(
    simulation: AttackDefenseSimulation,
    heuristic: CurriculumHeuristic,
    *,
    rollout_steps: int,
    device: torch.device,
) -> TeacherRollout:
    """Collect recurrent imitation sequences from the versioned curriculum teacher."""

    if rollout_steps < 2:
        raise SimulationTrainingError("rollout_steps must be at least two")
    batch = simulation.batch
    batch.reset()
    observation_rows: list[list[Tensor]] = [[] for _ in range(6)]
    actor_rows: list[Tensor] = []
    action_rows: list[Tensor] = []
    terminated_rows: list[Tensor] = []
    completed_episodes = 0
    environments = np.arange(batch.batch_size, dtype=np.int64)

    for step in range(rollout_steps):
        if step > 0 and bool(terminated_rows[-1].any()):
            batch.reset_done()
        observation = simulation_feature_tensors(simulation, device=str(device))
        actors = torch.from_numpy(np.array(batch.active_players, copy=True)).to(
            device=device,
            dtype=torch.long,
        )
        actions_array = curriculum_heuristic_actions(simulation, environments, heuristic)
        actions = torch.from_numpy(actions_array).to(device=device, dtype=torch.long)
        for rows, tensor in zip(observation_rows, observation, strict=True):
            rows.append(tensor.detach().clone())
        actor_rows.append(actors)
        action_rows.append(actions)

        batch.step(actions_array)
        terminated = torch.from_numpy(np.array(batch.terminated, copy=True)).to(device=device)
        terminated_rows.append(terminated)
        completed_episodes += int(terminated.sum().item())

    stacked_observations = tuple(torch.stack(rows) for rows in observation_rows)
    return TeacherRollout(
        global_features=stacked_observations[0],
        player_features=stacked_observations[1],
        player_mask=stacked_observations[2],
        hand_token_ids=stacked_observations[3],
        hand_mask=stacked_observations[4],
        action_mask=stacked_observations[5],
        actors=torch.stack(actor_rows),
        actions=torch.stack(action_rows),
        terminated=torch.stack(terminated_rows),
        completed_episodes=completed_episodes,
    )


def train_teacher_rollout(
    model: RecurrentPolicyValueNet,
    optimizer: torch.optim.Optimizer,
    rollout: TeacherRollout,
    config: SimulationTrainingConfig,
) -> TeacherTrainingMetrics:
    """Imitate teacher sequences while preserving independent memory per seat."""

    model.train()
    loss_sum = 0.0
    correct = 0
    gradient_norm_sum = 0.0
    measured_samples = 0
    device = rollout.actions.device

    for _ in range(config.teacher_epochs):
        permutation = torch.randperm(rollout.batch_size, device=device)
        for start in range(0, rollout.batch_size, config.environment_minibatch_size):
            environments = permutation[start : start + config.environment_minibatch_size]
            minibatch_size = int(environments.shape[0])
            seat_states = torch.zeros(
                (minibatch_size, 2, model.hidden_size),
                dtype=torch.float32,
                device=device,
            )
            logits_rows: list[Tensor] = []
            action_rows: list[Tensor] = []
            for step in range(rollout.steps):
                if step > 0:
                    continuing = (~rollout.terminated[step - 1].index_select(0, environments)).to(
                        seat_states.dtype
                    )
                    seat_states = seat_states * continuing[:, None, None]
                actors = rollout.actors[step].index_select(0, environments)
                active_states = _active_seat_states(seat_states, actors)
                logits, _, next_active_states = model(
                    *rollout.observations_at(step, environments),
                    recurrent_state=active_states,
                )
                logits_rows.append(logits)
                action_rows.append(rollout.actions[step].index_select(0, environments))
                seat_states = _replace_active_seat_states(
                    seat_states,
                    actors,
                    next_active_states,
                )

            logits = torch.cat(logits_rows)
            actions = torch.cat(action_rows)
            loss = functional.cross_entropy(logits, actions)
            if not bool(torch.isfinite(loss)):
                raise SimulationTrainingError("teacher warm-start produced a non-finite loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()  # type: ignore[no-untyped-call]
            gradient_norm = nn.utils.clip_grad_norm_(
                model.parameters(),
                config.max_gradient_norm,
            )
            optimizer.step()

            sample_count = rollout.steps * minibatch_size
            measured_samples += sample_count
            loss_sum += float(loss.detach()) * sample_count
            correct += int((logits.detach().argmax(dim=1) == actions).sum().item())
            gradient_norm_sum += float(gradient_norm.detach()) * sample_count

    if measured_samples == 0:
        raise SimulationTrainingError("teacher warm-start received an empty rollout")
    return TeacherTrainingMetrics(
        loss=loss_sum / measured_samples,
        accuracy=correct / measured_samples,
        gradient_norm=gradient_norm_sum / measured_samples,
    )


def signed_generalized_advantages(
    *,
    rewards: Tensor,
    values: Tensor,
    actors: Tensor,
    terminated: Tensor,
    final_values: Tensor,
    final_actors: Tensor,
    gamma: float,
    gae_lambda: float,
) -> tuple[Tensor, Tensor]:
    """Compute zero-sum GAE while converting between active-seat perspectives."""

    expected_shape = rewards.shape
    if (
        rewards.ndim != 2
        or values.shape != expected_shape
        or actors.shape != expected_shape
        or terminated.shape != expected_shape
        or final_values.shape != expected_shape[1:]
        or final_actors.shape != expected_shape[1:]
    ):
        raise SimulationTrainingError("signed GAE inputs have incompatible shapes")

    advantages = torch.empty_like(values)
    next_advantage = torch.zeros_like(final_values)
    next_value = final_values
    next_actor = final_actors
    for step in range(rewards.shape[0] - 1, -1, -1):
        continuing = (~terminated[step]).to(values.dtype)
        perspective_sign = torch.where(
            actors[step] == next_actor,
            torch.ones_like(values[step]),
            -torch.ones_like(values[step]),
        )
        delta = rewards[step] + gamma * continuing * perspective_sign * next_value - values[step]
        next_advantage = delta + gamma * gae_lambda * continuing * perspective_sign * next_advantage
        advantages[step] = next_advantage
        next_value = values[step]
        next_actor = actors[step]
    return advantages, advantages + values


def collect_self_play_rollout(
    model: RecurrentPolicyValueNet,
    simulation: AttackDefenseSimulation,
    *,
    rollout_steps: int,
    gamma: float,
    gae_lambda: float,
    device: torch.device,
    heuristic: CurriculumHeuristic | None = None,
    heuristic_opponent_fraction: float = 0.0,
) -> SelfPlayRollout:
    """Collect one bounded rollout with independent recurrent memory per seat."""

    if rollout_steps < 2:
        raise SimulationTrainingError("rollout_steps must be at least two")
    batch = simulation.batch
    batch.reset()
    seat_states = torch.zeros(
        (batch.batch_size, 2, model.hidden_size),
        dtype=torch.float32,
        device=device,
    )
    observation_rows: list[list[Tensor]] = [[] for _ in range(6)]
    actor_rows: list[Tensor] = []
    action_rows: list[Tensor] = []
    policy_trainable_rows: list[Tensor] = []
    log_probability_rows: list[Tensor] = []
    value_rows: list[Tensor] = []
    reward_rows: list[Tensor] = []
    terminated_rows: list[Tensor] = []
    completed_episodes = 0

    if not 0.0 <= heuristic_opponent_fraction <= 1.0:
        raise SimulationTrainingError("heuristic opponent fraction must be between zero and one")
    heuristic_environment_count = round(batch.batch_size * heuristic_opponent_fraction)
    if heuristic_environment_count and heuristic is None:
        raise SimulationTrainingError("heuristic opponent fraction requires a heuristic policy")
    heuristic_environments = torch.zeros(batch.batch_size, dtype=torch.bool, device=device)
    if heuristic_environment_count:
        selected = torch.randperm(batch.batch_size, device=device)[:heuristic_environment_count]
        heuristic_environments[selected] = True
    learner_seats = torch.arange(batch.batch_size, device=device, dtype=torch.long) % 2

    model.eval()
    for step in range(rollout_steps):
        if step > 0:
            previous_terminated = terminated_rows[-1]
            if bool(previous_terminated.any()):
                seat_states[previous_terminated] = 0.0
                batch.reset_done()

        observation = simulation_feature_tensors(simulation, device=str(device))
        actors = torch.from_numpy(np.array(batch.active_players, copy=True)).to(
            device=device,
            dtype=torch.long,
        )
        active_states = _active_seat_states(seat_states, actors)
        with torch.no_grad():
            logits, values, next_active_states = model(
                *observation,
                recurrent_state=active_states,
            )
            distribution = torch.distributions.Categorical(logits=logits)
            actions = distribution.sample()  # type: ignore[no-untyped-call]
            policy_trainable = ~(heuristic_environments & (actors != learner_seats))
            heuristic_rows = (~policy_trainable).nonzero(as_tuple=False).squeeze(1)
            if heuristic_rows.numel() > 0 and heuristic is not None:
                heuristic_rows_array = np.ascontiguousarray(
                    heuristic_rows.cpu().numpy(),
                    dtype=np.int64,
                )
                heuristic_actions = curriculum_heuristic_actions(
                    simulation,
                    heuristic_rows_array,
                    heuristic,
                )
                actions[heuristic_rows] = torch.from_numpy(heuristic_actions).to(device=device)
            log_probabilities = distribution.log_prob(actions)  # type: ignore[no-untyped-call]
        seat_states = _replace_active_seat_states(
            seat_states,
            actors,
            next_active_states,
        )

        for rows, tensor in zip(observation_rows, observation, strict=True):
            rows.append(tensor.detach().clone())
        actor_rows.append(actors)
        action_rows.append(actions)
        policy_trainable_rows.append(policy_trainable)
        log_probability_rows.append(log_probabilities)
        value_rows.append(values)

        batch.step(np.ascontiguousarray(actions.cpu().numpy(), dtype=np.int64))
        terminated = torch.from_numpy(np.array(batch.terminated, copy=True)).to(device=device)
        seat_returns = np.array(batch.terminal_returns, copy=True)
        actor_indices = actors.cpu().numpy()
        rewards = torch.from_numpy(seat_returns[np.arange(batch.batch_size), actor_indices]).to(
            device=device
        )
        reward_rows.append(rewards)
        terminated_rows.append(terminated)
        completed_episodes += int(terminated.sum().item())

    final_terminated = terminated_rows[-1]
    final_actors = torch.from_numpy(np.array(batch.active_players, copy=True)).to(
        device=device,
        dtype=torch.long,
    )
    final_values = torch.zeros(batch.batch_size, dtype=torch.float32, device=device)
    continuing_indices = (~final_terminated).nonzero(as_tuple=False).squeeze(1)
    if continuing_indices.numel() > 0:
        final_observation = simulation_feature_tensors(simulation, device=str(device))
        continuing_actors = final_actors.index_select(0, continuing_indices)
        continuing_seat_states = seat_states.index_select(0, continuing_indices)
        continuing_active_states = _active_seat_states(
            continuing_seat_states,
            continuing_actors,
        )
        with torch.no_grad():
            _, continuing_values, _ = model(
                *(tensor.index_select(0, continuing_indices) for tensor in final_observation),
                recurrent_state=continuing_active_states,
            )
        final_values[continuing_indices] = continuing_values

    rewards = torch.stack(reward_rows)
    values = torch.stack(value_rows)
    actors = torch.stack(actor_rows)
    terminated = torch.stack(terminated_rows)
    advantages, returns = signed_generalized_advantages(
        rewards=rewards,
        values=values,
        actors=actors,
        terminated=terminated,
        final_values=final_values,
        final_actors=final_actors,
        gamma=gamma,
        gae_lambda=gae_lambda,
    )
    stacked_observations = tuple(torch.stack(rows) for rows in observation_rows)
    return SelfPlayRollout(
        global_features=stacked_observations[0],
        player_features=stacked_observations[1],
        player_mask=stacked_observations[2],
        hand_token_ids=stacked_observations[3],
        hand_mask=stacked_observations[4],
        action_mask=stacked_observations[5],
        actors=actors,
        actions=torch.stack(action_rows),
        policy_trainable=torch.stack(policy_trainable_rows),
        old_log_probabilities=torch.stack(log_probability_rows),
        old_values=values,
        rewards=rewards,
        terminated=terminated,
        advantages=advantages,
        returns=returns,
        completed_episodes=completed_episodes,
    )


def train_ppo_rollout(
    model: RecurrentPolicyValueNet,
    optimizer: torch.optim.Optimizer,
    rollout: SelfPlayRollout,
    config: SimulationTrainingConfig,
) -> PpoTrainingMetrics:
    """Replay a rollout by environment, preserving two independent seat memories."""

    model.train()
    learner_advantages = rollout.advantages[rollout.policy_trainable]
    if learner_advantages.numel() == 0:
        raise SimulationTrainingError("PPO rollout contains no learner decisions")
    advantages = (rollout.advantages - learner_advantages.mean()) / learner_advantages.std(
        unbiased=False
    ).clamp_min(1e-8)
    metric_totals = {
        "total_loss": 0.0,
        "policy_loss": 0.0,
        "value_loss": 0.0,
        "entropy": 0.0,
        "approximate_kl": 0.0,
        "clip_fraction": 0.0,
        "gradient_norm": 0.0,
    }
    measured_samples = 0
    device = rollout.actions.device

    for _ in range(config.ppo_epochs):
        permutation = torch.randperm(rollout.batch_size, device=device)
        for start in range(0, rollout.batch_size, config.environment_minibatch_size):
            environments = permutation[start : start + config.environment_minibatch_size]
            minibatch_size = int(environments.shape[0])
            seat_states = torch.zeros(
                (minibatch_size, 2, model.hidden_size),
                dtype=torch.float32,
                device=device,
            )
            log_probability_rows: list[Tensor] = []
            value_rows: list[Tensor] = []
            entropy_rows: list[Tensor] = []
            for step in range(rollout.steps):
                if step > 0:
                    continuing = (~rollout.terminated[step - 1].index_select(0, environments)).to(
                        seat_states.dtype
                    )
                    seat_states = seat_states * continuing[:, None, None]
                actors = rollout.actors[step].index_select(0, environments)
                active_states = _active_seat_states(seat_states, actors)
                logits, values, next_active_states = model(
                    *rollout.observations_at(step, environments),
                    recurrent_state=active_states,
                )
                actions = rollout.actions[step].index_select(0, environments)
                distribution = torch.distributions.Categorical(logits=logits)
                log_probability_rows.append(
                    distribution.log_prob(actions)  # type: ignore[no-untyped-call]
                )
                value_rows.append(values)
                entropy_rows.append(distribution.entropy())  # type: ignore[no-untyped-call]
                seat_states = _replace_active_seat_states(
                    seat_states,
                    actors,
                    next_active_states,
                )

            new_log_probabilities = torch.cat(log_probability_rows)
            new_values = torch.cat(value_rows)
            entropies = torch.cat(entropy_rows)
            old_log_probabilities = rollout.old_log_probabilities[:, environments].reshape(-1)
            old_values = rollout.old_values[:, environments].reshape(-1)
            target_advantages = advantages[:, environments].reshape(-1)
            target_returns = rollout.returns[:, environments].reshape(-1)
            policy_trainable = rollout.policy_trainable[:, environments].reshape(-1)
            if not bool(policy_trainable.any()):
                raise SimulationTrainingError("PPO minibatch contains no learner decisions")

            log_ratio = new_log_probabilities - old_log_probabilities
            ratio = log_ratio.exp()
            learner_ratio = ratio[policy_trainable]
            learner_advantages = target_advantages[policy_trainable]
            unclipped_policy_loss = -learner_advantages * learner_ratio
            clipped_policy_loss = -learner_advantages * learner_ratio.clamp(
                1.0 - config.clip_range,
                1.0 + config.clip_range,
            )
            policy_loss = torch.maximum(unclipped_policy_loss, clipped_policy_loss).mean()
            entropy = entropies[policy_trainable].mean()
            clipped_values = old_values + (new_values - old_values).clamp(
                -config.clip_range,
                config.clip_range,
            )
            value_loss = (
                0.5
                * torch.maximum(
                    (new_values - target_returns).square(),
                    (clipped_values - target_returns).square(),
                ).mean()
            )
            total_loss = (
                policy_loss + config.value_weight * value_loss - config.entropy_weight * entropy
            )
            if not bool(torch.isfinite(total_loss)):
                raise SimulationTrainingError("PPO produced a non-finite loss")

            optimizer.zero_grad(set_to_none=True)
            total_loss.backward()  # type: ignore[no-untyped-call]
            gradient_norm = nn.utils.clip_grad_norm_(
                model.parameters(),
                config.max_gradient_norm,
            )
            optimizer.step()

            with torch.no_grad():
                learner_log_ratio = log_ratio[policy_trainable]
                approximate_kl = ((learner_ratio - 1.0) - learner_log_ratio).mean()
                clip_fraction = ((learner_ratio - 1.0).abs() > config.clip_range).float().mean()
            sample_count = rollout.steps * minibatch_size
            measured_samples += sample_count
            values_to_add = {
                "total_loss": total_loss,
                "policy_loss": policy_loss,
                "value_loss": value_loss,
                "entropy": entropy,
                "approximate_kl": approximate_kl,
                "clip_fraction": clip_fraction,
                "gradient_norm": gradient_norm,
            }
            for name, value in values_to_add.items():
                metric_totals[name] += float(value.detach()) * sample_count

    if measured_samples == 0:
        raise SimulationTrainingError("PPO received an empty rollout")
    metrics = PpoTrainingMetrics(
        **{name: value / measured_samples for name, value in metric_totals.items()}
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise SimulationTrainingError("PPO produced non-finite metrics")
    return metrics


def _source_digest(
    *,
    parent: ModelManifest,
    simulation: AttackDefenseSimulation,
    config: SimulationTrainingConfig,
) -> str:
    value = {
        "schema_version": 1,
        "source_kind": "native-heuristic-warmstart-on-policy-self-play",
        "parent_model_id": parent.model_id,
        "parent_weights_sha256": parent.weights_sha256,
        "simulation": simulation.metadata.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def train_simulation_candidate(
    *,
    base_model_directory: Path,
    model_root: Path,
    snapshot_path: Path,
    config: SimulationTrainingConfig,
) -> ModelManifest:
    """Train and persist a non-promotable shared-policy native self-play candidate."""

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    parent, model = load_model(base_model_directory)
    if parent.client_sha256 != snapshot.client.sha256:
        raise ValueError("base model client fingerprint differs from the Bible snapshot")
    if parent.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ValueError("base model vocabulary differs from the Bible snapshot")
    if parent.architecture.policy_architecture != SLOT_AWARE_POLICY:
        raise ValueError("simulation training requires a new slot-aware-v1 base model")

    simulation = create_attack_defense_simulation(
        snapshot_path,
        batch_size=config.batch_size,
        seed=config.seed,
        ruleset=config.ruleset,
    )
    if parent.architecture.action_count != simulation.metadata.action_count:
        raise ValueError("base model action head differs from the simulator")
    if parent.architecture.global_feature_count != simulation.metadata.global_feature_count:
        raise ValueError("base model global features differ from the simulator")
    if parent.feature_schema_version != simulation.metadata.observation_schema_version:
        raise ValueError("base model feature schema differs from the simulator observation schema")
    if parent.vocabulary_sha256 != simulation.metadata.vocabulary_sha256:
        raise ValueError("base model vocabulary fingerprint differs from the simulator")

    device = _resolve_device(config.device)
    torch.manual_seed(config.seed)
    model.to(device)
    log = structlog.get_logger()
    heuristic = build_curriculum_heuristic(snapshot, vocabulary, ruleset=config.ruleset)
    teacher_metrics: list[TeacherTrainingMetrics] = []
    teacher_completed_episodes = 0
    teacher_transitions = 0
    if config.teacher_updates:
        teacher_optimizer = torch.optim.Adam(
            model.parameters(),
            lr=config.teacher_learning_rate,
        )
        for update in range(1, config.teacher_updates + 1):
            teacher_rollout = collect_heuristic_rollout(
                simulation,
                heuristic,
                rollout_steps=config.rollout_steps,
                device=device,
            )
            teacher_update_metrics = train_teacher_rollout(
                model,
                teacher_optimizer,
                teacher_rollout,
                config,
            )
            teacher_metrics.append(teacher_update_metrics)
            teacher_completed_episodes += teacher_rollout.completed_episodes
            teacher_transitions += teacher_rollout.steps * teacher_rollout.batch_size
            log.info(
                "simulation_teacher_update",
                update=update,
                updates=config.teacher_updates,
                transitions=teacher_transitions,
                completed_episodes=teacher_completed_episodes,
                **teacher_update_metrics.model_dump(),
            )

    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    metric_sums = {name: 0.0 for name in PpoTrainingMetrics.model_fields}
    armor_selection_rate_sum = 0.0
    absolute_advantage_sum = 0.0
    completed_episodes = 0
    ppo_transitions = 0
    for update in range(1, config.updates + 1):
        self_play_rollout = collect_self_play_rollout(
            model,
            simulation,
            rollout_steps=config.rollout_steps,
            gamma=config.gamma,
            gae_lambda=config.gae_lambda,
            device=device,
            heuristic=heuristic,
            heuristic_opponent_fraction=config.heuristic_opponent_fraction,
        )
        metrics = train_ppo_rollout(model, optimizer, self_play_rollout, config)
        completed_episodes += self_play_rollout.completed_episodes
        ppo_transitions += self_play_rollout.steps * self_play_rollout.batch_size
        defense_decisions = self_play_rollout.global_features[:, :, 4] > 0.5
        defense_count = int(defense_decisions.sum().item())
        armor_selection_rate = (
            float(
                (
                    defense_decisions
                    & (self_play_rollout.actions >= 1)
                    & (self_play_rollout.actions <= 9)
                )
                .float()
                .sum()
                .item()
            )
            / defense_count
            if defense_count
            else 0.0
        )
        mean_absolute_advantage = float(self_play_rollout.advantages.abs().mean().item())
        armor_selection_rate_sum += armor_selection_rate
        absolute_advantage_sum += mean_absolute_advantage
        for name, value in metrics.model_dump().items():
            metric_sums[name] += value
        log.info(
            "simulation_training_update",
            update=update,
            updates=config.updates,
            transitions=ppo_transitions,
            completed_episodes=completed_episodes,
            heuristic_opponent_action_fraction=float(
                (~self_play_rollout.policy_trainable).float().mean().item()
            ),
            armor_selection_rate=armor_selection_rate,
            mean_absolute_advantage=mean_absolute_advantage,
            **metrics.model_dump(),
        )

    model.to("cpu")
    source_sha256 = _source_digest(
        parent=parent,
        simulation=simulation,
        config=config,
    )
    return save_candidate(
        model_root,
        model,
        vocabulary,
        parent=parent,
        seed=config.seed,
        training_algorithm=ALGORITHM,
        training_dataset_sha256=source_sha256,
        training_run_ids=(),
        metrics={
            "training_transitions": float(teacher_transitions + ppo_transitions),
            "teacher_transitions": float(teacher_transitions),
            "teacher_completed_episodes": float(teacher_completed_episodes),
            "teacher_updates": float(config.teacher_updates),
            "teacher_loss_initial": teacher_metrics[0].loss if teacher_metrics else 0.0,
            "teacher_loss_final": teacher_metrics[-1].loss if teacher_metrics else 0.0,
            "teacher_accuracy_initial": teacher_metrics[0].accuracy if teacher_metrics else 0.0,
            "teacher_accuracy_final": teacher_metrics[-1].accuracy if teacher_metrics else 0.0,
            "ppo_transitions": float(ppo_transitions),
            "heuristic_opponent_fraction": config.heuristic_opponent_fraction,
            "training_completed_episodes": float(completed_episodes),
            "training_updates": float(config.updates),
            "training_ppo_epochs": float(config.ppo_epochs),
            "mean_armor_selection_rate": armor_selection_rate_sum / config.updates,
            "mean_forgive_rate": 1.0 - armor_selection_rate_sum / config.updates,
            "mean_absolute_advantage": absolute_advantage_sum / config.updates,
            **{f"mean_{name}": value / config.updates for name, value in metric_sums.items()},
        },
        training_context={
            "source_kind": "native-heuristic-warmstart-on-policy-self-play",
            "heuristic_policy_id": heuristic.policy_id,
            "simulation": simulation.metadata.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
        },
    )
