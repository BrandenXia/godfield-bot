import hashlib
import os
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import structlog
from playwright.async_api import BrowserContext, Page, async_playwright

from godfield_bot.browser.controls import BrowserContractError, click_text_control
from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)
from godfield_bot.domain.reference_diff import ArtifactDelta, BibleDiff, TextDelta
from godfield_bot.elements import ELEMENT_IMAGE_PATHS, CombatElement
from godfield_bot.weapon_rules import DYNAMIC_MP_ATTACK_PATTERN, WeaponAttackRule

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

PLAIN_ATTACK_PATTERN = re.compile(r"^ATK(\d+)$")
PLAIN_ATTACK_BOOST_PATTERN = re.compile(r"^\+ATK(\d+)$")
PROBABILISTIC_ATTACK_PATTERN = re.compile(r"^(\d+)%ATK(\d+)$")
PLAIN_DEFENSE_PATTERN = re.compile(r"^DEF(\d+)$")
HP_UTILITY_PATTERN = re.compile(r"^HP\+(\d+)$")
MP_UTILITY_PATTERN = re.compile(r"^MP\+(\d+)$")
CP_UTILITY_PATTERN = re.compile(r"^\$\+(\d+)$")
VERIFIED_PASSIVE_ATTACK_EFFECTS = frozenset(
    {
        "Bounce a NE weapon",
        "Bounce a miracle",
        "Reflect a NE weapon",
        "Reflect a miracle",
        "Block a miracle",
    }
)
VERIFIED_AUTOMATIC_ATTACK_EFFECTS = frozenset(
    {
        "Absorb HP",
        "Hell on damage",
        "Cold on damage",
        "Dream on damage",
        "Dark Cloud on damage",
        "Flash on damage",
        "Fog on damage",
    }
)
VERIFIED_BROWSER_AUTOMATIC_ATTACK_EFFECTS = frozenset(
    {
        "Attack somebody",
        "Do a miracle w/o cost",
        "Get the same damage",
        "Set Fire element",
        "Set Water element",
    }
)
VERIFIED_BROWSER_ATTACK_EFFECT_MULTIPLIERS = {
    "Attack twice": 2.0,
}
VERIFIED_EFFECT_ATTACK_MIRACLE_ABILITIES = {
    "Absorb HP": "absorbHP",
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


async def fingerprint_client(context: BrowserContext) -> ClientFingerprint:
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


async def _selected_detail(page: Page, image_path: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    result = cast(
        dict[str, Any],
        await page.evaluate(
            """
            (wanted) => {
              const images = [...document.querySelectorAll(`img[src="${wanted}"]`)];
              const detailImage = images.find(
                (image) => image.parentElement?.querySelector('span')
              );
              const panel = detailImage?.parentElement?.parentElement;
              if (!panel) return {text: '', elementImagePaths: []};
              const elementImagePaths = [...panel.querySelectorAll('img')]
                .map((image) => new URL(image.src).pathname)
                .filter((path) => path.startsWith('/images/elements/'));
              return {text: panel.innerText, elementImagePaths};
            }
            """,
            image_path,
        ),
    )
    return (
        _clean_lines(cast(str, result["text"])),
        tuple(dict.fromkeys(cast(list[str], result["elementImagePaths"]))),
    )


async def _extract_category(page: Page, category: str, *, timeout_ms: float) -> ArtifactCategory:
    category_slug = category.lower()
    await click_text_control(page, category)
    first_image = page.locator(f'img[src^="/images/items/{category_slug}/"]').first
    await first_image.wait_for(state="attached", timeout=timeout_ms)
    sources = await _artifact_sources(page, category_slug)
    if not sources:
        raise ReferenceExtractionError(f"no artifact images found for {category}")

    raw_items: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for image_path in sources:
        target = page.locator(f'img[src="{image_path}"] + div')
        if await target.count() != 1:
            raise ReferenceExtractionError(
                f"expected one click target for {image_path}, found {await target.count()}"
            )
        await target.click(timeout=timeout_ms)
        detail, element_image_paths = await _selected_detail(page, image_path)
        if not detail:
            raise ReferenceExtractionError(f"empty detail panel for {image_path}")
        raw_items.append((image_path, detail, element_image_paths))

    notes = longest_common_prefix([detail for _, detail, _ in raw_items])
    items = tuple(
        ArtifactRecord(
            asset=Path(image_path).stem,
            image_path=image_path,
            detail=without_prefix(detail, notes),
            element_image_paths=element_image_paths,
        )
        for image_path, detail, element_image_paths in raw_items
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
            client = await fingerprint_client(context)
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


def diff_bible_snapshots(baseline: BibleSnapshot, candidate: BibleSnapshot) -> BibleDiff:
    reference_changes = tuple(
        TextDelta(
            name=name,
            before=baseline.reference_sections.get(name, ()),
            after=candidate.reference_sections.get(name, ()),
        )
        for name in sorted(baseline.reference_sections.keys() | candidate.reference_sections.keys())
        if baseline.reference_sections.get(name, ()) != candidate.reference_sections.get(name, ())
    )
    category_names = baseline.catalog.keys() | candidate.catalog.keys()
    note_changes = tuple(
        TextDelta(
            name=name,
            before=baseline.catalog[name].notes if name in baseline.catalog else (),
            after=candidate.catalog[name].notes if name in candidate.catalog else (),
        )
        for name in sorted(category_names)
        if (baseline.catalog[name].notes if name in baseline.catalog else ())
        != (candidate.catalog[name].notes if name in candidate.catalog else ())
    )
    artifact_changes: list[ArtifactDelta] = []
    for category_name in sorted(category_names):
        before_items = (
            {item.asset: item for item in baseline.catalog[category_name].items}
            if category_name in baseline.catalog
            else {}
        )
        after_items = (
            {item.asset: item for item in candidate.catalog[category_name].items}
            if category_name in candidate.catalog
            else {}
        )
        for asset in sorted(before_items.keys() | after_items.keys()):
            before = before_items.get(asset)
            after = after_items.get(asset)
            if before == after:
                continue
            if before is None:
                change: Literal["added", "removed", "modified"] = "added"
            elif after is None:
                change = "removed"
            else:
                change = "modified"
            artifact_changes.append(
                ArtifactDelta(
                    category=category_name,
                    asset=asset,
                    change=change,
                    before=before,
                    after=after,
                )
            )
    client_changed = baseline.client.sha256 != candidate.client.sha256
    source_url_changed = baseline.source_url != candidate.source_url
    language_changed = baseline.language != candidate.language
    has_semantic_changes = bool(
        client_changed
        or source_url_changed
        or language_changed
        or reference_changes
        or note_changes
        or artifact_changes
    )
    return BibleDiff(
        baseline_client_sha256=baseline.client.sha256,
        candidate_client_sha256=candidate.client.sha256,
        client_changed=client_changed,
        source_url_changed=source_url_changed,
        language_changed=language_changed,
        baseline_category_counts=category_counts(baseline),
        candidate_category_counts=category_counts(candidate),
        reference_section_changes=reference_changes,
        category_note_changes=note_changes,
        artifact_changes=tuple(artifact_changes),
        has_semantic_changes=has_semantic_changes,
    )


def _combat_element(artifact: ArtifactRecord) -> CombatElement | None:
    if not artifact.element_image_paths:
        return "non-element"
    if len(artifact.element_image_paths) != 1:
        return None
    return ELEMENT_IMAGE_PATHS.get(artifact.element_image_paths[0])


def plain_attack_weapon_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, CombatElement]]:
    """Return effect-free weapon attacks and their single combat element."""

    result: dict[str, tuple[int, CombatElement]] = {}
    for artifact in snapshot.catalog["weapons"].items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 4:
            continue
        attack = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        if (
            attack is not None
            and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
            and artifact.detail[3].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(attack.group(1)), element)
    return result


def plain_attack_weapon_values(snapshot: BibleSnapshot) -> dict[str, int]:
    """Return effect-free non-element weapon attacks from the current Bible."""

    return {
        slug: attack
        for slug, (attack, element) in plain_attack_weapon_cards(snapshot).items()
        if element == "non-element"
    }


def plain_attack_booster_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, CombatElement]]:
    """Return effect-free additive attacks and their single combat element."""

    result: dict[str, tuple[int, CombatElement]] = {}
    for artifact in snapshot.catalog["weapons"].items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 4:
            continue
        boost = PLAIN_ATTACK_BOOST_PATTERN.fullmatch(artifact.detail[1])
        if (
            boost is not None
            and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
            and artifact.detail[3].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(boost.group(1)), element)
    return result


