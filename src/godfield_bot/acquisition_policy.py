"""Bounded official-Training interventions for mechanics collection, not strength."""

from collections.abc import Mapping

from godfield_bot.domain.action import ActionKind, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState
from godfield_bot.elements import CombatElement
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.policy import HeuristicV0Policy
from godfield_bot.weapon_rules import WeaponAttackRule

ACQUISITION_POLICY_ID = "official-training-acquisition-miracle-v1"
ACQUISITION_MAX_PRIORITIZED_SELECTIONS = 2


class AcquisitionMiraclePolicy(HeuristicV0Policy):
    """Prioritize a reviewed, affordable miracle twice; preserve phase controls.

    The budget counts prioritized decisions, not server-confirmed casts. The
    ordinary fallback can still choose miracles after the intervention budget.
    Repeated polling of an unchanged legal state does not consume the budget.
    """

    policy_id = ACQUISITION_POLICY_ID

    def __init__(
        self,
        verified_weapon_attacks: Mapping[str, WeaponAttackRule],
        plain_armor_defenses: Mapping[str, int],
        verified_miracle_attacks: Mapping[str, tuple[int, int, CombatElement]],
        plain_hp_utilities: Mapping[str, int],
        plain_mp_utilities: Mapping[str, int],
        *,
        focus: str,
    ) -> None:
        super().__init__(
            verified_weapon_attacks,
            plain_armor_defenses,
            verified_miracle_attacks,
            plain_hp_utilities,
            plain_mp_utilities,
        )
        if focus not in self.verified_miracle_attacks:
            raise ValueError("miracle collection requires a reviewed fixed-attack miracle slug")
        self.focus = focus
        self.prioritized_selection_count = 0
        self._last_focus_key: tuple[str, tuple[str, ...]] | None = None
        self._last_focus_decision: PolicyDecision | None = None

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        fallback = super().decide(state, legal_actions)
        key = (
            legal_actions.state_digest,
            tuple(action.model_dump_json() for action in legal_actions.actions),
        )
        if key != self._last_focus_key:
            self._last_focus_key = None
            self._last_focus_decision = None
        if game_state_digest(state) != legal_actions.state_digest:
            raise ValueError("miracle collection legal actions do not match the current state")
        chosen = next(
            action
            for action in legal_actions.actions
            if action.action_id == fallback.chosen_action_id
        )
        artifacts = {artifact.slot: artifact for artifact in state.hand}
        base_artifact = (
            artifacts.get(chosen.artifact_slot) if chosen.artifact_slot is not None else None
        )
        # Never replace target/confirmation/defense/healing/utility/wait controls.
        if (
            chosen.kind is not ActionKind.SELECT_ARTIFACT
            or base_artifact is None
            or base_artifact.category not in {"weapons", "miracles"}
        ):
            return fallback
        me = state.players[state.self_player_index]
        if me.mp < self.verified_miracle_attacks[self.focus][1]:
            return fallback
        candidates = [
            action
            for action in legal_actions.actions
            if action.kind is ActionKind.SELECT_ARTIFACT
            and action.artifact_slot is not None
            and (artifact := artifacts.get(action.artifact_slot)) is not None
            and artifact.category == "miracles"
            and artifact.slug == self.focus
            and action.artifact_asset_path == artifact.asset_path
        ]
        if not candidates:
            return fallback
        if self._last_focus_decision is not None:
            return self._last_focus_decision
        if self.prioritized_selection_count >= ACQUISITION_MAX_PRIORITIZED_SELECTIONS:
            return fallback
        selected = min(candidates, key=lambda action: action.artifact_slot or 0)
        self.prioritized_selection_count += 1
        decision = fallback.model_copy(
            update={
                "chosen_action_id": selected.action_id,
                "scores": {
                    action.action_id: float(action == selected) for action in legal_actions.actions
                },
                "rationale": (
                    f"collection only: prioritize reviewed {self.focus}; selection "
                    f"{self.prioritized_selection_count}/{ACQUISITION_MAX_PRIORITIZED_SELECTIONS}; "
                    "not evidence of an accepted or reusable cast"
                ),
            }
        )
        self._last_focus_key, self._last_focus_decision = key, decision
        return decision
