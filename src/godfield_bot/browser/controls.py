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
    """Click one normalized hand slot, following a same-bounds Dream overlay."""

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            r"""
            ({wantedSlot, wantedPath}) => {
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width >= 60 && rect.width <= 100 &&
                  rect.height >= 60 && rect.height <= 100;
              };
              const images = [...document.querySelectorAll('img')]
                .filter((image) => {
                  if (!rendered(image)) return false;
                  const path = new URL(image.src).pathname;
                  if (!/^\/images\/items\/[^/]+\/[^/]+\.(?:png|svg|webp)$/.test(path) ||
                      path.startsWith('/images/items/trade/')) return false;
                  const rect = image.getBoundingClientRect();
                  return rect.x >= 100 && rect.x <= 850 && rect.y >= 480 && rect.y <= 690;
                })
                .sort((left, right) => {
                  const leftRect = left.getBoundingClientRect();
                  const rightRect = right.getBoundingClientRect();
                  return leftRect.y - rightRect.y || leftRect.x - rightRect.x;
                });
              if (wantedSlot < 0 || wantedSlot >= images.length) return null;
              const selected = images[wantedSlot];
              const path = new URL(selected.src).pathname;
              if (path !== wantedPath) return null;
              const selectedRect = selected.getBoundingClientRect();
              let target = selected.nextElementSibling;
              while (target?.tagName === 'IMG' && rendered(target)) {
                const overlayRect = target.getBoundingClientRect();
                const sameBounds = Math.abs(overlayRect.x - selectedRect.x) <= 1.5 &&
                  Math.abs(overlayRect.y - selectedRect.y) <= 1.5 &&
                  Math.abs(overlayRect.width - selectedRect.width) <= 1.5 &&
                  Math.abs(overlayRect.height - selectedRect.height) <= 1.5;
                if (!sameBounds) return null;
                target = target.nextElementSibling;
              }
              if (!target || target.tagName !== 'DIV' || !rendered(target) ||
                  getComputedStyle(target).cursor !== 'pointer') return null;
              const allDivs = [...document.querySelectorAll('div')];
              return {targetDomIndex: allDivs.indexOf(target), path};
            }
            """,
            {"wantedSlot": slot, "wantedPath": asset_path},
        ),
    )
    if descriptor is None:
        raise BrowserContractError("normalized hand slot no longer matches the live DOM")
    target = page.locator("div").nth(cast(int, descriptor["targetDomIndex"]))
    if not await target.is_visible():
        raise BrowserContractError("unique visible hand hit target was not found")
    await target.click(force=True)


async def click_player_target(page: Page, *, player_index: int, player_name: str) -> None:
    """Click one player row after re-deriving its index and name from live stats."""

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            r"""
            ({wantedIndex, wantedName}) => {
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
              const spans = [...document.querySelectorAll('span')].filter(rendered);
              const hpLabels = spans
                .filter((element) => {
                  const rect = element.getBoundingClientRect();
                  return element.innerText.trim() === 'HP' && rect.x >= 700 && rect.y < 400;
                })
                .sort((left, right) => left.getBoundingClientRect().y -
                  right.getBoundingClientRect().y);
              const rows = [];
              for (const hp of hpLabels) {
                const hpRect = hp.getBoundingClientRect();
                const names = spans.filter((element) => {
                  const rect = element.getBoundingClientRect();
                  const value = element.innerText.trim();
                  return Math.abs(rect.y - hpRect.y) <= 1.5 && rect.x < hpRect.x &&
                    !['HP', 'MP', '$'].includes(value) && !/^\d+$/.test(value);
                });
                if (names.length !== 1) return null;
                rows.push(names[0]);
              }
              if (wantedIndex < 0 || wantedIndex >= rows.length) return null;
              const selectedName = rows[wantedIndex];
              if (selectedName.innerText.trim() !== wantedName) return null;
              const nameRect = selectedName.getBoundingClientRect();
              const allDivs = [...document.querySelectorAll('div')];
              const candidates = allDivs.filter((element) => {
                if (!rendered(element) || getComputedStyle(element).cursor !== 'pointer') {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                const parentCursor = element.parentElement
                  ? getComputedStyle(element.parentElement).cursor
                  : '';
                return parentCursor !== 'pointer' && element.innerText.trim() === '' &&
                  rect.x >= 700 && rect.x <= nameRect.x &&
                  Math.abs(rect.y - nameRect.y) <= 1.5 &&
                  rect.width >= 250 && rect.width <= 400 &&
                  rect.height >= 25 && rect.height <= 60;
              });
              if (candidates.length !== 1) return null;
              return {domIndex: allDivs.indexOf(candidates[0]), bounds: bounds(candidates[0])};
            }
            """,
            {"wantedIndex": player_index, "wantedName": player_name},
        ),
    )
    if descriptor is None:
        raise BrowserContractError("normalized player target no longer matches the live DOM")
    target = page.locator("div").nth(cast(int, descriptor["domIndex"]))
    if not await target.is_visible():
        raise BrowserContractError("unique visible player-row hit target was not found")
    await target.click(force=True)


