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
