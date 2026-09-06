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


async def click_header_back(page: Page, title: str) -> None:
    """Click the header control immediately left of an exact visible title."""

    clicked: bool = await page.evaluate(
        """
        (wantedTitle) => {
          const rendered = (element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0;
          };
          const title = [...document.querySelectorAll('span')]
            .find((element) => rendered(element) && element.innerText.trim() === wantedTitle);
          if (!title) return false;
          const titleRect = title.getBoundingClientRect();
          const candidates = [...document.querySelectorAll('div')]
            .filter((element) => {
              if (!rendered(element) || getComputedStyle(element).cursor !== 'pointer') {
                return false;
              }
              const rect = element.getBoundingClientRect();
              const overlapsTitleVertically = rect.top < titleRect.bottom &&
                rect.bottom > titleRect.top;
              const parentCursor = element.parentElement
                ? getComputedStyle(element.parentElement).cursor
                : '';
              return overlapsTitleVertically && rect.right <= titleRect.left &&
                parentCursor !== 'pointer';
            })
            .sort((left, right) => right.getBoundingClientRect().right -
              left.getBoundingClientRect().right);
          if (candidates.length !== 1) return false;
          candidates[0].click();
          return true;
        }
        """,
        title,
    )
    if not clicked:
        raise BrowserContractError(f"unique header back control not found for: {title}")
