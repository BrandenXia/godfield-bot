from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from godfield_bot.domain.game import GameState


class ActionKind(StrEnum):
    WAIT = "wait"
    PASS = "pass"
    SELECT_ARTIFACT = "select_artifact"
    SELECT_TARGET = "select_target"
    FORGIVE = "forgive"
    CONFIRM_CHANCE = "confirm_chance"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class LegalAction(BaseModel):
    action_id: str
    kind: ActionKind
    label: str
    artifact_slot: int | None = Field(default=None, ge=0)
    artifact_asset_path: str | None = None
    target_player_index: int | None = Field(default=None, ge=0)
    target_player_name: str | None = None
    control_panel: Literal["left", "right"] | None = None
    context_asset_paths: tuple[str, ...] = ()
    actor_player_name: str | None = None
    expected_action_display: str | None = None

    @model_validator(mode="after")
    def artifact_selection_has_identity(self) -> "LegalAction":
        if self.kind is ActionKind.SELECT_ARTIFACT and (
            self.artifact_slot is None or self.artifact_asset_path is None
        ):
            raise ValueError("artifact selection requires a slot and asset path")
        if self.kind is ActionKind.SELECT_TARGET and (
            self.target_player_index is None or not self.target_player_name
        ):
            raise ValueError("target selection requires a player index and name")
        if self.kind is ActionKind.CONFIRM and (
            self.artifact_asset_path is None
            or self.target_player_index is None
            or not self.target_player_name
            or self.control_panel is None
        ):
            raise ValueError("confirmation requires artifact, target, and panel identities")
        if self.kind is ActionKind.FORGIVE and (
            (self.artifact_asset_path is None and not self.context_asset_paths)
            or self.target_player_index is None
            or not self.target_player_name
            or self.control_panel is None
        ):
            raise ValueError("phase completion requires artifact, target, and panel identities")
        if self.kind is ActionKind.PASS and (
            not self.actor_player_name
            or self.control_panel != "left"
            or self.artifact_asset_path is not None
            or self.target_player_index is not None
            or self.target_player_name is not None
        ):
            raise ValueError("pass requires the verified actor and empty left panel")
        if self.kind is ActionKind.CONFIRM_CHANCE and (
            self.artifact_asset_path is None
            or not self.actor_player_name
            or not self.expected_action_display
            or self.control_panel != "left"
            or self.target_player_index is not None
            or self.target_player_name is not None
        ):
            raise ValueError(
                "untargeted confirmation requires artifact, actor, display, and empty target"
            )
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


class ActionTransition(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    action_id: str
    before_state_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    after_state_digest: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    state_changed: bool | None
    field_delta: int | None = None
    player_hp_deltas: dict[str, int] = Field(default_factory=dict)
    before_state: GameState | None = None
    after_state: GameState | None = None

    @model_validator(mode="after")
    def observed_state_contract_is_consistent(self) -> "ActionTransition":
        if self.state_changed is None:
            if self.after_state_digest is not None or self.after_state is not None:
                raise ValueError("unobserved transition cannot include an after state")
            return self
        if self.after_state_digest is None:
            raise ValueError("observed transition requires an after-state digest")
        if self.state_changed == (self.after_state_digest == self.before_state_digest):
            raise ValueError("state-change flag conflicts with transition digests")
        if self.before_state is None and self.after_state is not None:
            raise ValueError("embedded after state requires an embedded before state")
        if self.before_state is not None and self.after_state is None:
            raise ValueError("embedded observed states must include both endpoints")
        return self
