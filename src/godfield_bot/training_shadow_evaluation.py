from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.action import ActionTransition, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenObservation
from godfield_bot.domain.outcome import MatchOutcome, MatchResult, SparseTerminalReward
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.run import EventKind, RunEvent, RunMode, RunRecord, RunStatus
from godfield_bot.features import DREAM_FEATURE_SCHEMA_VERSION
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.model_registry import ModelStatus, load_model
from godfield_bot.outcomes import classify_two_player_terminal
from godfield_bot.run_store import RunStore
from godfield_bot.simulation import SimulationMetadata
from godfield_bot.simulation_evaluation import (
    SimulationEvaluationReport,
    wilson_lower_bound,
)
from godfield_bot.simulation_policy import DREAM_RESOURCE_HEURISTIC_POLICY_ID
from godfield_bot.training_shadow import (
    DREAM_RULESET_ID,
    OFFICIAL_TRAINING_SHADOW_POLICY_ID,
    OfficialTrainingShadowPolicy,
    TrainingShadowEvidence,
)

TRAINING_SHADOW_READINESS_GATE_ID: Final = "official-training-shadow-readiness-v1"
VISIBILITY_ABSTAIN_REASON: Final = (
    "hidden player statistics require a visibility-aware feature schema"
)
REQUIRED_ACTION_FAMILIES: Final = (
    "artifact:armor",
    "artifact:miracles",
    "artifact:sundries",
    "artifact:weapons",
    "confirm:attack",
    "confirm:chance",
    "confirm:defense",
    "confirm:utility",
    "forgive",
    "pass",
)
STATUS_STRATA: Final = ("illness", "flash", "dark-cloud", "dream")
OPERATIONAL_TERMINAL_CLASSIFICATIONS: Final = frozenset(
    {
        "sustained_unknown_terminal_candidate",
        "unclassified_terminal_candidate",
    }
)


class TrainingShadowReadinessError(RuntimeError):
    """Raised when official Training shadow evidence cannot be audited safely."""


class TrainingShadowReadinessConfig(BaseModel):
    minimum_native_evaluations: int = Field(default=3, ge=1, le=100)
    minimum_completed_games: int = Field(default=20, ge=1, le=100_000)
    minimum_completion_lower_bound: float = Field(default=0.80, ge=0, le=1)
    minimum_exact_view_opportunities: int = Field(default=500, ge=1, le=1_000_000)
    minimum_exact_view_coverage_lower_bound: float = Field(default=0.98, ge=0, le=1)
    maximum_encoding_gaps: int = Field(default=5, ge=0, le=1_000_000)
    minimum_illness_opportunities: int = Field(default=20, ge=0, le=1_000_000)
    minimum_flash_opportunities: int = Field(default=10, ge=0, le=1_000_000)
    minimum_dark_cloud_opportunities: int = Field(default=20, ge=0, le=1_000_000)
    minimum_dream_opportunities: int = Field(default=20, ge=0, le=1_000_000)
    minimum_visibility_abstentions: int = Field(default=20, ge=0, le=1_000_000)
    minimum_each_action_family: int = Field(default=1, ge=0, le=1_000_000)
    maximum_failed_runs: int = Field(default=0, ge=0, le=100_000)
    confidence_z: float = Field(default=1.96, gt=0, le=10)


