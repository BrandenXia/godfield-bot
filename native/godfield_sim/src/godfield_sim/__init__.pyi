from typing import Final

import numpy as np
import numpy.typing as npt

KERNEL_SCHEMA_VERSION: Final[int]
OBSERVATION_SCHEMA_VERSION: Final[int]
RULESET_ID: Final[str]
CURSE_DYNAMICS_SCHEMA_VERSION: Final[int]
CURSE_DYNAMICS_RULESET_ID: Final[str]
CURSE_DECISION_SCHEMA_VERSION: Final[int]
CURSE_DECISION_RULESET_ID: Final[str]
DREAM_INVENTORY_SCHEMA_VERSION: Final[int]
DREAM_INVENTORY_RULESET_ID: Final[str]
CURSE_FOG_BIT: Final[int]
CURSE_DREAM_BIT: Final[int]
CURSE_FLASH_BIT: Final[int]
CURSE_DARK_CLOUD_BIT: Final[int]
ORDERED_INVENTORY_REPLAY_SCHEMA_VERSION: Final[int]
ORDERED_INVENTORY_REPLAY_RULESET_ID: Final[str]
GUARDIAN_LIFECYCLE_KERNEL_SCHEMA_VERSION: Final[int]
GUARDIAN_LIFECYCLE_OBSERVATION_SCHEMA_VERSION: Final[int]
GUARDIAN_LIFECYCLE_RULESET_ID: Final[str]
GUARDIAN_COMBAT_KERNEL_SCHEMA_VERSION: Final[int]
GUARDIAN_COMBAT_OBSERVATION_SCHEMA_VERSION: Final[int]
GUARDIAN_COMBAT_RULESET_ID: Final[str]
GUARDIAN_TURN_KERNEL_SCHEMA_VERSION: Final[int]
GUARDIAN_TURN_OBSERVATION_SCHEMA_VERSION: Final[int]
GUARDIAN_TURN_RULESET_ID: Final[str]
GUARDIAN_TURN_MAX_DEFENSE_ACTIONS: Final[int]
GUARDIAN_ACTOR_HAND_SCHEMA_VERSION: Final[int]
GUARDIAN_UTILITY_TURN_KERNEL_SCHEMA_VERSION: Final[int]
GUARDIAN_UTILITY_TURN_OBSERVATION_SCHEMA_VERSION: Final[int]
GUARDIAN_UTILITY_TURN_RULESET_ID: Final[str]
GUARDIAN_UTILITY_ACTOR_HAND_SCHEMA_VERSION: Final[int]
GUARDIAN_DISCARD_TURN_KERNEL_SCHEMA_VERSION: Final[int]
GUARDIAN_DISCARD_TURN_OBSERVATION_SCHEMA_VERSION: Final[int]
GUARDIAN_DISCARD_TURN_RULESET_ID: Final[str]
PROVISIONAL_GUARDIAN_SCHEMA_VERSION: Final[int]
PROVISIONAL_GUARDIAN_RULESET_ID: Final[str]
PROVISIONAL_SOAP_SCHEMA_VERSION: Final[int]
PROVISIONAL_SOAP_RULESET_ID: Final[str]
ACTION_COUNT: Final[int]
HAND_SLOTS: Final[int]
ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
ATTACK_DEFENSE_RULESET_ID: Final[str]
COMBO_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
COMBO_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
COMBO_ATTACK_DEFENSE_RULESET_ID: Final[str]
RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
STOCHASTIC_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
STOCHASTIC_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
STOCHASTIC_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT: Final[int]
EXPANDED_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
EXPANDED_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
EXPANDED_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
REFLECTION_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
REFLECTION_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
REFLECTION_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
DYNAMIC_MP_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
DYNAMIC_MP_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
DYNAMIC_MP_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
SAME_DAMAGE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
SAME_DAMAGE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
SAME_DAMAGE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
ATTACK_TWICE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
ATTACK_TWICE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
ATTACK_TWICE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
RANDOM_TARGET_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
RANDOM_TARGET_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
RANDOM_TARGET_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
ILLNESS_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
ILLNESS_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
ILLNESS_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
ILLNESS_CURE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
ILLNESS_CURE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
ILLNESS_CURE_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
HEAVEN_HERB_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
HEAVEN_HERB_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
HEAVEN_HERB_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
FEVER_MASK_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
FEVER_MASK_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
FEVER_MASK_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
MIRACLE_BLOCK_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIRACLE_BLOCK_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIRACLE_BLOCK_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
MIRACLE_BLOCK_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIRACLE_BLOCK_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIRACLE_BLOCK_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
MIRACLE_BOUNCE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIRACLE_BOUNCE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIRACLE_BOUNCE_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
MIRACLE_BOUNCE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIRACLE_BOUNCE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIRACLE_BOUNCE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
MIRACLE_BOUNCE_MIRACLE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIRACLE_BOUNCE_MIRACLE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIRACLE_BOUNCE_MIRACLE_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
MIRACLE_REFLECTION_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIRACLE_REFLECTION_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIRACLE_REFLECTION_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
FOG_FLASH_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
FOG_FLASH_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
FOG_FLASH_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
DARK_CLOUD_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
DARK_CLOUD_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
DARK_CLOUD_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
DREAM_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
DREAM_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
DREAM_RESOURCE_ATTACK_DEFENSE_RULESET_ID: Final[str]
ILLNESS_GLOBAL_FEATURE_COUNT: Final[int]
CURSE_GLOBAL_FEATURE_COUNT: Final[int]
DARK_CLOUD_GLOBAL_FEATURE_COUNT: Final[int]
DREAM_GLOBAL_FEATURE_COUNT: Final[int]
MIXED_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
MIXED_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
MIXED_ATTACK_DEFENSE_RULESET_ID: Final[str]
ELEMENTAL_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION: Final[int]
ELEMENTAL_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION: Final[int]
ELEMENTAL_ATTACK_DEFENSE_RULESET_ID: Final[str]
ELEMENTAL_GLOBAL_FEATURE_COUNT: Final[int]
ELEMENT_COUNT: Final[int]
ELEMENT_NON_ELEMENT: Final[int]
ELEMENT_FIRE: Final[int]
ELEMENT_WATER: Final[int]
ELEMENT_WOOD: Final[int]
ELEMENT_STONE: Final[int]
ELEMENT_LIGHT: Final[int]
ELEMENT_DARKNESS: Final[int]
WEAPON_SLOTS: Final[int]
ARMOR_SLOTS: Final[int]
PHASE_ATTACK: Final[int]
PHASE_DEFENSE: Final[int]
PHASE_TERMINAL: Final[int]
CARD_KIND_WEAPON: Final[int]
CARD_KIND_ARMOR: Final[int]
CARD_KIND_ATTACK_BOOSTER: Final[int]
CARD_KIND_HP_UTILITY: Final[int]
CARD_KIND_MP_UTILITY: Final[int]
CARD_KIND_ATTACK_MIRACLE: Final[int]
CARD_KIND_HP_MIRACLE: Final[int]
CARD_KIND_CHANCE_ATTACK_MIRACLE: Final[int]
CARD_KIND_EFFECT_ATTACK_MIRACLE: Final[int]
CARD_KIND_ADDITIVE_MIRACLE: Final[int]
CARD_KIND_REFLECTION_ARMOR: Final[int]
CARD_KIND_REFLECTION_WEAPON: Final[int]
CARD_KIND_DUAL_ROLE: Final[int]
CARD_KIND_CHANCE_WEAPON: Final[int]
CARD_KIND_CHANCE_DUAL_ROLE: Final[int]
CARD_KIND_ABSORPTION_WEAPON: Final[int]
CARD_KIND_ATTACK_TWICE_WEAPON: Final[int]
CARD_KIND_RANDOM_TARGET_WEAPON: Final[int]
CARD_KIND_ILLNESS_WEAPON: Final[int]
CARD_KIND_ILLNESS_CURE_SUNDRY: Final[int]
CARD_KIND_ILLNESS_CURE_MIRACLE: Final[int]
CARD_KIND_HEAVEN_HERB: Final[int]
CARD_KIND_FEVER_MASK: Final[int]
CARD_KIND_MIRACLE_BLOCK_ARMOR: Final[int]
CARD_KIND_MIRACLE_BLOCK_WEAPON: Final[int]
CARD_KIND_MIRACLE_BLOCK_BOOSTER: Final[int]
CARD_KIND_MIRACLE_BOUNCE_ARMOR: Final[int]
CARD_KIND_MIRACLE_BOUNCE_BOOSTER: Final[int]
CARD_KIND_MIRACLE_BOUNCE_MIRACLE: Final[int]
CARD_KIND_MIRACLE_REFLECTION_ARMOR: Final[int]
CARD_KIND_MIRACLE_REFLECTION_WEAPON: Final[int]
CARD_KIND_FOG_FLASH_WEAPON: Final[int]
CARD_KIND_FOG_FLASH_ATTACK_MIRACLE: Final[int]
CARD_KIND_FOG_MIRACLE: Final[int]
CARD_KIND_DARK_CLOUD_WEAPON: Final[int]
CARD_KIND_DARK_CLOUD_MIRACLE: Final[int]
CARD_KIND_DREAM_WEAPON: Final[int]
CARD_KIND_DREAM_MIRACLE: Final[int]
ILLNESS_NONE: Final[int]
ILLNESS_COLD: Final[int]
ILLNESS_FEVER: Final[int]
ILLNESS_HELL: Final[int]
ILLNESS_HEAVEN: Final[int]
CARD_KIND_CHANCE_ABSORPTION_WEAPON: Final[int]
CARD_KIND_DYNAMIC_MP_WEAPON: Final[int]
CARD_KIND_SAME_DAMAGE_WEAPON: Final[int]
FORGIVE_ACTION_INDEX: Final[int]
CONFIRM_ACTION_INDEX: Final[int]
GLOBAL_FEATURE_COUNT: Final[int]

