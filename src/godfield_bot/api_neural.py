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
    ApiItemState,
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
    RESOURCE_FEATURE_SCHEMA_VERSION,
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
    plain_hp_utility_sundries,
    plain_mp_utility_sundries,
    verified_attack_miracle_cards,
    verified_hp_utility_miracle_cards,
)
from godfield_bot.simulation_policy import CONFIRM_ACTION_INDEX, FORGIVE_ACTION_INDEX

API_COMBO_SHADOW_POLICY_ID = "api-combo-neural-shadow-v1"
API_RESOURCE_SHADOW_POLICY_ID = "api-resource-neural-shadow-v2"
COMBO_RULESET_ID = "plain-elemental-combo-attack-defense-redraw-duel-v1"
RESOURCE_RULESET_ID = (
    "plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1"
)
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
    supported_rulesets = {
        FEATURE_SCHEMA_VERSION: COMBO_RULESET_ID,
        RESOURCE_FEATURE_SCHEMA_VERSION: RESOURCE_RULESET_ID,
    }
    expected_ruleset = supported_rulesets.get(manifest.feature_schema_version)
    if expected_ruleset is None:
        raise ApiNeuralPolicyError("live inference requires feature schema v4 or v5")
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
        simulation.get("ruleset_id") != expected_ruleset
        or simulation.get("action_semantics") != "sequential-combo-selection"
    ):
        raise ApiNeuralPolicyError(
            "model was not trained on the matching live combo action semantics"
        )


@dataclass
class ApiComboShadowPolicy:
    """Translate one live state into an observable, non-executable learned proposal."""

    manifest: ModelManifest
    model: RecurrentPolicyValueNet
    vocabulary: ArtifactVocabulary
    snapshot: BibleSnapshot
    recurrent_state: Tensor | None = None
    _base_cards: dict[str, tuple[int, CombatElement]] = field(init=False, repr=False)
    _booster_cards: dict[str, tuple[int, CombatElement]] = field(init=False, repr=False)
    _armor_cards: dict[str, tuple[int, CombatElement]] = field(init=False, repr=False)
    _hp_utilities: dict[str, int] = field(init=False, repr=False)
    _mp_utilities: dict[str, int] = field(init=False, repr=False)
    _attack_miracles: dict[str, tuple[int, int, CombatElement]] = field(
        init=False,
        repr=False,
    )
    _hp_miracles: dict[str, tuple[int, int]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _validate_shadow_model(self.manifest, self.vocabulary, self.snapshot)
        self.model.eval()
        self._base_cards = plain_attack_weapon_cards(self.snapshot)
        self._booster_cards = plain_attack_booster_cards(self.snapshot)
        self._armor_cards = plain_defense_armor_cards(self.snapshot)
        if self.resource_enabled:
            self._hp_utilities = plain_hp_utility_sundries(self.snapshot)
            self._mp_utilities = plain_mp_utility_sundries(self.snapshot)
            self._attack_miracles = verified_attack_miracle_cards(self.snapshot)
            self._hp_miracles = verified_hp_utility_miracle_cards(self.snapshot)
        else:
            self._hp_utilities = {}
            self._mp_utilities = {}
            self._attack_miracles = {}
            self._hp_miracles = {}

    @property
    def policy_id(self) -> str:
        if self.manifest.feature_schema_version == RESOURCE_FEATURE_SCHEMA_VERSION:
            return API_RESOURCE_SHADOW_POLICY_ID
        return API_COMBO_SHADOW_POLICY_ID

    @property
    def resource_enabled(self) -> bool:
        return self.manifest.feature_schema_version == RESOURCE_FEATURE_SCHEMA_VERSION

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
                policy_id=self.policy_id,
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
            strict_items = [item for item in items if item is not None]
            if state.phase is ApiPhase.TURN:
                first = strict_items[0]
                is_plain_combo = self._matches_combat_card(
                    first,
                    self._base_cards,
                    stat="attack",
                    is_plus_attack=False,
                ) and all(
                    self._matches_combat_card(
                        item,
                        self._booster_cards,
                        stat="attack",
                        is_plus_attack=True,
                    )
                    for item in strict_items[1:]
                )
                is_resource = (
                    self.resource_enabled
                    and len(strict_items) == 1
                    and self._matches_resource_card(first, state)
                )
                if is_plain_combo or is_resource:
                    macros.append(action)
            elif state.phase is ApiPhase.DEFENSE and all(
                self._matches_combat_card(
                    item,
                    self._armor_cards,
                    stat="defense",
                    is_plus_attack=False,
                )
                for item in strict_items
            ):
                macros.append(action)
        return macros

    @staticmethod
    def _matches_combat_card(
        item: ApiItemState,
        rules: dict[str, tuple[int, CombatElement]],
        *,
        stat: str,
        is_plus_attack: bool,
    ) -> bool:
        rule = rules.get(item.asset or "")
        if rule is None:
            return False
        expected_value, expected_element = rule
        expected_category = "armor" if stat == "defense" else "weapons"
        return (
            item.category == expected_category
            and getattr(item, stat) == expected_value
            and (item.element or "non-element") == expected_element
            and item.ability is None
            and item.cost == 0
            and item.is_plus_attack is is_plus_attack
        )

    def _matches_resource_card(self, item: ApiItemState, state: ApiGameState) -> bool:
        me = next(player for player in state.players if player.is_self)
        asset = item.asset or ""
        if (
            item.category == "sundries"
            and item.cost == 0
            and item.element is None
        ):
            if item.ability == "boostHP":
                return me.hp < 100 and item.ability_value == self._hp_utilities.get(asset)
            if item.ability == "boostMP":
                return me.mp < 100 and item.ability_value == self._mp_utilities.get(asset)
            return False
        attack_rule = self._attack_miracles.get(asset)
        if attack_rule is not None:
            attack, cost, element = attack_rule
            return (
                item.category == "miracles"
                and item.ability is None
                and item.attack == attack
                and item.cost == cost
                and item.cost <= me.mp
                and not item.is_plus_attack
                and (item.element or "non-element") == element
            )
        hp_rule = self._hp_miracles.get(asset)
        if hp_rule is None:
            return False
        utility, cost = hp_rule
        return (
            item.category == "miracles"
            and item.ability == "boostHP"
            and item.ability_value == utility
            and item.cost == cost
            and item.cost <= me.mp
            and item.element is None
            and me.hp < 100
        )

    def _is_atomic_resource(self, item: ApiItemState) -> bool:
        asset = item.asset or ""
        return (
            item.category == "sundries"
            and asset in {*self._hp_utilities, *self._mp_utilities}
        ) or (item.category == "miracles" and asset in self._hp_miracles)

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
            schema_version=(5 if self.resource_enabled else 4),
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
        pass_action = next(
            (action for action in legal_actions.actions if action.kind is ApiActionKind.PASS),
            None,
        )
        if not macros and not (state.phase is ApiPhase.DEFENSE and pass_action is not None):
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
                    action_mask[FORGIVE_ACTION_INDEX] = pass_action is not None
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
                if self.resource_enabled and self._is_atomic_resource(item):
                    proposal = next(
                        (
                            macro
                            for macro in macros
                            if macro.item_instance_ids == (item.instance_id,)
                        ),
                        None,
                    )
                    break
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
                proposal = pass_action
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
                policy_id=self.policy_id,
                state_digest=legal_actions.state_digest,
                chosen_action_id=proposal.action_id,
                scores={
                    action.action_id: float(action.action_id == proposal.action_id)
                    for action in legal_actions.actions
                },
                rationale=(
                    "non-executable learned curriculum proposal; the tactical heuristic "
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
