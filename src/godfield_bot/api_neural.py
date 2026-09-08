from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torch import Tensor

from godfield_bot.api_game import (
    ApiActionKind,
    ApiGameState,
    ApiLegalAction,
    ApiLegalActionSet,
    ApiPhase,
    ApiPolicyDecision,
    api_game_state_digest,
)
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import COMBAT_ELEMENT_IDS, COMBAT_ELEMENTS, CombatElement
from godfield_bot.features import (
    FEATURE_SCHEMA_VERSION,
    GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
    StateFeatures,
)
from godfield_bot.model_registry import (
    ModelManifest,
    ModelStatus,
    load_model,
    vocabulary_digest,
)
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors
from godfield_bot.reference import (
    plain_attack_booster_cards,
    plain_attack_weapon_cards,
    plain_defense_armor_cards,
)
from godfield_bot.simulation_policy import CONFIRM_ACTION_INDEX, FORGIVE_ACTION_INDEX

API_COMBO_SHADOW_POLICY_ID = "api-combo-neural-shadow-v1"
COMBO_RULESET_ID = "plain-elemental-combo-attack-defense-redraw-duel-v1"
MAX_HAND_SLOTS = 9
MAX_PLAYERS = 9


class ApiNeuralPolicyError(RuntimeError):
    """Raised when a learned model cannot be bound safely to live API state."""


def _combat_element(value: str | None) -> CombatElement:
    normalized = "non-element" if value is None else value
    if normalized not in COMBAT_ELEMENT_IDS:
        raise ApiNeuralPolicyError(f"live API state contains unknown element {normalized!r}")
    return normalized


def _combine_attack_elements(existing: CombatElement, added: CombatElement) -> CombatElement:
    if existing == added:
        return existing
    ordinary = {"fire", "water", "wood", "stone"}
    if existing == "light" and added in ordinary:
        return added
    if added == "light" and existing in ordinary:
        return existing
    return "non-element"


def _validate_shadow_model(
    manifest: ModelManifest,
    vocabulary: ArtifactVocabulary,
    snapshot: BibleSnapshot,
) -> None:
    if manifest.status not in {ModelStatus.CANDIDATE, ModelStatus.CHAMPION}:
        raise ApiNeuralPolicyError("live shadow inference requires a candidate or champion model")
    if manifest.feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise ApiNeuralPolicyError("live combo inference requires feature schema v4")
    if (
        manifest.architecture.action_count != 21
        or manifest.architecture.global_feature_count != GLOBAL_FEATURE_COUNT
        or manifest.architecture.vocabulary_size != len(vocabulary.tokens)
    ):
        raise ApiNeuralPolicyError("model architecture differs from the live combo bridge")
    if manifest.client_sha256 != snapshot.client.sha256:
        raise ApiNeuralPolicyError("model client fingerprint differs from the Bible snapshot")
    if manifest.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ApiNeuralPolicyError("model vocabulary differs from the Bible snapshot")
    simulation = manifest.training_context.get("simulation")
    if not isinstance(simulation, dict) or (
        simulation.get("ruleset_id") != COMBO_RULESET_ID
        or simulation.get("action_semantics") != "sequential-combo-selection"
    ):
        raise ApiNeuralPolicyError("model was not trained on the live combo action semantics")


