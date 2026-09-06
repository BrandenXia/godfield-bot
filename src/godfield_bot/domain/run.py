from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, JsonValue


class RunMode(StrEnum):
    TRAINING = "training"
    PRIVATE = "private"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class EventKind(StrEnum):
    OBSERVATION = "observation"
    GAME_STATE = "game_state"
    LEGAL_ACTIONS = "legal_actions"
    DECISION = "decision"
    ACTION_RESULT = "action_result"
    REWARD = "reward"
    MATCH_END = "match_end"
    ERROR = "error"


class RunSpec(BaseModel):
    mode: RunMode
    identity: str
    client_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    model_id: str | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class RunRecord(RunSpec):
    run_id: str
    started_at: datetime
    ended_at: datetime | None = None
    status: RunStatus
    outcome: dict[str, JsonValue] | None = None


class RunEvent(BaseModel):
    run_id: str
    sequence: int = Field(ge=0)
    occurred_at: datetime
    kind: EventKind
    payload: dict[str, JsonValue]