class CurseDynamicsBatch:
    def __init__(
        self, batch_size: int, player_count: int, initial_hp: int = ...
    ) -> None: ...
    def load_players(
        self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
        hp: npt.NDArray[np.int64], illness: npt.NDArray[np.int64],
        curse_masks: npt.NDArray[np.int64],
    ) -> None: ...
    def apply_illnesses(
        self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
        stages: npt.NDArray[np.int64],
    ) -> None: ...
    def apply_curses(
        self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
        curse_bits: npt.NDArray[np.int64],
    ) -> None: ...
    def cure_players(
        self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
        scopes: npt.NDArray[np.int64],
    ) -> None: ...
    def finish_turns(
        self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
        expected_ticks: npt.NDArray[np.int64], progression_tickets: npt.NDArray[np.int64],
    ) -> None: ...
    def reset_environments(self, environments: npt.NDArray[np.int64]) -> None: ...
    def snapshot(self) -> npt.NDArray[np.int64]: ...
    def transition_snapshot(self) -> npt.NDArray[np.int64]: ...
    def status_observations(
        self, environments: npt.NDArray[np.int64], actors: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]: ...
    def defense_card_limits(
        self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
        ordinary_limits: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]: ...
    def hit_decisions(
        self, environments: npt.NDArray[np.int64], targets: npt.NDArray[np.int64],
        hit_rates: npt.NDArray[np.int64], hit_tickets: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]: ...
    def enemy_targets(
        self, environments: npt.NDArray[np.int64], actors: npt.NDArray[np.int64],
        intended_targets: npt.NDArray[np.int64], eligible_enemies: npt.NDArray[np.int64],
        selection_tickets: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]: ...
    @property
    def illness_count(self) -> int: ...
    @property
    def curse_count(self) -> int: ...
    @property
    def cure_count(self) -> int: ...
    @property
    def tick_count(self) -> int: ...
    @property
    def death_count(self) -> int: ...

