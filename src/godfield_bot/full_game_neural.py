"""Separate full-game recurrent policy and accepted-command seat memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator
from torch import Tensor, nn

from godfield_bot.full_game import DevelopmentFullGameBatch
from godfield_bot.full_game_observation import (
    ATTACK_HISTORY_OBSERVATION_ID,
    CHOICES,
    CONTEXT_MODELS,
    GLOBAL_FIELDS,
    HAND_FEATURES,
    HAND_SLOTS,
    HISTORY_GLOBAL_FIELDS,
    MODEL_VOCABULARY,
    OBSERVATION_ID,
    PLAYER_FEATURES,
    FullGameObservation,
    FullGameObservationEncoder,
    FullGameObservationId,
)
from godfield_bot.full_game_rewards import (
    FullGameRewardAdapter,
    FullGameRewardBatch,
    FullGameRewardTransition,
)

IntArray = npt.NDArray[np.int64]


class FullGamePolicyArchitecture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=2, strict=True)
    observation_id: FullGameObservationId = OBSERVATION_ID
    hand_slots: Literal[18] = 18
    choices: Literal[28] = 28
    vocabulary_size: Literal[297] = 297
    maximum_players: Literal[9] = 9
    embedding_size: int = Field(default=32, ge=8, le=128, strict=True)
    hidden_size: int = Field(default=128, ge=16, le=256, strict=True)
    recurrence: Literal["gru-independent-environment-epoch-seat-accepted-only"] = (
        "gru-independent-environment-epoch-seat-accepted-only"
    )
    action_head: Literal["28-native-numeric-choices-conditioned-on-public-phase"] = (
        "28-native-numeric-choices-conditioned-on-public-phase"
    )
    old_checkpoint_compatible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def observation_contract(self) -> FullGamePolicyArchitecture:
        if (self.schema_version == 2) != (self.observation_id == ATTACK_HISTORY_OBSERVATION_ID):
            raise ValueError("full-game policy observation version differs")
        return self


@dataclass(frozen=True)
class FullGamePolicyInputs:
    global_features: Tensor
    players: Tensor
    cards: Tensor
    hand_features: Tensor
    context_models: Tensor
    choices: Tensor


def full_game_policy_inputs(observation: FullGameObservation) -> FullGamePolicyInputs:
    # Leases and instance IDs are never neural inputs. Copy readonly numpy data
    # so neither torch nor a caller can write into the observation snapshot.
    return FullGamePolicyInputs(
        *(
            torch.from_numpy(a.copy())
            for a in (
                observation.global_features,
                observation.players,
                observation.card_model_ids,
                observation.hand_features,
                observation.context_model_ids,
                observation.choice_mask,
            )
        )
    )


class FullGameActorCritic(nn.Module):
    def __init__(self, architecture: FullGamePolicyArchitecture | None = None) -> None:
        super().__init__()
        self.architecture = architecture or FullGamePolicyArchitecture()
        e, h = self.architecture.embedding_size, self.architecture.hidden_size
        self.embedding = nn.Embedding(MODEL_VOCABULARY, e, padding_idx=0)
        self.card_encoder = nn.Sequential(nn.Linear(e + len(HAND_FEATURES), e), nn.SiLU())
        self.player_encoder = nn.Sequential(nn.Linear(len(PLAYER_FEATURES), e), nn.SiLU())
        self.context_encoder = nn.Sequential(
            nn.Linear(len(GLOBAL_FIELDS) + e * len(CONTEXT_MODELS), h), nn.SiLU()
        )
        # Flatten the fixed public roster/hand so numeric phase6 choices do not
        # inherit a card-only or target-only action meaning. Padding is zero.
        self.observation_encoder = nn.Sequential(nn.Linear(e * (HAND_SLOTS + 9) + h, h), nn.SiLU())
        self.memory = nn.GRUCell(h, h)
        self.action_head = nn.Linear(h, CHOICES)
        self.value_head = nn.Linear(h, 1)
        self.history_encoder: nn.Linear | None = None
        if self.architecture.observation_id == ATTACK_HISTORY_OBSERVATION_ID:
            self.history_encoder = nn.Linear(
                len(HISTORY_GLOBAL_FIELDS) - len(GLOBAL_FIELDS), h, bias=False
            )
            nn.init.zeros_(self.history_encoder.weight)

    def forward(
        self, inputs: FullGamePolicyInputs, recurrent_state: Tensor | None = None
    ) -> tuple[Tensor, Tensor, Tensor]:
        x = inputs
        n = x.global_features.shape[0]
        tensors = (
            x.global_features,
            x.players,
            x.cards,
            x.hand_features,
            x.context_models,
            x.choices,
        )
        if (
            x.global_features.shape
            != (
                n,
                len(HISTORY_GLOBAL_FIELDS if self.history_encoder is not None else GLOBAL_FIELDS),
            )
            or x.players.shape != (n, 9, len(PLAYER_FEATURES))
            or x.cards.shape != (n, 18)
            or x.hand_features.shape != (n, 18, len(HAND_FEATURES))
            or x.context_models.shape != (n, len(CONTEXT_MODELS))
            or x.choices.shape != (n, CHOICES)
            or any(t.device != self.embedding.weight.device for t in tensors)
            or any(
                t.dtype != torch.float32 for t in (x.global_features, x.players, x.hand_features)
            )
            or x.cards.dtype != torch.int64
            or x.context_models.dtype != torch.int64
            or x.choices.dtype != torch.bool
        ):
            raise ValueError("full-game policy input shape, dtype or device differs")
        if not bool(x.choices.any(dim=1).all()) or n == 0:
            raise ValueError("full-game policy requires active legal choices in every row")
        if any(
            not bool(torch.isfinite(t).all())
            for t in (x.global_features, x.players, x.hand_features)
        ):
            raise ValueError("full-game policy input is not finite")
        if any(
            bool(((t < 0) | (t >= MODEL_VOCABULARY)).any()) for t in (x.cards, x.context_models)
        ):
            raise ValueError("full-game policy model vocabulary differs")
        if recurrent_state is None:
            recurrent_state = x.global_features.new_zeros((n, self.architecture.hidden_size))
        if (
            recurrent_state.shape != (n, self.architecture.hidden_size)
            or recurrent_state.dtype != torch.float32
            or recurrent_state.device != x.cards.device
            or not bool(torch.isfinite(recurrent_state).all())
        ):
            raise ValueError("full-game policy recurrent state differs")
        cards = self.card_encoder(torch.cat((self.embedding(x.cards), x.hand_features), dim=-1))
        # MLP biases must not turn an absent slot/player into learned data.
        cards = cards * (x.cards != 0).unsqueeze(-1)
        players = self.player_encoder(x.players) * (x.players[:, :, :1] != 0)
        context = self.context_encoder(
            torch.cat(
                (
                    x.global_features[:, : len(GLOBAL_FIELDS)],
                    self.embedding(x.context_models).flatten(1),
                ),
                dim=1,
            )
        )
        if self.history_encoder is not None:
            context = context + self.history_encoder(x.global_features[:, len(GLOBAL_FIELDS) :])
        encoded = self.observation_encoder(
            torch.cat((cards.flatten(1), players.flatten(1), context), dim=1)
        )
        state = self.memory(encoded, recurrent_state)
        logits, values = self.action_head(state), self.value_head(state).squeeze(-1)
        if any(not bool(torch.isfinite(t).all()) for t in (state, logits, values)):
            raise ValueError("full-game policy produced non-finite outputs")
        return logits.masked_fill(~x.choices, torch.finfo(logits.dtype).min), values, state


def transfer_full_game_attack_history(source: FullGameActorCritic) -> FullGameActorCritic:
    """Keep the existing policy path and start the new history projection at zero."""
    if source.architecture.observation_id != OBSERVATION_ID:
        raise ValueError("attack-history transfer requires a version 1 policy")
    architecture = FullGamePolicyArchitecture.model_validate(
        source.architecture.model_dump()
        | {"schema_version": 2, "observation_id": ATTACK_HISTORY_OBSERVATION_ID}
    )
    with torch.random.fork_rng(devices=[]):
        target = FullGameActorCritic(architecture).float().cpu()
    target.load_state_dict(target.state_dict() | source.state_dict(), strict=True)
    return target.eval()


@dataclass(frozen=True)
class FullGamePolicyStep:
    observation: FullGameObservation
    previous_memory: Tensor
    actions: IntArray
    log_probabilities: Tensor
    values: Tensor
    transition: FullGameRewardTransition


class FullGamePolicyController:
    """CPU inference and transactional memory, not an optimizer or replay dataset.

    Caller performs trusted setup/start on the source batch. Steps and resets
    must go through this object; the reward adapter detects raw cursor drift.
    No state, sample receipt or sampling RNG change survives a rejected command.
    """

    def __init__(
        self,
        configured: DevelopmentFullGameBatch,
        policy: FullGameActorCritic,
        *,
        seed: int = 67,
        opponent: FullGameActorCritic | None = None,
        opponent_seats: tuple[int, ...] = (),
    ) -> None:
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("full-game policy sampling seed is invalid")
        if any(p.device.type != "cpu" or p.dtype != torch.float32 for p in policy.parameters()):
            raise ValueError("full-game controller requires a float32 CPU policy")
        if (
            (opponent is None) != (not opponent_seats)
            or len(set(opponent_seats)) != len(opponent_seats)
            or any(
                type(seat) is not int or not 0 <= seat < configured.metadata.player_count
                for seat in opponent_seats
            )
            or (
                opponent is not None
                and (
                    opponent.architecture != policy.architecture
                    or any(
                        p.device.type != "cpu" or p.dtype != torch.float32
                        for p in opponent.parameters()
                    )
                )
            )
        ):
            raise ValueError("full-game controller opponent architecture or seats differ")
        self.encoder = FullGameObservationEncoder(configured, policy.architecture.observation_id)
        self.rewards = FullGameRewardAdapter(configured)
        self.policy = policy
        self._opponent = opponent
        self._opponent_seats = opponent_seats
        self._states = torch.zeros(
            (configured.metadata.batch_size, 9, policy.architecture.hidden_size),
            dtype=torch.float32,
            device="cpu",
        )
        self._epochs = self.encoder.encode().leases[:, 1].copy()
        self._rng = torch.Generator(device="cpu").manual_seed(seed)

    def memory_snapshot(self) -> Tensor:
        return self._states.clone()

    def sampling_state(self) -> Tensor:
        return self._rng.get_state().clone()

    def _infer(
        self, observation: FullGameObservation, previous: Tensor
    ) -> tuple[Tensor, Tensor, Tensor]:
        if self._opponent is None:
            logits, values, memory = self.policy(full_game_policy_inputs(observation), previous)
            return logits, values, memory
        opponent_rows = np.isin(observation.leases[:, 3], self._opponent_seats)
        logits = previous.new_empty((len(previous), CHOICES))
        values = previous.new_empty(len(previous))
        memory = torch.empty_like(previous)
        for mask, policy in ((~opponent_rows, self.policy), (opponent_rows, self._opponent)):
            rows = np.flatnonzero(mask).astype(np.int64)
            if len(rows):
                logits[rows], values[rows], memory[rows] = policy(
                    full_game_policy_inputs(observation.take(rows)), previous[rows]
                )
        return logits, values, memory

    def step(self, environments: IntArray, *, deterministic: bool = False) -> FullGamePolicyStep:
        if type(deterministic) is not bool:
            raise ValueError("full-game deterministic control must be boolean")
        observation = self.encoder.encode()
        selected = observation.take(environments)
        if not len(selected.leases) or not selected.choice_mask.any(axis=1).all():
            raise ValueError("full-game controller requires nonempty active environments")
        if not np.array_equal(observation.leases[:, 1], self._epochs):
            raise RuntimeError("untracked full-game reset; use the policy controller")
        envs = selected.leases[:, 0].copy()
        actors = selected.leases[:, 3].copy()
        previous = self._states[envs, actors].clone()
        with torch.no_grad():
            logits, values, proposed = self._infer(selected, previous)
            probabilities = torch.softmax(logits, dim=1)
            rng_before = self._rng.get_state()
            actions = (
                logits.argmax(dim=1)
                if deterministic
                else torch.multinomial(probabilities, 1, generator=self._rng).squeeze(1)
            )
            log_probabilities = (
                torch.log_softmax(logits, dim=1).gather(1, actions[:, None]).squeeze(1)
            )
            command = np.column_stack((selected.leases, actions.numpy())).astype(np.int64)
            try:
                transition = self.rewards.step(command)
            except Exception:
                self._rng.set_state(rng_before)
                raise
            self._states[envs, actors] = proposed
        accepted = actions.numpy().copy()
        accepted.setflags(write=False)
        return FullGamePolicyStep(
            selected, previous, accepted, log_probabilities, values, transition
        )

    def poll_rewards(self) -> FullGameRewardBatch:
        return self.rewards.poll()

    def reset_environments(self, environments: IntArray) -> None:
        self.rewards.reset_environments(environments)
        self._states[torch.from_numpy(environments.copy())] = 0
        self._epochs[environments] = self.rewards.configured.batch.episode_snapshot()[
            environments, 0
        ]
