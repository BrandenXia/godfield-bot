import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
import torch

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.features import StateFeatureEncoder, load_vocabulary
from godfield_bot.legal_actions import observation_only_actions
from godfield_bot.model_registry import initialize_model, load_model
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors
from godfield_bot.training import TrainingError, actor_critic_loss, train_step

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


def test_actor_critic_rejects_illegal_replay_target() -> None:
    minimum = torch.finfo(torch.float32).min
    logits = torch.tensor([[0.0, minimum]])

    with pytest.raises(TrainingError, match="masked as illegal"):
        actor_critic_loss(
            logits,
            torch.tensor([0.0]),
            torch.tensor([1]),
            torch.tensor([1.0]),
        )


def test_train_step_updates_recurrent_model() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    game_state = state()
    features = StateFeatureEncoder(vocabulary).encode(
        game_state,
        observation_only_actions(game_state),
    )
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=len(features.action_mask),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    before = model.value_head.weight.detach().clone()

    metrics = train_step(
        model,
        optimizer,
        features_to_tensors([features]),
        torch.tensor([0]),
        torch.tensor([1.0]),
    )

    assert metrics.total_loss > 0
    assert not torch.equal(before, model.value_head.weight.detach())


def test_initialized_model_round_trips_with_checksums(tmp_path) -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    manifest = initialize_model(
        tmp_path / "models",
        vocabulary,
        client_sha256="a" * 64,
    )
    model_directory = tmp_path / "models" / manifest.model_id

    loaded_manifest, loaded_model = load_model(model_directory)

    assert loaded_manifest == manifest
    assert loaded_model.policy_head.out_features == 10
    assert stat.S_IMODE((model_directory / "weights.pt").stat().st_mode) == 0o600
