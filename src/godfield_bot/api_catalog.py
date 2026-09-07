from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from godfield_bot.api_account import PYGODFIELD_REVISION

SUPPORTED_LANGUAGES = ("en", "ja", "fr", "ko", "pt", "ru", "zh-hans", "zh-hant")
CATALOG_URL = "https://godfield.net/i18n/{lang}.json"


class ApiCatalogError(RuntimeError):
    """Raised when the live item catalog cannot be captured safely."""


class ApiCatalogItem(BaseModel):
    model_id: int = Field(gt=0)
    raw: dict[str, Any]


def api_catalog_digest(items: Sequence[ApiCatalogItem]) -> str:
    canonical = json.dumps(
        [item.model_dump(mode="json") for item in items],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class ApiCatalogSnapshot(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    source_url: str
    language: str
    upstream_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_items: int = Field(ge=0)
    items: tuple[ApiCatalogItem, ...]

    @model_validator(mode="after")
    def verify_catalog_integrity(self) -> ApiCatalogSnapshot:
        expected_ids = list(range(1, len(self.items) + 1))
        actual_ids = [item.model_id for item in self.items]
        if actual_ids != expected_ids:
            raise ValueError("API catalog model IDs must be contiguous and ordered")
        if self.total_items != len(self.items):
            raise ValueError("API catalog total does not match its item records")
        if self.content_sha256 != api_catalog_digest(self.items):
            raise ValueError("API catalog content checksum does not match its item records")
        return self


def fetch_api_catalog_snapshot(
    *,
    language: str = "en",
    timeout_seconds: float = 20,
) -> ApiCatalogSnapshot:
    """Fetch the live game catalog through pygodfield's public catalog API."""

    if language not in SUPPORTED_LANGUAGES:
        raise ApiCatalogError(f"unsupported catalog language: {language}")
    if timeout_seconds <= 0:
        raise ApiCatalogError("catalog timeout must be positive")

    from godfield import GodfieldError, ItemCatalog  # type: ignore[import-untyped]

    try:
        catalog = ItemCatalog.fetch(lang=language, timeout=timeout_seconds)
        items = tuple(
            ApiCatalogItem(model_id=model.model_id, raw=dict(model.raw)) for model in catalog
        )
    except (GodfieldError, TypeError, ValueError) as error:
        raise ApiCatalogError("pygodfield could not fetch a valid live item catalog") from error

    return ApiCatalogSnapshot(
        observed_at=datetime.now(UTC),
        source_url=CATALOG_URL.format(lang=language),
        language=language,
        upstream_revision=PYGODFIELD_REVISION,
        content_sha256=api_catalog_digest(items),
        total_items=len(items),
        items=items,
    )


def write_api_catalog_snapshot(snapshot: ApiCatalogSnapshot, output: Path) -> None:
    """Write a generated catalog snapshot atomically."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def read_api_catalog_snapshot(path: Path) -> ApiCatalogSnapshot:
    try:
        return ApiCatalogSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ApiCatalogError("the API catalog snapshot is unreadable or invalid") from error


def item_catalog_from_snapshot(snapshot: ApiCatalogSnapshot) -> object:
    """Build pygodfield's catalog without an unversioned network or home-cache read."""

    from godfield import ItemCatalog

    return ItemCatalog(
        [item.raw for item in snapshot.items],
        lang=snapshot.language,
    )
