import json
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
from godfield_bot.domain.outcome_replay import OutcomeReplayEpisode
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.replay import ReplaySample
from godfield_bot.domain.run import RunMode
from godfield_bot.features import (
    RESOURCE_FEATURE_SCHEMA_VERSION,
    StateFeatureEncoder,
    action_index,
    load_vocabulary,
)
from godfield_bot.imitation import ImitationTrainingConfig, train_imitation_candidate
from godfield_bot.legal_actions import game_state_digest, observation_only_actions
from godfield_bot.model_registry import (
    COMBO_FEATURE_MIGRATION,
    ELEMENT_FEATURE_MIGRATION,
    RESOURCE_FEATURE_MIGRATION,
    STOCHASTIC_RESOURCE_FEATURE_MIGRATION,
    ModelStatus,
    initialize_model,
    load_model,
    migrate_combo_features,
    migrate_element_features,
    migrate_resource_features,
    migrate_stochastic_resource_features,
)
from godfield_bot.neural import RecurrentPolicyValueNet, features_to_tensors
from godfield_bot.outcome_training import OutcomeTrainingConfig, train_outcome_candidate
from godfield_bot.outcomes import classify_two_player_terminal, sparse_terminal_reward
from godfield_bot.policy import OFFICIAL_TRAINING_NEURAL_POLICY_ID
from godfield_bot.runner import build_action_transition
from godfield_bot.training import (
    TrainingError,
    actor_critic_loss,
    behavior_cloning_sequence_step,
    outcome_supervised_sequence_step,
    sparse_outcome_actor_critic_loss,
    train_step,
)

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
    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
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
    assert manifest.schema_version == 3
    assert manifest.feature_schema_version == 4
    assert manifest.architecture.global_feature_count == 13
    assert manifest.architecture.policy_architecture == "slot-aware-v1"
    assert loaded_model.policy_head.out_features == 21
    assert loaded_model.artifact_policy_head is not None
    assert stat.S_IMODE((model_directory / "weights.pt").stat().st_mode) == 0o600


def test_legacy_four_feature_model_is_rejected_with_migration_message(tmp_path) -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    manifest = initialize_model(
        tmp_path / "models",
        vocabulary,
        client_sha256="a" * 64,
    )
    model_directory = tmp_path / "models" / manifest.model_id
    legacy = manifest.model_copy(
        update={
            "schema_version": 1,
            "feature_schema_version": 1,
            "architecture": manifest.architecture.model_copy(update={"global_feature_count": 4}),
        }
    )
    (model_directory / "manifest.json").write_text(
        legacy.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="initialize a current model"):
        load_model(model_directory)


def test_element_feature_migration_preserves_neutral_outputs(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = load_vocabulary(SNAPSHOT)
    root = tmp_path / "models"
    source = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=2,
        global_feature_count=6,
    )
    migrated = migrate_element_features(
        root / source.model_id,
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )
    _, source_model = load_model(root / source.model_id)
    _, migrated_model = load_model(root / migrated.model_id)
    torch.manual_seed(67)
    legacy_globals = torch.rand((4, 6))
    elemental_globals = torch.cat((legacy_globals, torch.zeros((4, 7))), dim=1)
    players = torch.rand((4, 2, 4))
    player_mask = torch.ones((4, 2), dtype=torch.bool)
    hand = torch.randint(2, len(vocabulary.tokens), (4, 9))
    hand_mask = torch.ones((4, 9), dtype=torch.bool)
    action_mask = torch.ones((4, 21), dtype=torch.bool)

    source_outputs = source_model(
        legacy_globals,
        players,
        player_mask,
        hand,
        hand_mask,
        action_mask,
    )
    migrated_outputs = migrated_model(
        elemental_globals,
        players,
        player_mask,
        hand,
        hand_mask,
        action_mask,
    )

    assert migrated.status is ModelStatus.INITIALIZED
    assert migrated.parent_model_id == source.model_id
    assert migrated.training_algorithm == ELEMENT_FEATURE_MIGRATION
    assert migrated.feature_schema_version == 3
    assert migrated.architecture.global_feature_count == 13
    for source_output, migrated_output in zip(source_outputs, migrated_outputs, strict=True):
        torch.testing.assert_close(source_output, migrated_output)


