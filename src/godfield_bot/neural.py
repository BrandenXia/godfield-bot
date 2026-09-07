from collections.abc import Sequence
from typing import Literal

import torch
from torch import Tensor, nn

from godfield_bot.features import GLOBAL_FEATURE_COUNT, PLAYER_FEATURE_COUNT, StateFeatures

PolicyArchitecture = Literal["pooled-hand-v0", "slot-aware-v1"]
POOLED_HAND_POLICY: PolicyArchitecture = "pooled-hand-v0"
SLOT_AWARE_POLICY: PolicyArchitecture = "slot-aware-v1"


class RecurrentPolicyValueNet(nn.Module):
    """Small masked actor-critic with recurrent state across game observations."""

    def __init__(
        self,
        *,
        vocabulary_size: int,
        action_count: int,
        global_feature_count: int = GLOBAL_FEATURE_COUNT,
        player_feature_count: int = PLAYER_FEATURE_COUNT,
        embedding_size: int = 32,
        hidden_size: int = 128,
        policy_architecture: PolicyArchitecture = SLOT_AWARE_POLICY,
    ) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.global_feature_count = global_feature_count
        self.player_feature_count = player_feature_count
        self.policy_architecture = policy_architecture
        self.artifact_embedding = nn.Embedding(
            vocabulary_size,
            embedding_size,
            padding_idx=0,
        )
        self.player_encoder = nn.Sequential(
            nn.Linear(player_feature_count, hidden_size),
            nn.ReLU(),
        )
        self.global_encoder = nn.Sequential(
            nn.Linear(global_feature_count, hidden_size),
            nn.ReLU(),
        )
        self.observation_encoder = nn.Sequential(
            nn.Linear(hidden_size * 2 + embedding_size, hidden_size),
            nn.ReLU(),
        )
        self.memory = nn.GRUCell(hidden_size, hidden_size)
        self.policy_head = nn.Linear(hidden_size, action_count)
        self.artifact_policy_head = (
            nn.Sequential(
                nn.Linear(hidden_size + embedding_size, hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, 1),
            )
            if policy_architecture == SLOT_AWARE_POLICY
            else None
        )
        self.value_head = nn.Linear(hidden_size, 1)

    def forward(
        self,
        global_features: Tensor,
        player_features: Tensor,
        player_mask: Tensor,
        hand_token_ids: Tensor,
        hand_mask: Tensor,
        action_mask: Tensor,
        recurrent_state: Tensor | None = None,
    ) -> tuple[Tensor, Tensor, Tensor]:
        if global_features.ndim != 2 or global_features.shape[1] != self.global_feature_count:
            raise ValueError("global feature shape does not match policy architecture")
        if player_features.ndim != 3 or player_features.shape[2] != self.player_feature_count:
            raise ValueError("player feature shape does not match policy architecture")
        batch_size = global_features.shape[0]
        if recurrent_state is None:
            recurrent_state = global_features.new_zeros((batch_size, self.hidden_size))

        encoded_players = self.player_encoder(player_features)
        player_weights = player_mask.unsqueeze(-1).to(encoded_players.dtype)
        player_summary = (encoded_players * player_weights).sum(dim=1) / player_weights.sum(
            dim=1
        ).clamp_min(1.0)

        embedded_hand = self.artifact_embedding(hand_token_ids)
        hand_weights = hand_mask.unsqueeze(-1).to(embedded_hand.dtype)
        hand_summary = (embedded_hand * hand_weights).sum(dim=1) / hand_weights.sum(
            dim=1
        ).clamp_min(1.0)

        global_summary = self.global_encoder(global_features)
        observation = self.observation_encoder(
            torch.cat((global_summary, player_summary, hand_summary), dim=-1)
        )
        next_recurrent_state = self.memory(observation, recurrent_state)
        logits = self.policy_head(next_recurrent_state)
        if self.artifact_policy_head is not None:
            hand_slots = hand_token_ids.shape[1]
            if hand_slots + 1 > logits.shape[1]:
                raise ValueError("hand slots do not fit inside the policy action head")
            slot_context = next_recurrent_state.unsqueeze(1).expand(-1, hand_slots, -1)
            artifact_logits = self.artifact_policy_head(
                torch.cat((slot_context, embedded_hand), dim=-1)
            ).squeeze(-1)
            logits = torch.cat(
                (logits[:, :1], artifact_logits, logits[:, hand_slots + 1 :]),
                dim=1,
            )
        if action_mask.shape != logits.shape:
            raise ValueError("action mask shape does not match policy logits")
        if not bool(action_mask.any(dim=1).all()):
            raise ValueError("every batch row must contain a legal action")
        masked_logits = logits.masked_fill(~action_mask, torch.finfo(logits.dtype).min)
        value = self.value_head(next_recurrent_state).squeeze(-1)
        return masked_logits, value, next_recurrent_state


def features_to_tensors(
    features: Sequence[StateFeatures],
    *,
    device: torch.device | str = "cpu",
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
    if not features:
        raise ValueError("at least one encoded state is required")
    return (
        torch.tensor([row.global_features for row in features], dtype=torch.float32, device=device),
        torch.tensor([row.player_features for row in features], dtype=torch.float32, device=device),
        torch.tensor([row.player_mask for row in features], dtype=torch.bool, device=device),
        torch.tensor([row.hand_token_ids for row in features], dtype=torch.long, device=device),
        torch.tensor([row.hand_mask for row in features], dtype=torch.bool, device=device),
        torch.tensor([row.action_mask for row in features], dtype=torch.bool, device=device),
    )
