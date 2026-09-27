from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, Field, ValidationError

from godfield_bot.domain.action import LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import CombatElement
from godfield_bot.policy import HeuristicV0Policy
from godfield_bot.training_shadow import OfficialTrainingShadowPolicy
from godfield_bot.weapon_rules import WeaponAttackRule

if TYPE_CHECKING:
    from godfield_bot.training_shadow_evaluation import TrainingShadowReadinessReport

OFFICIAL_TRAINING_CANARY_POLICY_ID: Final = "official-training-neural-canary-v1"
CANARY_MAX_INTERVENTIONS: Final = 1
CANARY_MINIMUM_PROPOSAL_PROBABILITY: Final = 0.75
CANARY_MINIMUM_BEHAVIOR_MARGIN: Final = 0.25


class TrainingCanaryError(ValueError):
    """Raised when guarded official-Training control cannot be admitted safely."""


class TrainingCanaryEvidence(BaseModel):
    """Attribute one mixed-policy decision without calling it neural control."""

    schema_version: Literal[1] = 1
    evidence_type: Literal["official_training_canary"] = "official_training_canary"
    observed_at: datetime
    policy_id: Literal["official-training-neural-canary-v1"] = (
        "official-training-neural-canary-v1"
    )
    behavior_policy_id: Literal["heuristic-v0"] = "heuristic-v0"
    model_id: str
    model_weights_sha256: str
    feature_schema_version: Literal[10] = 10
    readiness_evaluation_id: str
    readiness_input_sha256: str
    state_digest: str
    field_number: int = Field(ge=0)
    behavior_action_id: str
    chosen_action_id: str
    candidate_evaluated: bool
    exact_view_covered: bool
    proposed_action_id: str | None = None
    agreement: bool | None = None
    proposal_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    behavior_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    behavior_margin: float | None = Field(default=None, ge=-1.0, le=1.0)
    minimum_proposal_probability: float = Field(ge=0.0, le=1.0)
    minimum_behavior_margin: float = Field(ge=0.0, le=1.0)
    intervention_eligible: bool
    intervention_executed: bool
    interventions_used: int = Field(ge=0, le=CANARY_MAX_INTERVENTIONS)
    interventions_remaining: int = Field(ge=0, le=CANARY_MAX_INTERVENTIONS)
    reason: str
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    recurrent_reset: bool = False


def _read_readiness_report(path: Path) -> TrainingShadowReadinessReport:
    from godfield_bot.training_shadow_evaluation import TrainingShadowReadinessReport

    try:
        return TrainingShadowReadinessReport.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise TrainingCanaryError(
            "Training canary readiness report is unreadable or invalid"
        ) from error


