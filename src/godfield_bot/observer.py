from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from godfield_bot.account import start_account_session
from godfield_bot.browser.controls import click_header_back, click_text_control
from godfield_bot.browser.profile import open_account_context
from godfield_bot.config import AppSettings
from godfield_bot.domain.observation import (
    ScreenKind,
    ScreenObservation,
    VisibleControl,
    VisibleImage,
    VisibleMarker,
    VisibleText,
)


class ObservationError(RuntimeError):
    """Raised when a safe typed observation cannot be produced."""


class ObservationTarget(StrEnum):
    MENU = "menu"
    TRAINING = "training"
    GAME = "game"


async def _start_or_recover_training_battle(
    page: Page,
    *,
    timeout_seconds: float,
) -> None:
    start_battle = page.get_by_text("Start Battle", exact=True)
    try:
        await start_battle.wait_for(
            state="visible",
            timeout=min(timeout_seconds, 5.0) * 1_000,
        )
    except PlaywrightTimeoutError:
        await click_header_back(page, "Training")
        await page.get_by_text("Hidden Melee", exact=True).wait_for(
            state="visible",
            timeout=timeout_seconds * 1_000,
        )
        await click_text_control(page, "Training")
        await start_battle.wait_for(
            state="visible",
            timeout=timeout_seconds * 1_000,
        )
    await click_text_control(page, "Start Battle")


def classify_screen(text: tuple[str, ...], images: tuple[VisibleImage, ...]) -> ScreenKind:
    labels = set(text)
    image_paths = {image.path for image in images}
    if {"Training", "Hidden Melee", "Royal Duel"}.issubset(labels):
        return ScreenKind.MENU
    if "HP" in labels and (
        any(label.startswith("G.F.") for label in labels)
        or any("/images/items/" in path for path in image_paths)
    ):
        return ScreenKind.GAME
    if "Training" in labels and "/images/screens/room.webp" in image_paths:
        return ScreenKind.TRAINING_SETUP
    if {"Elements", "Curses", "Trade", "Weapons"}.issubset(labels):
        return ScreenKind.BIBLE
    if "Prophet Name" in labels and "Genesis" in labels:
        return ScreenKind.HOME
    return ScreenKind.UNKNOWN