@dataclass
class ApiComboShadowPolicy:
    """Translate one live state into an observable, non-executable combo proposal."""

    manifest: ModelManifest
    model: RecurrentPolicyValueNet
    vocabulary: ArtifactVocabulary
    snapshot: BibleSnapshot
    recurrent_state: Tensor | None = None
    _base_assets: set[str] = field(init=False, repr=False)
    _booster_assets: set[str] = field(init=False, repr=False)
    _armor_assets: set[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _validate_shadow_model(self.manifest, self.vocabulary, self.snapshot)
        self.model.eval()
        self._base_assets = set(plain_attack_weapon_cards(self.snapshot))
        self._booster_assets = set(plain_attack_booster_cards(self.snapshot))
        self._armor_assets = set(plain_defense_armor_cards(self.snapshot))

    def reset(self) -> None:
        self.recurrent_state = None

    def observe_behavior(
        self,
        proposal: ApiLegalAction | None,
        behavior: ApiLegalAction | None,
    ) -> None:
        """Discard counterfactual memory when the behavior policy chose another macro."""

        if proposal is None or behavior is None or proposal.action_id != behavior.action_id:
            self.reset()

    def _unsupported(
        self,
        state: ApiGameState,
        legal_actions: ApiLegalActionSet,
        reason: str,
    ) -> tuple[ApiPolicyDecision, None]:
        self.reset()
        return (
            ApiPolicyDecision(
                decided_at=datetime.now(UTC),
                policy_id=API_COMBO_SHADOW_POLICY_ID,
                state_digest=legal_actions.state_digest,
                scores={action.action_id: 0.0 for action in legal_actions.actions},
                rationale=reason,
                executable=False,
                model_id=self.manifest.model_id,
                model_weights_sha256=self.manifest.weights_sha256,
            ),
            None,
        )

    def _strict_macros(
        self,
        state: ApiGameState,
        legal_actions: ApiLegalActionSet,
    ) -> list[ApiLegalAction]:
        by_instance = {item.instance_id: item for item in state.hand}
        macros: list[ApiLegalAction] = []
        for action in legal_actions.actions:
            if action.kind is not ApiActionKind.USE_ITEM or not action.item_instance_ids:
                continue
            items = [by_instance.get(instance_id) for instance_id in action.item_instance_ids]
            if any(item is None or not item.identity_reliable for item in items):
                continue
            assets = [item.asset for item in items if item is not None]
            if state.phase is ApiPhase.TURN:
                if assets[0] in self._base_assets and all(
                    asset in self._booster_assets for asset in assets[1:]
                ):
                    macros.append(action)
            elif state.phase is ApiPhase.DEFENSE and all(
                asset in self._armor_assets for asset in assets
            ):
                macros.append(action)
        return macros

    def _features(
        self,
        state: ApiGameState,
        *,
        selected_slots: set[int],
        selected_value: int,
        selected_element: CombatElement,
        action_mask: list[bool],
    ) -> StateFeatures:
        me = next(player for player in state.players if player.is_self)
        ordered_players = (me, *(player for player in state.players if not player.is_self))
        players = [
            (
                min(player.hp, 100) / 100.0,
                min(player.mp, 100) / 100.0,
                min(player.cp, 100) / 100.0,
                float(player.is_self),
            )
            for player in ordered_players
        ]
        player_mask = [True] * len(players)
        while len(players) < MAX_PLAYERS:
            players.append((0.0, 0.0, 0.0, 0.0))
            player_mask.append(False)

        hand_token_ids: list[int] = []
        hand_mask: list[bool] = []
        for slot, item in enumerate(state.hand):
            selected = slot in selected_slots
            hand_token_ids.append(
                0
                if selected
                else self.vocabulary.token_id(item.category or "", item.asset or "")
            )
            hand_mask.append(not selected)
        while len(hand_token_ids) < MAX_HAND_SLOTS:
            hand_token_ids.append(0)
            hand_mask.append(False)

        response = state.phase is ApiPhase.DEFENSE
        pending_value = (
            state.pending_attack.attack
            if response and state.pending_attack is not None
            else selected_value
        )
        visible_element = (
            _combat_element(state.pending_attack.element)
            if response and state.pending_attack is not None
            else selected_element
        )
        element_features = [0.0] * len(COMBAT_ELEMENTS)
        if response or selected_slots:
            element_features[COMBAT_ELEMENT_IDS[visible_element]] = 1.0
        return StateFeatures(
            global_features=(
                min(state.field_number, 100) / 100.0,
                min(me.hp, 100) / 100.0,
                min(me.mp, 100) / 100.0,
                min(me.cp, 100) / 100.0,
                float(response),
                min(pending_value, 100) / 100.0,
                *element_features,
            ),
            player_features=tuple(players),
            player_mask=tuple(player_mask),
            hand_token_ids=tuple(hand_token_ids),
            hand_mask=tuple(hand_mask),
            action_mask=tuple(action_mask),
        )

    def decide(
        self,
        state: ApiGameState,
        legal_actions: ApiLegalActionSet,
    ) -> tuple[ApiPolicyDecision, ApiLegalAction | None]:
        if legal_actions.state_digest != api_game_state_digest(state):
            return self._unsupported(
                state,
                legal_actions,
                "shadow model received actions from a different live state",
            )
        if len(state.players) != 2:
            return self._unsupported(
                state,
                legal_actions,
                "shadow model is restricted to two-player private games",
            )
        if state.phase not in {ApiPhase.TURN, ApiPhase.DEFENSE}:
            return self._unsupported(
                state,
                legal_actions,
                "shadow model does not cover this live phase",
            )
        if state.has_active_curses:
            return self._unsupported(
                state,
                legal_actions,
                "shadow model abstained because curses are outside its curriculum",
            )
        if len(state.hand) > MAX_HAND_SLOTS:
            return self._unsupported(
                state,
                legal_actions,
                "shadow model abstained because the live hand exceeds nine slots",
            )

        macros = self._strict_macros(state, legal_actions)
        if not macros:
            return self._unsupported(
                state,
                legal_actions,
                "shadow model found no live macro covered by its curriculum",
            )
        hand_slot_by_id = {
            item.instance_id: slot
            for slot, item in enumerate(state.hand)
            if item.instance_id is not None
        }
        selected_slots: set[int] = set()
        selected_ids: list[int] = []
        selected_value = 0
        selected_element: CombatElement = "non-element"
        action_indices: list[int] = []
        probabilities: list[float] = []
        values: list[float] = []
        proposal: ApiLegalAction | None = None

        import torch

        for _step in range(MAX_HAND_SLOTS + 1):
            selected_set = set(selected_ids)
            action_mask = [False] * self.manifest.architecture.action_count
            if not selected_ids:
                if state.phase is ApiPhase.TURN:
                    selectable = {macro.item_instance_ids[0] for macro in macros}
                else:
                    selectable = {
                        instance_id for macro in macros for instance_id in macro.item_instance_ids
                    }
                    action_mask[FORGIVE_ACTION_INDEX] = True
            else:
                selectable = {
                    instance_id
                    for macro in macros
                    if selected_set.issubset(macro.item_instance_ids)
                    for instance_id in macro.item_instance_ids
                    if instance_id not in selected_set
                }
                action_mask[CONFIRM_ACTION_INDEX] = any(
                    selected_set == set(macro.item_instance_ids) for macro in macros
                )
            for instance_id in selectable:
                slot = hand_slot_by_id.get(instance_id)
                if slot is not None and slot not in selected_slots:
                    action_mask[slot + 1] = True
            if not any(action_mask):
                return self._unsupported(
                    state,
                    legal_actions,
                    "shadow model reached no verified continuation",
                )

            features = self._features(
                state,
                selected_slots=selected_slots,
                selected_value=selected_value,
                selected_element=selected_element,
                action_mask=action_mask,
            )
            tensors = features_to_tensors((features,))
            with torch.no_grad():
                logits, value, next_state = self.model(*tensors, self.recurrent_state)
                probability = torch.softmax(logits, dim=-1)
                action_index = int(logits.argmax(dim=-1).item())
            self.recurrent_state = next_state.detach()
            action_indices.append(action_index)
            probabilities.append(float(probability[0, action_index].item()))
            values.append(float(value[0].item()))

            if 1 <= action_index <= MAX_HAND_SLOTS:
                slot = action_index - 1
                item = state.hand[slot]
                if item.instance_id is None:
                    return self._unsupported(
                        state,
                        legal_actions,
                        "shadow model selected a transient item placeholder",
                    )
                selected_slots.add(slot)
                selected_ids.append(item.instance_id)
                if state.phase is ApiPhase.TURN:
                    selected_value += item.attack
                    item_element = _combat_element(item.element)
                    selected_element = (
                        item_element
                        if len(selected_ids) == 1
                        else _combine_attack_elements(selected_element, item_element)
                    )
                else:
                    selected_value += item.defense
                continue
            if action_index == FORGIVE_ACTION_INDEX and not selected_ids:
                proposal = next(
                    (
                        action
                        for action in legal_actions.actions
                        if action.kind is ApiActionKind.PASS
                    ),
                    None,
                )
                break
            if action_index == CONFIRM_ACTION_INDEX and selected_ids:
                selected_set = set(selected_ids)
                proposal = next(
                    (
                        macro
                        for macro in macros
                        if selected_set == set(macro.item_instance_ids)
                    ),
                    None,
                )
                break
            return self._unsupported(
                state,
                legal_actions,
                "shadow model emitted an action outside the verified bridge",
            )

        if proposal is None:
            return self._unsupported(
                state,
                legal_actions,
                "shadow model did not finish its bounded combo selection",
            )
        return (
            ApiPolicyDecision(
                decided_at=datetime.now(UTC),
                policy_id=API_COMBO_SHADOW_POLICY_ID,
                state_digest=legal_actions.state_digest,
                chosen_action_id=proposal.action_id,
                scores={
                    action.action_id: float(action.action_id == proposal.action_id)
                    for action in legal_actions.actions
                },
                rationale=(
                    "non-executable learned combo proposal; the conservative heuristic "
                    "remains the live behavior policy"
                ),
                executable=False,
                model_id=self.manifest.model_id,
                model_weights_sha256=self.manifest.weights_sha256,
                selection_action_indices=tuple(action_indices),
                selection_probabilities=tuple(probabilities),
                value_estimates=tuple(values),
            ),
            proposal,
        )


def load_api_combo_shadow_policy(
    model_directory: Path,
    bible_snapshot_path: Path,
) -> ApiComboShadowPolicy:
    try:
        snapshot = BibleSnapshot.model_validate_json(
            bible_snapshot_path.read_text(encoding="utf-8")
        )
        vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
        manifest, model = load_model(model_directory)
    except (OSError, ValueError) as error:
        raise ApiNeuralPolicyError(
            "live shadow model artifacts are unreadable or invalid"
        ) from error
    return ApiComboShadowPolicy(manifest, model, vocabulary, snapshot)
