"""Source-pinned local guardian roster and per-episode frozen-opponent memory."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import uuid4

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.guardian_neural import (
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
    guardian_feature_tensors,
)
from godfield_bot.guardian_rollout import (
    GuardianObservation,
    GuardianRolloutArena,
    GuardianRolloutMetadata,
    IntArray,
    greedy_guardian_actions,
)

if TYPE_CHECKING:
    from godfield_bot.guardian_training import GuardianArenaManifest

Counter = Annotated[int, Field(ge=0, strict=True)]


def guardian_baseline_id(arena: GuardianRolloutMetadata) -> str:
    return (
        "greedy-discard-smoke-baseline-v3"
        if arena.config.inventory_discards
        else "greedy-utility-smoke-baseline-v2"
        if arena.config.inventory_utilities
        else "greedy-smoke-baseline-v1"
    )


def guardian_arena_contract(arena: GuardianRolloutMetadata) -> dict[str, object]:
    """Same exclusions as strict guardian resume: only seed/batch may differ."""
    return {
        "config": arena.config.model_dump(exclude={"batch_size", "seed"}),
        "native": arena.base_native.model_dump(exclude={"batch_size"}),
        "rollout": arena.model_dump(exclude={"config", "native"}),
        "discard_wrapper": arena.native.model_dump(exclude={"utility_base"})
        if arena.config.inventory_discards
        else None,
    }


class GuardianLeagueMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["greedy", "model"]
    opponent_id: str = Field(min_length=1)
    weight: int = Field(default=1, ge=1, le=1000, strict=True)
    checkpoint_directory: str | None = None
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    weights_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def source_identity(self) -> GuardianLeagueMember:
        sources = (self.checkpoint_directory, self.manifest_sha256, self.weights_sha256)
        if self.kind == "model":
            if (
                any(value is None for value in sources)
                or not Path(self.checkpoint_directory or "").is_absolute()
            ):
                raise ValueError(
                    "guardian league model needs an absolute path and both source hashes"
                )
        elif any(value is not None for value in sources):
            raise ValueError("guardian league greedy member cannot claim checkpoint sources")
        return self


class GuardianLeagueSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["local-frozen-guardian-league-v1"] = "local-frozen-guardian-league-v1"
    league_id: str = Field(min_length=1)
    created_at: datetime
    reference_model_id: str = Field(min_length=1)
    reference_weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    architecture: GuardianPolicyArchitecture
    arena: GuardianRolloutMetadata
    members: tuple[GuardianLeagueMember, ...] = Field(min_length=2, max_length=9)
    selection_stream: Literal["seed-environment-episode-channel-6774-v1"] = (
        "seed-environment-episode-channel-6774-v1"
    )
    opponent_action_mode: Literal["argmax"] = "argmax"
    opponent_scope: Literal["one-fixed-opponent-per-episode"] = "one-fixed-opponent-per-episode"
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def roster_contract(self) -> GuardianLeagueSnapshot:
        models = [member for member in self.members if member.kind == "model"]
        greedy = [member for member in self.members if member.kind == "greedy"]
        if (
            self.arena.config.player_count != 2
            or self.architecture.action_count != self.arena.action_count
            or self.architecture.hand_feature_count != self.arena.hand_feature_count
            or self.architecture.observation_schema_id != self.arena.observation_schema_id
            or len({member.opponent_id for member in self.members}) != len(self.members)
            or len({member.weights_sha256 for member in models}) != len(models)
            or len(greedy) != 1
            or greedy[0].opponent_id != guardian_baseline_id(self.arena)
            or not any(
                member.opponent_id == self.reference_model_id
                and member.weights_sha256 == self.reference_weights_sha256
                for member in models
            )
        ):
            raise ValueError(
                "guardian league needs distinct compatible policies and its exact parent"
            )
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class GuardianLeagueCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["episode-and-decision-counter-deltas-v1"] = (
        "episode-and-decision-counter-deltas-v1"
    )
    league_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_ids: tuple[str, ...] = Field(min_length=2, max_length=9)
    episode_starts: tuple[Counter, ...]
    learner_decisions: tuple[Counter, ...]
    opponent_decisions: tuple[Counter, ...]
    completed_games: tuple[Counter, ...]
    truncated_games: tuple[Counter, ...]

    @model_validator(mode="after")
    def account_members(self) -> GuardianLeagueCounts:
        if len(set(self.member_ids)) != len(self.member_ids) or any(
            len(getattr(self, field)) != len(self.member_ids)
            for field in (
                "episode_starts",
                "learner_decisions",
                "opponent_decisions",
                "completed_games",
                "truncated_games",
            )
        ):
            raise ValueError("guardian league counters must align with every roster member")
        return self


@dataclass(frozen=True)
class FrozenGuardianLeague:
    snapshot: GuardianLeagueSnapshot
    models: tuple[GuardianArenaPolicy | None, ...]

    def __post_init__(self) -> None:
        if len(self.models) != len(self.snapshot.members):
            raise ValueError("frozen guardian models must align with roster members")
        for member, model in zip(self.snapshot.members, self.models, strict=True):
            if (member.kind == "greedy") != (model is None) or (
                model is not None
                and (
                    model.architecture != self.snapshot.architecture
                    or model.training
                    or any(parameter.requires_grad for parameter in model.parameters())
                )
            ):
                raise ValueError(
                    "guardian opponents must be compatible, eval-mode and gradient-frozen"
                )


def create_guardian_league(
    *,
    reference_checkpoint: Path,
    opponent_checkpoints: tuple[Path, ...],
    catalog_path: Path,
    bible_path: Path,
    league_directory: Path,
    greedy_weight: int = 1,
) -> tuple[Path, GuardianLeagueSnapshot]:
    from godfield_bot.guardian_training import (
        MANIFEST_FILE,
        _compatible,
        _file_digest,
        load_guardian_checkpoint,
    )

    with torch.random.fork_rng(devices=[]):
        reference, _ = load_guardian_checkpoint(reference_checkpoint)
        fresh = GuardianRolloutArena(
            catalog_path=catalog_path, bible_path=bible_path, config=reference.training.arena
        )
        _compatible(reference, fresh.metadata, reference.architecture)
        members = [
            GuardianLeagueMember(
                kind="greedy",
                opponent_id=guardian_baseline_id(fresh.metadata),
                weight=greedy_weight,
            )
        ]
        for directory in (reference_checkpoint, *opponent_checkpoints):
            manifest, _ = load_guardian_checkpoint(directory)
            _compatible(manifest, fresh.metadata, reference.architecture)
            members.append(
                GuardianLeagueMember(
                    kind="model",
                    opponent_id=manifest.model_id,
                    checkpoint_directory=str(directory.resolve()),
                    manifest_sha256=_file_digest(directory / MANIFEST_FILE),
                    weights_sha256=manifest.weights_sha256,
                )
            )
        snapshot = GuardianLeagueSnapshot(
            league_id=str(uuid4()),
            created_at=datetime.now(UTC),
            reference_model_id=reference.model_id,
            reference_weights_sha256=reference.weights_sha256,
            architecture=reference.architecture,
            arena=reference.arena,
            members=tuple(members),
        )
    league_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = league_directory / f"{snapshot.league_id}.json"
    temporary = league_directory / f".{snapshot.league_id}.tmp"
    with os.fdopen(os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as sink:
        sink.write(snapshot.model_dump_json(indent=2) + "\n")
    os.replace(temporary, destination)
    return destination, snapshot


def load_guardian_league(
    path: Path, *, reference: GuardianArenaManifest, arena: GuardianRolloutMetadata
) -> FrozenGuardianLeague:
    from godfield_bot.guardian_training import (
        MANIFEST_FILE,
        _compatible,
        _file_digest,
        load_guardian_checkpoint,
    )

    snapshot = GuardianLeagueSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        snapshot.reference_model_id != reference.model_id
        or snapshot.reference_weights_sha256 != reference.weights_sha256
        or snapshot.architecture != reference.architecture
        or guardian_arena_contract(snapshot.arena) != guardian_arena_contract(arena)
    ):
        raise ValueError("guardian league parent, architecture, or arena contract differs")
    models: list[GuardianArenaPolicy | None] = []
    # Loading policy modules must not advance the learner's sampling RNG.
    with torch.random.fork_rng(devices=[]):
        for member in snapshot.members:
            if member.kind == "greedy":
                models.append(None)
                continue
            assert member.checkpoint_directory is not None
            directory = Path(member.checkpoint_directory)
            manifest, model = load_guardian_checkpoint(directory)
            _compatible(manifest, arena, reference.architecture)
            if (
                manifest.model_id != member.opponent_id
                or manifest.weights_sha256 != member.weights_sha256
                or _file_digest(directory / MANIFEST_FILE) != member.manifest_sha256
            ):
                raise ValueError("guardian league checkpoint identity or source hashes changed")
            models.append(model.eval().requires_grad_(False))
    return FrozenGuardianLeague(snapshot=snapshot, models=tuple(models))


class GuardianLeagueController:
    """Own private opponent memories; a roster never becomes a learner feature."""

    def __init__(self, league: FrozenGuardianLeague, *, batch_size: int, seed: int):
        if (
            type(batch_size) is not int
            or not 1 <= batch_size <= 4096
            or type(seed) is not int
            or not 0 <= seed <= 2**32 - 1
        ):
            raise ValueError("guardian opponent batch/seed must satisfy rollout bounds")
        self.league = league
        self.seed = seed
        self.assignments = np.full(batch_size, -1, dtype=np.int64)
        self.episode_ids = np.full(batch_size, -1, dtype=np.int64)
        self.memories = [
            torch.zeros((batch_size, 2, model.hidden_size)) if model is not None else None
            for model in league.models
        ]
        weights = np.asarray(
            [member.weight for member in league.snapshot.members], dtype=np.float64
        )
        self.probabilities = weights / weights.sum()

    def begin(self, observation: GuardianObservation) -> IntArray:
        if observation.episode_ids.shape != self.episode_ids.shape or np.any(
            observation.episode_ids < 0
        ):
            raise ValueError("guardian opponent episode projection differs from its batch")
        changed = np.flatnonzero(observation.episode_ids != self.episode_ids)
        for env in changed:
            episode = int(observation.episode_ids[env])
            rng = np.random.default_rng(
                np.random.SeedSequence([self.seed, int(env), episode, 6774])
            )
            self.assignments[env] = rng.choice(len(self.probabilities), p=self.probabilities)
            self.episode_ids[env] = episode
        for memory in self.memories:
            if memory is not None:
                memory[changed] = 0
        return changed

    def actions(self, observation: GuardianObservation, rows: IntArray) -> IntArray:
        if (
            rows.ndim != 1
            or rows.dtype != np.int64
            or np.any(rows < 0)
            or np.any(rows >= len(self.assignments))
            or len(np.unique(rows)) != len(rows)
            or observation.episode_ids.shape != self.episode_ids.shape
            or np.any(self.assignments[rows] < 0)
            or np.any(observation.episode_ids[rows] != self.episode_ids[rows])
            or not observation.active[rows].all()
        ):
            raise ValueError("guardian opponent rows must be active in an assigned episode")
        result = np.full(len(observation.actors), -1, dtype=np.int64)
        for index, model in enumerate(self.league.models):
            selected = rows[self.assignments[rows] == index]
            if not len(selected):
                continue
            if model is None:
                result[selected] = greedy_guardian_actions(observation)[selected]
                continue
            memory = self.memories[index]
            assert memory is not None
            actors = torch.from_numpy(observation.actors[selected].copy())
            with torch.no_grad():
                logits, _, states = model(
                    *guardian_feature_tensors(observation, selected),
                    recurrent_state=memory[selected, actors],
                )
            result[selected] = logits.argmax(-1).numpy()
            memory[selected, actors] = states
        return result
