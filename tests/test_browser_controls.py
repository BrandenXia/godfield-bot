import asyncio
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from godfield_bot.browser.controls import (
    BrowserContractError,
    click_action_panel,
    click_hand_artifact,
)

BROWSER_DIRECTORY = Path(".playwright")


async def _exercise_nested_pointer_contract() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.set_content(
                """
                <base href="https://godfield.net/">
                <style>
                  body { margin: 0; min-height: 800px; }
                  .card { position: absolute; left: 110px; top: 493px;
                    width: 80px; height: 80px; }
                  #root { cursor: pointer; z-index: 2; }
                  #nested { position: absolute; inset: 0; cursor: pointer; }
                  #image { z-index: 1; }
                </style>
                <div id="root" class="card" onclick="window.clickCount += 1">
                  <div id="nested"></div>
                </div>
                <img id="image" class="card" src="/images/items/miracles/rock.webp">
                <script>window.clickCount = 0;</script>
                """
            )

            await click_hand_artifact(
                page,
                slot=0,
                asset_path="/images/items/miracles/rock.webp",
            )

            assert await page.evaluate("window.clickCount") == 1

            await page.set_content(
                """
                <base href="https://godfield.net/">
                <style>
                  body { margin: 0; min-height: 800px; }
                  .card { position: absolute; left: 110px; top: 493px;
                    width: 80px; height: 80px; }
                  .target { cursor: pointer; z-index: 2; }
                  #image { z-index: 1; }
                </style>
                <div class="card target"></div>
                <div class="card target"></div>
                <img id="image" class="card" src="/images/items/miracles/rock.webp">
                """
            )

            with pytest.raises(BrowserContractError, match="normalized hand slot"):
                await click_hand_artifact(
                    page,
                    slot=0,
                    asset_path="/images/items/miracles/rock.webp",
                )
        finally:
            await browser.close()


def test_hand_click_uses_one_root_when_pointer_layers_share_bounds(monkeypatch) -> None:
    if not BROWSER_DIRECTORY.exists():
        pytest.skip("local Playwright browser is not installed")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(BROWSER_DIRECTORY.resolve()))

    asyncio.run(_exercise_nested_pointer_contract())


async def _exercise_exact_combo_action_panel_contract() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.set_content(
                """
                <base href="https://godfield.net/">
                <style>
                  body { margin: 0; min-height: 800px; }
                  span { position: absolute; }
                  #actor { left: 217px; top: 50px; }
                  #target { left: 551px; top: 50px; }
                  #display { left: 145px; top: 403px; }
                  .card { position: absolute; left: 125px; width: 80px; height: 80px; }
                  #utility { top: 103px; }
                  #weapon { top: 203px; }
                  #panel { position: absolute; left: 115px; top: 93px;
                    width: 310px; height: 300px; cursor: pointer; }
                </style>
                <span id="actor">ロキ-67</span>
                <span id="target">CPU</span>
                <span id="display">ATK13</span>
                <div id="panel" onclick="window.clickCount += 1"></div>
                <img id="utility" class="card"
                  src="/images/items/sundries/romance-water.webp">
                <img id="weapon" class="card"
                  src="/images/items/weapons/severe-gale-sword.webp">
                <script>window.clickCount = 0;</script>
                """
            )

            context = (
                "/images/items/sundries/romance-water.webp",
                "/images/items/weapons/severe-gale-sword.webp",
            )
            await click_action_panel(
                page,
                asset_path="/images/items/weapons/severe-gale-sword.webp",
                target_name="CPU",
                panel="left",
                context_asset_paths=context,
                actor_name="ロキ-67",
                action_display="ATK13",
            )
            assert await page.evaluate("window.clickCount") == 1

            with pytest.raises(BrowserContractError, match="selected action"):
                await click_action_panel(
                    page,
                    asset_path="/images/items/weapons/severe-gale-sword.webp",
                    target_name="CPU",
                    panel="left",
                    context_asset_paths=(context[1],),
                    actor_name="ロキ-67",
                    action_display="ATK13",
                )
        finally:
            await browser.close()


def test_combo_action_click_requires_exact_cards_actor_target_and_display(monkeypatch) -> None:
    if not BROWSER_DIRECTORY.exists():
        pytest.skip("local Playwright browser is not installed")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(BROWSER_DIRECTORY.resolve()))

    asyncio.run(_exercise_exact_combo_action_panel_contract())
