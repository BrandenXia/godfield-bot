from pathlib import Path

import pytest
import torch

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import ModelStatus, initialize_model, load_model
from godfield_bot.neural import RecurrentPolicyValueNet
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_training import (
    ALGORITHM,
    SimulationTrainingConfig,
    collect_self_play_rollout,
    signed_generalized_advantages,
    train_ppo_rollout,
    train_simulation_candidate,
)

pytest.importorskip("godfield_sim")

SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")


def test_signed_gae_flips_future_value_when_control_changes_seat() -> None:
    advantages, returns = signed_generalized_advantages(
        rewards=torch.tensor([[0.0], [-1.0]]),
        values=torch.zeros((2, 1)),
        actors=torch.tensor([[0], [1]]),
        terminated=torch.tensor([[False], [True]]),
        final_values=torch.zeros(1),
        final_actors=torch.tensor([1]),
        gamma=1.0,
        gae_lambda=1.0,
    )

    torch.testing.assert_close(advantages[:, 0], torch.tensor([1.0, -1.0]))
    torch.testing.assert_close(returns, advantages)


def test_signed_gae_preserves_future_value_for_same_seat() -> None:
    advantages, _ = signed_generalized_advantages(
        rewards=torch.tensor([[0.0], [-1.0]]),
        values=torch.zeros((2, 1)),
        actors=torch.tensor([[1], [1]]),
        terminated=torch.tensor([[False], [True]]),
        final_values=torch.zeros(1),
        final_actors=torch.tensor([1]),
        gamma=1.0,
        gae_lambda=1.0,
    )

    torch.testing.assert_close(advantages[:, 0], torch.tensor([-1.0, -1.0]))


def test_recurrent_rollout_replay_reconstructs_old_policy_before_update() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    torch.manual_seed(67)
    model = RecurrentPolicyValueNet(vocabulary_size=len(vocabulary.tokens), action_count=21)
    simulation = create_attack_defense_simulation(SNAPSHOT, batch_size=4, seed=67)
    rollout = collect_self_play_rollout(
        model,
        simulation,
        rollout_steps=6,
        gamma=0.99,
        gae_lambda=0.95,
        device=torch.device("cpu"),
    )
    chosen_actions_are_legal = rollout.action_mask.gather(
        2,
        rollout.actions.unsqueeze(-1),
    ).squeeze(-1)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)
    metrics = train_ppo_rollout(
        model,
        optimizer,
        rollout,
        SimulationTrainingConfig(
            batch_size=4,
            rollout_steps=6,
            updates=1,
            ppo_epochs=1,
            environment_minibatch_size=4,
        ),
    )

    assert chosen_actions_are_legal.all()
    assert abs(metrics.approximate_kl) < 1e-6
    assert metrics.clip_fraction == 0.0


def test_native_self_play_writes_fingerprinted_non_promotable_candidate(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    model_root = tmp_path / "models"
    parent = initialize_model(
        model_root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )

    candidate = train_simulation_candidate(
        base_model_directory=model_root / parent.model_id,
        model_root=model_root,
        snapshot_path=SNAPSHOT,
        config=SimulationTrainingConfig(
            batch_size=8,
            rollout_steps=4,
            updates=1,
            ppo_epochs=1,
            environment_minibatch_size=4,
            seed=67,
        ),
    )
    loaded_manifest, loaded_model = load_model(model_root / candidate.model_id)

    assert loaded_manifest == candidate
    assert candidate.status is ModelStatus.CANDIDATE
    assert candidate.parent_model_id == parent.model_id
    assert candidate.training_algorithm == ALGORITHM
    assert candidate.training_dataset_sha256 is not None
    assert candidate.training_run_ids == ()
    assert candidate.metrics["training_transitions"] == 32
    assert candidate.metrics["training_updates"] == 1
    assert candidate.training_context["source_kind"] == "native-on-policy-self-play"
    simulation_context = candidate.training_context["simulation"]
    assert isinstance(simulation_context, dict)
    assert simulation_context["ruleset_id"] == "plain-attack-defense-redraw-duel-v1"
    assert simulation_context["promotion_eligible"] is False
    assert loaded_model.global_feature_count == 6
