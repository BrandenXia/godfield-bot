"""Separate numeric-slot recurrent policy for the provisional local arena."""

from __future__ import annotations

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field
from torch import Tensor, nn

from godfield_bot.guardian_rollout import (
    ACTION_COUNT,
    GLOBAL_FEATURE_COUNT,
    HAND_FEATURE_COUNT,
    HAND_SLOTS,
    MAX_PLAYERS,
    PLAYER_FEATURE_COUNT,
    GuardianObservation,
    IntArray,
)


class GuardianPolicyArchitecture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    vocabulary_size: int = Field(ge=2, le=4096, strict=True)
    embedding_size: int = Field(default=32, ge=8, le=128, strict=True)
    hidden_size: int = Field(default=128, ge=16, le=256, strict=True)


def guardian_feature_tensors(
    observation: GuardianObservation, rows: IntArray | None = None
) -> tuple[Tensor, ...]:
    """Copy read-only policy projections; never include rollout bookkeeping."""
    return tuple(
        torch.from_numpy(np.array(value if rows is None else value[rows], copy=True))
        for value in (
            observation.global_features,
            observation.players,
            observation.player_mask,
            observation.hand_model_ids,
            observation.hand_features,
            observation.hand_mask,
            observation.action_mask,
        )
    )


class GuardianArenaPolicy(nn.Module):
    """Own numeric cards and distinct self/enemy summaries, with per-seat memory.

    Raw catalog model IDs are embedding tokens; zero is the empty-slot padding.
    Slot and target scoring are shared, rather than tied to fixed seat numbers.
    This module is deliberately not registered as a live RecurrentPolicyValueNet.
    """

    def __init__(self, architecture: GuardianPolicyArchitecture):
        super().__init__()
        self.architecture = architecture
        self.hidden_size = architecture.hidden_size
        hidden = architecture.hidden_size
        self.artifact_embedding = nn.Embedding(
            architecture.vocabulary_size, architecture.embedding_size, padding_idx=0
        )
        self.card_encoder = nn.Sequential(
            nn.Linear(architecture.embedding_size + HAND_FEATURE_COUNT, hidden), nn.ReLU()
        )
        self.player_encoder = nn.Sequential(nn.Linear(PLAYER_FEATURE_COUNT, hidden), nn.ReLU())
        self.global_encoder = nn.Sequential(nn.Linear(GLOBAL_FEATURE_COUNT, hidden), nn.ReLU())
        self.observation_encoder = nn.Sequential(nn.Linear(hidden * 4, hidden), nn.ReLU())
        self.memory = nn.GRUCell(hidden, hidden)
        self.control_head = nn.Linear(hidden, 3)  # pass, forgive, confirm
        self.card_head = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.ReLU(), nn.Linear(hidden, 1)
        )
        self.target_head = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.ReLU(), nn.Linear(hidden, 1)
        )
        self.value_head = nn.Linear(hidden, 1)

    def forward(
        self,
        global_features: Tensor,
        players: Tensor,
        player_mask: Tensor,
        hand_model_ids: Tensor,
        hand_features: Tensor,
        hand_mask: Tensor,
        action_mask: Tensor,
        recurrent_state: Tensor | None = None,
    ) -> tuple[Tensor, Tensor, Tensor]:
        batch = global_features.shape[0]
        if (
            global_features.shape != (batch, GLOBAL_FEATURE_COUNT)
            or players.shape != (batch, MAX_PLAYERS, PLAYER_FEATURE_COUNT)
            or player_mask.shape != (batch, MAX_PLAYERS)
            or hand_model_ids.shape != (batch, HAND_SLOTS)
            or hand_features.shape != (batch, HAND_SLOTS, HAND_FEATURE_COUNT)
            or hand_mask.shape != (batch, HAND_SLOTS)
            or action_mask.shape != (batch, ACTION_COUNT)
        ):
            raise ValueError("guardian policy feature shape differs from arena schema")
        if not bool(action_mask.any(dim=1).all()):
            raise ValueError("guardian policy requires an active legal action in every row")
        if bool(
            ((hand_model_ids < 0) | (hand_model_ids >= self.architecture.vocabulary_size)).any()
        ):
            raise ValueError("guardian policy model ID is outside its pinned vocabulary")
        if recurrent_state is None:
            recurrent_state = global_features.new_zeros((batch, self.hidden_size))
        if recurrent_state.shape != (batch, self.hidden_size):
            raise ValueError("guardian policy recurrent-state shape differs")
        cards = self.card_encoder(
            torch.cat((self.artifact_embedding(hand_model_ids), hand_features), dim=-1)
        )
        hand_weights = hand_mask.unsqueeze(-1).to(cards.dtype)
        hand_summary = (cards * hand_weights).sum(dim=1) / hand_weights.sum(dim=1).clamp_min(1)
        encoded_players = self.player_encoder(players)
        enemy_weights = player_mask.clone()
        enemy_weights[:, 0] = False
        weights = enemy_weights.unsqueeze(-1).to(encoded_players.dtype)
        enemy_summary = (encoded_players * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1)
        encoded = self.observation_encoder(
            torch.cat(
                (
                    self.global_encoder(global_features),
                    encoded_players[:, 0],
                    enemy_summary,
                    hand_summary,
                ),
                dim=-1,
            )
        )
        state = self.memory(encoded, recurrent_state)
        controls = self.control_head(state)
        slots = self.card_head(
            torch.cat((state[:, None].expand(-1, HAND_SLOTS, -1), cards), dim=-1)
        ).squeeze(-1)
        targets = self.target_head(
            torch.cat((state[:, None].expand(-1, MAX_PLAYERS, -1), encoded_players), dim=-1)
        ).squeeze(-1)
        logits = torch.cat((controls[:, :1], slots, targets, controls[:, 1:]), dim=1)
        values = self.value_head(state).squeeze(-1)
        if not bool(torch.isfinite(logits).all()) or not bool(torch.isfinite(values).all()):
            raise ValueError("guardian policy produced non-finite outputs")
        return logits.masked_fill(~action_mask, torch.finfo(logits.dtype).min), values, state