class OfficialTrainingCanaryPolicy:
    """Allow one high-confidence schema-v10 disagreement in an official game."""

    policy_id = OFFICIAL_TRAINING_CANARY_POLICY_ID

    def __init__(
        self,
        model_directory: Path,
        snapshot: BibleSnapshot,
        readiness_report_path: Path,
        verified_weapon_attacks: Mapping[str, WeaponAttackRule],
        plain_armor_defenses: Mapping[str, int],
        verified_miracle_attacks: Mapping[str, tuple[int, int, CombatElement]] | None = None,
        plain_hp_utilities: Mapping[str, int] | None = None,
        plain_mp_utilities: Mapping[str, int] | None = None,
    ) -> None:
        self.behavior = HeuristicV0Policy(
            verified_weapon_attacks,
            plain_armor_defenses,
            verified_miracle_attacks,
            plain_hp_utilities,
            plain_mp_utilities,
        )
        self.verified_weapon_attacks = self.behavior.verified_weapon_attacks
        self.verified_miracle_attacks = self.behavior.verified_miracle_attacks
        self.plain_hp_utilities = self.behavior.plain_hp_utilities
        self.plain_mp_utilities = self.behavior.plain_mp_utilities
        self.plain_armor_defenses = self.behavior.plain_armor_defenses
        self.shadow = OfficialTrainingShadowPolicy(model_directory, snapshot)
        self.manifest = self.shadow.manifest
        self.readiness = _read_readiness_report(readiness_report_path)
        if not self.readiness.passed or not self.readiness.ready_for_guarded_intervention:
            raise TrainingCanaryError(
                "Training canary requires a passing guarded-intervention readiness report"
            )
        if self.readiness.gate_reasons or self.readiness.metrics.evidence_error_count:
            raise TrainingCanaryError("Training canary readiness report contains gate errors")
        if (
            self.readiness.candidate_model_id != self.manifest.model_id
            or self.readiness.candidate_weights_sha256 != self.manifest.weights_sha256
        ):
            raise TrainingCanaryError(
                "Training canary readiness report names different immutable model weights"
            )
        self.interventions_used = 0
        self.last_evidence: TrainingCanaryEvidence | None = None

    def _evidence(
        self,
        state: GameState,
        behavior: PolicyDecision,
        chosen_action_id: str,
        *,
        candidate_evaluated: bool,
        exact_view_covered: bool,
        proposed_action_id: str | None,
        agreement: bool | None,
        proposal_probability: float | None,
        behavior_probability: float | None,
        intervention_eligible: bool,
        intervention_executed: bool,
        reason: str,
        candidate_scores: dict[str, float] | None = None,
        recurrent_reset: bool = False,
    ) -> TrainingCanaryEvidence:
        margin = (
            proposal_probability - behavior_probability
            if proposal_probability is not None and behavior_probability is not None
            else None
        )
        return TrainingCanaryEvidence(
            observed_at=state.observed_at,
            model_id=self.manifest.model_id,
            model_weights_sha256=self.manifest.weights_sha256,
            readiness_evaluation_id=self.readiness.evaluation_id,
            readiness_input_sha256=self.readiness.input_sha256,
            state_digest=behavior.state_digest,
            field_number=state.field_number,
            behavior_action_id=behavior.chosen_action_id,
            chosen_action_id=chosen_action_id,
            candidate_evaluated=candidate_evaluated,
            exact_view_covered=exact_view_covered,
            proposed_action_id=proposed_action_id,
            agreement=agreement,
            proposal_probability=proposal_probability,
            behavior_probability=behavior_probability,
            behavior_margin=margin,
            minimum_proposal_probability=CANARY_MINIMUM_PROPOSAL_PROBABILITY,
            minimum_behavior_margin=CANARY_MINIMUM_BEHAVIOR_MARGIN,
            intervention_eligible=intervention_eligible,
            intervention_executed=intervention_executed,
            interventions_used=self.interventions_used,
            interventions_remaining=CANARY_MAX_INTERVENTIONS - self.interventions_used,
            reason=reason,
            candidate_scores=candidate_scores or {},
            recurrent_reset=recurrent_reset,
        )

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        behavior = self.behavior.decide(state, legal_actions)
        if self.interventions_used >= CANARY_MAX_INTERVENTIONS:
            self.shadow.reset()
            self.last_evidence = self._evidence(
                state,
                behavior,
                behavior.chosen_action_id,
                candidate_evaluated=False,
                exact_view_covered=False,
                proposed_action_id=None,
                agreement=None,
                proposal_probability=None,
                behavior_probability=None,
                intervention_eligible=False,
                intervention_executed=False,
                reason="single-intervention budget is exhausted; heuristic retains control",
                recurrent_reset=True,
            )
            return behavior.model_copy(
                update={
                    "policy_id": self.policy_id,
                    "rationale": f"canary fallback after intervention: {behavior.rationale}",
                }
            )

        proposal = self.shadow.evaluate(state, legal_actions, behavior)
        if not proposal.covered or proposal.proposed_action_id is None:
            self.last_evidence = self._evidence(
                state,
                behavior,
                behavior.chosen_action_id,
                candidate_evaluated=True,
                exact_view_covered=False,
                proposed_action_id=None,
                agreement=None,
                proposal_probability=None,
                behavior_probability=None,
                intervention_eligible=False,
                intervention_executed=False,
                reason=proposal.abstain_reason or "candidate abstained",
                recurrent_reset=proposal.recurrent_reset,
            )
            return behavior.model_copy(
                update={
                    "policy_id": self.policy_id,
                    "rationale": (
                        f"canary abstention: {self.last_evidence.reason}; "
                        f"{behavior.rationale}"
                    ),
                }
            )

        proposed_probability = proposal.scores[proposal.proposed_action_id]
        behavior_probability = proposal.scores.get(behavior.chosen_action_id, 0.0)
        agreement = proposal.proposed_action_id == behavior.chosen_action_id
        margin = proposed_probability - behavior_probability
        eligible = (
            not agreement
            and proposed_probability >= CANARY_MINIMUM_PROPOSAL_PROBABILITY
            and margin >= CANARY_MINIMUM_BEHAVIOR_MARGIN
        )
        if eligible:
            self.interventions_used += 1
            self.shadow.reset()
            chosen_action_id = proposal.proposed_action_id
            reason = "first high-confidence exact-view disagreement admitted"
        elif agreement:
            chosen_action_id = behavior.chosen_action_id
            reason = "candidate agrees with heuristic; intervention budget remains unused"
        else:
            chosen_action_id = behavior.chosen_action_id
            reason = "candidate disagreement is below the canary confidence gate"

        self.last_evidence = self._evidence(
            state,
            behavior,
            chosen_action_id,
            candidate_evaluated=True,
            exact_view_covered=True,
            proposed_action_id=proposal.proposed_action_id,
            agreement=agreement,
            proposal_probability=proposed_probability,
            behavior_probability=behavior_probability,
            intervention_eligible=eligible,
            intervention_executed=eligible,
            reason=reason,
            candidate_scores=proposal.scores,
            recurrent_reset=proposal.recurrent_reset or eligible,
        )
        return PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=self.policy_id,
            state_digest=behavior.state_digest,
            chosen_action_id=chosen_action_id,
            scores=(proposal.scores if eligible else behavior.scores),
            rationale=f"Training canary: {reason}",
            executable=behavior.executable,
        )