async def click_empty_action_panel(page: Page, *, actor_name: str) -> None:
    """Confirm an empty Pray action after revalidating its actor and left panel."""

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            """
            (wantedActor) => {
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const spans = [...document.querySelectorAll('span')].filter(rendered);
              const actors = spans.filter((element) => {
                const rect = element.getBoundingClientRect();
                return element.innerText.trim() === wantedActor &&
                  rect.x >= 100 && rect.x <= 450 && rect.y >= 40 && rect.y <= 80;
              });
              const pray = spans.filter((element) => {
                const rect = element.getBoundingClientRect();
                return element.innerText.trim() === 'Pray' &&
                  rect.x >= 100 && rect.x <= 450 && rect.y >= 390 && rect.y <= 450;
              });
              const selectedItems = [...document.querySelectorAll('img[src*="/images/items/"]')]
                .filter((element) => {
                  if (!rendered(element)) return false;
                  const rect = element.getBoundingClientRect();
                  return rect.x >= 100 && rect.x <= 450 && rect.y >= 80 && rect.y <= 300 &&
                    rect.width >= 60 && rect.width <= 100 &&
                    rect.height >= 60 && rect.height <= 100;
                });
              if (actors.length !== 1 || pray.length !== 1 || selectedItems.length !== 0) {
                return null;
              }
              const allDivs = [...document.querySelectorAll('div')];
              const candidates = allDivs.filter((element) => {
                if (!rendered(element) || getComputedStyle(element).cursor !== 'pointer') {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                const parentCursor = element.parentElement
                  ? getComputedStyle(element.parentElement).cursor
                  : '';
                return parentCursor !== 'pointer' && element.innerText.trim() === '' &&
                  rect.x >= 100 && rect.x <= 150 && rect.y >= 80 && rect.y <= 120 &&
                  rect.width >= 250 && rect.width <= 350 &&
                  rect.height >= 250 && rect.height <= 350;
              });
              if (candidates.length !== 1) return null;
              return {domIndex: allDivs.indexOf(candidates[0])};
            }
            """,
            actor_name,
        ),
    )
    if descriptor is None:
        raise BrowserContractError("empty Pray action no longer matches the verified left panel")
    target = page.locator("div").nth(cast(int, descriptor["domIndex"]))
    if not await target.is_visible():
        raise BrowserContractError("unique visible empty-action hit target was not found")
    await target.click(force=True)


