from playwright.async_api import Page


class BrowserContractError(RuntimeError):
    """Raised when the rendered client no longer matches a safe interaction contract."""


async def click_text_control(page: Page, text: str) -> None:
    """Click a visible God Field control through its transparent hit target."""

    labels = page.get_by_text(text, exact=True)
    for index in range(await labels.count()):
        label = labels.nth(index)
        if not await label.is_visible():
            continue
        candidate = label
        for _ in range(4):
            candidate = candidate.locator("..")
            style = await candidate.get_attribute("style") or ""
            if "cursor: pointer" in style and await candidate.is_visible():
                hit_targets = candidate.locator(":scope > div")
                if await hit_targets.count():
                    await hit_targets.last.click(force=True)
                else:
                    await candidate.click(force=True)
                return
    raise BrowserContractError(f"visible clickable control not found: {text}")
