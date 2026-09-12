from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import COMBAT_ELEMENT_IDS
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.reference import (
    plain_attack_booster_cards,
    plain_attack_weapon_cards,
    plain_attack_weapon_values,
    plain_chance_dual_role_weapon_cards,
    plain_chance_weapon_cards,
    plain_defense_armor_cards,
    plain_defense_armor_values,
    plain_dual_role_weapon_cards,
    plain_hp_utility_sundries,
    plain_mp_utility_sundries,
    verified_absorption_weapon_cards,
    verified_attack_booster_miracle_cards,
    verified_attack_miracle_cards,
    verified_chance_absorption_weapon_cards,
    verified_chance_attack_miracle_cards,
    verified_effect_attack_miracle_cards,
    verified_hp_utility_miracle_cards,
    verified_reflection_armor_cards,
    verified_reflection_weapon_cards,
)

if TYPE_CHECKING:
    from godfield_sim import AttackDefenseBatch, FixedAttackBatch
    from torch import Tensor

AttackDefenseRuleset = Literal[
    "fixed-role",
    "mixed-hand",
    "elemental-hand",
    "combo-hand",
    "resource-hand",
    "stochastic-resource-hand",
    "expanded-resource-hand",
    "reflection-resource-hand",
    "reflection-weapon-resource-hand",
    "dual-role-resource-hand",
    "chance-weapon-resource-hand",
    "absorption-weapon-resource-hand",
]


class SimulationUnavailableError(RuntimeError):
    """Raised when the optional native simulation package is unavailable."""


class SimulationMetadata(BaseModel):
    schema_version: int = 2
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
    global_feature_count: int = Field(default=6, gt=0)
    action_semantics: Literal[
        "atomic-hand-slot-macro",
        "atomic-attack-defense-macro",
        "sequential-combo-selection",
    ] = "atomic-hand-slot-macro"
    sampling_distribution: Literal[
        "uniform-redraw-with-replacement",
        "fixed-role-uniform-redraw-with-replacement",
        "mixed-role-uniform-redraw-with-attack-liveness",
        "elemental-mixed-role-uniform-redraw-with-attack-liveness",
        "elemental-combo-4-2-3-initial-uniform-redraw-with-base-liveness",
        "elemental-resource-3-1-2-2-1-initial-uniform-redraw-with-base-liveness",
        "elemental-stochastic-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-expanded-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-reflection-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-reflection-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-dual-role-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-chance-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-absorption-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
    ] = "uniform-redraw-with-replacement"
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


@dataclass(frozen=True)
class AttackDefenseSimulation:
    """A native defense curriculum and its exact rule-catalog identity."""

    batch: AttackDefenseBatch
    metadata: SimulationMetadata


