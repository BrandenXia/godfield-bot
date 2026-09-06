from pathlib import Path

from pydantic import BaseModel, model_validator

from godfield_bot.domain.action import ActionKind, LegalActionSet
from godfield_bot.domain.game import GameState
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.legal_actions import game_state_digest

PAD_TOKEN = "<PAD>"
UNKNOWN_TOKEN = "<UNKNOWN>"
TRADE_TOKENS = ("trade/buy", "trade/exchange", "trade/sell")
ARTIFACT_ACTION_OFFSET = 1


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
    schema_version: int = 1
    global_features: tuple[float, ...]
    player_features: tuple[tuple[float, ...], ...]
    player_mask: tuple[bool, ...]
    hand_token_ids: tuple[int, ...]
    hand_mask: tuple[bool, ...]
    action_mask: tuple[bool, ...]


class StateFeatureEncoder:
    global_feature_count = 4
    player_feature_count = 4

    def __init__(
        self,
        vocabulary: ArtifactVocabulary,
        *,
        max_players: int = 9,
        max_hand_slots: int = 9,
    ) -> None:
        if max_players < 2 or max_hand_slots < 1:
            raise ValueError("feature limits must support a playable game")
        self.vocabulary = vocabulary
        self.max_players = max_players
        self.max_hand_slots = max_hand_slots

    def encode(self, state: GameState, legal_actions: LegalActionSet) -> StateFeatures:
        if legal_actions.state_digest != game_state_digest(state):
            raise FeatureEncodingError("legal actions do not belong to this game state")
        if len(state.players) > self.max_players:
            raise FeatureEncodingError("player count exceeds model capacity")
        if len(state.hand) > self.max_hand_slots:
            raise FeatureEncodingError("hand size exceeds model capacity")

        self_player = state.players[state.self_player_index]
        global_features = (
            min(state.field_number, 100) / 100.0,
            min(self_player.hp, 100) / 100.0,
            min(self_player.mp, 100) / 100.0,
            min(self_player.money, 100) / 100.0,
        )
        players: list[tuple[float, ...]] = [
            (
                min(player.hp, 100) / 100.0,
                min(player.mp, 100) / 100.0,
                min(player.money, 100) / 100.0,
                float(player.is_self),
            )
            for player in state.players
        ]
        player_mask = [True] * len(players)
        while len(players) < self.max_players:
            players.append((0.0,) * self.player_feature_count)
            player_mask.append(False)

        hand_tokens = [
            self.vocabulary.token_id(artifact.category, artifact.slug) for artifact in state.hand
        ]
        hand_mask = [True] * len(hand_tokens)
        while len(hand_tokens) < self.max_hand_slots:
            hand_tokens.append(0)
            hand_mask.append(False)

        target_action_offset = ARTIFACT_ACTION_OFFSET + self.max_hand_slots
        forgive_action_index = target_action_offset + self.max_players
        confirm_action_index = forgive_action_index + 1
        action_mask = [False] * (confirm_action_index + 1)
        for action in legal_actions.actions:
            if action.kind is ActionKind.WAIT:
                action_mask[0] = True
            elif action.kind is ActionKind.SELECT_ARTIFACT:
                if action.artifact_slot is None or action.artifact_slot >= self.max_hand_slots:
                    raise FeatureEncodingError("artifact action has an invalid slot")
                action_mask[ARTIFACT_ACTION_OFFSET + action.artifact_slot] = True
            elif action.kind is ActionKind.SELECT_TARGET:
                if (
                    action.target_player_index is None
                    or action.target_player_index >= self.max_players
                ):
                    raise FeatureEncodingError("target action has an invalid player index")
                action_mask[target_action_offset + action.target_player_index] = True
            elif action.kind is ActionKind.FORGIVE:
                action_mask[forgive_action_index] = True
            elif action.kind is ActionKind.CONFIRM:
                action_mask[confirm_action_index] = True
            else:
                raise FeatureEncodingError(
                    f"action kind {action.kind} is outside the neural action head"
                )
        if not any(action_mask):
            raise FeatureEncodingError("neural action mask has no legal action")

        return StateFeatures(
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
