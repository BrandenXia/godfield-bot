from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import ModelStatus, load_model
from godfield_bot.simulation import AttackDefenseRuleset, create_attack_defense_simulation
from godfield_bot.simulation_evaluation import (
    SimulationEvaluationConfig,
    SimulationMatchupEvaluation,
    _evaluate_side,
    _resolve_device,
    _summarize_matchup,
)
from godfield_bot.simulation_league import (
    SimulationLeagueSnapshot,
    load_simulation_league,
    validate_league_model,
)
from godfield_bot.simulation_policy import build_curriculum_heuristic


class SimulationLeagueEvaluationConfig(BaseModel):
    ruleset: AttackDefenseRuleset
    games_per_seat: int = Field(default=2048, ge=2, le=100_000)
    max_decisions_per_game: int = Field(default=512, ge=2, le=100_000)
    minimum_score: float = Field(default=0.5, ge=0.5, le=1)
    confidence_z: float = Field(default=1.96, gt=0, le=10)
    seed: int = Field(default=67, ge=0, le=18_446_744_073_709_551_615)
    device: Literal["cpu", "mps", "cuda"] = "cpu"


class SimulationLeagueEvaluationReport(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["native-frozen-league-evaluation"] = "native-frozen-league-evaluation"
    evaluation_id: str
    created_at: datetime
    candidate_model_id: str
    candidate_weights_sha256: str
    parent_model_id: str
    parent_weights_sha256: str
    league: SimulationLeagueSnapshot
    league_sha256: str
    input_sha256: str
    config: SimulationLeagueEvaluationConfig
    matchups: tuple[SimulationMatchupEvaluation, ...]
    passed: bool
    gate_reasons: tuple[str, ...]
    promotion_eligible: Literal[False] = False


class StoredSimulationLeagueEvaluation(BaseModel):
    report_path: str
    report: SimulationLeagueEvaluationReport


def evaluate_simulation_league_candidate(
    *,
    candidate_model_directory: Path,
    league_path: Path,
    snapshot_path: Path,
    evaluation_directory: Path,
    config: SimulationLeagueEvaluationConfig,
) -> StoredSimulationLeagueEvaluation:
    """Require paired superiority over every frozen member, with no incomplete games."""

    manifest, candidate = load_model(candidate_model_directory)
    if manifest.status is not ModelStatus.CANDIDATE or manifest.parent_model_id is None:
        raise ValueError("league evaluation requires a candidate with a frozen parent")
    parent, _ = load_model(candidate_model_directory.parent / manifest.parent_model_id)
    if parent.model_id != manifest.parent_model_id:
        raise ValueError("parent directory manifest identity differs from the candidate lineage")
    bible = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(bible)
    simulation = create_attack_defense_simulation(
        snapshot_path, batch_size=1, seed=config.seed, ruleset=config.ruleset
    ).metadata
    heuristic = build_curriculum_heuristic(bible, vocabulary, ruleset=config.ruleset)
    device = _resolve_device(config.device)
    league = load_simulation_league(
        league_path,
        reference=manifest,
        simulation=simulation,
        heuristic=heuristic,
        ruleset=config.ruleset,
        required_parent_id=parent.model_id,
        device=str(device),
    )
    # The learner must match the contract too, even if every opponent is compatible.
    validate_league_model(manifest, parent, simulation)
    training_league_digest = manifest.training_context.get("league_sha256")
    if training_league_digest is not None and training_league_digest != league.snapshot.sha256:
        raise ValueError("evaluation league differs from the candidate's frozen training league")
    candidate.to(device).eval()
    paired_config = SimulationEvaluationConfig(**config.model_dump())
    matchups: list[SimulationMatchupEvaluation] = []
    for member, opponent in zip(league.snapshot.members, league.models, strict=True):
        sides = [
            _evaluate_side(
                candidate=candidate,
                opponent=opponent,
                heuristic=heuristic if opponent is None else None,
                snapshot_path=snapshot_path,
                games=config.games_per_seat,
                seed=config.seed,
                candidate_seat=seat,
                max_decisions=config.max_decisions_per_game,
                device=device,
                ruleset=config.ruleset,
            )
            for seat in range(2)
        ]
        matchup = _summarize_matchup(
            opponent_kind=member.kind,
            opponent_id=member.opponent_id,
            candidate_as_seat_zero=sides[0],
            candidate_as_seat_one=sides[1],
            config=paired_config,
            require_superiority=True,
        )
        matchups.append(matchup)
        structlog.get_logger().info(
            "simulation_league_matchup",
            opponent_id=member.opponent_id,
            score=matchup.paired_score,
            lower_bound=matchup.paired_score_lower_bound,
            incomplete_games=matchup.incomplete_games,
            passed=matchup.passed,
        )
    reasons = tuple(
        (
            f"{matchup.opponent_id}: {matchup.incomplete_games} games exceeded the decision limit"
            if matchup.incomplete_games
            else f"{matchup.opponent_id}: paired lower bound "
            f"{matchup.paired_score_lower_bound:.4f} does not exceed "
            f"{matchup.required_paired_score:.4f}"
        )
        for matchup in matchups
        if not matchup.passed
    )
    inputs = {
        "source_kind": "native-frozen-league-evaluation",
        "candidate_model_id": manifest.model_id,
        "candidate_weights_sha256": manifest.weights_sha256,
        "parent_model_id": parent.model_id,
        "parent_weights_sha256": parent.weights_sha256,
        "league_sha256": league.snapshot.sha256,
        "config": config.model_dump(mode="json"),
    }
    report = SimulationLeagueEvaluationReport(
        evaluation_id=str(uuid4()),
        created_at=datetime.now(UTC),
        candidate_model_id=manifest.model_id,
        candidate_weights_sha256=manifest.weights_sha256,
        parent_model_id=parent.model_id,
        parent_weights_sha256=parent.weights_sha256,
        league=league.snapshot,
        league_sha256=league.snapshot.sha256,
        input_sha256=hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        config=config,
        matchups=tuple(matchups),
        passed=not reasons,
        gate_reasons=reasons,
    )
    prepare_private_directory(evaluation_directory)
    destination = evaluation_directory / f"{report.evaluation_id}.json"
    temporary = evaluation_directory / f".{report.evaluation_id}.tmp"
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return StoredSimulationLeagueEvaluation(report_path=str(destination), report=report)
