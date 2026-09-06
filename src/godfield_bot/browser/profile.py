import os
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from filelock import FileLock, Timeout
from playwright.async_api import BrowserContext, async_playwright

from godfield_bot.config import AppSettings


class ProfileStorageError(RuntimeError):
    """Raised when the persistent browser identity cannot be used safely."""


def prepare_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    actual_mode = stat.S_IMODE(path.stat().st_mode)
    if actual_mode != 0o700:
        raise ProfileStorageError(
            f"private directory permissions are {actual_mode:o}, expected 700"
        )


@asynccontextmanager
async def open_account_context(
    settings: AppSettings, *, headed: bool
) -> AsyncIterator[BrowserContext]:
    """Exclusively open the persistent account profile."""

    prepare_private_directory(settings.state_root)
    prepare_private_directory(settings.profile_directory)
    lock_path = settings.state_root / ".profile.lock"
    lock = FileLock(lock_path, timeout=0)
    try:
        with lock:
            os.chmod(lock_path, 0o600)
            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=settings.profile_directory,
                    headless=not headed,
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    yield context
                finally:
                    await context.close()
    except Timeout as error:
        raise ProfileStorageError("the account browser profile is already in use") from error
