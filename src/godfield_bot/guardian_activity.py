"""Opt-in local training prior, not a game rule or inference-time pass ban."""

from __future__ import annotations

import torch
from torch import Tensor
from torch.nn import functional as F


def guardian_ready_activity_loss(
    logits: Tensor, legal_actions: Tensor, learner_ready: Tensor
) -> tuple[Tensor, Tensor, int]:
    """Encourage probability of the nonpass group, not a particular move.

    Eligible states are learner-controlled ready states with both pass and a
    legal alternative. Forced passes, other phases and baseline-controlled
    states are excluded. Returns mean negative log group probability, mean
    pass probability and eligible sample count. No actions/labels are replaced.
    """
    if (
        logits.ndim < 2
        or logits.shape[-1] not in (30, 48)
        or legal_actions.shape != logits.shape
        or learner_ready.shape != logits.shape[:-1]
        or not logits.is_floating_point()
        or legal_actions.dtype != torch.bool
        or learner_ready.dtype != torch.bool
        or legal_actions.device != logits.device
        or learner_ready.device != logits.device
    ):
        raise ValueError("ready activity requires matching logits and boolean observed-state masks")
    if not bool(torch.isfinite(logits[legal_actions]).all()):
        raise ValueError("ready activity refuses non-finite legal logits")
    eligible = learner_ready & legal_actions[..., 0] & legal_actions[..., 1:].any(-1)
    count = int(eligible.sum())
    if count == 0:
        # Mask before multiplying: illegal -inf and large masked sentinels must
        # not turn a connected zero into NaN through reduction overflow.
        zero = logits.masked_fill(~legal_actions, 0).mul(0).sum()
        return zero, zero.detach(), 0
    selected = logits[eligible].masked_fill(~legal_actions[eligible], float("-inf"))
    log_probabilities = F.log_softmax(selected, dim=-1)
    loss = (-torch.logsumexp(log_probabilities[:, 1:], dim=-1)).clamp_min(0).mean()
    pass_probability = log_probabilities[:, 0].exp().mean()
    return loss, pass_probability.detach(), count