def verified_attack_weapon_values(snapshot: BibleSnapshot) -> dict[str, int]:
    """Return fixed neutral attacks that require no follow-up decision."""

    result = plain_attack_weapon_values(snapshot)
    for artifact in snapshot.catalog["weapons"].items:
        if artifact.element_image_paths or len(artifact.detail) != 5:
            continue
        attack = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        if (
            attack is not None
            and artifact.detail[2]
            in VERIFIED_PASSIVE_ATTACK_EFFECTS | VERIFIED_AUTOMATIC_ATTACK_EFFECTS
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = int(attack.group(1))
        if (
            attack is not None
            and PLAIN_DEFENSE_PATTERN.fullmatch(artifact.detail[2]) is not None
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = int(attack.group(1))
    return result


def verified_browser_weapon_attacks(snapshot: BibleSnapshot) -> dict[str, WeaponAttackRule]:
    """Return one-click weapon attacks with an exact UI display and expected damage.

    Browser confirmation is guarded by both the selected artifact asset and the exact
    rendered attack expression. Single-element attacks, additive weapons used alone,
    probabilistic attacks, and audited automatic effects need no additional player
    choice, so they are safe to execute even though the native simulator currently
    models only a smaller deterministic subset.
    """

    result: dict[str, WeaponAttackRule] = {}
    allowed_effects = (
        VERIFIED_PASSIVE_ATTACK_EFFECTS
        | VERIFIED_AUTOMATIC_ATTACK_EFFECTS
        | VERIFIED_BROWSER_AUTOMATIC_ATTACK_EFFECTS
        | VERIFIED_BROWSER_ATTACK_EFFECT_MULTIPLIERS.keys()
    )
    for artifact in snapshot.catalog["weapons"].items:
        if _combat_element(artifact) is None:
            continue
        attack_text = artifact.detail[1]
        fixed = PLAIN_ATTACK_PATTERN.fullmatch(attack_text)
        additive = PLAIN_ATTACK_BOOST_PATTERN.fullmatch(attack_text)
        probabilistic = PROBABILISTIC_ATTACK_PATTERN.fullmatch(attack_text)
        dynamic_mp = DYNAMIC_MP_ATTACK_PATTERN.fullmatch(attack_text)
        ascension = (
            re.fullmatch(r"(\d+)%ATK(\d+) at Ascension", artifact.detail[2])
            if probabilistic is not None and len(artifact.detail) == 5
            else None
        )
        if fixed is None and additive is None and probabilistic is None and dynamic_mp is None:
            continue
        if len(artifact.detail) == 4:
            price_index = 2
        elif len(artifact.detail) == 5 and (
            artifact.detail[2] in allowed_effects
            or PLAIN_DEFENSE_PATTERN.fullmatch(artifact.detail[2]) is not None
            or (dynamic_mp is not None and artifact.detail[2] == "Consume all the MP")
            or ascension is not None
        ):
            price_index = 3
        else:
            continue
        if re.fullmatch(r"\$\d+", artifact.detail[price_index]) is None or not artifact.detail[
            price_index + 1
        ].startswith("Gift Rate:"):
            continue
        if fixed is not None:
            expected_damage = float(fixed.group(1))
            action_display = attack_text
        elif additive is not None:
            expected_damage = float(additive.group(1))
            action_display = f"ATK{additive.group(1)}"
        elif dynamic_mp is not None:
            # This coefficient is resolved against live MP by the heuristic.
            expected_damage = float(dynamic_mp.group(1))
            action_display = attack_text
        else:
            assert probabilistic is not None
            expected_damage = int(probabilistic.group(1)) * int(probabilistic.group(2)) / 100.0
            action_display = attack_text
        if len(artifact.detail) == 5:
            expected_damage *= VERIFIED_BROWSER_ATTACK_EFFECT_MULTIPLIERS.get(
                artifact.detail[2],
                1.0,
            )
        if ascension is not None:
            result[artifact.asset] = (
                action_display,
                expected_damage,
                (f"{ascension.group(1)}%ATK{ascension.group(2)}",),
            )
        else:
            result[artifact.asset] = (action_display, expected_damage)
    return result


def verified_attack_miracle_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, CombatElement]]:
    """Return fixed-attack miracles with exact MP cost and one element."""

    result: dict[str, tuple[int, int, CombatElement]] = {}
    for artifact in snapshot.catalog["miracles"].items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        attack = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        cost = re.fullmatch(r"(\d+)MP", artifact.detail[3])
        if (
            attack is not None
            and artifact.detail[2] == "Cost"
            and cost is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (
                int(attack.group(1)),
                int(cost.group(1)),
                element,
            )
    return result


def verified_effect_attack_miracle_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, CombatElement, str]]:
    """Return fixed-attack miracles with an audited automatic effect."""

    miracles = snapshot.catalog.get("miracles")
    if miracles is None:
        return {}
    result: dict[str, tuple[int, int, CombatElement, str]] = {}
    for artifact in miracles.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 6:
            continue
        attack = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        cost = re.fullmatch(r"(\d+)MP", artifact.detail[4])
        if (
            attack is not None
            and artifact.detail[2] in VERIFIED_EFFECT_ATTACK_MIRACLE_ABILITIES
            and artifact.detail[3] == "Cost"
            and cost is not None
            and artifact.detail[5].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (
                int(attack.group(1)),
                int(cost.group(1)),
                element,
                VERIFIED_EFFECT_ATTACK_MIRACLE_ABILITIES[artifact.detail[2]],
            )
    return result


def verified_attack_booster_miracle_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, CombatElement]]:
    """Return additive attack miracles with an exact MP cost and element."""

    miracles = snapshot.catalog.get("miracles")
    if miracles is None:
        return {}
    result: dict[str, tuple[int, int, CombatElement]] = {}
    for artifact in miracles.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        boost = PLAIN_ATTACK_BOOST_PATTERN.fullmatch(artifact.detail[1])
        cost = re.fullmatch(r"(\d+)MP", artifact.detail[3])
        if (
            boost is not None
            and artifact.detail[2] == "Cost"
            and cost is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (
                int(boost.group(1)),
                int(cost.group(1)),
                element,
            )
    return result


def verified_reflection_armor_cards(snapshot: BibleSnapshot) -> frozenset[str]:
    """Return armor whose complete audited effect is unconditional reflection."""

    armor = snapshot.catalog.get("armor")
    if armor is None:
        return frozenset()
    return frozenset(
        artifact.asset
        for artifact in armor.items
        if not artifact.element_image_paths
        and len(artifact.detail) == 4
        and artifact.detail[1] == "Reflect anything"
        and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
        and artifact.detail[3].startswith("Gift Rate:")
    )


def verified_reflection_weapon_cards(snapshot: BibleSnapshot) -> dict[str, int]:
    """Return NE weapons with an audited deterministic reflection response."""

    weapons = snapshot.catalog.get("weapons")
    if weapons is None:
        return {}
    result: dict[str, int] = {}
    for artifact in weapons.items:
        if artifact.element_image_paths or len(artifact.detail) != 5:
            continue
        match = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        if (
            match is not None
            and artifact.detail[2] == "Reflect a NE weapon"
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = int(match.group(1))
    return result


def plain_dual_role_weapon_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, CombatElement]]:
    """Return weapons with exact ATK, DEF, and one combat element."""

    weapons = snapshot.catalog.get("weapons")
    if weapons is None:
        return {}
    result: dict[str, tuple[int, int, CombatElement]] = {}
    for artifact in weapons.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        attack = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        defense = PLAIN_DEFENSE_PATTERN.fullmatch(artifact.detail[2])
        if (
            attack is not None
            and defense is not None
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (
                int(attack.group(1)),
                int(defense.group(1)),
                element,
            )
    return result


def plain_chance_weapon_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, CombatElement]]:
    """Return effect-free chance weapons with exact hit rate and ATK."""

    weapons = snapshot.catalog.get("weapons")
    if weapons is None:
        return {}
    result: dict[str, tuple[int, int, CombatElement]] = {}
    for artifact in weapons.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 4:
            continue
        attack = PROBABILISTIC_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        if (
            attack is not None
            and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
            and artifact.detail[3].startswith("Gift Rate:")
        ):
            hit_rate = int(attack.group(1))
            attack_value = int(attack.group(2))
            if 1 <= hit_rate <= 100 and attack_value > 0:
                result[artifact.asset] = (hit_rate, attack_value, element)
    return result


