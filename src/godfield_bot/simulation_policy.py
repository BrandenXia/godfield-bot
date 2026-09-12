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
    verified_attack_booster_miracle_cards,
    verified_attack_miracle_cards,
    verified_chance_attack_miracle_cards,
    verified_effect_attack_miracle_cards,
    verified_hp_utility_miracle_cards,
    verified_reflection_armor_cards,
    verified_reflection_weapon_cards,
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
FORGIVE_ACTION_INDEX = 19
CONFIRM_ACTION_INDEX = 20


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
    reflection_defenses: frozenset[int] = frozenset()
    policy_id: str = HEURISTIC_POLICY_ID


def build_curriculum_heuristic(
    snapshot: BibleSnapshot,
    vocabulary: ArtifactVocabulary,
    *,
    ruleset: AttackDefenseRuleset = "fixed-role",
) -> CurriculumHeuristic:
    boosters: dict[str, int] = {}
    dual_role_defenses: dict[str, int] = {}
    chance_weapon_slugs: set[str] = set()
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
        }:
            attacks.update(verified_reflection_weapon_cards(snapshot))
        if ruleset in {"dual-role-resource-hand", "chance-weapon-resource-hand"}:
            dual_roles = plain_dual_role_weapon_cards(snapshot)
            attacks.update(
                {slug: attack for slug, (attack, _defense, _element) in dual_roles.items()}
            )
            dual_role_defenses = {
                slug: defense for slug, (_attack, defense, _element) in dual_roles.items()
            }
        if ruleset == "chance-weapon-resource-hand":
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
                    for slug, (hit_rate, attack, _defense, _element) in (
                        chance_dual_roles.items()
                    )
                }
            )
            dual_role_defenses.update(
                {
                    slug: defense
                    for slug, (_hit_rate, _attack, defense, _element) in (
                        chance_dual_roles.items()
                    )
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
    }:
        reflection_defense_tokens.update(
            vocabulary.token_id("armor", slug) for slug in verified_reflection_armor_cards(snapshot)
        )
    if ruleset in {
        "reflection-weapon-resource-hand",
        "dual-role-resource-hand",
        "chance-weapon-resource-hand",
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
        ),
        reflection_defenses=frozenset(reflection_defense_tokens),
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
                attack_candidates = [
                    (attacks[int(hand[action - 1])], action)
                    for action in range(1, 10)
                    if legal[action] and int(hand[action - 1]) in attacks
                ]
                opponent_hp = round(float(batch.player_features[environment, 1, 0]) * 100)
                lethal = [
                    item
                    for item in attack_candidates
                    if item[0] >= opponent_hp
                    and int(hand[item[1] - 1]) not in policy.chance_attack_tokens
                ]
                if lethal:
                    actions[output_index] = max(lethal, key=lambda item: (item[0], -item[1]))[1]
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
                miracle_attacks = policy.attack_miracles or {}
                strongest_legal = max((value for value, _action in attack_candidates), default=0)
                actor = int(batch.active_players[environment])
                mp = int(batch.magic_points[environment, actor])
                blocked_upgrade = any(
                    token in miracle_attacks
                    and miracle_attacks[token][0] > strongest_legal
                    and miracle_attacks[token][1] > mp
                    for token in map(int, hand)
                )
                mp_utilities = policy.mp_utilities or {}
                restoration = [
                    (mp_utilities[int(hand[action - 1])], action)
                    for action in range(1, 10)
                    if legal[action] and int(hand[action - 1]) in mp_utilities
                ]
                if blocked_upgrade and restoration:
                    actions[output_index] = max(restoration, key=lambda item: (item[0], -item[1]))[
                        1
                    ]
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
                (policy.defenses[int(hand[action - 1])], action)
                for action in range(1, 10)
                if legal[action] and int(hand[action - 1]) in policy.defenses
            ]
            self_hp = round(float(batch.player_features[environment, 0, 0]) * 100)
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
