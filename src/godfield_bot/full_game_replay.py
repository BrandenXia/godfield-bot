"""Verify accepted behavior and recurrent seat continuity before optimization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from godfield_bot.full_game_neural import FullGameActorCritic, full_game_policy_inputs
from godfield_bot.full_game_rollout import (
    FullGameEpisodeCollection,
    IntArray,
    full_game_policy_sha256,
    validate_full_game_collection,
)


@dataclass(frozen=True)
class FullGameSeatSequence:
    environment: int
    epoch: int
    actor: int
    rows: IntArray  # indices into that environment's complete sample table


def full_game_seat_sequences(
    collection: FullGameEpisodeCollection,
) -> tuple[FullGameSeatSequence, ...]:
    """Only actual accepted history, in each seat's native decision order."""
    validate_full_game_collection(collection)
    sequences = []
    for e in collection.episodes:
        if e.samples is None:
            continue
        actors = e.samples.commands[:, 3]
        for actor in np.unique(actors):
            rows = np.flatnonzero(actors == actor).astype(np.int64)
            rows.setflags(write=False)
            sequences.append(
                FullGameSeatSequence(e.outcome.environment, e.outcome.epoch, int(actor), rows)
            )
    return tuple(sequences)


@dataclass(frozen=True)
class FullGameBehaviorReplay:
    decisions: int
    seat_sequences: int
    maximum_log_probability_error: float
    maximum_value_error: float
    maximum_memory_handoff_error: float


def verify_full_game_behavior(
    collection: FullGameEpisodeCollection, policy: FullGameActorCritic, *, chunk_size: int = 512
) -> FullGameBehaviorReplay:
    """Replay each recorded GRU edge under the pinned behavior weights.

    Compare its probability/value and the next decision's same-seat memory.
    First memories are independently checked as zero by collection validation.
    Forward chunking bounds verification storage; it does not truncate or
    recompute a different recurrent gradient schedule.
    """
    if type(chunk_size) is not int or not 1 <= chunk_size <= 2048:
        raise ValueError("full-game behavior replay chunk size is outside its bound")
    if full_game_policy_sha256(policy) != collection.metadata.behavior_policy_sha256:
        raise ValueError("full-game behavior replay weights differ from collection")
    sequences = full_game_seat_sequences(collection)
    log_error, value_error, memory_error = 0.0, 0.0, 0.0
    tolerance = 2e-5  # CPU float32 batches may use different matrix kernel sizes.
    by_env: dict[int, list[FullGameSeatSequence]] = {}
    for sequence in sequences:
        by_env.setdefault(sequence.environment, []).append(sequence)
    with torch.no_grad():
        for episode in collection.episodes:
            s = episode.samples
            if s is None or len(s.commands) == 0:
                continue
            next_memory = np.empty_like(s.previous_memory)
            for start in range(0, len(s.commands), chunk_size):
                stop = min(start + chunk_size, len(s.commands))
                rows = np.arange(start, stop, dtype=np.int64)
                inputs = full_game_policy_inputs(s.observation.take(rows))
                previous = torch.from_numpy(s.previous_memory[start:stop].copy())
                logits, values, memory = policy(inputs, previous)
                actions = torch.from_numpy(s.commands[start:stop, 5].copy())
                logs = torch.log_softmax(logits, dim=1).gather(1, actions[:, None])[:, 0]
                log_error = max(
                    log_error,
                    float(np.abs(logs.numpy() - s.behavior_log_probabilities[start:stop]).max()),
                )
                value_error = max(
                    value_error, float(np.abs(values.numpy() - s.behavior_values[start:stop]).max())
                )
                next_memory[start:stop] = memory.numpy()
            for sequence in by_env[episode.outcome.environment]:
                rows = sequence.rows
                if len(rows) > 1:
                    memory_error = max(
                        memory_error,
                        float(np.abs(next_memory[rows[:-1]] - s.previous_memory[rows[1:]]).max()),
                    )
    if max(log_error, value_error) > tolerance:
        raise ValueError("full-game behavior replay probability or value differs")
    if memory_error > tolerance:
        raise ValueError("full-game behavior replay same-seat memory handoff differs")
    return FullGameBehaviorReplay(
        collection.eligible_decisions, len(sequences), log_error, value_error, memory_error
    )
