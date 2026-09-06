from datetime import UTC, datetime
from typing import Protocol

from godfield_bot.domain.action import ActionKind, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState


class Policy(Protocol):
    policy_id: str

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision: ...


class SafeObserverPolicy:
    """A deterministic baseline that refuses unverified external actions."""

    policy_id = "safe-observer-v0"

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        del state
        wait_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.WAIT
        ]
        if len(wait_actions) != 1:
            raise ValueError("safe observer policy requires exactly one WAIT action")
        wait = wait_actions[0]
        return PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=self.policy_id,
            state_digest=legal_actions.state_digest,
            chosen_action_id=wait.action_id,
            scores={wait.action_id: 1.0},
            rationale=legal_actions.blocked_reason or "observation-only safety gate",
            executable=False,
        )