class DreamInventoryBatch:
    def __init__(
        self, batch_size: int, player_count: int, profiles: npt.NDArray[np.int64],
        capacity: int = ...,
    ) -> None: ...
    def seed_hand(self, environment: int, owner: int, items: npt.NDArray[np.int64]) -> None: ...
    def add_cards(
        self, environments: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
        instance_ids: npt.NDArray[np.int64], model_ids: npt.NDArray[np.int64],
        curse_masks: npt.NDArray[np.int64], disguise_tickets: npt.NDArray[np.int64],
        fake_tickets: npt.NDArray[np.int64],
    ) -> None: ...
    def use_cards(
        self, environments: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
        expected_items: npt.NDArray[np.int64],
    ) -> None: ...
    def remove_cards(
        self, environments: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
        expected_items: npt.NDArray[np.int64],
    ) -> None: ...
    def restore_displays(
        self, environments: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
    ) -> None: ...
    def reset_environments(self, environments: npt.NDArray[np.int64]) -> None: ...
    def snapshot(self) -> npt.NDArray[np.int64]: ...
    def actor_hands(
        self, environments: npt.NDArray[np.int64], actors: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]: ...
    @property
    def capacity(self) -> int: ...
    @property
    def gift_count(self) -> int: ...
    @property
    def consumed_count(self) -> int: ...
    @property
    def miracle_use_count(self) -> int: ...
    @property
    def removal_count(self) -> int: ...
    @property
    def restored_count(self) -> int: ...

class OrderedInventoryReplay:
    def __init__(
        self,
        initial_items: npt.NDArray[np.int64],
        ordinary_consumable_model_ids: npt.NDArray[np.int64],
        capacity: int = ...,
    ) -> None: ...
    def consume(self, expected_items: npt.NDArray[np.int64]) -> None: ...
    def gift(self, item: npt.NDArray[np.int64]) -> None: ...
    def configure_retained_miracles(self, model_ids: npt.NDArray[np.int64]) -> None: ...
    def perform_retained_miracle(self, expected_item: npt.NDArray[np.int64]) -> None: ...
    def configure_observed_removal_models(self, model_ids: npt.NDArray[np.int64]) -> None: ...
    def remove_observed_three(self, expected_items: npt.NDArray[np.int64]) -> None: ...
    def snapshot(self) -> npt.NDArray[np.int64]: ...
    @property
    def size(self) -> int: ...
    @property
    def capacity(self) -> int: ...
    @property
    def consumed_item_count(self) -> int: ...
    @property
    def gift_item_count(self) -> int: ...
    @property
    def retained_miracles_configured(self) -> bool: ...
    @property
    def retained_miracle_use_count(self) -> int: ...
    @property
    def observed_removals_configured(self) -> bool: ...
    @property
    def observed_removal_count(self) -> int: ...

class GuardianTurnBatch:
    def __init__(
        self, batch_size: int, player_count: int, guardian_slots: int,
        weighted_profiles: npt.NDArray[np.int64],
        effect_profiles: npt.NDArray[np.int64],
        defense_profiles: npt.NDArray[np.int64], hand_slots: int = 18,
        max_turns: int = 1000, initial_hp: int = 40,
        initial_mp: int = 10, initial_cp: int = 0,
        attack_profiles: npt.NDArray[np.int64] | None = None,
    ) -> None: ...
    def summon(self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
               instances: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
               groups: npt.NDArray[np.int64]) -> None: ...
    def remove(self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
               instances: npt.NDArray[np.int64]) -> None: ...
    def deal_defenses(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                      slots: npt.NDArray[np.int64], instances: npt.NDArray[np.int64],
                      models: npt.NDArray[np.int64]) -> None: ...
    def deal_cards(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                   slots: npt.NDArray[np.int64], instances: npt.NDArray[np.int64],
                   models: npt.NDArray[np.int64]) -> None: ...
    def begin_card_attacks(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                           slots: npt.NDArray[np.int64], targets: npt.NDArray[np.int64]) -> None: ...
    def begin_effects(self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
                      instances: npt.NDArray[np.int64], targets: npt.NDArray[np.int64],
                      selection_tickets: npt.NDArray[np.int64], hit_tickets: npt.NDArray[np.int64]) -> None: ...
    def pass_turns(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64]) -> None: ...
    def step_defenses(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                      actions: npt.NDArray[np.int64]) -> None: ...
    def reset_environments(self, environments: npt.NDArray[np.int64]) -> None: ...
    def resolve_bounces(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                        targets: npt.NDArray[np.int64]) -> None: ...
    def defense_action_masks(self) -> npt.NDArray[np.bool_]: ...
    def attack_action_masks(self) -> npt.NDArray[np.bool_]: ...
    def attack_target_masks(self) -> npt.NDArray[np.bool_]: ...
    def bounce_target_masks(self) -> npt.NDArray[np.bool_]: ...
    def turn_snapshot(self) -> npt.NDArray[np.int64]: ...
    def inventory_snapshot(self) -> npt.NDArray[np.int64]: ...
    def hand_feature_snapshot(self) -> npt.NDArray[np.int64]: ...
    def actor_hand_snapshot(self) -> npt.NDArray[np.int64]: ...
    def guardian_snapshot(self) -> npt.NDArray[np.int64]: ...
    def resource_snapshot(self) -> npt.NDArray[np.int64]: ...
    def combat_snapshot(self) -> npt.NDArray[np.int64]: ...
    @property
    def hand_slots(self) -> int: ...
    @property
    def action_count(self) -> int: ...
    @property
    def consumed_card_count(self) -> int: ...
    @property
    def resolved_effect_count(self) -> int: ...
    @property
    def miracle_cast_count(self) -> int: ...
    @property
    def mp_spent(self) -> int: ...