class TrainingShadowReadinessMetrics(BaseModel):
    runs_scanned: int = Field(ge=0)
    shadow_runs_seen: int = Field(ge=0)
    matching_runs: int = Field(ge=0)
    excluded_runs: dict[str, int]
    completed_games: int = Field(ge=0)
    incomplete_games: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    operational_aborts: int = Field(ge=0)
    behavior_wins: int = Field(ge=0)
    behavior_losses: int = Field(ge=0)
    behavior_draws: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=1)
    completion_lower_bound: float = Field(ge=0, le=1)
    shadow_samples: int = Field(ge=0)
    eligible_decisions: int = Field(ge=0)
    visibility_abstentions: int = Field(ge=0)
    exact_view_opportunities: int = Field(ge=0)
    exact_view_proposals: int = Field(ge=0)
    encoding_gaps: int = Field(ge=0)
    encoding_gap_reasons: dict[str, int]
    exact_view_coverage: float = Field(ge=0, le=1)
    exact_view_coverage_lower_bound: float = Field(ge=0, le=1)
    behavior_agreements: int = Field(ge=0)
    behavior_agreement: float = Field(ge=0, le=1)
    behavior_agreement_lower_bound: float = Field(ge=0, le=1)
    status_opportunities: dict[str, int]
    status_proposals: dict[str, int]
    proposal_action_families: dict[str, int]
    evidence_error_count: int = Field(ge=0)
    evidence_errors: tuple[str, ...]


class TrainingShadowReadinessReport(BaseModel):
    schema_version: Literal[1] = 1
    evaluation_id: str
    gate_id: Literal["official-training-shadow-readiness-v1"] = (
        TRAINING_SHADOW_READINESS_GATE_ID
    )
    created_at: datetime
    candidate_model_id: str
    candidate_weights_sha256: str
    shadow_policy_id: Literal["official-training-neural-shadow-v1"] = (
        "official-training-neural-shadow-v1"
    )
    behavior_policy_id: Literal["heuristic-v0"] = "heuristic-v0"
    feature_schema_version: Literal[10] = 10
    native_evaluation_ids: tuple[str, ...]
    native_evaluation_input_sha256s: tuple[str, ...]
    source_database: str
    native_evaluation_directory: str
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_ids: tuple[str, ...]
    config: TrainingShadowReadinessConfig
    metrics: TrainingShadowReadinessMetrics
    passed: bool
    ready_for_guarded_intervention: bool
    gate_reasons: tuple[str, ...]
    promotion_eligible: Literal[False] = False


class StoredTrainingShadowReadiness(BaseModel):
    report_path: str
    report: TrainingShadowReadinessReport


@dataclass
class _Counts:
    completed_games: int = 0
    failed_runs: int = 0
    operational_aborts: int = 0
    outcomes: Counter[str] = field(default_factory=Counter)
    shadow_samples: int = 0
    eligible_decisions: int = 0
    visibility_abstentions: int = 0
    exact_view_opportunities: int = 0
    exact_view_proposals: int = 0
    agreements: int = 0
    encoding_gaps: Counter[str] = field(default_factory=Counter)
    status_opportunities: Counter[str] = field(default_factory=Counter)
    status_proposals: Counter[str] = field(default_factory=Counter)
    proposal_families: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def add_error(self, run_id: str, sequence: int, reason: str) -> None:
        self.errors.append(f"{run_id}:{sequence}: {reason}")


def _rate(successes: int, trials: int) -> float:
    return successes / trials if trials else 0.0


def _action_family(action_id: str) -> str:
    if action_id.startswith("artifact:"):
        parts = action_id.split(":", 2)
        category = parts[2].split("/", 1)[0] if len(parts) == 3 else "unknown"
        return f"artifact:{category}"
    if action_id.startswith("confirm:"):
        return ":".join(action_id.split(":", 2)[:2])
    return action_id.split(":", 1)[0]


def _status_strata(state: GameState) -> set[str]:
    strata: set[str] = set()
    if any(player.illness_stage for player in state.players):
        strata.add("illness")
    if any(player.flashed for player in state.players):
        strata.add("flash")
    if any(player.dark_clouded for player in state.players):
        strata.add("dark-cloud")
    if any(player.dreaming for player in state.players):
        strata.add("dream")
    return strata


