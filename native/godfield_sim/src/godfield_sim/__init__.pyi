from typing import Final

import numpy as np
import numpy.typing as npt

KERNEL_SCHEMA_VERSION: Final[int]
OBSERVATION_SCHEMA_VERSION: Final[int]
RULESET_ID: Final[str]
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
FORGIVE_ACTION_INDEX: Final[int]
CONFIRM_ACTION_INDEX: Final[int]
GLOBAL_FEATURE_COUNT: Final[int]

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
    def hand_mask(self) -> npt.NDArray[np.bool_]: ...
    @property
    def hand_card_kinds(self) -> npt.NDArray[np.uint8]: ...
    @property
    def hand_elements(self) -> npt.NDArray[np.uint8]: ...
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
