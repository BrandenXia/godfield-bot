"""Fixed ordinary combat profiles shared with the source-checked guardian slice."""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_batch import _guardian_card_profiles

FULL_GAME_COMBAT_SHA256: Final = "cdb29067a11535efeb6884b0fdee9968707c47e1cbf0a3d6e14adbd33bf341dd"


class FullGameCombatPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    profile_sha256: Literal["cdb29067a11535efeb6884b0fdee9968707c47e1cbf0a3d6e14adbd33bf341dd"] = (
        FULL_GAME_COMBAT_SHA256
    )
    attack_profiles: tuple[tuple[int, int, int, int, int], ...]
    armor_profiles: tuple[tuple[int, int, int, int, int], ...]
    attack_fields: tuple[str, ...] = ("model_id", "attack", "element", "origin", "mp_cost")
    armor_fields: tuple[str, ...] = ("model_id", "defense", "element", "kind", "mp_cost")
    ordinary_weapon_count: Literal[39] = 39
    attack_miracle_count: Literal[6] = 6
    ordinary_armor_count: Literal[47] = 47
    combat_effect_count: Literal[92] = 92
    timing_and_hidden_resolution_verified: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> FullGameCombatPlan:
        digest = hashlib.sha256(
            json.dumps((self.attack_profiles, self.armor_profiles), separators=(",", ":")).encode()
        ).hexdigest()
        if (
            digest != self.profile_sha256
            or self.attack_fields != ("model_id", "attack", "element", "origin", "mp_cost")
            or self.armor_fields != ("model_id", "defense", "element", "kind", "mp_cost")
        ):
            raise ValueError("full-game ordinary combat profiles differ from pinned sources")
        return self


def build_full_game_combat_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameCombatPlan:
    # Reuse exact API/Bible cross-checks, not the guardian scheduler or its state.
    defenses, attacks = _guardian_card_profiles(catalog, bible)
    return FullGameCombatPlan(
        attack_profiles=tuple(sorted(attacks)),
        armor_profiles=tuple(sorted(row for row in defenses if row[3] == 0)),
    )
