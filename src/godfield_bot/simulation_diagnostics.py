"""Read-only checkpoint diagnostics; these traces never confer policy authority."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

import numpy as np
import torch
from pydantic import BaseModel, Field

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import load_model
from godfield_bot.simulation import (
    AttackDefenseRuleset,
    SimulationMetadata,
    create_attack_defense_simulation,
    simulation_feature_tensors,
)
from godfield_bot.simulation_evaluation import _model_actions
from godfield_bot.simulation_league import validate_league_model
from godfield_bot.simulation_policy import build_curriculum_heuristic, curriculum_heuristic_actions

if TYPE_CHECKING:
    from godfield_sim import AttackDefenseBatch

SPLITMIX_INCREMENT = 0x9E3779B97F4A7C15
UINT64_MAX = (1 << 64) - 1


def environment_seed(seed: int, environment: int) -> int:
    """Reproduce one native environment's RNG without constructing its whole batch."""

    if not 0 <= seed <= UINT64_MAX or not 0 <= environment < 1_000_000:
        raise ValueError("seed or environment index is outside the native range")
    return (seed + environment * SPLITMIX_INCREMENT) & UINT64_MAX


class SimulationTraceConfig(BaseModel):
    ruleset: AttackDefenseRuleset = "wide-hand-gift-weighted-dream-resource-hand"
    seed: int = Field(default=67, ge=0, le=UINT64_MAX)
    environment: int = Field(default=0, ge=0, lt=1_000_000)
    candidate_seat: int = Field(default=0, ge=0, le=1)
    max_decisions: int = Field(default=512, ge=2, le=4096)


class SimulationDecisionTrace(BaseModel):
    decision: int
    actor: int
    phase: int
    turn: int
    action_index: int
    action_name: str
    # HP is from the visible policy observation; Fog-hidden opponents are null.
    hp_before: tuple[int | None, int | None]
    mp_before: tuple[int, int]
    hp_after: tuple[int | None, int | None]
    mp_after: tuple[int, int]
    selected_count: int
    pending_attack: int
    pending_element: int | None = None
    terminal: bool
    legal_action_names: tuple[str, ...] = ()
    illness_before: tuple[int, int] | None = None
    illness_after: tuple[int, int] | None = None


def _visible_hp(batch: AttackDefenseBatch) -> tuple[int | None, int | None]:
    actor = int(batch.active_players[0])
    own = round(float(batch.player_features[0, 0, 0]) * 100)
    other = (
        None if batch.fog_flags[0, actor] else round(float(batch.player_features[0, 1, 0]) * 100)
    )
    return (own, other) if actor == 0 else (other, own)


