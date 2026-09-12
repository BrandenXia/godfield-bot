from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
import numpy.typing as npt
import torch
from pydantic import BaseModel, Field
from torch import Tensor

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import ModelManifest, ModelStatus, load_model, vocabulary_digest
from godfield_bot.neural import RecurrentPolicyValueNet
from godfield_bot.simulation import (
    SimulationMetadata,
    create_attack_defense_simulation,
    simulation_feature_tensors,
)
from godfield_bot.simulation_policy import (
    CurriculumHeuristic,
    build_curriculum_heuristic,
    curriculum_heuristic_actions,
)


class SimulationEvaluationError(RuntimeError):
    """Raised when a curriculum comparison cannot produce trustworthy evidence."""


class SimulationEvaluationConfig(BaseModel):
    ruleset: Literal[
        "fixed-role",
        "mixed-hand",
        "elemental-hand",
        "combo-hand",
        "resource-hand",
        "stochastic-resource-hand",
        "expanded-resource-hand",
        "reflection-resource-hand",
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
    ] = "fixed-role"
    games_per_seat: int = Field(default=512, ge=1, le=100_000)
    max_decisions_per_game: int = Field(default=512, ge=2, le=100_000)
    minimum_score: float = Field(default=0.5, ge=0, le=1)
    heuristic_noninferiority_margin: float = Field(default=0.025, ge=0, le=1)
    confidence_z: float = Field(default=1.96, gt=0, le=10)
    seed: int = Field(default=67, ge=0, le=18_446_744_073_709_551_615)
    device: Literal["cpu", "mps", "cuda"] = "cpu"


class SimulationMatchupEvaluation(BaseModel):
    opponent_kind: Literal["model", "heuristic"]
    opponent_id: str
    gate_kind: Literal["paired-superiority", "paired-noninferiority"]
    games_per_seat: int = Field(gt=0)
    completed_games: int = Field(ge=0)
    incomplete_games: int = Field(ge=0)
    candidate_wins: int = Field(ge=0)
    candidate_losses: int = Field(ge=0)
    candidate_draws: int = Field(ge=0)
    candidate_score: float = Field(ge=0, le=1)
    wilson_lower_bound: float = Field(ge=0, le=1)
    paired_score: float = Field(ge=0, le=1)
    paired_score_standard_error: float = Field(ge=0)
    paired_score_lower_bound: float = Field(ge=0, le=1)
    required_paired_score: float = Field(ge=0, le=1)
    mean_decisions_per_completed_game: float = Field(ge=0)
    candidate_won_both_pairs: int = Field(ge=0)
    candidate_split_pairs: int = Field(ge=0)
    candidate_lost_both_pairs: int = Field(ge=0)
    incomplete_pairs: int = Field(ge=0)
    kernel_transitions: int = Field(ge=0)
    passed: bool


class SimulationEvaluationReport(BaseModel):
    schema_version: int = 2
    evaluation_id: str
    created_at: datetime
    candidate_model_id: str
    candidate_weights_sha256: str
    parent_model_id: str
    parent_weights_sha256: str
    input_sha256: str
    simulation: SimulationMetadata
    config: SimulationEvaluationConfig
    matchups: tuple[SimulationMatchupEvaluation, SimulationMatchupEvaluation]
    passed: bool
    gate_reasons: tuple[str, ...]
    promotion_eligible: Literal[False] = False


class StoredSimulationEvaluation(BaseModel):
    report_path: str
    report: SimulationEvaluationReport


@dataclass(frozen=True)
class _SideEvaluation:
    outcomes: np.ndarray
    completed: np.ndarray
    decisions: np.ndarray
    kernel_transitions: int


