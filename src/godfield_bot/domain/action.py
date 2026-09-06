from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ActionKind(StrEnum):
    WAIT = "wait"
    SELECT_ARTIFACT = "select_artifact"
    SELECT_TARGET = "select_target"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class LegalAction(BaseModel):
    action_id: str
    kind: ActionKind
    label: str
    artifact_slot: int | None = Field(default=None, ge=0)
    artifact_asset_path: str | None = None
    target_player_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def artifact_selection_has_identity(self) -> "LegalAction":
        if self.kind is ActionKind.SELECT_ARTIFACT and (
            self.artifact_slot is None or self.artifact_asset_path is None
        ):
            raise ValueError("artifact selection requires a slot and asset path")
        return self


class LegalActionSet(BaseModel):
    schema_version: int = 1
    state_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    actions: tuple[LegalAction, ...]
    coverage_complete: bool
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def action_ids_are_unique(self) -> "LegalActionSet":
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("legal action IDs must be unique")
        if not self.coverage_complete and not self.blocked_reason:
            raise ValueError("incomplete action coverage requires a blocked reason")
        return self


class PolicyDecision(BaseModel):
    schema_version: int = 1
    decided_at: datetime
    policy_id: str
    state_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    chosen_action_id: str
    scores: dict[str, float]
    rationale: str
    executable: bool


class ActionExecutionResult(BaseModel):
    schema_version: int = 1
    executed_at: datetime
    action_id: str
    kind: ActionKind
    dispatched: bool
    latency_ms: float = Field(ge=0)
