from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from godfield_bot.domain.action import (
    ActionExecutionResult,
    ActionTransition,
    LegalAction,
    LegalActionSet,
    PolicyDecision,
)
from godfield_bot.domain.game import GameState


class ReplaySample(BaseModel):
    """One fully verified browser transition suitable for offline learning."""

    schema_version: int = 1
    run_id: str
    transition_sequence: int = Field(ge=0)
    client_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    model_id: str | None = None
    before_state: GameState
    legal_actions: LegalActionSet
    chosen_action: LegalAction
    decision: PolicyDecision
    execution: ActionExecutionResult
    after_state: GameState
    transition: ActionTransition

    @model_validator(mode="after")
    def evidence_describes_one_accepted_action(self) -> "ReplaySample":
        action_id = self.chosen_action.action_id
        if action_id not in {action.action_id for action in self.legal_actions.actions}:
            raise ValueError("chosen action is outside the recorded legal set")
        if {
            self.decision.chosen_action_id,
            self.execution.action_id,
            self.transition.action_id,
        } != {action_id}:
            raise ValueError("replay evidence refers to different actions")
        if not self.decision.executable or not self.execution.dispatched:
            raise ValueError("replay action was not executed")
        if self.execution.kind is not self.chosen_action.kind:
            raise ValueError("executed action kind differs from the chosen action")
        if self.decision.policy_id != self.policy_id:
            raise ValueError("decision policy differs from run policy")
        if self.transition.state_changed is not True:
            raise ValueError("replay transition did not change normalized state")
        if {
            self.legal_actions.state_digest,
            self.decision.state_digest,
            self.transition.before_state_digest,
        } != {self.transition.before_state_digest}:
            raise ValueError("replay evidence refers to different starting states")
        return self


class ReplayExportSummary(BaseModel):
    schema_version: int = 1
    destination: Path
    runs_scanned: int = Field(ge=0)
    transitions_seen: int = Field(ge=0)
    samples_exported: int = Field(ge=0)
    skipped: dict[str, int] = Field(default_factory=dict)
