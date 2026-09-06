from datetime import UTC, datetime
from pathlib import Path

import torch

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.features import StateFeatureEncoder, load_vocabulary
from godfield_bot.legal_actions import observation_only_actions
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors

SNAPSHOT = Path("data/snapshots/2026-09-06/bible.json")


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
    features = StateFeatureEncoder(vocabulary).encode(
        game_state,
        observation_only_actions(game_state),
    )

    assert len(vocabulary.tokens) == 296
    assert len(features.player_features) == 9
    assert len(features.hand_token_ids) == 9
    assert features.hand_token_ids[0] > 1
    assert features.action_mask == (
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    )


def test_recurrent_policy_masks_actions_and_backpropagates() -> None:
    torch.manual_seed(67)
    vocabulary = load_vocabulary(SNAPSHOT)
    game_state = state()
    features = StateFeatureEncoder(vocabulary).encode(
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

    assert logits.shape == (1, 10)
    assert value.shape == (1,)
    assert recurrent_state.shape == (1, 128)
    assert logits[0, 0].isfinite()
    assert logits[0, 1] == torch.finfo(logits.dtype).min
    assert model.policy_head.weight.grad is not None
