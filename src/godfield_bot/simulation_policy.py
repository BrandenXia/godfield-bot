from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from godfield_bot.domain.reference import BibleSnapshot
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
    verified_attack_twice_weapon_cards,
    verified_chance_absorption_weapon_cards,
    verified_chance_attack_miracle_cards,
    verified_dynamic_mp_weapon_cards,
    verified_effect_attack_miracle_cards,
    verified_fever_mask_armor,
    verified_fog_flash_attack_miracles,
    verified_fog_flash_weapon_cards,
    verified_fog_miracles,
    verified_heaven_herb_cards,
    verified_hp_utility_miracle_cards,
    verified_illness_cure_miracles,
    verified_illness_cure_sundries,
    verified_illness_weapon_cards,
    verified_miracle_block_armor,
    verified_miracle_block_weapon_cards,
    verified_miracle_bounce_armor,
    verified_miracle_bounce_miracles,
    verified_miracle_bounce_weapon_boosters,
    verified_miracle_reflection_armor,
    verified_miracle_reflection_weapons,
    verified_random_target_weapon_cards,
    verified_reflection_armor_cards,
    verified_reflection_weapon_cards,
    verified_same_damage_weapon_cards,
)
from godfield_bot.simulation import AttackDefenseRuleset, AttackDefenseSimulation

HEURISTIC_POLICY_ID = "plain-max-attack-conservative-defense-v0"
ELEMENTAL_HEURISTIC_POLICY_ID = "plain-element-aware-max-attack-conservative-defense-v1"
COMBO_HEURISTIC_POLICY_ID = "plain-elemental-greedy-combo-v2"
RESOURCE_HEURISTIC_POLICY_ID = "plain-resource-aware-combo-v1"
STOCHASTIC_RESOURCE_HEURISTIC_POLICY_ID = "expected-value-stochastic-resource-combo-v1"
EXPANDED_RESOURCE_HEURISTIC_POLICY_ID = "expected-value-additive-miracle-resource-combo-v1"
REFLECTION_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-reflection-resource-combo-v1"
REFLECTION_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-reflection-weapon-resource-combo-v1"
DUAL_ROLE_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-dual-role-resource-combo-v1"
CHANCE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-chance-weapon-resource-combo-v1"
ABSORPTION_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-absorption-weapon-resource-combo-v1"
DYNAMIC_MP_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-dynamic-mp-weapon-resource-combo-v1"
SAME_DAMAGE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-same-damage-weapon-resource-combo-v1"
ATTACK_TWICE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-attack-twice-weapon-resource-combo-v1"
RANDOM_TARGET_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = (
    "evidenced-random-target-weapon-resource-combo-v1"
)
ILLNESS_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-illness-weapon-resource-combo-v1"
ILLNESS_CURE_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-illness-cure-resource-combo-v1"
HEAVEN_HERB_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-heaven-herb-resource-combo-v1"
FEVER_MASK_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-fever-mask-resource-combo-v1"
MIRACLE_BLOCK_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-miracle-block-resource-combo-v1"
MIRACLE_BLOCK_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = (
    "evidenced-miracle-block-weapon-resource-combo-v1"
)
MIRACLE_BOUNCE_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-miracle-bounce-resource-combo-v1"
MIRACLE_BOUNCE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID = (
    "evidenced-miracle-bounce-weapon-resource-combo-v1"
)
MIRACLE_BOUNCE_MIRACLE_RESOURCE_HEURISTIC_POLICY_ID = (
    "evidenced-miracle-bounce-miracle-resource-combo-v1"
)
MIRACLE_REFLECTION_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-miracle-reflection-resource-combo-v1"
FOG_FLASH_RESOURCE_HEURISTIC_POLICY_ID = "evidenced-fog-flash-resource-combo-v2"
FORGIVE_ACTION_INDEX = 19
CONFIRM_ACTION_INDEX = 20
MIRACLE_ATTACK_CARD_KINDS = frozenset({6, 8, 9, 36, 37})


class SimulationPolicyError(RuntimeError):
    """Raised when a curriculum policy cannot select a legal action."""


