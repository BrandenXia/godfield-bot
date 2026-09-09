from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState
from godfield_bot.weapon_rules import WeaponAttackRule, weapon_attack_value


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
    """Executable baseline constrained to Bible-audited fixed attacks and plain armor."""

    policy_id = "heuristic-v0"

    def __init__(
        self,
        verified_weapon_attacks: Mapping[str, WeaponAttackRule],
        plain_armor_defenses: Mapping[str, int],
        verified_miracle_attacks: Mapping[str, tuple[int, int, str]] | None = None,
    ) -> None:
        if not verified_weapon_attacks or not plain_armor_defenses:
            raise ValueError("heuristic-v0 requires Bible-audited artifact values")
        self.verified_weapon_attacks = dict(verified_weapon_attacks)
        self.verified_miracle_attacks = dict(verified_miracle_attacks or {})
        self.plain_armor_defenses = dict(plain_armor_defenses)

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        wait_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.WAIT
        ]
        if len(wait_actions) != 1:
            raise ValueError("heuristic policy requires exactly one WAIT action")
        artifact_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.SELECT_ARTIFACT
        ]
        target_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.SELECT_TARGET
        ]
        forgive_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.FORGIVE
        ]
        pass_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.PASS
        ]
        confirm_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.CONFIRM
        ]
        chance_actions = [
            action
            for action in legal_actions.actions
            if action.kind is ActionKind.CONFIRM_CHANCE
        ]
        if len(target_actions) > 1:
            raise ValueError("heuristic policy requires at most one verified target")
        if len(forgive_actions) > 1:
            raise ValueError("heuristic policy requires at most one Forgive action")
        if len(confirm_actions) > 1:
            raise ValueError("heuristic policy requires at most one verified confirmation")
        if len(chance_actions) > 1:
            raise ValueError("heuristic policy requires at most one chance confirmation")
        if len(pass_actions) > 1:
            raise ValueError("heuristic policy requires at most one verified pass")
        ranked_actions = [
            action
            for action in artifact_actions
            if action.artifact_slot is not None
            and (
                (
                    state.hand[action.artifact_slot].category == "weapons"
                    and state.hand[action.artifact_slot].slug in self.verified_weapon_attacks
                )
                or (
                    state.hand[action.artifact_slot].category == "miracles"
                    and state.hand[action.artifact_slot].slug in self.verified_miracle_attacks
                    and self.verified_miracle_attacks[state.hand[action.artifact_slot].slug][1]
                    <= state.players[state.self_player_index].mp
                )
                or (
                    state.hand[action.artifact_slot].category == "armor"
                    and state.hand[action.artifact_slot].slug in self.plain_armor_defenses
                )
            )
        ]

        def artifact_value(action: LegalAction) -> tuple[float, int]:
            if action.artifact_slot is None:
                raise ValueError("ranked artifact action is missing its slot")
            artifact = state.hand[action.artifact_slot]
            if artifact.category == "weapons":
                value = weapon_attack_value(
                    self.verified_weapon_attacks[artifact.slug],
                    mp=state.players[state.self_player_index].mp,
                )
            elif artifact.category == "miracles":
                value = self.verified_miracle_attacks[artifact.slug][0]
            else:
                value = self.plain_armor_defenses[artifact.slug]
            return value, -action.artifact_slot

        chosen = (
            confirm_actions[0]
            if confirm_actions
            else chance_actions[0]
            if chance_actions
            else target_actions[0]
            if target_actions
            else max(ranked_actions, key=artifact_value)
            if ranked_actions
            else pass_actions[0]
            if pass_actions
            else forgive_actions[0]
            if forgive_actions
            else wait_actions[0]
        )
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
                "select the sole verified opponent target"
                if chosen.kind is ActionKind.SELECT_TARGET
                else "resolve the selected Bible-audited untargeted attack"
                if chosen.kind is ActionKind.CONFIRM_CHANCE
                else "confirm the selected verified attack on the named sole opponent"
                if chosen.kind is ActionKind.CONFIRM
                else "select the strongest affordable phase-appropriate Bible-audited artifact"
                if chosen.kind is ActionKind.SELECT_ARTIFACT
                else "forgive an incoming attack with no verified usable defense"
                if chosen.kind is ActionKind.FORGIVE
                else "pass an attack turn because no reviewed attack is usable"
                if chosen.kind is ActionKind.PASS
                else legal_actions.blocked_reason or "no executable action verified"
            ),
            executable=executable,
        )