def plain_chance_dual_role_weapon_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, int, CombatElement]]:
    """Return chance weapons with exact hit rate, ATK, DEF, and element."""

    weapons = snapshot.catalog.get("weapons")
    if weapons is None:
        return {}
    result: dict[str, tuple[int, int, int, CombatElement]] = {}
    for artifact in weapons.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        attack = PROBABILISTIC_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        defense = PLAIN_DEFENSE_PATTERN.fullmatch(artifact.detail[2])
        if (
            attack is not None
            and defense is not None
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            hit_rate = int(attack.group(1))
            attack_value = int(attack.group(2))
            if 1 <= hit_rate <= 100 and attack_value > 0:
                result[artifact.asset] = (
                    hit_rate,
                    attack_value,
                    int(defense.group(1)),
                    element,
                )
    return result


def verified_absorption_weapon_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, CombatElement]]:
    """Return fixed weapons whose complete audited effect is HP absorption."""

    weapons = snapshot.catalog.get("weapons")
    if weapons is None:
        return {}
    result: dict[str, tuple[int, CombatElement]] = {}
    for artifact in weapons.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        attack = PLAIN_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        if (
            attack is not None
            and artifact.detail[2] == "Absorb HP"
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(attack.group(1)), element)
    return result


def verified_chance_absorption_weapon_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, CombatElement]]:
    """Return chance weapons whose complete audited effect is HP absorption."""

    weapons = snapshot.catalog.get("weapons")
    if weapons is None:
        return {}
    result: dict[str, tuple[int, int, CombatElement]] = {}
    for artifact in weapons.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        attack = PROBABILISTIC_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        if (
            attack is not None
            and artifact.detail[2] == "Absorb HP"
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            hit_rate = int(attack.group(1))
            attack_value = int(attack.group(2))
            if 1 <= hit_rate <= 100 and attack_value > 0:
                result[artifact.asset] = (hit_rate, attack_value, element)
    return result


def verified_chance_attack_miracle_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int, int, CombatElement]]:
    """Return plain chance-attack miracles with hit rate, damage, cost, and element."""

    miracles = snapshot.catalog.get("miracles")
    if miracles is None:
        return {}
    result: dict[str, tuple[int, int, int, CombatElement]] = {}
    for artifact in miracles.items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 5:
            continue
        attack = PROBABILISTIC_ATTACK_PATTERN.fullmatch(artifact.detail[1])
        cost = re.fullmatch(r"(\d+)MP", artifact.detail[3])
        if (
            attack is not None
            and artifact.detail[2] == "Cost"
            and cost is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            hit_rate = int(attack.group(1))
            attack_value = int(attack.group(2))
            if not 1 <= hit_rate <= 100 or attack_value == 0:
                continue
            result[artifact.asset] = (
                hit_rate,
                attack_value,
                int(cost.group(1)),
                element,
            )
    return result


def plain_hp_utility_sundries(snapshot: BibleSnapshot) -> dict[str, int]:
    """Return unconditional, consumable HP gains from the accepted Bible."""

    result: dict[str, int] = {}
    for artifact in snapshot.catalog["sundries"].items:
        if artifact.element_image_paths or len(artifact.detail) != 4:
            continue
        utility = HP_UTILITY_PATTERN.fullmatch(artifact.detail[1])
        if (
            utility is not None
            and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
            and artifact.detail[3].startswith("Gift Rate:")
        ):
            result[artifact.asset] = int(utility.group(1))
    return result


def plain_mp_utility_sundries(snapshot: BibleSnapshot) -> dict[str, int]:
    """Return unconditional, consumable MP gains from the accepted Bible."""

    result: dict[str, int] = {}
    for artifact in snapshot.catalog["sundries"].items:
        if artifact.element_image_paths or len(artifact.detail) != 4:
            continue
        utility = MP_UTILITY_PATTERN.fullmatch(artifact.detail[1])
        if (
            utility is not None
            and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
            and artifact.detail[3].startswith("Gift Rate:")
        ):
            result[artifact.asset] = int(utility.group(1))
    return result


def verified_stochastic_hp_sundries(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int]]:
    """Return self-targeting HP-or-damage sundries with both outcomes audited."""

    sundries = snapshot.catalog.get("sundries")
    if sundries is None:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for artifact in sundries.items:
        if artifact.element_image_paths or len(artifact.detail) != 5:
            continue
        utility = HP_UTILITY_PATTERN.fullmatch(artifact.detail[1])
        damage = re.fullmatch(r"or (\d+) damage", artifact.detail[2])
        if (
            utility is not None
            and damage is not None
            and re.fullmatch(r"\$\d+", artifact.detail[3]) is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(utility.group(1)), int(damage.group(1)))
    return result