class GuardianUtilityTurnBatch:
    def __init__(
        self, batch_size: int, player_count: int, guardian_slots: int,
        weighted_profiles: npt.NDArray[np.int64], effect_profiles: npt.NDArray[np.int64],
        defense_profiles: npt.NDArray[np.int64], attack_profiles: npt.NDArray[np.int64],
        utility_profiles: npt.NDArray[np.int64], hand_slots: int = 18,
        max_turns: int = 1000, initial_hp: int = 40, initial_mp: int = 10,
        initial_cp: int = 0,
    ) -> None: ...
    def summon(self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
               instances: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
               groups: npt.NDArray[np.int64]) -> None: ...
    def remove(self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
               instances: npt.NDArray[np.int64]) -> None: ...
    def deal_defenses(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                      slots: npt.NDArray[np.int64], instances: npt.NDArray[np.int64],
                      models: npt.NDArray[np.int64]) -> None: ...
    def deal_cards(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                   slots: npt.NDArray[np.int64], instances: npt.NDArray[np.int64],
                   models: npt.NDArray[np.int64]) -> None: ...
    def use_utility_cards(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                          slots: npt.NDArray[np.int64]) -> None: ...
    def begin_card_attacks(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                           slots: npt.NDArray[np.int64], targets: npt.NDArray[np.int64]) -> None: ...
    def begin_effects(self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
                      instances: npt.NDArray[np.int64], targets: npt.NDArray[np.int64],
                      selection_tickets: npt.NDArray[np.int64], hit_tickets: npt.NDArray[np.int64]) -> None: ...
    def pass_turns(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64]) -> None: ...
    def step_defenses(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                      actions: npt.NDArray[np.int64]) -> None: ...
    def reset_environments(self, environments: npt.NDArray[np.int64]) -> None: ...
    def resolve_bounces(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                        targets: npt.NDArray[np.int64]) -> None: ...
    def utility_action_masks(self) -> npt.NDArray[np.bool_]: ...
    def ready_action_masks(self) -> npt.NDArray[np.bool_]: ...
    def defense_action_masks(self) -> npt.NDArray[np.bool_]: ...
    def attack_action_masks(self) -> npt.NDArray[np.bool_]: ...
    def attack_target_masks(self) -> npt.NDArray[np.bool_]: ...
    def bounce_target_masks(self) -> npt.NDArray[np.bool_]: ...
    def turn_snapshot(self) -> npt.NDArray[np.int64]: ...
    def inventory_snapshot(self) -> npt.NDArray[np.int64]: ...
    def hand_feature_snapshot(self) -> npt.NDArray[np.int64]: ...
    def actor_hand_snapshot(self) -> npt.NDArray[np.int64]: ...
    def guardian_snapshot(self) -> npt.NDArray[np.int64]: ...
    def resource_snapshot(self) -> npt.NDArray[np.int64]: ...
    def combat_snapshot(self) -> npt.NDArray[np.int64]: ...
    @property
    def hand_slots(self) -> int: ...
    @property
    def action_count(self) -> int: ...
    @property
    def consumed_card_count(self) -> int: ...
    @property
    def resolved_effect_count(self) -> int: ...
    @property
    def miracle_cast_count(self) -> int: ...
    @property
    def mp_spent(self) -> int: ...
    @property
    def utility_use_count(self) -> int: ...
    @property
    def hp_gained(self) -> int: ...
    @property
    def mp_gained(self) -> int: ...

class GuardianDiscardTurnBatch(GuardianUtilityTurnBatch):
    def __init__(
        self, batch_size: int, player_count: int, guardian_slots: int,
        weighted_profiles: npt.NDArray[np.int64], effect_profiles: npt.NDArray[np.int64],
        defense_profiles: npt.NDArray[np.int64], attack_profiles: npt.NDArray[np.int64],
        utility_profiles: npt.NDArray[np.int64], discard_models: npt.NDArray[np.int64],
        hand_slots: int = 18, max_turns: int = 1000, initial_hp: int = 40,
        initial_mp: int = 10, initial_cp: int = 0,
    ) -> None: ...
    def discard_cards(self, environments: npt.NDArray[np.int64], players: npt.NDArray[np.int64],
                      slots: npt.NDArray[np.int64]) -> None: ...
    def discard_action_masks(self) -> npt.NDArray[np.bool_]: ...
    @property
    def discarded_card_count(self) -> int: ...

