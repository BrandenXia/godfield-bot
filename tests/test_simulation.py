import gc
from pathlib import Path

import pytest

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.simulation import (
    benchmark_attack_defense_simulation,
    benchmark_fixed_attack_simulation,
    create_attack_defense_simulation,
    create_fixed_attack_simulation,
    simulation_feature_tensors,
)
from godfield_bot.simulation_policy import (
    CurriculumHeuristic,
    build_curriculum_heuristic,
    curriculum_heuristic_actions,
)

np = pytest.importorskip("numpy")
godfield_sim = pytest.importorskip("godfield_sim")
FixedAttackBatch = godfield_sim.FixedAttackBatch
AttackDefenseBatch = godfield_sim.AttackDefenseBatch
ElementalAttackDefenseBatch = godfield_sim.ElementalAttackDefenseBatch
ComboAttackDefenseBatch = godfield_sim.ComboAttackDefenseBatch
ResourceAttackDefenseBatch = godfield_sim.ResourceAttackDefenseBatch
StochasticResourceAttackDefenseBatch = godfield_sim.StochasticResourceAttackDefenseBatch
ExpandedResourceAttackDefenseBatch = godfield_sim.ExpandedResourceAttackDefenseBatch
ReflectionResourceAttackDefenseBatch = godfield_sim.ReflectionResourceAttackDefenseBatch
ReflectionWeaponResourceAttackDefenseBatch = godfield_sim.ReflectionWeaponResourceAttackDefenseBatch
DualRoleResourceAttackDefenseBatch = godfield_sim.DualRoleResourceAttackDefenseBatch
ChanceWeaponResourceAttackDefenseBatch = godfield_sim.ChanceWeaponResourceAttackDefenseBatch
AbsorptionWeaponResourceAttackDefenseBatch = godfield_sim.AbsorptionWeaponResourceAttackDefenseBatch
DynamicMpWeaponResourceAttackDefenseBatch = godfield_sim.DynamicMpWeaponResourceAttackDefenseBatch
SameDamageWeaponResourceAttackDefenseBatch = godfield_sim.SameDamageWeaponResourceAttackDefenseBatch
AttackTwiceWeaponResourceAttackDefenseBatch = (
    godfield_sim.AttackTwiceWeaponResourceAttackDefenseBatch
)
RandomTargetWeaponResourceAttackDefenseBatch = (
    godfield_sim.RandomTargetWeaponResourceAttackDefenseBatch
)
IllnessWeaponResourceAttackDefenseBatch = godfield_sim.IllnessWeaponResourceAttackDefenseBatch
IllnessCureResourceAttackDefenseBatch = godfield_sim.IllnessCureResourceAttackDefenseBatch
HeavenHerbResourceAttackDefenseBatch = godfield_sim.HeavenHerbResourceAttackDefenseBatch
FeverMaskResourceAttackDefenseBatch = godfield_sim.FeverMaskResourceAttackDefenseBatch
MiracleBlockResourceAttackDefenseBatch = godfield_sim.MiracleBlockResourceAttackDefenseBatch
MiracleBlockWeaponResourceAttackDefenseBatch = (
    godfield_sim.MiracleBlockWeaponResourceAttackDefenseBatch
)
MiracleBounceResourceAttackDefenseBatch = godfield_sim.MiracleBounceResourceAttackDefenseBatch

SNAPSHOT_PATH = Path(__file__).parents[1] / "data" / "snapshots" / "2026-09-07" / "bible.json"


def native_batch(*, batch_size: int = 4, attack: int = 13) -> FixedAttackBatch:
    return FixedAttackBatch(
        batch_size,
        np.asarray([2], dtype=np.uint32),
        np.asarray([attack], dtype=np.uint16),
        67,
        40,
    )


def defense_batch(*, batch_size: int = 4, attack: int = 13, defense: int = 4) -> AttackDefenseBatch:
    return AttackDefenseBatch(
        batch_size,
        np.asarray([2], dtype=np.uint32),
        np.asarray([attack], dtype=np.uint16),
        np.asarray([3], dtype=np.uint32),
        np.asarray([defense], dtype=np.uint16),
        67,
        40,
    )


def elemental_batch(
    *,
    batch_size: int = 8,
    attack: int = 13,
    defense: int = 4,
    attack_element: int = 0,
    defense_element: int = 0,
) -> ElementalAttackDefenseBatch:
    return ElementalAttackDefenseBatch(
        batch_size,
        np.asarray([2], dtype=np.uint32),
        np.asarray([attack], dtype=np.uint16),
        np.asarray([attack_element], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([defense], dtype=np.uint16),
        np.asarray([defense_element], dtype=np.uint8),
        67,
        40,
    )


def combo_batch(
    *,
    attack: int = 10,
    boost: int = 3,
    defense: int = 8,
    attack_element: int = 1,
    booster_element: int = 5,
    defense_element: int = 2,
) -> ComboAttackDefenseBatch:
    return ComboAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([attack], dtype=np.uint16),
        np.asarray([attack_element], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([boost], dtype=np.uint16),
        np.asarray([booster_element], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([defense], dtype=np.uint16),
        np.asarray([defense_element], dtype=np.uint8),
        67,
        40,
    )


def resource_batch(
    *,
    seed: int = 14,
    initial_hp: int = 40,
    initial_mp: int = 10,
    miracle_cost: int = 12,
) -> ResourceAttackDefenseBatch:
    return ResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([miracle_cost], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([7], dtype=np.uint16),
        seed,
        initial_hp,
        initial_mp,
    )


def stochastic_resource_batch(
    *,
    seed: int = 0,
    chance_hit_rate: int = 50,
) -> StochasticResourceAttackDefenseBatch:
    return StochasticResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([chance_hit_rate], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        seed,
        40,
        10,
    )


def expanded_resource_batch(
    *,
    seed: int = 0,
    initial_mp: int = 10,
    additive_cost: int = 7,
) -> ExpandedResourceAttackDefenseBatch:
    return ExpandedResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([50], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([11], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([additive_cost], dtype=np.uint16),
        seed,
        40,
        initial_mp,
    )


def reflection_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
) -> ReflectionResourceAttackDefenseBatch:
    return ReflectionResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([50], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([11], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([2], dtype=np.uint16),
        np.asarray([12], dtype=np.uint32),
        seed,
        initial_hp,
        10,
    )


def reflection_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    weapon_element: int = godfield_sim.ELEMENT_NON_ELEMENT,
) -> ReflectionWeaponResourceAttackDefenseBatch:
    return ReflectionWeaponResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([weapon_element], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([50], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([11], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([2], dtype=np.uint16),
        np.asarray([12], dtype=np.uint32),
        np.asarray([13], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        seed,
        initial_hp,
        10,
    )


def dual_role_resource_batch(
    *,
    seed: int = 0,
    weapon_element: int = godfield_sim.ELEMENT_NON_ELEMENT,
) -> DualRoleResourceAttackDefenseBatch:
    return DualRoleResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([weapon_element], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([50], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([11], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([2], dtype=np.uint16),
        np.asarray([12], dtype=np.uint32),
        np.asarray([13], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([14, 15], dtype=np.uint32),
        np.asarray([5, 4], dtype=np.uint16),
        np.asarray([7, 4], dtype=np.uint16),
        np.asarray(
            [godfield_sim.ELEMENT_NON_ELEMENT, godfield_sim.ELEMENT_FIRE],
            dtype=np.uint8,
        ),
        seed,
        40,
        10,
    )


def chance_weapon_resource_batch(
    *,
    seed: int = 0,
    chance_hit_rate: int = 50,
) -> ChanceWeaponResourceAttackDefenseBatch:
    return ChanceWeaponResourceAttackDefenseBatch(
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([50], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([11], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([2], dtype=np.uint16),
        np.asarray([12], dtype=np.uint32),
        np.asarray([13], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([14], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([15], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([chance_hit_rate], dtype=np.uint16),
        np.asarray([16], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([6], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WOOD], dtype=np.uint8),
        np.asarray([75], dtype=np.uint16),
        seed,
        40,
        10,
    )


def absorption_weapon_resource_args(*, chance_hit_rate: int = 50) -> tuple[object, ...]:
    return (
        1,
        np.asarray([2], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([3], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([5], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([6], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint32),
        np.asarray([25], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WATER], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([8], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([3], dtype=np.uint16),
        np.asarray([9], dtype=np.uint32),
        np.asarray([20], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([50], dtype=np.uint16),
        np.asarray([10], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([4], dtype=np.uint16),
        np.asarray([11], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([2], dtype=np.uint16),
        np.asarray([12], dtype=np.uint32),
        np.asarray([13], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([14], dtype=np.uint32),
        np.asarray([5], dtype=np.uint16),
        np.asarray([7], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([15], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
        np.asarray([50], dtype=np.uint16),
        np.asarray([16], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([6], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WOOD], dtype=np.uint8),
        np.asarray([75], dtype=np.uint16),
        np.asarray([17], dtype=np.uint32),
        np.asarray([10], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([18], dtype=np.uint32),
        np.asarray([8], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_WOOD], dtype=np.uint8),
        np.asarray([chance_hit_rate], dtype=np.uint16),
    )


def absorption_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 30,
    initial_mp: int = 10,
    chance_hit_rate: int = 50,
) -> AbsorptionWeaponResourceAttackDefenseBatch:
    return AbsorptionWeaponResourceAttackDefenseBatch(
        *absorption_weapon_resource_args(chance_hit_rate=chance_hit_rate),
        seed,
        initial_hp,
        initial_mp,
    )


def dynamic_mp_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    initial_mp: int = 10,
) -> DynamicMpWeaponResourceAttackDefenseBatch:
    return DynamicMpWeaponResourceAttackDefenseBatch(
        *absorption_weapon_resource_args(),
        np.asarray([19], dtype=np.uint32),
        np.asarray([2], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        seed,
        initial_hp,
        initial_mp,
    )


def same_damage_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    initial_mp: int = 10,
) -> SameDamageWeaponResourceAttackDefenseBatch:
    return SameDamageWeaponResourceAttackDefenseBatch(
        *absorption_weapon_resource_args(),
        np.asarray([19], dtype=np.uint32),
        np.asarray([2], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([20], dtype=np.uint32),
        np.asarray([14], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        seed,
        initial_hp,
        initial_mp,
    )


def attack_twice_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    initial_mp: int = 10,
    armor_defense: int = 8,
) -> AttackTwiceWeaponResourceAttackDefenseBatch:
    base_args = list(absorption_weapon_resource_args())
    base_args[8] = np.asarray([armor_defense], dtype=np.uint16)
    return AttackTwiceWeaponResourceAttackDefenseBatch(
        *base_args,
        np.asarray([19], dtype=np.uint32),
        np.asarray([2], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([20], dtype=np.uint32),
        np.asarray([14], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([21], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        seed,
        initial_hp,
        initial_mp,
    )


def random_target_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    initial_mp: int = 10,
) -> RandomTargetWeaponResourceAttackDefenseBatch:
    return RandomTargetWeaponResourceAttackDefenseBatch(
        *absorption_weapon_resource_args(),
        np.asarray([19], dtype=np.uint32),
        np.asarray([2], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([20], dtype=np.uint32),
        np.asarray([14], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([21], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([22], dtype=np.uint32),
        np.asarray([30], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        seed,
        initial_hp,
        initial_mp,
    )


def illness_weapon_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    initial_mp: int = 10,
    armor_defense: int = 8,
) -> IllnessWeaponResourceAttackDefenseBatch:
    base_args = list(absorption_weapon_resource_args())
    base_args[8] = np.asarray([armor_defense], dtype=np.uint16)
    return IllnessWeaponResourceAttackDefenseBatch(
        *base_args,
        np.asarray([19], dtype=np.uint32),
        np.asarray([2], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([20], dtype=np.uint32),
        np.asarray([14], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([21], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([22], dtype=np.uint32),
        np.asarray([30], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([23, 24], dtype=np.uint32),
        np.asarray([8, 8], dtype=np.uint16),
        np.asarray(
            [godfield_sim.ELEMENT_NON_ELEMENT, godfield_sim.ELEMENT_NON_ELEMENT],
            dtype=np.uint8,
        ),
        np.asarray([godfield_sim.ILLNESS_COLD, godfield_sim.ILLNESS_HELL], dtype=np.uint16),
        seed,
        initial_hp,
        initial_mp,
    )


def illness_cure_resource_batch(
    *,
    seed: int = 0,
    initial_hp: int = 40,
    initial_mp: int = 10,
    armor_defense: int = 8,
    heaven_herb: bool = False,
    fever_mask: bool = False,
    miracle_block: bool = False,
    miracle_block_weapon: bool = False,
    miracle_bounce: bool = False,
    miracle_block_defense: int = 15,
) -> (
    IllnessCureResourceAttackDefenseBatch
    | HeavenHerbResourceAttackDefenseBatch
    | FeverMaskResourceAttackDefenseBatch
    | MiracleBlockResourceAttackDefenseBatch
    | MiracleBlockWeaponResourceAttackDefenseBatch
    | MiracleBounceResourceAttackDefenseBatch
):
    base_args = list(absorption_weapon_resource_args())
    base_args[8] = np.asarray([armor_defense], dtype=np.uint16)
    curriculum_args = (
        *base_args,
        np.asarray([19], dtype=np.uint32),
        np.asarray([2], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([20], dtype=np.uint32),
        np.asarray([14], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([21], dtype=np.uint32),
        np.asarray([3], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_NON_ELEMENT], dtype=np.uint8),
        np.asarray([22], dtype=np.uint32),
        np.asarray([30], dtype=np.uint16),
        np.asarray([godfield_sim.ELEMENT_LIGHT], dtype=np.uint8),
        np.asarray([23, 24], dtype=np.uint32),
        np.asarray([8, 8], dtype=np.uint16),
        np.asarray(
            [godfield_sim.ELEMENT_NON_ELEMENT, godfield_sim.ELEMENT_NON_ELEMENT],
            dtype=np.uint8,
        ),
        np.asarray([godfield_sim.ILLNESS_COLD, godfield_sim.ILLNESS_HELL], dtype=np.uint16),
        np.asarray([25, 26, 27, 28], dtype=np.uint32),
        np.asarray([0, 0, 2, 5], dtype=np.uint16),
        np.asarray([1, 2, 1, 2], dtype=np.uint16),
    )
    if heaven_herb or fever_mask or miracle_block or miracle_block_weapon or miracle_bounce:
        heaven_args = (
            *curriculum_args,
            np.asarray([29], dtype=np.uint32),
            np.asarray([20], dtype=np.uint16),
        )
        if fever_mask or miracle_block or miracle_block_weapon or miracle_bounce:
            batch_type = (
                MiracleBounceResourceAttackDefenseBatch
                if miracle_bounce
                else (
                    MiracleBlockWeaponResourceAttackDefenseBatch
                    if miracle_block_weapon
                    else (
                        MiracleBlockResourceAttackDefenseBatch
                        if miracle_block
                        else FeverMaskResourceAttackDefenseBatch
                    )
                )
            )
            return batch_type(
                *heaven_args,
                np.asarray([30], dtype=np.uint32),
                np.asarray([10], dtype=np.uint16),
                np.asarray([godfield_sim.ELEMENT_FIRE], dtype=np.uint8),
                np.asarray([31], dtype=np.uint32)
                if miracle_block or miracle_block_weapon or miracle_bounce
                else np.asarray([], dtype=np.uint32),
                np.asarray([miracle_block_defense], dtype=np.uint16)
                if miracle_block or miracle_block_weapon or miracle_bounce
                else np.asarray([], dtype=np.uint16),
                np.asarray([32, 33, 34], dtype=np.uint32)
                if miracle_block_weapon or miracle_bounce
                else np.asarray([], dtype=np.uint32),
                np.asarray([11, 13, 15], dtype=np.uint16)
                if miracle_block_weapon or miracle_bounce
                else np.asarray([], dtype=np.uint16),
                np.asarray([35], dtype=np.uint32)
                if miracle_block_weapon or miracle_bounce
                else np.asarray([], dtype=np.uint32),
                np.asarray([15], dtype=np.uint16)
                if miracle_block_weapon or miracle_bounce
                else np.asarray([], dtype=np.uint16),
                np.asarray([36], dtype=np.uint32)
                if miracle_bounce
                else np.asarray([], dtype=np.uint32),
                np.asarray([9], dtype=np.uint16)
                if miracle_bounce
                else np.asarray([], dtype=np.uint16),
                seed,
                initial_hp,
                initial_mp,
            )
        return HeavenHerbResourceAttackDefenseBatch(
            *heaven_args,
            seed,
            initial_hp,
            initial_mp,
        )
    return IllnessCureResourceAttackDefenseBatch(
        *curriculum_args,
        seed,
        initial_hp,
        initial_mp,
    )


def first_legal_actions(batch: FixedAttackBatch) -> np.ndarray:
    return batch.action_mask.argmax(axis=1).astype(np.int64)


def test_snapshot_factory_fingerprints_non_promotable_curriculum() -> None:
    simulation = create_fixed_attack_simulation(SNAPSHOT_PATH, batch_size=8)

    assert simulation.metadata.kernel_schema_version == 2
    assert simulation.metadata.observation_schema_version == 2
    assert simulation.metadata.ruleset_id == "plain-attack-redraw-duel-v1"
    assert simulation.metadata.rule_catalog_size == 18
    assert simulation.metadata.action_count == 21
    assert simulation.metadata.hand_slots == 9
    assert simulation.metadata.sampling_distribution == "uniform-redraw-with-replacement"
    assert simulation.metadata.promotion_eligible is False
    assert simulation.batch.batch_size == 8


def test_defense_factory_fingerprints_neutral_role_catalogs() -> None:
    simulation = create_attack_defense_simulation(SNAPSHOT_PATH, batch_size=8)

    assert simulation.metadata.kernel_schema_version == 1
    assert simulation.metadata.observation_schema_version == 2
    assert simulation.metadata.ruleset_id == "plain-attack-defense-redraw-duel-v1"
    assert simulation.metadata.rule_catalog_size == 33
    assert simulation.metadata.sampling_distribution == (
        "fixed-role-uniform-redraw-with-replacement"
    )
    assert simulation.metadata.promotion_eligible is False
    assert simulation.batch.batch_size == 8


def test_mixed_hand_factory_versions_distribution_without_changing_observation_schema() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="mixed-hand",
    )
    kinds = simulation.batch.hand_card_kinds

    assert simulation.metadata.kernel_schema_version == 1
    assert simulation.metadata.observation_schema_version == 2
    assert simulation.metadata.ruleset_id == ("plain-mixed-hand-attack-defense-redraw-duel-v1")
    assert simulation.metadata.sampling_distribution == (
        "mixed-role-uniform-redraw-with-attack-liveness"
    )
    assert simulation.batch.mixed_hands is True
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_WEAPON, axis=1) == 5)
    assert np.any(kinds[:, :5] == godfield_sim.CARD_KIND_ARMOR)
    assert np.any(kinds[:, 5:] == godfield_sim.CARD_KIND_WEAPON)
    np.testing.assert_array_equal(
        simulation.batch.action_mask[:, 1:10],
        kinds == godfield_sim.CARD_KIND_WEAPON,
    )


def test_elemental_factory_versions_expanded_catalog_and_observation() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="elemental-hand",
    )

    assert simulation.metadata.schema_version == 2
    assert simulation.metadata.kernel_schema_version == 1
    assert simulation.metadata.observation_schema_version == 3
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-mixed-hand-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 86
    assert simulation.metadata.global_feature_count == 13
    assert simulation.metadata.sampling_distribution == (
        "elemental-mixed-role-uniform-redraw-with-attack-liveness"
    )
    assert simulation.batch.mixed_hands is True
    assert simulation.batch.elemental is True
    assert simulation.batch.global_feature_count == 13
    assert simulation.batch.global_features.shape == (128, 13)
    assert simulation.batch.hand_elements.shape == (128, 9)
    assert int(simulation.batch.hand_elements.max()) == godfield_sim.ELEMENT_DARKNESS


def test_combo_factory_versions_catalog_and_sequential_action_contract() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="combo-hand",
    )
    kinds = simulation.batch.hand_card_kinds

    assert simulation.metadata.observation_schema_version == 4
    assert simulation.metadata.ruleset_id == ("plain-elemental-combo-attack-defense-redraw-duel-v1")
    assert simulation.metadata.rule_catalog_size == 103
    assert simulation.metadata.action_semantics == "sequential-combo-selection"
    assert simulation.metadata.sampling_distribution == (
        "elemental-combo-4-2-3-initial-uniform-redraw-with-base-liveness"
    )
    assert simulation.batch.combo is True
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_WEAPON, axis=1) == 4)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ATTACK_BOOSTER, axis=1) == 2)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ARMOR, axis=1) == 3)


def test_resource_factory_versions_catalog_resources_and_initial_deal() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="resource-hand",
    )
    batch = simulation.batch
    kinds = batch.hand_card_kinds

    assert simulation.metadata.observation_schema_version == 5
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 117
    assert simulation.metadata.action_semantics == "sequential-combo-selection"
    assert simulation.metadata.sampling_distribution == (
        "elemental-resource-3-1-2-2-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.resource_curriculum is True
    assert batch.initial_mp == 10
    assert np.all(batch.magic_points == 10)
    assert np.allclose(batch.global_features[:, 2], 0.10)
    assert np.allclose(batch.player_features[:, :, 1], 0.10)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_WEAPON, axis=1) == 3)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ARMOR, axis=1) == 2)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ATTACK_BOOSTER, axis=1) == 1)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ATTACK_MIRACLE, axis=1) == 1)
    assert np.all(
        np.count_nonzero(
            np.isin(
                kinds,
                [
                    godfield_sim.CARD_KIND_HP_UTILITY,
                    godfield_sim.CARD_KIND_MP_UTILITY,
                    godfield_sim.CARD_KIND_HP_MIRACLE,
                ],
            ),
            axis=1,
        )
        == 2
    )


def test_stochastic_resource_factory_versions_catalog_effect_signal_and_initial_deal() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="stochastic-resource-hand",
    )
    batch = simulation.batch
    kinds = batch.hand_card_kinds

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 124
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-stochastic-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.stochastic_resource_curriculum is True
    assert batch.global_features.shape == (128, 14)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_WEAPON, axis=1) == 2)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ARMOR, axis=1) == 2)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ATTACK_BOOSTER, axis=1) == 1)
    assert np.all(np.count_nonzero(kinds == godfield_sim.CARD_KIND_ATTACK_MIRACLE, axis=1) == 1)
    assert np.all(
        np.count_nonzero(kinds == godfield_sim.CARD_KIND_CHANCE_ATTACK_MIRACLE, axis=1) == 1
    )
    assert np.all(
        np.count_nonzero(kinds == godfield_sim.CARD_KIND_EFFECT_ATTACK_MIRACLE, axis=1) == 1
    )


def test_expanded_resource_factory_versions_additive_miracle_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="expanded-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-additive-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 126
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-expanded-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.stochastic_resource_curriculum is True
    assert batch.additive_miracle_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_ADDITIVE_MIRACLE)


def test_additive_miracle_accumulates_cost_and_is_reusable() -> None:
    batch = expanded_resource_batch(seed=0, initial_mp=7, additive_cost=7)
    attacker = int(batch.active_players[0])
    weapon_slot = int(np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0])
    additive_slot = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ADDITIVE_MIRACLE)[0]
    )

    batch.step(np.asarray([weapon_slot + 1], dtype=np.int64))
    assert batch.action_mask[0, additive_slot + 1]
    batch.step(np.asarray([additive_slot + 1], dtype=np.int64))

    assert batch.selected_values[0] == 15
    assert batch.selected_elements[0] == godfield_sim.ELEMENT_FIRE
    assert batch.magic_points[0, attacker] == 7
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    assert batch.magic_points[0, attacker] == 0
    assert batch.pending_attacks[0] == 15
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))

    opponent_weapon = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0]
    )
    batch.step(np.asarray([opponent_weapon + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
    assert batch.active_players[0] == attacker
    assert batch.hand_token_ids[0, additive_slot] == 11

    next_weapon = int(np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0])
    batch.step(np.asarray([next_weapon + 1], dtype=np.int64))
    assert not batch.action_mask[0, additive_slot + 1]


def test_reflection_resource_factory_versions_super_mirror_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="reflection-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-additive-reflection-resource-miracle-"
        "attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 127
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-reflection-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.reflection_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_REFLECTION_ARMOR)


def test_reflection_weapon_factory_versions_dual_role_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="reflection-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-additive-reflection-weapon-resource-"
        "miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 128
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-reflection-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.reflection_curriculum is True
    assert batch.reflection_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_REFLECTION_ARMOR)
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_REFLECTION_WEAPON)


