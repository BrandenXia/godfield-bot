import hashlib
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import torch
from pydantic import BaseModel, Field

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.neural import RecurrentPolicyValueNet


class ModelStatus(StrEnum):
    INITIALIZED = "initialized"
    CANDIDATE = "candidate"
    CHAMPION = "champion"
    REJECTED = "rejected"


class ModelArchitecture(BaseModel):
    vocabulary_size: int = Field(gt=1)
    action_count: int = Field(gt=0)
    global_feature_count: int = Field(default=4, gt=0)
    player_feature_count: int = Field(default=4, gt=0)
    embedding_size: int = Field(default=32, gt=0)
    hidden_size: int = Field(default=128, gt=0)


class ModelManifest(BaseModel):
    schema_version: int = 1
    model_id: str
    created_at: datetime
    status: ModelStatus
    client_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    vocabulary_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    weights_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    weights_file: str
    architecture: ModelArchitecture
    seed: int
    parent_model_id: str | None = None
    training_algorithm: str | None = None
    training_dataset_sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    training_run_ids: tuple[str, ...] = ()
    metrics: dict[str, float] = Field(default_factory=dict)


def vocabulary_digest(vocabulary: ArtifactVocabulary) -> str:
    return hashlib.sha256(vocabulary.model_dump_json().encode()).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_model(architecture: ModelArchitecture) -> RecurrentPolicyValueNet:
    return RecurrentPolicyValueNet(**architecture.model_dump())


def initialize_model(
    root: Path,
    vocabulary: ArtifactVocabulary,
    *,
    client_sha256: str,
    seed: int = 67,
    max_hand_slots: int = 9,
    max_players: int = 9,
) -> ModelManifest:
    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    architecture = ModelArchitecture(
        vocabulary_size=len(vocabulary.tokens),
        action_count=3 + max_hand_slots + max_players,
    )
    torch.manual_seed(seed)
    model = _build_model(architecture)
    weights_file = "weights.pt"
    weights_path = model_directory / weights_file
    temporary_weights = model_directory / "weights.pt.tmp"
    torch.save(model.state_dict(), temporary_weights)
    os.chmod(temporary_weights, 0o600)
    os.replace(temporary_weights, weights_path)
    manifest = ModelManifest(
        model_id=model_id,
        created_at=datetime.now(UTC),
        status=ModelStatus.INITIALIZED,
        client_sha256=client_sha256,
        vocabulary_sha256=vocabulary_digest(vocabulary),
        weights_sha256=_file_digest(weights_path),
        weights_file=weights_file,
        architecture=architecture,
        seed=seed,
    )
    manifest_path = model_directory / "manifest.json"
    temporary_manifest = model_directory / "manifest.json.tmp"
    temporary_manifest.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary_manifest, 0o600)
    os.replace(temporary_manifest, manifest_path)
    return manifest


def load_model(model_directory: Path) -> tuple[ModelManifest, RecurrentPolicyValueNet]:
    manifest = ModelManifest.model_validate_json(
        (model_directory / "manifest.json").read_text(encoding="utf-8")
    )
    weights_path = model_directory / manifest.weights_file
    if _file_digest(weights_path) != manifest.weights_sha256:
        raise ValueError("model weight checksum does not match manifest")
    model = _build_model(manifest.architecture)
    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    return manifest, model


def save_candidate(
    root: Path,
    model: RecurrentPolicyValueNet,
    vocabulary: ArtifactVocabulary,
    *,
    parent: ModelManifest,
    seed: int,
    training_algorithm: str,
    training_dataset_sha256: str,
    training_run_ids: tuple[str, ...],
    metrics: dict[str, float],
) -> ModelManifest:
    """Persist trained weights as a new immutable, non-promoted candidate."""

    if vocabulary_digest(vocabulary) != parent.vocabulary_sha256:
        raise ValueError("candidate vocabulary differs from its parent model")
    expected = _build_model(parent.architecture)
    expected.load_state_dict(model.state_dict())
    del expected

    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    weights_file = "weights.pt"
    weights_path = model_directory / weights_file
    temporary_weights = model_directory / "weights.pt.tmp"
    torch.save(model.state_dict(), temporary_weights)
    os.chmod(temporary_weights, 0o600)
    os.replace(temporary_weights, weights_path)
    manifest = ModelManifest(
        model_id=model_id,
        created_at=datetime.now(UTC),
        status=ModelStatus.CANDIDATE,
        client_sha256=parent.client_sha256,
        vocabulary_sha256=parent.vocabulary_sha256,
        weights_sha256=_file_digest(weights_path),
        weights_file=weights_file,
        architecture=parent.architecture,
        seed=seed,
        parent_model_id=parent.model_id,
        training_algorithm=training_algorithm,
        training_dataset_sha256=training_dataset_sha256,
        training_run_ids=tuple(dict.fromkeys(training_run_ids)),
        metrics=metrics,
    )
    temporary_manifest = model_directory / "manifest.json.tmp"
    temporary_manifest.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_manifest, 0o600)
    os.replace(temporary_manifest, model_directory / "manifest.json")
    return manifest