class GuardianCombatBatch:
    def __init__(
        self, batch_size: int, player_count: int, slots_per_environment: int,
        weighted_profiles: npt.NDArray[np.int64],
        basic_attack_profiles: npt.NDArray[np.int64], initial_hp: int = ...,
        initial_mp: int = ..., initial_cp: int = ...,
    ) -> None: ...
    def summon(
        self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
        instances: npt.NDArray[np.int64], owners: npt.NDArray[np.int64],
        groups: npt.NDArray[np.int64],
    ) -> None: ...
    def remove(
        self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
        instances: npt.NDArray[np.int64],
    ) -> None: ...
    def reset_environments(self, environments: npt.NDArray[np.int64]) -> None: ...
    def begin_attacks(
        self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
        instances: npt.NDArray[np.int64], targets: npt.NDArray[np.int64],
        selection_tickets: npt.NDArray[np.int64], hit_tickets: npt.NDArray[np.int64],
    ) -> None: ...
    def resolve_defenses(
        self, environments: npt.NDArray[np.int64], defense_values: npt.NDArray[np.int64],
        defense_elements: npt.NDArray[np.int64],
    ) -> None: ...
    def begin_effects(
        self, environments: npt.NDArray[np.int64], slots: npt.NDArray[np.int64],
        instances: npt.NDArray[np.int64], targets: npt.NDArray[np.int64],
        selection_tickets: npt.NDArray[np.int64], hit_tickets: npt.NDArray[np.int64],
    ) -> None: ...
    def guardian_snapshot(self) -> npt.NDArray[np.int64]: ...
    def hp_snapshot(self) -> npt.NDArray[np.int64]: ...
    def combat_snapshot(self) -> npt.NDArray[np.int64]: ...
    def resource_snapshot(self) -> npt.NDArray[np.int64]: ...
    @property
    def resolved_attack_count(self) -> int: ...
    @property
    def resolved_effect_count(self) -> int: ...

class GuardianLifecycleBatch:
    def __init__(
        self,
        batch_size: int,
        player_count: int,
        slots_per_environment: int,
        profiles: npt.NDArray[np.int64],
    ) -> None: ...
    def summon(
        self,
        environments: npt.NDArray[np.int64],
        slots: npt.NDArray[np.int64],
        instance_ids: npt.NDArray[np.int64],
        owners: npt.NDArray[np.int64],
        groups: npt.NDArray[np.int64],
    ) -> None: ...
    def remove(
        self,
        environments: npt.NDArray[np.int64],
        slots: npt.NDArray[np.int64],
        expected_instance_ids: npt.NDArray[np.int64],
    ) -> None: ...
    def reset_environments(self, environments: npt.NDArray[np.int64]) -> None: ...
    def attack_models(
        self,
        environments: npt.NDArray[np.int64],
        slots: npt.NDArray[np.int64],
        expected_instance_ids: npt.NDArray[np.int64],
        tickets: npt.NDArray[np.int64],
    ) -> npt.NDArray[np.int64]: ...
    def snapshot(self) -> npt.NDArray[np.int64]: ...
    @property
    def batch_size(self) -> int: ...
    @property
    def player_count(self) -> int: ...
    @property
    def slots_per_environment(self) -> int: ...
    @property
    def active_count(self) -> int: ...
    @property
    def summon_count(self) -> int: ...
    @property
    def removal_count(self) -> int: ...
    @property
    def reset_count(self) -> int: ...

class ProvisionalGuardianPicker:
    def __init__(self, profiles: npt.NDArray[np.int64]) -> None: ...
    def model_for_ticket(self, group: int, ticket: int) -> int: ...
    def total_weight(self, group: int) -> int: ...
    @property
    def profile_count(self) -> int: ...
    @property
    def group_count(self) -> int: ...

class ProvisionalSoapProjection:
    def __init__(
        self,
        initial_items: npt.NDArray[np.int64],
        miracle_model_ids: npt.NDArray[np.int64],
        capacity: int = ...,
    ) -> None: ...
    def wash_selected_two(self, expected_items: npt.NDArray[np.int64]) -> None: ...
    def snapshot(self) -> npt.NDArray[np.int64]: ...
    @property
    def size(self) -> int: ...
    @property
    def removed_item_count(self) -> int: ...

class FixedAttackBatch:
    def __init__(
        self,
        batch_size: int,
        token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
    ) -> None: ...
    @property
    def batch_size(self) -> int: ...
    @property
    def seed(self) -> int: ...
    @property
    def initial_hp(self) -> int: ...
    @property
    def global_features(self) -> npt.NDArray[np.float32]: ...
    @property
    def player_features(self) -> npt.NDArray[np.float32]: ...
    @property
    def player_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def hand_token_ids(self) -> npt.NDArray[np.int64]: ...
    @property
    def hand_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def action_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def active_players(self) -> npt.NDArray[np.uint8]: ...
    @property
    def terminal_returns(self) -> npt.NDArray[np.float32]: ...
    @property
    def terminated(self) -> npt.NDArray[np.bool_]: ...
    @property
    def episode_ids(self) -> npt.NDArray[np.uint64]: ...
    @property
    def turn_numbers(self) -> npt.NDArray[np.uint16]: ...
    def reset(self) -> None: ...
    def reset_done(self) -> int: ...
    def step(self, actions: npt.NDArray[np.int64]) -> None: ...

