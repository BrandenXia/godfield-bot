"""Checked held-card capabilities, not a permission to omit incompatible effects."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

if TYPE_CHECKING:
    from godfield_bot.full_game import FullGamePlan

ROLE_FIELDS: Final = (
    "attack-leader=1",
    "utility-leader=2",
    "attack-addition=4",
    "numeric-defense=8",
    "special-defense=16",
    "element-filter=32",
    "cost-reducer=64",
    "passive-ownership=128",
    "trade=256",
)
FULL_GAME_ROLES_SHA256: Final = "2ba9b5958eac738e74ba303f836bc1d01e696c073dde2a1da59b73743350807c"


class FullGameRoleManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    role_fields: tuple[str, ...] = ROLE_FIELDS
    model_roles: tuple[tuple[StrictInt, StrictInt], ...]
    profile_sha256: Literal["2ba9b5958eac738e74ba303f836bc1d01e696c073dde2a1da59b73743350807c"] = (
        FULL_GAME_ROLES_SHA256
    )

    @model_validator(mode="after")
    def complete_checked_roles(self) -> FullGameRoleManifest:
        digest = hashlib.sha256(
            json.dumps(self.model_roles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.role_fields != ROLE_FIELDS
            or tuple(m for m, _ in self.model_roles) != tuple(range(3, 240))
            or any(bits < 1 or bits > 511 for _, bits in self.model_roles)
            or self.profile_sha256 != digest
        ):
            raise ValueError("full-game role manifest must cover all237 held models exactly")
        return self


def build_full_game_role_manifest(plan: FullGamePlan) -> FullGameRoleManifest:
    roles = {model: 0 for model, _ in plan.inventory.profiles}

    def add(models: set[int], bit: int) -> None:
        for model in models:
            roles[model] |= bit

    add(
        {r[0] for r in plan.combat.attack_profiles}
        | {r[0] for r in plan.combat.boost_profiles if r[5]}
        | {r[0] for r in plan.removal.profiles}
        | {r[0] for r in plan.costs.profiles if r[1] == 1}
        | {r[0] for r in plan.weapons.profiles}
        | {r[0] for r in plan.danger.profiles if r[1] == 1}
        | {r[0] for r in plan.attack_family.profiles},
        1,
    )
    add(
        {r[0] for r in plan.effect_profiles}
        | {r[0] for r in plan.guardians.summon_profiles}
        | set(plan.phenomena.fate_model_ids),
        2,
    )
    add({r[0] for r in plan.combat.boost_profiles} | {r[0] for r in plan.area.profiles}, 4)
    add(
        {r[0] for r in plan.combat.armor_profiles}
        | {r[0] for r in plan.dream_defense.profiles}
        | {r[0] for r in plan.costs.profiles if r[1] == 2},
        8,
    )
    add({r[0] for r in plan.combat.special_profiles}, 16)
    add({r[0] for r in plan.combat.defense_effect_profiles if r[1] == 5}, 32)
    add({r[0] for r in plan.costs.profiles}, 64)
    add(
        {r[0] for r in plan.passives.profiles}
        | {r[0] for r in plan.attack_family.profiles}
        | {r[0] for r in plan.danger.profiles if r[1] == 2},
        128,
    )
    add(set(plan.trade.exchange_model_ids) | {4, 5}, 256)
    profiles = tuple(sorted(roles.items()))
    return FullGameRoleManifest(model_roles=profiles)
