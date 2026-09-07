from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.reference import plain_attack_weapon_values

if TYPE_CHECKING:
    from godfield_sim import FixedAttackBatch
    from torch import Tensor


class SimulationUnavailableError(RuntimeError):
    """Raised when the optional native simulation package is unavailable."""


class SimulationMetadata(BaseModel):
    schema_version: int = 1
    kernel_schema_version: int
    observation_schema_version: int
    ruleset_id: str
    client_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    vocabulary_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    rule_catalog_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    rule_catalog_size: int = Field(gt=0)
    action_count: int = Field(gt=0)
    hand_slots: int = Field(gt=0)
    action_semantics: Literal["atomic-hand-slot-macro"] = "atomic-hand-slot-macro"
    sampling_distribution: Literal["uniform-with-replacement"] = "uniform-with-replacement"
    promotion_eligible: Literal[False] = False


class SimulationBenchmark(BaseModel):
    metadata: SimulationMetadata
    batch_size: int = Field(gt=0)
    batch_steps: int = Field(gt=0)
    transitions: int = Field(gt=0)
    completed_episodes: int = Field(ge=0)
    elapsed_seconds: float = Field(gt=0)
    transitions_per_second: float = Field(gt=0)


@dataclass(frozen=True)
class FixedAttackSimulation:
    """A native batch plus the fingerprints required to interpret its output."""

    batch: FixedAttackBatch
    metadata: SimulationMetadata


def simulation_feature_tensors(
    simulation: FixedAttackSimulation,
    *,
    device: str = "cpu",
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
    """Expose the current native observation to PyTorch without a CPU copy.

    These tensors are ephemeral views. A simulator step updates their backing
    buffers, so rollout storage must clone any observation it needs to retain.
    """

    try:
        import torch
    except ImportError as error:
        raise SimulationUnavailableError(
            "PyTorch is unavailable; run `uv sync --extra simulation --extra training`"
        ) from error

    batch = simulation.batch
    tensors = (
        torch.utils.dlpack.from_dlpack(batch.global_features),
        torch.utils.dlpack.from_dlpack(batch.player_features),
        torch.utils.dlpack.from_dlpack(batch.player_mask),
        torch.utils.dlpack.from_dlpack(batch.hand_token_ids),
        torch.utils.dlpack.from_dlpack(batch.hand_mask),
        torch.utils.dlpack.from_dlpack(batch.action_mask),
    )
    if device == "cpu":
        return tensors
    return tuple(tensor.to(device) for tensor in tensors)  # type: ignore[return-value]


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_fixed_attack_simulation(
    snapshot_path: Path,
    *,
    batch_size: int,
    seed: int = 67,
    initial_hp: int = 40,
) -> FixedAttackSimulation:
    """Build the non-promotable fixed-attack curriculum from an accepted snapshot."""

    try:
        import numpy as np
        from godfield_sim import (
            ACTION_COUNT,
            HAND_SLOTS,
            KERNEL_SCHEMA_VERSION,
            OBSERVATION_SCHEMA_VERSION,
            RULESET_ID,
            FixedAttackBatch,
        )
    except ImportError as error:
        raise SimulationUnavailableError(
            "native simulation is unavailable; run `uv sync --extra simulation --group dev`"
        ) from error

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    attacks = plain_attack_weapon_values(snapshot)
    if not attacks:
        raise ValueError("accepted snapshot contains no effect-free neutral attacks")
    catalog = [
        {
            "attack": attack,
            "slug": slug,
            "token_id": vocabulary.token_id("weapons", slug),
        }
        for slug, attack in sorted(attacks.items())
    ]
    token_ids = np.asarray([row["token_id"] for row in catalog], dtype=np.uint32)
    attack_values = np.asarray([row["attack"] for row in catalog], dtype=np.uint16)
    batch = FixedAttackBatch(batch_size, token_ids, attack_values, seed, initial_hp)
    return FixedAttackSimulation(
        batch=batch,
        metadata=SimulationMetadata(
            kernel_schema_version=KERNEL_SCHEMA_VERSION,
            observation_schema_version=OBSERVATION_SCHEMA_VERSION,
            ruleset_id=RULESET_ID,
            client_sha256=snapshot.client.sha256,
            vocabulary_sha256=hashlib.sha256(vocabulary.model_dump_json().encode()).hexdigest(),
            rule_catalog_sha256=_sha256_json(catalog),
            rule_catalog_size=len(catalog),
            action_count=ACTION_COUNT,
            hand_slots=HAND_SLOTS,
        ),
    )


def benchmark_fixed_attack_simulation(
    snapshot_path: Path,
    *,
    batch_size: int,
    batch_steps: int,
    seed: int = 67,
) -> SimulationBenchmark:
    """Measure native transition collection without neural inference."""

    import numpy as np

    simulation = create_fixed_attack_simulation(
        snapshot_path,
        batch_size=batch_size,
        seed=seed,
    )
    actions = np.empty(batch_size, dtype=np.int64)
    completed_episodes = 0
    started = time.perf_counter()
    for _ in range(batch_steps):
        simulation.batch.reset_done()
        actions[:] = simulation.batch.action_mask.argmax(axis=1)
        simulation.batch.step(actions)
        completed_episodes += int(np.count_nonzero(simulation.batch.terminated))
    elapsed = time.perf_counter() - started
    transitions = batch_size * batch_steps
    return SimulationBenchmark(
        metadata=simulation.metadata,
        batch_size=batch_size,
        batch_steps=batch_steps,
        transitions=transitions,
        completed_episodes=completed_episodes,
        elapsed_seconds=elapsed,
        transitions_per_second=transitions / elapsed,
    )