async def capture_screen(page: Page) -> ScreenObservation:
    raw = cast(
        dict[str, Any],
        await page.evaluate(
            """
            () => {
              const bounds = (element) => {
                const rect = element.getBoundingClientRect();
                return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
              };
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const text = [...document.querySelectorAll('span')]
                .filter(rendered)
                .map((element) => element.innerText.trim())
                .filter(Boolean);
              const textElements = [...document.querySelectorAll('span')]
                .filter(rendered)
                .map((element) => ({
                  text: element.innerText.trim(),
                  bounds: bounds(element),
                  color: getComputedStyle(element).color,
                }))
                .filter((element) => element.text);
              const controls = [...document.querySelectorAll('div, input, a, select')]
                .filter((element) => {
                  if (!rendered(element)) return false;
                  if (element.matches('input, a, select')) return true;
                  const cursor = getComputedStyle(element).cursor;
                  const parentCursor = element.parentElement
                    ? getComputedStyle(element.parentElement).cursor
                    : '';
                  return cursor === 'pointer' && parentCursor !== 'pointer';
                })
                .map((element) => ({
                  text: (element.innerText || element.getAttribute('aria-label') || '').trim(),
                  tag: element.tagName.toLowerCase(),
                  bounds: bounds(element),
                }));
              const images = [...document.querySelectorAll('img')]
                .filter(rendered)
                .map((element) => {
                  const imageBounds = bounds(element);
                  let sibling = element.nextElementSibling;
                  while (sibling?.tagName === 'IMG' && rendered(sibling)) {
                    const overlayBounds = bounds(sibling);
                    const sameBounds = Math.abs(overlayBounds.x - imageBounds.x) <= 1.5 &&
                      Math.abs(overlayBounds.y - imageBounds.y) <= 1.5 &&
                      Math.abs(overlayBounds.width - imageBounds.width) <= 1.5 &&
                      Math.abs(overlayBounds.height - imageBounds.height) <= 1.5;
                    if (!sameBounds) break;
                    sibling = sibling.nextElementSibling;
                  }
                  const handImage = imageBounds.x >= 100 && imageBounds.x <= 850 &&
                    imageBounds.y >= 480 && imageBounds.y <= 690;
                  const pointerTarget = sibling?.tagName === 'DIV' && rendered(sibling) &&
                    getComputedStyle(sibling).cursor === 'pointer';
                  const hitTarget = handImage && pointerTarget ? bounds(sibling) : null;
                  return {
                    path: new URL(element.src).pathname,
                    bounds: imageBounds,
                    hit_target_bounds: hitTarget,
                  };
                });
              const markers = [...document.querySelectorAll('*')]
                .filter((element) => {
                  if (!rendered(element)) return false;
                  const rect = element.getBoundingClientRect();
                  if (rect.x < 700 || rect.y > 400) return false;
                  if (rect.width < 10 || rect.width > 24 || rect.height < 10 ||
                      rect.height > 24 || Math.abs(rect.width - rect.height) > 2) return false;
                  const style = getComputedStyle(element);
                  const opaqueBackground = style.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                    style.backgroundColor !== 'transparent';
                  const opaqueFill = style.fill !== 'none' && style.fill !== 'rgba(0, 0, 0, 0)' &&
                    style.fill !== 'transparent';
                  const round = element.tagName.toLowerCase() === 'circle' ||
                    parseFloat(style.borderRadius) >= rect.width / 3;
                  return round && (opaqueBackground || opaqueFill);
                })
                .map((element) => ({
                  bounds: bounds(element),
                  background_color: getComputedStyle(element).backgroundColor ===
                    'rgba(0, 0, 0, 0)'
                    ? getComputedStyle(element).fill
                    : getComputedStyle(element).backgroundColor,
                }));
              return {
                url: location.href,
                title: document.title,
                viewportWidth: innerWidth,
                viewportHeight: innerHeight,
                text: [...new Set(text)],
                textElements,
                controls,
                images,
                markers,
              };
            }
            """
        ),
    )
    text = tuple(cast(list[str], raw["text"]))
    text_elements = tuple(VisibleText.model_validate(value) for value in raw["textElements"])
    controls = tuple(VisibleControl.model_validate(value) for value in raw["controls"])
    images = tuple(VisibleImage.model_validate(value) for value in raw["images"])
    markers = tuple(VisibleMarker.model_validate(value) for value in raw["markers"])
    return ScreenObservation(
        observed_at=datetime.now(UTC),
        url=cast(str, raw["url"]),
        title=cast(str, raw["title"]),
        kind=classify_screen(text, images),
        viewport_width=cast(int, raw["viewportWidth"]),
        viewport_height=cast(int, raw["viewportHeight"]),
        text=text,
        text_elements=text_elements,
        controls=controls,
        images=images,
        markers=markers,
    )


async def observe_account_screen(
    settings: AppSettings,
    *,
    target: ObservationTarget,
    headed: bool,
    screenshot: Path | None,
    settle_seconds: float,
    timeout_seconds: float,
) -> ScreenObservation:
    async with open_account_context(settings, headed=headed) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await start_account_session(page, settings, timeout_seconds=timeout_seconds)
        observation = await capture_screen(page)
        if target is ObservationTarget.GAME and observation.kind is ScreenKind.GAME:
            await page.wait_for_timeout(settle_seconds * 1_000)
            observation = await capture_screen(page)
        if target is ObservationTarget.MENU and observation.kind is not ScreenKind.MENU:
            raise ObservationError(f"expected menu screen, observed {observation.kind}")
        if target in {ObservationTarget.TRAINING, ObservationTarget.GAME} and (
            observation.kind is ScreenKind.MENU
        ):
            await click_text_control(page, "Training")
            await page.wait_for_timeout(settle_seconds * 1_000)
            observation = await capture_screen(page)
        if target is ObservationTarget.GAME and observation.kind is not ScreenKind.GAME:
            if observation.kind is not ScreenKind.TRAINING_SETUP:
                raise ObservationError(
                    f"expected Training setup or game, observed {observation.kind}"
                )
            await _start_or_recover_training_battle(
                page,
                timeout_seconds=timeout_seconds,
            )
            await page.wait_for_timeout(settle_seconds * 1_000)
            observation = await capture_screen(page)
        if screenshot is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot), full_page=True)
    return observation
