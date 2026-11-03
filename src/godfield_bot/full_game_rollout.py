"""Accepted complete episodes and undiscounted per-seat terminal targets."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

import numpy as np
import numpy.typing as npt
import torch
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from godfield_bot.full_game import DevelopmentFullGameBatch, FullGameMetadata
from godfield_bot.full_game_neural import (
    FullGameActorCritic,
    FullGamePolicyArchitecture,
    FullGamePolicyController,
    FullGamePolicyStep,
)
from godfield_bot.full_game_observation import (
    GLOBAL_FIELDS,
    HAND_FEATURES,
    PLAYER_FEATURES,
    FullGameEncoderMetadata,
    FullGameObservation,
)
from godfield_bot.full_game_rewards import FullGameRewardBatch, FullGameRewardMetadata

if TYPE_CHECKING:
    from godfield_sim import FullGameBatch

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]
OutcomeStatus = Literal["winner", "draw", "turn-limit", "decision-limit", "collection-aborted"]
SignedOutcome = Annotated[int, Field(ge=-1, le=1, strict=True)]


def _readonly(a: npt.NDArray[Any]) -> npt.NDArray[Any]:
    a.setflags(write=False)
    return a


def full_game_policy_sha256(policy: FullGameActorCritic) -> str:
    """Canonical tensor content, excluding runtime/zip timestamp metadata."""
    digest = hashlib.sha256(policy.architecture.model_dump_json().encode())
    for name, value in sorted(policy.state_dict().items()):
        if value.device.type != "cpu" or value.dtype != torch.float32:
            raise ValueError("full-game collection requires CPU float32 weights")
        if not bool(torch.isfinite(value).all()):
            raise ValueError("full-game collection refuses non-finite weights")
        digest.update(json.dumps((name, list(value.shape), str(value.dtype))).encode())
        digest.update(value.detach().contiguous().numpy().astype("<f4", copy=False).tobytes())
    return digest.hexdigest()


class FullGameCollectionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    environment: FullGameMetadata
    encoder: FullGameEncoderMetadata
    rewards: FullGameRewardMetadata
    architecture: FullGamePolicyArchitecture
    behavior_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sampling_seed: int = Field(ge=0, lt=2**63, strict=True)
    max_stored_decisions: int = Field(ge=1, le=32768, strict=True)
    behavior: Literal["private-frozen-policy-copy-through-complete-collection-batch"] = (
        "private-frozen-policy-copy-through-complete-collection-batch"
    )
    return_rule: Literal["undiscounted-native-terminal-outcome-of-each-acting-seat"] = (
        "undiscounted-native-terminal-outcome-of-each-acting-seat"
    )
    incomplete_episodes: Literal["exclude-all-prior-decisions-no-bootstrap-no-synthetic-loss"] = (
        "exclude-all-prior-decisions-no-bootstrap-no-synthetic-loss"
    )
    rejected_batch: Literal[
        "stop-collection-exclude-incomplete-preserve-exact-attempt-no-substitution"
    ] = "stop-collection-exclude-incomplete-preserve-exact-attempt-no-substitution"
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def compatible(self) -> FullGameCollectionMetadata:
        environment_hash = hashlib.sha256(
            json.dumps(
                self.environment.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if (
            self.encoder.environment_metadata_sha256 != environment_hash
            or self.rewards.environment_metadata_sha256 != environment_hash
            or self.rewards.ruleset_id != self.environment.ruleset_id
            or self.architecture.observation_id != self.encoder.observation_id
            or self.environment.batch_size * self.environment.max_decisions
            > self.max_stored_decisions
        ):
            raise ValueError("full-game collection metadata contracts or storage bounds differ")
        return self


class FullGameCollectedOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    environment: int = Field(ge=0, le=4095, strict=True)
    epoch: int = Field(ge=1, strict=True)
    status: OutcomeStatus
    native_phase: int = Field(ge=0, le=13, strict=True)
    native_outcome: int = Field(ge=0, le=4, strict=True)
    native_actor: int = Field(ge=0, le=8, strict=True)
    accepted_commands: int = Field(ge=0, le=1_000_000_000, strict=True)
    completed_turns: int = Field(ge=0, le=1_000_000_000, strict=True)
    winner: int = Field(ge=-1, le=8, strict=True)
    winning_players: tuple[Annotated[int, Field(ge=0, le=8, strict=True)], ...]
    terminal_values: tuple[SignedOutcome, ...]
    terminal_valid: tuple[StrictBool, ...]

    @model_validator(mode="after")
    def actual_ending(self) -> FullGameCollectedOutcome:
        if len(self.terminal_values) != 9 or len(self.terminal_valid) != 9:
            raise ValueError("collected terminal payoff must retain nine absolute seats")
        expected = {
            "winner": (12, 1),
            "draw": (12, 2),
            "turn-limit": (13, 3),
            "decision-limit": (13, 4),
        }
        if (
            self.status in expected
            and (self.native_phase, self.native_outcome) != expected[self.status]
        ):
            raise ValueError("collected ending differs from native outcome")
        if (
            (
                self.status == "collection-aborted"
                and (self.native_phase >= 12 or self.native_outcome != 0)
            )
            or (self.winner >= 0) != (self.status == "winner")
            or any(v not in (-1, 0, 1) for v in self.terminal_values)
            or any(
                v != 0
                for v, valid in zip(self.terminal_values, self.terminal_valid, strict=True)
                if not valid
            )
            or (self.status in ("winner", "draw")) != any(self.terminal_valid)
            or (self.status != "winner" and (self.winning_players or any(self.terminal_values)))
        ):
            raise ValueError("collected terminal validity cannot fabricate a loss or draw")
        return self


@dataclass(frozen=True)
class FullGameEpisodeSamples:
    observation: FullGameObservation
    commands: IntArray
    previous_memory: FloatArray
    behavior_log_probabilities: FloatArray
    behavior_values: FloatArray
    terminal_targets: FloatArray


@dataclass(frozen=True)
class FullGameCollectedEpisode:
    outcome: FullGameCollectedOutcome
    # None means excluded, not a legitimate draw/empty terminal trajectory.
    samples: FullGameEpisodeSamples | None


@dataclass(frozen=True)
class FullGameEpisodeCollection:
    metadata: FullGameCollectionMetadata
    episodes: tuple[FullGameCollectedEpisode, ...]
    rejected_commands: IntArray  # unaccepted exact public commands, diagnostic only
    collection_error: str | None

    @property
    def eligible_decisions(self) -> int:
        return sum(len(e.samples.commands) for e in self.episodes if e.samples is not None)

    @property
    def eligible_policy_decisions(self) -> int:
        return sum(
            int(e.samples.observation.policy_gradient_mask.sum())
            for e in self.episodes
            if e.samples is not None
        )

    @property
    def accepted_decisions(self) -> int:
        return sum(e.outcome.accepted_commands for e in self.episodes)


class _CaptureCommands:
    """Diagnostic capture; no private data is sent to policy observations."""

    def __init__(self, batch: Any) -> None:
        self.batch = batch
        self.commands = np.empty((0, 6), dtype=np.int64)
        self.error: Exception | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.batch, name)

    def step(self, commands: IntArray) -> None:
        self.commands = commands.copy()
        self.error = None
        try:
            self.batch.step(commands)
        except (ValueError, RuntimeError) as error:
            self.error = error
            raise


def _initial_fingerprint(batch: Any) -> str:
    digest = hashlib.sha256()
    for name in (
        "episode_snapshot",
        "diagnostic_players",
        "diagnostic_inventory",
        "team_ids",
        "guardian_snapshot",
        "confusion_snapshot",
    ):
        digest.update(name.encode())
        digest.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())
    return digest.hexdigest()


def collect_full_game_episodes(
    configured: DevelopmentFullGameBatch,
    policy: FullGameActorCritic,
    *,
    sampling_seed: int = 67,
    max_stored_decisions: int = 32768,
) -> FullGameEpisodeCollection:
    """One bounded epoch per environment; never reset away an ending or failure.

    Trusted unstarted/zero-command setup is allowed and fingerprinted. This is
    collection plumbing, not a training authorization or complete resume log.
    Native errors stop the batch and exclude every still-incomplete episode;
    already completed episodes retain their verified terminal targets.
    """
    from dataclasses import replace

    m, b = configured.metadata, configured.batch
    FullGameMetadata.model_validate(m.model_dump())
    if (
        type(max_stored_decisions) is not int
        or not 1 <= max_stored_decisions <= 32768
        or m.batch_size * m.max_decisions > max_stored_decisions
    ):
        raise ValueError("full-game complete-episode storage exceeds its explicit bound")
    if type(sampling_seed) is not int or not 0 <= sampling_seed < 2**63:
        raise ValueError("full-game collection sampling seed is invalid")
    state = b.episode_snapshot()
    if (
        not np.isin(state[:, 3], (0, 1, 12)).all()
        or np.any(state[:, 7] != 0)
        or np.any(state[:, 1] != 1)
    ):
        raise ValueError("full-game collection requires zero-command episode setup")
    expected_teams = np.broadcast_to(
        m.initial_teams or (0,) * m.player_count, (m.batch_size, m.player_count)
    )
    if not np.array_equal(b.team_ids()[:, : m.player_count], expected_teams):
        raise ValueError("full-game collection team seeds differ from configured metadata")
    behavior_hash = full_game_policy_sha256(policy)
    frozen = copy.deepcopy(policy).eval()
    # The source policy may continue to be edited by its caller; this collector
    # owns one private behavior version and never trains it while games run.
    for parameter in frozen.parameters():
        parameter.requires_grad_(False)
    capture = _CaptureCommands(b)
    controller = FullGamePolicyController(
        replace(configured, batch=cast("FullGameBatch", capture)), frozen, seed=sampling_seed
    )
    initial_hash = _initial_fingerprint(b)
    unstarted = np.flatnonzero(state[:, 3] == 0).astype(np.int64)
    if len(unstarted):
        b.start_environments(unstarted)
    metadata = FullGameCollectionMetadata(
        environment=m,
        encoder=controller.encoder.metadata,
        rewards=controller.rewards.metadata,
        architecture=frozen.architecture,
        behavior_policy_sha256=behavior_hash,
        initial_state_sha256=initial_hash,
        sampling_seed=sampling_seed,
        max_stored_decisions=max_stored_decisions,
    )
    rows: list[list[tuple[FullGamePolicyStep, int]]] = [[] for _ in range(m.batch_size)]
    terminal = np.zeros((m.batch_size, 9), dtype=np.int64)
    credits = np.zeros((m.batch_size, 9), dtype=np.int64)

    def credit(rewards: FullGameRewardBatch) -> None:
        terminal[:] += rewards.values
        credits[:] += rewards.valid
        if np.any(credits > 1):
            raise RuntimeError("full-game collection duplicated terminal credit")

    credit(controller.poll_rewards())
    error_reason = None
    rejected = np.empty((0, 6), dtype=np.int64)
    for _ in range(m.max_decisions):
        before = b.episode_snapshot().copy()
        active = np.flatnonzero(np.isin(before[:, 3], (1, 2, 3, 4, 6, 7))).astype(np.int64)
        if not len(active):
            break
        try:
            result = controller.step(active)
        except (ValueError, RuntimeError) as error:
            if capture.error is not error:
                raise  # Encoder/policy/credit bugs are not native failed episodes.
            if not np.array_equal(before, b.episode_snapshot()):
                raise RuntimeError("native rejected collection batch changed its cursor") from error
            messages = str(error).splitlines()
            error_reason = (messages[0] if messages else type(error).__name__)[:300]
            rejected = capture.commands.copy()
            break
        if not np.array_equal(result.transition.commands[:, :5], result.observation.leases):
            raise RuntimeError("accepted collection commands differ from observed leases")
        for index, command in enumerate(result.transition.commands):
            rows[int(command[0])].append((result, index))
        credit(result.transition.rewards)
    credit(controller.poll_rewards())
    state = b.episode_snapshot()
    winners = b.winning_seats()
    empty = controller.encoder.encode().take(np.empty(0, dtype=np.int64))
    episodes = []
    for env, entries in enumerate(rows):
        row = state[env]
        if len(entries) != row[7] or row[1] != len(entries) + 1:
            raise RuntimeError("full-game accepted decision accounting differs")
        ended = row[3] == 12
        expected_credit = np.arange(9) < m.player_count if ended else np.zeros(9, dtype=np.bool_)
        if not np.array_equal(credits[env], expected_credit):
            raise RuntimeError("full-game complete episode lacks exact terminal credit")
        if row[3] < 12 and error_reason is None:
            raise RuntimeError("full-game collection stopped before a real ending or native limit")
        statuses: dict[int, OutcomeStatus] = {
            1: "winner",
            2: "draw",
            3: "turn-limit",
            4: "decision-limit",
        }
        status = statuses.get(int(row[5]), "collection-aborted")
        outcome = FullGameCollectedOutcome(
            environment=env,
            epoch=int(row[0]),
            status=status,
            native_phase=int(row[3]),
            native_outcome=int(row[5]),
            native_actor=int(row[2]),
            accepted_commands=len(entries),
            completed_turns=int(row[4]),
            winner=int(row[6]),
            winning_players=tuple(int(i) for i in np.flatnonzero(winners[env])),
            terminal_values=tuple(int(i) for i in terminal[env]),
            terminal_valid=tuple(bool(i) for i in credits[env]),
        )
        samples = None
        if ended:
            observation = FullGameObservation(
                **{
                    field.name: _readonly(
                        np.concatenate(
                            [
                                getattr(result.observation, field.name)[i : i + 1]
                                for result, i in entries
                            ],
                            axis=0,
                        )
                    )
                    if entries
                    else getattr(empty, field.name)
                    for field in fields(empty)
                }
            )
            commands = (
                np.concatenate(
                    [result.transition.commands[i : i + 1] for result, i in entries], axis=0
                )
                if entries
                else np.empty((0, 6), dtype=np.int64)
            )
            previous = (
                np.concatenate(
                    [result.previous_memory[i : i + 1].numpy() for result, i in entries], axis=0
                )
                if entries
                else np.empty((0, frozen.architecture.hidden_size), dtype=np.float32)
            )
            logs = np.asarray(
                [float(result.log_probabilities[i]) for result, i in entries], dtype=np.float32
            )
            values = np.asarray(
                [float(result.values[i]) for result, i in entries], dtype=np.float32
            )
            targets = terminal[env, commands[:, 3]].astype(np.float32)
            for a in (commands, previous, logs, values, targets):
                _readonly(a)
            samples = FullGameEpisodeSamples(observation, commands, previous, logs, values, targets)
        episodes.append(FullGameCollectedEpisode(outcome, samples))
    if full_game_policy_sha256(frozen) != behavior_hash:
        raise RuntimeError("full-game behavior weights changed during collection")
    _readonly(rejected)
    collection = FullGameEpisodeCollection(metadata, tuple(episodes), rejected, error_reason)
    validate_full_game_collection(collection)
    return collection


def validate_full_game_collection(collection: FullGameEpisodeCollection) -> None:
    """Validate credit/command/data alignment before a learner uses any samples."""
    metadata = FullGameCollectionMetadata.model_validate(collection.metadata.model_dump())
    m = metadata.environment
    if tuple(e.outcome.environment for e in collection.episodes) != tuple(range(m.batch_size)):
        raise ValueError("full-game collection episode roster differs")
    teams = m.initial_teams or (0,) * m.player_count
    aborted = set()
    for episode in collection.episodes:
        o = FullGameCollectedOutcome.model_validate(episode.outcome.model_dump())
        if (
            o.native_actor >= m.player_count
            or o.winner >= m.player_count
            or o.accepted_commands > m.max_decisions
            or o.completed_turns > m.max_turns
        ):
            raise ValueError("full-game collection outcome exceeds configured bounds")
        ended = o.status in ("winner", "draw")
        winners = tuple(
            seat
            for seat in range(m.player_count)
            if o.status == "winner"
            and (seat == o.winner or (teams[o.winner] != 0 and teams[seat] == teams[o.winner]))
        )
        values = tuple(
            (1 if seat in winners else -1) if o.status == "winner" and seat < m.player_count else 0
            for seat in range(9)
        )
        valid = tuple(ended and seat < m.player_count for seat in range(9))
        if o.winning_players != winners or o.terminal_values != values or o.terminal_valid != valid:
            raise ValueError("full-game collection faction credit differs")
        if (episode.samples is not None) != ended:
            raise ValueError("full-game incomplete episode must not retain learner samples")
        if o.status == "collection-aborted":
            aborted.add(o.environment)
        if not ended:
            continue
        s = episode.samples
        assert s is not None
        n, h = o.accepted_commands, metadata.architecture.hidden_size
        layouts = (
            (s.commands, (n, 6), np.int64),
            (s.previous_memory, (n, h), np.float32),
            (s.behavior_log_probabilities, (n,), np.float32),
            (s.behavior_values, (n,), np.float32),
            (s.terminal_targets, (n,), np.float32),
            (s.observation.leases, (n, 5), np.int64),
            (s.observation.global_features, (n, len(GLOBAL_FIELDS)), np.float32),
            (s.observation.players, (n, 9, len(PLAYER_FEATURES)), np.float32),
            (s.observation.player_mask, (n, 9), np.bool_),
            (s.observation.card_model_ids, (n, 18), np.int64),
            (s.observation.hand_features, (n, 18, len(HAND_FEATURES)), np.float32),
            (s.observation.hand_mask, (n, 18), np.bool_),
            (s.observation.context_model_ids, (n, 5), np.int64),
            (s.observation.choice_mask, (n, 28), np.bool_),
            (s.observation.policy_gradient_mask, (n,), np.bool_),
        )
        for a, shape, dtype in layouts:
            if (
                not isinstance(a, np.ndarray)
                or a.shape != shape
                or a.dtype != dtype
                or not np.isfinite(a).all()
            ):
                raise ValueError("full-game collection sample layout or values differ")
        commands = s.commands
        if (
            np.any(commands[:, 0] != o.environment)
            or np.any(commands[:, 1] != o.epoch)
            or not np.array_equal(commands[:, 2], np.arange(1, n + 1))
            or np.any(commands[:, 3] < 0)
            or np.any(commands[:, 3] >= m.player_count)
            or not np.isin(commands[:, 4], (1, 2, 3, 4, 6, 7)).all()
            or np.any(commands[:, 5] < 0)
            or np.any(commands[:, 5] >= 28)
            or not np.array_equal(commands[:, :5], s.observation.leases)
            or not s.observation.choice_mask[np.arange(n), commands[:, 5]].all()
            or not np.array_equal(
                s.terminal_targets, np.asarray(values, dtype=np.float32)[commands[:, 3]]
            )
            or np.any(s.behavior_log_probabilities > 1e-6)
        ):
            raise ValueError("full-game collection accepted samples or terminal targets differ")
        for actor in range(m.player_count):
            indexes = np.flatnonzero(commands[:, 3] == actor)
            if len(indexes) and s.previous_memory[indexes[0]].any():
                raise ValueError("full-game collection contains cross-episode seat memory")
    rejected = collection.rejected_commands
    if (
        not isinstance(rejected, np.ndarray)
        or rejected.dtype != np.int64
        or rejected.ndim != 2
        or rejected.shape[1] != 6
        or len(rejected) != len(aborted)
        or set(rejected[:, 0].tolist()) != aborted
        or bool(aborted) != (collection.collection_error is not None)
    ):
        raise ValueError("full-game collection rejection accounting differs")
    for command in rejected:
        o = collection.episodes[int(command[0])].outcome
        if (
            tuple(command[:5])
            != (o.environment, o.epoch, o.accepted_commands + 1, o.native_actor, o.native_phase)
            or not 0 <= command[5] < 28
        ):
            raise ValueError("full-game collection rejected command context differs")