def _resolve_device(name: str) -> torch.device:
    device = torch.device(name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise SimulationEvaluationError("CUDA was requested but is unavailable")
    if device.type == "mps" and not torch.backends.mps.is_available():
        raise SimulationEvaluationError("MPS was requested but is unavailable")
    return device


def wilson_lower_bound(successes: float, trials: int, z: float) -> float:
    if trials <= 0:
        return 0.0
    probability = successes / trials
    z_squared = z * z
    denominator = 1.0 + z_squared / trials
    center = probability + z_squared / (2.0 * trials)
    radius = z * math.sqrt(
        probability * (1.0 - probability) / trials + z_squared / (4.0 * trials * trials)
    )
    return max(0.0, (center - radius) / denominator)


def paired_score_statistics(
    scores: npt.NDArray[np.float64],
    z: float,
) -> tuple[float, float, float]:
    """Return the mean, standard error, and normal lower bound of paired scores."""

    if scores.size == 0:
        return 0.0, 0.0, 0.0
    mean = float(scores.mean())
    if scores.size == 1:
        return mean, 0.0, 0.0
    standard_error = float(scores.std(ddof=1) / math.sqrt(scores.size))
    return mean, standard_error, max(0.0, mean - z * standard_error)


def _model_actions(
    model: RecurrentPolicyValueNet,
    recurrent_states: Tensor,
    observation: tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor],
    rows: npt.NDArray[np.int64],
    device: torch.device,
) -> npt.NDArray[np.int64]:
    if rows.size == 0:
        return np.empty(0, dtype=np.int64)
    row_indices = torch.from_numpy(rows).to(device=device, dtype=torch.long)
    with torch.no_grad():
        logits, _, next_states = model(
            *(tensor.index_select(0, row_indices) for tensor in observation),
            recurrent_state=recurrent_states.index_select(0, row_indices),
        )
    recurrent_states[row_indices] = next_states
    actions: npt.NDArray[np.int64] = logits.argmax(dim=1).cpu().numpy().astype(np.int64, copy=False)
    return actions


def _evaluate_side(
    *,
    candidate: RecurrentPolicyValueNet,
    opponent: RecurrentPolicyValueNet | None,
    heuristic: CurriculumHeuristic | None,
    snapshot_path: Path,
    games: int,
    seed: int,
    candidate_seat: int,
    max_decisions: int,
    device: torch.device,
    ruleset: Literal[
        "fixed-role",
        "mixed-hand",
        "elemental-hand",
        "combo-hand",
        "resource-hand",
        "stochastic-resource-hand",
        "expanded-resource-hand",
        "reflection-resource-hand",
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
    ],
) -> _SideEvaluation:
    simulation = create_attack_defense_simulation(
        snapshot_path,
        batch_size=games,
        seed=seed,
        ruleset=ruleset,
    )
    batch = simulation.batch
    candidate_states = torch.zeros(
        (games, candidate.hidden_size),
        dtype=torch.float32,
        device=device,
    )
    opponent_states = (
        torch.zeros(
            (games, opponent.hidden_size),
            dtype=torch.float32,
            device=device,
        )
        if opponent is not None
        else None
    )
    completed = np.zeros(games, dtype=np.bool_)
    outcomes = np.zeros(games, dtype=np.int8)
    decisions = np.zeros(games, dtype=np.uint32)
    previous_terminated = np.zeros(games, dtype=np.bool_)
    kernel_transitions = 0

    for decision in range(max_decisions):
        if decision > 0 and previous_terminated.any():
            reset_rows = torch.from_numpy(previous_terminated).to(device=device)
            candidate_states[reset_rows] = 0.0
            if opponent_states is not None:
                opponent_states[reset_rows] = 0.0
            batch.reset_done()

        observation = simulation_feature_tensors(simulation, device=str(device))
        actors = np.array(batch.active_players, copy=True)
        candidate_rows = np.flatnonzero(actors == candidate_seat)
        opponent_rows = np.flatnonzero(actors != candidate_seat)
        actions = np.full(games, -1, dtype=np.int64)
        actions[candidate_rows] = _model_actions(
            candidate,
            candidate_states,
            observation,
            candidate_rows,
            device,
        )
        if opponent is not None and opponent_states is not None:
            actions[opponent_rows] = _model_actions(
                opponent,
                opponent_states,
                observation,
                opponent_rows,
                device,
            )
        elif heuristic is not None:
            actions[opponent_rows] = curriculum_heuristic_actions(
                simulation,
                opponent_rows,
                heuristic,
            )
        else:
            raise SimulationEvaluationError("evaluation opponent is missing")
        if np.any(actions < 0):
            raise SimulationEvaluationError("evaluation failed to assign every action")

        decisions[~completed] += 1
        batch.step(actions)
        kernel_transitions += games
        previous_terminated = np.array(batch.terminated, copy=True)
        newly_completed = previous_terminated & ~completed
        if newly_completed.any():
            candidate_returns = np.array(batch.terminal_returns, copy=True)[:, candidate_seat]
            outcomes[newly_completed] = np.sign(candidate_returns[newly_completed]).astype(np.int8)
            completed[newly_completed] = True
        if completed.all():
            break

    return _SideEvaluation(
        outcomes=outcomes,
        completed=completed,
        decisions=decisions,
        kernel_transitions=kernel_transitions,
    )


