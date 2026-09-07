from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MatchResult(StrEnum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"


class MatchOutcome(BaseModel):
    """A terminal result supported by an observed, normalized game state."""

    schema_version: Literal[1] = 1
    observed_at: datetime
    mode: Literal["training"] = "training"
    classification: Literal["two_player_hp_terminal"] = "two_player_hp_terminal"
    terminal_state_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    self_player_name: str
    opponent_player_names: tuple[str, ...]
    result: MatchResult

    @model_validator(mode="after")
    def exactly_one_opponent(self) -> "MatchOutcome":
        if len(self.opponent_player_names) != 1:
            raise ValueError("two-player outcome requires exactly one opponent")
        return self


class SparseTerminalReward(BaseModel):
    """Outcome-only reward; intermediate transitions never use this record."""

    schema_version: Literal[1] = 1
    observed_at: datetime
    scheme: Literal["terminal-outcome-v1"] = "terminal-outcome-v1"
    terminal_state_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    result: MatchResult
    value: float = Field(ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def value_matches_result(self) -> "SparseTerminalReward":
        expected = {
            MatchResult.WIN: 1.0,
            MatchResult.LOSS: -1.0,
            MatchResult.DRAW: 0.0,
        }[self.result]
        if self.value != expected:
            raise ValueError("terminal reward value does not match the match result")
        return self
