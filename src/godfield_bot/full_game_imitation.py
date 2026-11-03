"""Bounded, public-only tactical demonstrations and recurrent supervised warm-up."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Annotated, Literal

import numpy as np
import numpy.typing as npt
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator
from torch import nn

from godfield_bot.full_game import DevelopmentFullGameBatch, FullGameMetadata
from godfield_bot.full_game_greedy import GREEDY_POLICY_ID, FullGameGreedyPolicy
from godfield_bot.full_game_neural import (
    FullGameActorCritic,
    FullGamePolicyInputs,
    full_game_policy_inputs,
)
from godfield_bot.full_game_observation import (
    FullGameObservation,
    FullGameObservationEncoder,
    FullGameObservationId,
)
from godfield_bot.full_game_rollout import full_game_policy_sha256

Count = Annotated[int, Field(ge=0, strict=True)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class FullGameImitationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    batches: int = Field(default=8, ge=1, le=256, strict=True)
    seed: int = Field(default=1_000_000, ge=0, lt=2**63 - 1024, strict=True)
    epochs: int = Field(default=8, ge=1, le=64, strict=True)
    sequence_length: int = Field(default=32, ge=1, le=128, strict=True)
    sequences_per_group: int = Field(default=16, ge=1, le=64, strict=True)
    learning_rate: float = Field(default=0.001, gt=0, le=0.01, allow_inf_nan=False)
    max_gradient_norm: float = Field(default=1, gt=0, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounded_graph(self) -> FullGameImitationConfig:
        if self.sequence_length * self.sequences_per_group > 2048:
            raise ValueError("full-game imitation groups may contain at most 2048 decisions")
        return self

    def seeds(self) -> range:
        return range(self.seed, self.seed + self.batches)


class FullGameDemonstrationSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    environment_seed: int
    outcomes: tuple[Count, ...]  # winners, draws, turn and decision limits
    accepted_decisions: Count
    terminal_decisions: Count
    actor_decisions: Count
    phase_counts: tuple[Count, ...]
    demonstration_sha256: Digest

    @model_validator(mode="after")
    def accounting(self) -> FullGameDemonstrationSummary:
        if (
            len(self.outcomes) != 4
            or not 0 <= self.actor_decisions <= self.terminal_decisions <= self.accepted_decisions
            or len(self.phase_counts) != 14
            or sum(self.phase_counts) != self.terminal_decisions
        ):
            raise ValueError("full-game demonstration accounting differs")
        return self


class FullGameImitationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cross_entropy: float = Field(ge=0, allow_inf_nan=False)
    accuracy: float = Field(ge=0, le=1, allow_inf_nan=False)


class FullGameImitationUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    demonstration: FullGameDemonstrationSummary
    before: FullGameImitationMetrics | None
    after: FullGameImitationMetrics | None
    before_policy_sha256: Digest
    after_policy_sha256: Digest


class FullGameImitationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    teacher: Literal["full-game-public-greedy-v1"] = GREEDY_POLICY_ID
    method: Literal["complete-public-teacher-episodes-masked-cross-entropy-fresh-ppo-adam"] = (
        "complete-public-teacher-episodes-masked-cross-entropy-fresh-ppo-adam"
    )
    recurrent_boundary: Literal["per-seat-from-zero-detach-between-chronological-windows"] = (
        "per-seat-from-zero-detach-between-chronological-windows"
    )
    config: FullGameImitationConfig
    environment: FullGameMetadata
    observation_id: FullGameObservationId
    updates: tuple[FullGameImitationUpdate, ...]
    before_policy_sha256: Digest
    after_policy_sha256: Digest
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def update_chain(self) -> FullGameImitationReport:
        if len(self.updates) != self.config.batches or self.environment.seed != self.config.seed:
            raise ValueError("full-game imitation batch schedule differs")
        previous = self.before_policy_sha256
        for seed, update in zip(self.config.seeds(), self.updates, strict=True):
            summary = update.demonstration
            if (
                summary.environment_seed != seed
                or sum(summary.outcomes) != self.environment.batch_size
                or summary.accepted_decisions
                > self.environment.batch_size * self.environment.max_decisions
                or update.before_policy_sha256 != previous
                or (update.before is not None) != (summary.actor_decisions > 0)
                or (update.after is not None) != (update.before is not None)
                or (update.before is None and update.after_policy_sha256 != previous)
            ):
                raise ValueError("full-game imitation update contract differs")
            previous = update.after_policy_sha256
        if previous != self.after_policy_sha256:
            raise ValueError("full-game imitation final policy differs")
        return self


@dataclass(frozen=True)
class FullGameDemonstrations:
    observation: FullGameObservation
    actions: npt.NDArray[np.int64]
    sequences: tuple[npt.NDArray[np.int64], ...]
    summary: FullGameDemonstrationSummary


def collect_full_game_demonstrations(
    configured: DevelopmentFullGameBatch, observation_id: FullGameObservationId
) -> FullGameDemonstrations:
    """Record only accepted public teacher decisions from true terminal episodes."""
    b, m = configured.batch, configured.metadata
    if m.batch_size * m.max_decisions > 32768:
        raise ValueError("full-game demonstration batch exceeds storage bound")
    if np.any(b.episode_snapshot()[:, 3] != 0):
        raise ValueError("full-game demonstration collection requires fresh environments")
    encoder, teacher = (
        FullGameObservationEncoder(configured, observation_id),
        FullGameGreedyPolicy(m),
    )
    observations, actions = [], []
    b.start_environments(np.arange(m.batch_size, dtype=np.int64))
    for _ in range(m.max_decisions):
        active = np.flatnonzero(b.choice_masks().any(axis=1)).astype(np.int64)
        if not len(active):
            break
        o = encoder.encode().take(active)
        a = teacher.actions(o)
        before = b.episode_snapshot()[active, 7].copy()
        b.step(np.column_stack((o.leases, a)))
        if not np.array_equal(b.episode_snapshot()[active, 7], before + 1):
            raise RuntimeError("full-game teacher command was not accepted exactly once")
        observations.append(o)
        actions.append(a)
    state = b.episode_snapshot()
    if not np.isin(state[:, 5], (1, 2, 3, 4)).all():
        raise RuntimeError("full-game teacher collection ended with active episodes")
    # Keep incomplete episode decisions only long enough to account for their rejection.
    o = FullGameObservation(
        **{
            f.name: np.concatenate([getattr(row, f.name) for row in observations])
            if observations
            else getattr(encoder.encode(), f.name)[:0].copy()
            for f in fields(FullGameObservation)
        }
    )
    a = np.concatenate(actions) if actions else np.empty(0, dtype=np.int64)
    terminal = np.isin(state[o.leases[:, 0], 5], (1, 2))
    o = o.take(np.flatnonzero(terminal).astype(np.int64))
    a = a[terminal]
    digest = hashlib.sha256(state.astype("<i8").tobytes())
    for f in fields(o):
        array = getattr(o, f.name)
        digest.update(f.name.encode())
        digest.update(array.astype(array.dtype.newbyteorder("<"), copy=False).tobytes())
    digest.update(a.astype("<i8").tobytes())
    a.setflags(write=False)
    sequences = tuple(
        np.flatnonzero((o.leases[:, 0] == env) & (o.leases[:, 3] == seat)).astype(np.int64)
        for env in range(m.batch_size)
        for seat in range(m.player_count)
        if np.any((o.leases[:, 0] == env) & (o.leases[:, 3] == seat))
    )
    return FullGameDemonstrations(
        o,
        a,
        sequences,
        FullGameDemonstrationSummary(
            environment_seed=m.seed,
            outcomes=tuple(int((state[:, 5] == outcome).sum()) for outcome in (1, 2, 3, 4)),
            accepted_decisions=int(state[:, 7].sum()),
            terminal_decisions=len(a),
            actor_decisions=int(o.policy_gradient_mask.sum()),
            phase_counts=tuple(int(v) for v in np.bincount(o.leases[:, 4], minlength=14)),
            demonstration_sha256=digest.hexdigest(),
        ),
    )


def _supervised_epoch(
    policy: FullGameActorCritic,
    data: FullGameDemonstrations,
    inputs: FullGamePolicyInputs,
    config: FullGameImitationConfig,
    *,
    backward: bool,
) -> FullGameImitationMetrics:
    loss_total, correct = 0.0, 0
    actions = torch.tensor(data.actions)
    mask = torch.tensor(data.observation.policy_gradient_mask)
    count = data.summary.actor_decisions
    for start in range(0, len(data.sequences), config.sequences_per_group):
        sequences = data.sequences[start : start + config.sequences_per_group]
        memory = torch.zeros(len(sequences), policy.architecture.hidden_size)
        for chunk in range(0, max(len(seq) for seq in sequences), config.sequence_length):
            losses = []
            for time in range(chunk, min(chunk + config.sequence_length, max(map(len, sequences)))):
                positions = torch.tensor([i for i, seq in enumerate(sequences) if time < len(seq)])
                rows = torch.tensor([sequences[i][time] for i in positions.tolist()])
                subset = FullGamePolicyInputs(
                    **{f.name: getattr(inputs, f.name)[rows] for f in fields(inputs)}
                )
                logits, _, next_memory = policy(subset, memory[positions])
                memory = memory.index_copy(0, positions, next_memory)
                active = mask[rows]
                if bool(active.any()):
                    loss = (
                        nn.functional.cross_entropy(
                            logits[active], actions[rows][active], reduction="sum"
                        )
                        / count
                    )
                    losses.append(loss)
                    loss_total += float(loss.detach())
                    correct += int((logits[active].argmax(1) == actions[rows][active]).sum())
            if backward and losses:
                torch.stack(losses).sum().backward()  # type: ignore[no-untyped-call]
            memory = memory.detach()
    return FullGameImitationMetrics(cross_entropy=loss_total, accuracy=correct / count)


def fit_full_game_demonstrations(
    policy: FullGameActorCritic,
    optimizer: torch.optim.Adam,
    data: FullGameDemonstrations,
    config: FullGameImitationConfig,
) -> tuple[FullGameImitationMetrics, FullGameImitationMetrics]:
    if not data.summary.actor_decisions:
        raise ValueError("full-game imitation requires voluntary terminal teacher decisions")
    parameters = list(policy.parameters())
    owned = [p for group in optimizer.param_groups for p in group["params"]]
    if len(owned) != len(parameters) or {id(p) for p in owned} != {id(p) for p in parameters}:
        raise ValueError("full-game imitation optimizer must own the policy")
    o = data.observation
    if (
        data.actions.dtype != np.int64
        or data.actions.shape != (len(o.leases),)
        or data.summary.terminal_decisions != len(data.actions)
        or data.summary.actor_decisions != int(o.policy_gradient_mask.sum())
        or np.any(data.actions < 0)
        or np.any(data.actions >= o.choice_mask.shape[1])
        or not o.choice_mask[np.arange(len(data.actions)), data.actions].all()
        or not data.sequences
        or not np.array_equal(np.sort(np.concatenate(data.sequences)), np.arange(len(data.actions)))
        or any(
            len(rows) == 0
            or not np.all(o.leases[rows, :2] == o.leases[rows[0], :2])
            or not np.all(o.leases[rows, 3] == o.leases[rows[0], 3])
            or np.any(np.diff(o.leases[rows, 2]) <= 0)
            for rows in data.sequences
        )
    ):
        raise ValueError("full-game imitation decisions or seat sequences differ")
    inputs = full_game_policy_inputs(o)
    previous_policy, previous_optimizer = (
        copy.deepcopy(policy.state_dict()),
        copy.deepcopy(optimizer.state_dict()),
    )
    with torch.no_grad():
        before = _supervised_epoch(policy, data, inputs, config, backward=False)
    try:
        for _ in range(config.epochs):
            optimizer.zero_grad(set_to_none=True)
            _supervised_epoch(policy, data, inputs, config, backward=True)
            nn.utils.clip_grad_norm_(parameters, config.max_gradient_norm, error_if_nonfinite=True)
            optimizer.step()
            full_game_policy_sha256(policy)
        with torch.no_grad():
            after = _supervised_epoch(policy, data, inputs, config, backward=False)
    except Exception:
        policy.load_state_dict(previous_policy)
        optimizer.load_state_dict(previous_optimizer)
        optimizer.zero_grad(set_to_none=True)
        raise
    return before, after


def warm_start_full_game(
    policy: FullGameActorCritic,
    config: FullGameImitationConfig,
    create_batch: Callable[[int], DevelopmentFullGameBatch],
    on_update: Callable[[int, FullGameImitationUpdate], None] | None = None,
) -> FullGameImitationReport:
    optimizer = torch.optim.Adam(policy.parameters(), lr=config.learning_rate)
    original_hash = full_game_policy_sha256(policy)
    updates = []
    initial_environment = None
    for index, seed in enumerate(config.seeds()):
        configured = create_batch(seed)
        if initial_environment is None:
            initial_environment = configured.metadata
        elif configured.metadata.model_dump(exclude={"seed"}) != initial_environment.model_dump(
            exclude={"seed"}
        ):
            raise ValueError("full-game imitation environment changed between batches")
        data = collect_full_game_demonstrations(configured, policy.architecture.observation_id)
        before_hash = full_game_policy_sha256(policy)
        before, after = (
            fit_full_game_demonstrations(policy, optimizer, data, config)
            if data.summary.actor_decisions
            else (None, None)
        )
        updates.append(
            FullGameImitationUpdate(
                demonstration=data.summary,
                before=before,
                after=after,
                before_policy_sha256=before_hash,
                after_policy_sha256=full_game_policy_sha256(policy),
            )
        )
        del data
        if on_update is not None:
            on_update(index + 1, updates[-1])
    assert initial_environment is not None
    if not any(update.before is not None for update in updates):
        raise ValueError("full-game imitation found no voluntary terminal demonstrations")
    return FullGameImitationReport(
        config=config,
        environment=initial_environment,
        observation_id=policy.architecture.observation_id,
        updates=tuple(updates),
        before_policy_sha256=original_hash,
        after_policy_sha256=full_game_policy_sha256(policy),
    )