def _summarize_matchup(
    *,
    opponent_kind: Literal["model", "heuristic"],
    opponent_id: str,
    candidate_as_seat_zero: _SideEvaluation,
    candidate_as_seat_one: _SideEvaluation,
    config: SimulationEvaluationConfig,
) -> SimulationMatchupEvaluation:
    sides = (candidate_as_seat_zero, candidate_as_seat_one)
    completed_games = sum(int(side.completed.sum()) for side in sides)
    incomplete_games = 2 * config.games_per_seat - completed_games
    completed_outcomes = np.concatenate([side.outcomes[side.completed] for side in sides])
    candidate_wins = int(np.count_nonzero(completed_outcomes == 1))
    candidate_losses = int(np.count_nonzero(completed_outcomes == -1))
    candidate_draws = int(np.count_nonzero(completed_outcomes == 0))
    score_successes = candidate_wins + 0.5 * candidate_draws
    score = score_successes / completed_games if completed_games else 0.0
    lower_bound = wilson_lower_bound(
        score_successes,
        completed_games,
        config.confidence_z,
    )

    paired_complete = candidate_as_seat_zero.completed & candidate_as_seat_one.completed
    paired_wins = candidate_as_seat_zero.outcomes.astype(
        np.int16
    ) + candidate_as_seat_one.outcomes.astype(np.int16)
    won_both = int(np.count_nonzero(paired_complete & (paired_wins == 2)))
    lost_both = int(np.count_nonzero(paired_complete & (paired_wins == -2)))
    split = int(np.count_nonzero(paired_complete)) - won_both - lost_both
    paired_scores = (
        candidate_as_seat_zero.outcomes[paired_complete].astype(np.float64)
        + candidate_as_seat_one.outcomes[paired_complete].astype(np.float64)
        + 2.0
    ) / 4.0
    paired_score, paired_standard_error, paired_lower_bound = paired_score_statistics(
        paired_scores,
        config.confidence_z,
    )
    gate_kind: Literal["paired-superiority", "paired-noninferiority"]
    if opponent_kind == "model":
        gate_kind = "paired-superiority"
        required_paired_score = config.minimum_score
        confidence_passed = paired_lower_bound > required_paired_score
    else:
        gate_kind = "paired-noninferiority"
        required_paired_score = max(
            0.0,
            config.minimum_score - config.heuristic_noninferiority_margin,
        )
        confidence_passed = paired_lower_bound >= required_paired_score
    completed_decisions = np.concatenate([side.decisions[side.completed] for side in sides])
    mean_decisions = (
        float(completed_decisions.astype(np.float64).mean()) if completed_decisions.size else 0.0
    )
    return SimulationMatchupEvaluation(
        opponent_kind=opponent_kind,
        opponent_id=opponent_id,
        gate_kind=gate_kind,
        games_per_seat=config.games_per_seat,
        completed_games=completed_games,
        incomplete_games=incomplete_games,
        candidate_wins=candidate_wins,
        candidate_losses=candidate_losses,
        candidate_draws=candidate_draws,
        candidate_score=score,
        wilson_lower_bound=lower_bound,
        paired_score=paired_score,
        paired_score_standard_error=paired_standard_error,
        paired_score_lower_bound=paired_lower_bound,
        required_paired_score=required_paired_score,
        mean_decisions_per_completed_game=mean_decisions,
        candidate_won_both_pairs=won_both,
        candidate_split_pairs=split,
        candidate_lost_both_pairs=lost_both,
        incomplete_pairs=config.games_per_seat - int(np.count_nonzero(paired_complete)),
        kernel_transitions=sum(side.kernel_transitions for side in sides),
        passed=incomplete_games == 0 and confidence_passed,
    )