def _matching_run_reason(
    run: RunRecord,
    *,
    model_id: str,
    weights_sha256: str,
    client_sha256: str,
) -> str | None:
    if run.mode is not RunMode.TRAINING or run.policy_id != "heuristic-v0":
        return "not-heuristic-training"
    if run.config.get("shadow_policy_id") != OFFICIAL_TRAINING_SHADOW_POLICY_ID:
        return "not-schema-v10-shadow"
    if run.config.get("shadow_model_id") != model_id:
        return "different-model"
    if run.config.get("shadow_weights_sha256") != weights_sha256:
        return "different-weights"
    if run.config.get("shadow_feature_schema_version") != DREAM_FEATURE_SCHEMA_VERSION:
        return "different-feature-schema"
    if run.client_sha256 != client_sha256:
        return "different-client"
    if run.status is RunStatus.RUNNING:
        return "run-still-running"
    return None


def _validate_terminal_evidence(
    run: RunRecord,
    events: tuple[RunEvent, ...],
    counts: _Counts,
) -> None:
    terminal_states: dict[str, MatchOutcome] = {}
    for event in events:
        state: GameState | None = None
        if event.kind is EventKind.GAME_STATE:
            try:
                state = GameState.model_validate(event.payload)
            except ValidationError:
                continue
        elif event.kind is EventKind.TRANSITION:
            try:
                transition = ActionTransition.model_validate(event.payload)
            except ValidationError:
                counts.add_error(run.run_id, event.sequence, "invalid action transition")
                continue
            if transition.before_state is not None and game_state_digest(
                transition.before_state
            ) != transition.before_state_digest:
                counts.add_error(run.run_id, event.sequence, "transition state digest mismatch")
                continue
            if transition.after_state is not None and game_state_digest(
                transition.after_state
            ) != transition.after_state_digest:
                counts.add_error(run.run_id, event.sequence, "transition state digest mismatch")
                continue
            state = transition.after_state
        if state is None:
            continue
        classified = classify_two_player_terminal(state)
        if classified is not None:
            terminal_states[classified.terminal_state_digest] = classified
    terminal_pairs: list[tuple[MatchOutcome, SparseTerminalReward]] = []
    for index, event in enumerate(events):
        if event.kind is not EventKind.MATCH_END:
            continue
        try:
            outcome = MatchOutcome.model_validate(event.payload)
        except ValidationError:
            classification = event.payload.get("classification")
            if (
                run.status is RunStatus.ABORTED
                and classification in OPERATIONAL_TERMINAL_CLASSIFICATIONS
            ):
                if index + 1 < len(events) and events[index + 1].kind is EventKind.REWARD:
                    counts.add_error(
                        run.run_id,
                        event.sequence,
                        "operational terminal candidate has an unexpected reward",
                    )
                continue
            counts.add_error(run.run_id, event.sequence, "invalid terminal outcome")
            continue
        if index + 1 >= len(events) or events[index + 1].kind is not EventKind.REWARD:
            counts.add_error(run.run_id, event.sequence, "terminal outcome has no adjacent reward")
            continue
        try:
            reward = SparseTerminalReward.model_validate(events[index + 1].payload)
        except ValidationError:
            counts.add_error(run.run_id, event.sequence, "invalid terminal reward")
            continue
        if (
            reward.result is not outcome.result
            or reward.terminal_state_digest != outcome.terminal_state_digest
        ):
            counts.add_error(run.run_id, event.sequence, "terminal outcome and reward disagree")
            continue
        classified = terminal_states.get(outcome.terminal_state_digest)
        if (
            classified is None
            or classified.result is not outcome.result
            or classified.self_player_name != outcome.self_player_name
            or classified.opponent_player_names != outcome.opponent_player_names
        ):
            counts.add_error(
                run.run_id,
                event.sequence,
                "terminal outcome has no matching normalized terminal state",
            )
            continue
        terminal_pairs.append((outcome, reward))

    if run.status is RunStatus.FAILED:
        counts.failed_runs += 1
    if run.status is RunStatus.ABORTED:
        counts.operational_aborts += 1
    if run.status is not RunStatus.COMPLETED:
        if terminal_pairs:
            counts.add_error(run.run_id, 0, "incomplete run contains a terminal outcome")
        return
    if len(terminal_pairs) != 1:
        counts.add_error(run.run_id, 0, "completed run must contain one terminal outcome")
        return
    outcome, reward = terminal_pairs[0]
    summary = run.outcome or {}
    if (
        summary.get("reason") != "classified_terminal"
        or summary.get("result") != outcome.result.value
        or summary.get("reward") != reward.value
        or summary.get("terminal_state_digest") != outcome.terminal_state_digest
    ):
        counts.add_error(run.run_id, 0, "completed run summary disagrees with terminal evidence")
        return
    counts.completed_games += 1
    counts.outcomes[outcome.result.value] += 1


