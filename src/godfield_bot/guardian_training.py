"""CPU recurrent imitation/PPO and separate checkpoints for the local duel arena."""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
import structlog
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator
from torch import Tensor, nn
from torch.nn import functional as F

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.guardian_coverage import (
    GuardianWindowOutcomeCoverage,
    count_guardian_window_outcomes,
)
from godfield_bot.guardian_discard_refill import GuardianDiscardRefillPlan
from godfield_bot.guardian_neural import (
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
    guardian_feature_tensors,
    migrate_guardian_discard_policy,
    migrate_guardian_horizon_policy,
    migrate_guardian_utility_policy,
)
from godfield_bot.guardian_rollout import (
    DISCARD_START,
    FORGIVE,
    GuardianObservation,
    GuardianRolloutArena,
    GuardianRolloutConfig,
    GuardianRolloutMetadata,
    GuardianTransition,
    GuardianUtilityStatistics,
    IntArray,
    greedy_guardian_actions,
)
from godfield_bot.simulation_training import (
    PpoTrainingMetrics,
    TeacherTrainingMetrics,
    signed_generalized_advantages,
)

ALGORITHM: Literal["provisional-guardian-duel-recurrent-imitation-ppo-v1"] = (
    "provisional-guardian-duel-recurrent-imitation-ppo-v1"
)
IMITATION_ALGORITHM: Literal["provisional-guardian-duel-recurrent-imitation-only-v1"] = (
    "provisional-guardian-duel-recurrent-imitation-only-v1"
)
DEFENSE_FEEDBACK_ALGORITHM: Literal[
    "provisional-guardian-duel-recurrent-imitation-ppo-defense-feedback-v1"
] = "provisional-guardian-duel-recurrent-imitation-ppo-defense-feedback-v1"
MANIFEST_FILE = "arena-manifest.json"
WEIGHTS_FILE = "arena-weights.pt"


class GuardianTrainingError(RuntimeError):
    """A local training/checkpoint contract cannot be satisfied."""


class GuardianTrainingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    arena: GuardianRolloutConfig = Field(
        default_factory=lambda: GuardianRolloutConfig(max_decisions=128)
    )
    rollout_steps: int = Field(default=64, ge=2, le=256, strict=True)
    updates: int = Field(default=10, ge=0, le=1000, strict=True)
    teacher_updates: int = Field(default=64, ge=0, le=1000, strict=True)
    teacher_selected_defense_weight: float = Field(default=1, ge=1, le=16, allow_inf_nan=False)
    defense_feedback_weight: float = Field(default=0, ge=0, le=4, allow_inf_nan=False)
    defense_feedback_scope: Literal["all-defense", "finish-decisions"] = "all-defense"
    ppo_epochs: int = Field(default=2, ge=1, le=10, strict=True)
    environment_minibatch_size: int = Field(default=16, ge=1, le=512, strict=True)
    teacher_learning_rate: float = Field(default=1e-3, gt=0, le=0.1, allow_inf_nan=False)
    learning_rate: float = Field(default=3e-4, gt=0, le=0.1, allow_inf_nan=False)
    gae_lambda: float = Field(default=0.95, ge=0, le=1, allow_inf_nan=False)
    clip_range: float = Field(default=0.2, gt=0, le=1, allow_inf_nan=False)
    value_weight: float = Field(default=0.5, ge=0, le=10, allow_inf_nan=False)
    entropy_weight: float = Field(default=0.01, ge=0, le=1, allow_inf_nan=False)
    max_gradient_norm: float = Field(default=0.5, gt=0, le=10, allow_inf_nan=False)
    baseline_opponent_fraction: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    hidden_size: int = Field(default=128, ge=16, le=256, strict=True)
    embedding_size: int = Field(default=32, ge=8, le=128, strict=True)
    evaluation_games: int = Field(default=32, ge=2, le=256, strict=True)
    cpu_threads: int = Field(default=2, ge=1, le=16, strict=True)

    @model_validator(mode="after")
    def bounded_duel(self) -> GuardianTrainingConfig:
        if self.updates == 0 and (self.teacher_updates == 0 or self.defense_feedback_weight > 0):
            raise ValueError("imitation-only training needs teacher updates and no PPO feedback")
        if self.arena.player_count != 2:
            raise ValueError(
                "guardian training v1 is duel-only; multiplayer requires different returns"
            )
        if self.environment_minibatch_size > self.arena.batch_size:
            raise ValueError("environment_minibatch_size cannot exceed arena batch_size")
        if self.rollout_steps * self.arena.batch_size > 32768:
            raise ValueError("guardian rollout storage is limited to 32768 transitions")
        if self.rollout_steps * self.environment_minibatch_size > 4096:
            raise ValueError("guardian recurrent minibatch is limited to 4096 decisions")
        if self.evaluation_games % 2:
            raise ValueError("evaluation_games must be even for paired learner seats")
        return self


@contextmanager
def _runtime(seed: int, threads: int) -> Iterator[None]:
    previous_threads = torch.get_num_threads()
    try:
        torch.set_num_threads(threads)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            yield
    finally:
        torch.set_num_threads(previous_threads)


def _replace_states(states: Tensor, actors: Tensor, active: Tensor) -> Tensor:
    selector = F.one_hot(actors, num_classes=2).unsqueeze(-1).to(states.dtype)
    return states * (1 - selector) + active[:, None] * selector


@dataclass(frozen=True)
class GuardianLearningRollout:
    observations: tuple[Tensor, ...]
    actors: Tensor
    actions: Tensor
    starts: Tensor
    initial_states: Tensor
    policy_trainable: Tensor
    old_log_probabilities: Tensor
    old_values: Tensor
    rewards: Tensor
    done: Tensor
    advantages: Tensor
    returns: Tensor
    completed_games: int
    truncated_games: int
    phase_counts: tuple[int, ...]
    digest: str
    replacement_gifts: int
    defense_teacher_actions: Tensor | None = None
    utility_statistics: GuardianUtilityStatistics | None = None
    discarded_cards: int | None = None
    outcome_coverage: GuardianWindowOutcomeCoverage | None = None

    @property
    def steps(self) -> int:
        return int(self.actions.shape[0])

    @property
    def batch_size(self) -> int:
        return int(self.actions.shape[1])


