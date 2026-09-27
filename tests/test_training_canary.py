from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from unittest.mock import Mock

import pytest

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
    DREAM_FEATURE_SCHEMA_VERSION,
    DREAM_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
)
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.model_registry import ModelManifest, ModelStatus, initialize_model
from godfield_bot.training_canary import (
    OFFICIAL_TRAINING_CANARY_POLICY_ID,
    OfficialTrainingCanaryPolicy,
    TrainingCanaryError,
)
from godfield_bot.training_shadow import DREAM_RULESET_ID, TrainingShadowEvidence
from godfield_bot.training_shadow_evaluation import TrainingShadowReadinessReport

SNAPSHOT = Path("data/snapshots/2026-09-20/bible.json")
BIBLE = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))


def _candidate(tmp_path: Path) -> tuple[Path, ModelManifest]:
    vocabulary = ArtifactVocabulary.from_snapshot(BIBLE)
    initialized = initialize_model(
        tmp_path / "models",
        vocabulary,
        client_sha256=BIBLE.client.sha256,
        feature_schema_version=DREAM_FEATURE_SCHEMA_VERSION,
        global_feature_count=DREAM_GLOBAL_FEATURE_COUNT,
    )
    candidate = initialized.model_copy(
        update={
            "status": ModelStatus.CANDIDATE,
            "training_context": {
                "simulation": {
                    "ruleset_id": DREAM_RULESET_ID,
                    "observation_schema_version": DREAM_FEATURE_SCHEMA_VERSION,
                    "action_semantics": "sequential-combo-selection",
                }
            },
        }
    )
    directory = tmp_path / "models" / candidate.model_id
    (directory / "manifest.json").write_text(
        candidate.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return directory, candidate


def _readiness(
    tmp_path: Path,
    manifest: ModelManifest,
    *,
    passed: bool = True,
    model_id: str | None = None,
    gate_id: Literal[
        "official-training-shadow-readiness-v1",
        "official-training-shadow-readiness-v2",
    ] = "official-training-shadow-readiness-v2",
) -> Path:
    metrics = {
        "runs_scanned": 20,
        "shadow_runs_seen": 20,
        "matching_runs": 20,
        "excluded_runs": {},
        "completed_games": 20,
        "incomplete_games": 0,
        "failed_runs": 0,
        "operational_aborts": 0,
        "behavior_wins": 2,
        "behavior_losses": 18,
        "behavior_draws": 0,
        "completion_rate": 1.0,
        "completion_lower_bound": 0.8,
        "shadow_samples": 600,
        "eligible_decisions": 550,
        "visibility_abstentions": 25,
        "exact_view_opportunities": 525,
        "exact_view_proposals": 525,
        "encoding_gaps": 0,
        "encoding_gap_reasons": {},
        "exact_view_coverage": 1.0,
        "exact_view_coverage_lower_bound": 0.99,
        "behavior_agreements": 500,
        "behavior_agreement": 0.95,
        "behavior_agreement_lower_bound": 0.92,
        "status_opportunities": {
            "illness": 20,
            "flash": 10,
            "dark-cloud": 20,
            "dream": 20,
        },
        "status_proposals": {
            "illness": 20,
            "flash": 10,
            "dark-cloud": 20,
            "dream": 20,
        },
        "proposal_action_families": {},
        "evidence_error_count": 0,
        "evidence_errors": [],
    }
    report = TrainingShadowReadinessReport(
        evaluation_id="readiness-1",
        gate_id=gate_id,
        created_at=datetime.now(UTC),
        candidate_model_id=model_id or manifest.model_id,
        candidate_weights_sha256=manifest.weights_sha256,
        native_evaluation_ids=("native-1", "native-2", "native-3"),
        native_evaluation_input_sha256s=("a" * 64, "b" * 64, "c" * 64),
        source_database="runs.sqlite",
        native_evaluation_directory="evaluations",
        input_sha256="d" * 64,
        run_ids=("run-1",),
        config={},
        metrics=metrics,
        passed=passed,
        ready_for_guarded_intervention=passed,
        gate_reasons=() if passed else ("fixture rejection",),
    )
    path = tmp_path / "readiness.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _state_and_actions() -> tuple[GameState, LegalActionSet]:
    state = GameState(
        observed_at=datetime.now(UTC),
        field_number=4,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=35, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=28, mp=7, money=20, is_self=False),
        ),
        hand=tuple(
            HandArtifact(
                slot=slot,
                category="weapons",
                slug="bronze-club",
                asset_path="/images/items/weapons/bronze-club.webp",
                bounds=Bounds(x=110 + slot * 90, y=493, width=80, height=80),
            )
            for slot in range(2)
        ),
        scene_layers=("/images/screens/room.webp",),
    )
    digest = game_state_digest(state)
    actions = tuple(
        LegalAction(
            action_id=f"artifact:{slot}:weapons/bronze-club",
            kind=ActionKind.SELECT_ARTIFACT,
            label=f"Select Bronze Club in slot {slot}",
            artifact_slot=slot,
            artifact_asset_path=state.hand[slot].asset_path,
        )
        for slot in range(2)
    )
    return state, LegalActionSet(
        state_digest=digest,
        actions=(LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"), *actions),
        coverage_complete=False,
        blocked_reason="fixture exposes two reviewed actions",
    )


def _policy(tmp_path: Path) -> OfficialTrainingCanaryPolicy:
    directory, manifest = _candidate(tmp_path)
    return OfficialTrainingCanaryPolicy(
        directory,
        BIBLE,
        _readiness(tmp_path, manifest),
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    )


def _proposal(
    state: GameState,
    behavior: PolicyDecision,
    *,
    proposed_action_id: str,
    proposal_probability: float,
    behavior_probability: float,
) -> TrainingShadowEvidence:
    return TrainingShadowEvidence(
        observed_at=state.observed_at,
        model_id="fixture-model",
        model_weights_sha256="e" * 64,
        state_digest=behavior.state_digest,
        field_number=state.field_number,
        behavior_action_id=behavior.chosen_action_id,
        behavior_executable=True,
        covered=True,
        proposed_action_id=proposed_action_id,
        agreement=proposed_action_id == behavior.chosen_action_id,
        scores={
            behavior.chosen_action_id: behavior_probability,
            proposed_action_id: proposal_probability,
            "wait": 0.0,
        },
        recurrent_reset=proposed_action_id != behavior.chosen_action_id,
    )


def test_canary_executes_only_first_high_confidence_disagreement(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    state, actions = _state_and_actions()
    proposed_action_id = "artifact:1:weapons/bronze-club"

    def disagreement(
        state: GameState,
        _actions: LegalActionSet,
        behavior: PolicyDecision,
    ) -> TrainingShadowEvidence:
        return _proposal(
            state,
            behavior,
            proposed_action_id=proposed_action_id,
            proposal_probability=0.95,
            behavior_probability=0.05,
        )

    evaluate = Mock(side_effect=disagreement)
    policy.shadow.evaluate = evaluate

    first = policy.decide(state, actions)
    first_evidence = policy.last_evidence
    second = policy.decide(state, actions)
    second_evidence = policy.last_evidence

    assert first.policy_id == OFFICIAL_TRAINING_CANARY_POLICY_ID
    assert first.chosen_action_id == proposed_action_id
    assert first_evidence is not None
    assert first_evidence.intervention_executed is True
    assert first_evidence.interventions_used == 1
    assert first_evidence.recurrent_reset is True
    assert second.chosen_action_id == "artifact:0:weapons/bronze-club"
    assert second_evidence is not None
    assert second_evidence.candidate_evaluated is False
    assert second_evidence.intervention_executed is False
    assert second_evidence.interventions_remaining == 0
    assert evaluate.call_count == 1


def test_canary_keeps_budget_after_low_confidence_disagreement(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    state, actions = _state_and_actions()
    proposed_action_id = "artifact:1:weapons/bronze-club"

    def low_confidence(
        state: GameState,
        _actions: LegalActionSet,
        behavior: PolicyDecision,
    ) -> TrainingShadowEvidence:
        return _proposal(
            state,
            behavior,
            proposed_action_id=proposed_action_id,
            proposal_probability=0.60,
            behavior_probability=0.40,
        )

    policy.shadow.evaluate = Mock(side_effect=low_confidence)

    decision = policy.decide(state, actions)
    evidence = policy.last_evidence

    assert decision.chosen_action_id == "artifact:0:weapons/bronze-club"
    assert policy.interventions_used == 0
    assert evidence is not None
    assert evidence.exact_view_covered is True
    assert evidence.intervention_eligible is False
    assert evidence.interventions_remaining == 1
    assert "below" in evidence.reason


def test_canary_agreement_does_not_consume_intervention(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    state, actions = _state_and_actions()

    def agreement(
        state: GameState,
        _actions: LegalActionSet,
        behavior: PolicyDecision,
    ) -> TrainingShadowEvidence:
        return _proposal(
            state,
            behavior,
            proposed_action_id=behavior.chosen_action_id,
            proposal_probability=0.95,
            behavior_probability=0.95,
        )

    policy.shadow.evaluate = Mock(side_effect=agreement)

    decision = policy.decide(state, actions)
    evidence = policy.last_evidence

    assert decision.chosen_action_id == "artifact:0:weapons/bronze-club"
    assert policy.interventions_used == 0
    assert evidence is not None
    assert evidence.agreement is True
    assert evidence.intervention_executed is False
    assert evidence.interventions_remaining == 1


def test_canary_rejects_nonpassing_or_mismatched_readiness(tmp_path: Path) -> None:
    directory, manifest = _candidate(tmp_path)
    arguments = (
        directory,
        BIBLE,
        _readiness(tmp_path, manifest, passed=False),
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    )

    with pytest.raises(TrainingCanaryError, match="passing"):
        OfficialTrainingCanaryPolicy(*arguments)

    mismatch = _readiness(tmp_path, manifest, model_id="different-model")
    with pytest.raises(TrainingCanaryError, match="different immutable model weights"):
        OfficialTrainingCanaryPolicy(
            directory,
            BIBLE,
            mismatch,
            {"bronze-club": ("ATK1", 1.0)},
            {"iron-shield": 4},
        )


def test_canary_accepts_legacy_absolute_gap_readiness_report(tmp_path: Path) -> None:
    directory, manifest = _candidate(tmp_path)
    readiness = _readiness(
        tmp_path,
        manifest,
        gate_id="official-training-shadow-readiness-v1",
    )

    policy = OfficialTrainingCanaryPolicy(
        directory,
        BIBLE,
        readiness,
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    )

    assert policy.readiness.gate_id == "official-training-shadow-readiness-v1"
