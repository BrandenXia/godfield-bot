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
from godfield_bot.guardian_neural import (
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
    guardian_feature_tensors,
)
from godfield_bot.guardian_rollout import (
    ACTION_COUNT,
    FORGIVE,
    GuardianRolloutArena,
    GuardianRolloutConfig,
    GuardianRolloutMetadata,
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
    updates: int = Field(default=10, ge=1, le=1000, strict=True)
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
        initial_states = self.states.detach().clone()
        completed = truncated = 0
        initial_gifts = self.arena.replacement_gifts
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
            torch.stack(trainable_history),
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
        or bool(((teacher_actions < 0) | (teacher_actions >= ACTION_COUNT)).any())
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
    paired_initial_states: Literal[True] = True
    opponent: Literal["greedy-smoke-baseline-v1"] = "greedy-smoke-baseline-v1"
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
    defense_deselections = 0
    if model is not None:
        model.eval()
    for learner_seat in (0, 1):
        arena_config = config.model_copy(update={"batch_size": games // 2, "seed": seed})
        arena = GuardianRolloutArena(
            catalog_path=catalog_path, bible_path=bible_path, config=arena_config
        )
        memory = torch.zeros((games // 2, model.hidden_size if model is not None else 0))
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
            transition = arena.step(actions)
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
        replacement_gifts += arena.replacement_gifts
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
        defense_deselections=defense_deselections,
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


class GuardianArenaManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["local-guardian-duel-neural-checkpoint-v1"] = (
        "local-guardian-duel-neural-checkpoint-v1"
    )
    observation_schema_id: Literal["actor-relative-guardian-arena-v1"] = (
        "actor-relative-guardian-arena-v1"
    )
    policy_architecture: Literal["numeric-slot-recurrent-guardian-arena-v1"] = (
        "numeric-slot-recurrent-guardian-arena-v1"
    )
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
    ] = ALGORITHM
    parent_weights_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rollout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    teacher_metrics: tuple[GuardianTeacherMetrics, ...]
    update_metrics: tuple[GuardianUpdateMetrics, ...]
    evaluation_before: GuardianEvaluation
    evaluation_after: GuardianEvaluation
    evaluation_baseline: GuardianEvaluation | None = None
    local_training_eligible: Literal[True] = True
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    optimizer_resumed: Literal[False] = False

    @model_validator(mode="after")
    def validate_training_contract(self) -> GuardianArenaManifest:
        expected_algorithm = (
            DEFENSE_FEEDBACK_ALGORITHM if self.training.defense_feedback_weight > 0 else ALGORITHM
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
            self.arena.native.batch_size != self.training.arena.batch_size
            or self.arena.native.player_count != 2
        ):
            raise ValueError("checkpoint native batch does not match its duel curriculum")
        decisions = self.training.arena.batch_size * self.training.rollout_steps
        for index, update in enumerate(self.update_metrics, 1):
            if (
                update.update != index
                or update.learner_decisions + update.baseline_decisions != decisions
                or len(update.decisions_by_phase) != 6
                or min(update.decisions_by_phase) < 0
                or sum(update.decisions_by_phase) != decisions
            ):
                raise ValueError("checkpoint update does not account for all decisions")
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
                math.isfinite(value) for value in teacher.model_dump().values() if value is not None
            )
            for teacher in self.teacher_metrics
        ):
            raise ValueError("checkpoint has non-finite teacher metrics")
        expected_seed = (self.training.arena.seed + 1_000_003) % 2**32
        if any(
            evaluation.games != self.training.evaluation_games or evaluation.seed != expected_seed
            for evaluation in (
                self.evaluation_before,
                self.evaluation_after,
                self.evaluation_baseline,
            )
            if evaluation is not None
        ):
            raise ValueError(
                "checkpoint diagnostic evaluations differ from the declared seed/games"
            )
        return self


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
    if parent.architecture != architecture or parent.arena.native.model_dump(
        exclude={"batch_size"}
    ) != arena.native.model_dump(exclude={"batch_size"}):
        raise GuardianTrainingError(
            "arena checkpoint architecture, source pins, or native contract differs"
        )
    if parent.arena.config.model_dump(exclude={"batch_size", "seed"}) != arena.config.model_dump(
        exclude={"batch_size", "seed"}
    ):
        raise GuardianTrainingError("arena checkpoint curriculum/reward configuration differs")
    if parent.arena.model_dump(exclude={"native", "config"}) != arena.model_dump(
        exclude={"native", "config"}
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


def train_guardian_candidate(
    *,
    catalog_path: Path,
    bible_path: Path,
    checkpoint_root: Path,
    config: GuardianTrainingConfig,
    resume: Path | None = None,
) -> tuple[Path, GuardianArenaManifest]:
    """Create a new private local checkpoint; never overwrite a source model."""
    with _runtime(config.arena.seed, config.cpu_threads):
        arena = GuardianRolloutArena(
            catalog_path=catalog_path, bible_path=bible_path, config=config.arena
        )
        catalog = read_api_catalog_snapshot(catalog_path)
        architecture = GuardianPolicyArchitecture(
            vocabulary_size=max(item.model_id for item in catalog.items) + 1,
            hidden_size=config.hidden_size,
            embedding_size=config.embedding_size,
        )
        parent = None
        if resume is not None:
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
            )
        after = evaluate_guardian_policy(
            model,
            catalog_path=catalog_path,
            bible_path=bible_path,
            config=config.arena,
            games=config.evaluation_games,
            seed=evaluation_seed,
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
            model_id=model_id,
            created_at=datetime.now(UTC),
            weights_sha256=_file_digest(directory / WEIGHTS_FILE),
            architecture=architecture,
            arena=arena.metadata,
            training=config,
            algorithm=DEFENSE_FEEDBACK_ALGORITHM
            if config.defense_feedback_weight > 0
            else ALGORITHM,
            parent_weights_sha256=parent.weights_sha256 if parent is not None else None,
            rollout_sha256=digest.hexdigest(),
            teacher_metrics=tuple(teacher_metrics),
            update_metrics=tuple(update_metrics),
            evaluation_before=before,
            evaluation_after=after,
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