async def click_phase_control(
    page: Page,
    *,
    text: str,
    panel: str,
    context_asset_paths: tuple[str, ...],
    target_name: str,
) -> None:
    """Click a phase panel after revalidating its label, target, and context assets."""

    if panel == "left":
        panel_min_x, panel_max_x = 100, 150
        label_min_x, label_max_x = 100, 450
        asset_min_x, asset_max_x = 450, 550
    elif panel == "right":
        panel_min_x, panel_max_x = 450, 500
        label_min_x, label_max_x = 451, 750
        asset_min_x, asset_max_x = 100, 200
    else:
        raise BrowserContractError(f"unsupported phase control panel: {panel}")

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            """
            ({wantedText, wantedPaths, wantedTarget, panelMinX, panelMaxX,
              labelMinX, labelMaxX, assetMinX, assetMaxX}) => {
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const labels = [...document.querySelectorAll('span')].filter((element) => {
                if (!rendered(element) || element.innerText.trim() !== wantedText) return false;
                const rect = element.getBoundingClientRect();
                return rect.x >= labelMinX && rect.x <= labelMaxX &&
                  rect.y >= 390 && rect.y <= 450;
              });
              if (labels.length !== 1) return null;
              const selectedImages = [...document.querySelectorAll('img')].filter((element) => {
                if (!rendered(element)) return false;
                const rect = element.getBoundingClientRect();
                return rect.x >= assetMinX && rect.x <= assetMaxX &&
                  rect.y >= 80 && rect.y <= 380 &&
                  rect.width >= 60 && rect.width <= 100 &&
                  rect.height >= 60 && rect.height <= 100;
              });
              const actualPaths = selectedImages
                .map((element) => new URL(element.src).pathname)
                .sort();
              const expectedPaths = [...wantedPaths].sort();
              if (actualPaths.length !== expectedPaths.length ||
                  actualPaths.some((value, index) => value !== expectedPaths[index])) return null;
              const targets = [...document.querySelectorAll('span')].filter((element) => {
                if (!rendered(element) || element.innerText.trim() !== wantedTarget) return false;
                const rect = element.getBoundingClientRect();
                return rect.x >= 451 && rect.x <= 750 && rect.y >= 40 && rect.y <= 80;
              });
              if (targets.length !== 1) return null;
              const allDivs = [...document.querySelectorAll('div')];
              const candidates = allDivs.filter((element) => {
                if (!rendered(element) || getComputedStyle(element).cursor !== 'pointer') {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                const parentCursor = element.parentElement
                  ? getComputedStyle(element.parentElement).cursor
                  : '';
                return parentCursor !== 'pointer' && element.innerText.trim() === '' &&
                  rect.x >= panelMinX && rect.x <= panelMaxX &&
                  rect.y >= 80 && rect.y <= 120 &&
                  rect.width >= 250 && rect.width <= 350 &&
                  rect.height >= 250 && rect.height <= 350;
              });
              if (candidates.length !== 1) return null;
              return {domIndex: allDivs.indexOf(candidates[0])};
            }
            """,
            {
                "wantedText": text,
                "wantedPaths": list(context_asset_paths),
                "wantedTarget": target_name,
                "panelMinX": panel_min_x,
                "panelMaxX": panel_max_x,
                "labelMinX": label_min_x,
                "labelMaxX": label_max_x,
                "assetMinX": asset_min_x,
                "assetMaxX": asset_max_x,
            },
        ),
    )
    if descriptor is None:
        raise BrowserContractError("phase control no longer matches its verified hit target")
    target = page.locator("div").nth(cast(int, descriptor["domIndex"]))
    if not await target.is_visible():
        raise BrowserContractError("unique visible phase-control hit target was not found")
    await target.click(force=True)


