import math

import torch
from pydantic import BaseModel
from torch import Tensor, nn
from torch.nn import functional as functional

from godfield_bot.neural import RecurrentPolicyValueNet


class TrainingError(RuntimeError):
    """Raised when replay data violates the policy training contract."""


class TrainingMetrics(BaseModel):
    total_loss: float
    policy_loss: float
    value_loss: float
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
