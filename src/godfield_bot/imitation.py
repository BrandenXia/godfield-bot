import hashlib
from collections import OrderedDict
from pathlib import Path

import torch
from pydantic import BaseModel, Field

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
    FEATURE_SCHEMA_VERSION,
    GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
    StateFeatureEncoder,
    StateFeatures,
    action_index,
)
from godfield_bot.model_registry import (
    ModelManifest,
    load_model,
    save_candidate,
    vocabulary_digest,
)
from godfield_bot.replay import load_replay_jsonl
from godfield_bot.training import (
    behavior_cloning_sequence_step,
    evaluate_imitation_sequences,
)

ALGORITHM = "behavior-cloning-v0"


class ImitationTrainingConfig(BaseModel):
    epochs: int = Field(default=20, ge=1, le=10_000)
    learning_rate: float = Field(default=1e-3, gt=0, le=1)
    max_gradient_norm: float = Field(default=1.0, gt=0, le=100)
    seed: int = 67


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_imitation_candidate(
    *,
    base_model_directory: Path,
    model_root: Path,
    replay_path: Path,
    snapshot_path: Path,
    config: ImitationTrainingConfig,
) -> ModelManifest:
    """Create an offline candidate that imitates accepted browser actions."""

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    artifact_vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    parent, model = load_model(base_model_directory)
    if parent.feature_schema_version != FEATURE_SCHEMA_VERSION or (
        parent.architecture.global_feature_count != GLOBAL_FEATURE_COUNT
    ):
        raise ValueError("replay training requires a feature-schema-v3 base model")
    if parent.client_sha256 != snapshot.client.sha256:
        raise ValueError("base model client fingerprint differs from the Bible snapshot")
    if parent.vocabulary_sha256 != vocabulary_digest(artifact_vocabulary):
        raise ValueError("base model vocabulary differs from the Bible snapshot")

    replay_sha256 = _file_digest(replay_path)
    samples = load_replay_jsonl(replay_path)
    if _file_digest(replay_path) != replay_sha256:
        raise ValueError("replay dataset changed while it was being loaded")
    if any(sample.client_sha256 != parent.client_sha256 for sample in samples):
        raise ValueError("replay client fingerprint differs from the base model")

    encoder = StateFeatureEncoder(artifact_vocabulary, snapshot)
    grouped: OrderedDict[str, tuple[list[StateFeatures], list[int]]] = OrderedDict()
    for sample in samples:
        encoded_state = encoder.encode(sample.before_state, sample.legal_actions)
        target = action_index(sample.chosen_action)
        if (
            len(encoded_state.action_mask) != parent.architecture.action_count
            or target >= parent.architecture.action_count
            or not encoded_state.action_mask[target]
        ):
            raise ValueError("replay action is incompatible with the base model action head")
        trajectory = grouped.setdefault(sample.run_id, ([], []))
        trajectory[0].append(encoded_state)
        trajectory[1].append(target)
    trajectories = tuple(
        (trajectory_features, actions) for trajectory_features, actions in grouped.values()
    )

    torch.manual_seed(config.seed)
    before = evaluate_imitation_sequences(model, trajectories)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    for _ in range(config.epochs):
        for trajectory_features, actions in trajectories:
            behavior_cloning_sequence_step(
                model,
                optimizer,
                trajectory_features,
                actions,
                max_gradient_norm=config.max_gradient_norm,
            )
    after = evaluate_imitation_sequences(model, trajectories)
    if _file_digest(replay_path) != replay_sha256:
        raise ValueError("replay dataset changed during training")
    return save_candidate(
        model_root,
        model,
        artifact_vocabulary,
        parent=parent,
        seed=config.seed,
        training_algorithm=ALGORITHM,
        training_dataset_sha256=replay_sha256,
        training_run_ids=tuple(grouped),
        metrics={
            "training_samples": float(len(samples)),
            "training_trajectories": float(len(trajectories)),
            "training_epochs": float(config.epochs),
            "imitation_loss_before": before.loss,
            "imitation_loss_after": after.loss,
            "imitation_accuracy_before": before.accuracy,
            "imitation_accuracy_after": after.accuracy,
        },
    )