def verified_hp_utility_miracle_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int]]:
    """Return unconditional HP miracles with an exact MP cost."""

    result: dict[str, tuple[int, int]] = {}
    for artifact in snapshot.catalog["miracles"].items:
        if artifact.element_image_paths or len(artifact.detail) != 5:
            continue
        utility = HP_UTILITY_PATTERN.fullmatch(artifact.detail[1])
        cost = re.fullmatch(r"(\d+)MP", artifact.detail[3])
        if (
            utility is not None
            and artifact.detail[2] == "Cost"
            and cost is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(utility.group(1)), int(cost.group(1)))
    return result


def verified_cp_utility_miracle_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, int]]:
    """Return unconditional CP miracles with an exact MP cost."""

    miracles = snapshot.catalog.get("miracles")
    if miracles is None:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for artifact in miracles.items:
        if artifact.element_image_paths or len(artifact.detail) != 5:
            continue
        utility = CP_UTILITY_PATTERN.fullmatch(artifact.detail[1])
        cost = re.fullmatch(r"(\d+)MP", artifact.detail[3])
        if (
            utility is not None
            and artifact.detail[2] == "Cost"
            and cost is not None
            and artifact.detail[4].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(utility.group(1)), int(cost.group(1)))
    return result


def plain_defense_armor_cards(
    snapshot: BibleSnapshot,
) -> dict[str, tuple[int, CombatElement]]:
    """Return effect-free armor defenses and their single combat element."""

    result: dict[str, tuple[int, CombatElement]] = {}
    for artifact in snapshot.catalog["armor"].items:
        element = _combat_element(artifact)
        if element is None or len(artifact.detail) != 4:
            continue
        defense = PLAIN_DEFENSE_PATTERN.fullmatch(artifact.detail[1])
        if (
            defense is not None
            and re.fullmatch(r"\$\d+", artifact.detail[2]) is not None
            and artifact.detail[3].startswith("Gift Rate:")
        ):
            result[artifact.asset] = (int(defense.group(1)), element)
    return result


def plain_defense_armor_values(snapshot: BibleSnapshot) -> dict[str, int]:
    """Return effect-free non-element armor defenses from the current Bible."""

    return {
        slug: defense
        for slug, (defense, element) in plain_defense_armor_cards(snapshot).items()
        if element == "non-element"
    }


def ensure_expected_counts(actual: dict[str, int], expected: Iterable[tuple[str, int]]) -> None:
    for category, count in expected:
        if actual.get(category) != count:
            raise ReferenceExtractionError(
                f"{category} count drift: expected {count}, observed {actual.get(category)}"
            )