class GuardianDuelCollector:
    """Keep episodes and detached seat memories across update boundaries."""

    def __init__(self, arena: GuardianRolloutArena, model: GuardianArenaPolicy):
        if arena.config.player_count != 2:
            raise GuardianTrainingError("signed arena learning requires exactly two players")
        self.arena = arena
        self.model = model
        self.states = torch.zeros((arena.config.batch_size, 2, model.hidden_size))
        self.previous_done = torch.ones(arena.config.batch_size, dtype=torch.bool)

    def collect(
        self, config: GuardianTrainingConfig, *, teacher: bool = False
    ) -> GuardianLearningRollout:
        if config.arena != self.arena.config:
            raise GuardianTrainingError("collector and training arena configurations differ")
        observations: list[list[Tensor]] = [[] for _ in range(7)]
        actors_history, actions_history, starts_history, trainable_history = [], [], [], []
        teacher_actions_history: list[Tensor] = []
        log_probs, values_history, rewards_history, done_history = [], [], [], []
        terminated_history: list[Tensor] = []
        initial_states = self.states.detach().clone()
        completed = truncated = 0
        initial_gifts = self.arena.replacement_gifts
        initial_utilities = self.arena.utility_statistics
        initial_discards = self.arena.discarded_cards
        phase_counts = np.zeros(6, dtype=np.int64)
        digest = hashlib.sha256(self.arena.metadata.model_dump_json().encode())
        envs = torch.arange(config.arena.batch_size)
        baseline_envs = envs < round(config.arena.batch_size * config.baseline_opponent_fraction)
        self.model.eval()
        for _ in range(config.rollout_steps):
            starts = self.previous_done.clone()
            self.states[self.previous_done] = 0
            obs = self.arena.reset_done()
            features = guardian_feature_tensors(obs)
            actors = torch.from_numpy(obs.actors.copy())
            with torch.no_grad():
                logits, values, next_states = self.model(
                    *features, recurrent_state=self.states[envs, actors]
                )
                distribution = torch.distributions.Categorical(logits=logits)
                actions = distribution.sample()  # type: ignore[no-untyped-call]
                learner_seats = (envs + torch.from_numpy(obs.episode_ids.copy())) % 2
                trainable = ~(baseline_envs & (actors != learner_seats))
                baseline = (
                    torch.from_numpy(greedy_guardian_actions(obs))
                    if teacher or bool((~trainable).any()) or config.defense_feedback_weight > 0
                    else None
                )
                if teacher:
                    assert baseline is not None
                    actions = baseline
                    trainable = torch.ones_like(trainable)
                elif bool((~trainable).any()):
                    assert baseline is not None
                    actions = torch.where(trainable, actions, baseline)
                if config.defense_feedback_weight > 0:
                    assert baseline is not None
                    teacher_actions_history.append(baseline)
                probabilities = distribution.log_prob(actions)  # type: ignore[no-untyped-call]
            self.states = _replace_states(self.states, actors, next_states).detach()
            transition = self.arena.step(np.ascontiguousarray(actions.numpy(), dtype=np.int64))
            done = torch.from_numpy((transition.terminated | transition.truncated).copy())
            rewards = torch.from_numpy(transition.acting_rewards.copy())
            for history, feature in zip(observations, features, strict=True):
                history.append(feature)
            actors_history.append(actors)
            actions_history.append(actions)
            starts_history.append(starts)
            trainable_history.append(trainable)
            log_probs.append(probabilities)
            values_history.append(values)
            rewards_history.append(rewards)
            done_history.append(done)
            terminated_history.append(torch.from_numpy(transition.terminated.copy()))
            self.previous_done = done
            completed += int(np.count_nonzero(transition.newly_finished & transition.terminated))
            truncated += int(np.count_nonzero(transition.newly_finished & transition.truncated))
            phase_counts += np.bincount(obs.phases, minlength=6)
            for value in (
                *features,
                actors,
                actions,
                rewards,
                done,
                torch.from_numpy(obs.episode_ids.copy()),
            ):
                digest.update(value.numpy().tobytes())
            if config.defense_feedback_weight > 0:
                digest.update(teacher_actions_history[-1].numpy().tobytes())
        final = self.arena.observe()
        final_values = torch.zeros(config.arena.batch_size)
        rows = np.flatnonzero(final.active)
        if len(rows):
            final_actors = torch.from_numpy(final.actors[rows].copy())
            with torch.no_grad():
                _, bootstrap, _ = self.model(
                    *guardian_feature_tensors(final, rows),
                    recurrent_state=self.states[rows, final_actors],
                )
            final_values[rows] = bootstrap
        rewards = torch.stack(rewards_history)
        values = torch.stack(values_history)
        actors = torch.stack(actors_history)
        done = torch.stack(done_history)
        trainable = torch.stack(trainable_history)
        terminated = torch.stack(terminated_history)
        coverage = count_guardian_window_outcomes(
            terminated=terminated, truncated=done & ~terminated, trainable=trainable
        )
        advantages, returns = signed_generalized_advantages(
            rewards=rewards,
            values=values,
            actors=actors,
            terminated=done,
            final_values=final_values,
            final_actors=torch.from_numpy(final.actors.copy()),
            gamma=config.arena.gamma,
            gae_lambda=config.gae_lambda,
        )
        return GuardianLearningRollout(
            tuple(torch.stack(history) for history in observations),
            actors,
            torch.stack(actions_history),
            torch.stack(starts_history),
            initial_states,
            trainable,
            torch.stack(log_probs),
            values,
            rewards,
            done,
            advantages,
            returns,
            completed,
            truncated,
            tuple(int(value) for value in phase_counts),
            digest.hexdigest(),
            self.arena.replacement_gifts - initial_gifts,
            torch.stack(teacher_actions_history) if teacher_actions_history else None,
            self.arena.utility_statistics.since(initial_utilities)
            if initial_utilities is not None and self.arena.utility_statistics is not None
            else None,
            self.arena.discarded_cards - initial_discards
            if config.arena.inventory_discards
            else None,
            coverage,
        )


def replay_guardian_rollout(
    model: GuardianArenaPolicy, rollout: GuardianLearningRollout, environments: Tensor
) -> tuple[Tensor, Tensor]:
    states = rollout.initial_states.index_select(0, environments)
    logits_history, values_history = [], []
    envs = torch.arange(len(environments))
    for step in range(rollout.steps):
        starts = rollout.starts[step].index_select(0, environments)
        states = states * (~starts)[:, None, None]
        actors = rollout.actors[step].index_select(0, environments)
        logits, values, next_states = model(
            *(feature[step].index_select(0, environments) for feature in rollout.observations),
            recurrent_state=states[envs, actors],
        )
        states = _replace_states(states, actors, next_states)
        logits_history.append(logits)
        values_history.append(values)
    return torch.stack(logits_history), torch.stack(values_history)


def _optimizer_step(
    model: GuardianArenaPolicy,
    optimizer: torch.optim.Optimizer,
    loss: Tensor,
    config: GuardianTrainingConfig,
) -> Tensor:
    if not bool(torch.isfinite(loss)):
        raise GuardianTrainingError("guardian training produced a non-finite loss")
    optimizer.zero_grad(set_to_none=True)
    loss.backward()  # type: ignore[no-untyped-call]
    norm = nn.utils.clip_grad_norm_(
        model.parameters(), config.max_gradient_norm, error_if_nonfinite=True
    )
    optimizer.step()
    return norm


class GuardianTeacherMetrics(TeacherTrainingMetrics):
    # Older exploratory checkpoints did not record this subgroup; unknown
    # remains null rather than being rewritten as a measured zero.
    selected_defense_accuracy: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    selected_defense_samples: int | None = Field(default=None, ge=0, strict=True)
    utility_statistics: GuardianUtilityStatistics | None = None
    discarded_cards: int | None = Field(default=None, ge=0, strict=True)
    outcome_coverage: GuardianWindowOutcomeCoverage | None = None


def train_guardian_teacher(
    model: GuardianArenaPolicy,
    optimizer: torch.optim.Optimizer,
    rollout: GuardianLearningRollout,
    config: GuardianTrainingConfig,
) -> GuardianTeacherMetrics:
    model.train()
    loss_sum = norm_sum = 0.0
    correct = samples = selected_correct = selected_samples = 0
    permutation = torch.randperm(rollout.batch_size)
    for start in range(0, rollout.batch_size, config.environment_minibatch_size):
        environments = permutation[start : start + config.environment_minibatch_size]
        logits, _ = replay_guardian_rollout(model, rollout, environments)
        actions = rollout.actions[:, environments]
        # Selected-defense mistakes can create repeated toggles. Oversample
        # these visible states without changing legal masks or action decoding.
        selected_defense = (rollout.observations[0][:, environments, 1] > 0) & (
            rollout.observations[4][:, environments, :, 6].any(dim=-1)
        )
        weights = torch.where(selected_defense, config.teacher_selected_defense_weight, 1.0)
        losses = F.cross_entropy(logits.flatten(0, 1), actions.flatten(), reduction="none")
        loss = (losses * weights.flatten()).sum() / weights.sum()
        norm = _optimizer_step(model, optimizer, loss, config)
        count = actions.numel()
        samples += count
        matched = logits.detach().argmax(dim=-1) == actions
        correct += int(matched.sum())
        selected_correct += int((matched & selected_defense).sum())
        selected_samples += int(selected_defense.sum())
        loss_sum += float(loss.detach()) * count
        norm_sum += float(norm) * count
    return GuardianTeacherMetrics(
        loss=loss_sum / samples,
        accuracy=correct / samples,
        gradient_norm=norm_sum / samples,
        selected_defense_accuracy=selected_correct / selected_samples if selected_samples else 0,
        selected_defense_samples=selected_samples,
        utility_statistics=rollout.utility_statistics,
        discarded_cards=rollout.discarded_cards,
        outcome_coverage=rollout.outcome_coverage,
    )


class GuardianPpoMetrics(PpoTrainingMetrics):
    # Historical PPO updates had no feedback measurements. New updates record
    # zero samples when disabled, not fabricated measurements for old records.
    defense_teacher_loss: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    defense_teacher_accuracy: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    defense_teacher_samples: int | None = Field(default=None, ge=0, strict=True)


