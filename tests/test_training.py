import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
import torch

from godfield_bot.domain.action import (
    ActionExecutionResult,
    ActionKind,
    LegalAction,
    LegalActionSet,
    PolicyDecision,
)
from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.replay import ReplaySample
from godfield_bot.features import StateFeatureEncoder, action_index, load_vocabulary
from godfield_bot.imitation import ImitationTrainingConfig, train_imitation_candidate
from godfield_bot.legal_actions import game_state_digest, observation_only_actions
from godfield_bot.model_registry import ModelStatus, initialize_model, load_model
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors
from godfield_bot.runner import build_action_transition
from godfield_bot.training import (
    TrainingError,
    actor_critic_loss,
    behavior_cloning_sequence_step,
    train_step,
)

SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")


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
    assert loaded_model.policy_head.out_features == 21
    assert stat.S_IMODE((model_directory / "weights.pt").stat().st_mode) == 0o600


def imitation_sample() -> ReplaySample:
    before = state()
    after = before.model_copy(
        update={
            "observed_at": datetime.now(UTC),
            "field_number": 1,
            "players": (
                before.players[0],
                before.players[1].model_copy(update={"hp": 38}),
            ),
        }
    )
    chosen = LegalAction(
        action_id="forgive",
        kind=ActionKind.FORGIVE,
        label="Forgive verified incoming effect",
        artifact_asset_path="/images/items/weapons/bronze-club.webp",
        target_player_index=0,
        target_player_name="ロキ-67",
        control_panel="right",
    )
    legal_actions = LegalActionSet(
        state_digest=game_state_digest(before),
        actions=(
            LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),
            chosen,
        ),
        coverage_complete=False,
        blocked_reason="fixture covers one verified action",
    )
    decision = PolicyDecision(
        decided_at=datetime.now(UTC),
        policy_id="heuristic-v0",
        state_digest=legal_actions.state_digest,
        chosen_action_id=chosen.action_id,
        scores={"wait": 0.0, "forgive": 1.0},
        rationale="fixture",
        executable=True,
    )
    execution = ActionExecutionResult(
        executed_at=datetime.now(UTC),
        action_id=chosen.action_id,
        kind=chosen.kind,
        dispatched=True,
        latency_ms=1,
    )
    return ReplaySample(
        run_id="fixture-run",
        transition_sequence=4,
        client_sha256=BibleSnapshot.model_validate_json(
            SNAPSHOT.read_text(encoding="utf-8")
        ).client.sha256,
        policy_id="heuristic-v0",
        before_state=before,
        legal_actions=legal_actions,
        chosen_action=chosen,
        decision=decision,
        execution=execution,
        after_state=after,
        transition=build_action_transition(chosen.action_id, before, after),
    )


def test_behavior_cloning_updates_policy_without_value_target() -> None:
    torch.manual_seed(67)
    vocabulary = load_vocabulary(SNAPSHOT)
    sample = imitation_sample()
    features = StateFeatureEncoder(vocabulary).encode(
        sample.before_state,
        sample.legal_actions,
    )
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=len(features.action_mask),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    policy_before = model.policy_head.weight.detach().clone()
    value_before = model.value_head.weight.detach().clone()

    metrics = behavior_cloning_sequence_step(
        model,
        optimizer,
        [features],
        [action_index(sample.chosen_action)],
    )

    assert metrics.loss > 0
    assert not torch.equal(policy_before, model.policy_head.weight.detach())
    assert torch.equal(value_before, model.value_head.weight.detach())


def test_replay_training_writes_immutable_candidate_lineage(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = load_vocabulary(SNAPSHOT)
    root = tmp_path / "models"
    parent = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )
    replay = tmp_path / "replay.jsonl"
    replay.write_text(imitation_sample().model_dump_json() + "\n", encoding="utf-8")

    candidate = train_imitation_candidate(
        base_model_directory=root / parent.model_id,
        model_root=root,
        replay_path=replay,
        snapshot_path=SNAPSHOT,
        config=ImitationTrainingConfig(epochs=2),
    )
    loaded_manifest, _ = load_model(root / candidate.model_id)

    assert candidate.status is ModelStatus.CANDIDATE
    assert candidate.parent_model_id == parent.model_id
    assert candidate.training_algorithm == "behavior-cloning-v0"
    assert candidate.training_dataset_sha256 is not None
    assert candidate.training_run_ids == ("fixture-run",)
    assert candidate.metrics["training_samples"] == 1
    assert loaded_manifest == candidate
    assert (root / parent.model_id / "manifest.json").read_text(encoding="utf-8") == (
        parent.model_dump_json(indent=2) + "\n"
    )
