from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.reference import plain_attack_weapon_values, plain_defense_armor_values
from godfield_bot.simulation import AttackDefenseSimulation

HEURISTIC_POLICY_ID = "plain-max-attack-conservative-defense-v0"
FORGIVE_ACTION_INDEX = 19


class SimulationPolicyError(RuntimeError):
    """Raised when a curriculum policy cannot select a legal action."""


@dataclass(frozen=True)
class CurriculumHeuristic:
    attacks: dict[int, int]
    defenses: dict[int, int]


def build_curriculum_heuristic(
    snapshot: BibleSnapshot,
    vocabulary: ArtifactVocabulary,
) -> CurriculumHeuristic:
    return CurriculumHeuristic(
        attacks={
            vocabulary.token_id("weapons", slug): attack
            for slug, attack in plain_attack_weapon_values(snapshot).items()
        },
        defenses={
            vocabulary.token_id("armor", slug): defense
            for slug, defense in plain_defense_armor_values(snapshot).items()
        },
    )


def curriculum_heuristic_actions(
    simulation: AttackDefenseSimulation,
    rows: npt.NDArray[np.int64],
    policy: CurriculumHeuristic,
) -> npt.NDArray[np.int64]:
    """Choose max attack or conservative armor with deterministic slot ties."""

    batch = simulation.batch
    actions = np.empty(rows.size, dtype=np.int64)
    for output_index, environment in enumerate(rows):
        hand = batch.hand_token_ids[environment]
        legal = batch.action_mask[environment]
        if batch.phases[environment] == 0:
            candidates = [
                (policy.attacks[int(hand[action - 1])], action)
                for action in range(1, 10)
                if legal[action] and int(hand[action - 1]) in policy.attacks
            ]
            if not candidates:
                raise SimulationPolicyError("heuristic found no known legal attack")
            actions[output_index] = max(candidates, key=lambda item: (item[0], -item[1]))[1]
            continue

        pending_attack = int(batch.pending_attacks[environment])
        candidates = [
            (policy.defenses[int(hand[action - 1])], action)
            for action in range(1, 10)
            if legal[action] and int(hand[action - 1]) in policy.defenses
        ]
        if not candidates:
            if legal[FORGIVE_ACTION_INDEX]:
                actions[output_index] = FORGIVE_ACTION_INDEX
                continue
            raise SimulationPolicyError("heuristic found no known legal defense or pass")
        sufficient = [item for item in candidates if item[0] >= pending_attack]
        if sufficient:
            actions[output_index] = min(sufficient, key=lambda item: (item[0], item[1]))[1]
        else:
            actions[output_index] = max(candidates, key=lambda item: (item[0], -item[1]))[1]
    return actions
