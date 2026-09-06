from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from playwright.async_api import Page

from godfield_bot.account import start_account_session
from godfield_bot.browser.controls import click_text_control
from godfield_bot.browser.profile import open_account_context
from godfield_bot.config import AppSettings
from godfield_bot.domain.observation import (
    ScreenKind,
    ScreenObservation,
    VisibleControl,
    VisibleImage,
    VisibleText,
)


class ObservationError(RuntimeError):
    """Raised when a safe typed observation cannot be produced."""


class ObservationTarget(StrEnum):
    MENU = "menu"
    TRAINING = "training"
    GAME = "game"


def classify_screen(text: tuple[str, ...], images: tuple[VisibleImage, ...]) -> ScreenKind:
    labels = set(text)
    image_paths = {image.path for image in images}
    if {"Training", "Hidden Melee", "Royal Duel"}.issubset(labels):
        return ScreenKind.MENU
    if any("/images/items/" in path for path in image_paths) and "HP" in labels:
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
                .map((element) => ({
                  path: new URL(element.src).pathname,
                  bounds: bounds(element),
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
              };
            }
            """
        ),
    )
    text = tuple(cast(list[str], raw["text"]))
    text_elements = tuple(VisibleText.model_validate(value) for value in raw["textElements"])
    controls = tuple(VisibleControl.model_validate(value) for value in raw["controls"])
    images = tuple(VisibleImage.model_validate(value) for value in raw["images"])
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
            await page.get_by_text("Start Battle", exact=True).wait_for(
                state="visible",
                timeout=timeout_seconds * 1_000,
            )
            await click_text_control(page, "Start Battle")
            await page.wait_for_timeout(settle_seconds * 1_000)
            observation = await capture_screen(page)
        if screenshot is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot), full_page=True)
    return observation
