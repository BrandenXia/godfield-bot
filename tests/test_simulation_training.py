import hashlib
from pathlib import Path

import pytest
import torch

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
    ELEMENT_FEATURE_SCHEMA_VERSION,
    LEGACY_FEATURE_SCHEMA_VERSION,
    LEGACY_GLOBAL_FEATURE_COUNT,
    RESOURCE_FEATURE_SCHEMA_VERSION,
    ArtifactVocabulary,
)
from godfield_bot.model_registry import ModelManifest, ModelStatus, initialize_model, load_model
from godfield_bot.neural import POOLED_HAND_POLICY, RecurrentPolicyValueNet
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_policy import build_curriculum_heuristic
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


def test_training_config_selects_versioned_mixed_hand_ruleset() -> None:
    assert SimulationTrainingConfig(ruleset="mixed-hand").ruleset == "mixed-hand"
    assert SimulationTrainingConfig(ruleset="elemental-hand").ruleset == "elemental-hand"
    assert SimulationTrainingConfig(ruleset="combo-hand").ruleset == "combo-hand"
    assert SimulationTrainingConfig(ruleset="resource-hand").ruleset == "resource-hand"
    assert (
        SimulationTrainingConfig(ruleset="expanded-resource-hand").ruleset
        == "expanded-resource-hand"
    )


def initialize_fixed_simulation_model(
    root: Path,
    vocabulary: ArtifactVocabulary,
    *,
    client_sha256: str,
) -> ModelManifest:
    return initialize_model(
        root,
        vocabulary,
        client_sha256=client_sha256,
        feature_schema_version=LEGACY_FEATURE_SCHEMA_VERSION,
        global_feature_count=LEGACY_GLOBAL_FEATURE_COUNT,
    )


def legacy_pooled_model(root: Path) -> Path:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    manifest = initialize_fixed_simulation_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )
    model_directory = root / manifest.model_id
    architecture = manifest.architecture.model_copy(
        update={"policy_architecture": POOLED_HAND_POLICY}
    )
    model = RecurrentPolicyValueNet(**architecture.model_dump())
    weights_path = model_directory / manifest.weights_file
    torch.save(model.state_dict(), weights_path)
    legacy_manifest = manifest.model_copy(
        update={
            "schema_version": 2,
            "architecture": architecture,
            "weights_sha256": hashlib.sha256(weights_path.read_bytes()).hexdigest(),
        }
    )
    (model_directory / "manifest.json").write_text(
        legacy_manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return model_directory


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
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=21,
        global_feature_count=LEGACY_GLOBAL_FEATURE_COUNT,
    )
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
    assert rollout.policy_trainable.all()
    assert abs(metrics.approximate_kl) < 1e-6
    assert metrics.clip_fraction == 0.0


def test_rollout_masks_frozen_heuristic_actions_from_policy_training() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=21,
        global_feature_count=LEGACY_GLOBAL_FEATURE_COUNT,
    )
    simulation = create_attack_defense_simulation(SNAPSHOT, batch_size=8, seed=67)

    rollout = collect_self_play_rollout(
        model,
        simulation,
        rollout_steps=8,
        gamma=0.99,
        gae_lambda=0.95,
        device=torch.device("cpu"),
        heuristic=build_curriculum_heuristic(snapshot, vocabulary),
        heuristic_opponent_fraction=1.0,
    )

    assert rollout.policy_trainable.any()
    assert (~rollout.policy_trainable).any()
    assert rollout.action_mask.gather(2, rollout.actions.unsqueeze(-1)).all()


def test_legacy_pooled_checkpoint_loads_but_cannot_continue_simulator_training(
    tmp_path: Path,
) -> None:
    model_root = tmp_path / "models"
    model_directory = legacy_pooled_model(model_root)

    manifest, model = load_model(model_directory)

    assert manifest.schema_version == 2
    assert manifest.architecture.policy_architecture == POOLED_HAND_POLICY
    assert model.artifact_policy_head is None
    with pytest.raises(ValueError, match="requires a new slot-aware-v1 base model"):
        train_simulation_candidate(
            base_model_directory=model_directory,
            model_root=model_root,
            snapshot_path=SNAPSHOT,
            config=SimulationTrainingConfig(
                batch_size=2,
                rollout_steps=2,
                updates=1,
                teacher_updates=0,
                environment_minibatch_size=2,
            ),
        )


