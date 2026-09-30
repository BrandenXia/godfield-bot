"""Separate numeric-slot recurrent policy for the provisional local arena."""

from __future__ import annotations

from typing import Literal

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator
from torch import Tensor, nn

from godfield_bot.guardian_rollout import (
    ACTION_COUNT,
    DISCARD_ACTION_COUNT,
    DISCARD_OBSERVATION_ID,
    GLOBAL_FEATURE_COUNT,
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
    hand_feature_count: Literal[7, 9] = 7
    action_count: Literal[30, 48] = 30
    observation_schema_id: Literal[
        "actor-relative-guardian-arena-v1",
        "actor-relative-guardian-utility-arena-v2",
        "actor-relative-guardian-discard-arena-v3",
    ] = "actor-relative-guardian-arena-v1"

    @model_validator(mode="after")
    def feature_contract(self) -> GuardianPolicyArchitecture:
        expected = (
            DISCARD_OBSERVATION_ID
            if self.action_count == DISCARD_ACTION_COUNT
            else "actor-relative-guardian-utility-arena-v2"
            if self.hand_feature_count == 9
            else "actor-relative-guardian-arena-v1"
        )
        if self.observation_schema_id != expected or (
            self.action_count == DISCARD_ACTION_COUNT and self.hand_feature_count != 9
        ):
            raise ValueError("guardian architecture hand width and observation identity differ")
        return self


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
            nn.Linear(architecture.embedding_size + architecture.hand_feature_count, hidden),
            nn.ReLU(),
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
        # Absent in old architectures: their state dicts remain byte-compatible.
        self.discard_head = (
            nn.Sequential(nn.Linear(hidden * 2, hidden), nn.ReLU(), nn.Linear(hidden, 1))
            if architecture.action_count == DISCARD_ACTION_COUNT
            else None
        )

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
            or hand_features.shape != (batch, HAND_SLOTS, self.architecture.hand_feature_count)
            or hand_mask.shape != (batch, HAND_SLOTS)
            or action_mask.shape != (batch, self.architecture.action_count)
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
        if self.discard_head is not None:
            discards = self.discard_head(
                torch.cat((state[:, None].expand(-1, HAND_SLOTS, -1), cards), dim=-1)
            ).squeeze(-1)
            logits = torch.cat((logits, discards), dim=1)
        values = self.value_head(state).squeeze(-1)
        if not bool(torch.isfinite(logits).all()) or not bool(torch.isfinite(values).all()):
            raise ValueError("guardian policy produced non-finite outputs")
        return logits.masked_fill(~action_mask, torch.finfo(logits.dtype).min), values, state


def migrate_guardian_utility_policy(
    source: GuardianArenaPolicy, architecture: GuardianPolicyArchitecture
) -> GuardianArenaPolicy:
    """Explicit local-only 7→9 transfer; role/7 is compensated in encoder weights.

    New HP/MP columns start at zero. Every other tensor is copied exactly;
    the source's parameters and recurrent/action architecture are untouched.
    """
    if (
        source.architecture.hand_feature_count != 7
        or architecture.hand_feature_count != 9
        or source.architecture.model_dump(exclude={"hand_feature_count", "observation_schema_id"})
        != architecture.model_dump(exclude={"hand_feature_count", "observation_schema_id"})
    ):
        raise ValueError("utility migration requires matching 7→9 guardian architectures")
    if not all(bool(torch.isfinite(value).all()) for value in source.parameters()):
        raise ValueError("utility migration refuses non-finite source parameters")
    target = GuardianArenaPolicy(architecture)
    tensors = {name: value.detach().clone() for name, value in source.state_dict().items()}
    key = "card_encoder.0.weight"
    old_weight = tensors[key]
    widened = old_weight.new_zeros((old_weight.shape[0], old_weight.shape[1] + 2))
    widened[:, : old_weight.shape[1]] = old_weight
    widened[:, architecture.embedding_size] *= 7 / 5
    tensors[key] = widened
    target.load_state_dict(tensors, strict=True)
    if not all(bool(torch.isfinite(value).all()) for value in target.parameters()):
        raise ValueError("utility migration produced non-finite parameters")
    return target


def migrate_guardian_discard_policy(
    source: GuardianArenaPolicy, architecture: GuardianPolicyArchitecture
) -> GuardianArenaPolicy:
    """Explicit 30→48 action transfer; keep all learned tensors unchanged.

    New shared slot scoring starts from the learned card scorer with only its
    final layer reset to constant -4. With discard masked off, original logits,
    values and recurrent states are identical. No optimizer state is resumed.
    """
    if (
        source.architecture.action_count != ACTION_COUNT
        or source.architecture.hand_feature_count != 9
        or architecture.action_count != DISCARD_ACTION_COUNT
        or source.architecture.model_dump(exclude={"action_count", "observation_schema_id"})
        != architecture.model_dump(exclude={"action_count", "observation_schema_id"})
    ):
        raise ValueError("discard migration requires matching nine-feature 30→48 architectures")
    if not all(bool(torch.isfinite(value).all()) for value in source.parameters()):
        raise ValueError("discard migration refuses non-finite source parameters")
    target = GuardianArenaPolicy(architecture)
    tensors = {name: value.detach().clone() for name, value in source.state_dict().items()}
    for name, value in source.card_head.state_dict().items():
        tensors[f"discard_head.{name}"] = value.detach().clone()
    tensors["discard_head.2.weight"].zero_()
    tensors["discard_head.2.bias"].fill_(-4)
    target.load_state_dict(tensors, strict=True)
    return target


def migrate_guardian_horizon_policy(
    source: GuardianArenaPolicy,
    *,
    source_max_turns: int,
    source_max_decisions: int,
    target_max_turns: int,
    target_max_decisions: int,
) -> GuardianArenaPolicy:
    """Explicit longer-bound transfer, without altering the observation schema.

    Inputs 7 and 42 are count/limit. Multiplying their encoder columns by
    target_limit/source_limit preserves the same count's contribution (up to
    floating-point rounding). This promises neither post-limit behavior nor
    unchanged terminal rewards. All other weights, including bias, are copied.
    """
    bounds = (source_max_turns, source_max_decisions, target_max_turns, target_max_decisions)
    if any(type(value) is not int or not 1 <= value <= 100_000 for value in bounds):
        raise ValueError("horizon migration requires integer bounds in [1, 100000]")
    if (
        target_max_turns < source_max_turns
        or target_max_decisions < source_max_decisions
        or (target_max_turns, target_max_decisions) == (source_max_turns, source_max_decisions)
    ):
        raise ValueError("horizon migration must extend at least one bound and never shrink")
    if not all(bool(torch.isfinite(value).all()) for value in source.parameters()):
        raise ValueError("horizon migration refuses non-finite source parameters")
    target = GuardianArenaPolicy(source.architecture)
    tensors = {name: value.detach().clone() for name, value in source.state_dict().items()}
    weight = tensors["global_encoder.0.weight"]
    weight[:, 7] *= target_max_turns / source_max_turns
    weight[:, 42] *= target_max_decisions / source_max_decisions
    target.load_state_dict(tensors, strict=True)
    if not all(bool(torch.isfinite(value).all()) for value in target.parameters()):
        raise ValueError("horizon migration produced non-finite parameters")
    return target
