import re
from collections.abc import Collection
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, model_validator

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import COMBAT_ELEMENT_IDS, COMBAT_ELEMENTS, ELEMENT_IMAGE_PATHS
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.reference import (
    verified_absorption_weapon_cards,
    verified_attack_twice_weapon_cards,
    verified_chance_absorption_weapon_cards,
    verified_dark_cloud_miracles,
    verified_dark_cloud_weapon_cards,
    verified_dream_miracles,
    verified_dream_weapon_cards,
    verified_effect_attack_miracle_cards,
    verified_fog_flash_attack_miracles,
    verified_fog_flash_weapon_cards,
    verified_fog_miracles,
    verified_illness_weapon_cards,
    verified_same_damage_weapon_cards,
)

PAD_TOKEN = "<PAD>"
UNKNOWN_TOKEN = "<UNKNOWN>"
TRADE_TOKENS = ("trade/buy", "trade/exchange", "trade/sell")
ARTIFACT_ACTION_OFFSET = 1
LEGACY_FEATURE_SCHEMA_VERSION = 2
LEGACY_GLOBAL_FEATURE_COUNT = 6
ELEMENT_FEATURE_SCHEMA_VERSION = 3
FEATURE_SCHEMA_VERSION = 4
RESOURCE_FEATURE_SCHEMA_VERSION = 5
GLOBAL_FEATURE_COUNT = LEGACY_GLOBAL_FEATURE_COUNT + len(COMBAT_ELEMENTS)
STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION = 6
STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT = GLOBAL_FEATURE_COUNT + 1
ILLNESS_FEATURE_SCHEMA_VERSION = 7
ILLNESS_GLOBAL_FEATURE_COUNT = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT + 2
CURSE_FEATURE_SCHEMA_VERSION = 8
CURSE_GLOBAL_FEATURE_COUNT = ILLNESS_GLOBAL_FEATURE_COUNT + 4
DARK_CLOUD_FEATURE_SCHEMA_VERSION = 9
DARK_CLOUD_GLOBAL_FEATURE_COUNT = CURSE_GLOBAL_FEATURE_COUNT + 2
DREAM_FEATURE_SCHEMA_VERSION = 10
WIDE_HAND_FEATURE_SCHEMA_VERSION = 11
DREAM_GLOBAL_FEATURE_COUNT = DARK_CLOUD_GLOBAL_FEATURE_COUNT + 2
PLAYER_FEATURE_COUNT = 4
ATTACK_DISPLAY_PATTERN = re.compile(r"^ATK(\d+)$")


def action_index(
    action: LegalAction,
    *,
    max_players: int = 9,
    max_hand_slots: int = 9,
) -> int:
    """Map one typed action onto the versioned neural action head."""

    target_action_offset = ARTIFACT_ACTION_OFFSET + max_hand_slots
    forgive_action_index = target_action_offset + max_players
    confirm_action_index = forgive_action_index + 1
    if action.kind is ActionKind.WAIT:
        return 0
    if action.kind is ActionKind.SELECT_ARTIFACT:
        if action.artifact_slot is None or action.artifact_slot >= max_hand_slots:
            raise FeatureEncodingError("artifact action has an invalid slot")
        return ARTIFACT_ACTION_OFFSET + action.artifact_slot
    if action.kind is ActionKind.SELECT_TARGET:
        if action.target_player_index is None or action.target_player_index >= max_players:
            raise FeatureEncodingError("target action has an invalid player index")
        return target_action_offset + action.target_player_index
    if action.kind in {ActionKind.PASS, ActionKind.FORGIVE}:
        return forgive_action_index
    if action.kind in {
        ActionKind.CONFIRM,
        ActionKind.CONFIRM_CHANCE,
        ActionKind.CONFIRM_UTILITY,
    }:
        return confirm_action_index
    raise FeatureEncodingError(f"action kind {action.kind} is outside the neural action head")


class FeatureEncodingError(RuntimeError):
    """Raised when state cannot fit the versioned neural input contract."""


