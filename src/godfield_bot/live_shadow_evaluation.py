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

from godfield_bot.api_game import (
    ApiGameState,
    ApiLegalActionSet,
    ApiPhase,
    ApiPolicyDecision,
    api_game_state_digest,
)
from godfield_bot.api_neural import API_RESOURCE_SHADOW_POLICY_ID, RESOURCE_RULESET_ID
from godfield_bot.api_runtime import ApiPolicyName, ApiPrivateMatchOutcome
from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.outcome import MatchResult, SparseTerminalReward
from godfield_bot.domain.run import EventKind, RunEvent, RunMode, RunRecord, RunStatus
from godfield_bot.features import RESOURCE_FEATURE_SCHEMA_VERSION
from godfield_bot.model_registry import ModelManifest, ModelStatus, load_model
from godfield_bot.run_store import RunStore
from godfield_bot.simulation_evaluation import (
    SimulationEvaluationReport,
    wilson_lower_bound,
)
from godfield_bot.simulation_policy import RESOURCE_HEURISTIC_POLICY_ID

LIVE_RESOURCE_SHADOW_GATE_ID: Final = "live-resource-shadow-readiness-v3"
RESOURCE_KINDS: Final = ("hp-sundry", "mp-sundry", "attack-miracle", "hp-miracle")


class LiveShadowEvaluationError(RuntimeError):
    """Raised when recorded live-shadow evidence cannot be evaluated safely."""


class LiveShadowEvaluationConfig(BaseModel):
    minimum_completed_games: int = Field(default=20, ge=1, le=100_000)
    minimum_turn_opportunities: int = Field(default=40, ge=1, le=1_000_000)
    minimum_defense_opportunities: int = Field(default=20, ge=1, le=1_000_000)
    minimum_resource_opportunities: int = Field(default=12, ge=1, le=1_000_000)
    minimum_each_resource_kind: int = Field(default=1, ge=1, le=1_000_000)
    minimum_completion_lower_bound: float = Field(default=0.75, ge=0, le=1)
    minimum_coverage_lower_bound: float = Field(default=0.50, ge=0, le=1)
    minimum_agreement_lower_bound: float = Field(default=0.60, ge=0, le=1)
    minimum_resource_coverage_lower_bound: float = Field(default=0.50, ge=0, le=1)
    minimum_resource_agreement_lower_bound: float = Field(default=0.50, ge=0, le=1)
    maximum_failed_runs: int = Field(default=0, ge=0, le=100_000)
    maximum_operational_aborts: int = Field(default=0, ge=0, le=100_000)
    confidence_z: float = Field(default=1.96, gt=0, le=10)


class LiveShadowMetrics(BaseModel):
    runs_scanned: int = Field(ge=0)
    neural_shadow_runs_seen: int = Field(ge=0)
    matching_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    operational_abort_runs: int = Field(ge=0)
    excluded_runs: dict[str, int]
    states_seen: int = Field(ge=0)
    decision_pairs: int = Field(ge=0)
    matches_started: int = Field(ge=0)
    completed_games: int = Field(ge=0)
    incomplete_games: int = Field(ge=0)
    behavior_wins: int = Field(ge=0)
    behavior_losses: int = Field(ge=0)
    behavior_draws: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=1)
    completion_lower_bound: float = Field(ge=0, le=1)
    turn_opportunities: int = Field(ge=0)
    defense_opportunities: int = Field(ge=0)
    candidate_proposals: int = Field(ge=0)
    proposal_coverage: float = Field(ge=0, le=1)
    proposal_coverage_lower_bound: float = Field(ge=0, le=1)
    behavior_agreements: int = Field(ge=0)
    behavior_agreement: float = Field(ge=0, le=1)
    behavior_agreement_lower_bound: float = Field(ge=0, le=1)
    resource_opportunities: int = Field(ge=0)
    resource_kind_opportunities: dict[str, int]
    resource_proposals: int = Field(ge=0)
    resource_action_proposals: int = Field(ge=0)
    resource_coverage: float = Field(ge=0, le=1)
    resource_coverage_lower_bound: float = Field(ge=0, le=1)
    resource_agreements: int = Field(ge=0)
    resource_agreement: float = Field(ge=0, le=1)
    resource_agreement_lower_bound: float = Field(ge=0, le=1)
    evidence_error_count: int = Field(ge=0)
    evidence_errors: tuple[str, ...]


