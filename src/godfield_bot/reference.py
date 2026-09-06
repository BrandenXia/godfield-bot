import hashlib
import os
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import structlog
from playwright.async_api import BrowserContext, Page, async_playwright

from godfield_bot.browser.controls import BrowserContractError, click_text_control
from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)

log = structlog.get_logger()

BASE_URL = "https://godfield.net/"
BUNDLE_URL = "https://godfield.net/main.dart.js"

ITEM_CATEGORIES = (
    "Weapons",
    "Armor",
    "Sundries",
    "Miracles",
    "Devils",
    "Guardians",
    "Phenomena",
)

REFERENCE_SENTINELS = {
    "Elements": "Attacks of Non-element",
    "Curses": "Cold",
    "Trade": "Weapons, Sun Amulet",
}

IGNORED_REFERENCE_LINES = {
    "Bible",
    "Settings",
    "Prophet Name",
    "Genesis",
    *ITEM_CATEGORIES,
    *REFERENCE_SENTINELS,
}


class ReferenceExtractionError(BrowserContractError):
    """Raised when the public Bible no longer satisfies its selector contract."""


def longest_common_prefix(rows: Sequence[Sequence[str]]) -> tuple[str, ...]:
    if not rows:
        return ()
    prefix: list[str] = []
    for values in zip(*rows, strict=False):
        if len(set(values)) != 1:
            break
        prefix.append(values[0])
    return tuple(prefix)


def without_prefix(values: Sequence[str], prefix: Sequence[str]) -> tuple[str, ...]:
    return tuple(values[len(prefix) :])


def _clean_lines(text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in text.splitlines() if line.strip())


async def _fingerprint_client(context: BrowserContext) -> ClientFingerprint:
    response = await context.request.get(BUNDLE_URL, fail_on_status_code=True)
    body = await response.body()
    headers = response.headers
    return ClientFingerprint(
        url=BUNDLE_URL,
        sha256=hashlib.sha256(body).hexdigest(),
        etag=headers.get("etag", "").strip('"') or None,
        last_modified=headers.get("last-modified"),
    )


async def _open_bible(page: Page, *, timeout_ms: float) -> None:
    await page.goto(f"{BASE_URL}?lang=en", wait_until="domcontentloaded", timeout=timeout_ms)
    await page.locator('input[type="text"]').wait_for(state="visible", timeout=timeout_ms)
    await click_text_control(page, "Bible")
    await page.get_by_text("Elements", exact=True).wait_for(state="visible", timeout=timeout_ms)


async def _extract_reference_sections(
    page: Page, *, timeout_ms: float
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for section, sentinel in REFERENCE_SENTINELS.items():
        await click_text_control(page, section)
        await page.get_by_text(sentinel, exact=False).first.wait_for(
            state="visible", timeout=timeout_ms
        )
        lines = _clean_lines(await page.locator("body").inner_text())
        result[section.lower()] = tuple(
            line for line in lines if line not in IGNORED_REFERENCE_LINES
        )
    return result


async def _artifact_sources(page: Page, category_slug: str) -> tuple[str, ...]:
    locator = page.locator(f'img[src^="/images/items/{category_slug}/"]')
    sources: list[str] = []
    for index in range(await locator.count()):
        source = await locator.nth(index).get_attribute("src")
        if source and source not in sources:
            sources.append(source)
    return tuple(sources)


async def _selected_detail(page: Page, image_path: str) -> tuple[str, ...]:
    text: str = await page.evaluate(
        """
        (wanted) => {
          const images = [...document.querySelectorAll(`img[src="${wanted}"]`)];
          const detailImage = images.find((image) => image.parentElement?.querySelector('span'));
          const panel = detailImage?.parentElement?.parentElement;
          return panel?.innerText ?? '';
        }
        """,
        image_path,
    )
    return _clean_lines(text)


async def _extract_category(page: Page, category: str, *, timeout_ms: float) -> ArtifactCategory:
    category_slug = category.lower()
    await click_text_control(page, category)
    first_image = page.locator(f'img[src^="/images/items/{category_slug}/"]').first
    await first_image.wait_for(state="attached", timeout=timeout_ms)
    sources = await _artifact_sources(page, category_slug)
    if not sources:
        raise ReferenceExtractionError(f"no artifact images found for {category}")

    raw_items: list[tuple[str, tuple[str, ...]]] = []
    for image_path in sources:
        target = page.locator(f'img[src="{image_path}"] + div')
        if await target.count() != 1:
            raise ReferenceExtractionError(
                f"expected one click target for {image_path}, found {await target.count()}"
            )
        await target.click(timeout=timeout_ms)
        detail = await _selected_detail(page, image_path)
        if not detail:
            raise ReferenceExtractionError(f"empty detail panel for {image_path}")
        raw_items.append((image_path, detail))

    notes = longest_common_prefix([detail for _, detail in raw_items])
    items = tuple(
        ArtifactRecord(
            asset=Path(image_path).stem,
            image_path=image_path,
            detail=without_prefix(detail, notes),
        )
        for image_path, detail in raw_items
    )
    log.info("reference_category_extracted", category=category_slug, count=len(items))
    return ArtifactCategory(notes=notes, items=items)


async def refresh_bible(*, headed: bool, timeout_seconds: float) -> BibleSnapshot:
    """Extract the live public Bible through the same browser UI a player sees."""

    timeout_ms = timeout_seconds * 1_000
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed)
        context = await browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        try:
            client = await _fingerprint_client(context)
            page = await context.new_page()
            await _open_bible(page, timeout_ms=timeout_ms)
            reference_sections = await _extract_reference_sections(page, timeout_ms=timeout_ms)
            catalog = {
                category.lower(): await _extract_category(page, category, timeout_ms=timeout_ms)
                for category in ITEM_CATEGORIES
            }
        finally:
            await context.close()
            await browser.close()

    total = sum(len(category.items) for category in catalog.values())
    return BibleSnapshot(
        observed_at=datetime.now(UTC),
        source_url=BASE_URL,
        language="en",
        client=client,
        reference_sections=reference_sections,
        catalog=catalog,
        total_artifacts=total,
    )


def write_snapshot(snapshot: BibleSnapshot, output: Path) -> None:
    """Write a generated snapshot atomically."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)


def category_counts(snapshot: BibleSnapshot) -> dict[str, int]:
    return {name: len(category.items) for name, category in snapshot.catalog.items()}


def ensure_expected_counts(actual: dict[str, int], expected: Iterable[tuple[str, int]]) -> None:
    for category, count in expected:
        if actual.get(category) != count:
            raise ReferenceExtractionError(
                f"{category} count drift: expected {count}, observed {actual.get(category)}"
            )
