"""Command admission contract for the new engine; no gameplay is executed here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SafeCounter = Annotated[int, Field(strict=True, ge=1, le=2**53 - 1)]
ProtocolVersion = Annotated[int, Field(strict=True, ge=1, le=1)]
EnvironmentId = Annotated[int, Field(strict=True, ge=0, le=999_999)]
ActorId = Annotated[int, Field(strict=True, ge=0, le=8)]
ChoiceId = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
FullGamePhase = Literal[
    "setup",
    "ready",
    "attack-selection",
    "target-selection",
    "defense-selection",
    "redirect-selection",
    "trade-response",
    "removal-selection",
    "revival-selection",
    "overflow-selection",
    "event-selection",
    "automatic",
    "terminal",
    "truncated",
]


class FullGameCommand(BaseModel):
    """One public choice bound to exactly one native decision context."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: ProtocolVersion = 1
    environment: EnvironmentId
    episode: SafeCounter
    decision: SafeCounter
    actor: ActorId
    phase: FullGamePhase
    choice_id: ChoiceId


class FullGameDecisionContext(BaseModel):
    """Trusted adapter projection of a native decision, not a policy feature vector."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: ProtocolVersion = 1
    environment: EnvironmentId
    episode: SafeCounter
    decision: SafeCounter
    actor: ActorId
    phase: FullGamePhase
    legal_choice_ids: tuple[ChoiceId, ...]

    @model_validator(mode="after")
    def bounded_choices(self) -> FullGameDecisionContext:
        if len(self.legal_choice_ids) > 16_384 or len(set(self.legal_choice_ids)) != len(
            self.legal_choice_ids
        ):
            raise ValueError("full-game choice IDs must be unique and bounded")
        if self.phase in ("setup", "automatic", "terminal", "truncated"):
            if self.legal_choice_ids:
                raise ValueError("noninteractive full-game phases cannot expose policy choices")
        elif not self.legal_choice_ids:
            raise ValueError("interactive full-game phase must expose a legal choice")
        return self


class FullGameCommandError(ValueError):
    """The whole command batch must be rejected before native mutation."""


def validate_full_game_commands(
    commands: Sequence[FullGameCommand],
    contexts: Mapping[int, FullGameDecisionContext],
) -> tuple[FullGameCommand, ...]:
    """Validate admission only; the future native engine must recheck at commit.

    Neither this function nor its caller-supplied contexts advance a decision,
    create an action mask, or provide exactly-once execution by themselves.
    Epochs and decision counters belong to the authoritative native engine.
    """
    if len(commands) > 1_000_000:
        raise FullGameCommandError("full-game command batch exceeds its row bound")
    accepted: list[FullGameCommand] = []
    seen: set[int] = set()
    for command in commands:
        # Even deliberately unchecked model copies must fail admission closed.
        command = FullGameCommand.model_validate(command.model_dump())
        if command.environment in seen:
            raise FullGameCommandError("duplicate environment in full-game command batch")
        seen.add(command.environment)
        context = contexts.get(command.environment)
        if context is None:
            raise FullGameCommandError("full-game command has no active decision context")
        context = FullGameDecisionContext.model_validate(context.model_dump())
        if (
            command.environment != context.environment
            or command.episode != context.episode
            or command.decision != context.decision
            or command.actor != context.actor
            or command.phase != context.phase
        ):
            raise FullGameCommandError("stale or mismatched full-game decision context")
        if command.choice_id not in context.legal_choice_ids:
            raise FullGameCommandError("illegal full-game phase choice")
        accepted.append(command)
    return tuple(accepted)
