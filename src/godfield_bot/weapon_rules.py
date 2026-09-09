import re

WeaponAttackRule = tuple[str, float] | tuple[str, float, tuple[str, ...]]

DYNAMIC_MP_ATTACK_PATTERN = re.compile("^ATK\\{(\\d+)\N{MULTIPLICATION SIGN}MP\\}$")


def resolved_weapon_attack_displays(rule: WeaponAttackRule, *, mp: int) -> tuple[str, ...]:
    """Resolve a Bible attack expression to every exact display valid at this state."""

    dynamic = DYNAMIC_MP_ATTACK_PATTERN.fullmatch(rule[0])
    primary = rule[0] if dynamic is None else f"ATK{int(dynamic.group(1)) * mp}"
    alternatives = rule[2] if len(rule) == 3 else ()
    return (primary, *alternatives)


def weapon_attack_value(rule: WeaponAttackRule, *, mp: int) -> float:
    """Return state-aware attack value for deterministic heuristic ranking."""

    dynamic = DYNAMIC_MP_ATTACK_PATTERN.fullmatch(rule[0])
    if dynamic is None:
        return rule[1]
    return float(int(dynamic.group(1)) * mp)
