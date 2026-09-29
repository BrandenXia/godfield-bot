"""Catalog-pinned hypotheses kept separate from observed replay and promotion."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot

PROVISIONAL_SOAP_RULESET_ID = "catalog-derived-selected-two-used-miracles-provisional-v1"


class ProvisionalRuleUnavailableError(RuntimeError):
    """The separately versioned provisional native component is unavailable."""


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
