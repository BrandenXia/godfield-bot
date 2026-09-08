from datetime import UTC, datetime
from pathlib import Path

import pytest
import torch

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import StateFeatureEncoder, action_index, load_vocabulary
from godfield_bot.legal_actions import game_state_digest, observation_only_actions
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors

SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")
BIBLE = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))


def state() -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=0,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=40, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=40, mp=10, money=20, is_self=False),
        ),
        hand=(
            HandArtifact(
                slot=0,
                category="weapons",
                slug="bronze-club",
                asset_path="/images/items/weapons/bronze-club.webp",
                bounds=Bounds(x=200, y=493, width=80, height=80),
            ),
        ),
        scene_layers=("/images/screens/fog.webp",),
    )


def test_snapshot_vocabulary_and_feature_shapes() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    game_state = state()
    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
        game_state,
        observation_only_actions(game_state),
    )

    assert len(vocabulary.tokens) == 296
    assert features.schema_version == 3
    assert features.global_features == (0.0, 0.4, 0.1, 0.2, 0.0, 0.0, *([0.0] * 7))
    assert len(features.player_features) == 9
    assert len(features.hand_token_ids) == 9
    assert features.hand_token_ids[0] > 1
    assert len(features.action_mask) == 21
    assert features.action_mask[0] is True
    assert not any(features.action_mask[1:])


def test_live_response_features_encode_phase_and_pending_attack() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    response_state = state().model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_display": "ATK13",
            "phase_control": "Forgive",
        }
    )

    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
        response_state,
        observation_only_actions(response_state),
    )

    assert features.global_features == (
        0.0,
        0.4,
        0.1,
        0.2,
        1.0,
        0.13,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )


def test_live_response_features_encode_pending_attack_element() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = load_vocabulary(SNAPSHOT)
    response_state = state().model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_display": "ATK1",
            "action_artifact_asset_path": "/images/items/weapons/torch.webp",
            "phase_control": "Forgive",
        }
    )

    features = StateFeatureEncoder(vocabulary, snapshot).encode(
        response_state,
        observation_only_actions(response_state),
    )

    assert features.global_features[6:13] == (0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_outgoing_attack_is_not_encoded_as_a_defense_response() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    attack_state = state().model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_target": "CPU",
            "action_display": "ATK13",
        }
    )

    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
        attack_state,
        observation_only_actions(attack_state),
    )

    assert features.global_features[4:] == (0.0,) * 9


def test_recurrent_policy_masks_actions_and_backpropagates() -> None:
    torch.manual_seed(67)
    vocabulary = load_vocabulary(SNAPSHOT)
    game_state = state()
    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
        game_state,
        observation_only_actions(game_state),
    )
    tensors = features_to_tensors([features])
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=len(features.action_mask),
    )

    logits, value, recurrent_state = model(*tensors)
    loss = logits[:, 0].sum() + value.sum()
    loss.backward()

    assert logits.shape == (1, 21)
    assert value.shape == (1,)
    assert recurrent_state.shape == (1, 128)
    assert logits[0, 0].isfinite()
    assert logits[0, 1] == torch.finfo(logits.dtype).min
    assert model.policy_head.weight.grad is not None


def test_recurrent_policy_rejects_legacy_global_feature_shape() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    model = RecurrentPolicyValueNet(vocabulary_size=len(vocabulary.tokens), action_count=21)

    with torch.no_grad(), pytest.raises(ValueError, match="global feature shape"):
        model(
            torch.zeros((1, 4)),
            torch.zeros((1, 9, 4)),
            torch.ones((1, 9), dtype=torch.bool),
            torch.zeros((1, 9), dtype=torch.long),
            torch.ones((1, 9), dtype=torch.bool),
            torch.ones((1, 21), dtype=torch.bool),
        )


def test_slot_aware_policy_moves_card_scores_with_the_cards() -> None:
    torch.manual_seed(67)
    model = RecurrentPolicyValueNet(vocabulary_size=8, action_count=21)
    global_features = torch.zeros((1, 13))
    player_features = torch.zeros((1, 2, 4))
    player_mask = torch.ones((1, 2), dtype=torch.bool)
    hand_mask = torch.tensor([[True, True, False, False, False, False, False, False, False]])
    action_mask = torch.zeros((1, 21), dtype=torch.bool)
    action_mask[:, 1:3] = True
    first_hand = torch.tensor([[2, 3, 0, 0, 0, 0, 0, 0, 0]])
    swapped_hand = torch.tensor([[3, 2, 0, 0, 0, 0, 0, 0, 0]])

    first_logits, _, _ = model(
        global_features,
        player_features,
        player_mask,
        first_hand,
        hand_mask,
        action_mask,
    )
    swapped_logits, _, _ = model(
        global_features,
        player_features,
        player_mask,
        swapped_hand,
        hand_mask,
        action_mask,
    )

    assert first_logits[0, 1] != first_logits[0, 2]
    torch.testing.assert_close(first_logits[0, 1], swapped_logits[0, 2])
    torch.testing.assert_close(first_logits[0, 2], swapped_logits[0, 1])


def test_target_action_uses_player_segment_of_action_head() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    game_state = state()
    legal_actions = LegalActionSet(
        state_digest=game_state_digest(game_state),
        actions=(
            LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),
            LegalAction(
                action_id="target:1:CPU",
                kind=ActionKind.SELECT_TARGET,
                label="Target CPU",
                target_player_index=1,
                target_player_name="CPU",
            ),
        ),
        coverage_complete=False,
        blocked_reason="test fixture covers only target selection",
    )

    features = StateFeatureEncoder(vocabulary, BIBLE).encode(game_state, legal_actions)

    assert [index for index, allowed in enumerate(features.action_mask) if allowed] == [0, 11]


def test_confirm_action_uses_final_action_head_slot() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    game_state = state()
    legal_actions = LegalActionSet(
        state_digest=game_state_digest(game_state),
        actions=(
            LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),
            LegalAction(
                action_id="confirm:attack:bronze-club:1:CPU",
                kind=ActionKind.CONFIRM,
                label="Confirm attack",
                artifact_asset_path="/images/items/weapons/bronze-club.webp",
                target_player_index=1,
                target_player_name="CPU",
                control_panel="left",
            ),
        ),
        coverage_complete=False,
        blocked_reason="test fixture covers only confirmation",
    )

    features = StateFeatureEncoder(vocabulary, BIBLE).encode(game_state, legal_actions)

    assert [index for index, allowed in enumerate(features.action_mask) if allowed] == [0, 20]
    assert action_index(legal_actions.actions[1]) == 20