class SimulationGameTrace(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["native-game-diagnostic-not-gate"] = "native-game-diagnostic-not-gate"
    trace_id: str
    created_at: datetime
    candidate_model_id: str
    candidate_weights_sha256: str
    opponent_id: str
    opponent_weights_sha256: str | None
    simulation: SimulationMetadata
    config: SimulationTraceConfig
    derived_seed: int
    input_sha256: str
    completed: bool
    candidate_outcome: int | None
    decisions: tuple[SimulationDecisionTrace, ...]
    promotion_eligible: Literal[False] = False


def trace_simulation_game(
    *,
    candidate_model_directory: Path,
    snapshot_path: Path,
    trace_directory: Path,
    config: SimulationTraceConfig,
    opponent_model_directory: Path | None = None,
) -> tuple[Path, SimulationGameTrace]:
    """Replay a first-deal index against a frozen model or curriculum heuristic.

    Native RNG states match the indexed batched environment. Different neural
    matrix batch sizes can change floating-point ties, so this is diagnostic
    evidence, not a substitute for the original paired evaluation.
    """

    manifest, candidate = load_model(candidate_model_directory)
    derived_seed = environment_seed(config.seed, config.environment)
    simulation = create_attack_defense_simulation(
        snapshot_path, batch_size=1, seed=derived_seed, ruleset=config.ruleset
    )
    validate_league_model(manifest, manifest, simulation.metadata)
    bible = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(bible)
    heuristic = build_curriculum_heuristic(bible, vocabulary, ruleset=config.ruleset)
    opponent = None
    opponent_id = heuristic.policy_id
    opponent_digest = None
    if opponent_model_directory is not None:
        opponent_manifest, opponent = load_model(opponent_model_directory)
        validate_league_model(opponent_manifest, manifest, simulation.metadata)
        opponent_id = opponent_manifest.model_id
        opponent_digest = opponent_manifest.weights_sha256
        opponent.eval()
    candidate.eval()
    candidate_states = torch.zeros(1, candidate.hidden_size)
    opponent_states = torch.zeros(1, candidate.hidden_size)
    device = torch.device("cpu")
    rows = np.array([0], dtype=np.int64)
    batch = simulation.batch
    records: list[SimulationDecisionTrace] = []
    for decision in range(1, config.max_decisions + 1):
        observation = simulation_feature_tensors(simulation, device="cpu")
        actor = int(batch.active_players[0])
        if actor == config.candidate_seat:
            action = int(_model_actions(candidate, candidate_states, observation, rows, device)[0])
        elif opponent is not None:
            action = int(_model_actions(opponent, opponent_states, observation, rows, device)[0])
        else:
            action = int(curriculum_heuristic_actions(simulation, rows, heuristic)[0])

        def action_name(index: int) -> str:
            if 1 <= index <= simulation.metadata.hand_slots:
                return vocabulary.tokens[int(batch.hand_token_ids[0, index - 1])]
            if index == simulation.metadata.action_count - 1:
                return "confirm"
            if index == simulation.metadata.action_count - 2:
                return "forgive"
            return f"reserved-action-{index}"

        name = action_name(action)
        legal_names = tuple(
            action_name(int(index)) for index in np.flatnonzero(batch.action_mask[0])
        )
        illness = (int(batch.illness_stages[0, 0]), int(batch.illness_stages[0, 1]))
        hp = _visible_hp(batch)
        mp = tuple(map(int, batch.magic_points[0]))
        phase, turn = int(batch.phases[0]), int(batch.turn_numbers[0])
        selected_count, pending_attack = (
            int(batch.selected_counts[0]),
            int(batch.pending_attacks[0]),
        )
        pending_element = int(batch.pending_elements[0])
        batch.step(np.array([action], dtype=np.int64))
        records.append(
            SimulationDecisionTrace(
                decision=decision,
                actor=actor,
                phase=phase,
                turn=turn,
                action_index=action,
                action_name=name,
                hp_before=(hp[0], hp[1]),
                mp_before=(mp[0], mp[1]),
                hp_after=_visible_hp(batch),
                mp_after=(int(batch.magic_points[0, 0]), int(batch.magic_points[0, 1])),
                selected_count=selected_count,
                pending_attack=pending_attack,
                pending_element=pending_element,
                terminal=bool(batch.terminated[0]),
                legal_action_names=legal_names,
                illness_before=illness,
                illness_after=(int(batch.illness_stages[0, 0]), int(batch.illness_stages[0, 1])),
            )
        )
        if batch.terminated[0]:
            break
    completed = bool(batch.terminated[0])
    inputs = {
        "candidate": manifest.weights_sha256,
        "opponent_id": opponent_id,
        "opponent_weights": opponent_digest,
        "simulation": simulation.metadata.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
    }
    trace = SimulationGameTrace(
        trace_id=str(uuid4()),
        created_at=datetime.now(UTC),
        candidate_model_id=manifest.model_id,
        candidate_weights_sha256=manifest.weights_sha256,
        opponent_id=opponent_id,
        opponent_weights_sha256=opponent_digest,
        simulation=simulation.metadata,
        config=config,
        derived_seed=derived_seed,
        input_sha256=hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        completed=completed,
        candidate_outcome=(
            int(np.sign(batch.terminal_returns[0, config.candidate_seat])) if completed else None
        ),
        decisions=tuple(records),
    )
    prepare_private_directory(trace_directory)
    path = trace_directory / f"{trace.trace_id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(trace.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return path, trace