class ArtifactVocabulary(BaseModel):
    schema_version: int = 1
    tokens: tuple[str, ...]

    @model_validator(mode="after")
    def validate_tokens(self) -> "ArtifactVocabulary":
        if self.tokens[:2] != (PAD_TOKEN, UNKNOWN_TOKEN):
            raise ValueError("artifact vocabulary must begin with PAD and UNKNOWN")
        if len(self.tokens) != len(set(self.tokens)):
            raise ValueError("artifact vocabulary tokens must be unique")
        return self

    @classmethod
    def from_snapshot(cls, snapshot: BibleSnapshot) -> "ArtifactVocabulary":
        artifacts = {
            f"{category_name}/{artifact.asset}"
            for category_name, category in snapshot.catalog.items()
            for artifact in category.items
        }
        artifacts.update(TRADE_TOKENS)
        return cls(tokens=(PAD_TOKEN, UNKNOWN_TOKEN, *sorted(artifacts)))

    def token_id(self, category: str, slug: str) -> int:
        token = f"{category}/{slug}"
        try:
            return self.tokens.index(token)
        except ValueError:
            return 1


class StateFeatures(BaseModel):
    schema_version: Literal[4, 5, 6, 7, 8, 9, 10, 11] = 4
    global_features: tuple[float, ...]
    player_features: tuple[tuple[float, ...], ...]
    player_mask: tuple[bool, ...]
    hand_token_ids: tuple[int, ...]
    hand_mask: tuple[bool, ...]
    action_mask: tuple[bool, ...]


