"""Fixed tactical opponent for local full-game evaluation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from godfield_bot.full_game import FullGameMetadata
from godfield_bot.full_game_observation import (
    GLOBAL_FIELDS,
    HAND_FEATURES,
    HAND_SLOTS,
    PLAYER_FEATURES,
    FullGameObservation,
)

GREEDY_POLICY_ID: Final = "full-game-public-greedy-v1"
GREEDY_POLICY_SHA256: Final = hashlib.sha256(GREEDY_POLICY_ID.encode()).hexdigest()
DISCARD: Final = HAND_SLOTS + 1
CONTEXT_START: Final = GLOBAL_FIELDS.index("pending_observations.active")
CONTEXT_INDEX: Final = {name: i for i, name in enumerate(GLOBAL_FIELDS[CONTEXT_START:])}
HP: Final = PLAYER_FEATURES.index("hp_fraction")
ENEMY: Final = PLAYER_FEATURES.index("relation_3")
VISIBLE: Final = PLAYER_FEATURES.index("visible")


@dataclass(frozen=True)
class _Decision:
    phase: int
    legal: list[int]
    models: npt.NDArray[np.int64]
    hand: npt.NDArray[np.float32]
    players: npt.NDArray[np.float32]
    context: npt.NDArray[np.float64]
    actor: int
    hp: int
    mp: int
    cp: int

    def value(self, view: str, field: str) -> int:
        return round(float(self.context[CONTEXT_INDEX[f"{view}_observations.{field}"]]))

    def selected(self, phase: str) -> list[int]:
        ranks = self.hand[:, HAND_FEATURES.index(f"{phase}_selection_rank")]
        return [int(slot) + 1 for slot in ranks.argsort() if ranks[slot] > 0]


class FullGameGreedyPolicy:
    """Use displayed profiles and one public observation, with no engine access."""

    def __init__(self, metadata: FullGameMetadata) -> None:
        self.cap = metadata.resource_cap
        self.players = metadata.player_count
        plan = metadata.plan
        self.attacks = {
            model: (power, element, cost)
            for model, power, element, _, cost in plan.combat.attack_profiles
        }
        self.armor = {model: value for model, value, *_ in plan.combat.armor_profiles}
        self.chances = dict(plan.combat.chance_profiles)
        self.boosts = {
            model: (power, element, cost, kind)
            for model, power, element, cost, kind, _ in plan.combat.boost_profiles
        }
        for model, power, element, cost, _, can_lead in plan.combat.boost_profiles:
            if can_lead:
                self.attacks.setdefault(model, (power, element, cost))
        self.reducers = {model for model, *_ in plan.costs.profiles}
        for model, _, power, defense in plan.costs.profiles:
            if power:
                self.attacks[model] = (power, 0, 0)
            if defense:
                self.armor[model] = defense
        self.armor.update({model: value for model, value, *_ in plan.dream_defense.profiles})
        self.specials = {
            model: (kind, origin, neutral, cost)
            for model, kind, origin, neutral, cost in plan.combat.special_profiles
        }
        self.effects = {
            model: (kind, value) for model, kind, value in plan.combat.attack_effect_profiles
        }
        self.utility = {
            model: (kind, value, cost) for model, kind, value, cost in plan.effect_profiles
        }
        self.utility.update({model: (8, 0, cost) for model, cost in plan.guardians.summon_profiles})
        self.miracles = {model for model, category in plan.inventory.profiles if category == 4}
        self.discardable = set(plan.discard.discard_model_ids)
        self.area_costs = dict(plan.area.profiles)
        self.complex = {
            model: (kind, power, element) for model, kind, power, element in plan.weapons.profiles
        }
        for model, attack, rate, _, _, element in plan.attack_family.profiles:
            self.attacks[model] = (attack, element, 0)
            self.chances[model] = rate
        self.removal = {model: 4 if kind == 1 else 1 for model, kind, _ in plan.removal.profiles}
        self.danger = {
            model: (power, element)
            for model, kind, power, element in plan.danger.profiles
            if kind == 1
        }

    def actions(self, observation: FullGameObservation) -> npt.NDArray[np.int64]:
        decisions = []
        for i, lease in enumerate(observation.leases):
            legal = np.flatnonzero(observation.choice_mask[i]).tolist()
            if not legal:
                raise ValueError("full-game greedy policy requires an active observation")
            if len(legal) == 1:
                decisions.append(legal[0])
                continue
            context = observation.global_features[i, CONTEXT_START : len(GLOBAL_FIELDS)].astype(
                np.float64
            )
            decoded = np.sign(context) * np.expm1(np.abs(context) * np.log(100))
            players = observation.players[i]
            hp, mp, cp = (round(float(x) * self.cap) for x in players[0, HP : HP + 3])
            decision = _Decision(
                int(lease[4]),
                legal,
                observation.card_model_ids[i],
                observation.hand_features[i],
                players,
                decoded,
                int(lease[3]),
                hp,
                mp,
                cp,
            )
            choice = self._choose(decision)
            if choice not in legal:
                raise RuntimeError("full-game greedy policy produced an unavailable choice")
            decisions.append(choice)
        return np.asarray(decisions, dtype=np.int64)

    def _choose(self, d: _Decision) -> int:
        slots = {
            choice: int(d.models[choice - 1]) for choice in d.legal if 1 <= choice <= HAND_SLOTS
        }
        if d.phase == 1:
            return self._ready(d, slots)
        if d.phase == 2:
            return self._compose(d, slots)
        if d.phase == 3:
            return min(d.legal, key=lambda choice: self._target_hp(d, choice - DISCARD))
        if d.phase == 4:
            return self._defend(d, slots)
        if d.phase == 6:
            return self._trade(d, slots)
        if d.phase == 7:
            if 0 in d.legal:
                return 0
            return (
                min(slots, key=lambda choice: self._keep(slots[choice], d, choice))
                if slots
                else DISCARD
            )
        raise ValueError("unsupported full-game greedy phase")

    def _keep(self, model: int, d: _Decision, choice: int) -> float:
        if d.hand[choice - 1, 0] > 0:
            return -10
        return max(
            self._lead_score(model, d),
            0.65 * self.armor.get(model, 0),
            4 if model in self.specials else 0,
        )

    def _lead_score(self, model: int, d: _Decision) -> float:
        if model in self.utility:
            kind, value, cost = self.utility[model]
            gain = {
                1: min(value, self.cap - d.hp) * (1.25 if d.hp < 40 else 0.75),
                2: min(value, max(0, 25 - d.mp)) * 0.55,
                3: 2 * float(d.players[0, 5]) + 4 * float(d.players[0, 6:10].sum()),
                4: 16 * float(d.players[0, 5]) + 5 * float(d.players[0, 6:10].sum()),
                5: min(value, self.cap - d.cp) * 0.15,
                6: -10,
                7: -1,
                8: 13 if d.players[0, PLAYER_FEATURES.index("guardian_group_0")] else -2,
            }[kind]
            return gain - 0.35 * cost
        if model == 3:
            return 0.75 * min(15, self.cap - d.hp, d.cp + max(0, d.mp - 18)) if d.hp < 65 else -1
        if model in (4, 5):
            return 2 if model == 4 else 0.5
        base_power, element, cost = self.attacks.get(model, (0, 0, 0))
        power: float = base_power
        if model in self.complex:
            kind, value, element = self.complex[model]
            power = value * d.mp * 0.7 if kind == 1 else value * (2 if kind == 3 else 1)
        if model in self.danger:
            power, element = self.danger[model]
            power *= 0.25
        effect, _ = self.effects.get(model, (0, 0))
        bonus = {0: 0, 1: power * 0.35, 2: 4, 3: 4, 4: 7, 5: 8}.get(effect, 0)
        strength = power * (1.35 if element == 5 else 1.15 if element else 1)
        if element == 6 and power > 0:
            strength += 12
        return (strength + bonus + self.removal.get(model, 0)) * self.chances.get(
            model, 100
        ) / 100 - 0.35 * cost

    def _ready(self, d: _Decision, slots: dict[int, int]) -> int:
        has_reducer = any(model in self.reducers for model in d.models)
        scores = {}
        for choice, model in slots.items():
            cost = self.utility.get(model, (0, 0, 0))[2] + self.attacks.get(model, (0, 0, 0))[2]
            if cost <= d.mp or (model in self.miracles and has_reducer):
                scores[choice] = self._lead_score(model, d)
        if scores:
            best = max(scores, key=scores.__getitem__)
            if scores[best] > 2 or (0 not in d.legal and DISCARD not in d.legal):
                return best
        sacrifice = d.value("apocalypse", "active") and any(
            model in self.discardable and self._keep(int(model), d, i) <= 1
            for i, model in enumerate(d.models, start=1)
        )
        if DISCARD in d.legal and (sacrifice or (0 not in d.legal and not scores)):
            return DISCARD
        if 0 in d.legal:
            return 0
        if scores:
            return max(scores, key=scores.__getitem__)
        return DISCARD if DISCARD in d.legal else d.legal[0]

    def _waiver(self, d: _Decision, slots: dict[int, int], selected: list[int]) -> int | None:
        if selected and int(d.models[selected[-1] - 1]) in self.miracles:
            for choice, model in slots.items():
                if choice not in selected and model in self.reducers:
                    return choice
        return None

    def _compose(self, d: _Decision, slots: dict[int, int]) -> int:
        selected = d.selected("attack")
        cost = d.value("attack_selection", "displayed_mp_cost")
        waiver = self._waiver(d, slots, selected)
        if waiver is not None and (cost > d.mp or cost >= 3):
            return waiver
        if 0 not in d.legal:
            return next(choice for choice in reversed(selected) if choice in slots)
        power = d.value("attack_selection", "displayed_attack")
        element = d.value("attack_selection", "displayed_element")
        if d.value("utility_selection", "active") or len(selected) >= 5 or power >= 75:
            return 0
        options = {}
        for choice, model in slots.items():
            if choice in selected:
                continue
            if model in self.area_costs and not d.value("area", "active"):
                enemies = (
                    (d.players[:, ENEMY] > 0)
                    & ((d.players[:, VISIBLE] == 0) | (d.players[:, HP] > 0))
                ).sum()
                if enemies > 1 and cost + self.area_costs[model] <= d.mp and power >= 8:
                    options[choice] = power * (enemies - 1) - 4
            if model in self.boosts:
                gain, addition_element, extra, kind = self.boosts[model]
                if cost + extra <= d.mp:
                    options[choice] = (
                        (power if kind == 2 else gain)
                        + (4 if kind == 1 and element == 0 and addition_element else 0)
                        - 0.5 * extra
                    )
        best = max(options, key=options.__getitem__, default=0)
        return best if options.get(best, 0) >= 3 else 0

    def _target_hp(self, d: _Decision, seat: int) -> float:
        offset = (seat - d.actor) % self.players
        player = d.players[offset]
        return float(player[HP]) if player[VISIBLE] else 0.5

    def _defend(self, d: _Decision, slots: dict[int, int]) -> int:
        selected = d.selected("defense")
        cost = d.value("special_defense", "displayed_mp_cost")
        waiver = self._waiver(d, slots, selected)
        if waiver is not None and (cost > d.mp or cost >= 3):
            return waiver
        if 0 not in d.legal:
            return next(choice for choice in reversed(selected) if choice in slots)
        power = d.value("pending", "attack")
        remaining = max(0, power - d.value("pending", "displayed_selected_defense"))
        if d.value("special_defense", "displayed_response_kind") or (power > 0 and remaining == 0):
            return 0
        origin = d.value("pending", "origin")
        element = d.value("pending", "element")
        source = d.value("special_defense", "damage_source")
        source_enemy = source >= 0 and d.players[(source - d.actor) % self.players, ENEMY] > 0
        market = d.value("market", "kind")
        pressure = remaining or (0 if market == 2 else 6)
        options = {}
        for choice, model in slots.items():
            if choice in selected:
                continue
            kind, allowed_origin, neutral, extra = self.specials.get(model, (0, -1, 0, 0))
            if kind and allowed_origin in (-1, origin) and (not neutral or element == 0):
                # Reflection can retaliate. Bounce still carries a self/ally risk.
                if extra <= d.mp and (kind != 2 or source_enemy):
                    options[choice] = (
                        pressure * (1.45 if kind == 2 else 0.8 if kind == 3 else 1)
                        - 0.7 * extra
                        - 2,
                        0,
                    )
                continue
            armor = self.armor.get(model, 0)
            if remaining and armor > 0:
                options[choice] = (min(armor, remaining), -armor)
        best = max(options, key=options.__getitem__, default=0)
        return best if options.get(best, (0, 0))[0] > 0 else 0

    def _trade(self, d: _Decision, slots: dict[int, int]) -> int:
        mode = d.value("trade", "mode")
        if mode == 2:
            return 0 if 0 in d.legal else min(slots, key=lambda c: self._keep(slots[c], d, c))
        if mode == 3:
            price = d.value("market", "revealed_price")
            model = d.value("market", "revealed_item_model")
            return int(
                1 in d.legal and price <= d.cp and self._lead_score(model, d) > max(4, price * 0.5)
            )
        hp = d.value("trade", "preview_hp")
        edits = d.value("trade", "amount_edits")
        if hp < 80 and edits < 3:
            if 8 in d.legal:
                return 8
            if 4 in d.legal and d.value("trade", "preview_mp") > 24:
                return 4
        return 0