def test_combo_feature_migration_preserves_weights_exactly(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = load_vocabulary(SNAPSHOT)
    root = tmp_path / "models"
    legacy = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=2,
        global_feature_count=6,
    )
    elemental = migrate_element_features(
        root / legacy.model_id,
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )
    combo = migrate_combo_features(
        root / elemental.model_id,
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )
    _, elemental_model = load_model(root / elemental.model_id)
    _, combo_model = load_model(root / combo.model_id)

    assert combo.feature_schema_version == 4
    assert combo.parent_model_id == elemental.model_id
    assert combo.training_algorithm == COMBO_FEATURE_MIGRATION
    for name, value in elemental_model.state_dict().items():
        torch.testing.assert_close(value, combo_model.state_dict()[name], rtol=0, atol=0)


def test_resource_feature_migration_preserves_weights_exactly(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = load_vocabulary(SNAPSHOT)
    root = tmp_path / "models"
    combo = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=4,
        global_feature_count=13,
    )
    resource = migrate_resource_features(
        root / combo.model_id,
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
    )
    _, combo_model = load_model(root / combo.model_id)
    _, resource_model = load_model(root / resource.model_id)

    assert resource.feature_schema_version == 5
    assert resource.parent_model_id == combo.model_id
    assert resource.training_algorithm == RESOURCE_FEATURE_MIGRATION
    assert resource.training_context["tensor_transform"] == "identity"
    for name, value in combo_model.state_dict().items():
        torch.testing.assert_close(value, resource_model.state_dict()[name], rtol=0, atol=0)


def test_stochastic_resource_migration_adds_zero_initialized_effect_input(tmp_path) -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    root = tmp_path / "models"
    resource = initialize_model(
        root,
        vocabulary,
        client_sha256=BIBLE.client.sha256,
        feature_schema_version=5,
        global_feature_count=13,
    )
    stochastic = migrate_stochastic_resource_features(
        root / resource.model_id,
        root,
        vocabulary,
        client_sha256=BIBLE.client.sha256,
    )
    _, resource_model = load_model(root / resource.model_id)
    _, stochastic_model = load_model(root / stochastic.model_id)
    resource_state = resource_model.state_dict()
    stochastic_state = stochastic_model.state_dict()

    assert stochastic.feature_schema_version == 6
    assert stochastic.architecture.global_feature_count == 14
    assert stochastic.parent_model_id == resource.model_id
    assert stochastic.training_algorithm == STOCHASTIC_RESOURCE_FEATURE_MIGRATION
    torch.testing.assert_close(
        stochastic_state["global_encoder.0.weight"][:, :13],
        resource_state["global_encoder.0.weight"],
        rtol=0,
        atol=0,
    )
    assert torch.count_nonzero(stochastic_state["global_encoder.0.weight"][:, 13]) == 0
    for name, value in resource_state.items():
        if name != "global_encoder.0.weight":
            torch.testing.assert_close(value, stochastic_state[name], rtol=0, atol=0)


def test_schema_v3_model_requires_explicit_policy_architecture(tmp_path) -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    manifest = initialize_model(
        tmp_path / "models",
        vocabulary,
        client_sha256="a" * 64,
    )
    model_directory = tmp_path / "models" / manifest.model_id
    manifest_data = json.loads((model_directory / "manifest.json").read_text(encoding="utf-8"))
    del manifest_data["architecture"]["policy_architecture"]
    (model_directory / "manifest.json").write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema v3 requires an explicit policy architecture"):
        load_model(model_directory)


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
    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
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


def outcome_episode(*, model_id: str = "fixture-model") -> OutcomeReplayEpisode:
    original = imitation_sample()
    sample = original.model_copy(
        update={
            "policy_id": OFFICIAL_TRAINING_NEURAL_POLICY_ID,
            "model_id": model_id,
            "decision": original.decision.model_copy(
                update={"policy_id": OFFICIAL_TRAINING_NEURAL_POLICY_ID}
            ),
        }
    )
    terminal_state = sample.after_state.model_copy(
        update={
            "observed_at": datetime.now(UTC),
            "field_number": 2,
            "players": (
                sample.after_state.players[0],
                sample.after_state.players[1].model_copy(update={"hp": 0}),
            ),
        }
    )
    outcome = classify_two_player_terminal(terminal_state)
    assert outcome is not None
    return OutcomeReplayEpisode(
        run_id=sample.run_id,
        mode=RunMode.TRAINING,
        client_sha256=sample.client_sha256,
        policy_id=sample.policy_id,
        model_id=sample.model_id,
        steps=(sample,),
        terminal_state=terminal_state,
        outcome=outcome,
        reward=sparse_terminal_reward(outcome),
    )