def test_dual_role_factory_versions_atk_def_weapon_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="dual-role-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-additive-reflection-dual-role-resource-"
        "miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 135
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-dual-role-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.dual_role_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_DUAL_ROLE)


def test_chance_weapon_factory_versions_effect_free_chance_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="chance-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-weapon-additive-reflection-"
        "dual-role-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 150
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-chance-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.chance_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_CHANCE_WEAPON)
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_CHANCE_DUAL_ROLE)


def test_absorption_weapon_factory_versions_effect_weapon_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="absorption-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-additive-"
        "reflection-dual-role-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 153
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-absorption-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.absorption_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_ABSORPTION_WEAPON)
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_CHANCE_ABSORPTION_WEAPON)


def test_dynamic_mp_weapon_factory_versions_consuming_weapon_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="dynamic-mp-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "additive-reflection-dual-role-resource-miracle-attack-defense-redraw-"
        "duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 154
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-dynamic-mp-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.dynamic_mp_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_DYNAMIC_MP_WEAPON)


def test_same_damage_weapon_factory_versions_evil_broadsword_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="same-damage-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-additive-reflection-dual-role-resource-miracle-"
        "attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 155
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-same-damage-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.same_damage_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_SAME_DAMAGE_WEAPON)


def test_attack_twice_weapon_factory_versions_saw_boom_boom_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="attack-twice-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-additive-reflection-dual-role-"
        "resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 156
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-attack-twice-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.attack_twice_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_ATTACK_TWICE_WEAPON)


def test_random_target_weapon_factory_versions_dangerous_pestle_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="random-target-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 6
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-additive-"
        "reflection-dual-role-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 157
    assert simulation.metadata.global_feature_count == 14
    assert simulation.metadata.sampling_distribution == (
        "elemental-random-target-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.random_target_weapon_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_RANDOM_TARGET_WEAPON)


def test_illness_weapon_factory_versions_status_catalog_and_observation() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="illness-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-additive-reflection-dual-role-resource-miracle-attack-defense-"
        "redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 161
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-illness-weapon-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.illness_weapon_curriculum is True
    assert batch.illness_stages.shape == (512, 2)
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_ILLNESS_WEAPON)


def test_illness_cure_factory_keeps_schema_and_adds_verified_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="illness-cure-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-illness-cure-additive-reflection-dual-role-resource-miracle-"
        "attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 165
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-illness-cure-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.illness_weapon_curriculum is True
    assert batch.illness_cure_curriculum is True
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_ILLNESS_CURE_SUNDRY)
    assert np.any(batch.hand_card_kinds == godfield_sim.CARD_KIND_ILLNESS_CURE_MIRACLE)
    cure_cards = np.isin(
        batch.hand_card_kinds,
        [
            godfield_sim.CARD_KIND_ILLNESS_CURE_SUNDRY,
            godfield_sim.CARD_KIND_ILLNESS_CURE_MIRACLE,
        ],
    )
    assert not np.any(batch.action_mask[:, 1:10][cure_cards])


def test_heaven_herb_factory_keeps_schema_and_adds_verified_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="heaven-herb-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-illness-cure-heaven-herb-additive-reflection-dual-role-resource-"
        "miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 166
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-heaven-herb-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.illness_cure_curriculum is True
    assert batch.heaven_herb_curriculum is True
    herb_cards = batch.hand_card_kinds == godfield_sim.CARD_KIND_HEAVEN_HERB
    assert np.any(herb_cards)
    assert np.all(batch.action_mask[:, 1:10][herb_cards])


def test_fever_mask_factory_keeps_schema_and_adds_verified_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="fever-mask-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-illness-cure-heaven-herb-fever-mask-additive-reflection-dual-"
        "role-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 167
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-fever-mask-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.heaven_herb_curriculum is True
    assert batch.fever_mask_curriculum is True
    fever_masks = batch.hand_card_kinds == godfield_sim.CARD_KIND_FEVER_MASK
    assert np.any(fever_masks)
    assert np.all(batch.hand_elements[fever_masks] == godfield_sim.ELEMENT_FIRE)


def test_miracle_block_factory_keeps_schema_and_adds_verified_catalog() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="miracle-block-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-illness-cure-heaven-herb-fever-mask-miracle-block-additive-"
        "reflection-dual-role-resource-miracle-attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 171
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-miracle-block-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
    )
    assert batch.fever_mask_curriculum is True
    assert batch.miracle_block_curriculum is True
    angel_armor = batch.hand_card_kinds == godfield_sim.CARD_KIND_MIRACLE_BLOCK_ARMOR
    assert np.any(angel_armor)
    assert np.all(batch.hand_elements[angel_armor] == godfield_sim.ELEMENT_NON_ELEMENT)