def test_native_self_play_writes_fingerprinted_non_promotable_candidate(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    model_root = tmp_path / "models"
    parent = initialize_fixed_simulation_model(
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
            teacher_updates=1,
            teacher_epochs=1,
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
    assert candidate.metrics["training_transitions"] == 64
    assert candidate.metrics["teacher_transitions"] == 32
    assert candidate.metrics["ppo_transitions"] == 32
    assert candidate.metrics["teacher_updates"] == 1
    assert candidate.metrics["training_updates"] == 1
    assert (
        candidate.training_context["source_kind"]
        == "native-heuristic-warmstart-on-policy-self-play"
    )
    simulation_context = candidate.training_context["simulation"]
    assert isinstance(simulation_context, dict)
    assert simulation_context["ruleset_id"] == "plain-attack-defense-redraw-duel-v1"
    assert simulation_context["promotion_eligible"] is False
    assert loaded_model.global_feature_count == 6
    assert loaded_model.artifact_policy_head is not None


def test_elemental_self_play_uses_expanded_observation_and_heuristic(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    model_root = tmp_path / "models"
    parent = initialize_model(
        model_root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=ELEMENT_FEATURE_SCHEMA_VERSION,
        global_feature_count=13,
    )

    candidate = train_simulation_candidate(
        base_model_directory=model_root / parent.model_id,
        model_root=model_root,
        snapshot_path=SNAPSHOT,
        config=SimulationTrainingConfig(
            ruleset="elemental-hand",
            batch_size=8,
            rollout_steps=4,
            updates=1,
            ppo_epochs=1,
            environment_minibatch_size=4,
            teacher_updates=1,
            teacher_epochs=1,
            seed=67,
        ),
    )
    _, loaded_model = load_model(model_root / candidate.model_id)
    simulation_context = candidate.training_context["simulation"]

    assert isinstance(simulation_context, dict)
    assert simulation_context["ruleset_id"] == (
        "plain-elemental-mixed-hand-attack-defense-redraw-duel-v1"
    )
    assert simulation_context["global_feature_count"] == 13
    assert candidate.training_context["heuristic_policy_id"] == (
        "plain-element-aware-max-attack-conservative-defense-v1"
    )
    assert loaded_model.global_feature_count == 13


def test_combo_self_play_uses_sequential_schema_and_heuristic(tmp_path) -> None:
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
            ruleset="combo-hand",
            batch_size=8,
            rollout_steps=6,
            updates=1,
            ppo_epochs=1,
            environment_minibatch_size=4,
            teacher_updates=1,
            teacher_epochs=1,
            seed=67,
        ),
    )
    simulation_context = candidate.training_context["simulation"]

    assert isinstance(simulation_context, dict)
    assert simulation_context["observation_schema_version"] == 4
    assert simulation_context["action_semantics"] == "sequential-combo-selection"
    assert candidate.training_context["heuristic_policy_id"] == ("plain-elemental-greedy-combo-v2")


def test_resource_self_play_uses_stateful_mp_schema_and_heuristic(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    model_root = tmp_path / "models"
    parent = initialize_model(
        model_root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=RESOURCE_FEATURE_SCHEMA_VERSION,
    )

    candidate = train_simulation_candidate(
        base_model_directory=model_root / parent.model_id,
        model_root=model_root,
        snapshot_path=SNAPSHOT,
        config=SimulationTrainingConfig(
            ruleset="resource-hand",
            batch_size=8,
            rollout_steps=8,
            updates=1,
            ppo_epochs=1,
            environment_minibatch_size=4,
            teacher_updates=1,
            teacher_epochs=1,
            seed=67,
        ),
    )
    simulation_context = candidate.training_context["simulation"]

    assert isinstance(simulation_context, dict)
    assert simulation_context["observation_schema_version"] == 5
    assert simulation_context["rule_catalog_size"] == 117
    assert candidate.training_context["heuristic_policy_id"] == ("plain-resource-aware-combo-v1")
