"""Non-mutating outcome coverage for bounded guardian learning windows."""

from __future__ import annotations

from typing import Literal

import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator
from torch import Tensor


class GuardianWindowOutcomeCoverage(BaseModel):
    """A winner may be a win or loss for the acting player; no future is peeked."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    scope: Literal["current-window-only-no-future-peeking-v1"] = (
        "current-window-only-no-future-peeking-v1"
    )
    decisions: int = Field(ge=1, strict=True)
    completed_episodes: int = Field(ge=0, strict=True)
    truncated_episodes: int = Field(ge=0, strict=True)
    winner_covered_decisions: int = Field(ge=0, strict=True)
    truncation_covered_decisions: int = Field(ge=0, strict=True)
    open_decisions: int = Field(ge=0, strict=True)
    trainable_decisions: int = Field(ge=0, strict=True)
    trainable_winner_covered_decisions: int = Field(ge=0, strict=True)
    trainable_truncation_covered_decisions: int = Field(ge=0, strict=True)
    trainable_open_decisions: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def accounted(self) -> GuardianWindowOutcomeCoverage:
        groups = (
            (self.winner_covered_decisions, self.trainable_winner_covered_decisions),
            (self.truncation_covered_decisions, self.trainable_truncation_covered_decisions),
            (self.open_decisions, self.trainable_open_decisions),
        )
        if (
            sum(total for total, _ in groups) != self.decisions
            or sum(eligible for _, eligible in groups) != self.trainable_decisions
            or any(eligible > total for total, eligible in groups)
            or self.completed_episodes > self.winner_covered_decisions
            or self.truncated_episodes > self.truncation_covered_decisions
            or (self.completed_episodes == 0) != (self.winner_covered_decisions == 0)
            or (self.truncated_episodes == 0) != (self.truncation_covered_decisions == 0)
        ):
            raise ValueError("guardian outcome coverage must account for every sampled decision")
        return self


def count_guardian_window_outcomes(
    *, terminated: Tensor, truncated: Tensor, trainable: Tensor
) -> GuardianWindowOutcomeCoverage:
    """Classify each decision by its next absorbing outcome inside this window.

    Episode boundaries override later outcomes. An unfinished tail stays open,
    even if its game finishes in a subsequent collection window. This is only
    observability: it does not alter signed GAE, bootstrap values, or gradients.
    Trainable means imitation-eligible in teacher collection and learner-policy
    eligible in PPO collection, not necessarily neural-controlled in both modes.
    """
    if (
        terminated.ndim != 2
        or terminated.numel() == 0
        or truncated.shape != terminated.shape
        or trainable.shape != terminated.shape
        or any(
            t.dtype != torch.bool or t.device != terminated.device
            for t in (terminated, truncated, trainable)
        )
        or bool((terminated & truncated).any())
    ):
        raise ValueError("guardian outcome flags require disjoint matching boolean windows")
    labels = torch.zeros_like(terminated, dtype=torch.int64)
    future = labels.new_zeros(terminated.shape[1])
    for step in range(terminated.shape[0] - 1, -1, -1):
        future = torch.where(terminated[step], 1, torch.where(truncated[step], 2, future))
        labels[step] = future
    winner, limited, open_ = labels == 1, labels == 2, labels == 0
    return GuardianWindowOutcomeCoverage(
        decisions=terminated.numel(),
        completed_episodes=int(terminated.sum()),
        truncated_episodes=int(truncated.sum()),
        winner_covered_decisions=int(winner.sum()),
        truncation_covered_decisions=int(limited.sum()),
        open_decisions=int(open_.sum()),
        trainable_decisions=int(trainable.sum()),
        trainable_winner_covered_decisions=int((trainable & winner).sum()),
        trainable_truncation_covered_decisions=int((trainable & limited).sum()),
        trainable_open_decisions=int((trainable & open_).sum()),
    )