def test_miracle_block_weapon_factory_adds_verified_dual_role_family() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="miracle-block-weapon-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-illness-cure-heaven-herb-fever-mask-miracle-block-armor-weapon-"
        "additive-reflection-dual-role-resource-miracle-attack-defense-redraw-"
        "duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 175
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-miracle-block-weapon-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.miracle_block_curriculum is True
    assert batch.miracle_block_weapon_curriculum is True
    angel_weapons = batch.hand_card_kinds == godfield_sim.CARD_KIND_MIRACLE_BLOCK_WEAPON
    angel_bows = batch.hand_card_kinds == godfield_sim.CARD_KIND_MIRACLE_BLOCK_BOOSTER
    assert np.any(angel_weapons)
    assert np.any(angel_bows)
    assert np.all(batch.hand_elements[angel_weapons | angel_bows] == 0)


def test_miracle_bounce_factory_adds_verified_sky_armor_family() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=512,
        ruleset="miracle-bounce-resource-hand",
    )
    batch = simulation.batch

    assert simulation.metadata.observation_schema_version == 7
    assert simulation.metadata.ruleset_id == (
        "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
        "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-"
        "weapon-illness-cure-heaven-herb-fever-mask-miracle-block-armor-weapon-"
        "miracle-bounce-armor-additive-reflection-dual-role-resource-miracle-"
        "attack-defense-redraw-duel-v1"
    )
    assert simulation.metadata.rule_catalog_size == 180
    assert simulation.metadata.global_feature_count == 16
    assert simulation.metadata.sampling_distribution == (
        "elemental-miracle-bounce-resource-2-1-2-1-1-1-1-"
        "initial-uniform-redraw-with-base-liveness"
    )
    assert batch.miracle_block_weapon_curriculum is True
    assert batch.miracle_bounce_curriculum is True
    sky_armor = batch.hand_card_kinds == godfield_sim.CARD_KIND_MIRACLE_BOUNCE_ARMOR
    assert np.any(sky_armor)
    assert np.all(batch.hand_elements[sky_armor] == godfield_sim.ELEMENT_NON_ELEMENT)