class AttackDefenseBatch:
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        mixed_hands: bool = ...,
    ) -> None: ...
    @property
    def batch_size(self) -> int: ...
    @property
    def seed(self) -> int: ...
    @property
    def initial_hp(self) -> int: ...
    @property
    def mixed_hands(self) -> bool: ...
    @property
    def elemental(self) -> bool: ...
    @property
    def combo(self) -> bool: ...
    @property
    def resource_curriculum(self) -> bool: ...
    @property
    def stochastic_resource_curriculum(self) -> bool: ...
    @property
    def additive_miracle_curriculum(self) -> bool: ...
    @property
    def reflection_curriculum(self) -> bool: ...
    @property
    def reflection_weapon_curriculum(self) -> bool: ...
    @property
    def dual_role_curriculum(self) -> bool: ...
    @property
    def chance_weapon_curriculum(self) -> bool: ...
    @property
    def absorption_weapon_curriculum(self) -> bool: ...
    @property
    def dynamic_mp_weapon_curriculum(self) -> bool: ...
    @property
    def same_damage_weapon_curriculum(self) -> bool: ...
    @property
    def attack_twice_weapon_curriculum(self) -> bool: ...
    @property
    def random_target_weapon_curriculum(self) -> bool: ...
    @property
    def illness_weapon_curriculum(self) -> bool: ...
    @property
    def illness_cure_curriculum(self) -> bool: ...
    @property
    def heaven_herb_curriculum(self) -> bool: ...
    @property
    def fever_mask_curriculum(self) -> bool: ...
    @property
    def miracle_block_curriculum(self) -> bool: ...
    @property
    def miracle_block_weapon_curriculum(self) -> bool: ...
    @property
    def miracle_bounce_curriculum(self) -> bool: ...
    @property
    def miracle_bounce_weapon_curriculum(self) -> bool: ...
    @property
    def miracle_bounce_miracle_curriculum(self) -> bool: ...
    @property
    def miracle_reflection_curriculum(self) -> bool: ...
    @property
    def fog_flash_curriculum(self) -> bool: ...
    @property
    def dark_cloud_curriculum(self) -> bool: ...
    @property
    def dream_curriculum(self) -> bool: ...
    @property
    def gift_weighted(self) -> bool: ...
    def configure_hand_capacity(
        self, minimum_initial_hand: int = 9, maximum_initial_hand: int = 18
    ) -> None: ...
    @property
    def hand_slots(self) -> int: ...
    @property
    def action_count(self) -> int: ...
    @property
    def forgive_action_index(self) -> int: ...
    @property
    def confirm_action_index(self) -> int: ...
    @property
    def hand_sizes(self) -> npt.NDArray[np.uint8]: ...
    def configure_gift_weights(
        self, token_ids: npt.NDArray[np.uint32], weights: npt.NDArray[np.uint16]
    ) -> None: ...
    @property
    def initial_mp(self) -> int: ...
    @property
    def global_feature_count(self) -> int: ...
    @property
    def global_features(self) -> npt.NDArray[np.float32]: ...
    @property
    def player_features(self) -> npt.NDArray[np.float32]: ...
    @property
    def player_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def hand_token_ids(self) -> npt.NDArray[np.int64]: ...
    @property
    def actual_hand_token_ids(self) -> npt.NDArray[np.int64]: ...
    @property
    def hand_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def hand_card_kinds(self) -> npt.NDArray[np.uint8]: ...
    @property
    def hand_elements(self) -> npt.NDArray[np.uint8]: ...
    @property
    def illness_stages(self) -> npt.NDArray[np.uint8]: ...
    @property
    def fog_flags(self) -> npt.NDArray[np.uint8]: ...
    @property
    def flash_flags(self) -> npt.NDArray[np.uint8]: ...
    @property
    def dark_cloud_flags(self) -> npt.NDArray[np.uint8]: ...
    @property
    def dream_flags(self) -> npt.NDArray[np.uint8]: ...
    @property
    def action_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def active_players(self) -> npt.NDArray[np.uint8]: ...
    @property
    def phases(self) -> npt.NDArray[np.uint8]: ...
    @property
    def pending_attacks(self) -> npt.NDArray[np.uint16]: ...
    @property
    def pending_elements(self) -> npt.NDArray[np.uint8]: ...
    @property
    def pending_base_kinds(self) -> npt.NDArray[np.uint8]: ...
    @property
    def pending_strikes_remaining(self) -> npt.NDArray[np.uint8]: ...
    @property
    def pending_reflected(self) -> npt.NDArray[np.bool_]: ...
    @property
    def pending_bounced(self) -> npt.NDArray[np.bool_]: ...
    @property
    def selected_hand_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def selected_counts(self) -> npt.NDArray[np.uint8]: ...
    @property
    def selected_values(self) -> npt.NDArray[np.uint16]: ...
    @property
    def selected_elements(self) -> npt.NDArray[np.uint8]: ...
    @property
    def terminal_returns(self) -> npt.NDArray[np.float32]: ...
    @property
    def terminated(self) -> npt.NDArray[np.bool_]: ...
    @property
    def episode_ids(self) -> npt.NDArray[np.uint64]: ...
    @property
    def turn_numbers(self) -> npt.NDArray[np.uint16]: ...
    @property
    def magic_points(self) -> npt.NDArray[np.uint16]: ...
    def reset(self) -> None: ...
    def reset_done(self) -> int: ...
    def step(self, actions: npt.NDArray[np.int64]) -> None: ...

class ElementalAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
    ) -> None: ...

class ComboAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
    ) -> None: ...

class ResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class StochasticResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class ExpandedResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class ReflectionResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class ReflectionWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class DualRoleResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class ChanceWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        chance_weapon_token_ids: npt.NDArray[np.uint32],
        chance_weapon_attack_values: npt.NDArray[np.uint16],
        chance_weapon_elements: npt.NDArray[np.uint8],
        chance_weapon_hit_rates: npt.NDArray[np.uint16],
        chance_dual_role_token_ids: npt.NDArray[np.uint32],
        chance_dual_role_attack_values: npt.NDArray[np.uint16],
        chance_dual_role_defense_values: npt.NDArray[np.uint16],
        chance_dual_role_elements: npt.NDArray[np.uint8],
        chance_dual_role_hit_rates: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class AbsorptionWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        chance_weapon_token_ids: npt.NDArray[np.uint32],
        chance_weapon_attack_values: npt.NDArray[np.uint16],
        chance_weapon_elements: npt.NDArray[np.uint8],
        chance_weapon_hit_rates: npt.NDArray[np.uint16],
        chance_dual_role_token_ids: npt.NDArray[np.uint32],
        chance_dual_role_attack_values: npt.NDArray[np.uint16],
        chance_dual_role_defense_values: npt.NDArray[np.uint16],
        chance_dual_role_elements: npt.NDArray[np.uint8],
        chance_dual_role_hit_rates: npt.NDArray[np.uint16],
        absorption_weapon_token_ids: npt.NDArray[np.uint32],
        absorption_weapon_attack_values: npt.NDArray[np.uint16],
        absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_token_ids: npt.NDArray[np.uint32],
        chance_absorption_weapon_attack_values: npt.NDArray[np.uint16],
        chance_absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_hit_rates: npt.NDArray[np.uint16],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class DynamicMpWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        chance_weapon_token_ids: npt.NDArray[np.uint32],
        chance_weapon_attack_values: npt.NDArray[np.uint16],
        chance_weapon_elements: npt.NDArray[np.uint8],
        chance_weapon_hit_rates: npt.NDArray[np.uint16],
        chance_dual_role_token_ids: npt.NDArray[np.uint32],
        chance_dual_role_attack_values: npt.NDArray[np.uint16],
        chance_dual_role_defense_values: npt.NDArray[np.uint16],
        chance_dual_role_elements: npt.NDArray[np.uint8],
        chance_dual_role_hit_rates: npt.NDArray[np.uint16],
        absorption_weapon_token_ids: npt.NDArray[np.uint32],
        absorption_weapon_attack_values: npt.NDArray[np.uint16],
        absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_token_ids: npt.NDArray[np.uint32],
        chance_absorption_weapon_attack_values: npt.NDArray[np.uint16],
        chance_absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_hit_rates: npt.NDArray[np.uint16],
        dynamic_mp_weapon_token_ids: npt.NDArray[np.uint32],
        dynamic_mp_weapon_coefficients: npt.NDArray[np.uint16],
        dynamic_mp_weapon_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class SameDamageWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        chance_weapon_token_ids: npt.NDArray[np.uint32],
        chance_weapon_attack_values: npt.NDArray[np.uint16],
        chance_weapon_elements: npt.NDArray[np.uint8],
        chance_weapon_hit_rates: npt.NDArray[np.uint16],
        chance_dual_role_token_ids: npt.NDArray[np.uint32],
        chance_dual_role_attack_values: npt.NDArray[np.uint16],
        chance_dual_role_defense_values: npt.NDArray[np.uint16],
        chance_dual_role_elements: npt.NDArray[np.uint8],
        chance_dual_role_hit_rates: npt.NDArray[np.uint16],
        absorption_weapon_token_ids: npt.NDArray[np.uint32],
        absorption_weapon_attack_values: npt.NDArray[np.uint16],
        absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_token_ids: npt.NDArray[np.uint32],
        chance_absorption_weapon_attack_values: npt.NDArray[np.uint16],
        chance_absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_hit_rates: npt.NDArray[np.uint16],
        dynamic_mp_weapon_token_ids: npt.NDArray[np.uint32],
        dynamic_mp_weapon_coefficients: npt.NDArray[np.uint16],
        dynamic_mp_weapon_elements: npt.NDArray[np.uint8],
        same_damage_weapon_token_ids: npt.NDArray[np.uint32],
        same_damage_weapon_attack_values: npt.NDArray[np.uint16],
        same_damage_weapon_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class AttackTwiceWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        chance_weapon_token_ids: npt.NDArray[np.uint32],
        chance_weapon_attack_values: npt.NDArray[np.uint16],
        chance_weapon_elements: npt.NDArray[np.uint8],
        chance_weapon_hit_rates: npt.NDArray[np.uint16],
        chance_dual_role_token_ids: npt.NDArray[np.uint32],
        chance_dual_role_attack_values: npt.NDArray[np.uint16],
        chance_dual_role_defense_values: npt.NDArray[np.uint16],
        chance_dual_role_elements: npt.NDArray[np.uint8],
        chance_dual_role_hit_rates: npt.NDArray[np.uint16],
        absorption_weapon_token_ids: npt.NDArray[np.uint32],
        absorption_weapon_attack_values: npt.NDArray[np.uint16],
        absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_token_ids: npt.NDArray[np.uint32],
        chance_absorption_weapon_attack_values: npt.NDArray[np.uint16],
        chance_absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_hit_rates: npt.NDArray[np.uint16],
        dynamic_mp_weapon_token_ids: npt.NDArray[np.uint32],
        dynamic_mp_weapon_coefficients: npt.NDArray[np.uint16],
        dynamic_mp_weapon_elements: npt.NDArray[np.uint8],
        same_damage_weapon_token_ids: npt.NDArray[np.uint32],
        same_damage_weapon_attack_values: npt.NDArray[np.uint16],
        same_damage_weapon_elements: npt.NDArray[np.uint8],
        attack_twice_weapon_token_ids: npt.NDArray[np.uint32],
        attack_twice_weapon_attack_values: npt.NDArray[np.uint16],
        attack_twice_weapon_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class RandomTargetWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(
        self,
        batch_size: int,
        weapon_token_ids: npt.NDArray[np.uint32],
        attack_values: npt.NDArray[np.uint16],
        weapon_elements: npt.NDArray[np.uint8],
        booster_token_ids: npt.NDArray[np.uint32],
        booster_values: npt.NDArray[np.uint16],
        booster_elements: npt.NDArray[np.uint8],
        armor_token_ids: npt.NDArray[np.uint32],
        defense_values: npt.NDArray[np.uint16],
        armor_elements: npt.NDArray[np.uint8],
        hp_utility_token_ids: npt.NDArray[np.uint32],
        hp_utility_values: npt.NDArray[np.uint16],
        mp_utility_token_ids: npt.NDArray[np.uint32],
        mp_utility_values: npt.NDArray[np.uint16],
        attack_miracle_token_ids: npt.NDArray[np.uint32],
        attack_miracle_values: npt.NDArray[np.uint16],
        attack_miracle_elements: npt.NDArray[np.uint8],
        attack_miracle_costs: npt.NDArray[np.uint16],
        hp_miracle_token_ids: npt.NDArray[np.uint32],
        hp_miracle_values: npt.NDArray[np.uint16],
        hp_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_token_ids: npt.NDArray[np.uint32],
        chance_miracle_values: npt.NDArray[np.uint16],
        chance_miracle_elements: npt.NDArray[np.uint8],
        chance_miracle_costs: npt.NDArray[np.uint16],
        chance_miracle_hit_rates: npt.NDArray[np.uint16],
        effect_miracle_token_ids: npt.NDArray[np.uint32],
        effect_miracle_values: npt.NDArray[np.uint16],
        effect_miracle_elements: npt.NDArray[np.uint8],
        effect_miracle_costs: npt.NDArray[np.uint16],
        additive_miracle_token_ids: npt.NDArray[np.uint32],
        additive_miracle_values: npt.NDArray[np.uint16],
        additive_miracle_elements: npt.NDArray[np.uint8],
        additive_miracle_costs: npt.NDArray[np.uint16],
        reflection_armor_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_token_ids: npt.NDArray[np.uint32],
        reflection_weapon_values: npt.NDArray[np.uint16],
        dual_role_token_ids: npt.NDArray[np.uint32],
        dual_role_attack_values: npt.NDArray[np.uint16],
        dual_role_defense_values: npt.NDArray[np.uint16],
        dual_role_elements: npt.NDArray[np.uint8],
        chance_weapon_token_ids: npt.NDArray[np.uint32],
        chance_weapon_attack_values: npt.NDArray[np.uint16],
        chance_weapon_elements: npt.NDArray[np.uint8],
        chance_weapon_hit_rates: npt.NDArray[np.uint16],
        chance_dual_role_token_ids: npt.NDArray[np.uint32],
        chance_dual_role_attack_values: npt.NDArray[np.uint16],
        chance_dual_role_defense_values: npt.NDArray[np.uint16],
        chance_dual_role_elements: npt.NDArray[np.uint8],
        chance_dual_role_hit_rates: npt.NDArray[np.uint16],
        absorption_weapon_token_ids: npt.NDArray[np.uint32],
        absorption_weapon_attack_values: npt.NDArray[np.uint16],
        absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_token_ids: npt.NDArray[np.uint32],
        chance_absorption_weapon_attack_values: npt.NDArray[np.uint16],
        chance_absorption_weapon_elements: npt.NDArray[np.uint8],
        chance_absorption_weapon_hit_rates: npt.NDArray[np.uint16],
        dynamic_mp_weapon_token_ids: npt.NDArray[np.uint32],
        dynamic_mp_weapon_coefficients: npt.NDArray[np.uint16],
        dynamic_mp_weapon_elements: npt.NDArray[np.uint8],
        same_damage_weapon_token_ids: npt.NDArray[np.uint32],
        same_damage_weapon_attack_values: npt.NDArray[np.uint16],
        same_damage_weapon_elements: npt.NDArray[np.uint8],
        attack_twice_weapon_token_ids: npt.NDArray[np.uint32],
        attack_twice_weapon_attack_values: npt.NDArray[np.uint16],
        attack_twice_weapon_elements: npt.NDArray[np.uint8],
        random_target_weapon_token_ids: npt.NDArray[np.uint32],
        random_target_weapon_attack_values: npt.NDArray[np.uint16],
        random_target_weapon_elements: npt.NDArray[np.uint8],
        seed: int = ...,
        initial_hp: int = ...,
        initial_mp: int = ...,
    ) -> None: ...

class IllnessWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class IllnessCureResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class HeavenHerbResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class FeverMaskResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class MiracleBlockResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class MiracleBlockWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class MiracleBounceResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class MiracleBounceWeaponResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class MiracleBounceMiracleResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class MiracleReflectionResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class FogFlashResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class DarkCloudResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...

class DreamResourceAttackDefenseBatch(AttackDefenseBatch):
    def __init__(self, *args: object, **kwargs: object) -> None: ...
