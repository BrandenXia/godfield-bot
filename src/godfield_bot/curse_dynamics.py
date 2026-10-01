"""Source-pinned portable curse kernel; not a full-game policy environment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError
from godfield_bot.reference import verified_illness_cure_miracles, verified_illness_cure_sundries

if TYPE_CHECKING:
    from godfield_sim import CurseDynamicsBatch

CURSE_DYNAMICS_RULESET_ID: Final = "caller-driven-documented-curse-dynamics-provisional-v1"
CURSE_PROFILE_SHA256: Final = "916cfa809ee2e607c8cedafed77604a5d98c82eaf66949936fae517a7b8df38b"
_ILLNESS_PROFILES = ((0, 0, 0), (1, -1, 2), (2, -2, 3), (3, -5, 4), (4, 5, 5))
_CURSE_BITS = (("fog", 1), ("dream", 2), ("flash", 4), ("darkcloud", 8))
_CURE_PROFILES = ((199, 1, 0, 0), (200, 2, 0, 0), (237, 1, 1, 2), (238, 2, 1, 5))
_SOURCE_CURSES = (
    "Cold",
    "1 damage per turn",
    "(Fever if worsened)",
    "Fever",
    "2 damage per turn",
    "(Hell if worsened)",
    "Hell",
    "5 damage per turn",
    "(Heaven if worsened)",
    "Heaven",
    "HP+5 per turn",
    "(HP0 if worsened)",
    "Fog",
    "Surroundings",
    "become hidden",
    "Flash",
    "Only one artifact can",
    "be used for defense",
    "Dream",
    "Given artifacts look",
    "false by 50% chance",
    "Dark Cloud",
    "Received %ATK attacks",
    "hit certainly",
    "Diseases get worse naturally per turn by 5% chance.",
    "Diseases get worse when catched another disease.",
    "When using artifacts to an enemy from Fog, the target is selected at random.",
)


class CurseDynamicsPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["caller-driven-documented-curse-dynamics-provisional-v1"] = (
        CURSE_DYNAMICS_RULESET_ID
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["916cfa809ee2e607c8cedafed77604a5d98c82eaf66949936fae517a7b8df38b"] = (
        CURSE_PROFILE_SHA256
    )
    illness_profiles: tuple[tuple[int, int, int], ...] = _ILLNESS_PROFILES
    illness_fields: tuple[Literal["stage", "periodic_hp_change", "next_stage_or_death_5"], ...] = (
        "stage",
        "periodic_hp_change",
        "next_stage_or_death_5",
    )
    curse_bits: tuple[tuple[str, int], ...] = _CURSE_BITS
    cure_profiles: tuple[tuple[int, int, int, int], ...] = _CURE_PROFILES
    cure_fields: tuple[Literal["model_id", "scope", "reusable", "mp_cost"], ...] = (
        "model_id",
        "scope",
        "reusable",
        "mp_cost",
    )
    documented_mild_mask: Literal[5] = 5
    documented_mild_illness_stages: tuple[Literal[1, 2], ...] = (1, 2)
    progression_percent: Literal[5] = 5
    hp_cap: Literal[100] = 100
    source_evidence: Literal["pinned-bible-help-and-api-catalog"] = (
        "pinned-bible-help-and-api-catalog"
    )
    scheduling: Literal["caller-completes-owner-turn-provisional"] = (
        "caller-completes-owner-turn-provisional"
    )
    ordering: Literal["periodic-effect-then-worsening-survivors-provisional"] = (
        "periodic-effect-then-worsening-survivors-provisional"
    )
    randomness: Literal["caller-ticket-0-through-99-worsens-below-5"] = (
        "caller-ticket-0-through-99-worsens-below-5"
    )
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_rules(self) -> CurseDynamicsPlan:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "illness_profiles": self.illness_profiles,
                    "curse_bits": self.curse_bits,
                    "cure_profiles": self.cure_profiles,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or digest != self.profile_sha256
            or self.illness_fields != ("stage", "periodic_hp_change", "next_stage_or_death_5")
            or self.cure_fields != ("model_id", "scope", "reusable", "mp_cost")
            or self.documented_mild_illness_stages != (1, 2)
        ):
            raise ValueError("curse dynamics requires the pinned documented profile")
        return self


def build_curse_dynamics_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> CurseDynamicsPlan:
    """Pin disease amounts/chance and documented cure scopes, not event timing."""
    if bible.reference_sections.get("curses") != _SOURCE_CURSES:
        raise ValueError("pinned curse help differs")
    sundries = verified_illness_cure_sundries(bible)
    miracles = verified_illness_cure_miracles(bible)
    if sundries != {"smile-shell": False, "heart-shell": True} or miracles != {
        "tone": (2, False),
        "song": (5, True),
    }:
        raise ValueError("pinned four-card cure Bible profile differs")
    profiles = []
    for item in catalog.items:
        asset = item.raw.get("imageName")
        if asset not in (*sundries, *miracles):
            continue
        assert isinstance(asset, str)
        reusable = int(asset in miracles)
        cost, cure_all = miracles[asset] if reusable else (0, sundries[asset])
        if (
            item.raw.get("category") != ("miracles" if reusable else "sundries")
            or item.raw.get("ability") != ("removeAllCurses" if cure_all else "removeMildCurses")
            or type(item.raw.get("cost", 0)) is not int
            or item.raw.get("cost", 0) != cost
            or any(item.raw.get(field) is not None for field in ("atk", "def", "element", "curse"))
        ):
            raise ValueError("pinned four-card API cure profile differs")
        profiles.append((item.model_id, 2 if cure_all else 1, reusable, cost))
    return CurseDynamicsPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        cure_profiles=tuple(profiles),
    )


class CurseDynamicsMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    plan: CurseDynamicsPlan
    batch_size: int = Field(ge=1, le=1_000_000, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    initial_hp: int = Field(ge=1, le=100, strict=True)
    state_fields: tuple[str, ...] = ("hp", "illness_stage", "curse_mask", "completed_turn_ticks")
    transition_fields: tuple[str, ...] = (
        "operation",
        "previous_hp",
        "previous_illness",
        "previous_mask",
        "hp_delta",
        "newly_died",
    )
    player_roles: Literal["caller-selected-owner-no-team-or-opponent-policy"] = (
        "caller-selected-owner-no-team-or-opponent-policy"
    )
    snapshot_boundary: Literal["diagnostic-resources-status-not-policy-observation"] = (
        "diagnostic-resources-status-not-policy-observation"
    )
    ticks: Literal["monotonic-owner-count-checked-before-whole-batch-mutation"] = (
        "monotonic-owner-count-checked-before-whole-batch-mutation"
    )
    item_legality_and_costs_implemented: Literal[False] = False
    non_disease_effects_implemented: Literal[False] = False
    policy_projection_implemented: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def bounded_and_pinned_fields(self) -> CurseDynamicsMetadata:
        if (
            self.batch_size * self.player_count > 2_000_000
            or self.state_fields != ("hp", "illness_stage", "curse_mask", "completed_turn_ticks")
            or self.transition_fields
            != (
                "operation",
                "previous_hp",
                "previous_illness",
                "previous_mask",
                "hp_delta",
                "newly_died",
            )
        ):
            raise ValueError("curse dynamics state contract or capacity differs")
        return self


@dataclass(frozen=True)
class ProvisionalCurseDynamicsBatch:
    batch: CurseDynamicsBatch
    metadata: CurseDynamicsMetadata


def create_provisional_curse_dynamics_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    initial_hp: int = 40,
) -> ProvisionalCurseDynamicsBatch:
    plan = build_curse_dynamics_plan(
        read_api_catalog_snapshot(catalog_path),
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    metadata = CurseDynamicsMetadata(
        plan=plan, batch_size=batch_size, player_count=player_count, initial_hp=initial_hp
    )
    try:
        import godfield_sim as native
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "curse dynamics requires the native simulation extra"
        ) from None
    if (
        getattr(native, "CURSE_DYNAMICS_SCHEMA_VERSION", None) != 1
        or getattr(native, "CURSE_DYNAMICS_RULESET_ID", None) != CURSE_DYNAMICS_RULESET_ID
        or not hasattr(native, "CurseDynamicsBatch")
        or tuple(
            getattr(native, name, None)
            for name in (
                "CURSE_FOG_BIT",
                "CURSE_DREAM_BIT",
                "CURSE_FLASH_BIT",
                "CURSE_DARK_CLOUD_BIT",
            )
        )
        != (1, 2, 4, 8)
    ):
        raise ProvisionalRuleUnavailableError("native curse dynamics contract differs")
    return ProvisionalCurseDynamicsBatch(
        native.CurseDynamicsBatch(batch_size, player_count, initial_hp), metadata
    )