class LiveShadowEvaluationReport(BaseModel):
    schema_version: Literal[3] = 3
    evaluation_id: str
    gate_id: Literal["live-resource-shadow-readiness-v3"] = LIVE_RESOURCE_SHADOW_GATE_ID
    created_at: datetime
    candidate_model_id: str
    candidate_weights_sha256: str
    shadow_policy_id: Literal["api-resource-neural-shadow-v2"] = "api-resource-neural-shadow-v2"
    behavior_policy_id: Literal["api-combo-utility-heuristic-v3"] = (
        "api-combo-utility-heuristic-v3"
    )
    feature_schema_version: Literal[5] = 5
    native_evaluation_id: str
    native_evaluation_input_sha256: str
    source_database: str
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_ids: tuple[str, ...]
    config: LiveShadowEvaluationConfig
    metrics: LiveShadowMetrics
    passed: bool
    ready_for_controlled_trial: bool
    gate_reasons: tuple[str, ...]
    promotion_eligible: Literal[False] = False


class StoredLiveShadowEvaluation(BaseModel):
    report_path: str
    report: LiveShadowEvaluationReport


@dataclass
class _Counts:
    states_seen: int = 0
    decision_pairs: int = 0
    matches_started: int = 0
    completed_games: int = 0
    outcomes: Counter[str] = field(default_factory=Counter)
    turn_opportunities: int = 0
    defense_opportunities: int = 0
    candidate_proposals: int = 0
    agreements: int = 0
    resource_opportunities: int = 0
    resource_kinds: Counter[str] = field(default_factory=Counter)
    resource_proposals: int = 0
    resource_action_proposals: int = 0
    resource_agreements: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, run_id: str, sequence: int, reason: str) -> None:
        self.errors.append(f"{run_id}:{sequence}: {reason}")


def _rate(successes: int, trials: int) -> float:
    return successes / trials if trials else 0.0


def _resource_kinds(state: ApiGameState, legal: ApiLegalActionSet) -> set[str]:
    items = {item.instance_id: item for item in state.hand if item.instance_id is not None}
    me = next(player for player in state.players if player.is_self)
    kinds: set[str] = set()
    for action in legal.actions:
        if action.action_id.startswith("miracle-attack:"):
            kinds.add("attack-miracle")
            continue
        if not action.action_id.startswith("utility:") or not action.item_instance_ids:
            continue
        item = items.get(action.item_instance_ids[0])
        if action.action_id.startswith("utility:boostMP:"):
            if me.mp < 100:
                kinds.add("mp-sundry")
        elif item is not None and item.category == "miracles":
            if me.hp < 100:
                kinds.add("hp-miracle")
        elif me.hp < 100:
            kinds.add("hp-sundry")
    return kinds


def _is_resource_action(action_id: str | None) -> bool:
    return action_id is not None and action_id.startswith(("utility:", "miracle-attack:"))


def _matching_run_reason(run: RunRecord, *, model_id: str, weights_sha256: str) -> str | None:
    if run.mode is not RunMode.PRIVATE or run.policy_id != ApiPolicyName.NEURAL_SHADOW.value:
        return "not-neural-shadow"
    if run.config.get("shadow_model_id") != model_id:
        return "different-model"
    if run.config.get("shadow_model_weights_sha256") != weights_sha256:
        return "different-weights"
    if run.model_id != model_id:
        return "model-not-attached-to-run"
    if run.config.get("shadow_policy_id") != API_RESOURCE_SHADOW_POLICY_ID:
        return "legacy-or-different-adapter"
    if run.config.get("shadow_feature_schema_version") != RESOURCE_FEATURE_SCHEMA_VERSION:
        return "different-feature-schema"
    if run.config.get("behavior_policy") != ApiPolicyName.TACTICAL_HEURISTIC.value:
        return "different-behavior-policy"
    if run.status is RunStatus.RUNNING:
        return "run-still-running"
    return None