def miracle_block_defense_batch(
    attack_token: int,
    *,
    defense_token: int = 31,
    miracle_block_defense: int = 15,
) -> tuple[MiracleBlockResourceAttackDefenseBatch, int, int]:
    for seed in range(32768):
        batch = illness_cure_resource_batch(
            seed=seed,
            miracle_block=True,
            miracle_block_weapon=defense_token in {32, 33, 34, 35},
            miracle_block_defense=miracle_block_defense,
        )
        attacker = int(batch.active_players[0])
        attack_slots = np.flatnonzero(batch.hand_token_ids[0] == attack_token)
        if not attack_slots.size:
            continue
        attack_action = int(attack_slots[0]) + 1
        if not batch.action_mask[0, attack_action]:
            continue
        batch.step(np.asarray([attack_action], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        if batch.phases[0] != godfield_sim.PHASE_DEFENSE:
            continue
        angel_slots = np.flatnonzero(batch.hand_token_ids[0] == defense_token)
        if not angel_slots.size:
            continue
        return batch, attacker, int(angel_slots[0])
    raise AssertionError("fixture seeds did not expose attack into miracle-block armor")


def miracle_bounce_defense_batch(
    attack_token: int,
) -> tuple[MiracleBounceResourceAttackDefenseBatch, int, int]:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, miracle_bounce=True)
        attacker = int(batch.active_players[0])
        attack_slots = np.flatnonzero(batch.hand_token_ids[0] == attack_token)
        if not attack_slots.size:
            continue
        attack_action = int(attack_slots[0]) + 1
        if not batch.action_mask[0, attack_action]:
            continue
        batch.step(np.asarray([attack_action], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        if batch.phases[0] != godfield_sim.PHASE_DEFENSE:
            continue
        sky_slots = np.flatnonzero(batch.hand_token_ids[0] == 36)
        if sky_slots.size:
            return batch, attacker, int(sky_slots[0])
    raise AssertionError("fixture seeds did not expose attack into miracle-bounce armor")


@pytest.mark.parametrize("attack_token", [7, 9, 10])
def test_sky_armor_bounces_attack_miracle_to_random_duel_player(attack_token: int) -> None:
    batch, _attacker, sky_slot = miracle_bounce_defense_batch(attack_token)
    pending_attack = int(batch.pending_attacks[0])

    assert batch.action_mask[0, sky_slot + 1]
    batch.step(np.asarray([sky_slot + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert batch.phases[0] == godfield_sim.PHASE_DEFENSE
    assert batch.pending_attacks[0] == pending_attack
    assert batch.pending_bounced[0]
    assert batch.active_players[0] in {0, 1}


def test_sky_armor_uses_printed_defense_against_weapon() -> None:
    batch, _attacker, sky_slot = miracle_bounce_defense_batch(2)

    assert batch.pending_base_kinds[0] == godfield_sim.CARD_KIND_WEAPON
    assert batch.action_mask[0, sky_slot + 1]
    batch.step(np.asarray([sky_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == 9
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert not batch.pending_bounced[0]
    assert round(float(batch.player_features[0, 0, 0]) * 100) == 39


def test_miracle_bounce_samples_both_living_duel_targets() -> None:
    targets: set[int] = set()
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, miracle_bounce=True)
        attack_slots = np.flatnonzero(batch.hand_token_ids[0] == 7)
        if not attack_slots.size:
            continue
        attack_action = int(attack_slots[0]) + 1
        if not batch.action_mask[0, attack_action]:
            continue
        batch.step(np.asarray([attack_action], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        sky_slots = np.flatnonzero(batch.hand_token_ids[0] == 36)
        if not sky_slots.size:
            continue
        batch.step(np.asarray([int(sky_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        targets.add(int(batch.active_players[0]))
        if targets == {0, 1}:
            return
    raise AssertionError(f"bounce did not sample both duel targets: {targets}")


def test_miracle_bounce_is_one_hop_bounded() -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, miracle_bounce=True)
        attack_slots = np.flatnonzero(batch.hand_token_ids[0] == 7)
        if not attack_slots.size:
            continue
        attack_action = int(attack_slots[0]) + 1
        if not batch.action_mask[0, attack_action]:
            continue
        batch.step(np.asarray([attack_action], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        first_sky = np.flatnonzero(batch.hand_token_ids[0] == 36)
        if not first_sky.size:
            continue
        batch.step(np.asarray([int(first_sky[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        second_sky = np.flatnonzero(batch.hand_token_ids[0] == 36)
        if not second_sky.size:
            continue

        assert batch.pending_bounced[0]
        assert not batch.action_mask[0, int(second_sky[0]) + 1]
        return
    raise AssertionError("fixture seeds did not expose a second Sky armor after bounce")


@pytest.mark.parametrize(
    ("attack_token", "expected_kind", "expected_attack"),
    [
        (7, godfield_sim.CARD_KIND_ATTACK_MIRACLE, 25),
        (9, godfield_sim.CARD_KIND_CHANCE_ATTACK_MIRACLE, 20),
        (10, godfield_sim.CARD_KIND_EFFECT_ATTACK_MIRACLE, 10),
    ],
)
def test_miracle_block_armor_fully_blocks_attack_miracle(
    attack_token: int,
    expected_kind: int,
    expected_attack: int,
) -> None:
    batch, attacker, angel_slot = miracle_block_defense_batch(attack_token)
    defender_hp_before = round(float(batch.player_features[0, 0, 0]) * 100)

    assert batch.pending_base_kinds[0] == expected_kind
    assert batch.pending_attacks[0] == expected_attack
    assert batch.action_mask[0, angel_slot + 1]
    batch.step(np.asarray([angel_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == batch.pending_attacks[0]
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert not batch.terminated[0]
    assert round(float(batch.player_features[0, 0, 0]) * 100) == defender_hp_before
    assert batch.active_players[0] == 1 - attacker


def test_miracle_block_armor_uses_listed_defense_against_weapon() -> None:
    batch, _attacker, angel_slot = miracle_block_defense_batch(
        2,
        miracle_block_defense=5,
    )

    assert batch.pending_base_kinds[0] == godfield_sim.CARD_KIND_WEAPON
    assert batch.action_mask[0, angel_slot + 1]
    batch.step(np.asarray([angel_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == 5
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert round(float(batch.player_features[0, 0, 0]) * 100) == 35


def test_miracle_block_armor_obeys_elements_for_weapon() -> None:
    batch, _attacker, angel_slot = miracle_block_defense_batch(15)

    assert batch.pending_base_kinds[0] == godfield_sim.CARD_KIND_CHANCE_WEAPON
    assert batch.pending_elements[0] == godfield_sim.ELEMENT_FIRE
    assert not batch.action_mask[0, angel_slot + 1]


def test_miracle_block_weapon_is_a_consumable_base_attack() -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, miracle_block_weapon=True)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 32)
        if not weapon_slots.size:
            continue
        action = int(weapon_slots[0]) + 1
        assert batch.action_mask[0, action]
        batch.step(np.asarray([action], dtype=np.int64))
        assert batch.selected_values[0] == 11
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

        assert batch.pending_base_kinds[0] == godfield_sim.CARD_KIND_MIRACLE_BLOCK_WEAPON
        assert batch.pending_attacks[0] == 11
        return
    raise AssertionError("fixture seeds did not expose Angel Knife as an attack")


def test_angel_bow_requires_a_weapon_base_and_adds_attack() -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, miracle_block_weapon=True)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 2)
        bow_slots = np.flatnonzero(batch.hand_token_ids[0] == 35)
        if not weapon_slots.size or not bow_slots.size:
            continue
        bow_action = int(bow_slots[0]) + 1
        assert not batch.action_mask[0, bow_action]
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        visible_bows = np.flatnonzero(batch.hand_token_ids[0] == 35)
        assert visible_bows.size
        bow_action = int(visible_bows[0]) + 1
        assert batch.action_mask[0, bow_action]
        batch.step(np.asarray([bow_action], dtype=np.int64))

        assert batch.selected_values[0] == 25
        return
    raise AssertionError("fixture seeds did not expose weapon plus Angel Bow")


@pytest.mark.parametrize("defense_token", [32, 35])
def test_miracle_block_weapon_and_booster_fully_block_miracles(
    defense_token: int,
) -> None:
    batch, _attacker, defense_slot = miracle_block_defense_batch(
        7,
        defense_token=defense_token,
    )

    assert batch.action_mask[0, defense_slot + 1]
    batch.step(np.asarray([defense_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == batch.pending_attacks[0] == 25


@pytest.mark.parametrize("defense_token", [32, 35])
def test_miracle_block_weapon_and_booster_cannot_defend_weapons(
    defense_token: int,
) -> None:
    batch, _attacker, defense_slot = miracle_block_defense_batch(
        2,
        defense_token=defense_token,
    )

    assert not batch.action_mask[0, defense_slot + 1]


def fever_mask_defense_batch(
    *,
    initial_hp: int = 40,
    require_plain_armor: bool = False,
    require_plain_weapon: bool = False,
) -> tuple[FeverMaskResourceAttackDefenseBatch, int, int, int | None]:
    for seed in range(32768):
        batch = illness_cure_resource_batch(
            seed=seed,
            initial_hp=initial_hp,
            fever_mask=True,
        )
        attacker = int(batch.active_players[0])
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 2)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        fever_slots = np.flatnonzero(batch.hand_token_ids[0] == 30)
        armor_slots = np.flatnonzero(batch.hand_token_ids[0] == 4)
        defender_weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 2)
        if (
            not fever_slots.size
            or (require_plain_armor and not armor_slots.size)
            or (require_plain_weapon and not defender_weapon_slots.size)
        ):
            continue
        fever_slot = int(fever_slots[0])
        if not batch.action_mask[0, fever_slot + 1]:
            continue
        armor_slot = int(armor_slots[0]) if armor_slots.size else None
        return batch, attacker, fever_slot, armor_slot
    raise AssertionError("fixture seeds did not expose a Fever Mask defense")


def test_fever_mask_blocks_damage_and_inflicts_fever_after_survival() -> None:
    batch, attacker, fever_slot, _armor_slot = fever_mask_defense_batch(require_plain_weapon=True)
    defender = 1 - attacker
    defender_hp_before = round(float(batch.player_features[0, 0, 0]) * 100)
    turns_before = int(batch.turn_numbers[0])

    batch.step(np.asarray([fever_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == 10
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert not batch.terminated[0]
    assert batch.active_players[0] == defender
    assert batch.illness_stages[0, defender] == godfield_sim.ILLNESS_FEVER
    assert round(float(batch.player_features[0, 0, 0]) * 100) == defender_hp_before
    assert batch.turn_numbers[0] == turns_before + 1
    assert batch.selected_counts[0] == 0

    defender_weapon_slot = int(np.flatnonzero(batch.hand_token_ids[0] == 2)[0])
    batch.step(np.asarray([defender_weapon_slot + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))

    assert batch.illness_stages[0, defender] >= godfield_sim.ILLNESS_FEVER
    assert round(float(batch.player_features[0, 1, 0]) * 100) == defender_hp_before - 2


def test_fever_mask_is_masked_against_illness_weapons() -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, fever_mask=True)
        illness_slots = np.flatnonzero(batch.hand_token_ids[0] == 23)
        if not illness_slots.size:
            continue
        batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        fever_slots = np.flatnonzero(batch.hand_token_ids[0] == 30)
        if not fever_slots.size:
            continue

        assert not batch.action_mask[0, int(fever_slots[0]) + 1]
        return
    raise AssertionError("fixture seeds did not expose illness attack into Fever Mask")


def reflected_attack_batch(
    *, initial_hp: int = 40
) -> tuple[ReflectionResourceAttackDefenseBatch, int, int]:
    for seed in range(128):
        batch = reflection_resource_batch(seed=seed, initial_hp=initial_hp)
        attacker = int(batch.active_players[0])
        weapon_slot = int(
            np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0]
        )
        batch.step(np.asarray([weapon_slot + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        reflection_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_ARMOR
        )
        if reflection_slots.size:
            return batch, attacker, int(reflection_slots[0])
    raise AssertionError("fixture seeds did not produce reflection armor for the defender")


def reflection_weapon_defense_batch() -> tuple[ReflectionWeaponResourceAttackDefenseBatch, int]:
    for seed in range(512):
        batch = reflection_weapon_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        reflection_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_WEAPON
        )
        if reflection_slots.size:
            return batch, int(reflection_slots[0])
    raise AssertionError("fixture seeds did not produce Reflection Sword for the defender")


def test_reflection_sword_is_a_consumed_one_hop_defense_against_ne_weapon() -> None:
    batch, reflection_slot = reflection_weapon_defense_batch()
    original_attacker = 1 - int(batch.active_players[0])

    assert batch.pending_attacks[0] == 10
    assert batch.pending_elements[0] == godfield_sim.ELEMENT_NON_ELEMENT
    assert batch.action_mask[0, reflection_slot + 1]
    batch.step(np.asarray([reflection_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == 0
    assert np.count_nonzero(batch.action_mask[0]) == 1
    assert batch.action_mask[0, godfield_sim.CONFIRM_ACTION_INDEX]

    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    assert batch.active_players[0] == original_attacker
    assert batch.pending_attacks[0] == 10
    assert batch.pending_reflected[0]
    assert not np.any(
        batch.action_mask[0, 1:10]
        & (batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_WEAPON)
    )


def test_reflection_sword_can_lead_an_attack() -> None:
    for seed in range(512):
        batch = reflection_weapon_resource_batch(seed=seed)
        slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_WEAPON)
        if not slots.size:
            continue
        action = int(slots[0]) + 1
        assert batch.action_mask[0, action]
        batch.step(np.asarray([action], dtype=np.int64))
        assert batch.selected_values[0] == 10
        assert batch.action_mask[0, godfield_sim.CONFIRM_ACTION_INDEX]
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.pending_attacks[0] == 10
        return
    raise AssertionError("fixture seeds did not produce an attackable Reflection Sword")


def test_reflection_sword_does_not_reflect_a_miracle() -> None:
    for seed in range(512):
        batch = reflection_weapon_resource_batch(seed=seed)
        miracle_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ATTACK_MIRACLE
        )
        if not miracle_slots.size:
            continue
        batch.step(np.asarray([int(miracle_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        reflection_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_WEAPON
        )
        if not reflection_slots.size:
            continue
        assert all(not batch.action_mask[0, int(slot) + 1] for slot in reflection_slots)
        return
    raise AssertionError("fixture seeds did not produce miracle/Reflection Sword response")


def test_reflection_sword_does_not_reflect_an_elemental_weapon() -> None:
    for seed in range(512):
        batch = reflection_weapon_resource_batch(
            seed=seed,
            weapon_element=godfield_sim.ELEMENT_FIRE,
        )
        weapon_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        reflection_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_WEAPON
        )
        if not reflection_slots.size:
            continue
        assert all(not batch.action_mask[0, int(slot) + 1] for slot in reflection_slots)
        return
    raise AssertionError("fixture seeds did not produce elemental/Reflection Sword response")


def test_dual_role_weapon_uses_atk_on_attack_and_def_on_defense() -> None:
    attack_by_token = {14: 5, 15: 4}
    defense_by_token = {14: 7, 15: 4}

    for seed in range(512):
        attack_batch = dual_role_resource_batch(seed=seed)
        dual_slots = np.flatnonzero(
            attack_batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_DUAL_ROLE
        )
        if dual_slots.size:
            slot = int(dual_slots[0])
            token = int(attack_batch.hand_token_ids[0, slot])
            attack_batch.step(np.asarray([slot + 1], dtype=np.int64))
            assert attack_batch.selected_values[0] == attack_by_token[token]
            break
    else:
        raise AssertionError("fixture seeds did not produce a dual-role attack")

    for seed in range(512):
        defense_batch = dual_role_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(
            defense_batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON
        )
        if not weapon_slots.size:
            continue
        defense_batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        defense_batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        dual_slots = np.flatnonzero(
            defense_batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_DUAL_ROLE
        )
        if not dual_slots.size:
            continue
        slot = int(dual_slots[0])
        token = int(defense_batch.hand_token_ids[0, slot])
        assert defense_batch.action_mask[0, slot + 1]
        defense_batch.step(np.asarray([slot + 1], dtype=np.int64))
        assert defense_batch.selected_values[0] == defense_by_token[token]
        defense_batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        expected_hp = (40 - (10 - defense_by_token[token])) / 100
        assert defense_batch.player_features[0, 0, 0] == pytest.approx(expected_hp)
        assert defense_batch.turn_numbers[0] == 1
        return
    raise AssertionError("fixture seeds did not produce a dual-role defense")


@pytest.mark.parametrize(
    ("attack_element", "expected_legal"),
    [
        (godfield_sim.ELEMENT_WATER, True),
        (godfield_sim.ELEMENT_FIRE, False),
    ],
)
def test_elemental_dual_role_defense_uses_armor_compatibility(
    attack_element: int,
    expected_legal: bool,
) -> None:
    for seed in range(512):
        batch = dual_role_resource_batch(seed=seed, weapon_element=attack_element)
        weapon_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        fire_slots = np.flatnonzero(batch.hand_token_ids[0] == 15)
        if not fire_slots.size:
            continue
        assert bool(batch.action_mask[0, int(fire_slots[0]) + 1]) is expected_legal
        return
    raise AssertionError("fixture seeds did not produce a Fire dual-role defense")


def test_chance_weapon_can_hit_or_miss_and_is_consumed() -> None:
    outcomes: set[str] = set()
    for seed in range(4096):
        batch = chance_weapon_resource_batch(seed=seed, chance_hit_rate=50)
        slots = np.flatnonzero(batch.hand_token_ids[0] == 15)
        if not slots.size:
            continue
        slot = int(slots[0])
        batch.step(np.asarray([slot + 1], dtype=np.int64))
        assert batch.selected_values[0] == 10
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.selected_counts[0] == 0
        if batch.phases[0] == godfield_sim.PHASE_DEFENSE:
            assert batch.pending_attacks[0] == 10
            outcomes.add("hit")
        else:
            assert batch.phases[0] == godfield_sim.PHASE_ATTACK
            assert batch.pending_attacks[0] == 0
            assert batch.turn_numbers[0] == 1
            outcomes.add("miss")
        if outcomes == {"hit", "miss"}:
            return
    raise AssertionError(f"fixture seeds did not produce both chance outcomes: {outcomes}")


def test_chance_dual_role_uses_hit_rate_when_attacking() -> None:
    outcomes: set[str] = set()
    for seed in range(4096):
        batch = chance_weapon_resource_batch(seed=seed)
        slots = np.flatnonzero(batch.hand_token_ids[0] == 16)
        if not slots.size:
            continue
        batch.step(np.asarray([int(slots[0]) + 1], dtype=np.int64))
        assert batch.selected_values[0] == 8
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        if batch.phases[0] == godfield_sim.PHASE_DEFENSE:
            assert batch.pending_attacks[0] == 8
            outcomes.add("hit")
        else:
            assert batch.phases[0] == godfield_sim.PHASE_ATTACK
            assert batch.pending_attacks[0] == 0
            outcomes.add("miss")
        if outcomes == {"hit", "miss"}:
            return
    raise AssertionError(f"fixture seeds did not produce both Jinn outcomes: {outcomes}")


def test_chance_dual_role_uses_fixed_defense_without_rolling() -> None:
    for seed in range(4096):
        batch = chance_weapon_resource_batch(seed=seed)
        ordinary_weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 2)
        if not ordinary_weapon_slots.size:
            continue
        batch.step(np.asarray([int(ordinary_weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        jinn_slots = np.flatnonzero(batch.hand_token_ids[0] == 16)
        if not jinn_slots.size:
            continue
        slot = int(jinn_slots[0])
        assert batch.action_mask[0, slot + 1]
        batch.step(np.asarray([slot + 1], dtype=np.int64))
        assert batch.selected_values[0] == 6
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.player_features[0, 0, 0] == pytest.approx(0.36)
        assert batch.turn_numbers[0] == 1
        return
    raise AssertionError("fixture seeds did not produce an ordinary attack and Jinn defense")


def test_absorption_weapon_heals_only_actual_damage_after_defense() -> None:
    for seed in range(4096):
        batch = absorption_weapon_resource_batch(seed=seed)
        absorption_slots = np.flatnonzero(batch.hand_token_ids[0] == 17)
        if not absorption_slots.size:
            continue
        batch.step(np.asarray([int(absorption_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        armor_slots = np.flatnonzero(batch.hand_token_ids[0] == 4)
        if not armor_slots.size:
            continue
        batch.step(np.asarray([int(armor_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.player_features[0, 0, 0] == pytest.approx(0.28)
        assert batch.player_features[0, 1, 0] == pytest.approx(0.32)
        return
    raise AssertionError("fixture seeds did not produce absorption against numeric defense")


def test_chance_absorption_weapon_heals_on_hit_but_not_miss() -> None:
    outcomes: set[str] = set()
    for seed in range(4096):
        batch = absorption_weapon_resource_batch(seed=seed, chance_hit_rate=50)
        slots = np.flatnonzero(batch.hand_token_ids[0] == 18)
        if not slots.size:
            continue
        batch.step(np.asarray([int(slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        if batch.phases[0] == godfield_sim.PHASE_DEFENSE:
            batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
            assert batch.player_features[0, 0, 0] == pytest.approx(0.22)
            assert batch.player_features[0, 1, 0] == pytest.approx(0.38)
            outcomes.add("hit")
        else:
            assert batch.player_features[0, 0, 0] == pytest.approx(0.30)
            assert batch.player_features[0, 1, 0] == pytest.approx(0.30)
            outcomes.add("miss")
        if outcomes == {"hit", "miss"}:
            return
    raise AssertionError(f"fixture seeds did not produce both absorption outcomes: {outcomes}")


def test_reflected_absorption_transfers_healing_to_reflector() -> None:
    for seed in range(8192):
        batch = absorption_weapon_resource_batch(seed=seed)
        absorption_slots = np.flatnonzero(batch.hand_token_ids[0] == 17)
        if not absorption_slots.size:
            continue
        batch.step(np.asarray([int(absorption_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        mirror_slots = np.flatnonzero(batch.hand_token_ids[0] == 12)
        if not mirror_slots.size:
            continue
        batch.step(np.asarray([int(mirror_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.pending_reflected[0]
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.player_features[0, 0, 0] == pytest.approx(0.20)
        assert batch.player_features[0, 1, 0] == pytest.approx(0.40)
        return
    raise AssertionError("fixture seeds did not produce reflected absorption")


def test_dynamic_mp_weapon_snapshots_attack_and_consumes_all_mp_on_confirm() -> None:
    for seed in range(4096):
        batch = dynamic_mp_weapon_resource_batch(seed=seed, initial_mp=13)
        dynamic_slots = np.flatnonzero(batch.hand_token_ids[0] == 19)
        if not dynamic_slots.size:
            continue
        attacker = int(batch.active_players[0])
        batch.step(np.asarray([int(dynamic_slots[0]) + 1], dtype=np.int64))
        assert batch.selected_values[0] == 26
        assert batch.magic_points[0, attacker] == 13
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.pending_attacks[0] == 26
        assert batch.magic_points[0, attacker] == 0
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.player_features[0, 0, 0] == pytest.approx(0.14)
        return
    raise AssertionError("fixture seeds did not produce Magical Stick")


def test_dynamic_mp_weapon_allows_free_boost_but_blocks_paid_miracle_boost() -> None:
    observed: set[str] = set()
    for seed in range(8192):
        batch = dynamic_mp_weapon_resource_batch(seed=seed)
        dynamic_slots = np.flatnonzero(batch.hand_token_ids[0] == 19)
        if not dynamic_slots.size:
            continue
        ordinary_boosters = np.flatnonzero(batch.hand_token_ids[0] == 3)
        miracle_boosters = np.flatnonzero(batch.hand_token_ids[0] == 11)
        batch.step(np.asarray([int(dynamic_slots[0]) + 1], dtype=np.int64))
        if ordinary_boosters.size:
            action = int(ordinary_boosters[0]) + 1
            assert batch.action_mask[0, action]
            batch.step(np.asarray([action], dtype=np.int64))
            assert batch.selected_values[0] == 23
            observed.add("free")
        if miracle_boosters.size:
            action = int(miracle_boosters[0]) + 1
            assert not batch.action_mask[0, action]
            observed.add("paid")
        if observed == {"free", "paid"}:
            return
    raise AssertionError(f"fixture seeds did not expose both booster classes: {observed}")


def test_same_damage_weapon_applies_post_defense_damage_to_both_players() -> None:
    for seed in range(4096):
        batch = same_damage_weapon_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 20)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.global_features[0, 13] == -1.0
        armor_slots = np.flatnonzero(batch.hand_token_ids[0] == 4)
        if not armor_slots.size:
            continue
        batch.step(np.asarray([int(armor_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        np.testing.assert_allclose(batch.player_features[0, :, 0], [0.34, 0.34])
        assert batch.global_features[0, 13] == 0.0
        return
    raise AssertionError("fixture seeds did not produce Evil Broadsword against numeric defense")


def test_same_damage_weapon_skips_user_damage_after_lethal_target_damage() -> None:
    for seed in range(4096):
        batch = same_damage_weapon_resource_batch(seed=seed, initial_hp=10)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 20)
        if not weapon_slots.size:
            continue
        attacker = int(batch.active_players[0])
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.terminated[0]
        assert batch.terminal_returns[0, attacker] == 1.0
        assert batch.terminal_returns[0, 1 - attacker] == -1.0
        np.testing.assert_allclose(batch.player_features[0, :, 0], [0.0, 0.10])
        return
    raise AssertionError("fixture seeds did not produce lethal Evil Broadsword")


def test_same_damage_weapon_defeats_user_after_nonlethal_target_damage() -> None:
    for seed in range(8192):
        batch = same_damage_weapon_resource_batch(seed=seed, initial_hp=15)
        opening_weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 2)
        if not opening_weapon_slots.size:
            continue
        batch.step(np.asarray([int(opening_weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 20)
        if not weapon_slots.size:
            continue
        source = int(batch.active_players[0])
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.terminated[0]
        assert batch.terminal_returns[0, source] == -1.0
        assert batch.terminal_returns[0, 1 - source] == 1.0
        np.testing.assert_allclose(batch.player_features[0, :, 0], [0.01, 0.0])
        return
    raise AssertionError("fixture seeds did not produce a nonlethal same-damage self-KO")


def test_same_damage_weapon_masks_unevidenced_reflection_interaction() -> None:
    for seed in range(8192):
        batch = same_damage_weapon_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 20)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        mirror_slots = np.flatnonzero(batch.hand_token_ids[0] == 12)
        if not mirror_slots.size:
            continue
        assert all(not batch.action_mask[0, int(slot) + 1] for slot in mirror_slots)
        assert batch.action_mask[0, godfield_sim.FORGIVE_ACTION_INDEX]
        return
    raise AssertionError("fixture seeds did not produce Evil Broadsword with reflection")


def test_attack_twice_weapon_opens_two_independent_defense_windows() -> None:
    for seed in range(8192):
        batch = attack_twice_weapon_resource_batch(seed=seed, armor_defense=1)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 21)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        defender = int(batch.active_players[0])
        armor_slots = np.flatnonzero(batch.hand_token_ids[0] == 4)
        if not armor_slots.size:
            continue
        assert batch.global_features[0, 13] == 0.5
        assert batch.pending_strikes_remaining[0] == 2
        batch.step(np.asarray([int(armor_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.phases[0] == godfield_sim.PHASE_DEFENSE
        assert batch.active_players[0] == defender
        assert batch.turn_numbers[0] == 0
        assert batch.selected_counts[0] == 0
        assert not np.any(batch.selected_hand_mask[0])
        assert batch.global_features[0, 13] == 0.25
        assert batch.pending_strikes_remaining[0] == 1
        assert batch.player_features[0, 0, 0] == pytest.approx(0.38)
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.phases[0] == godfield_sim.PHASE_ATTACK
        assert batch.active_players[0] == defender
        assert batch.turn_numbers[0] == 1
        assert batch.global_features[0, 13] == 0.0
        assert batch.pending_strikes_remaining[0] == 1
        assert batch.player_features[0, 0, 0] == pytest.approx(0.35)
        return
    raise AssertionError("fixture seeds did not produce Saw Boom Boom with DEF1")


def test_attack_twice_weapon_stops_after_lethal_first_strike() -> None:
    for seed in range(4096):
        batch = attack_twice_weapon_resource_batch(seed=seed, initial_hp=3)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 21)
        if not weapon_slots.size:
            continue
        attacker = int(batch.active_players[0])
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.terminated[0]
        assert batch.turn_numbers[0] == 1
        assert batch.terminal_returns[0, attacker] == 1.0
        assert batch.terminal_returns[0, 1 - attacker] == -1.0
        return
    raise AssertionError("fixture seeds did not produce lethal Saw Boom Boom")


def test_attack_twice_weapon_masks_unevidenced_booster_and_reflection_composition() -> None:
    observed_booster = False
    observed_reflection = False
    for seed in range(16384):
        batch = attack_twice_weapon_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 21)
        if not weapon_slots.size:
            continue
        booster_slots = np.flatnonzero(batch.hand_token_ids[0] == 3)
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        if booster_slots.size:
            assert all(not batch.action_mask[0, int(slot) + 1] for slot in booster_slots)
            observed_booster = True
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        mirror_slots = np.flatnonzero(batch.hand_token_ids[0] == 12)
        if mirror_slots.size:
            assert all(not batch.action_mask[0, int(slot) + 1] for slot in mirror_slots)
            observed_reflection = True
        if observed_booster and observed_reflection:
            return
    raise AssertionError(
        "fixture seeds did not expose attack-twice booster and reflection composition"
    )


def test_random_target_weapon_reaches_self_and_opponent_paths() -> None:
    observed: set[str] = set()
    for seed in range(16384):
        batch = random_target_weapon_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 22)
        if not weapon_slots.size:
            continue
        source = int(batch.active_players[0])
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert batch.active_players[0] == 1 - source
        if batch.phases[0] == godfield_sim.PHASE_DEFENSE:
            assert batch.pending_attacks[0] == 30
            assert batch.turn_numbers[0] == 0
            assert batch.action_mask[0, godfield_sim.FORGIVE_ACTION_INDEX]
            observed.add("opponent")
        else:
            assert batch.phases[0] == godfield_sim.PHASE_ATTACK
            assert batch.pending_attacks[0] == 0
            assert batch.turn_numbers[0] == 1
            # Player features are ordered as the next actor, then their opponent.
            np.testing.assert_allclose(batch.player_features[0, :, 0], [0.40, 0.10])
            observed.add("self")
        if observed == {"self", "opponent"}:
            return
    raise AssertionError(f"fixture seeds did not expose both random targets: {observed}")


def test_random_target_weapon_self_ko_awards_opponent() -> None:
    for seed in range(16384):
        batch = random_target_weapon_resource_batch(seed=seed, initial_hp=30)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 22)
        if not weapon_slots.size:
            continue
        source = int(batch.active_players[0])
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        if not batch.terminated[0]:
            continue
        assert batch.turn_numbers[0] == 1
        assert batch.terminal_returns[0, source] == -1.0
        assert batch.terminal_returns[0, 1 - source] == 1.0
        return
    raise AssertionError("fixture seeds did not produce a Dangerous Pestle self-KO")


def test_random_target_weapon_masks_unevidenced_booster_and_reflection_composition() -> None:
    observed_booster = False
    observed_reflection = False
    for seed in range(32768):
        batch = random_target_weapon_resource_batch(seed=seed)
        weapon_slots = np.flatnonzero(batch.hand_token_ids[0] == 22)
        if not weapon_slots.size:
            continue
        booster_slots = np.flatnonzero(batch.hand_token_ids[0] == 3)
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        if booster_slots.size:
            assert all(not batch.action_mask[0, int(slot) + 1] for slot in booster_slots)
            observed_booster = True
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        if batch.phases[0] != godfield_sim.PHASE_DEFENSE:
            continue
        mirror_slots = np.flatnonzero(batch.hand_token_ids[0] == 12)
        if mirror_slots.size:
            assert all(not batch.action_mask[0, int(slot) + 1] for slot in mirror_slots)
            observed_reflection = True
        if observed_booster and observed_reflection:
            return
    raise AssertionError(
        "fixture seeds did not expose random-target booster and reflection composition"
    )


@pytest.mark.parametrize(
    ("token", "stage", "effect_feature"),
    [
        (23, godfield_sim.ILLNESS_COLD, 0.5),
        (24, godfield_sim.ILLNESS_HELL, 0.75),
    ],
)
def test_illness_weapon_inflicts_status_only_after_damage(
    token: int, stage: int, effect_feature: float
) -> None:
    for seed in range(32768):
        batch = illness_weapon_resource_batch(seed=seed)
        slots = np.flatnonzero(batch.hand_token_ids[0] == token)
        if not slots.size:
            continue
        source = int(batch.active_players[0])
        batch.step(np.asarray([int(slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        defender = 1 - source
        assert batch.global_features[0, 13] == pytest.approx(effect_feature)
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.illness_stages[0, defender] == stage
        assert batch.global_features[0, 14] == pytest.approx(stage / 4)
        assert batch.turn_numbers[0] == 1
        return
    raise AssertionError(f"fixture seeds did not expose illness weapon token {token}")


def test_illness_weapon_blocked_damage_does_not_inflict_status() -> None:
    for seed in range(32768):
        batch = illness_weapon_resource_batch(seed=seed, armor_defense=8)
        illness_slots = np.flatnonzero(batch.hand_token_ids[0] == 23)
        if not illness_slots.size:
            continue
        batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        armor_slots = np.flatnonzero(batch.hand_token_ids[0] == 4)
        if not armor_slots.size:
            continue
        batch.step(np.asarray([int(armor_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        assert np.all(batch.illness_stages[0] == godfield_sim.ILLNESS_NONE)
        return
    raise AssertionError("fixture seeds did not expose a blockable Cold attack")


def test_illness_weapon_masks_unevidenced_reflection_composition() -> None:
    for seed in range(32768):
        batch = illness_weapon_resource_batch(seed=seed)
        illness_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ILLNESS_WEAPON
        )
        if not illness_slots.size:
            continue
        batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        reflection_slots = np.flatnonzero(
            (batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_ARMOR)
            | (batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_WEAPON)
        )
        if not reflection_slots.size:
            continue
        assert all(not batch.action_mask[0, int(slot) + 1] for slot in reflection_slots)
        return
    raise AssertionError("fixture seeds did not expose status/reflection composition")


def test_cold_ticks_at_end_of_ill_player_turn_and_is_actor_relative() -> None:
    observed_stages: set[int] = set()
    for seed in range(32768):
        batch = illness_weapon_resource_batch(seed=seed, initial_hp=40)
        cold_slots = np.flatnonzero(batch.hand_token_ids[0] == 23)
        if not cold_slots.size:
            continue
        source = int(batch.active_players[0])
        ill_player = 1 - source
        batch.step(np.asarray([int(cold_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        weapon_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not weapon_slots.size:
            continue
        assert batch.active_players[0] == ill_player
        assert batch.global_features[0, 14] == pytest.approx(0.25)
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.turn_numbers[0] == 2
        assert batch.player_features[0, 1, 0] == pytest.approx(0.31)
        observed_stages.add(int(batch.illness_stages[0, ill_player]))
        assert batch.global_features[0, 15] == pytest.approx(
            int(batch.illness_stages[0, ill_player]) / 4
        )
        if observed_stages == {godfield_sim.ILLNESS_COLD, godfield_sim.ILLNESS_FEVER}:
            return
    raise AssertionError(
        f"fixture seeds did not expose both stable and worsening Cold ticks: {observed_stages}"
    )


def test_repeated_illness_advances_one_stage_regardless_of_incoming_stage() -> None:
    for seed in range(32768):
        batch = illness_weapon_resource_batch(seed=seed, initial_hp=100)
        cold_slots = np.flatnonzero(batch.hand_token_ids[0] == 23)
        if not cold_slots.size:
            continue
        source = int(batch.active_players[0])
        ill_player = 1 - source
        batch.step(np.asarray([int(cold_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        ordinary_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not ordinary_slots.size:
            continue
        batch.step(np.asarray([int(ordinary_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        illness_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ILLNESS_WEAPON
        )
        if not illness_slots.size:
            continue
        previous_stage = int(batch.illness_stages[0, ill_player])
        assert previous_stage in {godfield_sim.ILLNESS_COLD, godfield_sim.ILLNESS_FEVER}
        batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.illness_stages[0, ill_player] == previous_stage + 1
        return
    raise AssertionError("fixture seeds did not expose repeated illness attacks")


def test_hell_tick_can_end_the_ill_player_turn_in_defeat() -> None:
    for seed in range(32768):
        batch = illness_weapon_resource_batch(seed=seed, initial_hp=13)
        hell_slots = np.flatnonzero(batch.hand_token_ids[0] == 24)
        if not hell_slots.size:
            continue
        source = int(batch.active_players[0])
        ill_player = 1 - source
        batch.step(np.asarray([int(hell_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        weapon_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not weapon_slots.size:
            continue
        batch.step(np.asarray([int(weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        assert batch.terminated[0]
        assert batch.terminal_returns[0, source] == 1.0
        assert batch.terminal_returns[0, ill_player] == -1.0
        assert batch.turn_numbers[0] == 2
        return
    raise AssertionError("fixture seeds did not expose Hell followed by a plain attack")


def ill_actor_with_cure(
    illness_token: int,
    cure_token: int,
    *,
    start_seed: int = 0,
    initial_mp: int = 10,
) -> tuple[IllnessCureResourceAttackDefenseBatch, int, int]:
    for seed in range(start_seed, 32768):
        batch = illness_cure_resource_batch(seed=seed, initial_mp=initial_mp)
        illness_slots = np.flatnonzero(batch.hand_token_ids[0] == illness_token)
        ordinary_slots = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)
        if not illness_slots.size or not ordinary_slots.size:
            continue
        source = int(batch.active_players[0])
        batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        cure_slots = np.flatnonzero(batch.hand_token_ids[0] == cure_token)
        if cure_slots.size:
            return batch, 1 - source, int(cure_slots[0])
    raise AssertionError(
        f"fixture seeds did not expose illness {illness_token} with cure {cure_token}"
    )


@pytest.mark.parametrize(
    ("cure_token", "legal"),
    [(25, False), (27, False), (26, True), (28, True)],
)
def test_hell_requires_an_all_curses_cure(cure_token: int, legal: bool) -> None:
    batch, ill_player, cure_slot = ill_actor_with_cure(24, cure_token)

    assert batch.active_players[0] == ill_player
    assert batch.illness_stages[0, ill_player] == godfield_sim.ILLNESS_HELL
    assert bool(batch.action_mask[0, cure_slot + 1]) is legal


def test_illness_cure_miracle_requires_its_mp_cost() -> None:
    batch, ill_player, tone_slot = ill_actor_with_cure(23, 27, initial_mp=1)

    assert batch.active_players[0] == ill_player
    assert batch.illness_stages[0, ill_player] == godfield_sim.ILLNESS_COLD
    assert not batch.action_mask[0, tone_slot + 1]


@pytest.mark.parametrize(
    ("illness_token", "cure_token", "cost", "reusable", "start_seed"),
    [
        (23, 25, 0, False, 282),
        (24, 26, 0, False, 134),
        (23, 27, 2, True, 0),
        (24, 28, 5, True, 0),
    ],
)
def test_illness_cure_is_atomic_pre_tick_and_obeys_consumption(
    illness_token: int,
    cure_token: int,
    cost: int,
    reusable: bool,
    start_seed: int,
) -> None:
    batch, ill_player, cure_slot = ill_actor_with_cure(
        illness_token,
        cure_token,
        start_seed=start_seed,
    )
    hp_before = float(batch.player_features[0, 0, 0])
    mp_before = int(batch.magic_points[0, ill_player])
    turns_before = int(batch.turn_numbers[0])

    assert batch.action_mask[0, cure_slot + 1]
    batch.step(np.asarray([cure_slot + 1], dtype=np.int64))

    assert batch.illness_stages[0, ill_player] == godfield_sim.ILLNESS_NONE
    assert batch.magic_points[0, ill_player] == mp_before - cost
    assert batch.player_features[0, 1, 0] == pytest.approx(hp_before)
    assert batch.turn_numbers[0] == turns_before + 1
    opponent_weapon_slot = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0]
    )
    batch.step(np.asarray([opponent_weapon_slot + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
    assert batch.active_players[0] == ill_player
    if reusable:
        assert batch.hand_token_ids[0, cure_slot] == cure_token
        assert batch.hand_card_kinds[0, cure_slot] == (godfield_sim.CARD_KIND_ILLNESS_CURE_MIRACLE)
    else:
        assert batch.hand_token_ids[0, cure_slot] != cure_token


@pytest.mark.parametrize(
    ("illness_token", "expected_stage", "expected_tick"),
    [
        (None, godfield_sim.ILLNESS_HEAVEN, 5),
        (23, godfield_sim.ILLNESS_FEVER, -2),
        (24, godfield_sim.ILLNESS_HEAVEN, 5),
    ],
)
def test_heaven_herb_boosts_mp_adds_curse_and_runs_same_turn_tick(
    illness_token: int | None,
    expected_stage: int,
    expected_tick: int,
) -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(
            seed=seed,
            initial_mp=95,
            heaven_herb=True,
        )
        if illness_token is None:
            actor = int(batch.active_players[0])
        else:
            illness_slots = np.flatnonzero(batch.hand_token_ids[0] == illness_token)
            if not illness_slots.size:
                continue
            source = int(batch.active_players[0])
            batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
            batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
            batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
            if batch.terminated[0]:
                continue
            actor = 1 - source
            starting_stage = (
                godfield_sim.ILLNESS_COLD if illness_token == 23 else godfield_sim.ILLNESS_HELL
            )
            if batch.illness_stages[0, actor] != starting_stage:
                continue
        herb_slots = np.flatnonzero(batch.hand_token_ids[0] == 29)
        if not herb_slots.size:
            continue
        hp_before = round(float(batch.player_features[0, 0, 0]) * 100)
        turns_before = int(batch.turn_numbers[0])
        herb_slot = int(herb_slots[0])

        assert batch.action_mask[0, herb_slot + 1]
        batch.step(np.asarray([herb_slot + 1], dtype=np.int64))
        if batch.terminated[0]:
            continue

        assert batch.magic_points[0, actor] == 100
        assert batch.illness_stages[0, actor] == expected_stage
        assert round(float(batch.player_features[0, 1, 0]) * 100) == hp_before + expected_tick
        assert batch.turn_numbers[0] == turns_before + 1
        return
    raise AssertionError("fixture seeds did not expose stable Heaven Herb resolution")


def test_heaven_herb_is_consumed_and_is_lethal_when_already_in_heaven() -> None:
    for seed in range(262144):
        batch = illness_cure_resource_batch(seed=seed, heaven_herb=True)
        herb_slots = np.flatnonzero(batch.hand_token_ids[0] == 29)
        if not herb_slots.size:
            continue
        actor = int(batch.active_players[0])
        first_herb_slot = int(herb_slots[0])
        batch.step(np.asarray([first_herb_slot + 1], dtype=np.int64))
        if batch.terminated[0]:
            continue
        opponent_weapon_slots = np.flatnonzero(
            batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON
        )
        if not opponent_weapon_slots.size:
            continue
        batch.step(np.asarray([int(opponent_weapon_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        if batch.terminated[0]:
            continue
        herb_slots = np.flatnonzero(batch.hand_token_ids[0] == 29)
        if not herb_slots.size:
            continue

        assert batch.active_players[0] == actor
        assert batch.illness_stages[0, actor] == godfield_sim.ILLNESS_HEAVEN
        batch.step(np.asarray([int(herb_slots[0]) + 1], dtype=np.int64))

        assert batch.terminated[0]
        assert batch.terminal_returns[0, actor] == -1.0
        assert batch.magic_points[0, actor] == 50
        return
    raise AssertionError("fixture seeds did not redraw Heaven Herb for a Heaven player")


def test_super_mirror_redirects_full_attack_into_one_hop_defense() -> None:
    batch, attacker, reflection_slot = reflected_attack_batch()
    reflector = int(batch.active_players[0])

    assert reflector == 1 - attacker
    assert batch.pending_attacks[0] == 10
    assert batch.action_mask[0, reflection_slot + 1]
    batch.step(np.asarray([reflection_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == 0
    assert batch.action_mask[0, godfield_sim.CONFIRM_ACTION_INDEX]
    assert np.count_nonzero(batch.action_mask[0]) == 1

    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    assert batch.active_players[0] == attacker
    assert batch.phases[0] == godfield_sim.PHASE_DEFENSE
    assert batch.pending_attacks[0] == 10
    assert batch.pending_reflected[0]
    np.testing.assert_allclose(batch.player_features[0, :, 0], np.asarray([0.4, 0.4]))
    reflection_slots = np.flatnonzero(
        batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_REFLECTION_ARMOR
    )
    assert all(not batch.action_mask[0, int(slot) + 1] for slot in reflection_slots)

    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
    assert batch.active_players[0] == attacker
    assert batch.phases[0] == godfield_sim.PHASE_ATTACK
    assert batch.turn_numbers[0] == 1
    assert not batch.pending_reflected[0]
    assert batch.player_features[0, 0, 0] == pytest.approx(0.30)


def test_reflection_heuristic_uses_super_mirror_to_prevent_lethal_damage() -> None:
    batch, _attacker, reflection_slot = reflected_attack_batch(initial_hp=1)
    simulation = type("ReflectionSimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={2: 10, 7: 25, 9: 20, 10: 10},
        defenses={4: 8},
        boosters={3: 3, 11: 5},
        reflection_defenses=frozenset({12}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert action == reflection_slot + 1
    batch.step(np.asarray([action], dtype=np.int64))
    confirm = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert confirm == godfield_sim.CONFIRM_ACTION_INDEX


@pytest.mark.parametrize(
    ("seed", "expected_phase", "expected_attack", "expected_turn"),
    [
        (0, godfield_sim.PHASE_DEFENSE, 20, 0),
        (1, godfield_sim.PHASE_ATTACK, 0, 1),
    ],
)
def test_chance_miracle_resolves_deterministic_hit_or_miss_and_always_charges_mp(
    seed: int,
    expected_phase: int,
    expected_attack: int,
    expected_turn: int,
) -> None:
    batch = stochastic_resource_batch(seed=seed)
    attacker = int(batch.active_players[0])
    slot = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_CHANCE_ATTACK_MIRACLE)[0]
    )

    batch.step(np.asarray([slot + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert batch.magic_points[0, attacker] == 6
    assert batch.phases[0] == expected_phase
    assert batch.pending_attacks[0] == expected_attack
    assert batch.turn_numbers[0] == expected_turn


def test_absorption_heals_actual_hp_damage_and_is_visible_during_defense() -> None:
    batch = stochastic_resource_batch()
    attacker = int(batch.active_players[0])
    slot = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_EFFECT_ATTACK_MIRACLE)[0]
    )

    batch.step(np.asarray([slot + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert batch.global_features[0, 13] == 1.0
    assert batch.magic_points[0, attacker] == 6
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
    assert batch.player_features[0, 0, 0] == pytest.approx(0.30)
    assert batch.player_features[0, 1, 0] == pytest.approx(0.50)
    assert batch.global_features[0, 13] == 0.0


def test_resource_utilities_apply_once_and_pass_the_turn() -> None:
    mp_batch = resource_batch(seed=14)
    mp_actor = int(mp_batch.active_players[0])
    mp_action = (
        int(np.flatnonzero(mp_batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_MP_UTILITY)[0]) + 1
    )
    mp_batch.step(np.asarray([mp_action], dtype=np.int64))

    assert mp_batch.magic_points[0, mp_actor] == 15
    assert mp_batch.turn_numbers[0] == 1
    assert mp_batch.active_players[0] == 1 - mp_actor
    assert mp_batch.phases[0] == godfield_sim.PHASE_ATTACK

    hp_batch = resource_batch(seed=14)
    hp_actor = int(hp_batch.active_players[0])
    hp_action = (
        int(np.flatnonzero(hp_batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_HP_UTILITY)[0]) + 1
    )
    hp_batch.step(np.asarray([hp_action], dtype=np.int64))
    assert hp_batch.player_features[0, 1, 0] == pytest.approx(0.50)
    assert hp_batch.magic_points[0, hp_actor] == 10

    spring_batch = resource_batch(seed=2)
    spring_actor = int(spring_batch.active_players[0])
    spring_action = (
        int(np.flatnonzero(spring_batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_HP_MIRACLE)[0])
        + 1
    )
    spring_batch.step(np.asarray([spring_action], dtype=np.int64))
    assert spring_batch.magic_points[0, spring_actor] == 3
    assert spring_batch.player_features[0, 1, 0] == pytest.approx(0.50)


def test_attack_miracle_requires_mp_charges_on_confirm_and_is_reusable() -> None:
    blocked = resource_batch(initial_mp=10, miracle_cost=12)
    miracle_slot = int(
        np.flatnonzero(blocked.hand_card_kinds[0] == godfield_sim.CARD_KIND_ATTACK_MIRACLE)[0]
    )
    assert not blocked.action_mask[0, miracle_slot + 1]

    batch = resource_batch(initial_mp=12, miracle_cost=12)
    attacker = int(batch.active_players[0])
    miracle_slot = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ATTACK_MIRACLE)[0]
    )
    batch.step(np.asarray([miracle_slot + 1], dtype=np.int64))
    assert batch.selected_values[0] == 25
    assert batch.magic_points[0, attacker] == 12
    assert batch.action_mask[0, godfield_sim.CONFIRM_ACTION_INDEX]
    assert np.count_nonzero(batch.action_mask[0]) == 1

    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    assert batch.magic_points[0, attacker] == 0
    assert batch.pending_attacks[0] == 25
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
    opponent_weapon = int(
        np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0]
    )
    batch.step(np.asarray([opponent_weapon + 1], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
    assert batch.active_players[0] == attacker
    assert batch.hand_token_ids[0, miracle_slot] == 7
    assert not batch.action_mask[0, miracle_slot + 1]


def test_resource_actions_are_masked_when_they_cannot_change_state() -> None:
    batch = resource_batch(seed=14, initial_hp=100, initial_mp=100)
    for kind in (
        godfield_sim.CARD_KIND_HP_UTILITY,
        godfield_sim.CARD_KIND_MP_UTILITY,
        godfield_sim.CARD_KIND_HP_MIRACLE,
    ):
        for slot in np.flatnonzero(batch.hand_card_kinds[0] == kind):
            assert not batch.action_mask[0, int(slot) + 1]


def test_resource_heuristic_restores_mp_only_to_unlock_a_stronger_miracle() -> None:
    batch = resource_batch(seed=14, initial_mp=10, miracle_cost=12)
    policy = CurriculumHeuristic(
        attacks={2: 10, 7: 25},
        defenses={4: 8},
        boosters={3: 3},
        hp_utilities={5: (10, 0), 8: (10, 7)},
        mp_utilities={6: 5},
        attack_miracles={7: (25, 12)},
    )
    simulation = type("ResourceSimulation", (), {"batch": batch})()
    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert batch.hand_card_kinds[0, action - 1] == godfield_sim.CARD_KIND_MP_UTILITY

    affordable = resource_batch(seed=14, initial_mp=12, miracle_cost=12)
    affordable_simulation = type("ResourceSimulation", (), {"batch": affordable})()
    action = curriculum_heuristic_actions(
        affordable_simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert affordable.hand_card_kinds[0, action - 1] == (godfield_sim.CARD_KIND_ATTACK_MIRACLE)


def test_resource_heuristics_index_miracle_attacks_in_the_miracle_namespace() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)

    resource = build_curriculum_heuristic(snapshot, vocabulary, ruleset="resource-hand")
    assert resource.attack_miracles
    assert resource.attack_miracles.keys() <= resource.attacks.keys()
    assert 1 not in resource.attack_miracles

    stochastic = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="stochastic-resource-hand",
    )
    assert stochastic.attack_miracles
    assert stochastic.attack_miracles.keys() <= stochastic.attacks.keys()
    assert stochastic.chance_attack_tokens
    assert stochastic.chance_attack_tokens <= stochastic.attack_miracles.keys()

    expanded = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="expanded-resource-hand",
    )
    assert expanded.boosters is not None
    assert expanded.boosters[vocabulary.token_id("miracles", "fireball")] == 2
    assert expanded.boosters[vocabulary.token_id("miracles", "meteor")] == 10

    reflection = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="reflection-resource-hand",
    )
    assert reflection.reflection_defenses == frozenset(
        {vocabulary.token_id("armor", "super-mirror")}
    )

    reflection_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="reflection-weapon-resource-hand",
    )
    assert reflection_weapon.attacks[vocabulary.token_id("weapons", "reflection-sword")] == 10
    assert reflection_weapon.reflection_defenses == frozenset(
        {
            vocabulary.token_id("armor", "super-mirror"),
            vocabulary.token_id("weapons", "reflection-sword"),
        }
    )

    dual_role = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="dual-role-resource-hand",
    )
    assert dual_role.attacks[vocabulary.token_id("weapons", "sword-shield")] == 10
    assert dual_role.defenses[vocabulary.token_id("weapons", "sword-shield")] == 10

    chance_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="chance-weapon-resource-hand",
    )
    jinn = vocabulary.token_id("weapons", "jinn-s-rocking-horse")
    assert chance_weapon.attacks[jinn] == 6
    assert chance_weapon.defenses[jinn] == 6
    assert chance_weapon.attacks[vocabulary.token_id("weapons", "petit-saturn")] == 5
    assert jinn in chance_weapon.chance_attack_tokens

    absorption_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="absorption-weapon-resource-hand",
    )
    ghost_sword = vocabulary.token_id("weapons", "ghost-sword")
    real_ghost_sword = vocabulary.token_id("weapons", "real-ghost-sword")
    vine_shoot = vocabulary.token_id("weapons", "vine-shoot")
    assert absorption_weapon.attacks[ghost_sword] == 7
    assert absorption_weapon.attacks[real_ghost_sword] == 12
    assert absorption_weapon.attacks[vine_shoot] == 2
    assert ghost_sword not in absorption_weapon.chance_attack_tokens
    assert vine_shoot in absorption_weapon.chance_attack_tokens
    assert absorption_weapon.policy_id == "evidenced-absorption-weapon-resource-combo-v1"

    dynamic_mp_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="dynamic-mp-weapon-resource-hand",
    )
    magical_stick = vocabulary.token_id("weapons", "magical-stick")
    assert dynamic_mp_weapon.attacks[magical_stick] == 2
    assert dynamic_mp_weapon.dynamic_mp_attacks == {magical_stick: 2}
    assert dynamic_mp_weapon.policy_id == "evidenced-dynamic-mp-weapon-resource-combo-v1"

    same_damage_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="same-damage-weapon-resource-hand",
    )
    evil_broadsword = vocabulary.token_id("weapons", "evil-broadsword")
    assert same_damage_weapon.attacks[evil_broadsword] == 14
    assert same_damage_weapon.same_damage_attack_tokens == {evil_broadsword}
    assert same_damage_weapon.policy_id == "evidenced-same-damage-weapon-resource-combo-v1"

    attack_twice_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="attack-twice-weapon-resource-hand",
    )
    saw_boom_boom = vocabulary.token_id("weapons", "saw-boom-boom")
    assert attack_twice_weapon.attacks[saw_boom_boom] == 6
    assert attack_twice_weapon.policy_id == "evidenced-attack-twice-weapon-resource-combo-v1"

    random_target_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="random-target-weapon-resource-hand",
    )
    dangerous_pestle = vocabulary.token_id("weapons", "dangerous-pestle")
    assert random_target_weapon.attacks[dangerous_pestle] == 30
    assert random_target_weapon.random_target_attack_tokens == {dangerous_pestle}
    assert dangerous_pestle in random_target_weapon.chance_attack_tokens
    assert random_target_weapon.policy_id == "evidenced-random-target-weapon-resource-combo-v1"

    illness_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="illness-weapon-resource-hand",
    )
    assert illness_weapon.attacks[vocabulary.token_id("weapons", "gale-sword")] == 9
    assert illness_weapon.attacks[vocabulary.token_id("weapons", "hell-scissors")] == 8
    assert illness_weapon.policy_id == "evidenced-illness-weapon-resource-combo-v1"

    illness_cure = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="illness-cure-resource-hand",
    )
    assert illness_cure.illness_cures == {
        vocabulary.token_id("sundries", "heart-shell"): (2, 0),
        vocabulary.token_id("sundries", "smile-shell"): (1, 0),
        vocabulary.token_id("miracles", "song"): (2, 5),
        vocabulary.token_id("miracles", "tone"): (1, 2),
    }
    assert illness_cure.policy_id == "evidenced-illness-cure-resource-combo-v1"

    heaven_herb = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="heaven-herb-resource-hand",
    )
    assert heaven_herb.illness_cures == illness_cure.illness_cures
    assert heaven_herb.heaven_herbs == {
        vocabulary.token_id("sundries", "heaven-herb"): 20,
    }
    assert heaven_herb.policy_id == "evidenced-heaven-herb-resource-combo-v1"

    fever_mask = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="fever-mask-resource-hand",
    )
    fever_mask_token = vocabulary.token_id("armor", "fever-mask")
    assert fever_mask.illness_cures == illness_cure.illness_cures
    assert fever_mask.heaven_herbs == heaven_herb.heaven_herbs
    assert fever_mask.defenses[fever_mask_token] == 10
    assert fever_mask.self_fever_defenses == {fever_mask_token}
    assert fever_mask.policy_id == "evidenced-fever-mask-resource-combo-v1"

    miracle_block = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="miracle-block-resource-hand",
    )
    miracle_block_tokens = {
        vocabulary.token_id("armor", slug)
        for slug in ("angel-armor", "angel-cap", "angel-gauntlet", "angel-shield")
    }
    assert miracle_block.self_fever_defenses == fever_mask.self_fever_defenses
    assert miracle_block.miracle_block_defenses == miracle_block_tokens
    assert miracle_block.defenses[vocabulary.token_id("armor", "angel-armor")] == 15
    assert miracle_block.policy_id == "evidenced-miracle-block-resource-combo-v1"

    miracle_block_weapon = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="miracle-block-weapon-resource-hand",
    )
    angel_knife = vocabulary.token_id("weapons", "angel-knife")
    angel_bow = vocabulary.token_id("weapons", "angel-bow")
    weapon_defense_tokens = {
        vocabulary.token_id("weapons", slug)
        for slug in ("angel-axe", "angel-bow", "angel-knife", "angel-sword")
    }
    assert miracle_block_weapon.attacks[angel_knife] == 11
    assert miracle_block_weapon.boosters is not None
    assert miracle_block_weapon.boosters[angel_bow] == 15
    assert miracle_block_weapon.miracle_block_defenses == (
        miracle_block_tokens | weapon_defense_tokens
    )
    assert miracle_block_weapon.defenses[angel_bow] == 0
    assert miracle_block_weapon.policy_id == "evidenced-miracle-block-weapon-resource-combo-v1"

    miracle_bounce = build_curriculum_heuristic(
        snapshot,
        vocabulary,
        ruleset="miracle-bounce-resource-hand",
    )
    sky_tokens = {
        vocabulary.token_id("armor", slug)
        for slug in ("sky-armor", "sky-boots", "sky-gauntlet", "sky-helm", "sky-shield")
    }
    assert miracle_bounce.miracle_block_defenses == miracle_block_weapon.miracle_block_defenses
    assert miracle_bounce.miracle_bounce_defenses == sky_tokens
    assert miracle_bounce.defenses[vocabulary.token_id("armor", "sky-armor")] == 9
    assert miracle_bounce.policy_id == "evidenced-miracle-bounce-resource-combo-v1"


def test_fever_mask_heuristic_uses_plain_armor_when_curse_is_not_needed() -> None:
    batch, _attacker, fever_slot, armor_slot = fever_mask_defense_batch(require_plain_armor=True)
    assert armor_slot is not None
    simulation = type("FeverMaskSimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={2: 10},
        defenses={4: 8, 30: 10},
        self_fever_defenses=frozenset({30}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert action == armor_slot + 1
    assert action != fever_slot + 1


def test_fever_mask_heuristic_accepts_curse_to_prevent_lethal_damage() -> None:
    batch, _attacker, fever_slot, _armor_slot = fever_mask_defense_batch(initial_hp=5)
    simulation = type("FeverMaskSimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={2: 10},
        defenses={30: 10},
        self_fever_defenses=frozenset({30}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert action == fever_slot + 1


def test_miracle_block_heuristic_values_angel_as_full_miracle_block() -> None:
    batch, _attacker, angel_slot = miracle_block_defense_batch(
        7,
        miracle_block_defense=5,
    )
    simulation = type("MiracleBlockSimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={2: 10, 7: 25},
        defenses={31: 5},
        miracle_block_defenses=frozenset({31}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert action == angel_slot + 1
    batch.step(np.asarray([action], dtype=np.int64))
    assert batch.selected_values[0] == 25


def test_miracle_block_heuristic_keeps_listed_defense_for_weapons() -> None:
    batch, _attacker, angel_slot = miracle_block_defense_batch(
        2,
        miracle_block_defense=5,
    )
    simulation = type("MiracleBlockSimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={2: 10},
        defenses={31: 5},
        miracle_block_defenses=frozenset({31}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert action == angel_slot + 1
    batch.step(np.asarray([action], dtype=np.int64))
    assert batch.selected_values[0] == 5


def test_miracle_bounce_heuristic_values_sky_armor_as_full_redirect() -> None:
    batch, _attacker, sky_slot = miracle_bounce_defense_batch(7)
    simulation = type("MiracleBounceSimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={2: 10, 7: 25},
        defenses={36: 9},
        miracle_bounce_defenses=frozenset({36}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert action == sky_slot + 1


def test_illness_cure_heuristic_prioritizes_a_legal_cure() -> None:
    batch, _ill_player, cure_slot = ill_actor_with_cure(23, 27)
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=1,
        ruleset="illness-cure-resource-hand",
    )
    object.__setattr__(simulation, "batch", batch)
    policy = CurriculumHeuristic(
        attacks={token: 1 for token in range(2, 25)},
        defenses={},
        illness_cures={27: (1, 2)},
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]

    assert action == cure_slot + 1


def test_heaven_herb_heuristic_uses_full_mp_gain_when_healthy() -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, heaven_herb=True)
        herb_slots = np.flatnonzero(batch.hand_token_ids[0] == 29)
        if not herb_slots.size:
            continue
        simulation = type("HeavenHerbSimulation", (), {"batch": batch})()
        policy = CurriculumHeuristic(
            attacks={token: 1 for token in range(2, 25)},
            defenses={},
            heaven_herbs={29: 20},
        )

        action = curriculum_heuristic_actions(
            simulation,
            np.asarray([0], dtype=np.int64),
            policy,
        )[0]

        assert action == int(herb_slots[0]) + 1
        return
    raise AssertionError("fixture seeds did not expose Heaven Herb")


@pytest.mark.parametrize(("illness_token", "uses_herb"), [(23, False), (24, True)])
def test_heaven_herb_heuristic_avoids_worsening_mild_illness(
    illness_token: int,
    uses_herb: bool,
) -> None:
    for seed in range(32768):
        batch = illness_cure_resource_batch(seed=seed, heaven_herb=True)
        illness_slots = np.flatnonzero(batch.hand_token_ids[0] == illness_token)
        if not illness_slots.size:
            continue
        source = int(batch.active_players[0])
        batch.step(np.asarray([int(illness_slots[0]) + 1], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
        batch.step(np.asarray([godfield_sim.FORGIVE_ACTION_INDEX], dtype=np.int64))
        if batch.terminated[0]:
            continue
        actor = 1 - source
        expected_stage = (
            godfield_sim.ILLNESS_COLD if illness_token == 23 else godfield_sim.ILLNESS_HELL
        )
        if batch.illness_stages[0, actor] != expected_stage:
            continue
        herb_slots = np.flatnonzero(batch.hand_token_ids[0] == 29)
        if not herb_slots.size:
            continue
        simulation = type("HeavenHerbSimulation", (), {"batch": batch})()
        policy = CurriculumHeuristic(
            attacks={token: 1 for token in range(2, 25)},
            defenses={},
            heaven_herbs={29: 20},
        )

        action = curriculum_heuristic_actions(
            simulation,
            np.asarray([0], dtype=np.int64),
            policy,
        )[0]

        assert bool(action == int(herb_slots[0]) + 1) is uses_herb
        return
    raise AssertionError("fixture seeds did not expose illness with Heaven Herb")


def test_dynamic_mp_heuristic_ranks_attack_using_current_mp() -> None:
    policy = CurriculumHeuristic(
        attacks={2: 10, 19: 2},
        defenses={4: 8},
        dynamic_mp_attacks={19: 2},
    )
    for seed in range(8192):
        batch = dynamic_mp_weapon_resource_batch(seed=seed)
        if not np.any(batch.hand_token_ids[0] == 2) or not np.any(batch.hand_token_ids[0] == 19):
            continue
        simulation = type("DynamicMpSimulation", (), {"batch": batch})()
        action = curriculum_heuristic_actions(
            simulation,
            np.asarray([0], dtype=np.int64),
            policy,
        )[0]
        assert batch.hand_token_ids[0, action - 1] == 19
        return
    raise AssertionError("fixture seeds did not produce fixed and dynamic attacks together")


def test_same_damage_heuristic_avoids_nonlethal_self_ko_but_keeps_lethal_finish() -> None:
    hand = np.zeros((1, 9), dtype=np.int64)
    hand[0, :2] = [20, 2]
    legal = np.zeros((1, 21), dtype=np.bool_)
    legal[0, 1:3] = True
    player_features = np.zeros((1, 2, 4), dtype=np.float32)
    player_features[0, 0, 0] = 0.12
    player_features[0, 1, 0] = 0.40
    batch = type(
        "SameDamagePolicyBatch",
        (),
        {
            "hand_token_ids": hand,
            "action_mask": legal,
            "phases": np.asarray([godfield_sim.PHASE_ATTACK], dtype=np.uint8),
            "combo": True,
            "selected_counts": np.asarray([0], dtype=np.uint8),
            "resource_curriculum": True,
            "active_players": np.asarray([0], dtype=np.uint8),
            "magic_points": np.asarray([[10, 10]], dtype=np.uint16),
            "player_features": player_features,
        },
    )()
    simulation = type("SameDamagePolicySimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={20: 14, 2: 10},
        defenses={},
        same_damage_attack_tokens=frozenset({20}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert action == 2

    player_features[0, 1, 0] = 0.10
    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert action == 1


def test_random_target_heuristic_uses_expected_value_and_avoids_optional_self_ko() -> None:
    hand = np.zeros((1, 9), dtype=np.int64)
    hand[0, :2] = [22, 2]
    legal = np.zeros((1, 21), dtype=np.bool_)
    legal[0, 1:3] = True
    player_features = np.zeros((1, 2, 4), dtype=np.float32)
    player_features[0, 0, 0] = 0.20
    player_features[0, 1, 0] = 0.40
    batch = type(
        "RandomTargetPolicyBatch",
        (),
        {
            "hand_token_ids": hand,
            "action_mask": legal,
            "phases": np.asarray([godfield_sim.PHASE_ATTACK], dtype=np.uint8),
            "combo": True,
            "selected_counts": np.asarray([0], dtype=np.uint8),
            "resource_curriculum": True,
            "active_players": np.asarray([0], dtype=np.uint8),
            "magic_points": np.asarray([[10, 10]], dtype=np.uint16),
            "player_features": player_features,
        },
    )()
    simulation = type("RandomTargetPolicySimulation", (), {"batch": batch})()
    policy = CurriculumHeuristic(
        attacks={22: 30, 2: 16},
        defenses={},
        chance_attack_tokens=frozenset({22}),
        random_target_attack_tokens=frozenset({22}),
    )

    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert action == 2

    legal[0, 2] = False
    action = curriculum_heuristic_actions(
        simulation,
        np.asarray([0], dtype=np.int64),
        policy,
    )[0]
    assert action == 1


def test_combo_selection_aggregates_attack_and_defense_before_consuming() -> None:
    batch = combo_batch()
    base_action = (
        int(np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0]) + 1
    )
    batch.step(np.asarray([base_action], dtype=np.int64))

    assert batch.selected_counts[0] == 1
    assert batch.selected_values[0] == 10
    assert batch.selected_elements[0] == godfield_sim.ELEMENT_FIRE
    assert batch.selected_hand_mask[0, base_action - 1]
    assert batch.hand_token_ids[0, base_action - 1] == 0
    assert batch.global_features[0, 5] == pytest.approx(0.10)
    assert batch.global_features[0, 6 + godfield_sim.ELEMENT_FIRE] == 1.0
    assert batch.action_mask[0, godfield_sim.CONFIRM_ACTION_INDEX]

    booster_action = (
        int(np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ATTACK_BOOSTER)[0])
        + 1
    )
    batch.step(np.asarray([booster_action], dtype=np.int64))
    assert batch.selected_values[0] == 13
    assert batch.selected_elements[0] == godfield_sim.ELEMENT_FIRE
    np.testing.assert_array_equal(batch.hand_token_ids[0] == 0, batch.selected_hand_mask[0])

    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))
    assert batch.phases[0] == godfield_sim.PHASE_DEFENSE
    assert batch.pending_attacks[0] == 13
    assert batch.pending_elements[0] == godfield_sim.ELEMENT_FIRE
    assert batch.selected_counts[0] == 0
    assert batch.action_mask[0, godfield_sim.FORGIVE_ACTION_INDEX]

    armor_actions = np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ARMOR)[:2] + 1
    batch.step(np.asarray([armor_actions[0]], dtype=np.int64))
    assert not batch.action_mask[0, godfield_sim.FORGIVE_ACTION_INDEX]
    assert batch.action_mask[0, godfield_sim.CONFIRM_ACTION_INDEX]
    batch.step(np.asarray([armor_actions[1]], dtype=np.int64))
    assert batch.selected_values[0] == 16
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert batch.phases[0] == godfield_sim.PHASE_ATTACK
    assert batch.turn_numbers[0] == 1
    assert batch.global_features[0, 1] == pytest.approx(0.40)


def test_combo_mixed_non_light_elements_collapse_to_non_element() -> None:
    batch = combo_batch(booster_element=godfield_sim.ELEMENT_DARKNESS)
    base_action = (
        int(np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_WEAPON)[0]) + 1
    )
    batch.step(np.asarray([base_action], dtype=np.int64))
    booster_action = (
        int(np.flatnonzero(batch.hand_card_kinds[0] == godfield_sim.CARD_KIND_ATTACK_BOOSTER)[0])
        + 1
    )
    batch.step(np.asarray([booster_action], dtype=np.int64))
    batch.step(np.asarray([godfield_sim.CONFIRM_ACTION_INDEX], dtype=np.int64))

    assert batch.pending_elements[0] == godfield_sim.ELEMENT_NON_ELEMENT


@pytest.mark.parametrize(
    ("attack_element", "compatible_defenses"),
    [
        (godfield_sim.ELEMENT_NON_ELEMENT, set(range(7))),
        (
            godfield_sim.ELEMENT_FIRE,
            {godfield_sim.ELEMENT_WATER, godfield_sim.ELEMENT_LIGHT},
        ),
        (
            godfield_sim.ELEMENT_WATER,
            {godfield_sim.ELEMENT_FIRE, godfield_sim.ELEMENT_LIGHT},
        ),
        (
            godfield_sim.ELEMENT_WOOD,
            {godfield_sim.ELEMENT_STONE, godfield_sim.ELEMENT_LIGHT},
        ),
        (
            godfield_sim.ELEMENT_STONE,
            {godfield_sim.ELEMENT_WOOD, godfield_sim.ELEMENT_LIGHT},
        ),
        (godfield_sim.ELEMENT_LIGHT, set()),
        (godfield_sim.ELEMENT_DARKNESS, set(range(7))),
    ],
)
def test_elemental_defense_compatibility_masks(
    attack_element: int,
    compatible_defenses: set[int],
) -> None:
    for defense_element in range(7):
        batch = elemental_batch(
            attack_element=attack_element,
            defense_element=defense_element,
        )
        batch.step(batch.action_mask.argmax(axis=1).astype(np.int64))
        armor_legal = batch.action_mask[:, 1:10].any(axis=1)

        assert np.all(armor_legal == (defense_element in compatible_defenses))
        assert np.all(batch.action_mask[:, godfield_sim.FORGIVE_ACTION_INDEX])
        assert np.all(batch.pending_elements == attack_element)
        assert np.all(batch.global_features[:, 6 + attack_element] == 1.0)
        assert np.all(batch.global_features[:, 6:13].sum(axis=1) == 1.0)


def test_darkness_is_lethal_only_when_damage_penetrates_defense() -> None:
    penetrating = elemental_batch(
        attack=13,
        defense=4,
        attack_element=godfield_sim.ELEMENT_DARKNESS,
    )
    blocked = elemental_batch(
        attack=13,
        defense=20,
        attack_element=godfield_sim.ELEMENT_DARKNESS,
    )
    penetrating.step(penetrating.action_mask.argmax(axis=1).astype(np.int64))
    blocked.step(blocked.action_mask.argmax(axis=1).astype(np.int64))

    penetrating.step(penetrating.action_mask.argmax(axis=1).astype(np.int64))
    blocked.step(blocked.action_mask.argmax(axis=1).astype(np.int64))

    assert np.all(penetrating.terminated)
    assert not np.any(blocked.terminated)
    assert np.allclose(blocked.global_features[:, 1], 0.40)
    assert np.all(blocked.global_features[:, 6:13] == 0.0)


def test_elemental_catalog_rejects_unknown_element_ids() -> None:
    with pytest.raises(ValueError, match="unknown element ID"):
        elemental_batch(attack_element=7)


def test_mixed_hand_redraws_roles_and_preserves_attack_liveness() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        ruleset="mixed-hand",
    )
    batch = simulation.batch
    observed_non_initial_weapon_count = False

    for _ in range(40):
        attack_actions = batch.action_mask.argmax(axis=1).astype(np.int64)
        batch.step(attack_actions)
        visible_weapon_counts = np.count_nonzero(
            batch.hand_card_kinds == godfield_sim.CARD_KIND_WEAPON,
            axis=1,
        )
        observed_non_initial_weapon_count |= bool(np.any(visible_weapon_counts != 5))
        batch.step(
            np.full(
                batch.batch_size,
                godfield_sim.FORGIVE_ACTION_INDEX,
                dtype=np.int64,
            )
        )
        nonterminal = ~batch.terminated
        assert np.all(batch.action_mask[nonterminal, 1:10].any(axis=1))
        batch.reset_done()

    assert observed_non_initial_weapon_count


def test_defense_views_expose_phase_pending_attack_and_fixed_card_roles() -> None:
    batch = defense_batch()

    assert batch.phases.shape == (4,)
    assert batch.pending_attacks.shape == (4,)
    assert batch.hand_card_kinds.shape == (4, 9)
    assert not batch.phases.flags.writeable
    assert not batch.pending_attacks.flags.writeable
    assert np.all(batch.phases == godfield_sim.PHASE_ATTACK)
    assert np.all(batch.pending_attacks == 0)
    assert batch.global_features.shape == (4, 6)
    assert np.all(batch.global_features[:, 4:] == 0)
    assert np.all(batch.hand_card_kinds[:, :5] == godfield_sim.CARD_KIND_WEAPON)
    assert np.all(batch.hand_card_kinds[:, 5:] == godfield_sim.CARD_KIND_ARMOR)
    assert np.all(batch.action_mask[:, 1:6])
    assert not np.any(batch.action_mask[:, 0])
    assert not np.any(batch.action_mask[:, 6:])


def test_attack_then_armor_resolves_damage_and_hands_turn_to_defender() -> None:
    batch = defense_batch(attack=13, defense=4)
    attackers = batch.active_players.copy()

    batch.step(np.ones(batch.batch_size, dtype=np.int64))

    assert np.all(batch.phases == godfield_sim.PHASE_DEFENSE)
    assert np.all(batch.pending_attacks == 13)
    assert np.all(batch.global_features[:, 4] == 1)
    assert np.allclose(batch.global_features[:, 5], 0.13)
    assert np.all(batch.turn_numbers == 0)
    np.testing.assert_array_equal(batch.active_players, 1 - attackers)
    assert np.all(batch.action_mask[:, godfield_sim.FORGIVE_ACTION_INDEX])
    assert np.all(batch.action_mask[:, 6:10])
    assert not np.any(batch.action_mask[:, 1:6])

    batch.step(np.full(batch.batch_size, 6, dtype=np.int64))

    assert np.all(batch.phases == godfield_sim.PHASE_ATTACK)
    assert np.all(batch.pending_attacks == 0)
    assert np.all(batch.global_features[:, 4:] == 0)
    assert np.all(batch.turn_numbers == 1)
    assert np.allclose(batch.global_features[:, 1], 0.31)
    assert np.all(batch.action_mask[:, 1:6])


def test_defense_pass_and_full_block_have_expected_hp_effects() -> None:
    passing = defense_batch(attack=13, defense=4)
    blocking = defense_batch(attack=13, defense=20)
    attack_actions = np.ones(passing.batch_size, dtype=np.int64)
    passing.step(attack_actions)
    blocking.step(attack_actions.copy())

    passing.step(np.full(passing.batch_size, godfield_sim.FORGIVE_ACTION_INDEX, dtype=np.int64))
    blocking.step(np.full(blocking.batch_size, 6, dtype=np.int64))

    assert np.allclose(passing.global_features[:, 1], 0.27)
    assert np.allclose(blocking.global_features[:, 1], 0.40)


def test_lethal_attack_terminates_only_after_defense_resolution() -> None:
    batch = defense_batch(batch_size=16, attack=100, defense=1)
    attackers = batch.active_players.copy()

    batch.step(np.ones(batch.batch_size, dtype=np.int64))
    assert not np.any(batch.terminated)
    batch.step(np.full(batch.batch_size, godfield_sim.FORGIVE_ACTION_INDEX, dtype=np.int64))

    assert np.all(batch.terminated)
    assert np.all(batch.phases == godfield_sim.PHASE_TERMINAL)
    assert not np.any(batch.action_mask)
    for attacker, returns in zip(attackers, batch.terminal_returns, strict=True):
        assert returns[int(attacker)] == 1.0
        assert returns[1 - int(attacker)] == -1.0


def test_invalid_defense_action_rejects_batch_atomically() -> None:
    batch = defense_batch(batch_size=3)
    batch.step(np.ones(3, dtype=np.int64))
    before = batch.global_features.copy()
    actions = np.full(3, godfield_sim.FORGIVE_ACTION_INDEX, dtype=np.int64)
    actions[1] = 1

    with pytest.raises(ValueError, match="environment 1 selected a masked action"):
        batch.step(actions)

    np.testing.assert_array_equal(batch.global_features, before)
    assert np.all(batch.phases == godfield_sim.PHASE_DEFENSE)


def test_defense_catalogs_reject_cross_role_token_aliases() -> None:
    with pytest.raises(ValueError, match="weapon and armor catalog token IDs must be unique"):
        AttackDefenseBatch(
            1,
            np.asarray([2], dtype=np.uint32),
            np.asarray([3], dtype=np.uint16),
            np.asarray([2], dtype=np.uint32),
            np.asarray([4], dtype=np.uint16),
        )


def test_native_views_match_policy_shapes_and_are_read_only() -> None:
    batch = native_batch()

    assert batch.global_features.shape == (4, 6)
    assert batch.player_features.shape == (4, 2, 4)
    assert batch.player_mask.shape == (4, 2)
    assert batch.hand_token_ids.shape == (4, 9)
    assert batch.hand_mask.shape == (4, 9)
    assert batch.action_mask.shape == (4, 21)
    assert batch.terminal_returns.shape == (4, 2)
    assert batch.action_mask.dtype == np.bool_
    assert batch.global_features.dtype == np.float32
    assert not batch.global_features.flags.writeable
    assert not batch.action_mask.flags.writeable
    assert np.all(batch.action_mask[:, 1:10])
    assert not np.any(batch.action_mask[:, 0])
    assert not np.any(batch.action_mask[:, 10:])


def test_identical_seeds_produce_identical_batched_transitions() -> None:
    first = native_batch(batch_size=16)
    second = native_batch(batch_size=16)

    for _ in range(3):
        actions = first_legal_actions(first)
        first.step(actions)
        second.step(actions.copy())

    np.testing.assert_array_equal(first.active_players, second.active_players)
    np.testing.assert_array_equal(first.hand_token_ids, second.hand_token_ids)
    np.testing.assert_array_equal(first.global_features, second.global_features)
    np.testing.assert_array_equal(first.terminal_returns, second.terminal_returns)


def test_nonterminal_attacks_redraw_into_the_consumed_slot() -> None:
    batch = native_batch(batch_size=8, attack=1)

    batch.step(first_legal_actions(batch))
    batch.step(first_legal_actions(batch))

    assert not np.any(batch.terminated)
    assert np.all(batch.hand_mask)
    assert np.all(batch.hand_token_ids > 0)
    assert np.all(batch.action_mask[:, 1:10])


def test_curriculum_no_longer_ends_in_an_artificial_empty_hand_draw() -> None:
    batch = native_batch(batch_size=8, attack=1)

    for _ in range(18):
        batch.step(first_legal_actions(batch))

    assert not np.any(batch.terminated)
    assert np.all(batch.terminal_returns == 0)
    assert np.all(batch.action_mask[:, 1:10])


def test_terminal_step_emits_only_sparse_seat_returns() -> None:
    batch = native_batch(batch_size=32, attack=100)
    actors = batch.active_players.copy()

    batch.step(first_legal_actions(batch))

    assert np.all(batch.terminated)
    assert not np.any(batch.action_mask)
    for actor, returns in zip(actors, batch.terminal_returns, strict=True):
        assert returns[int(actor)] == 1.0
        assert returns[1 - int(actor)] == -1.0


def test_terminal_rows_must_be_consumed_before_reset() -> None:
    batch = native_batch(batch_size=3, attack=100)
    batch.step(first_legal_actions(batch))
    episode_ids = batch.episode_ids.copy()

    with pytest.raises(RuntimeError, match="call reset_done"):
        batch.step(np.ones(3, dtype=np.int64))

    assert batch.reset_done() == 3
    np.testing.assert_array_equal(batch.episode_ids, episode_ids + 1)
    assert not np.any(batch.terminated)
    assert np.all(batch.action_mask[:, 1:10])


def test_invalid_action_rejects_batch_without_partial_transition() -> None:
    batch = native_batch(batch_size=3)
    before = batch.global_features.copy()
    actions = first_legal_actions(batch)
    actions[1] = 20

    with pytest.raises(ValueError, match="environment 1 selected an action outside"):
        batch.step(actions)

    np.testing.assert_array_equal(batch.global_features, before)
    np.testing.assert_array_equal(batch.turn_numbers, np.zeros(3, dtype=np.uint16))


def test_native_catalog_rejects_duplicate_token_id_semantics() -> None:
    with pytest.raises(ValueError, match="catalog token IDs must be unique"):
        FixedAttackBatch(
            1,
            np.asarray([2, 2], dtype=np.uint32),
            np.asarray([3, 13], dtype=np.uint16),
        )


def test_view_keeps_native_owner_alive() -> None:
    batch = native_batch(batch_size=2)
    view = batch.global_features
    del batch
    gc.collect()

    assert view.shape == (2, 6)
    assert np.isfinite(view).all()


def test_pytorch_inference_views_share_native_buffers() -> None:
    torch = pytest.importorskip("torch")
    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.features import ArtifactVocabulary
    from godfield_bot.neural import RecurrentPolicyValueNet

    simulation = create_fixed_attack_simulation(SNAPSHOT_PATH, batch_size=8)
    global_array = simulation.batch.global_features

    tensors = simulation_feature_tensors(simulation)
    vocabulary = ArtifactVocabulary.from_snapshot(
        BibleSnapshot.model_validate_json(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    )
    model = RecurrentPolicyValueNet(
        vocabulary_size=len(vocabulary.tokens),
        action_count=21,
        global_feature_count=6,
    )
    logits, values, recurrent_state = model(*tensors)

    assert tensors[0].data_ptr() == global_array.__array_interface__["data"][0]
    assert tensors[0].dtype == torch.float32
    assert tensors[5].dtype == torch.bool
    assert tensors[5].shape == (8, 21)
    assert logits.shape == (8, 21)
    assert values.shape == (8,)
    assert recurrent_state.shape == (8, 128)


def test_defense_pytorch_views_include_live_compatible_response_features() -> None:
    simulation = create_attack_defense_simulation(SNAPSHOT_PATH, batch_size=8)
    tensors = simulation_feature_tensors(simulation)

    assert tensors[0].shape == (8, 6)
    assert tensors[0].data_ptr() == simulation.batch.global_features.__array_interface__["data"][0]
    assert not tensors[0][:, 4:].any()

    simulation.batch.step(np.ones(8, dtype=np.int64))

    assert tensors[0][:, 4].eq(1).all()
    np.testing.assert_allclose(
        tensors[0][:, 5].numpy(),
        simulation.batch.pending_attacks / 100.0,
    )


def test_benchmark_collects_full_batches() -> None:
    result = benchmark_fixed_attack_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        batch_steps=30,
    )

    assert result.transitions == 3840
    assert result.completed_episodes > 0
    assert result.transitions_per_second > 0


def test_defense_benchmark_collects_both_decision_phases() -> None:
    result = benchmark_attack_defense_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        batch_steps=30,
    )

    assert result.transitions == 3840
    assert result.completed_episodes > 0
    assert result.transitions_per_second > 0