def simulation_feature_tensors(
    simulation: FixedAttackSimulation | AttackDefenseSimulation,
    *,
    device: str = "cpu",
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
    """Expose a versioned native observation to PyTorch without a CPU copy.

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
            global_feature_count=6,
        ),
    )


def create_attack_defense_simulation(
    snapshot_path: Path,
    *,
    batch_size: int,
    seed: int = 67,
    initial_hp: int = 40,
    initial_mp: int = 10,
    ruleset: AttackDefenseRuleset = "fixed-role",
) -> AttackDefenseSimulation:
    """Build a non-promotable neutral attack/defense curriculum."""

    try:
        import numpy as np
        from godfield_sim import (
            ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            ACTION_COUNT,
            ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            ATTACK_DEFENSE_RULESET_ID,
            CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            COMBO_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            COMBO_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            COMBO_ATTACK_DEFENSE_RULESET_ID,
            DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            ELEMENTAL_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            ELEMENTAL_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            ELEMENTAL_ATTACK_DEFENSE_RULESET_ID,
            ELEMENTAL_GLOBAL_FEATURE_COUNT,
            EXPANDED_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            EXPANDED_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            EXPANDED_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            HAND_SLOTS,
            MIXED_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            MIXED_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            MIXED_ATTACK_DEFENSE_RULESET_ID,
            REFLECTION_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            REFLECTION_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            REFLECTION_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            STOCHASTIC_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION,
            STOCHASTIC_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION,
            STOCHASTIC_RESOURCE_ATTACK_DEFENSE_RULESET_ID,
            STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT,
            AbsorptionWeaponResourceAttackDefenseBatch,
            AttackDefenseBatch,
            ChanceWeaponResourceAttackDefenseBatch,
            ComboAttackDefenseBatch,
            DualRoleResourceAttackDefenseBatch,
            ElementalAttackDefenseBatch,
            ExpandedResourceAttackDefenseBatch,
            ReflectionResourceAttackDefenseBatch,
            ReflectionWeaponResourceAttackDefenseBatch,
            ResourceAttackDefenseBatch,
            StochasticResourceAttackDefenseBatch,
        )
    except ImportError as error:
        raise SimulationUnavailableError(
            "native simulation is unavailable; run `uv sync --extra simulation --group dev`"
        ) from error

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    expanded_rulesets = {
        "elemental-hand",
        "combo-hand",
        "resource-hand",
        "stochastic-resource-hand",
        "expanded-resource-hand",
        "reflection-resource-hand",
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
    }
    if ruleset in expanded_rulesets:
        attacks = plain_attack_weapon_cards(snapshot)
        defenses = plain_defense_armor_cards(snapshot)
    else:
        attacks = {
            slug: (attack, "non-element")
            for slug, attack in plain_attack_weapon_values(snapshot).items()
        }
        defenses = {
            slug: (defense, "non-element")
            for slug, defense in plain_defense_armor_values(snapshot).items()
        }
    if not attacks:
        raise ValueError("accepted snapshot contains no effect-free neutral attacks")
    if not defenses:
        raise ValueError("accepted snapshot contains no effect-free neutral armor")

    weapon_catalog = [
        {
            "attack": attack,
            "kind": "weapon",
            "slug": slug,
            "token_id": vocabulary.token_id("weapons", slug),
            **(
                {"element": element, "element_id": COMBAT_ELEMENT_IDS[element]}
                if ruleset in expanded_rulesets
                else {}
            ),
        }
        for slug, (attack, element) in sorted(attacks.items())
    ]
    armor_catalog = [
        {
            "defense": defense,
            "kind": "armor",
            "slug": slug,
            "token_id": vocabulary.token_id("armor", slug),
            **(
                {"element": element, "element_id": COMBAT_ELEMENT_IDS[element]}
                if ruleset in expanded_rulesets
                else {}
            ),
        }
        for slug, (defense, element) in sorted(defenses.items())
    ]
    weapon_token_ids = np.asarray([row["token_id"] for row in weapon_catalog], dtype=np.uint32)
    attack_values = np.asarray([row["attack"] for row in weapon_catalog], dtype=np.uint16)
    armor_token_ids = np.asarray([row["token_id"] for row in armor_catalog], dtype=np.uint32)
    defense_values = np.asarray([row["defense"] for row in armor_catalog], dtype=np.uint16)
    booster_catalog: list[dict[str, object]] = []
    batch: AttackDefenseBatch
    if ruleset in {
        "combo-hand",
        "resource-hand",
        "stochastic-resource-hand",
        "expanded-resource-hand",
        "reflection-resource-hand",
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
    }:
        boosters = plain_attack_booster_cards(snapshot)
        if not boosters:
            raise ValueError("accepted snapshot contains no effect-free attack boosters")
        booster_catalog = [
            {
                "attack_boost": boost,
                "kind": "attack-booster",
                "slug": slug,
                "token_id": vocabulary.token_id("weapons", slug),
                "element": element,
                "element_id": COMBAT_ELEMENT_IDS[element],
            }
            for slug, (boost, element) in sorted(boosters.items())
        ]
        weapon_elements = np.asarray([row["element_id"] for row in weapon_catalog], dtype=np.uint8)
        booster_token_ids = np.asarray(
            [row["token_id"] for row in booster_catalog], dtype=np.uint32
        )
        booster_values = np.asarray(
            [row["attack_boost"] for row in booster_catalog], dtype=np.uint16
        )
        booster_elements = np.asarray(
            [row["element_id"] for row in booster_catalog], dtype=np.uint8
        )
        armor_elements = np.asarray([row["element_id"] for row in armor_catalog], dtype=np.uint8)
        if ruleset in {
            "resource-hand",
            "stochastic-resource-hand",
            "expanded-resource-hand",
            "reflection-resource-hand",
            "reflection-weapon-resource-hand",
            "dual-role-resource-hand",
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
        }:
            hp_utilities = plain_hp_utility_sundries(snapshot)
            mp_utilities = plain_mp_utility_sundries(snapshot)
            attack_miracles = verified_attack_miracle_cards(snapshot)
            hp_miracles = verified_hp_utility_miracle_cards(snapshot)
            if not hp_utilities or not mp_utilities:
                raise ValueError("accepted snapshot contains no pure HP/MP utility sundries")
            if not attack_miracles or not hp_miracles:
                raise ValueError("accepted snapshot contains no supported utility/attack miracles")
            hp_utility_catalog: list[dict[str, object]] = [
                {
                    "kind": "hp-utility",
                    "slug": slug,
                    "token_id": vocabulary.token_id("sundries", slug),
                    "utility": utility,
                }
                for slug, utility in sorted(hp_utilities.items())
            ]
            mp_utility_catalog: list[dict[str, object]] = [
                {
                    "kind": "mp-utility",
                    "slug": slug,
                    "token_id": vocabulary.token_id("sundries", slug),
                    "utility": utility,
                }
                for slug, utility in sorted(mp_utilities.items())
            ]
            attack_miracle_catalog: list[dict[str, object]] = [
                {
                    "attack": attack,
                    "cost": cost,
                    "element": element,
                    "element_id": COMBAT_ELEMENT_IDS[element],
                    "kind": "attack-miracle",
                    "slug": slug,
                    "token_id": vocabulary.token_id("miracles", slug),
                }
                for slug, (attack, cost, element) in sorted(attack_miracles.items())
            ]
            hp_miracle_catalog: list[dict[str, object]] = [
                {
                    "cost": cost,
                    "kind": "hp-miracle",
                    "slug": slug,
                    "token_id": vocabulary.token_id("miracles", slug),
                    "utility": utility,
                }
                for slug, (utility, cost) in sorted(hp_miracles.items())
            ]
            resource_args = (
                batch_size,
                weapon_token_ids,
                attack_values,
                weapon_elements,
                booster_token_ids,
                booster_values,
                booster_elements,
                armor_token_ids,
                defense_values,
                armor_elements,
                np.asarray([row["token_id"] for row in hp_utility_catalog], dtype=np.uint32),
                np.asarray([row["utility"] for row in hp_utility_catalog], dtype=np.uint16),
                np.asarray([row["token_id"] for row in mp_utility_catalog], dtype=np.uint32),
                np.asarray([row["utility"] for row in mp_utility_catalog], dtype=np.uint16),
                np.asarray([row["token_id"] for row in attack_miracle_catalog], dtype=np.uint32),
                np.asarray([row["attack"] for row in attack_miracle_catalog], dtype=np.uint16),
                np.asarray([row["element_id"] for row in attack_miracle_catalog], dtype=np.uint8),
                np.asarray([row["cost"] for row in attack_miracle_catalog], dtype=np.uint16),
                np.asarray([row["token_id"] for row in hp_miracle_catalog], dtype=np.uint32),
                np.asarray([row["utility"] for row in hp_miracle_catalog], dtype=np.uint16),
                np.asarray([row["cost"] for row in hp_miracle_catalog], dtype=np.uint16),
            )
            stochastic_catalog: list[dict[str, object]] = []
            if ruleset in {
                "stochastic-resource-hand",
                "expanded-resource-hand",
                "reflection-resource-hand",
                "reflection-weapon-resource-hand",
                "dual-role-resource-hand",
                "chance-weapon-resource-hand",
                "absorption-weapon-resource-hand",
            }:
                chance_miracles = verified_chance_attack_miracle_cards(snapshot)
                effect_miracles = {
                    slug: values
                    for slug, values in verified_effect_attack_miracle_cards(snapshot).items()
                    if values[3] == "absorbHP"
                }
                if not chance_miracles or not effect_miracles:
                    raise ValueError(
                        "accepted snapshot contains no supported chance/absorption miracles"
                    )
                chance_catalog: list[dict[str, object]] = [
                    {
                        "attack": attack,
                        "cost": cost,
                        "element": element,
                        "element_id": COMBAT_ELEMENT_IDS[element],
                        "hit_rate": hit_rate,
                        "kind": "chance-attack-miracle",
                        "slug": slug,
                        "token_id": vocabulary.token_id("miracles", slug),
                    }
                    for slug, (hit_rate, attack, cost, element) in sorted(chance_miracles.items())
                ]
                effect_catalog: list[dict[str, object]] = [
                    {
                        "attack": attack,
                        "cost": cost,
                        "effect": effect,
                        "element": element,
                        "element_id": COMBAT_ELEMENT_IDS[element],
                        "kind": "effect-attack-miracle",
                        "slug": slug,
                        "token_id": vocabulary.token_id("miracles", slug),
                    }
                    for slug, (attack, cost, element, effect) in sorted(effect_miracles.items())
                ]
                stochastic_args = (
                    np.asarray([row["token_id"] for row in chance_catalog], dtype=np.uint32),
                    np.asarray([row["attack"] for row in chance_catalog], dtype=np.uint16),
                    np.asarray([row["element_id"] for row in chance_catalog], dtype=np.uint8),
                    np.asarray([row["cost"] for row in chance_catalog], dtype=np.uint16),
                    np.asarray([row["hit_rate"] for row in chance_catalog], dtype=np.uint16),
                    np.asarray([row["token_id"] for row in effect_catalog], dtype=np.uint32),
                    np.asarray([row["attack"] for row in effect_catalog], dtype=np.uint16),
                    np.asarray([row["element_id"] for row in effect_catalog], dtype=np.uint8),
                    np.asarray([row["cost"] for row in effect_catalog], dtype=np.uint16),
                )
                additive_catalog: list[dict[str, object]] = []
                reflection_catalog: list[dict[str, object]] = []
                reflection_weapon_catalog: list[dict[str, object]] = []
                dual_role_catalog: list[dict[str, object]] = []
                chance_weapon_catalog: list[dict[str, object]] = []
                chance_dual_role_catalog: list[dict[str, object]] = []
                absorption_weapon_catalog: list[dict[str, object]] = []
                chance_absorption_weapon_catalog: list[dict[str, object]] = []
                if ruleset in {
                    "expanded-resource-hand",
                    "reflection-resource-hand",
                    "reflection-weapon-resource-hand",
                    "dual-role-resource-hand",
                    "chance-weapon-resource-hand",
                    "absorption-weapon-resource-hand",
                }:
                    additive_miracles = verified_attack_booster_miracle_cards(snapshot)
                    if not additive_miracles:
                        raise ValueError(
                            "accepted snapshot contains no supported additive miracles"
                        )
                    additive_catalog = [
                        {
                            "attack_boost": boost,
                            "cost": cost,
                            "element": element,
                            "element_id": COMBAT_ELEMENT_IDS[element],
                            "kind": "additive-attack-miracle",
                            "slug": slug,
                            "token_id": vocabulary.token_id("miracles", slug),
                        }
                        for slug, (boost, cost, element) in sorted(additive_miracles.items())
                    ]
                    additive_args = (
                        np.asarray([row["token_id"] for row in additive_catalog], dtype=np.uint32),
                        np.asarray(
                            [row["attack_boost"] for row in additive_catalog],
                            dtype=np.uint16,
                        ),
                        np.asarray([row["element_id"] for row in additive_catalog], dtype=np.uint8),
                        np.asarray([row["cost"] for row in additive_catalog], dtype=np.uint16),
                    )
                    if ruleset in {
                        "reflection-resource-hand",
                        "reflection-weapon-resource-hand",
                        "dual-role-resource-hand",
                        "chance-weapon-resource-hand",
                        "absorption-weapon-resource-hand",
                    }:
                        reflection_armor = verified_reflection_armor_cards(snapshot)
                        if not reflection_armor:
                            raise ValueError(
                                "accepted snapshot contains no supported reflection armor"
                            )
                        reflection_catalog = [
                            {
                                "effect": "reflect-anything",
                                "kind": "reflection-armor",
                                "slug": slug,
                                "token_id": vocabulary.token_id("armor", slug),
                            }
                            for slug in sorted(reflection_armor)
                        ]
                        reflection_armor_token_ids = np.asarray(
                            [row["token_id"] for row in reflection_catalog],
                            dtype=np.uint32,
                        )
                        if ruleset in {
                            "reflection-weapon-resource-hand",
                            "dual-role-resource-hand",
                            "chance-weapon-resource-hand",
                            "absorption-weapon-resource-hand",
                        }:
                            reflection_weapons = verified_reflection_weapon_cards(snapshot)
                            if not reflection_weapons:
                                raise ValueError(
                                    "accepted snapshot contains no supported reflection weapon"
                                )
                            reflection_weapon_catalog = [
                                {
                                    "attack": attack,
                                    "effect": "reflect-non-element-weapon",
                                    "element": "non-element",
                                    "element_id": COMBAT_ELEMENT_IDS["non-element"],
                                    "kind": "reflection-weapon",
                                    "slug": slug,
                                    "token_id": vocabulary.token_id("weapons", slug),
                                }
                                for slug, attack in sorted(reflection_weapons.items())
                            ]
                            reflection_weapon_token_ids = np.asarray(
                                [row["token_id"] for row in reflection_weapon_catalog],
                                dtype=np.uint32,
                            )
                            reflection_weapon_values = np.asarray(
                                [row["attack"] for row in reflection_weapon_catalog],
                                dtype=np.uint16,
                            )
                            if ruleset in {
                                "dual-role-resource-hand",
                                "chance-weapon-resource-hand",
                                "absorption-weapon-resource-hand",
                            }:
                                dual_roles = plain_dual_role_weapon_cards(snapshot)
                                if not dual_roles:
                                    raise ValueError(
                                        "accepted snapshot contains no supported dual-role weapon"
                                    )
                                dual_role_catalog = [
                                    {
                                        "attack": attack,
                                        "defense": defense,
                                        "element": element,
                                        "element_id": COMBAT_ELEMENT_IDS[element],
                                        "kind": "dual-role-weapon",
                                        "slug": slug,
                                        "token_id": vocabulary.token_id("weapons", slug),
                                    }
                                    for slug, (attack, defense, element) in sorted(
                                        dual_roles.items()
                                    )
                                ]
                                dual_role_args = (
                                    np.asarray(
                                        [row["token_id"] for row in dual_role_catalog],
                                        dtype=np.uint32,
                                    ),
                                    np.asarray(
                                        [row["attack"] for row in dual_role_catalog],
                                        dtype=np.uint16,
                                    ),
                                    np.asarray(
                                        [row["defense"] for row in dual_role_catalog],
                                        dtype=np.uint16,
                                    ),
                                    np.asarray(
                                        [row["element_id"] for row in dual_role_catalog],
                                        dtype=np.uint8,
                                    ),
                                )
                                if ruleset in {
                                    "chance-weapon-resource-hand",
                                    "absorption-weapon-resource-hand",
                                }:
                                    chance_weapons = plain_chance_weapon_cards(snapshot)
                                    chance_dual_roles = plain_chance_dual_role_weapon_cards(
                                        snapshot
                                    )
                                    if not chance_weapons or not chance_dual_roles:
                                        raise ValueError(
                                            "accepted snapshot contains no supported chance "
                                            "weapon/dual-role weapon"
                                        )
                                    chance_weapon_catalog = [
                                        {
                                            "attack": attack,
                                            "element": element,
                                            "element_id": COMBAT_ELEMENT_IDS[element],
                                            "hit_rate": hit_rate,
                                            "kind": "chance-weapon",
                                            "slug": slug,
                                            "token_id": vocabulary.token_id("weapons", slug),
                                        }
                                        for slug, (hit_rate, attack, element) in sorted(
                                            chance_weapons.items()
                                        )
                                    ]
                                    chance_dual_role_catalog = [
                                        {
                                            "attack": attack,
                                            "defense": defense,
                                            "element": element,
                                            "element_id": COMBAT_ELEMENT_IDS[element],
                                            "hit_rate": hit_rate,
                                            "kind": "chance-dual-role-weapon",
                                            "slug": slug,
                                            "token_id": vocabulary.token_id("weapons", slug),
                                        }
                                        for slug, (hit_rate, attack, defense, element) in sorted(
                                            chance_dual_roles.items()
                                        )
                                    ]
                                    chance_weapon_token_ids = np.asarray(
                                        [row["token_id"] for row in chance_weapon_catalog],
                                        dtype=np.uint32,
                                    )
                                    chance_weapon_values = np.asarray(
                                        [row["attack"] for row in chance_weapon_catalog],
                                        dtype=np.uint16,
                                    )
                                    chance_weapon_elements = np.asarray(
                                        [row["element_id"] for row in chance_weapon_catalog],
                                        dtype=np.uint8,
                                    )
                                    chance_weapon_hit_rates = np.asarray(
                                        [row["hit_rate"] for row in chance_weapon_catalog],
                                        dtype=np.uint16,
                                    )
                                    chance_dual_role_token_ids = np.asarray(
                                        [row["token_id"] for row in chance_dual_role_catalog],
                                        dtype=np.uint32,
                                    )
                                    chance_dual_role_attack_values = np.asarray(
                                        [row["attack"] for row in chance_dual_role_catalog],
                                        dtype=np.uint16,
                                    )
                                    chance_dual_role_defense_values = np.asarray(
                                        [row["defense"] for row in chance_dual_role_catalog],
                                        dtype=np.uint16,
                                    )
                                    chance_dual_role_elements = np.asarray(
                                        [row["element_id"] for row in chance_dual_role_catalog],
                                        dtype=np.uint8,
                                    )
                                    chance_dual_role_hit_rates = np.asarray(
                                        [row["hit_rate"] for row in chance_dual_role_catalog],
                                        dtype=np.uint16,
                                    )
                                    if ruleset == "absorption-weapon-resource-hand":
                                        absorption_weapons = verified_absorption_weapon_cards(
                                            snapshot
                                        )
                                        chance_absorption_weapons = (
                                            verified_chance_absorption_weapon_cards(snapshot)
                                        )
                                        if not absorption_weapons or not chance_absorption_weapons:
                                            raise ValueError(
                                                "accepted snapshot contains no supported fixed/"
                                                "chance absorption weapon"
                                            )
                                        absorption_weapon_catalog = [
                                            {
                                                "attack": attack,
                                                "effect": "absorbHP",
                                                "element": element,
                                                "element_id": COMBAT_ELEMENT_IDS[element],
                                                "kind": "absorption-weapon",
                                                "slug": slug,
                                                "token_id": vocabulary.token_id("weapons", slug),
                                            }
                                            for slug, (attack, element) in sorted(
                                                absorption_weapons.items()
                                            )
                                        ]
                                        chance_absorption_weapon_catalog = [
                                            {
                                                "attack": attack,
                                                "effect": "absorbHP",
                                                "element": element,
                                                "element_id": COMBAT_ELEMENT_IDS[element],
                                                "hit_rate": hit_rate,
                                                "kind": "chance-absorption-weapon",
                                                "slug": slug,
                                                "token_id": vocabulary.token_id("weapons", slug),
                                            }
                                            for slug, (hit_rate, attack, element) in sorted(
                                                chance_absorption_weapons.items()
                                            )
                                        ]
                                        batch = AbsorptionWeaponResourceAttackDefenseBatch(
                                            *resource_args,
                                            *stochastic_args,
                                            *additive_args,
                                            reflection_armor_token_ids,
                                            reflection_weapon_token_ids,
                                            reflection_weapon_values,
                                            *dual_role_args,
                                            chance_weapon_token_ids,
                                            chance_weapon_values,
                                            chance_weapon_elements,
                                            chance_weapon_hit_rates,
                                            chance_dual_role_token_ids,
                                            chance_dual_role_attack_values,
                                            chance_dual_role_defense_values,
                                            chance_dual_role_elements,
                                            chance_dual_role_hit_rates,
                                            np.asarray(
                                                [
                                                    row["token_id"]
                                                    for row in absorption_weapon_catalog
                                                ],
                                                dtype=np.uint32,
                                            ),
                                            np.asarray(
                                                [
                                                    row["attack"]
                                                    for row in absorption_weapon_catalog
                                                ],
                                                dtype=np.uint16,
                                            ),
                                            np.asarray(
                                                [
                                                    row["element_id"]
                                                    for row in absorption_weapon_catalog
                                                ],
                                                dtype=np.uint8,
                                            ),
                                            np.asarray(
                                                [
                                                    row["token_id"]
                                                    for row in chance_absorption_weapon_catalog
                                                ],
                                                dtype=np.uint32,
                                            ),
                                            np.asarray(
                                                [
                                                    row["attack"]
                                                    for row in chance_absorption_weapon_catalog
                                                ],
                                                dtype=np.uint16,
                                            ),
                                            np.asarray(
                                                [
                                                    row["element_id"]
                                                    for row in chance_absorption_weapon_catalog
                                                ],
                                                dtype=np.uint8,
                                            ),
                                            np.asarray(
                                                [
                                                    row["hit_rate"]
                                                    for row in chance_absorption_weapon_catalog
                                                ],
                                                dtype=np.uint16,
                                            ),
                                            seed,
                                            initial_hp,
                                            initial_mp,
                                        )
                                    else:
                                        batch = ChanceWeaponResourceAttackDefenseBatch(
                                            *resource_args,
                                            *stochastic_args,
                                            *additive_args,
                                            reflection_armor_token_ids,
                                            reflection_weapon_token_ids,
                                            reflection_weapon_values,
                                            *dual_role_args,
                                            chance_weapon_token_ids,
                                            chance_weapon_values,
                                            chance_weapon_elements,
                                            chance_weapon_hit_rates,
                                            chance_dual_role_token_ids,
                                            chance_dual_role_attack_values,
                                            chance_dual_role_defense_values,
                                            chance_dual_role_elements,
                                            chance_dual_role_hit_rates,
                                            seed,
                                            initial_hp,
                                            initial_mp,
                                        )
                                else:
                                    batch = DualRoleResourceAttackDefenseBatch(
                                        *resource_args,
                                        *stochastic_args,
                                        *additive_args,
                                        reflection_armor_token_ids,
                                        reflection_weapon_token_ids,
                                        reflection_weapon_values,
                                        *dual_role_args,
                                        seed,
                                        initial_hp,
                                        initial_mp,
                                    )
                            else:
                                batch = ReflectionWeaponResourceAttackDefenseBatch(
                                    *resource_args,
                                    *stochastic_args,
                                    *additive_args,
                                    reflection_armor_token_ids,
                                    reflection_weapon_token_ids,
                                    reflection_weapon_values,
                                    seed,
                                    initial_hp,
                                    initial_mp,
                                )
                        else:
                            batch = ReflectionResourceAttackDefenseBatch(
                                *resource_args,
                                *stochastic_args,
                                *additive_args,
                                reflection_armor_token_ids,
                                seed,
                                initial_hp,
                                initial_mp,
                            )
                    else:
                        batch = ExpandedResourceAttackDefenseBatch(
                            *resource_args,
                            *stochastic_args,
                            *additive_args,
                            seed,
                            initial_hp,
                            initial_mp,
                        )
                else:
                    batch = StochasticResourceAttackDefenseBatch(
                        *resource_args,
                        *stochastic_args,
                        seed,
                        initial_hp,
                        initial_mp,
                    )
                stochastic_catalog = (
                    chance_catalog
                    + effect_catalog
                    + additive_catalog
                    + reflection_catalog
                    + reflection_weapon_catalog
                    + dual_role_catalog
                    + chance_weapon_catalog
                    + chance_dual_role_catalog
                    + absorption_weapon_catalog
                    + chance_absorption_weapon_catalog
                )
            else:
                batch = ResourceAttackDefenseBatch(
                    *resource_args,
                    seed,
                    initial_hp,
                    initial_mp,
                )
            booster_catalog += (
                hp_utility_catalog
                + mp_utility_catalog
                + attack_miracle_catalog
                + hp_miracle_catalog
                + stochastic_catalog
            )
        else:
            batch = ComboAttackDefenseBatch(
                batch_size,
                weapon_token_ids,
                attack_values,
                weapon_elements,
                booster_token_ids,
                booster_values,
                booster_elements,
                armor_token_ids,
                defense_values,
                armor_elements,
                seed,
                initial_hp,
            )
    elif ruleset == "elemental-hand":
        weapon_elements = np.asarray([row["element_id"] for row in weapon_catalog], dtype=np.uint8)
        armor_elements = np.asarray([row["element_id"] for row in armor_catalog], dtype=np.uint8)
        batch = ElementalAttackDefenseBatch(
            batch_size,
            weapon_token_ids,
            attack_values,
            weapon_elements,
            armor_token_ids,
            defense_values,
            armor_elements,
            seed,
            initial_hp,
        )
    else:
        batch = AttackDefenseBatch(
            batch_size,
            weapon_token_ids,
            attack_values,
            armor_token_ids,
            defense_values,
            seed,
            initial_hp,
            ruleset == "mixed-hand",
        )
    catalog = weapon_catalog + booster_catalog + armor_catalog
    sampling_distribution: Literal[
        "fixed-role-uniform-redraw-with-replacement",
        "mixed-role-uniform-redraw-with-attack-liveness",
        "elemental-mixed-role-uniform-redraw-with-attack-liveness",
        "elemental-combo-4-2-3-initial-uniform-redraw-with-base-liveness",
        "elemental-resource-3-1-2-2-1-initial-uniform-redraw-with-base-liveness",
        "elemental-stochastic-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-expanded-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-reflection-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-reflection-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-dual-role-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-chance-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
        "elemental-absorption-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness",
    ]
    action_semantics: Literal["atomic-attack-defense-macro", "sequential-combo-selection"] = (
        "atomic-attack-defense-macro"
    )
    if ruleset == "absorption-weapon-resource-hand":
        kernel_schema_version = ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = (
            ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        )
        ruleset_id = ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-absorption-weapon-resource-2-1-2-1-1-1-1-"
            "initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "chance-weapon-resource-hand":
        kernel_schema_version = CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = (
            CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        )
        ruleset_id = CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-chance-weapon-resource-2-1-2-1-1-1-1-"
            "initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "dual-role-resource-hand":
        kernel_schema_version = DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-dual-role-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "reflection-weapon-resource-hand":
        kernel_schema_version = REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = (
            REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        )
        ruleset_id = REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-reflection-weapon-resource-2-1-2-1-1-1-1-"
            "initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "reflection-resource-hand":
        kernel_schema_version = REFLECTION_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = REFLECTION_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = REFLECTION_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-reflection-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "expanded-resource-hand":
        kernel_schema_version = EXPANDED_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = EXPANDED_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = EXPANDED_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-expanded-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "stochastic-resource-hand":
        kernel_schema_version = STOCHASTIC_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = STOCHASTIC_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = STOCHASTIC_RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-stochastic-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "resource-hand":
        kernel_schema_version = RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = RESOURCE_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = ELEMENTAL_GLOBAL_FEATURE_COUNT
        sampling_distribution = (
            "elemental-resource-3-1-2-2-1-initial-uniform-redraw-with-base-liveness"
        )
        action_semantics = "sequential-combo-selection"
    elif ruleset == "combo-hand":
        kernel_schema_version = COMBO_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = COMBO_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = COMBO_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = ELEMENTAL_GLOBAL_FEATURE_COUNT
        sampling_distribution = "elemental-combo-4-2-3-initial-uniform-redraw-with-base-liveness"
        action_semantics = "sequential-combo-selection"
    elif ruleset == "elemental-hand":
        kernel_schema_version = ELEMENTAL_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = ELEMENTAL_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = ELEMENTAL_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = ELEMENTAL_GLOBAL_FEATURE_COUNT
        sampling_distribution = "elemental-mixed-role-uniform-redraw-with-attack-liveness"
    elif ruleset == "mixed-hand":
        kernel_schema_version = MIXED_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = MIXED_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = MIXED_ATTACK_DEFENSE_RULESET_ID
        global_feature_count = 6
        sampling_distribution = "mixed-role-uniform-redraw-with-attack-liveness"
    else:
        kernel_schema_version = ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION
        observation_schema_version = ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION
        ruleset_id = ATTACK_DEFENSE_RULESET_ID
        global_feature_count = 6
        sampling_distribution = "fixed-role-uniform-redraw-with-replacement"
    return AttackDefenseSimulation(
        batch=batch,
        metadata=SimulationMetadata(
            kernel_schema_version=kernel_schema_version,
            observation_schema_version=observation_schema_version,
            ruleset_id=ruleset_id,
            client_sha256=snapshot.client.sha256,
            vocabulary_sha256=hashlib.sha256(vocabulary.model_dump_json().encode()).hexdigest(),
            rule_catalog_sha256=_sha256_json(catalog),
            rule_catalog_size=len(catalog),
            action_count=ACTION_COUNT,
            hand_slots=HAND_SLOTS,
            global_feature_count=global_feature_count,
            action_semantics=action_semantics,
            sampling_distribution=sampling_distribution,
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


def benchmark_attack_defense_simulation(
    snapshot_path: Path,
    *,
    batch_size: int,
    batch_steps: int,
    seed: int = 67,
    ruleset: AttackDefenseRuleset = "fixed-role",
) -> SimulationBenchmark:
    """Measure native attack/defense transitions without neural inference."""

    import numpy as np

    simulation = create_attack_defense_simulation(
        snapshot_path,
        batch_size=batch_size,
        seed=seed,
        ruleset=ruleset,
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