def _evaluate_state_group(
    events: tuple[RunEvent, ...],
    index: int,
    counts: _Counts,
    *,
    run_id: str,
    model_id: str,
    weights_sha256: str,
) -> int | None:
    event = events[index]
    if (
        index < 1
        or index + 3 >= len(events)
        or events[index - 1].kind is not EventKind.OBSERVATION
        or events[index + 1].kind is not EventKind.LEGAL_ACTIONS
        or events[index + 2].kind is not EventKind.DECISION
        or events[index + 3].kind is not EventKind.EVIDENCE
    ):
        counts.add_error(run_id, event.sequence, "malformed Training policy event group")
        return None
    try:
        ScreenObservation.model_validate(events[index - 1].payload)
        state = GameState.model_validate(event.payload)
        legal = LegalActionSet.model_validate(events[index + 1].payload)
        behavior = PolicyDecision.model_validate(events[index + 2].payload)
        evidence = TrainingShadowEvidence.model_validate(events[index + 3].payload)
    except ValidationError:
        counts.add_error(run_id, event.sequence, "invalid Training policy event payload")
        return None
    digest = game_state_digest(state)
    if {legal.state_digest, behavior.state_digest, evidence.state_digest} != {digest}:
        counts.add_error(run_id, event.sequence, "state group has inconsistent digests")
        return events[index + 3].sequence
    if behavior.policy_id != "heuristic-v0":
        counts.add_error(run_id, event.sequence, "behavior decision has the wrong policy")
        return events[index + 3].sequence
    if (
        evidence.model_id != model_id
        or evidence.model_weights_sha256 != weights_sha256
        or evidence.policy_id != OFFICIAL_TRAINING_SHADOW_POLICY_ID
    ):
        counts.add_error(run_id, event.sequence, "shadow evidence has the wrong model identity")
        return events[index + 3].sequence
    if (
        evidence.behavior_action_id != behavior.chosen_action_id
        or evidence.behavior_executable != behavior.executable
    ):
        counts.add_error(run_id, event.sequence, "shadow evidence disagrees with behavior")
        return events[index + 3].sequence
    legal_ids = {action.action_id for action in legal.actions}
    if behavior.chosen_action_id not in legal_ids:
        counts.add_error(run_id, event.sequence, "behavior action is outside the legal set")
        return events[index + 3].sequence
    if evidence.proposed_action_id is not None and evidence.proposed_action_id not in legal_ids:
        counts.add_error(run_id, event.sequence, "shadow proposal is outside the legal set")
        return events[index + 3].sequence
    if not set(evidence.scores).issubset(legal_ids):
        counts.add_error(run_id, event.sequence, "shadow scores name actions outside the legal set")
        return events[index + 3].sequence
    if evidence.covered:
        if (
            evidence.proposed_action_id is None
            or evidence.agreement is None
            or evidence.abstain_reason is not None
            or evidence.proposed_action_id not in evidence.scores
        ):
            counts.add_error(run_id, event.sequence, "covered shadow evidence is incomplete")
            return events[index + 3].sequence
        if evidence.agreement != (
            evidence.proposed_action_id == evidence.behavior_action_id
        ):
            counts.add_error(run_id, event.sequence, "shadow agreement flag is inconsistent")
            return events[index + 3].sequence
    elif (
        evidence.proposed_action_id is not None
        or evidence.agreement is not None
        or evidence.abstain_reason is None
    ):
        counts.add_error(run_id, event.sequence, "shadow abstention is inconsistent")
        return events[index + 3].sequence

    counts.shadow_samples += 1
    if not behavior.executable:
        return events[index + 3].sequence
    counts.eligible_decisions += 1
    hidden = any(not player.stats_visible for player in state.players)
    if hidden:
        counts.visibility_abstentions += 1
        if evidence.covered or evidence.abstain_reason != VISIBILITY_ABSTAIN_REASON:
            counts.add_error(run_id, event.sequence, "hidden state did not fail closed")
        return events[index + 3].sequence

    counts.exact_view_opportunities += 1
    strata = _status_strata(state)
    counts.status_opportunities.update(strata)
    if not evidence.covered:
        counts.encoding_gaps[evidence.abstain_reason or "unspecified"] += 1
        return events[index + 3].sequence
    counts.exact_view_proposals += 1
    counts.status_proposals.update(strata)
    if evidence.agreement:
        counts.agreements += 1
    if evidence.proposed_action_id is not None:
        counts.proposal_families[_action_family(evidence.proposed_action_id)] += 1
    return events[index + 3].sequence


