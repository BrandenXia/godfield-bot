"""Versioned public properties derived solely from pinned displayed-card profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from godfield_bot.full_game import FullGameMetadata

CARD_PROPERTY_FIELDS: Final = (
    "fixed_attack_log",
    "mp_attack_coefficient_log",
    "defense_log",
    "attack_mp_cost_log",
    "defense_mp_cost_log",
    "utility_mp_cost_log",
    "addition_mp_cost_log",
    "utility_value_log",
    "price_log",
    "hit_rate_fraction",
    "attack_strikes_fraction",
    *(f"element_{i}" for i in range(7)),
    *(f"role_bit_{i}" for i in range(9)),
    *(f"utility_kind_{i}" for i in range(1, 9)),
    "block",
    "reflect",
    "bounce",
    "set_element",
    "double_attack",
    "reusable_miracle",
    "fate",
)


def public_card_property_table(metadata: FullGameMetadata) -> npt.NDArray[np.float32]:
    """Index by a public displayed ID, never by a hidden actual inventory row."""
    import numpy as np

    table = np.zeros((297, len(CARD_PROPERTY_FIELDS)), dtype=np.float64)
    indices = {name: i for i, name in enumerate(CARD_PROPERTY_FIELDS)}
    plan = metadata.plan

    def put(model: int, **values: float) -> None:
        for name, value in values.items():
            table[model, indices[name]] = value

    def element(model: int, value: int) -> None:
        table[model, indices["element_0"] : indices["element_6"] + 1] = 0
        table[model, indices[f"element_{value}"]] = 1

    for model, roles in metadata.roles.model_roles:
        for bit in range(9):
            put(model, **{f"role_bit_{bit}": float(bool(roles & (1 << bit)))})
        if roles & (1 | 4 | 8 | 16):
            put(model, hit_rate_fraction=1)
        if roles & 1:
            put(model, attack_strikes_fraction=0.5)
    for model, category in plan.inventory.profiles:
        put(model, reusable_miracle=float(category == 4))
    for model, power, elt, _, cost in plan.combat.attack_profiles:
        put(model, fixed_attack_log=power, attack_mp_cost_log=cost)
        element(model, elt)
    for model, defense, elt, _, cost in plan.combat.armor_profiles:
        put(model, defense_log=defense, defense_mp_cost_log=cost)
        if not table[model, indices["element_0"] : indices["element_6"] + 1].any():
            element(model, elt)
    for model, power, elt, cost, kind, can_lead in plan.combat.boost_profiles:
        put(
            model,
            fixed_attack_log=power,
            addition_mp_cost_log=cost,
            set_element=float(kind == 1),
            double_attack=float(kind == 2),
        )
        if can_lead:
            put(model, attack_mp_cost_log=cost)
        element(model, elt)
    for model, kind, _, _, cost in plan.combat.special_profiles:
        put(model, defense_mp_cost_log=cost, **{("block", "reflect", "bounce")[kind - 1]: 1})
    for model, kind, value, cost in plan.effect_profiles:
        put(model, utility_value_log=value, utility_mp_cost_log=cost, **{f"utility_kind_{kind}": 1})
    for model, cost in plan.guardians.summon_profiles:
        put(model, utility_mp_cost_log=cost, utility_kind_8=1)
    for model, _, power, defense in plan.costs.profiles:
        if power:
            put(model, fixed_attack_log=power)
            element(model, 0)
        if defense:
            put(model, defense_log=defense)
    for model, defense, elt, _ in plan.dream_defense.profiles:
        put(model, defense_log=defense)
        element(model, elt)
    for model, kind, value, elt in plan.weapons.profiles:
        if kind == 1:
            put(model, fixed_attack_log=0, mp_attack_coefficient_log=value)
        else:
            put(model, fixed_attack_log=value, attack_strikes_fraction=1 if kind == 3 else 0.5)
        element(model, elt)
    for model, kind, power, elt in plan.danger.profiles:
        if kind == 1:
            put(model, fixed_attack_log=power)
            element(model, elt)
    for model, power, rate, _, _, elt in plan.attack_family.profiles:
        put(model, fixed_attack_log=power, hit_rate_fraction=rate / 100)
        element(model, elt)
    for model, cost in plan.area.profiles:
        put(model, addition_mp_cost_log=cost)
    for model, rate in plan.combat.chance_profiles:
        put(model, hit_rate_fraction=rate / 100)
    for model, _, price in plan.trade.price_profiles:
        put(model, price_log=price)
    for model in plan.phenomena.fate_model_ids:
        put(model, fate=1)
    for i, name in enumerate(CARD_PROPERTY_FIELDS):
        if name.endswith("_log"):
            table[:, i] = np.sign(table[:, i]) * np.log1p(np.abs(table[:, i])) / np.log(100)
    result = table.astype(np.float32)
    result.setflags(write=False)
    return result