def test_outcome_step_updates_policy_and_value_heads() -> None:
    torch.manual_seed(67)
    vocabulary = load_vocabulary(SNAPSHOT)
    sample = imitation_sample()
    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
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

    metrics = outcome_supervised_sequence_step(
        model,
        optimizer,
        [features],
        [action_index(sample.chosen_action)],
        1.0,
    )

    assert metrics.total_loss > 0
    assert metrics.value_loss > 0
    assert not torch.equal(policy_before, model.policy_head.weight.detach())
    assert not torch.equal(value_before, model.value_head.weight.detach())


def test_outcome_step_rejects_shaped_return() -> None:
    vocabulary = load_vocabulary(SNAPSHOT)
    sample = imitation_sample()
    features = StateFeatureEncoder(vocabulary, BIBLE).encode(
        sample.before_state,
        sample.legal_actions,
    )
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=len(features.action_mask),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    with pytest.raises(TrainingError, match="sparse terminal return"):
        outcome_supervised_sequence_step(
            model,
            optimizer,
            [features],
            [action_index(sample.chosen_action)],
            0.5,
        )


def test_sparse_outcome_advantage_reinforces_wins_and_suppresses_losses() -> None:
    logits = torch.tensor([[0.0, 0.0]])
    values = torch.tensor([0.0])
    actions = torch.tensor([1])

    _, winning_policy_loss, _, _ = sparse_outcome_actor_critic_loss(
        logits,
        values,
        actions,
        torch.tensor([1.0]),
    )
    _, losing_policy_loss, _, _ = sparse_outcome_actor_critic_loss(
        logits,
        values,
        actions,
        torch.tensor([-1.0]),
    )

    assert winning_policy_loss > 0
    assert losing_policy_loss < 0


def test_outcome_training_writes_immutable_candidate_lineage(tmp_path) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = load_vocabulary(SNAPSHOT)
    root = tmp_path / "models"
    parent = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=RESOURCE_FEATURE_SCHEMA_VERSION,
    ).model_copy(
        update={
            "training_context": {
                "simulation": {
                    "ruleset_id": (
                        "plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1"
                    ),
                    "action_semantics": "sequential-combo-selection",
                }
            }
        }
    )
    (root / parent.model_id / "manifest.json").write_text(
        parent.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    _, parent_model = load_model(root / parent.model_id)
    parent_value_head = parent_model.value_head.weight.detach().clone()
    outcome_replay = tmp_path / "outcomes.jsonl"
    outcome_replay.write_text(
        outcome_episode(model_id=parent.model_id).model_dump_json() + "\n",
        encoding="utf-8",
    )

    candidate = train_outcome_candidate(
        base_model_directory=root / parent.model_id,
        model_root=root,
        outcome_replay_path=outcome_replay,
        snapshot_path=SNAPSHOT,
        config=OutcomeTrainingConfig(epochs=2),
    )
    loaded_manifest, candidate_model = load_model(root / candidate.model_id)

    assert candidate.status is ModelStatus.CANDIDATE
    assert candidate.parent_model_id == parent.model_id
    assert candidate.training_algorithm == "official-training-outcome-actor-critic-v1"
    assert candidate.training_dataset_sha256 is not None
    assert candidate.training_run_ids == ("fixture-run",)
    assert candidate.metrics["training_episodes"] == 1
    assert candidate.metrics["training_steps"] == 1
    assert candidate.metrics["training_wins"] == 1
    assert candidate.feature_schema_version == RESOURCE_FEATURE_SCHEMA_VERSION
    assert candidate.training_context["simulation"] == parent.training_context["simulation"]
    assert candidate.training_context["official_training"]["base_model_id"] == parent.model_id
    assert candidate.metrics["value_loss_after"] < candidate.metrics["value_loss_before"]
    assert not torch.equal(parent_value_head, candidate_model.value_head.weight.detach())
    assert loaded_manifest == candidate