def _evaluate_run(
    run: RunRecord,
    events: tuple[RunEvent, ...],
    counts: _Counts,
    *,
    model_id: str,
    weights_sha256: str,
) -> None:
    consumed_evidence: set[int] = set()
    for index, event in enumerate(events):
        if event.kind is EventKind.GAME_STATE:
            sequence = _evaluate_state_group(
                events,
                index,
                counts,
                run_id=run.run_id,
                model_id=model_id,
                weights_sha256=weights_sha256,
            )
            if sequence is not None:
                consumed_evidence.add(sequence)
    for event in events:
        if (
            event.kind is EventKind.EVIDENCE
            and event.payload.get("evidence_type") == "official_training_shadow"
            and event.sequence not in consumed_evidence
        ):
            counts.add_error(run.run_id, event.sequence, "orphaned Training shadow evidence")
    _validate_terminal_evidence(run, events, counts)


def _validate_native_evaluation(
    report: SimulationEvaluationReport,
    *,
    manifest_simulation: SimulationMetadata,
    model_id: str,
    weights_sha256: str,
    parent_model_id: str,
    parent_weights_sha256: str,
) -> None:
    if (
        report.candidate_model_id != model_id
        or report.candidate_weights_sha256 != weights_sha256
        or report.parent_model_id != parent_model_id
        or report.parent_weights_sha256 != parent_weights_sha256
    ):
        raise TrainingShadowReadinessError("native evaluation has inconsistent model lineage")
    if report.simulation != manifest_simulation or report.config.ruleset != "dream-resource-hand":
        raise TrainingShadowReadinessError("native evaluation uses a different Dream contract")
    expected_matchups = {
        ("model", parent_model_id, "paired-superiority"),
        ("heuristic", DREAM_RESOURCE_HEURISTIC_POLICY_ID, "paired-noninferiority"),
    }
    observed_matchups = {
        (matchup.opponent_kind, matchup.opponent_id, matchup.gate_kind)
        for matchup in report.matchups
    }
    if observed_matchups != expected_matchups:
        raise TrainingShadowReadinessError("native evaluation uses different gate opponents")
    for matchup in report.matchups:
        if (
            matchup.games_per_seat != report.config.games_per_seat
            or matchup.completed_games + matchup.incomplete_games
            != 2 * matchup.games_per_seat
            or matchup.candidate_wins
            + matchup.candidate_losses
            + matchup.candidate_draws
            != matchup.completed_games
            or matchup.candidate_won_both_pairs
            + matchup.candidate_split_pairs
            + matchup.candidate_lost_both_pairs
            + matchup.incomplete_pairs
            != matchup.games_per_seat
        ):
            raise TrainingShadowReadinessError("native evaluation counts are inconsistent")
    derived_passed = not report.gate_reasons and all(
        matchup.passed for matchup in report.matchups
    )
    if report.passed != derived_passed:
        raise TrainingShadowReadinessError("native evaluation verdict is inconsistent")