def train_guardian_ppo(
    model: GuardianArenaPolicy,
    optimizer: torch.optim.Optimizer,
    rollout: GuardianLearningRollout,
    config: GuardianTrainingConfig,
) -> GuardianPpoMetrics:
    model.train()
    selected = rollout.advantages[rollout.policy_trainable]
    if selected.numel() == 0:
        raise GuardianTrainingError("guardian PPO rollout has no learner decisions")
    teacher_actions = rollout.defense_teacher_actions
    if config.defense_feedback_weight > 0 and (
        teacher_actions is None
        or teacher_actions.shape != rollout.actions.shape
        or teacher_actions.dtype != torch.int64
        or bool(
            ((teacher_actions < 0) | (teacher_actions >= model.architecture.action_count)).any()
        )
        or not bool(rollout.observations[6].gather(-1, teacher_actions.unsqueeze(-1)).all())
    ):
        raise GuardianTrainingError("defense feedback requires legal observed-state labels")
    advantages = (rollout.advantages - selected.mean()) / selected.std(unbiased=False).clamp_min(
        1e-8
    )
    totals = dict.fromkeys(PpoTrainingMetrics.model_fields, 0.0)
    samples = 0
    feedback_loss_sum = 0.0
    feedback_samples = feedback_correct = 0
    for _ in range(config.ppo_epochs):
        permutation = torch.randperm(rollout.batch_size)
        for start in range(0, rollout.batch_size, config.environment_minibatch_size):
            envs = permutation[start : start + config.environment_minibatch_size]
            logits, values = replay_guardian_rollout(model, rollout, envs)
            distribution = torch.distributions.Categorical(logits=logits)
            log_prob = distribution.log_prob(rollout.actions[:, envs])  # type: ignore[no-untyped-call]
            entropy_all = distribution.entropy()  # type: ignore[no-untyped-call]
            mask = rollout.policy_trainable[:, envs]
            log_ratio = log_prob[mask] - rollout.old_log_probabilities[:, envs][mask]
            ratio = log_ratio.exp()
            adv = advantages[:, envs][mask]
            policy_loss = (
                torch.maximum(
                    -ratio * adv, -ratio.clamp(1 - config.clip_range, 1 + config.clip_range) * adv
                ).mean()
                if bool(mask.any())
                else log_ratio.sum()
            )
            entropy = entropy_all[mask].mean() if bool(mask.any()) else entropy_all[mask].sum()
            old_values = rollout.old_values[:, envs]
            clipped = old_values + (values - old_values).clamp(
                -config.clip_range, config.clip_range
            )
            returns = rollout.returns[:, envs]
            value_loss = (
                0.5
                * torch.maximum((values - returns).square(), (clipped - returns).square()).mean()
            )
            loss = policy_loss + config.value_weight * value_loss - config.entropy_weight * entropy
            # Supervise only learner-controlled defense states from this on-policy
            # rollout. The sampled actions, PPO likelihoods, rewards and legal
            # masks remain unchanged; no teacher is used at inference time.
            feedback_mask = mask & (rollout.observations[0][:, envs, 1] > 0)
            if config.defense_feedback_scope == "finish-decisions" and teacher_actions is not None:
                feedback_mask &= teacher_actions[:, envs] >= FORGIVE
            if config.defense_feedback_weight > 0 and bool(feedback_mask.any()):
                assert teacher_actions is not None
                labels = teacher_actions[:, envs][feedback_mask]
                predictions = logits[feedback_mask]
                selected_defense = rollout.observations[4][:, envs, :, 6].any(dim=-1)
                weights = torch.where(
                    selected_defense[feedback_mask], config.teacher_selected_defense_weight, 1.0
                )
                losses = F.cross_entropy(predictions, labels, reduction="none")
                feedback_loss = (losses * weights).sum() / weights.sum()
                loss = loss + config.defense_feedback_weight * feedback_loss
                count_feedback = labels.numel()
                feedback_samples += count_feedback
                feedback_correct += int((predictions.detach().argmax(-1) == labels).sum())
                feedback_loss_sum += float(feedback_loss.detach()) * count_feedback
            norm = _optimizer_step(model, optimizer, loss, config)
            kl = ((ratio - 1) - log_ratio).mean() if bool(mask.any()) else ratio.sum()
            fraction = (
                ((ratio - 1).abs() > config.clip_range).float().mean()
                if bool(mask.any())
                else ratio.sum()
            )
            measured = {
                "total_loss": loss,
                "policy_loss": policy_loss,
                "value_loss": value_loss,
                "entropy": entropy,
                "approximate_kl": kl,
                "clip_fraction": fraction,
                "gradient_norm": norm,
            }
            count = values.numel()
            samples += count
            for key, value in measured.items():
                totals[key] += float(value.detach()) * count
    metrics = GuardianPpoMetrics(
        **{key: value / samples for key, value in totals.items()},
        defense_teacher_loss=feedback_loss_sum / feedback_samples if feedback_samples else 0,
        defense_teacher_accuracy=feedback_correct / feedback_samples if feedback_samples else 0,
        defense_teacher_samples=feedback_samples,
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise GuardianTrainingError("guardian PPO metrics are not finite")
    return metrics


class GuardianTruncationCounts(BaseModel):
    turn_limit: int = Field(default=0, ge=0, strict=True)
    defense_selection_limit: int = Field(default=0, ge=0, strict=True)
    decision_limit: int = Field(default=0, ge=0, strict=True)


class GuardianReadyActionCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    attacks: int = Field(default=0, ge=0, strict=True)
    utilities: int = Field(default=0, ge=0, strict=True)
    discards: int = Field(default=0, ge=0, strict=True)
    forced_passes: int = Field(default=0, ge=0, strict=True)
    voluntary_passes: int = Field(default=0, ge=0, strict=True)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class GuardianPlayStatistics(BaseModel):
    """Visible-action diagnostics; pass-only witnesses never change termination."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    decisions_by_phase: tuple[int, ...]
    ready_actions: GuardianReadyActionCounts
    learner_ready_actions: GuardianReadyActionCounts
    mutual_forced_pass_games: int = Field(ge=0, strict=True)
    mutual_forced_pass_truncations: int = Field(ge=0, strict=True)
    stall_witness: Literal["consecutive-distinct-actors-with-pass-only-ready-masks-v1"] = (
        "consecutive-distinct-actors-with-pass-only-ready-masks-v1"
    )

    @model_validator(mode="after")
    def accounted(self) -> GuardianPlayStatistics:
        if (
            len(self.decisions_by_phase) != 6
            or min(self.decisions_by_phase) < 0
            or self.decisions_by_phase[2] != 0
            or self.decisions_by_phase[3] != 0
            or self.decisions_by_phase[0] != self.ready_actions.total
            or self.mutual_forced_pass_truncations > self.mutual_forced_pass_games
            or 2 * self.mutual_forced_pass_games > self.ready_actions.forced_passes
            or any(
                getattr(self.learner_ready_actions, field) > getattr(self.ready_actions, field)
                for field in GuardianReadyActionCounts.model_fields
            )
        ):
            raise ValueError("play diagnostics do not account for observed decisions")
        return self


class _GuardianPlayTracker:
    """One evaluation cohort, without resetting episodes or reading hidden hands."""

    def __init__(self, batch_size: int):
        self.phases = np.zeros(6, dtype=np.int64)
        self.ready = dict.fromkeys(GuardianReadyActionCounts.model_fields, 0)
        self.learner_ready = self.ready.copy()
        self.previous_forced_actor = np.full(batch_size, -1, dtype=np.int64)
        self.stalled = np.zeros(batch_size, dtype=np.bool_)
        self.stalled_truncations = 0

    def observe(
        self, observation: GuardianObservation, actions: IntArray, learner_seat: int
    ) -> None:
        active, actors = observation.active, observation.actors
        self.phases += np.bincount(observation.phases[active], minlength=6)
        ready = active & (observation.phases == 0)
        selected = ready & (actions >= 1) & (actions <= 18)
        utility = np.zeros(len(actions), dtype=np.bool_)
        rows = np.flatnonzero(selected)
        if observation.hand_features.shape[-1] == 9:
            utility[rows] = observation.hand_features[rows, actions[rows] - 1, 7:].any(axis=-1)
        forced = ready & (actions == 0) & ~observation.action_mask[:, 1:].any(axis=-1)
        groups = {
            "attacks": selected & ~utility,
            "utilities": utility,
            "discards": ready & (actions >= DISCARD_START),
            "forced_passes": forced,
            "voluntary_passes": ready & (actions == 0) & ~forced,
        }
        for field, mask in groups.items():
            self.ready[field] += int(np.count_nonzero(mask))
            self.learner_ready[field] += int(np.count_nonzero(mask & (actors == learner_seat)))
        self.stalled |= (
            forced & (self.previous_forced_actor >= 0) & (self.previous_forced_actor != actors)
        )
        self.previous_forced_actor[active & ~forced] = -1
        self.previous_forced_actor[forced] = actors[forced]

    def finish(self, transition: GuardianTransition) -> None:
        self.stalled_truncations += int(
            np.count_nonzero(transition.newly_finished & transition.truncated & self.stalled)
        )

    def statistics(self) -> GuardianPlayStatistics:
        return GuardianPlayStatistics(
            decisions_by_phase=tuple(int(value) for value in self.phases),
            ready_actions=GuardianReadyActionCounts(**self.ready),
            learner_ready_actions=GuardianReadyActionCounts(**self.learner_ready),
            mutual_forced_pass_games=int(np.count_nonzero(self.stalled)),
            mutual_forced_pass_truncations=self.stalled_truncations,
        )


class GuardianEvaluation(BaseModel):
    schema_version: Literal[1] = 1
    seed: int = Field(ge=0, le=2**32 - 1, strict=True)
    games: int = Field(ge=2, le=256, strict=True)
    wins: int = Field(ge=0, strict=True)
    losses: int = Field(ge=0, strict=True)
    truncations: int = Field(ge=0, strict=True)
    wins_by_learner_seat: tuple[int, int]
    losses_by_learner_seat: tuple[int, int]
    truncations_by_learner_seat: tuple[int, int]
    win_fraction_all_games: float = Field(ge=0, le=1, allow_inf_nan=False)
    truncation_causes: GuardianTruncationCounts | None = None
    policy_kind: Literal["neural-greedy", "greedy-reference"] = "neural-greedy"
    replacement_gifts: int | None = Field(default=None, ge=0, strict=True)
    defense_deselections: int | None = Field(default=None, ge=0, strict=True)
    utility_statistics: GuardianUtilityStatistics | None = None
    discarded_cards: int | None = Field(default=None, ge=0, strict=True)
    play_statistics: GuardianPlayStatistics | None = None
    paired_initial_states: Literal[True] = True
    opponent: Literal[
        "greedy-smoke-baseline-v1",
        "greedy-utility-smoke-baseline-v2",
        "greedy-discard-smoke-baseline-v3",
    ] = "greedy-smoke-baseline-v1"
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def all_attempts_counted(self) -> GuardianEvaluation:
        if self.games % 2 or self.wins + self.losses + self.truncations != self.games:
            raise ValueError("paired evaluation must account for every attempted game")
        for counts, total in (
            (self.wins_by_learner_seat, self.wins),
            (self.losses_by_learner_seat, self.losses),
            (self.truncations_by_learner_seat, self.truncations),
        ):
            if min(counts) < 0 or sum(counts) != total:
                raise ValueError("paired evaluation seat totals differ")
        for seat in (0, 1):
            if (
                self.wins_by_learner_seat[seat]
                + self.losses_by_learner_seat[seat]
                + self.truncations_by_learner_seat[seat]
                != self.games // 2
            ):
                raise ValueError("paired evaluation must account for both learner seats")
        if not math.isclose(self.win_fraction_all_games, self.wins / self.games, abs_tol=1e-12):
            raise ValueError("evaluation win fraction excludes attempted games")
        if (
            self.truncation_causes is not None
            and sum(self.truncation_causes.model_dump().values()) != self.truncations
        ):
            raise ValueError("evaluation does not account for every truncation reason")
        stats = self.play_statistics
        if stats is not None and (
            stats.mutual_forced_pass_games > self.games
            or stats.mutual_forced_pass_truncations > self.truncations
            or stats.ready_actions.utilities
            != (self.utility_statistics.uses if self.utility_statistics is not None else 0)
            or stats.ready_actions.discards != (self.discarded_cards or 0)
        ):
            raise ValueError("evaluation play diagnostics differ from game/utility totals")
        return self


def evaluate_guardian_policy(
    model: GuardianArenaPolicy | None,
    *,
    catalog_path: Path,
    bible_path: Path,
    config: GuardianRolloutConfig,
    games: int,
    seed: int,
) -> GuardianEvaluation:
    if config.player_count != 2 or type(games) is not int or not 2 <= games <= 256 or games % 2:
        raise GuardianTrainingError("evaluation requires 2..256 paired duel games")
    wins, losses, truncations = [0, 0], [0, 0], [0, 0]
    causes = GuardianTruncationCounts().model_dump()
    replacement_gifts = 0
    discarded_cards = 0
    defense_deselections = 0
    utility_totals = dict.fromkeys(GuardianUtilityStatistics.model_fields, 0)
    play_statistics = []
    if model is not None:
        model.eval()
    for learner_seat in (0, 1):
        arena_config = config.model_copy(update={"batch_size": games // 2, "seed": seed})
        arena = GuardianRolloutArena(
            catalog_path=catalog_path, bible_path=bible_path, config=arena_config
        )
        memory = torch.zeros((games // 2, model.hidden_size if model is not None else 0))
        tracker = _GuardianPlayTracker(games // 2)
        for _ in range(config.max_decisions):
            observation = arena.observe()
            if not np.any(observation.active):
                break
            actions = greedy_guardian_actions(observation)
            rows = np.flatnonzero(observation.active & (observation.actors == learner_seat))
            if len(rows) and model is not None:
                with torch.no_grad():
                    logits, _, states = model(
                        *guardian_feature_tensors(observation, rows), recurrent_state=memory[rows]
                    )
                actions[rows] = logits.argmax(dim=-1).numpy()
                memory[rows] = states
            defense_rows = np.flatnonzero(
                observation.active & (observation.phases == 1) & (actions >= 1) & (actions <= 18)
            )
            defense_deselections += int(
                np.count_nonzero(
                    observation.hand_features[defense_rows, actions[defense_rows] - 1, 6]
                )
            )
            tracker.observe(observation, actions, learner_seat)
            transition = arena.step(actions)
            tracker.finish(transition)
            ended = transition.newly_finished & transition.terminated
            wins[learner_seat] += int(
                np.count_nonzero(ended & (transition.winners == learner_seat))
            )
            losses[learner_seat] += int(
                np.count_nonzero(ended & (transition.winners != learner_seat))
            )
            truncations[learner_seat] += int(
                np.count_nonzero(transition.newly_finished & transition.truncated)
            )
            reasons = arena.finish_reasons()
            for env in np.flatnonzero(transition.newly_finished & transition.truncated):
                causes[reasons[env]] += 1
        if np.any(arena.observe().active):
            raise GuardianTrainingError("bounded evaluation left unfinished games")
        play_statistics.append(tracker.statistics())
        replacement_gifts += arena.replacement_gifts
        discarded_cards += arena.discarded_cards
        measured = arena.utility_statistics
        if measured is not None:
            for field, value in measured.model_dump().items():
                utility_totals[field] += value
    return GuardianEvaluation(
        seed=seed,
        games=games,
        wins=sum(wins),
        losses=sum(losses),
        truncations=sum(truncations),
        wins_by_learner_seat=(wins[0], wins[1]),
        losses_by_learner_seat=(losses[0], losses[1]),
        truncations_by_learner_seat=(truncations[0], truncations[1]),
        win_fraction_all_games=sum(wins) / games,
        truncation_causes=GuardianTruncationCounts(**causes),
        policy_kind="neural-greedy" if model is not None else "greedy-reference",
        replacement_gifts=replacement_gifts,
        discarded_cards=discarded_cards if config.inventory_discards else None,
        defense_deselections=defense_deselections,
        utility_statistics=GuardianUtilityStatistics(**utility_totals)
        if config.inventory_utilities
        else None,
        play_statistics=GuardianPlayStatistics(
            decisions_by_phase=tuple(
                sum(stats.decisions_by_phase[phase] for stats in play_statistics)
                for phase in range(6)
            ),
            ready_actions=GuardianReadyActionCounts(
                **{
                    field: sum(getattr(stats.ready_actions, field) for stats in play_statistics)
                    for field in GuardianReadyActionCounts.model_fields
                }
            ),
            learner_ready_actions=GuardianReadyActionCounts(
                **{
                    field: sum(
                        getattr(stats.learner_ready_actions, field) for stats in play_statistics
                    )
                    for field in GuardianReadyActionCounts.model_fields
                }
            ),
            mutual_forced_pass_games=sum(
                stats.mutual_forced_pass_games for stats in play_statistics
            ),
            mutual_forced_pass_truncations=sum(
                stats.mutual_forced_pass_truncations for stats in play_statistics
            ),
        ),
        opponent="greedy-discard-smoke-baseline-v3"
        if config.inventory_discards
        else "greedy-utility-smoke-baseline-v2"
        if config.inventory_utilities
        else "greedy-smoke-baseline-v1",
    )


class GuardianUpdateMetrics(BaseModel):
    update: int = Field(ge=1, strict=True)
    ppo: GuardianPpoMetrics
    completed_games: int = Field(ge=0, strict=True)
    truncated_games: int = Field(ge=0, strict=True)
    learner_decisions: int = Field(ge=0, strict=True)
    baseline_decisions: int = Field(ge=0, strict=True)
    decisions_by_phase: tuple[int, ...]
    replacement_gifts: int | None = Field(default=None, ge=0, strict=True)
    utility_statistics: GuardianUtilityStatistics | None = None
    discarded_cards: int | None = Field(default=None, ge=0, strict=True)
    outcome_coverage: GuardianWindowOutcomeCoverage | None = None


class GuardianUtilityMigration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    migration_id: Literal["guardian-card-encoder-7-to-9-role-rescale-v1"] = (
        "guardian-card-encoder-7-to-9-role-rescale-v1"
    )
    source_model_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_architecture: GuardianPolicyArchitecture
    source_arena: GuardianRolloutMetadata
    source_hand_features: Literal[7] = 7
    target_hand_features: Literal[9] = 9
    role_column_multiplier: Literal["7/5"] = "7/5"
    new_columns: Literal["zero-initialized-hp-mp-gain"] = "zero-initialized-hp-mp-gain"
    unchanged_tensors: Literal["all-except-first-card-encoder-weight"] = (
        "all-except-first-card-encoder-weight"
    )
    optimizer_resumed: Literal[False] = False

    @model_validator(mode="after")
    def source_contract(self) -> GuardianUtilityMigration:
        if (
            self.source_architecture.hand_feature_count != 7
            or self.source_arena.config.inventory_utilities
            or self.source_arena.schema_version != 1
        ):
            raise ValueError("utility migration requires a seven-feature source curriculum")
        return self


class GuardianDiscardMigration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    migration_id: Literal["guardian-actions-30-to-48-discard-head-v1"] = (
        "guardian-actions-30-to-48-discard-head-v1"
    )
    source_model_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_architecture: GuardianPolicyArchitecture
    source_arena: GuardianRolloutMetadata
    source_action_count: Literal[30] = 30
    target_action_count: Literal[48] = 48
    unchanged_tensors: Literal["all-source-tensors"] = "all-source-tensors"
    new_head: Literal["copied-card-hidden-layer-zero-output-weight-minus-four-bias"] = (
        "copied-card-hidden-layer-zero-output-weight-minus-four-bias"
    )
    optimizer_resumed: Literal[False] = False

    @model_validator(mode="after")
    def source_contract(self) -> GuardianDiscardMigration:
        if not (
            self.source_architecture.action_count == 30
            and self.source_architecture.hand_feature_count == 9
            and self.source_arena.action_count == 30
            and self.source_arena.hand_feature_count == 9
            and self.source_architecture.observation_schema_id
            == self.source_arena.observation_schema_id
            and self.source_arena.schema_version == 2
            and self.source_arena.config.refill == "weighted-utility-consumption-v1"
        ):
            raise ValueError("discard migration requires a 30-action weighted utility source")
        return self


class GuardianHorizonMigration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    migration_id: Literal["guardian-horizon-input-rescale-v1"] = "guardian-horizon-input-rescale-v1"
    source_model_id: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_architecture: GuardianPolicyArchitecture
    source_arena: GuardianRolloutMetadata
    target_max_turns: int = Field(ge=1, le=100_000, strict=True)
    target_max_decisions: int = Field(ge=1, le=100_000, strict=True)
    turn_column: Literal[7] = 7
    decision_column: Literal[42] = 42
    turn_column_multiplier: float = Field(gt=0, allow_inf_nan=False)
    decision_column_multiplier: float = Field(gt=0, allow_inf_nan=False)
    unchanged_tensors: Literal["all-except-two-global-encoder-weight-columns"] = (
        "all-except-two-global-encoder-weight-columns"
    )
    equivalence_scope: Literal["same-state-predictions-before-old-limits-float-tolerance"] = (
        "same-state-predictions-before-old-limits-float-tolerance"
    )
    optimizer_resumed: Literal[False] = False

    @model_validator(mode="after")
    def source_contract(self) -> GuardianHorizonMigration:
        config = self.source_arena.config
        if (
            self.source_architecture.hand_feature_count != self.source_arena.hand_feature_count
            or self.source_architecture.action_count != self.source_arena.action_count
            or self.source_architecture.observation_schema_id
            != self.source_arena.observation_schema_id
            or config.max_turns != self.source_arena.base_native.max_turns
            or self.target_max_turns < config.max_turns
            or self.target_max_decisions < config.max_decisions
            or (self.target_max_turns, self.target_max_decisions)
            == (config.max_turns, config.max_decisions)
            or self.turn_column_multiplier != self.target_max_turns / config.max_turns
            or self.decision_column_multiplier != self.target_max_decisions / config.max_decisions
        ):
            raise ValueError("horizon migration bounds, source architecture, or ratios differ")
        return self


class GuardianArenaManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2, 3] = 1
    source_kind: Literal[
        "local-guardian-duel-neural-checkpoint-v1",
        "local-guardian-utility-duel-neural-checkpoint-v2",
        "local-guardian-discard-duel-neural-checkpoint-v3",
    ] = "local-guardian-duel-neural-checkpoint-v1"
    observation_schema_id: Literal[
        "actor-relative-guardian-arena-v1",
        "actor-relative-guardian-utility-arena-v2",
        "actor-relative-guardian-discard-arena-v3",
    ] = "actor-relative-guardian-arena-v1"
    policy_architecture: Literal[
        "numeric-slot-recurrent-guardian-arena-v1",
        "numeric-slot-recurrent-guardian-utility-arena-v2",
        "numeric-slot-recurrent-guardian-discard-arena-v3",
    ] = "numeric-slot-recurrent-guardian-arena-v1"
    model_id: str
    created_at: datetime
    weights_file: Literal["arena-weights.pt"] = "arena-weights.pt"
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    architecture: GuardianPolicyArchitecture
    arena: GuardianRolloutMetadata
    training: GuardianTrainingConfig
    algorithm: Literal[
        "provisional-guardian-duel-recurrent-imitation-ppo-v1",
        "provisional-guardian-duel-recurrent-imitation-ppo-defense-feedback-v1",
        "provisional-guardian-duel-recurrent-imitation-only-v1",
    ] = ALGORITHM
    parent_weights_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    utility_migration: GuardianUtilityMigration | None = None
    discard_migration: GuardianDiscardMigration | None = None
    horizon_migration: GuardianHorizonMigration | None = None
    rollout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    teacher_metrics: tuple[GuardianTeacherMetrics, ...]
    update_metrics: tuple[GuardianUpdateMetrics, ...]
    evaluation_before: GuardianEvaluation
    evaluation_after: GuardianEvaluation
    evaluation_teacher: GuardianEvaluation | None = None
    evaluation_baseline: GuardianEvaluation | None = None
    local_training_eligible: Literal[True] = True
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    optimizer_resumed: Literal[False] = False

    @model_validator(mode="after")
    def validate_training_contract(self) -> GuardianArenaManifest:
        utility = self.training.arena.inventory_utilities
        discard = self.training.arena.inventory_discards
        if (
            self.schema_version != (3 if discard else 2 if utility else 1)
            or self.source_kind
            != (
                "local-guardian-discard-duel-neural-checkpoint-v3"
                if discard
                else "local-guardian-utility-duel-neural-checkpoint-v2"
                if utility
                else "local-guardian-duel-neural-checkpoint-v1"
            )
            or self.policy_architecture
            != (
                "numeric-slot-recurrent-guardian-discard-arena-v3"
                if discard
                else "numeric-slot-recurrent-guardian-utility-arena-v2"
                if utility
                else "numeric-slot-recurrent-guardian-arena-v1"
            )
            or self.observation_schema_id != self.arena.observation_schema_id
            or self.observation_schema_id != self.architecture.observation_schema_id
            or self.architecture.hand_feature_count != self.arena.hand_feature_count
            or self.architecture.action_count != self.arena.action_count
        ):
            raise ValueError(
                "checkpoint policy, native curriculum, and observation identities differ"
            )
        migration = self.utility_migration
        if migration is not None and (
            not utility
            or discard
            or self.parent_weights_sha256 != migration.source_weights_sha256
            or migration.source_architecture.model_dump(
                exclude={"hand_feature_count", "observation_schema_id"}
            )
            != self.architecture.model_dump(exclude={"hand_feature_count", "observation_schema_id"})
        ):
            raise ValueError(
                "utility checkpoint migration provenance differs from its parent/architecture"
            )
        if migration is not None:
            source_arena = migration.source_arena
            allowed = {"batch_size", "seed", "inventory_utilities", "refill"}
            common_native_fields = (
                "player_count",
                "slots_per_environment",
                "hand_slots",
                "max_turns",
                "max_defense_actions",
                "initial_hp",
                "initial_mp",
                "initial_cp",
                "defense_model_ids",
                "armor_model_ids",
                "defense_miracle_model_ids",
                "attack_weapon_model_ids",
                "attack_miracle_model_ids",
                "supported_effect_model_ids",
            )
            if (
                source_arena.config.model_dump(exclude=allowed)
                != self.arena.config.model_dump(exclude=allowed)
                or source_arena.base_native.catalog_sha256 != self.arena.base_native.catalog_sha256
                or source_arena.base_native.bible_client_sha256
                != self.arena.base_native.bible_client_sha256
                or (source_arena.config.refill == "none") != (self.arena.config.refill == "none")
                or any(
                    getattr(source_arena.base_native, field)
                    != getattr(self.arena.base_native, field)
                    for field in common_native_fields
                )
            ):
                raise ValueError(
                    "utility migration may not change original combat/reward/bound contracts"
                )
        transfer = self.discard_migration
        expanded_metadata_fields = {
            "native",
            "config",
            "schema_version",
            "source_kind",
            "curriculum_id",
            "observation_schema_id",
            "action_count",
            "acquisition_policy",
            "refill_plan",
            "action_layout",
        }
        if transfer is not None and (
            not discard
            or migration is not None
            or self.parent_weights_sha256 != transfer.source_weights_sha256
            or transfer.source_architecture.model_dump(
                exclude={"action_count", "observation_schema_id"}
            )
            != self.architecture.model_dump(exclude={"action_count", "observation_schema_id"})
            or transfer.source_arena.config.model_dump(
                exclude={"batch_size", "seed", "inventory_discards", "refill"}
            )
            != self.arena.config.model_dump(
                exclude={"batch_size", "seed", "inventory_discards", "refill"}
            )
            or transfer.source_arena.base_native.model_dump(exclude={"batch_size"})
            != self.arena.base_native.model_dump(exclude={"batch_size"})
            or transfer.source_arena.model_dump(exclude=expanded_metadata_fields)
            != self.arena.model_dump(exclude=expanded_metadata_fields)
            or not isinstance(self.arena.refill_plan, GuardianDiscardRefillPlan)
            or transfer.source_arena.refill_plan != self.arena.refill_plan.distribution_base
        ):
            raise ValueError(
                "discard migration may only expand actions/refill, not source/bounds/rewards"
            )
        horizon = self.horizon_migration
        if horizon is not None and (
            migration is not None
            or transfer is not None
            or self.parent_weights_sha256 != horizon.source_weights_sha256
            or self.architecture != horizon.source_architecture
            or self.arena.config.max_turns != horizon.target_max_turns
            or self.arena.base_native.max_turns != horizon.target_max_turns
            or self.arena.config.max_decisions != horizon.target_max_decisions
            or horizon.source_arena.config.model_dump(
                exclude={"batch_size", "seed", "max_turns", "max_decisions"}
            )
            != self.arena.config.model_dump(
                exclude={"batch_size", "seed", "max_turns", "max_decisions"}
            )
            or horizon.source_arena.base_native.model_dump(exclude={"batch_size", "max_turns"})
            != self.arena.base_native.model_dump(exclude={"batch_size", "max_turns"})
            or horizon.source_arena.model_dump(exclude={"native", "config"})
            != self.arena.model_dump(exclude={"native", "config"})
            or (
                discard
                and horizon.source_arena.native.model_dump(exclude={"utility_base"})
                != self.arena.native.model_dump(exclude={"utility_base"})
            )
        ):
            raise ValueError("horizon migration may only extend bounds, not rules/sources/rewards")
        expected_algorithm = (
            IMITATION_ALGORITHM
            if self.training.updates == 0
            else DEFENSE_FEEDBACK_ALGORITHM
            if self.training.defense_feedback_weight > 0
            else ALGORITHM
        )
        if self.algorithm != expected_algorithm:
            raise ValueError("checkpoint learning algorithm differs from feedback configuration")
        if self.arena.config != self.training.arena:
            raise ValueError("checkpoint arena and training configurations differ")
        if (
            len(self.update_metrics) != self.training.updates
            or len(self.teacher_metrics) != self.training.teacher_updates
        ):
            raise ValueError("checkpoint does not contain all declared training updates")
        if (
            self.architecture.hidden_size != self.training.hidden_size
            or self.architecture.embedding_size != self.training.embedding_size
        ):
            raise ValueError("checkpoint architecture differs from training configuration")
        if (
            self.arena.base_native.batch_size != self.training.arena.batch_size
            or self.arena.base_native.player_count != 2
        ):
            raise ValueError("checkpoint native batch does not match its duel curriculum")
        decisions = self.training.arena.batch_size * self.training.rollout_steps
        evaluations = [
            e
            for e in (
                self.evaluation_before,
                self.evaluation_after,
                self.evaluation_baseline,
                self.evaluation_teacher,
            )
            if e is not None
        ]
        collected_measurements = [
            *(metric.utility_statistics for metric in self.update_metrics),
            *(metric.utility_statistics for metric in self.teacher_metrics),
        ]
        measurements = [
            *collected_measurements,
            *(e.utility_statistics for e in evaluations),
        ]
        if (
            utility
            and (self.evaluation_baseline is None or any(metric is None for metric in measurements))
        ) or (not utility and any(metric is not None for metric in measurements)):
            raise ValueError("checkpoint utility statistics must match its measured curriculum")
        if any(metric is not None and metric.uses > decisions for metric in collected_measurements):
            raise ValueError("utility measurements exceed collected decisions")
        discard_counts = [
            *(m.discarded_cards for m in self.teacher_metrics),
            *(m.discarded_cards for m in self.update_metrics),
        ]
        if any(
            (count is None) == discard or (count is not None and count > decisions)
            for count in discard_counts
        ) or any((e.discarded_cards is None) == discard for e in evaluations):
            raise ValueError("checkpoint discard measurements differ from its curriculum")
        expected_opponent = (
            "greedy-discard-smoke-baseline-v3"
            if discard
            else "greedy-utility-smoke-baseline-v2"
            if utility
            else "greedy-smoke-baseline-v1"
        )
        if any(evaluation.opponent != expected_opponent for evaluation in evaluations):
            raise ValueError("checkpoint evaluation opponent differs from the curriculum")
        for index, update in enumerate(self.update_metrics, 1):
            if (
                update.update != index
                or update.learner_decisions + update.baseline_decisions != decisions
                or len(update.decisions_by_phase) != 6
                or min(update.decisions_by_phase) < 0
                or sum(update.decisions_by_phase) != decisions
            ):
                raise ValueError("checkpoint update does not account for all decisions")
            coverage = update.outcome_coverage
            if coverage is not None and (
                coverage.decisions != decisions
                or coverage.trainable_decisions != update.learner_decisions
                or coverage.completed_episodes != update.completed_games
                or coverage.truncated_episodes != update.truncated_games
            ):
                raise ValueError("checkpoint outcome coverage differs from its collected update")
            if not all(
                math.isfinite(value)
                for value in update.ppo.model_dump().values()
                if value is not None
            ):
                raise ValueError("checkpoint has non-finite PPO metrics")
            feedback = update.ppo
            if self.training.defense_feedback_weight > 0 and (
                feedback.defense_teacher_loss is None
                or feedback.defense_teacher_accuracy is None
                or feedback.defense_teacher_samples is None
                or feedback.defense_teacher_samples
                > min(update.learner_decisions, update.decisions_by_phase[1])
                * self.training.ppo_epochs
                or (
                    feedback.defense_teacher_samples == 0
                    and (
                        feedback.defense_teacher_loss != 0 or feedback.defense_teacher_accuracy != 0
                    )
                )
            ):
                raise ValueError("checkpoint requires complete bounded defense feedback metrics")
            if self.training.defense_feedback_weight == 0 and any(
                value not in (None, 0)
                for value in (
                    feedback.defense_teacher_loss,
                    feedback.defense_teacher_accuracy,
                    feedback.defense_teacher_samples,
                )
            ):
                raise ValueError("disabled defense feedback cannot record nonzero measurements")
        if any(
            not all(
                math.isfinite(value)
                for value in teacher.model_dump(
                    exclude={"utility_statistics", "outcome_coverage"}
                ).values()
                if value is not None
            )
            for teacher in self.teacher_metrics
        ):
            raise ValueError("checkpoint has non-finite teacher metrics")
        if any(
            teacher.outcome_coverage is not None
            and (
                teacher.outcome_coverage.decisions != decisions
                or teacher.outcome_coverage.trainable_decisions != decisions
            )
            for teacher in self.teacher_metrics
        ):
            raise ValueError("checkpoint teacher coverage differs from its supervised window")
        expected_seed = (self.training.arena.seed + 1_000_003) % 2**32
        if any(
            evaluation.games != self.training.evaluation_games or evaluation.seed != expected_seed
            for evaluation in evaluations
        ):
            raise ValueError(
                "checkpoint diagnostic evaluations differ from the declared seed/games"
            )
        if any(
            evaluation.play_statistics is not None
            and sum(evaluation.play_statistics.decisions_by_phase)
            > evaluation.games * self.training.arena.max_decisions
            for evaluation in evaluations
        ):
            raise ValueError("checkpoint play diagnostics exceed the bounded evaluation decisions")
        if self.evaluation_teacher is not None and (
            self.training.teacher_updates == 0
            or (self.training.updates == 0 and self.evaluation_teacher != self.evaluation_after)
        ):
            raise ValueError("checkpoint teacher evaluation differs from its declared stages")
        return self


class GuardianTrainingPhaseExposure(BaseModel):
    """Sum independent window classifications; do not relabel open prefixes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["sum-independent-windows-no-backfill-v1"] = (
        "sum-independent-windows-no-backfill-v1"
    )
    windows: int = Field(ge=0, strict=True)
    decisions_per_window: int = Field(ge=1, le=32768, strict=True)
    decisions: int = Field(ge=0, strict=True)
    measured_windows: int = Field(ge=0, strict=True)
    unmeasured_windows: int = Field(ge=0, strict=True)
    measured_window_totals: GuardianWindowOutcomeCoverage | None = None
    winner_covered_trainable_fraction: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def accounted(self) -> GuardianTrainingPhaseExposure:
        total = self.measured_window_totals
        if (
            self.windows != self.measured_windows + self.unmeasured_windows
            or self.decisions != self.windows * self.decisions_per_window
            or (total is None) != (self.measured_windows == 0)
            or (
                total is not None
                and total.decisions != self.measured_windows * self.decisions_per_window
            )
        ):
            raise ValueError("phase exposure must account for measured and unknown windows")
        fraction = self.winner_covered_trainable_fraction
        expected = (
            total.trainable_winner_covered_decisions / total.trainable_decisions
            if total is not None and total.trainable_decisions
            else None
        )
        if (fraction is None) != (expected is None) or (
            fraction is not None
            and expected is not None
            and not math.isclose(fraction, expected, abs_tol=1e-12)
        ):
            raise ValueError("phase outcome fraction must use only measured trainable decisions")
        return self


class GuardianTrainingExposureReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["verified-local-guardian-training-exposure-v1"] = (
        "verified-local-guardian-training-exposure-v1"
    )
    model_id: str
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arena_config: GuardianRolloutConfig
    rollout_steps: int = Field(ge=2, le=256, strict=True)
    teacher: GuardianTrainingPhaseExposure
    ppo: GuardianTrainingPhaseExposure
    evaluation_teacher: GuardianEvaluation | None = None
    evaluation_after: GuardianEvaluation
    checkpoint_weights_verified: Literal[True] = True
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False

    @model_validator(mode="after")
    def window_size(self) -> GuardianTrainingExposureReport:
        expected = self.arena_config.batch_size * self.rollout_steps
        if any(phase.decisions_per_window != expected for phase in (self.teacher, self.ppo)):
            raise ValueError("report exposure differs from the recorded collection window")
        return self


def report_guardian_training_exposure(directory: Path) -> GuardianTrainingExposureReport:
    """Read-only checksum/architecture-verified report; no games or source refresh.

    Historical absent measurements remain unknown. Winner coverage includes
    either side winning, not learner wins, returns, or inferred credit quality.
    """
    # Loading a policy initializes modules before verified tensors replace them.
    # Do not let that consume randomness from a caller's ongoing CPU training.
    with torch.random.fork_rng(devices=[]):
        manifest, _ = load_guardian_checkpoint(directory)
    decisions = manifest.training.arena.batch_size * manifest.training.rollout_steps

    def phase(
        metrics: tuple[GuardianTeacherMetrics, ...] | tuple[GuardianUpdateMetrics, ...],
    ) -> GuardianTrainingPhaseExposure:
        measured = [m.outcome_coverage for m in metrics if m.outcome_coverage is not None]
        total = (
            GuardianWindowOutcomeCoverage.model_validate(
                {
                    field: sum(getattr(m, field) for m in measured)
                    for field in GuardianWindowOutcomeCoverage.model_fields
                    if field not in {"schema_version", "scope"}
                }
            )
            if measured
            else None
        )
        return GuardianTrainingPhaseExposure(
            windows=len(metrics),
            decisions_per_window=decisions,
            decisions=len(metrics) * decisions,
            measured_windows=len(measured),
            unmeasured_windows=len(metrics) - len(measured),
            measured_window_totals=total,
            winner_covered_trainable_fraction=total.trainable_winner_covered_decisions
            / total.trainable_decisions
            if total is not None and total.trainable_decisions
            else None,
        )

    return GuardianTrainingExposureReport(
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        arena_config=manifest.training.arena,
        rollout_steps=manifest.training.rollout_steps,
        teacher=phase(manifest.teacher_metrics),
        ppo=phase(manifest.update_metrics),
        evaluation_teacher=manifest.evaluation_teacher,
        evaluation_after=manifest.evaluation_after,
    )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_guardian_checkpoint(directory: Path) -> tuple[GuardianArenaManifest, GuardianArenaPolicy]:
    manifest = GuardianArenaManifest.model_validate_json(
        (directory / MANIFEST_FILE).read_text(encoding="utf-8")
    )
    if (
        not {"schema_version", "source_kind", "observation_schema_id", "policy_architecture"}
        <= manifest.model_fields_set
    ):
        raise GuardianTrainingError("arena checkpoint requires explicit identities")
    if _file_digest(directory / WEIGHTS_FILE) != manifest.weights_sha256:
        raise GuardianTrainingError("arena checkpoint weight checksum differs")
    model = GuardianArenaPolicy(manifest.architecture)
    model.load_state_dict(
        torch.load(directory / WEIGHTS_FILE, map_location="cpu", weights_only=True)
    )
    if not all(bool(torch.isfinite(parameter).all()) for parameter in model.parameters()):
        raise GuardianTrainingError("arena checkpoint contains non-finite parameters")
    return manifest, model


def _compatible(
    parent: GuardianArenaManifest,
    arena: GuardianRolloutMetadata,
    architecture: GuardianPolicyArchitecture,
) -> None:
    if parent.architecture != architecture or parent.arena.base_native.model_dump(
        exclude={"batch_size"}
    ) != arena.base_native.model_dump(exclude={"batch_size"}):
        raise GuardianTrainingError(
            "arena checkpoint architecture, source pins, or native contract differs"
        )
    if parent.arena.config.model_dump(exclude={"batch_size", "seed"}) != arena.config.model_dump(
        exclude={"batch_size", "seed"}
    ):
        raise GuardianTrainingError("arena checkpoint curriculum/reward configuration differs")
    if parent.arena.model_dump(exclude={"native", "config"}) != arena.model_dump(
        exclude={"native", "config"}
    ) or (
        parent.arena.config.inventory_discards
        and parent.arena.native.model_dump(exclude={"utility_base"})
        != arena.native.model_dump(exclude={"utility_base"})
    ):
        raise GuardianTrainingError("arena checkpoint acquisition/observation contract differs")


def evaluate_guardian_checkpoint(
    directory: Path,
    *,
    catalog_path: Path,
    bible_path: Path,
    games: int,
    seed: int,
    cpu_threads: int = 2,
) -> GuardianEvaluation:
    """Read-only, source-pinned evaluation on separately specified local games."""
    with _runtime(seed, cpu_threads):
        manifest, model = load_guardian_checkpoint(directory)
        fresh = GuardianRolloutArena(
            catalog_path=catalog_path,
            bible_path=bible_path,
            config=manifest.training.arena,
        )
        _compatible(manifest, fresh.metadata, model.architecture)
        return evaluate_guardian_policy(
            model,
            catalog_path=catalog_path,
            bible_path=bible_path,
            config=manifest.training.arena,
            games=games,
            seed=seed,
        )


def _migrate_utility_checkpoint(
    source: Path,
    arena: GuardianRolloutMetadata,
    architecture: GuardianPolicyArchitecture,
    *,
    catalog_path: Path,
    bible_path: Path,
) -> tuple[GuardianArenaManifest, GuardianArenaPolicy, GuardianUtilityMigration]:
    parent, model = load_guardian_checkpoint(source)
    if not arena.config.inventory_utilities or parent.training.arena.inventory_utilities:
        raise GuardianTrainingError(
            "utility migration requires an old source and new utility curriculum"
        )
    # Preserve every original source, native, reward, and episode-bound check.
    # Only the explicit inventory/feature/refill expansion may differ.
    original_config = GuardianRolloutConfig.model_validate(
        {
            **arena.config.model_dump(),
            "inventory_utilities": False,
            "refill": "weighted-consumption-v1" if arena.config.refill != "none" else "none",
        }
    )
    original = GuardianRolloutArena(
        catalog_path=catalog_path, bible_path=bible_path, config=original_config
    )
    old_architecture = GuardianPolicyArchitecture.model_validate(
        {
            **architecture.model_dump(),
            "hand_feature_count": 7,
            "observation_schema_id": "actor-relative-guardian-arena-v1",
        }
    )
    _compatible(parent, original.metadata, old_architecture)
    migrated = migrate_guardian_utility_policy(model, architecture)
    record = GuardianUtilityMigration(
        source_model_id=parent.model_id,
        source_manifest_sha256=_file_digest(source / MANIFEST_FILE),
        source_weights_sha256=parent.weights_sha256,
        source_architecture=parent.architecture,
        source_arena=parent.arena,
    )
    return parent, migrated, record


def _migrate_discard_checkpoint(
    source: Path,
    arena: GuardianRolloutMetadata,
    architecture: GuardianPolicyArchitecture,
    *,
    catalog_path: Path,
    bible_path: Path,
) -> tuple[GuardianArenaManifest, GuardianArenaPolicy, GuardianDiscardMigration]:
    parent, model = load_guardian_checkpoint(source)
    if not arena.config.inventory_discards:
        raise GuardianTrainingError("discard migration requires the separate discard curriculum")
    original_config = GuardianRolloutConfig.model_validate(
        {
            **arena.config.model_dump(),
            "inventory_discards": False,
            "refill": "weighted-utility-consumption-v1",
        }
    )
    original = GuardianRolloutArena(
        catalog_path=catalog_path, bible_path=bible_path, config=original_config
    )
    old_architecture = GuardianPolicyArchitecture.model_validate(
        {
            **architecture.model_dump(),
            "action_count": 30,
            "observation_schema_id": "actor-relative-guardian-utility-arena-v2",
        }
    )
    _compatible(parent, original.metadata, old_architecture)
    migrated = migrate_guardian_discard_policy(model, architecture)
    record = GuardianDiscardMigration(
        source_model_id=parent.model_id,
        source_manifest_sha256=_file_digest(source / MANIFEST_FILE),
        source_weights_sha256=parent.weights_sha256,
        source_architecture=parent.architecture,
        source_arena=parent.arena,
    )
    return parent, migrated, record


def _migrate_horizon_checkpoint(
    source: Path,
    arena: GuardianRolloutMetadata,
    architecture: GuardianPolicyArchitecture,
    *,
    catalog_path: Path,
    bible_path: Path,
) -> tuple[GuardianArenaManifest, GuardianArenaPolicy, GuardianHorizonMigration]:
    parent, model = load_guardian_checkpoint(source)
    original_config = GuardianRolloutConfig.model_validate(
        {
            **arena.config.model_dump(),
            "max_turns": parent.arena.config.max_turns,
            "max_decisions": parent.arena.config.max_decisions,
        }
    )
    original = GuardianRolloutArena(
        catalog_path=catalog_path, bible_path=bible_path, config=original_config
    )
    # Reuse the strict resume contract at the original bounds: no other
    # curriculum, source, architecture, or reward difference is permitted.
    _compatible(parent, original.metadata, architecture)
    migrated = migrate_guardian_horizon_policy(
        model,
        source_max_turns=original_config.max_turns,
        source_max_decisions=original_config.max_decisions,
        target_max_turns=arena.config.max_turns,
        target_max_decisions=arena.config.max_decisions,
    )
    record = GuardianHorizonMigration(
        source_model_id=parent.model_id,
        source_manifest_sha256=_file_digest(source / MANIFEST_FILE),
        source_weights_sha256=parent.weights_sha256,
        source_architecture=parent.architecture,
        source_arena=parent.arena,
        target_max_turns=arena.config.max_turns,
        target_max_decisions=arena.config.max_decisions,
        turn_column_multiplier=arena.config.max_turns / original_config.max_turns,
        decision_column_multiplier=arena.config.max_decisions / original_config.max_decisions,
    )
    return parent, migrated, record


def train_guardian_candidate(
    *,
    catalog_path: Path,
    bible_path: Path,
    checkpoint_root: Path,
    config: GuardianTrainingConfig,
    resume: Path | None = None,
    migrate_utilities_from: Path | None = None,
    migrate_discards_from: Path | None = None,
    migrate_horizon_from: Path | None = None,
) -> tuple[Path, GuardianArenaManifest]:
    """Create a new private local checkpoint; never overwrite a source model."""
    if (
        sum(
            path is not None
            for path in (
                resume,
                migrate_utilities_from,
                migrate_discards_from,
                migrate_horizon_from,
            )
        )
        > 1
    ):
        raise GuardianTrainingError("choose only one resume or explicit migration source")
    if migrate_discards_from is not None and not config.arena.inventory_discards:
        raise GuardianTrainingError("--migrate-discards-from requires --inventory-discards")
    if migrate_utilities_from is not None and (
        not config.arena.inventory_utilities or config.arena.inventory_discards
    ):
        raise GuardianTrainingError("--migrate-utilities-from requires --inventory-utilities")
    with _runtime(config.arena.seed, config.cpu_threads):
        arena = GuardianRolloutArena(
            catalog_path=catalog_path, bible_path=bible_path, config=config.arena
        )
        catalog = read_api_catalog_snapshot(catalog_path)
        architecture = GuardianPolicyArchitecture(
            vocabulary_size=max(item.model_id for item in catalog.items) + 1,
            hidden_size=config.hidden_size,
            embedding_size=config.embedding_size,
            hand_feature_count=arena.metadata.hand_feature_count,
            action_count=arena.metadata.action_count,
            observation_schema_id=arena.metadata.observation_schema_id,
        )
        parent = None
        migration = None
        discard_migration = None
        horizon_migration = None
        if migrate_horizon_from is not None:
            parent, model, horizon_migration = _migrate_horizon_checkpoint(
                migrate_horizon_from,
                arena.metadata,
                architecture,
                catalog_path=catalog_path,
                bible_path=bible_path,
            )
        elif migrate_discards_from is not None:
            parent, model, discard_migration = _migrate_discard_checkpoint(
                migrate_discards_from,
                arena.metadata,
                architecture,
                catalog_path=catalog_path,
                bible_path=bible_path,
            )
        elif migrate_utilities_from is not None:
            parent, model, migration = _migrate_utility_checkpoint(
                migrate_utilities_from,
                arena.metadata,
                architecture,
                catalog_path=catalog_path,
                bible_path=bible_path,
            )
        elif resume is not None:
            parent, model = load_guardian_checkpoint(resume)
            _compatible(parent, arena.metadata, architecture)
        else:
            model = GuardianArenaPolicy(architecture)
        evaluation_seed = (config.arena.seed + 1_000_003) % 2**32
        before = evaluate_guardian_policy(
            model,
            catalog_path=catalog_path,
            bible_path=bible_path,
            config=config.arena,
            games=config.evaluation_games,
            seed=evaluation_seed,
        )
        baseline_reference = evaluate_guardian_policy(
            None,
            catalog_path=catalog_path,
            bible_path=bible_path,
            config=config.arena,
            games=config.evaluation_games,
            seed=evaluation_seed,
        )
        collector = GuardianDuelCollector(arena, model)
        digest = hashlib.sha256(config.model_dump_json().encode())
        teacher_metrics, update_metrics = [], []
        teacher_optimizer = torch.optim.Adam(model.parameters(), lr=config.teacher_learning_rate)
        log = structlog.get_logger()
        for update in range(config.teacher_updates):
            rollout = collector.collect(config, teacher=True)
            teacher_metric = train_guardian_teacher(model, teacher_optimizer, rollout, config)
            teacher_metrics.append(teacher_metric)
            digest.update(bytes.fromhex(rollout.digest))
            log.info(
                "guardian_teacher_update",
                update=update + 1,
                loss=teacher_metric.loss,
                accuracy=teacher_metric.accuracy,
                selected_defense_accuracy=teacher_metric.selected_defense_accuracy,
                utility_statistics=teacher_metric.utility_statistics.model_dump()
                if teacher_metric.utility_statistics is not None
                else None,
                discarded_cards=rollout.discarded_cards,
                outcome_coverage=rollout.outcome_coverage.model_dump()
                if rollout.outcome_coverage is not None
                else None,
            )
        teacher_evaluation = (
            evaluate_guardian_policy(
                model,
                catalog_path=catalog_path,
                bible_path=bible_path,
                config=config.arena,
                games=config.evaluation_games,
                seed=evaluation_seed,
            )
            if config.teacher_updates > 0
            else None
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
        for update in range(config.updates):
            rollout = collector.collect(config)
            metrics = train_guardian_ppo(model, optimizer, rollout, config)
            update_metrics.append(
                GuardianUpdateMetrics(
                    update=update + 1,
                    ppo=metrics,
                    completed_games=rollout.completed_games,
                    truncated_games=rollout.truncated_games,
                    learner_decisions=int(rollout.policy_trainable.sum()),
                    baseline_decisions=int((~rollout.policy_trainable).sum()),
                    decisions_by_phase=rollout.phase_counts,
                    replacement_gifts=rollout.replacement_gifts,
                    utility_statistics=rollout.utility_statistics,
                    discarded_cards=rollout.discarded_cards,
                    outcome_coverage=rollout.outcome_coverage,
                )
            )
            digest.update(bytes.fromhex(rollout.digest))
            log.info(
                "guardian_ppo_update",
                update=update + 1,
                total_loss=metrics.total_loss,
                completed_games=rollout.completed_games,
                truncated_games=rollout.truncated_games,
                replacement_gifts=rollout.replacement_gifts,
                defense_teacher_loss=metrics.defense_teacher_loss,
                defense_teacher_accuracy=metrics.defense_teacher_accuracy,
                defense_teacher_samples=metrics.defense_teacher_samples,
                utility_statistics=rollout.utility_statistics.model_dump()
                if rollout.utility_statistics is not None
                else None,
                discarded_cards=rollout.discarded_cards,
                outcome_coverage=rollout.outcome_coverage.model_dump()
                if rollout.outcome_coverage is not None
                else None,
            )
        after = (
            teacher_evaluation
            if config.updates == 0 and teacher_evaluation is not None
            else evaluate_guardian_policy(
                model,
                catalog_path=catalog_path,
                bible_path=bible_path,
                config=config.arena,
                games=config.evaluation_games,
                seed=evaluation_seed,
            )
        )
        if not all(bool(torch.isfinite(parameter).all()) for parameter in model.parameters()):
            raise GuardianTrainingError("refusing to save non-finite arena weights")
        model_id = str(uuid4())
        checkpoint_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = checkpoint_root / model_id
        directory.mkdir(mode=0o700)
        temporary_weights = directory / f"{WEIGHTS_FILE}.tmp"
        with os.fdopen(
            os.open(temporary_weights, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
        ) as sink:
            torch.save(model.state_dict(), sink)
        os.replace(temporary_weights, directory / WEIGHTS_FILE)
        manifest = GuardianArenaManifest(
            schema_version=3
            if config.arena.inventory_discards
            else 2
            if config.arena.inventory_utilities
            else 1,
            source_kind="local-guardian-discard-duel-neural-checkpoint-v3"
            if config.arena.inventory_discards
            else "local-guardian-utility-duel-neural-checkpoint-v2"
            if config.arena.inventory_utilities
            else "local-guardian-duel-neural-checkpoint-v1",
            observation_schema_id=arena.metadata.observation_schema_id,
            policy_architecture="numeric-slot-recurrent-guardian-discard-arena-v3"
            if config.arena.inventory_discards
            else "numeric-slot-recurrent-guardian-utility-arena-v2"
            if config.arena.inventory_utilities
            else "numeric-slot-recurrent-guardian-arena-v1",
            model_id=model_id,
            created_at=datetime.now(UTC),
            weights_sha256=_file_digest(directory / WEIGHTS_FILE),
            architecture=architecture,
            arena=arena.metadata,
            training=config,
            algorithm=IMITATION_ALGORITHM
            if config.updates == 0
            else DEFENSE_FEEDBACK_ALGORITHM
            if config.defense_feedback_weight > 0
            else ALGORITHM,
            parent_weights_sha256=parent.weights_sha256 if parent is not None else None,
            utility_migration=migration,
            discard_migration=discard_migration,
            horizon_migration=horizon_migration,
            rollout_sha256=digest.hexdigest(),
            teacher_metrics=tuple(teacher_metrics),
            update_metrics=tuple(update_metrics),
            evaluation_before=before,
            evaluation_after=after,
            evaluation_teacher=teacher_evaluation,
            evaluation_baseline=baseline_reference,
        )
        temporary_manifest = directory / f"{MANIFEST_FILE}.tmp"
        with os.fdopen(
            os.open(temporary_manifest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
            "w",
            encoding="utf-8",
        ) as sink:
            sink.write(manifest.model_dump_json(indent=2) + "\n")
        os.replace(temporary_manifest, directory / MANIFEST_FILE)
        return directory, manifest
