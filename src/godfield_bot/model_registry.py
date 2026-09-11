import hashlib
import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import torch
from pydantic import BaseModel, Field, JsonValue

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.features import (
    ELEMENT_FEATURE_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    GLOBAL_FEATURE_COUNT,
    LEGACY_FEATURE_SCHEMA_VERSION,
    LEGACY_GLOBAL_FEATURE_COUNT,
    PLAYER_FEATURE_COUNT,
    RESOURCE_FEATURE_SCHEMA_VERSION,
    STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION,
    STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
)
from godfield_bot.neural import (
    POOLED_HAND_POLICY,
    SLOT_AWARE_POLICY,
    PolicyArchitecture,
    RecurrentPolicyValueNet,
)


class ModelStatus(StrEnum):
    INITIALIZED = "initialized"
    CANDIDATE = "candidate"
    CHAMPION = "champion"
    REJECTED = "rejected"


class ModelArchitecture(BaseModel):
    vocabulary_size: int = Field(gt=1)
    action_count: int = Field(gt=0)
    global_feature_count: int = Field(default=GLOBAL_FEATURE_COUNT, gt=0)
    player_feature_count: int = Field(default=PLAYER_FEATURE_COUNT, gt=0)
    embedding_size: int = Field(default=32, gt=0)
    hidden_size: int = Field(default=128, gt=0)
    # Missing means a schema-v2 pooled-hand checkpoint.
    policy_architecture: PolicyArchitecture = POOLED_HAND_POLICY


class ModelManifest(BaseModel):
    schema_version: int = 3
    # Missing means a legacy v1 manifest; new writers always set this explicitly.
    feature_schema_version: int = 1
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
    training_context: dict[str, JsonValue] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


