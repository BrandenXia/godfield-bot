import math
from collections.abc import Sequence

import torch
from pydantic import BaseModel
from torch import Tensor, nn
from torch.nn import functional as functional

from godfield_bot.features import StateFeatures
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors


class TrainingError(RuntimeError):
    """Raised when replay data violates the policy training contract."""


class TrainingMetrics(BaseModel):
    total_loss: float
    policy_loss: float
    value_loss: float
    entropy: float
    gradient_norm: float


class ImitationMetrics(BaseModel):
    loss: float
    accuracy: float
    entropy: float
    gradient_norm: float


def actor_critic_loss(
    logits: Tensor,
    values: Tensor,
    target_actions: Tensor,
    returns: Tensor,
    *,
    value_weight: float = 0.5,
    entropy_weight: float = 0.01,
) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    if logits.ndim != 2 or values.ndim != 1:
        raise TrainingError("policy logits and values have invalid dimensions")
    if target_actions.shape != values.shape or returns.shape != values.shape:
        raise TrainingError("training targets do not match batch size")
    selected_logits = logits.gather(1, target_actions.unsqueeze(1)).squeeze(1)
    if bool((selected_logits == torch.finfo(logits.dtype).min).any()):
        raise TrainingError("replay selected an action masked as illegal")

    policy_loss = functional.cross_entropy(logits, target_actions)
    value_loss = functional.mse_loss(values, returns)
    probabilities = functional.softmax(logits, dim=-1)
    log_probabilities = functional.log_softmax(logits, dim=-1)
    entropy = -(probabilities * log_probabilities).sum(dim=-1).mean()
    total_loss = policy_loss + value_weight * value_loss - entropy_weight * entropy
    return total_loss, policy_loss, value_loss, entropy


def sparse_outcome_actor_critic_loss(
    logits: Tensor,
    values: Tensor,
    target_actions: Tensor,
    returns: Tensor,
    *,
    value_weight: float = 0.5,
    entropy_weight: float = 0.01,
) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    """Apply signed terminal advantage to actions observed in official games."""

    if logits.ndim != 2 or values.ndim != 1:
        raise TrainingError("policy logits and values have invalid dimensions")
    if target_actions.shape != values.shape or returns.shape != values.shape:
        raise TrainingError("training targets do not match batch size")
    selected_logits = logits.gather(1, target_actions.unsqueeze(1)).squeeze(1)
    if bool((selected_logits == torch.finfo(logits.dtype).min).any()):
        raise TrainingError("replay selected an action masked as illegal")

    log_probabilities = functional.log_softmax(logits, dim=-1)
    selected_log_probabilities = log_probabilities.gather(
        1, target_actions.unsqueeze(1)
    ).squeeze(1)
    advantages = returns - values.detach()
    policy_loss = -(selected_log_probabilities * advantages).mean()
    value_loss = functional.mse_loss(values, returns)
    probabilities = functional.softmax(logits, dim=-1)
    entropy = -(probabilities * log_probabilities).sum(dim=-1).mean()
    total_loss = policy_loss + value_weight * value_loss - entropy_weight * entropy
    return total_loss, policy_loss, value_loss, entropy