@dataclass(frozen=True)
class CurriculumHeuristic:
    attacks: dict[int, int]
    defenses: dict[int, int]
    boosters: dict[int, int] | None = None
    hp_utilities: dict[int, tuple[int, int]] | None = None
    mp_utilities: dict[int, int] | None = None
    attack_miracles: dict[int, tuple[int, int]] | None = None
    chance_attack_tokens: frozenset[int] = frozenset()
    dynamic_mp_attacks: dict[int, int] | None = None
    same_damage_attack_tokens: frozenset[int] = frozenset()
    random_target_attack_tokens: frozenset[int] = frozenset()
    reflection_defenses: frozenset[int] = frozenset()
    illness_cures: dict[int, tuple[int, int]] | None = None
    heaven_herbs: dict[int, int] | None = None
    self_fever_defenses: frozenset[int] = frozenset()
    miracle_block_defenses: frozenset[int] = frozenset()
    miracle_bounce_defenses: frozenset[int] = frozenset()
    miracle_reflection_defenses: frozenset[int] = frozenset()
    fog_attack_tokens: frozenset[int] = frozenset()
    flash_attack_tokens: frozenset[int] = frozenset()
    policy_id: str = HEURISTIC_POLICY_ID


def _resolved_attack_value(
    token: int,
    attacks: dict[int, int],
    dynamic_mp_attacks: dict[int, int],
    mp: int,
) -> int:
    coefficient = dynamic_mp_attacks.get(token)
    return attacks[token] if coefficient is None else coefficient * mp


def _attack_heuristic_value(
    token: int,
    attacks: dict[int, int],
    dynamic_mp_attacks: dict[int, int],
    random_target_attacks: frozenset[int],
    mp: int,
) -> int:
    """Return opponent-directed expected damage for attack ranking."""

    value = _resolved_attack_value(token, attacks, dynamic_mp_attacks, mp)
    return round(value / 2) if token in random_target_attacks else value


def _defense_heuristic_value(
    token: int,
    policy: CurriculumHeuristic,
    pending_attack: int,
    pending_base_kind: int,
) -> int:
    if pending_base_kind in MIRACLE_ATTACK_CARD_KINDS and token in (
        policy.miracle_block_defenses
        | policy.miracle_bounce_defenses
        | policy.miracle_reflection_defenses
    ):
        return pending_attack
    return policy.defenses[token]


