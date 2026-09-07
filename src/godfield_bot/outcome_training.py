import hashlib
from collections import Counter
from pathlib import Path

import torch
from pydantic import BaseModel, Field

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
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
from godfield_bot.outcome_replay import load_outcome_replay_jsonl
from godfield_bot.training import (
    evaluate_outcome_sequences,
    outcome_supervised_sequence_step,
)

ALGORITHM = "outcome-supervised-v0"


class OutcomeTrainingConfig(BaseModel):
    epochs: int = Field(default=20, ge=1, le=10_000)
    learning_rate: float = Field(default=1e-3, gt=0, le=1)
    value_weight: float = Field(default=0.5, ge=0, le=100)
    entropy_weight: float = Field(default=0.01, ge=0, le=100)
    max_gradient_norm: float = Field(default=1.0, gt=0, le=100)
    seed: int = 67


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_outcome_candidate(
    *,
    base_model_directory: Path,
    model_root: Path,
    outcome_replay_path: Path,
    snapshot_path: Path,
    config: OutcomeTrainingConfig,
) -> ModelManifest:
    """Create a non-deployable candidate from verified terminal episodes."""

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    artifact_vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    parent, model = load_model(base_model_directory)
    if parent.client_sha256 != snapshot.client.sha256:
        raise ValueError("base model client fingerprint differs from the Bible snapshot")
    if parent.vocabulary_sha256 != vocabulary_digest(artifact_vocabulary):
        raise ValueError("base model vocabulary differs from the Bible snapshot")

    dataset_sha256 = _file_digest(outcome_replay_path)
    episodes = load_outcome_replay_jsonl(outcome_replay_path)
    if _file_digest(outcome_replay_path) != dataset_sha256:
        raise ValueError("outcome replay changed while it was being loaded")
    if any(episode.client_sha256 != parent.client_sha256 for episode in episodes):
        raise ValueError("outcome replay client fingerprint differs from the base model")

    encoder = StateFeatureEncoder(artifact_vocabulary)
    encoded_episodes: list[tuple[list[StateFeatures], list[int], float]] = []
    outcome_counts: Counter[str] = Counter()
    for episode in episodes:
        trajectory_features: list[StateFeatures] = []
        actions: list[int] = []
        for step in episode.steps:
            encoded_state = encoder.encode(step.before_state, step.legal_actions)
            target = action_index(step.chosen_action)
            if (
                len(encoded_state.action_mask) != parent.architecture.action_count
                or target >= parent.architecture.action_count
                or not encoded_state.action_mask[target]
            ):
                raise ValueError("outcome replay action is incompatible with the model head")
            trajectory_features.append(encoded_state)
            actions.append(target)
        encoded_episodes.append((trajectory_features, actions, episode.reward.value))
        outcome_counts[episode.outcome.result.value] += 1

    torch.manual_seed(config.seed)
    before = evaluate_outcome_sequences(
        model,
        encoded_episodes,
        value_weight=config.value_weight,
        entropy_weight=config.entropy_weight,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    for _ in range(config.epochs):
        for trajectory_features, actions, terminal_return in encoded_episodes:
            outcome_supervised_sequence_step(
                model,
                optimizer,
                trajectory_features,
                actions,
                terminal_return,
                value_weight=config.value_weight,
                entropy_weight=config.entropy_weight,
                max_gradient_norm=config.max_gradient_norm,
            )
    after = evaluate_outcome_sequences(
        model,
        encoded_episodes,
        value_weight=config.value_weight,
        entropy_weight=config.entropy_weight,
    )
    if _file_digest(outcome_replay_path) != dataset_sha256:
        raise ValueError("outcome replay changed during training")
    return save_candidate(
        model_root,
        model,
        artifact_vocabulary,
        parent=parent,
        seed=config.seed,
        training_algorithm=ALGORITHM,
        training_dataset_sha256=dataset_sha256,
        training_run_ids=tuple(episode.run_id for episode in episodes),
        metrics={
            "training_episodes": float(len(episodes)),
            "training_steps": float(sum(len(episode.steps) for episode in episodes)),
            "training_epochs": float(config.epochs),
            "learning_rate": config.learning_rate,
            "value_weight": config.value_weight,
            "entropy_weight": config.entropy_weight,
            "max_gradient_norm": config.max_gradient_norm,
            "training_wins": float(outcome_counts["win"]),
            "training_losses": float(outcome_counts["loss"]),
            "training_draws": float(outcome_counts["draw"]),
            "total_loss_before": before.total_loss,
            "total_loss_after": after.total_loss,
            "policy_loss_before": before.policy_loss,
            "policy_loss_after": after.policy_loss,
            "value_loss_before": before.value_loss,
            "value_loss_after": after.value_loss,
            "entropy_before": before.entropy,
            "entropy_after": after.entropy,
        },
    )