def _input_digest(
    *,
    candidate: ModelManifest,
    parent: ModelManifest,
    simulation: SimulationMetadata,
    config: SimulationEvaluationConfig,
    heuristic_policy_id: str,
) -> str:
    value = {
        "schema_version": 2,
        "candidate_model_id": candidate.model_id,
        "candidate_weights_sha256": candidate.weights_sha256,
        "parent_model_id": parent.model_id,
        "parent_weights_sha256": parent.weights_sha256,
        "heuristic_policy_id": heuristic_policy_id,
        "simulation": simulation.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_report(report: SimulationEvaluationReport, directory: Path) -> Path:
    prepare_private_directory(directory)
    destination = directory / f"{report.evaluation_id}.json"
    temporary = directory / f".{report.evaluation_id}.json.tmp"
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination


def evaluate_simulation_candidate(
    *,
    candidate_model_directory: Path,
    snapshot_path: Path,
    evaluation_directory: Path,
    config: SimulationEvaluationConfig,
) -> StoredSimulationEvaluation:
    """Run paired curriculum comparisons against the frozen parent and heuristic."""

    candidate_manifest, candidate = load_model(candidate_model_directory)
    if candidate_manifest.status is not ModelStatus.CANDIDATE:
        raise ValueError("simulation evaluation requires a candidate model")
    if candidate_manifest.parent_model_id is None:
        raise ValueError("candidate model has no parent for frozen comparison")
    parent_directory = candidate_model_directory.parent / candidate_manifest.parent_model_id
    parent_manifest, parent = load_model(parent_directory)
    if parent_manifest.model_id != candidate_manifest.parent_model_id:
        raise ValueError("parent directory manifest identity differs from the candidate lineage")
    if candidate_manifest.architecture != parent_manifest.architecture:
        raise ValueError("candidate architecture differs from its parent")
    if candidate_manifest.client_sha256 != parent_manifest.client_sha256:
        raise ValueError("candidate client fingerprint differs from its parent")
    if candidate_manifest.vocabulary_sha256 != parent_manifest.vocabulary_sha256:
        raise ValueError("candidate vocabulary differs from its parent")

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    if candidate_manifest.client_sha256 != snapshot.client.sha256:
        raise ValueError("candidate client fingerprint differs from the Bible snapshot")
    if candidate_manifest.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ValueError("candidate vocabulary differs from the Bible snapshot")
    simulation = create_attack_defense_simulation(
        snapshot_path,
        batch_size=1,
        seed=config.seed,
        ruleset=config.ruleset,
    )
    if simulation.metadata.vocabulary_sha256 != candidate_manifest.vocabulary_sha256:
        raise ValueError("simulator vocabulary differs from the candidate")
    if (
        simulation.metadata.global_feature_count
        != candidate_manifest.architecture.global_feature_count
    ):
        raise ValueError("simulator global features differ from the candidate")
    if simulation.metadata.observation_schema_version != candidate_manifest.feature_schema_version:
        raise ValueError("simulator observation schema differs from the candidate")

    device = _resolve_device(config.device)
    candidate.to(device).eval()
    parent.to(device).eval()
    heuristic = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset=config.ruleset,
    )

    parent_sides = (
        _evaluate_side(
            candidate=candidate,
            opponent=parent,
            heuristic=None,
            snapshot_path=snapshot_path,
            games=config.games_per_seat,
            seed=config.seed,
            candidate_seat=0,
            max_decisions=config.max_decisions_per_game,
            device=device,
            ruleset=config.ruleset,
        ),
        _evaluate_side(
            candidate=candidate,
            opponent=parent,
            heuristic=None,
            snapshot_path=snapshot_path,
            games=config.games_per_seat,
            seed=config.seed,
            candidate_seat=1,
            max_decisions=config.max_decisions_per_game,
            device=device,
            ruleset=config.ruleset,
        ),
    )
    heuristic_sides = (
        _evaluate_side(
            candidate=candidate,
            opponent=None,
            heuristic=heuristic,
            snapshot_path=snapshot_path,
            games=config.games_per_seat,
            seed=config.seed,
            candidate_seat=0,
            max_decisions=config.max_decisions_per_game,
            device=device,
            ruleset=config.ruleset,
        ),
        _evaluate_side(
            candidate=candidate,
            opponent=None,
            heuristic=heuristic,
            snapshot_path=snapshot_path,
            games=config.games_per_seat,
            seed=config.seed,
            candidate_seat=1,
            max_decisions=config.max_decisions_per_game,
            device=device,
            ruleset=config.ruleset,
        ),
    )
    matchups = (
        _summarize_matchup(
            opponent_kind="model",
            opponent_id=parent_manifest.model_id,
            candidate_as_seat_zero=parent_sides[0],
            candidate_as_seat_one=parent_sides[1],
            config=config,
        ),
        _summarize_matchup(
            opponent_kind="heuristic",
            opponent_id=heuristic.policy_id,
            candidate_as_seat_zero=heuristic_sides[0],
            candidate_as_seat_one=heuristic_sides[1],
            config=config,
        ),
    )
    gate_reasons: list[str] = []
    for matchup in matchups:
        if matchup.passed:
            continue
        if matchup.incomplete_games:
            gate_reasons.append(
                f"{matchup.opponent_id}: {matchup.incomplete_games} games exceeded "
                "the decision limit"
            )
        elif matchup.gate_kind == "paired-superiority":
            gate_reasons.append(
                f"{matchup.opponent_id}: paired lower bound "
                f"{matchup.paired_score_lower_bound:.4f} does not exceed "
                f"{matchup.required_paired_score:.4f}"
            )
        else:
            gate_reasons.append(
                f"{matchup.opponent_id}: paired lower bound "
                f"{matchup.paired_score_lower_bound:.4f} is below non-inferiority "
                f"threshold {matchup.required_paired_score:.4f}"
            )
    report = SimulationEvaluationReport(
        evaluation_id=str(uuid4()),
        created_at=datetime.now(UTC),
        candidate_model_id=candidate_manifest.model_id,
        candidate_weights_sha256=candidate_manifest.weights_sha256,
        parent_model_id=parent_manifest.model_id,
        parent_weights_sha256=parent_manifest.weights_sha256,
        input_sha256=_input_digest(
            candidate=candidate_manifest,
            parent=parent_manifest,
            simulation=simulation.metadata,
            config=config,
            heuristic_policy_id=heuristic.policy_id,
        ),
        simulation=simulation.metadata,
        config=config,
        matchups=matchups,
        passed=not gate_reasons,
        gate_reasons=tuple(gate_reasons),
    )
    destination = _write_report(report, evaluation_directory)
    return StoredSimulationEvaluation(report_path=str(destination), report=report)
