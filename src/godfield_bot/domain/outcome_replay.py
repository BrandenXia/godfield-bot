from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from godfield_bot.domain.game import GameState
from godfield_bot.domain.outcome import MatchOutcome, SparseTerminalReward
from godfield_bot.domain.replay import ReplaySample
from godfield_bot.domain.run import RunMode


class OutcomeReplayEpisode(BaseModel):
    """A complete, terminal-labeled sequence of verified browser actions."""

    schema_version: Literal[2] = 2
    run_id: str
    mode: RunMode
    client_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    model_id: str | None = None
    steps: tuple[ReplaySample, ...] = Field(min_length=1)
    terminal_state: GameState
    outcome: MatchOutcome
    reward: SparseTerminalReward

    @model_validator(mode="after")
    def evidence_has_consistent_lineage(self) -> "OutcomeReplayEpisode":
        if any(
            (
                step.run_id,
                step.client_sha256,
                step.policy_id,
                step.model_id,
            )
            != (self.run_id, self.client_sha256, self.policy_id, self.model_id)
            for step in self.steps
        ):
            raise ValueError("episode steps have inconsistent run lineage")
        sequences = [step.transition_sequence for step in self.steps]
        if sequences != sorted(set(sequences)):
            raise ValueError("episode transition sequences are not strictly ordered")
        if (
            self.reward.result is not self.outcome.result
            or self.reward.terminal_state_digest != self.outcome.terminal_state_digest
        ):
            raise ValueError("episode outcome and reward do not describe one terminal state")
        return self


class OutcomeReplayExportSummary(BaseModel):
    schema_version: Literal[1] = 1
    destination: Path
    runs_scanned: int = Field(ge=0)
    completed_runs_seen: int = Field(ge=0)
    episodes_exported: int = Field(ge=0)
    steps_exported: int = Field(ge=0)
    skipped: dict[str, int] = Field(default_factory=dict)