def _validate_terminal_pair(
    events: tuple[RunEvent, ...],
    index: int,
    counts: _Counts,
    run_id: str,
) -> bool:
    event = events[index]
    try:
        outcome = ApiPrivateMatchOutcome.model_validate(event.payload)
    except ValidationError:
        counts.add_error(run_id, event.sequence, "invalid or unclassified terminal outcome")
        return False
    if index + 1 >= len(events) or events[index + 1].kind is not EventKind.REWARD:
        counts.add_error(run_id, event.sequence, "terminal outcome has no adjacent reward")
        return False
    reward_event = events[index + 1]
    try:
        reward = SparseTerminalReward.model_validate(reward_event.payload)
    except ValidationError:
        counts.add_error(run_id, reward_event.sequence, "invalid terminal reward")
        return False
    if (
        reward.result is not outcome.result
        or reward.terminal_state_digest != outcome.terminal_state_digest
    ):
        counts.add_error(run_id, reward_event.sequence, "terminal outcome and reward disagree")
        return False
    counts.outcomes[outcome.result.value] += 1
    return True


def _evaluate_state_group(
    events: tuple[RunEvent, ...],
    index: int,
    counts: _Counts,
    *,
    run_id: str,
    model_id: str,
    weights_sha256: str,
) -> None:
    event = events[index]
    counts.states_seen += 1
    try:
        state = ApiGameState.model_validate(event.payload)
    except ValidationError:
        counts.add_error(run_id, event.sequence, "invalid normalized API state")
        return
    if index + 1 >= len(events) or events[index + 1].kind is not EventKind.LEGAL_ACTIONS:
        counts.add_error(run_id, event.sequence, "state has no adjacent legal-action set")
        return
    legal_event = events[index + 1]
    try:
        legal = ApiLegalActionSet.model_validate(legal_event.payload)
    except ValidationError:
        counts.add_error(run_id, legal_event.sequence, "invalid legal-action set")
        return
    if legal.state_digest != api_game_state_digest(state):
        counts.add_error(run_id, legal_event.sequence, "legal-action digest is inconsistent")
        return

    decision_events = []
    cursor = index + 2
    while cursor < len(events) and events[cursor].kind is EventKind.DECISION:
        decision_events.append(events[cursor])
        cursor += 1
    if len(decision_events) != 2:
        counts.add_error(run_id, event.sequence, "state does not have exactly two decisions")
        return
    decisions: list[ApiPolicyDecision] = []
    for decision_event in decision_events:
        try:
            decisions.append(ApiPolicyDecision.model_validate(decision_event.payload))
        except ValidationError:
            counts.add_error(run_id, decision_event.sequence, "invalid API decision")
    shadow = [
        decision for decision in decisions if decision.policy_id == API_RESOURCE_SHADOW_POLICY_ID
    ]
    behavior = [
        decision
        for decision in decisions
        if decision.policy_id == ApiPolicyName.TACTICAL_HEURISTIC.value
    ]
    if len(shadow) != 1 or len(behavior) != 1:
        counts.add_error(run_id, event.sequence, "state does not have one shadow/behavior pair")
        return
    if [decision.policy_id for decision in decisions] != [
        API_RESOURCE_SHADOW_POLICY_ID,
        ApiPolicyName.TACTICAL_HEURISTIC.value,
    ]:
        counts.add_error(run_id, event.sequence, "decision pair is in the wrong order")
        return
    candidate = shadow[0]
    baseline = behavior[0]
    if candidate.state_digest != legal.state_digest or baseline.state_digest != legal.state_digest:
        counts.add_error(run_id, event.sequence, "decision pair has a mismatched state digest")
        return
    if candidate.executable:
        counts.add_error(run_id, event.sequence, "shadow decision was marked executable")
        return
    if candidate.model_id != model_id or candidate.model_weights_sha256 != weights_sha256:
        counts.add_error(run_id, event.sequence, "shadow decision has the wrong model identity")
        return
    if candidate.chosen_action_id is not None and not candidate.selection_action_indices:
        counts.add_error(run_id, event.sequence, "shadow proposal has no neural action trace")
        return
    if candidate.chosen_action_id is None and candidate.selection_action_indices:
        counts.add_error(run_id, event.sequence, "shadow abstention contains an action trace")
        return
    legal_ids = {action.action_id for action in legal.actions}
    if candidate.chosen_action_id is not None and candidate.chosen_action_id not in legal_ids:
        counts.add_error(run_id, event.sequence, "shadow proposal is outside the legal set")
        return
    if baseline.chosen_action_id is not None and baseline.chosen_action_id not in legal_ids:
        counts.add_error(run_id, event.sequence, "behavior action is outside the legal set")
        return
    counts.decision_pairs += 1

    actionable = (
        len(state.players) == 2
        and not state.has_active_curses
        and state.awaiting_player_id == state.self_player_id
        and state.phase in {ApiPhase.TURN, ApiPhase.DEFENSE}
    )
    if not actionable:
        return
    if state.phase is ApiPhase.TURN:
        counts.turn_opportunities += 1
    else:
        counts.defense_opportunities += 1
    if candidate.chosen_action_id is not None:
        counts.candidate_proposals += 1
        if candidate.chosen_action_id == baseline.chosen_action_id:
            counts.agreements += 1

    kinds = _resource_kinds(state, legal)
    if not kinds:
        return
    counts.resource_opportunities += 1
    counts.resource_kinds.update(kinds)
    if candidate.chosen_action_id is not None:
        counts.resource_proposals += 1
        if _is_resource_action(candidate.chosen_action_id):
            counts.resource_action_proposals += 1
        if candidate.chosen_action_id == baseline.chosen_action_id:
            counts.resource_agreements += 1


