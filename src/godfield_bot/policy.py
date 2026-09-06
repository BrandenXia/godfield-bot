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


class HeuristicV0Policy:
    """First executable baseline: select a weapon in the verified self phase."""

    policy_id = "heuristic-v0"

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        wait_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.WAIT
        ]
        if len(wait_actions) != 1:
            raise ValueError("heuristic policy requires exactly one WAIT action")
        artifact_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.SELECT_ARTIFACT
        ]
        weapon_actions = [
            action
            for action in artifact_actions
            if action.artifact_slot is not None
            and state.hand[action.artifact_slot].category == "weapons"
        ]
        chosen = weapon_actions[0] if weapon_actions else wait_actions[0]
        executable = chosen.kind is not ActionKind.WAIT
        return PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=self.policy_id,
            state_digest=legal_actions.state_digest,
            chosen_action_id=chosen.action_id,
            scores={
                action.action_id: float(action.action_id == chosen.action_id)
                for action in legal_actions.actions
            },
            rationale=(
                "select the first weapon with a verified hand hit target"
                if executable
                else legal_actions.blocked_reason or "no executable action verified"
            ),
            executable=executable,
        )
