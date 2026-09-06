from typing import Any, cast

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
        pointer_depth: int | None = await label.evaluate(
            """
            (element) => {
              let candidate = element;
              for (let depth = 1; depth <= 12 && candidate.parentElement; depth += 1) {
                candidate = candidate.parentElement;
                if (getComputedStyle(candidate).cursor === 'pointer') return depth;
              }
              return null;
            }
            """
        )
        if pointer_depth is None:
            label_bounds = await label.bounding_box()
            if label_bounds is None:
                continue
            await page.mouse.click(
                label_bounds["x"] + label_bounds["width"] / 2,
                label_bounds["y"] + label_bounds["height"] / 2,
            )
            return
        candidate = label
        for _ in range(pointer_depth):
            candidate = candidate.locator("..")
        if not await candidate.is_visible():
            continue
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


async def click_hand_artifact(page: Page, *, slot: int, asset_path: str) -> None:
    """Click the verified sibling hit target for one normalized hand slot."""

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            """
            ({wantedSlot, wantedPath}) => {
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width >= 60 && rect.width <= 100 &&
                  rect.height >= 60 && rect.height <= 100;
              };
              const images = [...document.querySelectorAll('img[src^="/images/items/"]')]
                .map((image, domIndex) => ({image, domIndex}))
                .filter(({image}) => rendered(image));
              const buckets = new Map();
              for (const candidate of images) {
                const key = Math.round(candidate.image.getBoundingClientRect().y / 5);
                if (!buckets.has(key)) buckets.set(key, []);
                buckets.get(key).push(candidate);
              }
              const groups = [...buckets.values()]
                .sort((left, right) => right.length - left.length);
              if (!groups.length || wantedSlot < 0 || wantedSlot >= groups[0].length) return null;
              const selected = groups[0][wantedSlot];
              const path = new URL(selected.image.src).pathname;
              if (path !== wantedPath) return null;
              const target = selected.image.nextElementSibling;
              if (!target || target.tagName !== 'DIV') return null;
              return {domIndex: selected.domIndex, path};
            }
            """,
            {"wantedSlot": slot, "wantedPath": asset_path},
        ),
    )
    if descriptor is None:
        raise BrowserContractError("normalized hand slot no longer matches the live DOM")
    images = page.locator('img[src^="/images/items/"]')
    image = images.nth(cast(int, descriptor["domIndex"]))
    target = image.locator("xpath=following-sibling::div[1]")
    if await target.count() != 1 or not await target.is_visible():
        raise BrowserContractError("unique visible hand hit target was not found")
    await target.click(force=True)