async def click_action_panel(
    page: Page,
    *,
    asset_path: str,
    target_name: str,
    panel: str,
) -> None:
    """Confirm a selected artifact after revalidating its named target and action panel."""

    if panel == "left":
        panel_min_x, panel_max_x = 100, 150
    elif panel == "right":
        panel_min_x, panel_max_x = 450, 500
    else:
        raise BrowserContractError(f"unsupported action panel: {panel}")

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            """
            ({wantedPath, wantedTarget, panelMinX, panelMaxX}) => {
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const selectedImages = [...document.querySelectorAll('img')].filter((element) => {
                if (!rendered(element) || new URL(element.src).pathname !== wantedPath) {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                return rect.x >= panelMinX && rect.x <= panelMaxX + 50 &&
                  rect.y >= 80 && rect.y <= 200 &&
                  rect.width >= 60 && rect.width <= 100 &&
                  rect.height >= 60 && rect.height <= 100;
              });
              if (selectedImages.length !== 1) return null;
              const targets = [...document.querySelectorAll('span')].filter((element) => {
                if (!rendered(element) || element.innerText.trim() !== wantedTarget) return false;
                const rect = element.getBoundingClientRect();
                return rect.x >= 451 && rect.x <= 750 && rect.y >= 40 && rect.y <= 80;
              });
              if (targets.length !== 1) return null;
              const allDivs = [...document.querySelectorAll('div')];
              const candidates = allDivs.filter((element) => {
                if (!rendered(element) || getComputedStyle(element).cursor !== 'pointer') {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                const parentCursor = element.parentElement
                  ? getComputedStyle(element.parentElement).cursor
                  : '';
                return parentCursor !== 'pointer' && element.innerText.trim() === '' &&
                  rect.x >= panelMinX && rect.x <= panelMaxX &&
                  rect.y >= 80 && rect.y <= 120 &&
                  rect.width >= 250 && rect.width <= 350 &&
                  rect.height >= 250 && rect.height <= 350;
              });
              if (candidates.length !== 1) return null;
              return {domIndex: allDivs.indexOf(candidates[0])};
            }
            """,
            {
                "wantedPath": asset_path,
                "wantedTarget": target_name,
                "panelMinX": panel_min_x,
                "panelMaxX": panel_max_x,
            },
        ),
    )
    if descriptor is None:
        raise BrowserContractError("selected action no longer matches its verified target panel")
    target = page.locator("div").nth(cast(int, descriptor["domIndex"]))
    if not await target.is_visible():
        raise BrowserContractError("unique visible action-panel hit target was not found")
    await target.click(force=True)


async def click_chance_panel(
    page: Page,
    *,
    asset_path: str,
    actor_name: str,
    action_display: str,
) -> None:
    """Resolve an untargeted chance attack after revalidating its exact left panel."""

    descriptor = cast(
        dict[str, Any] | None,
        await page.evaluate(
            """
            ({wantedPath, wantedActor, wantedDisplay}) => {
              const rendered = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const selected = [...document.querySelectorAll('img')].filter((element) => {
                if (!rendered(element) || new URL(element.src).pathname !== wantedPath) {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                return rect.x >= 100 && rect.x <= 200 && rect.y >= 80 && rect.y <= 200 &&
                  rect.width >= 60 && rect.width <= 100 &&
                  rect.height >= 60 && rect.height <= 100;
              });
              const spans = [...document.querySelectorAll('span')].filter(rendered);
              const actors = spans.filter((element) => {
                const rect = element.getBoundingClientRect();
                return element.innerText.trim() === wantedActor &&
                  rect.x >= 100 && rect.x <= 450 && rect.y >= 40 && rect.y <= 80;
              });
              const displays = spans.filter((element) => {
                const rect = element.getBoundingClientRect();
                return element.innerText.trim() === wantedDisplay &&
                  rect.x >= 100 && rect.x <= 450 && rect.y >= 390 && rect.y <= 450;
              });
              if (selected.length !== 1 || actors.length !== 1 || displays.length !== 1) {
                return null;
              }
              const allDivs = [...document.querySelectorAll('div')];
              const candidates = allDivs.filter((element) => {
                if (!rendered(element) || getComputedStyle(element).cursor !== 'pointer') {
                  return false;
                }
                const rect = element.getBoundingClientRect();
                const parentCursor = element.parentElement
                  ? getComputedStyle(element.parentElement).cursor
                  : '';
                return parentCursor !== 'pointer' && element.innerText.trim() === '' &&
                  rect.x >= 100 && rect.x <= 150 && rect.y >= 80 && rect.y <= 120 &&
                  rect.width >= 250 && rect.width <= 350 &&
                  rect.height >= 250 && rect.height <= 350;
              });
              if (candidates.length !== 1) return null;
              return {domIndex: allDivs.indexOf(candidates[0])};
            }
            """,
            {
                "wantedPath": asset_path,
                "wantedActor": actor_name,
                "wantedDisplay": action_display,
            },
        ),
    )
    if descriptor is None:
        raise BrowserContractError("chance attack no longer matches the verified left panel")
    target = page.locator("div").nth(cast(int, descriptor["domIndex"]))
    if not await target.is_visible():
        raise BrowserContractError("unique visible chance-attack hit target was not found")
    await target.click(force=True)