def _evaluate_run(
    store: RunStore,
    run: RunRecord,
    counts: _Counts,
    *,
    model_id: str,
    weights_sha256: str,
) -> tuple[RunEvent, ...]:
    events = store.events(run.run_id)
    match_open = False
    for index, event in enumerate(events):
        if event.kind is EventKind.GAME_STATE:
            if not match_open:
                counts.matches_started += 1
                match_open = True
            _evaluate_state_group(
                events,
                index,
                counts,
                run_id=run.run_id,
                model_id=model_id,
                weights_sha256=weights_sha256,
            )
        elif event.kind is EventKind.MATCH_END:
            if not match_open:
                counts.add_error(run.run_id, event.sequence, "terminal event has no open match")
            elif _validate_terminal_pair(events, index, counts, run.run_id):
                counts.completed_games += 1
            match_open = False
        elif event.kind is EventKind.OBSERVATION and match_open:
            match_open = False
    return events


def _evidence_digest(
    *,
    model_id: str,
    weights_sha256: str,
    native_report: SimulationEvaluationReport,
    config: LiveShadowEvaluationConfig,
    evidence: tuple[tuple[RunRecord, tuple[RunEvent, ...]], ...],
) -> str:
    digest = hashlib.sha256()
    header = {
        "schema_version": 3,
        "gate_id": LIVE_RESOURCE_SHADOW_GATE_ID,
        "model_id": model_id,
        "weights_sha256": weights_sha256,
        "native_evaluation": native_report.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
    }
    digest.update(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
    for run, events in evidence:
        digest.update(run.model_dump_json().encode())
        for event in events:
            digest.update(event.model_dump_json().encode())
    return digest.hexdigest()


def _write_report(report: LiveShadowEvaluationReport, directory: Path) -> Path:
    prepare_private_directory(directory)
    destination = directory / f"{report.evaluation_id}.json"
    temporary = directory / f".{report.evaluation_id}.json.tmp"
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination


def _validate_native_report(
    *,
    manifest: ModelManifest,
    candidate_model_directory: Path,
    report: SimulationEvaluationReport,
) -> None:
    if manifest.parent_model_id is None:
        raise LiveShadowEvaluationError("live resource gate requires candidate lineage")
    try:
        parent, _model = load_model(candidate_model_directory.parent / manifest.parent_model_id)
    except (OSError, ValueError) as error:
        raise LiveShadowEvaluationError("candidate parent model is unreadable") from error
    if parent.model_id != manifest.parent_model_id:
        raise LiveShadowEvaluationError("candidate parent identity is inconsistent")
    if (
        report.candidate_model_id != manifest.model_id
        or report.candidate_weights_sha256 != manifest.weights_sha256
    ):
        raise LiveShadowEvaluationError("native evaluation belongs to a different candidate")
    if (
        report.parent_model_id != parent.model_id
        or report.parent_weights_sha256 != parent.weights_sha256
    ):
        raise LiveShadowEvaluationError("native evaluation uses a different parent model")
    try:
        trained_simulation = report.simulation.model_validate(
            manifest.training_context["simulation"]
        )
    except (KeyError, ValidationError) as error:
        raise LiveShadowEvaluationError(
            "candidate has no valid resource simulation contract"
        ) from error
    if report.simulation != trained_simulation or report.config.ruleset != "resource-hand":
        raise LiveShadowEvaluationError("native evaluation uses a different resource contract")

    expected_matchups = {
        ("model", parent.model_id, "paired-superiority"),
        ("heuristic", RESOURCE_HEURISTIC_POLICY_ID, "paired-noninferiority"),
    }
    observed_matchups = {
        (matchup.opponent_kind, matchup.opponent_id, matchup.gate_kind)
        for matchup in report.matchups
    }
    if observed_matchups != expected_matchups:
        raise LiveShadowEvaluationError("native evaluation uses different gate opponents")
    for matchup in report.matchups:
        if matchup.games_per_seat != report.config.games_per_seat or (
            matchup.completed_games + matchup.incomplete_games != 2 * matchup.games_per_seat
        ):
            raise LiveShadowEvaluationError("native evaluation game counts are inconsistent")
        if (
            matchup.candidate_wins + matchup.candidate_losses + matchup.candidate_draws
            != matchup.completed_games
        ):
            raise LiveShadowEvaluationError("native evaluation outcomes are inconsistent")
        if (
            matchup.candidate_won_both_pairs
            + matchup.candidate_split_pairs
            + matchup.candidate_lost_both_pairs
            + matchup.incomplete_pairs
            != matchup.games_per_seat
        ):
            raise LiveShadowEvaluationError("native evaluation pair counts are inconsistent")
    derived_passed = not report.gate_reasons and all(matchup.passed for matchup in report.matchups)
    if report.passed != derived_passed:
        raise LiveShadowEvaluationError("native evaluation verdict is inconsistent")


def evaluate_live_shadow_candidate(
    *,
    candidate_model_directory: Path,
    bible_snapshot_path: Path,
    native_evaluation_path: Path,
    database_path: Path,
    evaluation_directory: Path,
    config: LiveShadowEvaluationConfig,
) -> StoredLiveShadowEvaluation:
    """Evaluate immutable schema-v5 shadow evidence without granting live control."""

    try:
        from godfield_bot.api_neural import load_api_combo_shadow_policy

        policy = load_api_combo_shadow_policy(candidate_model_directory, bible_snapshot_path)
        native_report = SimulationEvaluationReport.model_validate_json(
            native_evaluation_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise LiveShadowEvaluationError("model or native evaluation is unreadable") from error
    manifest = policy.manifest
    if manifest.status is not ModelStatus.CANDIDATE:
        raise LiveShadowEvaluationError("live resource gate requires a candidate model")
    if manifest.feature_schema_version != RESOURCE_FEATURE_SCHEMA_VERSION:
        raise LiveShadowEvaluationError("live resource gate requires a schema-v5 candidate")
    if policy.policy_id != API_RESOURCE_SHADOW_POLICY_ID:
        raise LiveShadowEvaluationError("candidate does not use the resource shadow adapter")
    _validate_native_report(
        manifest=manifest,
        candidate_model_directory=candidate_model_directory,
        report=native_report,
    )
    if (
        native_report.simulation.observation_schema_version != RESOURCE_FEATURE_SCHEMA_VERSION
        or native_report.simulation.ruleset_id != RESOURCE_RULESET_ID
        or native_report.simulation.client_sha256 != manifest.client_sha256
        or native_report.simulation.vocabulary_sha256 != manifest.vocabulary_sha256
        or native_report.config.ruleset != "resource-hand"
    ):
        raise LiveShadowEvaluationError("native evaluation uses a different resource contract")

    if not database_path.is_file():
        raise LiveShadowEvaluationError("live shadow evidence database does not exist")
    store = RunStore(database_path)
    runs = store.all_runs()
    counts = _Counts()
    excluded: Counter[str] = Counter()
    evidence: list[tuple[RunRecord, tuple[RunEvent, ...]]] = []
    neural_runs_seen = 0
    failed_runs = 0
    operational_abort_runs = 0
    for run in runs:
        if run.mode is RunMode.PRIVATE and run.policy_id == ApiPolicyName.NEURAL_SHADOW.value:
            neural_runs_seen += 1
        reason = _matching_run_reason(
            run,
            model_id=manifest.model_id,
            weights_sha256=manifest.weights_sha256,
        )
        if reason is not None:
            excluded[reason] += 1
            continue
        if run.status is RunStatus.FAILED:
            failed_runs += 1
        if (
            run.status is RunStatus.ABORTED
            and run.outcome is not None
            and run.outcome.get("reason")
            in {
                "action_limit",
                "no_progress_limit",
                "unclassified_terminal",
                "unsupported_self_turn",
            }
        ):
            operational_abort_runs += 1
        completed_before = counts.completed_games
        events = _evaluate_run(
            store,
            run,
            counts,
            model_id=manifest.model_id,
            weights_sha256=manifest.weights_sha256,
        )
        run_completed_games = counts.completed_games - completed_before
        if run.status is RunStatus.ABORTED:
            recorded_games = run.outcome.get("games_completed") if run.outcome else None
            if recorded_games != run_completed_games:
                counts.add_error(run.run_id, 0, "run summary disagrees with terminal game count")
        elif run.status is RunStatus.COMPLETED:
            if (
                run_completed_games != 1
                or run.outcome is None
                or run.outcome.get("reason") != "classified_terminal"
            ):
                counts.add_error(run.run_id, 0, "completed run has an invalid terminal summary")
        evidence.append((run, events))

    opportunities = counts.turn_opportunities + counts.defense_opportunities
    incomplete_games = max(0, counts.matches_started - counts.completed_games)
    completion = _rate(counts.completed_games, counts.matches_started)
    coverage = _rate(counts.candidate_proposals, opportunities)
    agreement = _rate(counts.agreements, counts.candidate_proposals)
    resource_coverage = _rate(counts.resource_proposals, counts.resource_opportunities)
    resource_agreement = _rate(counts.resource_agreements, counts.resource_proposals)
    metrics = LiveShadowMetrics(
        runs_scanned=len(runs),
        neural_shadow_runs_seen=neural_runs_seen,
        matching_runs=len(evidence),
        failed_runs=failed_runs,
        operational_abort_runs=operational_abort_runs,
        excluded_runs=dict(sorted(excluded.items())),
        states_seen=counts.states_seen,
        decision_pairs=counts.decision_pairs,
        matches_started=counts.matches_started,
        completed_games=counts.completed_games,
        incomplete_games=incomplete_games,
        behavior_wins=counts.outcomes[MatchResult.WIN.value],
        behavior_losses=counts.outcomes[MatchResult.LOSS.value],
        behavior_draws=counts.outcomes[MatchResult.DRAW.value],
        completion_rate=completion,
        completion_lower_bound=wilson_lower_bound(
            counts.completed_games,
            counts.matches_started,
            config.confidence_z,
        ),
        turn_opportunities=counts.turn_opportunities,
        defense_opportunities=counts.defense_opportunities,
        candidate_proposals=counts.candidate_proposals,
        proposal_coverage=coverage,
        proposal_coverage_lower_bound=wilson_lower_bound(
            counts.candidate_proposals,
            opportunities,
            config.confidence_z,
        ),
        behavior_agreements=counts.agreements,
        behavior_agreement=agreement,
        behavior_agreement_lower_bound=wilson_lower_bound(
            counts.agreements,
            counts.candidate_proposals,
            config.confidence_z,
        ),
        resource_opportunities=counts.resource_opportunities,
        resource_kind_opportunities={kind: counts.resource_kinds[kind] for kind in RESOURCE_KINDS},
        resource_proposals=counts.resource_proposals,
        resource_action_proposals=counts.resource_action_proposals,
        resource_coverage=resource_coverage,
        resource_coverage_lower_bound=wilson_lower_bound(
            counts.resource_proposals,
            counts.resource_opportunities,
            config.confidence_z,
        ),
        resource_agreements=counts.resource_agreements,
        resource_agreement=resource_agreement,
        resource_agreement_lower_bound=wilson_lower_bound(
            counts.resource_agreements,
            counts.resource_proposals,
            config.confidence_z,
        ),
        evidence_error_count=len(counts.errors),
        evidence_errors=tuple(counts.errors[:20]),
    )

    reasons: list[str] = []
    if not native_report.passed or any(not matchup.passed for matchup in native_report.matchups):
        reasons.append("the required native resource evaluation did not pass")
    if metrics.matching_runs == 0:
        reasons.append("no schema-v5 resource shadow runs match this candidate")
    if metrics.failed_runs > config.maximum_failed_runs:
        reasons.append(
            f"{metrics.failed_runs} matching runs failed; maximum is {config.maximum_failed_runs}"
        )
    if metrics.operational_abort_runs > config.maximum_operational_aborts:
        reasons.append(
            f"{metrics.operational_abort_runs} matching runs ended in operational aborts; "
            f"maximum is {config.maximum_operational_aborts}"
        )
    if metrics.evidence_error_count:
        reasons.append(f"{metrics.evidence_error_count} shadow evidence integrity errors found")
    if metrics.completed_games < config.minimum_completed_games:
        reasons.append(
            f"completed games {metrics.completed_games} are below {config.minimum_completed_games}"
        )
    if metrics.completion_lower_bound < config.minimum_completion_lower_bound:
        reasons.append(
            f"completion lower bound {metrics.completion_lower_bound:.4f} is below "
            f"{config.minimum_completion_lower_bound:.4f}"
        )
    if metrics.turn_opportunities < config.minimum_turn_opportunities:
        reasons.append(
            f"turn opportunities {metrics.turn_opportunities} are below "
            f"{config.minimum_turn_opportunities}"
        )
    if metrics.defense_opportunities < config.minimum_defense_opportunities:
        reasons.append(
            f"defense opportunities {metrics.defense_opportunities} are below "
            f"{config.minimum_defense_opportunities}"
        )
    if metrics.proposal_coverage_lower_bound < config.minimum_coverage_lower_bound:
        reasons.append(
            f"proposal coverage lower bound {metrics.proposal_coverage_lower_bound:.4f} "
            f"is below {config.minimum_coverage_lower_bound:.4f}"
        )
    if metrics.behavior_agreement_lower_bound < config.minimum_agreement_lower_bound:
        reasons.append(
            f"behavior agreement lower bound {metrics.behavior_agreement_lower_bound:.4f} "
            f"is below {config.minimum_agreement_lower_bound:.4f}"
        )
    if metrics.resource_opportunities < config.minimum_resource_opportunities:
        reasons.append(
            f"resource opportunities {metrics.resource_opportunities} are below "
            f"{config.minimum_resource_opportunities}"
        )
    for kind in RESOURCE_KINDS:
        observed = metrics.resource_kind_opportunities[kind]
        if observed < config.minimum_each_resource_kind:
            reasons.append(
                f"{kind} opportunities {observed} are below {config.minimum_each_resource_kind}"
            )
    if metrics.resource_coverage_lower_bound < config.minimum_resource_coverage_lower_bound:
        reasons.append(
            f"resource coverage lower bound {metrics.resource_coverage_lower_bound:.4f} "
            f"is below {config.minimum_resource_coverage_lower_bound:.4f}"
        )
    if metrics.resource_agreement_lower_bound < config.minimum_resource_agreement_lower_bound:
        reasons.append(
            f"resource agreement lower bound {metrics.resource_agreement_lower_bound:.4f} "
            f"is below {config.minimum_resource_agreement_lower_bound:.4f}"
        )

    input_sha256 = _evidence_digest(
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        native_report=native_report,
        config=config,
        evidence=tuple(evidence),
    )
    report = LiveShadowEvaluationReport(
        evaluation_id=str(uuid4()),
        created_at=datetime.now(UTC),
        candidate_model_id=manifest.model_id,
        candidate_weights_sha256=manifest.weights_sha256,
        native_evaluation_id=native_report.evaluation_id,
        native_evaluation_input_sha256=native_report.input_sha256,
        source_database=str(database_path),
        input_sha256=input_sha256,
        run_ids=tuple(run.run_id for run, _events in evidence),
        config=config,
        metrics=metrics,
        passed=not reasons,
        ready_for_controlled_trial=not reasons,
        gate_reasons=tuple(reasons),
    )
    destination = _write_report(report, evaluation_directory)
    return StoredLiveShadowEvaluation(report_path=str(destination), report=report)