def _matching_native_evaluations(
    directory: Path,
    *,
    model_id: str,
    weights_sha256: str,
    parent_model_id: str,
    parent_weights_sha256: str,
    manifest_simulation: SimulationMetadata,
) -> tuple[SimulationEvaluationReport, ...]:
    reports: list[SimulationEvaluationReport] = []
    for path in sorted(directory.glob("*.json")):
        try:
            report = SimulationEvaluationReport.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError):
            continue
        if (
            report.candidate_model_id != model_id
            or report.candidate_weights_sha256 != weights_sha256
        ):
            continue
        _validate_native_evaluation(
            report,
            manifest_simulation=manifest_simulation,
            model_id=model_id,
            weights_sha256=weights_sha256,
            parent_model_id=parent_model_id,
            parent_weights_sha256=parent_weights_sha256,
        )
        reports.append(report)
    identities = {(report.evaluation_id, report.input_sha256) for report in reports}
    seeds = {report.config.seed for report in reports}
    if len(identities) != len(reports) or len(seeds) != len(reports):
        raise TrainingShadowReadinessError("native evaluations are not independent")
    return tuple(sorted(reports, key=lambda report: report.evaluation_id))


def _input_digest(
    *,
    model_id: str,
    weights_sha256: str,
    config: TrainingShadowReadinessConfig,
    native_reports: tuple[SimulationEvaluationReport, ...],
    evidence: tuple[tuple[RunRecord, tuple[RunEvent, ...]], ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "schema_version": 1,
                "gate_id": TRAINING_SHADOW_READINESS_GATE_ID,
                "model_id": model_id,
                "weights_sha256": weights_sha256,
                "config": config.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    for report in native_reports:
        digest.update(report.model_dump_json().encode())
    for run, events in evidence:
        digest.update(run.model_dump_json().encode())
        for event in events:
            digest.update(event.model_dump_json().encode())
    return digest.hexdigest()


def _write_report(report: TrainingShadowReadinessReport, directory: Path) -> Path:
    prepare_private_directory(directory)
    destination = directory / f"{report.evaluation_id}.json"
    temporary = directory / f".{report.evaluation_id}.json.tmp"
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination


def evaluate_training_shadow_readiness(
    *,
    candidate_model_directory: Path,
    bible_snapshot_path: Path,
    native_evaluation_directory: Path,
    database_path: Path,
    evaluation_directory: Path,
    config: TrainingShadowReadinessConfig,
) -> StoredTrainingShadowReadiness:
    """Audit immutable official-CPU shadow evidence without granting control."""

    try:
        snapshot = BibleSnapshot.model_validate_json(
            bible_snapshot_path.read_text(encoding="utf-8")
        )
        policy = OfficialTrainingShadowPolicy(candidate_model_directory, snapshot)
    except (OSError, ValueError) as error:
        raise TrainingShadowReadinessError("candidate or Bible snapshot is unreadable") from error
    manifest = policy.manifest
    if manifest.status is not ModelStatus.CANDIDATE or manifest.parent_model_id is None:
        raise TrainingShadowReadinessError("readiness gate requires a candidate with lineage")
    try:
        parent, _model = load_model(candidate_model_directory.parent / manifest.parent_model_id)
        manifest_simulation = SimulationMetadata.model_validate(
            manifest.training_context["simulation"]
        )
    except (KeyError, OSError, ValueError) as error:
        raise TrainingShadowReadinessError("candidate lineage is unreadable") from error
    if (
        manifest_simulation.ruleset_id != DREAM_RULESET_ID
        or manifest_simulation.observation_schema_version != DREAM_FEATURE_SCHEMA_VERSION
    ):
        raise TrainingShadowReadinessError("candidate does not use the schema-v10 Dream contract")
    native_reports = _matching_native_evaluations(
        native_evaluation_directory,
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        parent_model_id=parent.model_id,
        parent_weights_sha256=parent.weights_sha256,
        manifest_simulation=manifest_simulation,
    )
    if not database_path.is_file():
        raise TrainingShadowReadinessError("Training shadow database does not exist")

    store = RunStore(database_path)
    runs = store.all_runs()
    excluded: Counter[str] = Counter()
    counts = _Counts()
    evidence: list[tuple[RunRecord, tuple[RunEvent, ...]]] = []
    shadow_runs_seen = 0
    for run in runs:
        if run.config.get("shadow_policy_id") == OFFICIAL_TRAINING_SHADOW_POLICY_ID:
            shadow_runs_seen += 1
        reason = _matching_run_reason(
            run,
            model_id=manifest.model_id,
            weights_sha256=manifest.weights_sha256,
            client_sha256=manifest.client_sha256,
        )
        if reason is not None:
            excluded[reason] += 1
            continue
        events = store.events(run.run_id)
        if not any(
            event.kind is EventKind.EVIDENCE
            and event.payload.get("evidence_type") == "official_training_shadow"
            for event in events
        ):
            excluded["no-shadow-evidence"] += 1
            continue
        _evaluate_run(
            run,
            events,
            counts,
            model_id=manifest.model_id,
            weights_sha256=manifest.weights_sha256,
        )
        evidence.append((run, events))

    exact_coverage = _rate(counts.exact_view_proposals, counts.exact_view_opportunities)
    agreement = _rate(counts.agreements, counts.exact_view_proposals)
    completion = _rate(counts.completed_games, len(evidence))
    metrics = TrainingShadowReadinessMetrics(
        runs_scanned=len(runs),
        shadow_runs_seen=shadow_runs_seen,
        matching_runs=len(evidence),
        excluded_runs=dict(sorted(excluded.items())),
        completed_games=counts.completed_games,
        incomplete_games=max(0, len(evidence) - counts.completed_games),
        failed_runs=counts.failed_runs,
        operational_aborts=counts.operational_aborts,
        behavior_wins=counts.outcomes[MatchResult.WIN.value],
        behavior_losses=counts.outcomes[MatchResult.LOSS.value],
        behavior_draws=counts.outcomes[MatchResult.DRAW.value],
        completion_rate=completion,
        completion_lower_bound=wilson_lower_bound(
            counts.completed_games,
            len(evidence),
            config.confidence_z,
        ),
        shadow_samples=counts.shadow_samples,
        eligible_decisions=counts.eligible_decisions,
        visibility_abstentions=counts.visibility_abstentions,
        exact_view_opportunities=counts.exact_view_opportunities,
        exact_view_proposals=counts.exact_view_proposals,
        encoding_gaps=sum(counts.encoding_gaps.values()),
        encoding_gap_reasons=dict(sorted(counts.encoding_gaps.items())),
        exact_view_coverage=exact_coverage,
        exact_view_coverage_lower_bound=wilson_lower_bound(
            counts.exact_view_proposals,
            counts.exact_view_opportunities,
            config.confidence_z,
        ),
        behavior_agreements=counts.agreements,
        behavior_agreement=agreement,
        behavior_agreement_lower_bound=wilson_lower_bound(
            counts.agreements,
            counts.exact_view_proposals,
            config.confidence_z,
        ),
        status_opportunities={name: counts.status_opportunities[name] for name in STATUS_STRATA},
        status_proposals={name: counts.status_proposals[name] for name in STATUS_STRATA},
        proposal_action_families={
            name: counts.proposal_families[name] for name in REQUIRED_ACTION_FAMILIES
        },
        evidence_error_count=len(counts.errors),
        evidence_errors=tuple(counts.errors[:20]),
    )

    reasons: list[str] = []
    passing_native = sum(report.passed for report in native_reports)
    if passing_native < config.minimum_native_evaluations:
        reasons.append(
            f"passing native evaluations {passing_native} are below "
            f"{config.minimum_native_evaluations}"
        )
    if metrics.matching_runs == 0:
        reasons.append("no official Training shadow runs match this candidate")
    if metrics.failed_runs > config.maximum_failed_runs:
        reasons.append(
            f"failed runs {metrics.failed_runs} exceed {config.maximum_failed_runs}"
        )
    if metrics.evidence_error_count:
        reasons.append(f"{metrics.evidence_error_count} shadow evidence integrity errors found")
    if metrics.completed_games < config.minimum_completed_games:
        reasons.append(
            f"completed games {metrics.completed_games} are below "
            f"{config.minimum_completed_games}"
        )
    if metrics.completion_lower_bound < config.minimum_completion_lower_bound:
        reasons.append(
            f"completion lower bound {metrics.completion_lower_bound:.4f} is below "
            f"{config.minimum_completion_lower_bound:.4f}"
        )
    if metrics.exact_view_opportunities < config.minimum_exact_view_opportunities:
        reasons.append(
            f"exact-view opportunities {metrics.exact_view_opportunities} are below "
            f"{config.minimum_exact_view_opportunities}"
        )
    if (
        metrics.exact_view_coverage_lower_bound
        < config.minimum_exact_view_coverage_lower_bound
    ):
        reasons.append(
            f"exact-view coverage lower bound "
            f"{metrics.exact_view_coverage_lower_bound:.4f} is below "
            f"{config.minimum_exact_view_coverage_lower_bound:.4f}"
        )
    if metrics.encoding_gaps > config.maximum_encoding_gaps:
        reasons.append(
            f"encoding gaps {metrics.encoding_gaps} exceed {config.maximum_encoding_gaps}"
        )
    status_minimums = {
        "illness": config.minimum_illness_opportunities,
        "flash": config.minimum_flash_opportunities,
        "dark-cloud": config.minimum_dark_cloud_opportunities,
        "dream": config.minimum_dream_opportunities,
    }
    for status, minimum in status_minimums.items():
        if metrics.status_opportunities[status] < minimum:
            reasons.append(
                f"{status} opportunities {metrics.status_opportunities[status]} are below "
                f"{minimum}"
            )
    if metrics.visibility_abstentions < config.minimum_visibility_abstentions:
        reasons.append(
            f"visibility abstentions {metrics.visibility_abstentions} are below "
            f"{config.minimum_visibility_abstentions}"
        )
    for family in REQUIRED_ACTION_FAMILIES:
        observed = metrics.proposal_action_families[family]
        if observed < config.minimum_each_action_family:
            reasons.append(
                f"{family} proposals {observed} are below "
                f"{config.minimum_each_action_family}"
            )

    sorted_evidence = tuple(
        sorted(evidence, key=lambda item: (item[0].started_at, item[0].run_id))
    )
    input_sha256 = _input_digest(
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        config=config,
        native_reports=native_reports,
        evidence=sorted_evidence,
    )
    report = TrainingShadowReadinessReport(
        evaluation_id=str(uuid4()),
        created_at=datetime.now(UTC),
        candidate_model_id=manifest.model_id,
        candidate_weights_sha256=manifest.weights_sha256,
        native_evaluation_ids=tuple(report.evaluation_id for report in native_reports),
        native_evaluation_input_sha256s=tuple(
            report.input_sha256 for report in native_reports
        ),
        source_database=str(database_path),
        native_evaluation_directory=str(native_evaluation_directory),
        input_sha256=input_sha256,
        run_ids=tuple(run.run_id for run, _events in sorted_evidence),
        config=config,
        metrics=metrics,
        passed=not reasons,
        ready_for_guarded_intervention=not reasons,
        gate_reasons=tuple(reasons),
    )
    destination = _write_report(report, evaluation_directory)
    return StoredTrainingShadowReadiness(
        report_path=str(destination),
        report=report,
    )
