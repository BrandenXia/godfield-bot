import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import structlog
from filelock import FileLock, Timeout
from playwright.async_api import async_playwright
from pydantic import BaseModel

from godfield_bot.browser.controls import BrowserContractError, click_text_control
from godfield_bot.config import AppSettings

log = structlog.get_logger()


class AccountStorageError(RuntimeError):
    """Raised when the persistent identity cannot be stored safely."""


class AccountMetadata(BaseModel):
    schema_version: int = 1
    identity: str
    created_at: datetime


class AccountCreationResult(BaseModel):
    identity: str
    created: bool


def metadata_path(settings: AppSettings) -> Path:
    return settings.state_root / "account.json"


def read_account_metadata(settings: AppSettings) -> AccountMetadata | None:
    path = metadata_path(settings)
    if not path.exists():
        return None
    return AccountMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def prepare_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    actual_mode = stat.S_IMODE(path.stat().st_mode)
    if actual_mode != 0o700:
        raise AccountStorageError(
            f"private directory permissions are {actual_mode:o}, expected 700"
        )


def _write_metadata(settings: AppSettings, metadata: AccountMetadata) -> None:
    prepare_private_directory(settings.state_root)
    destination = metadata_path(settings)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


async def create_account(
    settings: AppSettings, *, headed: bool, timeout_seconds: float
) -> AccountCreationResult:
    """Create and persist the dedicated anonymous account through the visible web UI."""

    existing = read_account_metadata(settings)
    if existing is not None:
        if existing.identity != settings.identity:
            raise AccountStorageError("stored account identity does not match configured identity")
        if not settings.profile_directory.exists():
            raise AccountStorageError("account metadata exists but the browser profile is missing")
        return AccountCreationResult(identity=existing.identity, created=False)

    prepare_private_directory(settings.state_root)
    prepare_private_directory(settings.profile_directory)
    lock_path = settings.state_root / ".profile.lock"
    lock = FileLock(lock_path, timeout=0)
    try:
        with lock:
            os.chmod(lock_path, 0o600)
            timeout_ms = timeout_seconds * 1_000
            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=settings.profile_directory,
                    headless=not headed,
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(
                        f"{settings.base_url}?lang=en",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    name_field = page.locator('input[type="text"]')
                    await name_field.wait_for(state="visible", timeout=timeout_ms)
                    await name_field.fill(settings.identity)
                    await click_text_control(page, "Genesis")
                    await page.get_by_text("Training", exact=True).wait_for(
                        state="visible", timeout=timeout_ms
                    )
                finally:
                    await context.close()
    except Timeout as error:
        raise AccountStorageError("the account browser profile is already in use") from error

    _write_metadata(
        settings,
        AccountMetadata(identity=settings.identity, created_at=datetime.now(UTC)),
    )
    log.info("account_created", identity=settings.identity)
    return AccountCreationResult(identity=settings.identity, created=True)


def account_status(settings: AppSettings) -> dict[str, object]:
    metadata = read_account_metadata(settings)
    return {
        "identity": settings.identity,
        "created": metadata is not None,
        "profile_present": settings.profile_directory.exists(),
        "public_duel_enabled": settings.public_duel_enabled,
        "created_at": metadata.created_at.isoformat() if metadata else None,
    }


def status_json(settings: AppSettings) -> str:
    return json.dumps(account_status(settings), ensure_ascii=False, indent=2)


__all__ = [
    "AccountStorageError",
    "BrowserContractError",
    "account_status",
    "create_account",
    "prepare_private_directory",
    "read_account_metadata",
    "status_json",
]