def train_step(
    model: RecurrentPolicyValueNet,
    optimizer: torch.optim.Optimizer,
    inputs: tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor],
    target_actions: Tensor,
    returns: Tensor,
    *,
    max_gradient_norm: float = 1.0,
) -> TrainingMetrics:
    model.train()
    optimizer.zero_grad(set_to_none=True)
    logits, values, _ = model(*inputs)
    total_loss, policy_loss, value_loss, entropy = actor_critic_loss(
        logits,
        values,
        target_actions,
        returns,
    )
    total_loss.backward()  # type: ignore[no-untyped-call]
    gradient_norm = nn.utils.clip_grad_norm_(model.parameters(), max_gradient_norm)
    optimizer.step()
    metrics = TrainingMetrics(
        total_loss=float(total_loss.detach()),
        policy_loss=float(policy_loss.detach()),
        value_loss=float(value_loss.detach()),
        entropy=float(entropy.detach()),
        gradient_norm=float(gradient_norm.detach()),
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise TrainingError("training step produced non-finite metrics")
    return metrics


def outcome_supervised_sequence_step(
    model: RecurrentPolicyValueNet,
    optimizer: torch.optim.Optimizer,
    features: Sequence[StateFeatures],
    target_actions: Sequence[int],
    terminal_return: float,
    *,
    value_weight: float = 0.5,
    entropy_weight: float = 0.01,
    max_gradient_norm: float = 1.0,
) -> TrainingMetrics:
    """Train one recurrent episode using its signed sparse terminal advantage."""

    if not features or len(features) != len(target_actions):
        raise TrainingError("outcome features and actions must be a non-empty aligned sequence")
    if terminal_return not in {-1.0, 0.0, 1.0}:
        raise TrainingError("outcome training requires a sparse terminal return")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    recurrent_state: Tensor | None = None
    logits_rows: list[Tensor] = []
    value_rows: list[Tensor] = []
    for state_features in features:
        logits, values, recurrent_state = model(
            *features_to_tensors([state_features]),
            recurrent_state=recurrent_state,
        )
        logits_rows.append(logits)
        value_rows.append(values)
    logits = torch.cat(logits_rows)
    values = torch.cat(value_rows)
    actions = torch.tensor(target_actions, dtype=torch.long, device=logits.device)
    returns = torch.full_like(values, terminal_return)
    total_loss, policy_loss, value_loss, entropy = sparse_outcome_actor_critic_loss(
        logits,
        values,
        actions,
        returns,
        value_weight=value_weight,
        entropy_weight=entropy_weight,
    )
    total_loss.backward()  # type: ignore[no-untyped-call]
    gradient_norm = nn.utils.clip_grad_norm_(model.parameters(), max_gradient_norm)
    optimizer.step()
    metrics = TrainingMetrics(
        total_loss=float(total_loss.detach()),
        policy_loss=float(policy_loss.detach()),
        value_loss=float(value_loss.detach()),
        entropy=float(entropy.detach()),
        gradient_norm=float(gradient_norm.detach()),
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise TrainingError("outcome training step produced non-finite metrics")
    return metrics


def evaluate_outcome_sequences(
    model: RecurrentPolicyValueNet,
    episodes: Sequence[tuple[Sequence[StateFeatures], Sequence[int], float]],
    *,
    value_weight: float = 0.5,
    entropy_weight: float = 0.01,
) -> TrainingMetrics:
    if not episodes or any(
        not features or len(features) != len(actions)
        for features, actions, _ in episodes
    ):
        raise TrainingError("outcome evaluation requires aligned episodes")
    if any(terminal_return not in {-1.0, 0.0, 1.0} for _, _, terminal_return in episodes):
        raise TrainingError("outcome evaluation requires sparse terminal returns")
    model.eval()
    logits_rows: list[Tensor] = []
    value_rows: list[Tensor] = []
    action_rows: list[int] = []
    return_rows: list[float] = []
    with torch.no_grad():
        for features, actions, terminal_return in episodes:
            recurrent_state: Tensor | None = None
            for state_features, target_action in zip(features, actions, strict=True):
                logits, values, recurrent_state = model(
                    *features_to_tensors([state_features]),
                    recurrent_state=recurrent_state,
                )
                logits_rows.append(logits)
                value_rows.append(values)
                action_rows.append(target_action)
                return_rows.append(terminal_return)
        logits = torch.cat(logits_rows)
        values = torch.cat(value_rows)
        targets = torch.tensor(action_rows, dtype=torch.long, device=logits.device)
        returns = torch.tensor(return_rows, dtype=values.dtype, device=values.device)
        total_loss, policy_loss, value_loss, entropy = sparse_outcome_actor_critic_loss(
            logits,
            values,
            targets,
            returns,
            value_weight=value_weight,
            entropy_weight=entropy_weight,
        )
    metrics = TrainingMetrics(
        total_loss=float(total_loss),
        policy_loss=float(policy_loss),
        value_loss=float(value_loss),
        entropy=float(entropy),
        gradient_norm=0.0,
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise TrainingError("outcome evaluation produced non-finite metrics")
    return metrics


def behavior_cloning_sequence_step(
    model: RecurrentPolicyValueNet,
    optimizer: torch.optim.Optimizer,
    features: Sequence[StateFeatures],
    target_actions: Sequence[int],
    *,
    max_gradient_norm: float = 1.0,
) -> ImitationMetrics:
    """Learn one run sequence without assigning synthetic value targets."""

    if not features or len(features) != len(target_actions):
        raise TrainingError("imitation features and actions must be a non-empty aligned sequence")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    recurrent_state: Tensor | None = None
    losses: list[Tensor] = []
    entropies: list[Tensor] = []
    correct = 0
    for state_features, target_action in zip(features, target_actions, strict=True):
        logits, _, recurrent_state = model(
            *features_to_tensors([state_features]),
            recurrent_state=recurrent_state,
        )
        if target_action < 0 or target_action >= logits.shape[1]:
            raise TrainingError("imitation action lies outside the policy head")
        target = torch.tensor([target_action], dtype=torch.long, device=logits.device)
        selected_logit = logits[0, target_action]
        if selected_logit == torch.finfo(logits.dtype).min:
            raise TrainingError("imitation selected an action masked as illegal")
        losses.append(functional.cross_entropy(logits, target))
        probabilities = functional.softmax(logits, dim=-1)
        log_probabilities = functional.log_softmax(logits, dim=-1)
        entropies.append(-(probabilities * log_probabilities).sum(dim=-1).mean())
        correct += int(logits.argmax(dim=1).item() == target_action)

    loss = torch.stack(losses).mean()
    entropy = torch.stack(entropies).mean()
    loss.backward()  # type: ignore[no-untyped-call]
    gradient_norm = nn.utils.clip_grad_norm_(model.parameters(), max_gradient_norm)
    optimizer.step()
    metrics = ImitationMetrics(
        loss=float(loss.detach()),
        accuracy=correct / len(features),
        entropy=float(entropy.detach()),
        gradient_norm=float(gradient_norm.detach()),
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise TrainingError("imitation step produced non-finite metrics")
    return metrics


def evaluate_imitation_sequences(
    model: RecurrentPolicyValueNet,
    trajectories: Sequence[tuple[Sequence[StateFeatures], Sequence[int]]],
) -> ImitationMetrics:
    if not trajectories or any(
        not features or len(features) != len(actions) for features, actions in trajectories
    ):
        raise TrainingError("imitation evaluation requires aligned trajectories")
    model.eval()
    losses: list[Tensor] = []
    entropies: list[Tensor] = []
    correct = 0
    sample_count = 0
    with torch.no_grad():
        for features, actions in trajectories:
            recurrent_state: Tensor | None = None
            for state_features, target_action in zip(features, actions, strict=True):
                logits, _, recurrent_state = model(
                    *features_to_tensors([state_features]),
                    recurrent_state=recurrent_state,
                )
                if target_action < 0 or target_action >= logits.shape[1]:
                    raise TrainingError("imitation action lies outside the policy head")
                if logits[0, target_action] == torch.finfo(logits.dtype).min:
                    raise TrainingError("imitation selected an action masked as illegal")
                target = torch.tensor([target_action], dtype=torch.long, device=logits.device)
                losses.append(functional.cross_entropy(logits, target))
                probabilities = functional.softmax(logits, dim=-1)
                log_probabilities = functional.log_softmax(logits, dim=-1)
                entropies.append(-(probabilities * log_probabilities).sum(dim=-1).mean())
                correct += int(logits.argmax(dim=1).item() == target_action)
                sample_count += 1
    metrics = ImitationMetrics(
        loss=float(torch.stack(losses).mean()),
        accuracy=correct / sample_count,
        entropy=float(torch.stack(entropies).mean()),
        gradient_norm=0.0,
    )
    if not all(math.isfinite(value) for value in metrics.model_dump().values()):
        raise TrainingError("imitation evaluation produced non-finite metrics")
    return metrics
