"""Catalog-pinned hypotheses kept separate from observed replay and promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot

PROVISIONAL_SOAP_RULESET_ID = "catalog-derived-selected-two-used-miracles-provisional-v1"
PROVISIONAL_GUARDIAN_RULESET_ID = "catalog-derived-guardian-weight-ticket-provisional-v1"
PROVISIONAL_STRENGTH_POWDER_RULESET_PREFIX = "provisional-strength-powder-v1-"
_PINNED_CATALOG_PATH = (
    Path(__file__).parents[2] / "data/snapshots/2026-09-21/api-catalog-en.json"
)


class ProvisionalRuleUnavailableError(RuntimeError):
    """The separately versioned provisional native component is unavailable."""


class ProvisionalGuardianPlan(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["catalog-derived-guardian-weight-ticket-v1"] = (
        "catalog-derived-guardian-weight-ticket-v1"
    )
    status: Literal["provisional-unvalidated"] = "provisional-unvalidated"
    native_ruleset_id: str = PROVISIONAL_GUARDIAN_RULESET_ID
    native_schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = ACQUISITION_REVIEWED_CLIENT_SHA256
    group_names: tuple[str, ...]
    weighted_profiles: tuple[tuple[int, int, int], ...]
    excluded_special_model_ids: tuple[int, ...]
    ticket_interpretation: Literal["hypothetical-relative-weights"] = (
        "hypothetical-relative-weights"
    )
    official_weight_selection_traces: Literal[0] = 0
    effect_resolution_implemented: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False


def build_provisional_guardian_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> ProvisionalGuardianPlan:
    """Pin a proposed ticket map, not guardian activation or combat behavior."""

    if catalog.content_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256:
        raise ValueError("provisional guardian plan requires the pinned reviewed catalog")
    if bible.client.sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256:
        raise ValueError("provisional guardian plan requires the pinned reviewed Bible")
    guardian_bible = bible.catalog.get("guardians")
    guardian_items = [item for item in catalog.items if item.raw.get("category") == "guardians"]
    if guardian_bible is None or len(guardian_items) != 42 or len(guardian_bible.items) != 42:
        raise ValueError("pinned guardian catalog must contain 42 matching artifacts")
    if {item.asset for item in guardian_bible.items} != {
        item.raw.get("imageName") for item in guardian_items
    }:
        raise ValueError("pinned guardian Bible and API model names differ")

    group_names = (
        "mars",
        "mercury",
        "jupiter",
        "saturn",
        "uranus",
        "pluto",
        "neptune",
        "venus",
    )
    profiles: list[tuple[int, int, int]] = []
    for group_index, name in enumerate(group_names):
        members = [item for item in guardian_items if item.raw.get("guardian") == name]
        if len(members) != 5:
            raise ValueError(f"pinned guardian group {name} must have five effects")
        members.sort(key=lambda item: item.model_id)
        rates = tuple(item.raw.get("guardianAttackRate") for item in members)
        if rates != (6, 5, 4, 3, 2):
            raise ValueError(f"pinned guardian group {name} weights differ")
        profiles.extend(
            (group_index, item.model_id, rate)
            for item, rate in zip(members, (6, 5, 4, 3, 2), strict=True)
        )
    specials = [
        item
        for item in guardian_items
        if item.raw.get("guardian") not in group_names
    ]
    if {(item.raw.get("guardian"), item.model_id) for item in specials} != {
        ("earth", 285),
        ("moon", 286),
    } or any(item.raw.get("guardianAttackRate") is not None for item in specials):
        raise ValueError("pinned special guardians differ from reviewed catalog")
    try:
        import godfield_sim as native
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "provisional guardian picker requires the native simulation extra"
        ) from None
    if (
        getattr(native, "PROVISIONAL_GUARDIAN_SCHEMA_VERSION", None) != 1
        or getattr(native, "PROVISIONAL_GUARDIAN_RULESET_ID", None)
        != PROVISIONAL_GUARDIAN_RULESET_ID
        or not hasattr(native, "ProvisionalGuardianPicker")
    ):
        raise ProvisionalRuleUnavailableError("provisional guardian native identity differs")
    return ProvisionalGuardianPlan(
        catalog_sha256=catalog.content_sha256,
        group_names=group_names,
        weighted_profiles=tuple(profiles),
        excluded_special_model_ids=(285, 286),
    )


def provisional_strength_powder_boost(bible: BibleSnapshot) -> int:
    """Return a pinned, unvalidated booster value for opt-in local training."""

    if bible.client.sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256:
        raise ValueError("provisional Strength Powder requires the pinned reviewed Bible")
    sundries = bible.catalog.get("sundries")
    powder_bible = (
        next((item for item in sundries.items if item.asset == "strength-powder"), None)
        if sundries
        else None
    )
    if powder_bible is None or powder_bible.detail != (
        "Strength Powder",
        "+ATK10",
        "$15",
        "Gift Rate: 2/500",
    ):
        raise ValueError("pinned Bible does not define the reviewed Strength Powder boost")
    catalog = read_api_catalog_snapshot(_PINNED_CATALOG_PATH)
    if catalog.content_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256:
        raise ValueError("provisional Strength Powder requires the pinned reviewed catalog")
    powder = next((item for item in catalog.items if item.model_id == 203), None)
    if powder is None or not (
        powder.raw.get("category") == "sundries"
        and powder.raw.get("imageName") == "strength-powder"
        and powder.raw.get("atk") == 10
        and powder.raw.get("isPlusAtk") is True
        and powder.raw.get("giftRate") == 2
    ):
        raise ValueError("pinned catalog does not define the reviewed Strength Powder boost")
    return 10


class ProvisionalSoapPlan(BaseModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["catalog-derived-provisional-soap-plan-v1"] = (
        "catalog-derived-provisional-soap-plan-v1"
    )
    status: Literal["provisional-unvalidated"] = "provisional-unvalidated"
    native_ruleset_id: str = PROVISIONAL_SOAP_RULESET_ID
    native_schema_version: Literal[1] = 1
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = ACQUISITION_REVIEWED_CLIENT_SHA256
    soap_model_id: Literal[206] = 206
    action: Literal["removeUsedMiracles"] = "removeUsedMiracles"
    selected_item_count: Literal[2] = 2
    selection_policy: Literal["caller-provided-only"] = "caller-provided-only"
    miracle_model_ids: tuple[int, ...]
    official_event_observation_count: Literal[0] = 0
    complete_game_replay: Literal[False] = False
    local_training_eligible: Literal[False] = False
    official_validation_eligible: Literal[False] = False
    promotion_eligible: Literal[False] = False


def build_provisional_soap_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> ProvisionalSoapPlan:
    if catalog.content_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256:
        raise ValueError("provisional Soap plan requires the pinned reviewed catalog")
    sundries = bible.catalog.get("sundries")
    soap_bible = (
        next((item for item in sundries.items if item.asset == "goddess-s-soap"), None)
        if sundries
        else None
    )
    if (
        bible.client.sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
        or soap_bible is None
        or soap_bible.detail[:3] != ("Goddess's Soap", "Wash away 2", "performed miracles")
    ):
        raise ValueError("provisional Soap plan requires the pinned reviewed Bible rule")
    soap = next((item for item in catalog.items if item.model_id == 206), None)
    if (
        soap is None
        or soap.raw.get("category") != "sundries"
        or soap.raw.get("ability") != "removeUsedMiracles"
    ):
        raise ValueError("pinned catalog does not define the reviewed Soap ability")
    miracles = tuple(
        item.model_id for item in catalog.items if item.raw.get("category") == "miracles"
    )
    if len(miracles) != 30:
        raise ValueError("pinned catalog miracle category differs")
    try:
        import godfield_sim as native
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "provisional Soap requires the native simulation extra"
        ) from None
    if (
        getattr(native, "PROVISIONAL_SOAP_SCHEMA_VERSION", None) != 1
        or getattr(native, "PROVISIONAL_SOAP_RULESET_ID", None) != PROVISIONAL_SOAP_RULESET_ID
        or not hasattr(native, "ProvisionalSoapProjection")
    ):
        raise ProvisionalRuleUnavailableError("provisional Soap native identity differs")
    return ProvisionalSoapPlan(
        catalog_sha256=catalog.content_sha256,
        miracle_model_ids=miracles,
    )
