import asyncio
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from godfield_bot.browser.controls import BrowserContractError, click_hand_artifact

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
