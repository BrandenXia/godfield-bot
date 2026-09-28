from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import ModelManifest, load_model
from godfield_bot.neural import RecurrentPolicyValueNet
from godfield_bot.simulation import (
    AttackDefenseRuleset,
    SimulationMetadata,
    create_attack_defense_simulation,
)
from godfield_bot.simulation_policy import CurriculumHeuristic, build_curriculum_heuristic

LEAGUE_ALGORITHM = "frozen-league-recurrent-ppo-v2"


class SimulationLeagueMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    kind: Literal["model", "heuristic"]
    opponent_id: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0, le=1_000_000)
    weights_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    model_directory: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> SimulationLeagueMember:
        if self.kind == "model":
            if self.weights_sha256 is None or not self.model_directory:
                raise ValueError("model league members require a checkpoint path and weight hash")
        elif self.weights_sha256 is not None or self.model_directory is not None:
            raise ValueError("heuristic league members cannot name model weights")
        return self


class SimulationLeagueSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    league_id: str
    created_at: datetime
    ruleset: AttackDefenseRuleset
    simulation: SimulationMetadata
    members: tuple[SimulationLeagueMember, ...] = Field(min_length=2, max_length=17)
    opponent_action_mode: Literal["argmax"] = "argmax"
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_members(self) -> SimulationLeagueSnapshot:
        identities = [(member.kind, member.opponent_id) for member in self.members]
        if len(set(identities)) != len(identities):
            raise ValueError("league contains duplicate opponents")
        if sum(member.kind == "heuristic" for member in self.members) != 1:
            raise ValueError("league requires exactly one versioned heuristic")
        return self

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class FrozenSimulationLeague:
    snapshot: SimulationLeagueSnapshot
    # Checkpoints align with snapshot.members; the heuristic has no neural model.
    models: tuple[RecurrentPolicyValueNet | None, ...]
    heuristic: CurriculumHeuristic


def validate_league_model(
    manifest: ModelManifest,
    reference: ModelManifest,
    simulation: SimulationMetadata,
) -> None:
    if manifest.architecture != reference.architecture:
        raise ValueError("league checkpoint architecture differs from the learner")
    if manifest.feature_schema_version != simulation.observation_schema_version:
        raise ValueError("league checkpoint observation schema differs from the simulator")
    if manifest.client_sha256 != simulation.client_sha256:
        raise ValueError("league checkpoint client fingerprint differs from the simulator")
    if manifest.vocabulary_sha256 != simulation.vocabulary_sha256:
        raise ValueError("league checkpoint vocabulary differs from the simulator")
    if (
        manifest.architecture.action_count != simulation.action_count
        or manifest.architecture.global_feature_count != simulation.global_feature_count
    ):
        raise ValueError("league checkpoint input/output dimensions differ from the simulator")


def create_simulation_league(
    *,
    base_model_directory: Path,
    opponent_model_directories: tuple[Path, ...],
    snapshot_path: Path,
    league_directory: Path,
    ruleset: AttackDefenseRuleset,
    heuristic_weight: float = 1.0,
) -> tuple[Path, SimulationLeagueSnapshot]:
    """Freeze an explicit opponent roster, always including the training parent."""

    reference, _ = load_model(base_model_directory)
    simulation = create_attack_defense_simulation(
        snapshot_path, batch_size=1, seed=67, ruleset=ruleset
    ).metadata
    validate_league_model(reference, reference, simulation)
    bible = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(bible)
    heuristic = build_curriculum_heuristic(bible, vocabulary, ruleset=ruleset)
    members = [
        SimulationLeagueMember(
            kind="heuristic", opponent_id=heuristic.policy_id, weight=heuristic_weight
        )
    ]
    for directory in (base_model_directory, *opponent_model_directories):
        manifest, _ = load_model(directory)
        validate_league_model(manifest, reference, simulation)
        members.append(
            SimulationLeagueMember(
                kind="model",
                opponent_id=manifest.model_id,
                weights_sha256=manifest.weights_sha256,
                model_directory=str(directory.resolve()),
            )
        )
    league = SimulationLeagueSnapshot(
        league_id=str(uuid4()),
        created_at=datetime.now(UTC),
        ruleset=ruleset,
        simulation=simulation,
        members=tuple(members),
    )
    prepare_private_directory(league_directory)
    destination = league_directory / f"{league.league_id}.json"
    temporary = league_directory / f".{league.league_id}.tmp"
    temporary.write_text(league.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination, league


def load_simulation_league(
    path: Path,
    *,
    reference: ModelManifest,
    simulation: SimulationMetadata,
    heuristic: CurriculumHeuristic,
    ruleset: AttackDefenseRuleset,
    required_parent_id: str,
    device: str,
) -> FrozenSimulationLeague:
    league = SimulationLeagueSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    if league.ruleset != ruleset or league.simulation != simulation:
        raise ValueError("league snapshot uses a different simulator contract")
    if not any(
        member.kind == "model" and member.opponent_id == required_parent_id
        for member in league.members
    ):
        raise ValueError("league must include the exact frozen training parent")
    models: list[RecurrentPolicyValueNet | None] = []
    for member in league.members:
        if member.kind == "heuristic":
            if member.opponent_id != heuristic.policy_id:
                raise ValueError("league heuristic version differs from the simulator")
            models.append(None)
            continue
        assert member.model_directory is not None
        manifest, model = load_model(Path(member.model_directory))
        if (
            manifest.model_id != member.opponent_id
            or manifest.weights_sha256 != member.weights_sha256
        ):
            raise ValueError("league checkpoint identity or weights changed after freezing")
        validate_league_model(manifest, reference, simulation)
        model.to(device).eval()
        model.requires_grad_(False)
        models.append(model)
    return FrozenSimulationLeague(snapshot=league, models=tuple(models), heuristic=heuristic)