def build_curriculum_heuristic(
    snapshot: BibleSnapshot,
    vocabulary: ArtifactVocabulary,
    *,
    ruleset: AttackDefenseRuleset = "fixed-role",
) -> CurriculumHeuristic:
    fog_flash_ruleset = ruleset == "fog-flash-resource-hand"
    miracle_reflection_ruleset = ruleset in {
        "miracle-reflection-resource-hand",
        "fog-flash-resource-hand",
    }
    miracle_bounce_miracle_ruleset = ruleset in {
        "miracle-bounce-miracle-resource-hand",
        "miracle-reflection-resource-hand",
        "fog-flash-resource-hand",
    }
    miracle_bounce_weapon_ruleset = ruleset in {
        "miracle-bounce-weapon-resource-hand",
        "miracle-bounce-miracle-resource-hand",
        "miracle-reflection-resource-hand",
        "fog-flash-resource-hand",
    }
    miracle_bounce_ruleset = ruleset in {
        "miracle-bounce-resource-hand",
        "miracle-bounce-weapon-resource-hand",
        "miracle-bounce-miracle-resource-hand",
        "miracle-reflection-resource-hand",
        "fog-flash-resource-hand",
    }
    miracle_block_weapon_ruleset = ruleset in {
        "miracle-block-weapon-resource-hand",
        "miracle-bounce-resource-hand",
        "miracle-bounce-weapon-resource-hand",
        "miracle-bounce-miracle-resource-hand",
        "miracle-reflection-resource-hand",
        "fog-flash-resource-hand",
    }
    miracle_block_ruleset = ruleset in {
        "miracle-block-resource-hand",
        "miracle-block-weapon-resource-hand",
        "miracle-bounce-resource-hand",
        "miracle-bounce-weapon-resource-hand",
        "miracle-bounce-miracle-resource-hand",
        "miracle-reflection-resource-hand",
        "fog-flash-resource-hand",
    }
    if miracle_block_ruleset:
        ruleset = "fever-mask-resource-hand"
    boosters: dict[str, int] = {}
    dual_role_defenses: dict[str, int] = {}
    chance_weapon_slugs: set[str] = set()
    dynamic_mp_attacks: dict[str, int] = {}
    same_damage_attack_slugs: set[str] = set()
    random_target_attack_slugs: set[str] = set()
    if ruleset in {
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
        "dynamic-mp-weapon-resource-hand",
        "same-damage-weapon-resource-hand",
        "attack-twice-weapon-resource-hand",
        "random-target-weapon-resource-hand",
        "illness-weapon-resource-hand",
        "illness-cure-resource-hand",
        "heaven-herb-resource-hand",
        "fever-mask-resource-hand",
    }:
        attacks = {
            slug: attack for slug, (attack, _element) in plain_attack_weapon_cards(snapshot).items()
        }
        defenses = {
            slug: defense
            for slug, (defense, _element) in plain_defense_armor_cards(snapshot).items()
        }
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
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            boosters = {
                slug: boost
                for slug, (boost, _element) in plain_attack_booster_cards(snapshot).items()
            }
            policy_id = COMBO_HEURISTIC_POLICY_ID
        else:
            policy_id = ELEMENTAL_HEURISTIC_POLICY_ID
        if ruleset in {
            "reflection-weapon-resource-hand",
            "dual-role-resource-hand",
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            attacks.update(verified_reflection_weapon_cards(snapshot))
        if ruleset in {
            "dual-role-resource-hand",
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            dual_roles = plain_dual_role_weapon_cards(snapshot)
            attacks.update(
                {slug: attack for slug, (attack, _defense, _element) in dual_roles.items()}
            )
            dual_role_defenses = {
                slug: defense for slug, (_attack, defense, _element) in dual_roles.items()
            }
        if ruleset in {
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            chance_weapons = plain_chance_weapon_cards(snapshot)
            chance_dual_roles = plain_chance_dual_role_weapon_cards(snapshot)
            chance_weapon_slugs.update(chance_weapons)
            chance_weapon_slugs.update(chance_dual_roles)
            attacks.update(
                {
                    slug: round(hit_rate * attack / 100)
                    for slug, (hit_rate, attack, _element) in chance_weapons.items()
                }
            )
            attacks.update(
                {
                    slug: round(hit_rate * attack / 100)
                    for slug, (hit_rate, attack, _defense, _element) in (chance_dual_roles.items())
                }
            )
            dual_role_defenses.update(
                {
                    slug: defense
                    for slug, (_hit_rate, _attack, defense, _element) in (chance_dual_roles.items())
                }
            )
        if ruleset in {
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            absorption_weapons = verified_absorption_weapon_cards(snapshot)
            chance_absorption_weapons = verified_chance_absorption_weapon_cards(snapshot)
            attacks.update(
                {slug: attack for slug, (attack, _element) in absorption_weapons.items()}
            )
            attacks.update(
                {
                    slug: round(hit_rate * attack / 100)
                    for slug, (hit_rate, attack, _element) in (chance_absorption_weapons.items())
                }
            )
            chance_weapon_slugs.update(chance_absorption_weapons)
        if ruleset in {
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            dynamic_mp_attacks = {
                slug: coefficient
                for slug, (coefficient, _element) in verified_dynamic_mp_weapon_cards(
                    snapshot
                ).items()
            }
            attacks.update(dynamic_mp_attacks)
        if ruleset in {
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            same_damage_attacks = verified_same_damage_weapon_cards(snapshot)
            same_damage_attack_slugs.update(same_damage_attacks)
            attacks.update(
                {slug: attack for slug, (attack, _element) in same_damage_attacks.items()}
            )
        if ruleset in {
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            attack_twice = verified_attack_twice_weapon_cards(snapshot)
            attacks.update(
                {
                    slug: attack * strikes
                    for slug, (attack, strikes, _element) in attack_twice.items()
                }
            )
        if ruleset in {
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            random_target_attacks = verified_random_target_weapon_cards(snapshot)
            random_target_attack_slugs.update(random_target_attacks)
            attacks.update(
                {slug: attack for slug, (attack, _element) in random_target_attacks.items()}
            )
        if ruleset in {
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            attacks.update(
                {
                    slug: attack
                    for slug, (attack, _element, _stage) in verified_illness_weapon_cards(
                        snapshot
                    ).items()
                }
            )
    else:
        attacks = plain_attack_weapon_values(snapshot)
        defenses = plain_defense_armor_values(snapshot)
        policy_id = HEURISTIC_POLICY_ID
    hp_utilities: dict[str, tuple[int, int]] = {}
    mp_utilities: dict[str, int] = {}
    attack_miracles: dict[str, tuple[int, int]] = {}
    chance_attack_slugs: set[str] = set()
    miracle_boosters: dict[str, int] = {}
    if ruleset in {
        "resource-hand",
        "stochastic-resource-hand",
        "expanded-resource-hand",
        "reflection-resource-hand",
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
        "dynamic-mp-weapon-resource-hand",
        "same-damage-weapon-resource-hand",
        "attack-twice-weapon-resource-hand",
        "random-target-weapon-resource-hand",
        "illness-weapon-resource-hand",
        "illness-cure-resource-hand",
        "heaven-herb-resource-hand",
        "fever-mask-resource-hand",
    }:
        hp_utilities.update(
            (slug, (utility, 0)) for slug, utility in plain_hp_utility_sundries(snapshot).items()
        )
        hp_utilities.update(verified_hp_utility_miracle_cards(snapshot))
        mp_utilities = plain_mp_utility_sundries(snapshot)
        attack_miracles = {
            slug: (attack, cost)
            for slug, (attack, cost, _element) in verified_attack_miracle_cards(snapshot).items()
        }
        policy_id = RESOURCE_HEURISTIC_POLICY_ID
        if ruleset in {
            "stochastic-resource-hand",
            "expanded-resource-hand",
            "reflection-resource-hand",
            "reflection-weapon-resource-hand",
            "dual-role-resource-hand",
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
        }:
            chance_miracles = {
                slug: (round(hit_rate * attack / 100), cost)
                for slug, (hit_rate, attack, cost, _element) in (
                    verified_chance_attack_miracle_cards(snapshot).items()
                )
            }
            chance_attack_slugs = set(chance_miracles)
            effect_miracles = {
                slug: (attack, cost)
                for slug, (attack, cost, _element, effect) in (
                    verified_effect_attack_miracle_cards(snapshot).items()
                )
                if effect == "absorbHP"
            }
            attack_miracles.update(chance_miracles)
            attack_miracles.update(effect_miracles)
            policy_id = STOCHASTIC_RESOURCE_HEURISTIC_POLICY_ID
            if ruleset in {
                "expanded-resource-hand",
                "reflection-resource-hand",
                "reflection-weapon-resource-hand",
                "dual-role-resource-hand",
                "chance-weapon-resource-hand",
                "absorption-weapon-resource-hand",
                "dynamic-mp-weapon-resource-hand",
                "same-damage-weapon-resource-hand",
                "attack-twice-weapon-resource-hand",
                "random-target-weapon-resource-hand",
                "illness-weapon-resource-hand",
                "illness-cure-resource-hand",
                "heaven-herb-resource-hand",
                "fever-mask-resource-hand",
            }:
                miracle_boosters = {
                    slug: boost
                    for slug, (boost, _cost, _element) in (
                        verified_attack_booster_miracle_cards(snapshot).items()
                    )
                }
                policy_id = EXPANDED_RESOURCE_HEURISTIC_POLICY_ID
                if ruleset == "reflection-resource-hand":
                    policy_id = REFLECTION_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "reflection-weapon-resource-hand":
                    policy_id = REFLECTION_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "dual-role-resource-hand":
                    policy_id = DUAL_ROLE_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "chance-weapon-resource-hand":
                    policy_id = CHANCE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "absorption-weapon-resource-hand":
                    policy_id = ABSORPTION_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "dynamic-mp-weapon-resource-hand":
                    policy_id = DYNAMIC_MP_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "same-damage-weapon-resource-hand":
                    policy_id = SAME_DAMAGE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "attack-twice-weapon-resource-hand":
                    policy_id = ATTACK_TWICE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "random-target-weapon-resource-hand":
                    policy_id = RANDOM_TARGET_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "illness-weapon-resource-hand":
                    policy_id = ILLNESS_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "illness-cure-resource-hand":
                    policy_id = ILLNESS_CURE_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "heaven-herb-resource-hand":
                    policy_id = HEAVEN_HERB_RESOURCE_HEURISTIC_POLICY_ID
                elif ruleset == "fever-mask-resource-hand":
                    policy_id = FEVER_MASK_RESOURCE_HEURISTIC_POLICY_ID
    attack_token_values = {
        vocabulary.token_id("weapons", slug): attack for slug, attack in attacks.items()
    }
    attack_token_values.update(
        {
            vocabulary.token_id("miracles", slug): attack
            for slug, (attack, _cost) in attack_miracles.items()
        }
    )
    booster_token_values = {
        vocabulary.token_id("weapons", slug): boost for slug, boost in boosters.items()
    }
    booster_token_values.update(
        {vocabulary.token_id("miracles", slug): boost for slug, boost in miracle_boosters.items()}
    )
    reflection_defense_tokens: set[int] = set()
    if ruleset in {
        "reflection-resource-hand",
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
        "dynamic-mp-weapon-resource-hand",
        "same-damage-weapon-resource-hand",
        "attack-twice-weapon-resource-hand",
        "random-target-weapon-resource-hand",
        "illness-weapon-resource-hand",
        "illness-cure-resource-hand",
        "heaven-herb-resource-hand",
        "fever-mask-resource-hand",
    }:
        reflection_defense_tokens.update(
            vocabulary.token_id("armor", slug) for slug in verified_reflection_armor_cards(snapshot)
        )
    if ruleset in {
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
        "absorption-weapon-resource-hand",
        "dynamic-mp-weapon-resource-hand",
        "same-damage-weapon-resource-hand",
        "attack-twice-weapon-resource-hand",
        "random-target-weapon-resource-hand",
        "illness-weapon-resource-hand",
        "illness-cure-resource-hand",
        "heaven-herb-resource-hand",
        "fever-mask-resource-hand",
    }:
        reflection_defense_tokens.update(
            vocabulary.token_id("weapons", slug)
            for slug in verified_reflection_weapon_cards(snapshot)
        )
    defense_token_values = {
        vocabulary.token_id("armor", slug): defense for slug, defense in defenses.items()
    }
    defense_token_values.update(
        {
            vocabulary.token_id("weapons", slug): defense
            for slug, defense in dual_role_defenses.items()
        }
    )
    illness_cures: dict[int, tuple[int, int]] = {}
    if ruleset in {
        "illness-cure-resource-hand",
        "heaven-herb-resource-hand",
        "fever-mask-resource-hand",
    }:
        illness_cures.update(
            {
                vocabulary.token_id("sundries", slug): (2 if cure_all else 1, 0)
                for slug, cure_all in verified_illness_cure_sundries(snapshot).items()
            }
        )
        illness_cures.update(
            {
                vocabulary.token_id("miracles", slug): (2 if cure_all else 1, cost)
                for slug, (cost, cure_all) in verified_illness_cure_miracles(snapshot).items()
            }
        )
    heaven_herbs: dict[int, int] = {}
    if ruleset in {"heaven-herb-resource-hand", "fever-mask-resource-hand"}:
        heaven_herbs = {
            vocabulary.token_id("sundries", slug): mp_gain
            for slug, mp_gain in verified_heaven_herb_cards(snapshot).items()
        }
    self_fever_defenses: set[int] = set()
    if ruleset == "fever-mask-resource-hand":
        fever_masks = verified_fever_mask_armor(snapshot)
        defense_token_values.update(
            {
                vocabulary.token_id("armor", slug): defense
                for slug, (defense, _element) in fever_masks.items()
            }
        )
        self_fever_defenses.update(vocabulary.token_id("armor", slug) for slug in fever_masks)
    miracle_block_defenses: set[int] = set()
    if miracle_block_ruleset:
        miracle_block_armor = verified_miracle_block_armor(snapshot)
        defense_token_values.update(
            {
                vocabulary.token_id("armor", slug): defense
                for slug, defense in miracle_block_armor.items()
            }
        )
        miracle_block_defenses.update(
            vocabulary.token_id("armor", slug) for slug in miracle_block_armor
        )
        policy_id = MIRACLE_BLOCK_RESOURCE_HEURISTIC_POLICY_ID
    if miracle_block_weapon_ruleset:
        miracle_block_weapons = verified_miracle_block_weapon_cards(snapshot)
        for slug, (attack, booster) in miracle_block_weapons.items():
            token = vocabulary.token_id("weapons", slug)
            if booster:
                booster_token_values[token] = attack
            else:
                attack_token_values[token] = attack
            defense_token_values[token] = 0
            miracle_block_defenses.add(token)
        policy_id = MIRACLE_BLOCK_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
    miracle_bounce_defenses: set[int] = set()
    if miracle_bounce_ruleset:
        miracle_bounce_armor = verified_miracle_bounce_armor(snapshot)
        defense_token_values.update(
            {
                vocabulary.token_id("armor", slug): defense
                for slug, defense in miracle_bounce_armor.items()
            }
        )
        miracle_bounce_defenses.update(
            vocabulary.token_id("armor", slug) for slug in miracle_bounce_armor
        )
        policy_id = MIRACLE_BOUNCE_RESOURCE_HEURISTIC_POLICY_ID
    if miracle_bounce_weapon_ruleset:
        for slug, boost in verified_miracle_bounce_weapon_boosters(snapshot).items():
            token = vocabulary.token_id("weapons", slug)
            booster_token_values[token] = boost
            defense_token_values[token] = 0
            miracle_bounce_defenses.add(token)
        policy_id = MIRACLE_BOUNCE_WEAPON_RESOURCE_HEURISTIC_POLICY_ID
    if miracle_bounce_miracle_ruleset:
        for slug in verified_miracle_bounce_miracles(snapshot):
            token = vocabulary.token_id("miracles", slug)
            defense_token_values[token] = 0
            miracle_bounce_defenses.add(token)
        policy_id = MIRACLE_BOUNCE_MIRACLE_RESOURCE_HEURISTIC_POLICY_ID
    miracle_reflection_defenses: set[int] = set()
    if miracle_reflection_ruleset:
        for slug, defense in verified_miracle_reflection_armor(snapshot).items():
            token = vocabulary.token_id("armor", slug)
            defense_token_values[token] = defense
            miracle_reflection_defenses.add(token)
        for slug, attack in verified_miracle_reflection_weapons(snapshot).items():
            token = vocabulary.token_id("weapons", slug)
            attack_token_values[token] = attack
            defense_token_values[token] = 0
            miracle_reflection_defenses.add(token)
        policy_id = MIRACLE_REFLECTION_RESOURCE_HEURISTIC_POLICY_ID
    fog_attack_tokens: set[int] = set()
    flash_attack_tokens: set[int] = set()
    if fog_flash_ruleset:
        for slug, (hit_rate, attack, _element, curse) in verified_fog_flash_weapon_cards(
            snapshot
        ).items():
            token = vocabulary.token_id("weapons", slug)
            attack_token_values[token] = round(hit_rate * attack / 100)
            (fog_attack_tokens if curse == "fog" else flash_attack_tokens).add(token)
            if hit_rate < 100:
                chance_weapon_slugs.add(slug)
        for slug, (hit_rate, attack, cost, _element, curse) in verified_fog_flash_attack_miracles(
            snapshot
        ).items():
            token = vocabulary.token_id("miracles", slug)
            expected_attack = round(hit_rate * attack / 100)
            attack_token_values[token] = expected_attack
            attack_miracles[slug] = (expected_attack, cost)
            (fog_attack_tokens if curse == "fog" else flash_attack_tokens).add(token)
            chance_attack_slugs.add(slug)
        for slug, (cost, _element) in verified_fog_miracles(snapshot).items():
            token = vocabulary.token_id("miracles", slug)
            attack_token_values[token] = 0
            attack_miracles[slug] = (0, cost)
            fog_attack_tokens.add(token)
        policy_id = FOG_FLASH_RESOURCE_HEURISTIC_POLICY_ID
    return CurriculumHeuristic(
        attacks=attack_token_values,
        defenses=defense_token_values,
        boosters=booster_token_values,
        hp_utilities={
            vocabulary.token_id("miracles" if cost else "sundries", slug): (utility, cost)
            for slug, (utility, cost) in hp_utilities.items()
        },
        mp_utilities={
            vocabulary.token_id("sundries", slug): utility for slug, utility in mp_utilities.items()
        },
        attack_miracles={
            vocabulary.token_id("miracles", slug): value for slug, value in attack_miracles.items()
        },
        chance_attack_tokens=frozenset(
            [vocabulary.token_id("miracles", slug) for slug in chance_attack_slugs]
            + [vocabulary.token_id("weapons", slug) for slug in chance_weapon_slugs]
            + [vocabulary.token_id("weapons", slug) for slug in random_target_attack_slugs]
        ),
        dynamic_mp_attacks={
            vocabulary.token_id("weapons", slug): coefficient
            for slug, coefficient in dynamic_mp_attacks.items()
        },
        same_damage_attack_tokens=frozenset(
            vocabulary.token_id("weapons", slug) for slug in same_damage_attack_slugs
        ),
        random_target_attack_tokens=frozenset(
            vocabulary.token_id("weapons", slug) for slug in random_target_attack_slugs
        ),
        reflection_defenses=frozenset(reflection_defense_tokens),
        illness_cures=illness_cures,
        heaven_herbs=heaven_herbs,
        self_fever_defenses=frozenset(self_fever_defenses),
        miracle_block_defenses=frozenset(miracle_block_defenses),
        miracle_bounce_defenses=frozenset(miracle_bounce_defenses),
        miracle_reflection_defenses=frozenset(miracle_reflection_defenses),
        fog_attack_tokens=frozenset(fog_attack_tokens),
        flash_attack_tokens=frozenset(flash_attack_tokens),
        policy_id=policy_id,
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
            if batch.combo and int(batch.selected_counts[environment]) > 0:
                boosters = policy.boosters or {}
                candidates = [
                    (boosters[int(hand[action - 1])], action)
                    for action in range(1, 10)
                    if legal[action] and int(hand[action - 1]) in boosters
                ]
                actions[output_index] = (
                    max(candidates, key=lambda item: (item[0], -item[1]))[1]
                    if candidates
                    else CONFIRM_ACTION_INDEX
                )
                continue
            if batch.resource_curriculum:
                attacks = policy.attacks
                actor = int(batch.active_players[environment])
                mp = int(batch.magic_points[environment, actor])
                dynamic_mp_attacks = policy.dynamic_mp_attacks or {}
                random_target_attacks = policy.random_target_attack_tokens
                hand_tokens = set(map(int, hand))
                attack_candidates = [
                    (
                        _attack_heuristic_value(
                            int(hand[action - 1]),
                            attacks,
                            dynamic_mp_attacks,
                            random_target_attacks,
                            mp,
                        ),
                        action,
                    )
                    for action in range(1, 10)
                    if legal[action] and int(hand[action - 1]) in attacks
                ]
                opponent_hp = round(float(batch.player_features[environment, 1, 0]) * 100)
                fog_flags = getattr(batch, "fog_flags", None)
                flash_flags = getattr(batch, "flash_flags", None)
                actor_fogged = (
                    bool(fog_flags[environment, actor]) if fog_flags is not None else False
                )
                lethal = [
                    item
                    for item in attack_candidates
                    if not actor_fogged
                    and item[0] >= opponent_hp
                    and int(hand[item[1] - 1]) not in policy.chance_attack_tokens
                ]
                if lethal:
                    actions[output_index] = max(lethal, key=lambda item: (item[0], -item[1]))[1]
                    continue
                illness_cures = policy.illness_cures or {}
                heaven_herbs = policy.heaven_herbs or {}
                illness_stage = (
                    int(batch.illness_stages[environment, actor])
                    if illness_cures or heaven_herbs
                    else 0
                )
                removable_curse = (
                    illness_stage > 0
                    or (bool(fog_flags[environment, actor]) if fog_flags is not None else False)
                    or (bool(flash_flags[environment, actor]) if flash_flags is not None else False)
                )
                if illness_cures:
                    cure_candidates = [
                        (illness_cures[int(hand[action - 1])], action)
                        for action in range(1, 10)
                        if legal[action] and int(hand[action - 1]) in illness_cures
                    ]
                    if removable_curse and cure_candidates:
                        actions[output_index] = min(
                            cure_candidates,
                            key=lambda item: (
                                item[0][0] > 1 and illness_stage <= 2,
                                item[0][1],
                                item[1],
                            ),
                        )[1]
                        continue
                if illness_stage in {0, 3} and mp <= 80:
                    herb_candidates = [
                        (heaven_herbs[int(hand[action - 1])], action)
                        for action in range(1, 10)
                        if legal[action] and int(hand[action - 1]) in heaven_herbs
                    ]
                    if herb_candidates:
                        actions[output_index] = max(
                            herb_candidates,
                            key=lambda item: (item[0], -item[1]),
                        )[1]
                        continue
                self_hp = round(float(batch.player_features[environment, 0, 0]) * 100)
                hp_utilities = policy.hp_utilities or {}
                healing = [
                    (hp_utilities[int(hand[action - 1])][0], action)
                    for action in range(1, 10)
                    if legal[action] and int(hand[action - 1]) in hp_utilities
                ]
                if self_hp <= 25 and healing:
                    actions[output_index] = max(healing, key=lambda item: (item[0], -item[1]))[1]
                    continue
                non_suicidal_attacks = [
                    item
                    for item in attack_candidates
                    if not (
                        (
                            int(hand[item[1] - 1]) in policy.same_damage_attack_tokens
                            and item[0] >= self_hp
                            and item[0] < opponent_hp
                        )
                        or (
                            int(hand[item[1] - 1]) in random_target_attacks
                            and policy.attacks[int(hand[item[1] - 1])] >= self_hp
                        )
                    )
                ]
                if non_suicidal_attacks:
                    attack_candidates = non_suicidal_attacks
                miracle_attacks = policy.attack_miracles or {}
                strongest_legal = max((value for value, _action in attack_candidates), default=0)
                blocked_miracle_upgrade = any(
                    token in miracle_attacks
                    and miracle_attacks[token][0] > strongest_legal
                    and miracle_attacks[token][1] > mp
                    for token in hand_tokens
                )
                mp_utilities = policy.mp_utilities or {}
                restoration = [
                    (mp_utilities[int(hand[action - 1])], action)
                    for action in range(1, 10)
                    if legal[action] and int(hand[action - 1]) in mp_utilities
                ]
                best_restoration = max((utility for utility, _action in restoration), default=0)
                dynamic_upgrade = any(
                    coefficient * min(100, mp + best_restoration) > strongest_legal
                    for token, coefficient in dynamic_mp_attacks.items()
                    if token in hand_tokens
                )
                if restoration and (blocked_miracle_upgrade or dynamic_upgrade):
                    actions[output_index] = max(restoration, key=lambda item: (item[0], -item[1]))[
                        1
                    ]
                    continue
                if attack_candidates:
                    opponent = 1 - actor
                    opponent_fogged = (
                        bool(fog_flags[environment, opponent]) if fog_flags is not None else False
                    )
                    opponent_flashed = (
                        bool(flash_flags[environment, opponent])
                        if flash_flags is not None
                        else False
                    )

                    strategic_candidates: list[tuple[int, int, int, int]] = []
                    for expected_damage, action in attack_candidates:
                        token = int(hand[action - 1])
                        curse_utility = 0
                        if token in policy.fog_attack_tokens and not opponent_fogged:
                            curse_utility = 4
                        elif token in policy.flash_attack_tokens and not opponent_flashed:
                            curse_utility = 3
                        strategic_candidates.append(
                            (expected_damage + curse_utility, expected_damage, -action, action)
                        )

                    actions[output_index] = max(strategic_candidates)[3]
                    continue
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
        pending_base_kind = int(batch.pending_base_kinds[environment])
        if batch.combo:
            selected_defense = int(batch.selected_values[environment])
            if selected_defense >= pending_attack and selected_defense > 0:
                actions[output_index] = CONFIRM_ACTION_INDEX
                continue
            reflection_defenses = policy.reflection_defenses
            reflection_actions = [
                action
                for action in range(1, 10)
                if legal[action] and int(hand[action - 1]) in reflection_defenses
            ]
            candidates = [
                (
                    _defense_heuristic_value(
                        int(hand[action - 1]),
                        policy,
                        pending_attack,
                        pending_base_kind,
                    ),
                    action,
                )
                for action in range(1, 10)
                if legal[action] and int(hand[action - 1]) in policy.defenses
            ]
            self_hp = round(float(batch.player_features[environment, 0, 0]) * 100)
            fever_candidates = [
                item for item in candidates if int(hand[item[1] - 1]) in policy.self_fever_defenses
            ]
            ordinary_candidates = [
                item
                for item in candidates
                if int(hand[item[1] - 1]) not in policy.self_fever_defenses
            ]
            if fever_candidates:
                actor = int(batch.active_players[environment])
                illness_stage = int(batch.illness_stages[environment, actor])
                ordinary_total = selected_defense + sum(
                    value for value, _action in ordinary_candidates
                )
                fever_total = ordinary_total + sum(value for value, _action in fever_candidates)
                fever_prevents_lethal = (
                    pending_attack - ordinary_total >= self_hp
                    and pending_attack - fever_total < self_hp
                    and illness_stage < 4
                )
                candidates = ordinary_candidates + (
                    fever_candidates if fever_prevents_lethal else []
                )
            total_available_defense = selected_defense + sum(value for value, _ in candidates)
            reflection_prevents_lethal = pending_attack - total_available_defense >= self_hp
            if reflection_actions and (not candidates or reflection_prevents_lethal):
                actions[output_index] = min(reflection_actions)
            elif candidates:
                actions[output_index] = max(candidates, key=lambda item: (item[0], -item[1]))[1]
            elif selected_defense > 0 or legal[CONFIRM_ACTION_INDEX]:
                actions[output_index] = CONFIRM_ACTION_INDEX
            elif legal[FORGIVE_ACTION_INDEX]:
                actions[output_index] = FORGIVE_ACTION_INDEX
            else:
                raise SimulationPolicyError(
                    "combo heuristic found no legal defense, confirm, or pass"
                )
            continue
        candidates = [
            (
                _defense_heuristic_value(
                    int(hand[action - 1]),
                    policy,
                    pending_attack,
                    pending_base_kind,
                ),
                action,
            )
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