ELEMENT_FEATURE_MIGRATION = "feature-schema-v3-element-expansion-v1"
COMBO_FEATURE_MIGRATION = "feature-schema-v4-combo-selection-v1"
RESOURCE_FEATURE_MIGRATION = "feature-schema-v5-hp-mp-utility-miracle-cost-v1"
STOCHASTIC_RESOURCE_FEATURE_MIGRATION = (
    "feature-schema-v6-chance-and-absorption-miracle-v1"
)
SUPPORTED_OBSERVATION_SCHEMAS = {
    (LEGACY_FEATURE_SCHEMA_VERSION, LEGACY_GLOBAL_FEATURE_COUNT),
    (ELEMENT_FEATURE_SCHEMA_VERSION, GLOBAL_FEATURE_COUNT),
    (FEATURE_SCHEMA_VERSION, GLOBAL_FEATURE_COUNT),
    (RESOURCE_FEATURE_SCHEMA_VERSION, GLOBAL_FEATURE_COUNT),
    (
        STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION,
        STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT,
    ),
}


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
    feature_schema_version: int = FEATURE_SCHEMA_VERSION,
    global_feature_count: int = GLOBAL_FEATURE_COUNT,
) -> ModelManifest:
    if (feature_schema_version, global_feature_count) not in SUPPORTED_OBSERVATION_SCHEMAS:
        raise ValueError("cannot initialize an unsupported observation architecture")
    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    architecture = ModelArchitecture(
        vocabulary_size=len(vocabulary.tokens),
        action_count=3 + max_hand_slots + max_players,
        global_feature_count=global_feature_count,
        policy_architecture=SLOT_AWARE_POLICY,
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
        feature_schema_version=feature_schema_version,
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
    if (
        manifest.schema_version == 3
        and "policy_architecture" not in manifest.architecture.model_fields_set
    ):
        raise ValueError("model schema v3 requires an explicit policy architecture")
    observation_schema = (
        manifest.feature_schema_version,
        manifest.architecture.global_feature_count,
    )
    if manifest.schema_version not in (2, 3) or (
        observation_schema not in SUPPORTED_OBSERVATION_SCHEMAS
        or manifest.architecture.player_feature_count != PLAYER_FEATURE_COUNT
    ):
        raise ValueError(
            "model uses an unsupported observation architecture; initialize a current model"
        )
    weights_path = model_directory / manifest.weights_file
    if _file_digest(weights_path) != manifest.weights_sha256:
        raise ValueError("model weight checksum does not match manifest")
    model = _build_model(manifest.architecture)
    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    return manifest, model


def migrate_element_features(
    source_model_directory: Path,
    root: Path,
    vocabulary: ArtifactVocabulary,
    *,
    client_sha256: str,
) -> ModelManifest:
    """Expand a schema-v2 checkpoint without changing its neutral-state outputs."""

    source, source_model = load_model(source_model_directory)
    if source.feature_schema_version != LEGACY_FEATURE_SCHEMA_VERSION or (
        source.architecture.global_feature_count != LEGACY_GLOBAL_FEATURE_COUNT
    ):
        raise ValueError("element migration requires a feature-schema-v2 source model")
    if source.architecture.policy_architecture != SLOT_AWARE_POLICY:
        raise ValueError("element migration requires a slot-aware-v1 source model")
    if source.client_sha256 != client_sha256:
        raise ValueError("source model client fingerprint differs from the Bible snapshot")
    if source.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ValueError("source model vocabulary differs from the Bible snapshot")

    architecture = source.architecture.model_copy(
        update={"global_feature_count": GLOBAL_FEATURE_COUNT}
    )
    migrated_model = _build_model(architecture)
    migrated_state = source_model.state_dict()
    input_weight_name = "global_encoder.0.weight"
    source_input_weights = migrated_state[input_weight_name]
    expanded_input_weights = source_input_weights.new_zeros(
        (source_input_weights.shape[0], GLOBAL_FEATURE_COUNT)
    )
    expanded_input_weights[:, :LEGACY_GLOBAL_FEATURE_COUNT] = source_input_weights
    migrated_state[input_weight_name] = expanded_input_weights
    migrated_model.load_state_dict(migrated_state)

    migration_input: dict[str, JsonValue] = {
        "schema_version": 1,
        "algorithm": ELEMENT_FEATURE_MIGRATION,
        "source_model_id": source.model_id,
        "source_weights_sha256": source.weights_sha256,
        "source_feature_schema_version": source.feature_schema_version,
        "target_feature_schema_version": ELEMENT_FEATURE_SCHEMA_VERSION,
        "new_global_inputs": GLOBAL_FEATURE_COUNT - LEGACY_GLOBAL_FEATURE_COUNT,
        "new_input_initialization": "zero",
    }
    migration_digest = hashlib.sha256(
        json.dumps(migration_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    weights_file = "weights.pt"
    weights_path = model_directory / weights_file
    temporary_weights = model_directory / "weights.pt.tmp"
    torch.save(migrated_model.state_dict(), temporary_weights)
    os.chmod(temporary_weights, 0o600)
    os.replace(temporary_weights, weights_path)
    manifest = ModelManifest(
        feature_schema_version=ELEMENT_FEATURE_SCHEMA_VERSION,
        model_id=model_id,
        created_at=datetime.now(UTC),
        status=ModelStatus.INITIALIZED,
        client_sha256=source.client_sha256,
        vocabulary_sha256=source.vocabulary_sha256,
        weights_sha256=_file_digest(weights_path),
        weights_file=weights_file,
        architecture=architecture,
        seed=source.seed,
        parent_model_id=source.model_id,
        training_algorithm=ELEMENT_FEATURE_MIGRATION,
        training_dataset_sha256=migration_digest,
        training_context=migration_input,
    )
    temporary_manifest = model_directory / "manifest.json.tmp"
    temporary_manifest.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_manifest, 0o600)
    os.replace(temporary_manifest, model_directory / "manifest.json")
    return manifest


def migrate_combo_features(
    source_model_directory: Path,
    root: Path,
    vocabulary: ArtifactVocabulary,
    *,
    client_sha256: str,
) -> ModelManifest:
    """Version an elemental checkpoint for sequential combo observations."""

    source, source_model = load_model(source_model_directory)
    if source.feature_schema_version != ELEMENT_FEATURE_SCHEMA_VERSION or (
        source.architecture.global_feature_count != GLOBAL_FEATURE_COUNT
    ):
        raise ValueError("combo migration requires a feature-schema-v3 source model")
    if source.architecture.policy_architecture != SLOT_AWARE_POLICY:
        raise ValueError("combo migration requires a slot-aware-v1 source model")
    if source.client_sha256 != client_sha256:
        raise ValueError("source model client fingerprint differs from the Bible snapshot")
    if source.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ValueError("source model vocabulary differs from the Bible snapshot")

    migration_input: dict[str, JsonValue] = {
        "schema_version": 1,
        "algorithm": COMBO_FEATURE_MIGRATION,
        "source_model_id": source.model_id,
        "source_weights_sha256": source.weights_sha256,
        "source_feature_schema_version": source.feature_schema_version,
        "target_feature_schema_version": FEATURE_SCHEMA_VERSION,
        "tensor_transform": "identity",
        "semantic_change": "outgoing combo aggregate in global attack and element inputs",
    }
    migration_digest = hashlib.sha256(
        json.dumps(migration_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    weights_file = "weights.pt"
    weights_path = model_directory / weights_file
    temporary_weights = model_directory / "weights.pt.tmp"
    torch.save(source_model.state_dict(), temporary_weights)
    os.chmod(temporary_weights, 0o600)
    os.replace(temporary_weights, weights_path)
    manifest = ModelManifest(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        model_id=model_id,
        created_at=datetime.now(UTC),
        status=ModelStatus.INITIALIZED,
        client_sha256=source.client_sha256,
        vocabulary_sha256=source.vocabulary_sha256,
        weights_sha256=_file_digest(weights_path),
        weights_file=weights_file,
        architecture=source.architecture,
        seed=source.seed,
        parent_model_id=source.model_id,
        training_algorithm=COMBO_FEATURE_MIGRATION,
        training_dataset_sha256=migration_digest,
        training_context=migration_input,
    )
    temporary_manifest = model_directory / "manifest.json.tmp"
    temporary_manifest.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_manifest, 0o600)
    os.replace(temporary_manifest, model_directory / "manifest.json")
    return manifest


def migrate_resource_features(
    source_model_directory: Path,
    root: Path,
    vocabulary: ArtifactVocabulary,
    *,
    client_sha256: str,
) -> ModelManifest:
    """Version a combo checkpoint for stateful MP and resource actions."""

    source, source_model = load_model(source_model_directory)
    if source.feature_schema_version != FEATURE_SCHEMA_VERSION or (
        source.architecture.global_feature_count != GLOBAL_FEATURE_COUNT
    ):
        raise ValueError("resource migration requires a feature-schema-v4 source model")
    if source.architecture.policy_architecture != SLOT_AWARE_POLICY:
        raise ValueError("resource migration requires a slot-aware-v1 source model")
    if source.client_sha256 != client_sha256:
        raise ValueError("source model client fingerprint differs from the Bible snapshot")
    if source.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ValueError("source model vocabulary differs from the Bible snapshot")

    migration_input: dict[str, JsonValue] = {
        "schema_version": 1,
        "algorithm": RESOURCE_FEATURE_MIGRATION,
        "source_model_id": source.model_id,
        "source_weights_sha256": source.weights_sha256,
        "source_feature_schema_version": source.feature_schema_version,
        "target_feature_schema_version": RESOURCE_FEATURE_SCHEMA_VERSION,
        "tensor_transform": "identity",
        "semantic_change": "stateful MP plus HP/MP utility and MP-cost miracle actions",
    }
    migration_digest = hashlib.sha256(
        json.dumps(migration_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    weights_file = "weights.pt"
    weights_path = model_directory / weights_file
    temporary_weights = model_directory / "weights.pt.tmp"
    torch.save(source_model.state_dict(), temporary_weights)
    os.chmod(temporary_weights, 0o600)
    os.replace(temporary_weights, weights_path)
    manifest = ModelManifest(
        feature_schema_version=RESOURCE_FEATURE_SCHEMA_VERSION,
        model_id=model_id,
        created_at=datetime.now(UTC),
        status=ModelStatus.INITIALIZED,
        client_sha256=source.client_sha256,
        vocabulary_sha256=source.vocabulary_sha256,
        weights_sha256=_file_digest(weights_path),
        weights_file=weights_file,
        architecture=source.architecture,
        seed=source.seed,
        parent_model_id=source.model_id,
        training_algorithm=RESOURCE_FEATURE_MIGRATION,
        training_dataset_sha256=migration_digest,
        training_context=migration_input,
    )
    temporary_manifest = model_directory / "manifest.json.tmp"
    temporary_manifest.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_manifest, 0o600)
    os.replace(temporary_manifest, model_directory / "manifest.json")
    return manifest


def migrate_stochastic_resource_features(
    source_model_directory: Path,
    root: Path,
    vocabulary: ArtifactVocabulary,
    *,
    client_sha256: str,
) -> ModelManifest:
    """Expand a schema-v5 checkpoint with the pending absorption-effect input."""

    source, source_model = load_model(source_model_directory)
    if source.feature_schema_version != RESOURCE_FEATURE_SCHEMA_VERSION or (
        source.architecture.global_feature_count != GLOBAL_FEATURE_COUNT
    ):
        raise ValueError(
            "stochastic resource migration requires a feature-schema-v5 source model"
        )
    if source.architecture.policy_architecture != SLOT_AWARE_POLICY:
        raise ValueError("stochastic resource migration requires a slot-aware-v1 source model")
    if source.client_sha256 != client_sha256:
        raise ValueError("source model client fingerprint differs from the Bible snapshot")
    if source.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise ValueError("source model vocabulary differs from the Bible snapshot")

    architecture = source.architecture.model_copy(
        update={"global_feature_count": STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT}
    )
    migrated_model = _build_model(architecture)
    migrated_state = source_model.state_dict()
    input_weight_name = "global_encoder.0.weight"
    source_input_weights = migrated_state[input_weight_name]
    expanded_input_weights = source_input_weights.new_zeros(
        (source_input_weights.shape[0], STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT)
    )
    expanded_input_weights[:, :GLOBAL_FEATURE_COUNT] = source_input_weights
    migrated_state[input_weight_name] = expanded_input_weights
    migrated_model.load_state_dict(migrated_state)

    migration_input: dict[str, JsonValue] = {
        "schema_version": 1,
        "algorithm": STOCHASTIC_RESOURCE_FEATURE_MIGRATION,
        "source_model_id": source.model_id,
        "source_weights_sha256": source.weights_sha256,
        "source_feature_schema_version": source.feature_schema_version,
        "target_feature_schema_version": STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION,
        "new_global_inputs": 1,
        "new_input_initialization": "zero",
        "semantic_change": "chance resolution plus visible pending absorption effect",
    }
    migration_digest = hashlib.sha256(
        json.dumps(migration_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    prepare_private_directory(root)
    model_id = str(uuid4())
    model_directory = root / model_id
    prepare_private_directory(model_directory)
    weights_file = "weights.pt"
    weights_path = model_directory / weights_file
    temporary_weights = model_directory / "weights.pt.tmp"
    torch.save(migrated_model.state_dict(), temporary_weights)
    os.chmod(temporary_weights, 0o600)
    os.replace(temporary_weights, weights_path)
    manifest = ModelManifest(
        feature_schema_version=STOCHASTIC_RESOURCE_FEATURE_SCHEMA_VERSION,
        model_id=model_id,
        created_at=datetime.now(UTC),
        status=ModelStatus.INITIALIZED,
        client_sha256=source.client_sha256,
        vocabulary_sha256=source.vocabulary_sha256,
        weights_sha256=_file_digest(weights_path),
        weights_file=weights_file,
        architecture=architecture,
        seed=source.seed,
        parent_model_id=source.model_id,
        training_algorithm=STOCHASTIC_RESOURCE_FEATURE_MIGRATION,
        training_dataset_sha256=migration_digest,
        training_context=migration_input,
    )
    temporary_manifest = model_directory / "manifest.json.tmp"
    temporary_manifest.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary_manifest, 0o600)
    os.replace(temporary_manifest, model_directory / "manifest.json")
    return manifest


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
    training_context: dict[str, JsonValue] | None = None,
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
        schema_version=parent.schema_version,
        feature_schema_version=parent.feature_schema_version,
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
        training_context=training_context or {},
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
