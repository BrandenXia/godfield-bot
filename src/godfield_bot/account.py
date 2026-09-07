import json
import os
from datetime import UTC, datetime
from pathlib import Path

import structlog
from playwright.async_api import Page
from pydantic import BaseModel

from godfield_bot.browser.controls import BrowserContractError, click_text_control
from godfield_bot.browser.profile import (
    ProfileStorageError,
    open_account_context,
    prepare_private_directory,
)
from godfield_bot.config import AppSettings

log = structlog.get_logger()


class AccountStorageError(ProfileStorageError):
    """Raised when the persistent identity cannot be stored safely."""


class AccountMetadata(BaseModel):
    schema_version: int = 2
    identity: str
    created_at: datetime
    auth_fingerprint: str | None = None


class AccountCreationResult(BaseModel):
    identity: str
    created: bool


class AccountSessionResult(BaseModel):
    identity: str
    entered_genesis: bool
    identity_continuity_verified: bool


def metadata_path(settings: AppSettings) -> Path:
    return settings.state_root / "account.json"


def read_account_metadata(settings: AppSettings) -> AccountMetadata | None:
    path = metadata_path(settings)
    if not path.exists():
        return None
    return AccountMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def _write_metadata(settings: AppSettings, metadata: AccountMetadata) -> None:
    prepare_private_directory(settings.state_root)
    destination = metadata_path(settings)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(metadata.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


async def firebase_identity_fingerprint(page: Page) -> str | None:
    """Hash the Firebase anonymous UID in-page without returning credential data."""

    result = await page.evaluate(
        """
        async () => {
          const databaseName = 'firebaseLocalStorageDb';
          if (indexedDB.databases) {
            const databases = await indexedDB.databases();
            if (!databases.some((database) => database.name === databaseName)) {
              return null;
            }
          }
          const database = await new Promise((resolve, reject) => {
            const request = indexedDB.open(databaseName);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
          });
          try {
            if (!database.objectStoreNames.contains('firebaseLocalStorage')) {
              return null;
            }
            const records = await new Promise((resolve, reject) => {
              const transaction = database.transaction('firebaseLocalStorage', 'readonly');
              const request = transaction.objectStore('firebaseLocalStorage').getAll();
              request.onerror = () => reject(request.error);
              request.onsuccess = () => resolve(request.result);
            });
            const userIds = [...new Set(records
              .map((record) => record?.value?.uid)
              .filter((value) => typeof value === 'string'))];
            if (userIds.length !== 1) return null;
            const input = new TextEncoder().encode(`godfield-bot-firebase-v1:${userIds[0]}`);
            const digest = await crypto.subtle.digest('SHA-256', input);
            return [...new Uint8Array(digest)]
              .map((value) => value.toString(16).padStart(2, '0'))
              .join('');
          } finally {
            database.close();
          }
        }
        """
    )
    return result if isinstance(result, str) else None


def _verify_identity_continuity(
    settings: AppSettings,
    metadata: AccountMetadata,
    observed_fingerprint: str | None,
) -> AccountMetadata:
    if observed_fingerprint is None:
        raise AccountStorageError("the persisted Firebase identity could not be verified")
    if metadata.auth_fingerprint is not None and metadata.auth_fingerprint != observed_fingerprint:
        raise AccountStorageError("the persisted Firebase identity changed unexpectedly")
    if metadata.auth_fingerprint is None:
        metadata = metadata.model_copy(
            update={"schema_version": 2, "auth_fingerprint": observed_fingerprint}
        )
        _write_metadata(settings, metadata)
    return metadata


async def start_account_session(
    page: Page,
    settings: AppSettings,
    *,
    timeout_seconds: float,
) -> AccountSessionResult:
    """Enter Genesis when needed and fail closed if the stored identity changed."""

    metadata = read_account_metadata(settings)
    if metadata is None:
        raise AccountStorageError("the persistent account has not been created")
    if metadata.identity != settings.identity:
        raise AccountStorageError("stored account identity does not match configured identity")

    timeout_ms = timeout_seconds * 1_000
    await page.goto(
        f"{settings.base_url}?lang=en",
        wait_until="domcontentloaded",
        timeout=timeout_ms,
    )
    await page.locator("body").wait_for(state="visible", timeout=timeout_ms)
    await page.wait_for_timeout(min(timeout_ms, 3_000))

    training = page.get_by_text("Training", exact=True)
    entered_genesis = False
    if not await training.is_visible():
        genesis = page.get_by_text("Genesis", exact=True)
        if not await genesis.is_visible():
            raise BrowserContractError("neither the home nor menu screen is visible")
        name_field = page.locator('input[type="text"]')
        await name_field.wait_for(state="visible", timeout=timeout_ms)
        await name_field.fill(settings.identity)
        await click_text_control(page, "Genesis")
        await training.wait_for(state="visible", timeout=timeout_ms)
        entered_genesis = True

    fingerprint = await firebase_identity_fingerprint(page)
    _verify_identity_continuity(settings, metadata, fingerprint)
    log.info(
        "account_session_ready",
        identity=settings.identity,
        entered_genesis=entered_genesis,
        identity_continuity_verified=True,
    )
    return AccountSessionResult(
        identity=settings.identity,
        entered_genesis=entered_genesis,
        identity_continuity_verified=True,
    )


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

    timeout_ms = timeout_seconds * 1_000
    async with open_account_context(settings, headed=headed) as context:
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
        await page.get_by_text("Training", exact=True).wait_for(state="visible", timeout=timeout_ms)
        fingerprint = await firebase_identity_fingerprint(page)
        if fingerprint is None:
            raise AccountStorageError("the Firebase identity could not be fingerprinted")

    _write_metadata(
        settings,
        AccountMetadata(
            identity=settings.identity,
            created_at=datetime.now(UTC),
            auth_fingerprint=fingerprint,
        ),
    )
    log.info("account_created", identity=settings.identity)
    return AccountCreationResult(identity=settings.identity, created=True)


def account_status(settings: AppSettings) -> dict[str, object]:
    from godfield_bot.api_account import api_account_status

    metadata = read_account_metadata(settings)
    status = {
        "identity": settings.identity,
        "created": metadata is not None,
        "profile_present": settings.profile_directory.exists(),
        "identity_continuity_protected": bool(metadata and metadata.auth_fingerprint),
        "public_duel_enabled": settings.public_duel_enabled,
        "created_at": metadata.created_at.isoformat() if metadata else None,
    }
    status.update(api_account_status(settings))
    return status


def status_json(settings: AppSettings) -> str:
    return json.dumps(account_status(settings), ensure_ascii=False, indent=2)


__all__ = [
    "AccountSessionResult",
    "AccountStorageError",
    "BrowserContractError",
    "account_status",
    "create_account",
    "firebase_identity_fingerprint",
    "prepare_private_directory",
    "read_account_metadata",
    "start_account_session",
    "status_json",
]