class StateFeatureEncoder:
    player_feature_count = PLAYER_FEATURE_COUNT

    def __init__(
        self,
        vocabulary: ArtifactVocabulary,
        snapshot: BibleSnapshot,
        *,
        max_players: int = 9,
        max_hand_slots: int = 9,
        feature_schema_version: int = FEATURE_SCHEMA_VERSION,
    ) -> None:
        if max_players < 2 or max_hand_slots < 1:
            raise ValueError("feature limits must support a playable game")
        global_feature_counts = {
            FEATURE_SCHEMA_VERSION: GLOBAL_FEATURE_COUNT,
            RESOURCE_FEATURE_SCHEMA_VERSION: GLOBAL_FEATURE_COUNT,
            STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION: (STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT),
            ILLNESS_FEATURE_SCHEMA_VERSION: ILLNESS_GLOBAL_FEATURE_COUNT,
            CURSE_FEATURE_SCHEMA_VERSION: CURSE_GLOBAL_FEATURE_COUNT,
            DARK_CLOUD_FEATURE_SCHEMA_VERSION: DARK_CLOUD_GLOBAL_FEATURE_COUNT,
            DREAM_FEATURE_SCHEMA_VERSION: DREAM_GLOBAL_FEATURE_COUNT,
            WIDE_HAND_FEATURE_SCHEMA_VERSION: DREAM_GLOBAL_FEATURE_COUNT,
        }
        if feature_schema_version not in global_feature_counts:
            raise ValueError("browser features require feature schema v4 through v11")
        if feature_schema_version == WIDE_HAND_FEATURE_SCHEMA_VERSION and (
            max_hand_slots != 18 or max_players != 9
        ):
            raise ValueError("schema v11 requires 18 hand slots and nine target slots")
        self.vocabulary = vocabulary
        self.max_players = max_players
        self.max_hand_slots = max_hand_slots
        self.feature_schema_version = cast(
            Literal[4, 5, 6, 7, 8, 9, 10, 11],
            feature_schema_version,
        )
        self.global_feature_count = global_feature_counts[feature_schema_version]
        self.artifact_element_ids: dict[str, int] = {}
        for category in snapshot.catalog.values():
            for artifact in category.items:
                if not artifact.element_image_paths:
                    self.artifact_element_ids[artifact.image_path] = 0
                elif len(artifact.element_image_paths) == 1:
                    element = ELEMENT_IMAGE_PATHS.get(artifact.element_image_paths[0])
                    if element is not None:
                        self.artifact_element_ids[artifact.image_path] = COMBAT_ELEMENT_IDS[element]
        self.pending_effects: dict[str, float] = {}
        self.ambiguous_pending_effects: set[str] = set()
        self._register_pending_effects(
            snapshot,
            "weapons",
            {
                *verified_absorption_weapon_cards(snapshot),
                *verified_chance_absorption_weapon_cards(snapshot),
            },
            1.0,
        )
        self._register_pending_effects(
            snapshot,
            "miracles",
            {
                slug
                for slug, rule in verified_effect_attack_miracle_cards(snapshot).items()
                if rule[3] == "absorbHP"
            },
            1.0,
        )
        self._register_pending_effects(
            snapshot,
            "weapons",
            verified_same_damage_weapon_cards(snapshot),
            -1.0,
        )
        self._register_pending_effects(
            snapshot,
            "weapons",
            {
                slug
                for slug, rule in verified_illness_weapon_cards(snapshot).items()
                if rule[2] == 1
            },
            0.5,
        )
        self._register_pending_effects(
            snapshot,
            "weapons",
            {
                slug
                for slug, rule in verified_illness_weapon_cards(snapshot).items()
                if rule[2] == 3
            },
            0.75,
        )
        fog_flash_weapons = verified_fog_flash_weapon_cards(snapshot)
        self._register_pending_effects(
            snapshot,
            "weapons",
            {slug for slug, rule in fog_flash_weapons.items() if rule[3] == "fog"},
            0.875,
        )
        self._register_pending_effects(
            snapshot,
            "weapons",
            {slug for slug, rule in fog_flash_weapons.items() if rule[3] == "flash"},
            -0.875,
        )
        fog_flash_miracles = verified_fog_flash_attack_miracles(snapshot)
        self._register_pending_effects(
            snapshot,
            "miracles",
            {slug for slug, rule in fog_flash_miracles.items() if rule[4] == "fog"},
            0.875,
        )
        self._register_pending_effects(
            snapshot,
            "miracles",
            {slug for slug, rule in fog_flash_miracles.items() if rule[4] == "flash"},
            -0.875,
        )
        self._register_pending_effects(
            snapshot,
            "miracles",
            verified_fog_miracles(snapshot),
            0.875,
        )
        self._register_pending_effects(
            snapshot,
            "weapons",
            verified_dark_cloud_weapon_cards(snapshot),
            -0.75,
        )
        self._register_pending_effects(
            snapshot,
            "miracles",
            verified_dark_cloud_miracles(snapshot),
            -0.75,
        )
        self._register_pending_effects(
            snapshot,
            "weapons",
            verified_dream_weapon_cards(snapshot),
            -0.625,
        )
        self._register_pending_effects(
            snapshot,
            "miracles",
            verified_dream_miracles(snapshot),
            -0.625,
        )
        self._register_ambiguous_pending_effects(
            snapshot,
            "weapons",
            verified_attack_twice_weapon_cards(snapshot),
        )

    def _register_pending_effects(
        self,
        snapshot: BibleSnapshot,
        category: str,
        slugs: Collection[str],
        encoded_effect: float,
    ) -> None:
        selected_slugs = set(slugs)
        for artifact in snapshot.catalog[category].items:
            if artifact.asset in selected_slugs:
                self.pending_effects[artifact.image_path] = encoded_effect

    def _register_ambiguous_pending_effects(
        self,
        snapshot: BibleSnapshot,
        category: str,
        slugs: Collection[str],
    ) -> None:
        selected_slugs = set(slugs)
        for artifact in snapshot.catalog[category].items:
            if artifact.asset in selected_slugs:
                self.ambiguous_pending_effects.add(artifact.image_path)

    def encode(self, state: GameState, legal_actions: LegalActionSet) -> StateFeatures:
        if legal_actions.state_digest != game_state_digest(state):
            raise FeatureEncodingError("legal actions do not belong to this game state")
        if any(not player.stats_visible for player in state.players):
            raise FeatureEncodingError(
                "hidden player statistics require a visibility-aware feature schema"
            )
        if len(state.players) > self.max_players:
            raise FeatureEncodingError("player count exceeds model capacity")
        if (
            self.feature_schema_version >= ILLNESS_FEATURE_SCHEMA_VERSION
            and len(state.players) != 2
        ):
            raise FeatureEncodingError("schema-v7+ browser features require exactly two players")
        if len(state.hand) > self.max_hand_slots and any(
            action.kind is ActionKind.SELECT_ARTIFACT
            and action.artifact_slot is not None
            and action.artifact_slot >= self.max_hand_slots
            for action in legal_actions.actions
        ):
            raise FeatureEncodingError(
                "hand size exceeds model capacity with a selectable overflow slot"
            )

        self_player = state.players[state.self_player_index]
        is_response_phase = (
            state.action_actor is not None
            and state.action_actor != self_player.name
            and state.action_target == self_player.name
            and state.phase_control is not None
        )
        is_outgoing_selection = (
            state.action_actor == self_player.name and state.phase_control is not None
        )
        pending_attack_match = (
            ATTACK_DISPLAY_PATTERN.fullmatch(state.action_display)
            if (is_response_phase or is_outgoing_selection) and state.action_display is not None
            else None
        )
        pending_attack = int(pending_attack_match.group(1)) if pending_attack_match else 0
        pending_element_features = [0.0] * len(COMBAT_ELEMENTS)
        if is_response_phase or is_outgoing_selection:
            if state.action_artifact_asset_path is None:
                pending_element_features[COMBAT_ELEMENT_IDS["non-element"]] = 1.0
            elif (
                pending_element := self.artifact_element_ids.get(state.action_artifact_asset_path)
            ) is not None:
                pending_element_features[pending_element] = 1.0
        global_features: tuple[float, ...] = (
            min(state.field_number, 100) / 100.0,
            min(self_player.hp, 100) / 100.0,
            min(self_player.mp, 100) / 100.0,
            (
                0.0
                if self.feature_schema_version >= STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION
                else min(self_player.money, 100) / 100.0
            ),
            float(is_response_phase),
            min(pending_attack, 100) / 100.0,
            *pending_element_features,
        )
        if self.feature_schema_version >= STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION:
            pending_effect = 0.0
            if is_response_phase and state.action_artifact_asset_path is not None:
                if state.action_artifact_asset_path in self.ambiguous_pending_effects:
                    raise FeatureEncodingError(
                        "attack-twice response does not expose its remaining-strike count"
                    )
                pending_effect = self.pending_effects.get(
                    state.action_artifact_asset_path,
                    0.0,
                )
            global_features += (pending_effect,)
        if self.feature_schema_version >= ILLNESS_FEATURE_SCHEMA_VERSION:
            opponent = next(player for player in state.players if not player.is_self)
            global_features += (
                self_player.illness_stage / 4.0,
                opponent.illness_stage / 4.0,
            )
        if self.feature_schema_version >= CURSE_FEATURE_SCHEMA_VERSION:
            global_features += (
                float(self_player.fogged),
                float(opponent.fogged),
                float(self_player.flashed),
                float(opponent.flashed),
            )
        if self.feature_schema_version >= DARK_CLOUD_FEATURE_SCHEMA_VERSION:
            global_features += (
                float(self_player.dark_clouded),
                float(opponent.dark_clouded),
            )
        if self.feature_schema_version >= DREAM_FEATURE_SCHEMA_VERSION:
            global_features += (
                float(self_player.dreaming),
                float(opponent.dreaming),
            )
        if len(global_features) != self.global_feature_count:
            raise FeatureEncodingError("browser global feature width is inconsistent")
        players: list[tuple[float, ...]] = [
            (
                min(player.hp, 100) / 100.0,
                min(player.mp, 100) / 100.0,
                (
                    0.0
                    if self.feature_schema_version >= STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION
                    else min(player.money, 100) / 100.0
                ),
                float(player.is_self),
            )
            for player in state.players
        ]
        player_mask = [True] * len(players)
        while len(players) < self.max_players:
            players.append((0.0,) * self.player_feature_count)
            player_mask.append(False)

        hand_tokens = [
            self.vocabulary.token_id(artifact.category, artifact.slug)
            for artifact in state.hand[: self.max_hand_slots]
        ]
        hand_mask = [True] * len(hand_tokens)
        while len(hand_tokens) < self.max_hand_slots:
            hand_tokens.append(0)
            hand_mask.append(False)

        confirm_action_index = ARTIFACT_ACTION_OFFSET + self.max_hand_slots + self.max_players + 1
        action_mask = [False] * (confirm_action_index + 1)
        for action in legal_actions.actions:
            index = action_index(
                action,
                max_players=self.max_players,
                max_hand_slots=self.max_hand_slots,
            )
            action_mask[index] = True
        if not any(action_mask):
            raise FeatureEncodingError("neural action mask has no legal action")

        return StateFeatures(
            schema_version=self.feature_schema_version,
            global_features=global_features,
            player_features=tuple(players),
            player_mask=tuple(player_mask),
            hand_token_ids=tuple(hand_tokens),
            hand_mask=tuple(hand_mask),
            action_mask=tuple(action_mask),
        )


def load_vocabulary(snapshot_path: Path) -> ArtifactVocabulary:
    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    return ArtifactVocabulary.from_snapshot(snapshot)
