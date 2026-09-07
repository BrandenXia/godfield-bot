from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from filelock import FileLock, Timeout
from playwright.async_api import Page
from pydantic import BaseModel, Field

from godfield_bot.account import read_account_metadata, start_account_session
from godfield_bot.browser.profile import open_account_context, prepare_private_directory
from godfield_bot.config import AppSettings

if TYPE_CHECKING:
    from godfield import GodfieldClient  # type: ignore[import-untyped]

PYGODFIELD_REVISION = "b33a31276b7e4dbaea962ff0df3ad3d1089a719d"


class ApiAccountError(RuntimeError):
    """Raised when the protocol client cannot safely reuse the bot identity."""


class ApiCredentials(BaseModel):
    user_id: str = Field(min_length=1, repr=False)
    id_token: str = Field(min_length=1, repr=False)
    refresh_token: str = Field(min_length=1, repr=False)
    expires_at: float = Field(gt=0, repr=False)


class ApiAccountEnableResult(BaseModel):
    identity: str
    enabled: bool
    identity_continuity_verified: bool
    upstream_revision: str = PYGODFIELD_REVISION


class ApiConnectionStatus(BaseModel):
    identity: str
    observed_at: datetime
    authenticated: bool = True
    identity_continuity_verified: bool = True
    upstream_revision: str = PYGODFIELD_REVISION
    online_by_mode: dict[str, int]


def api_token_path(settings: AppSettings) -> Path:
    return settings.api_token_file


def _identity_fingerprint(user_id: str) -> str:
    value = f"godfield-bot-firebase-v1:{user_id}".encode()
    return hashlib.sha256(value).hexdigest()


def _write_api_credentials(settings: AppSettings, credentials: ApiCredentials) -> None:
    prepare_private_directory(settings.state_root)
    destination = api_token_path(settings)
    temporary = destination.with_suffix(".json.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination_file:
            descriptor = -1
            destination_file.write(credentials.model_dump_json() + "\n")
        os.replace(temporary, destination)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def read_api_credentials(settings: AppSettings) -> ApiCredentials | None:
    path = api_token_path(settings)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ApiAccountError("the API credential file cannot be opened safely") from error
    try:
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode):
            raise ApiAccountError("the API credential path must be a regular file")
        actual_mode = stat.S_IMODE(file_status.st_mode)
        if actual_mode != 0o600:
            raise ApiAccountError(f"API credential permissions are {actual_mode:o}, expected 600")
        with os.fdopen(descriptor, encoding="utf-8") as credential_file:
            descriptor = -1
            serialized = credential_file.read()
        return ApiCredentials.model_validate_json(serialized)
    except ApiAccountError:
        raise
    except (OSError, ValueError) as error:
        raise ApiAccountError("the API credential file is unreadable or invalid") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def validate_api_credentials(settings: AppSettings) -> ApiCredentials:
    metadata = read_account_metadata(settings)
    if metadata is None or metadata.auth_fingerprint is None:
        raise ApiAccountError("the browser account identity has not been verified")
    credentials = read_api_credentials(settings)
    if credentials is None:
        raise ApiAccountError(
            "API control is not enabled; run `godfield-bot account enable-api --confirm-enable`"
        )
    if _identity_fingerprint(credentials.user_id) != metadata.auth_fingerprint:
        raise ApiAccountError(
            "the API credential identity differs from the ロキ-67 browser account"
        )
    return credentials


async def _extract_browser_api_credentials(page: Page) -> ApiCredentials:
    raw: Any = await page.evaluate(
        """
        async () => {
          const databaseName = 'firebaseLocalStorageDb';
          const database = await new Promise((resolve, reject) => {
            const request = indexedDB.open(databaseName);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
          });
          try {
            if (!database.objectStoreNames.contains('firebaseLocalStorage')) return null;
            const records = await new Promise((resolve, reject) => {
              const transaction = database.transaction('firebaseLocalStorage', 'readonly');
              const request = transaction.objectStore('firebaseLocalStorage').getAll();
              request.onerror = () => reject(request.error);
              request.onsuccess = () => resolve(request.result);
            });
            const candidates = records
              .map((record) => record?.value)
              .filter((value) =>
                typeof value?.uid === 'string' &&
                typeof value?.stsTokenManager?.accessToken === 'string' &&
                typeof value?.stsTokenManager?.refreshToken === 'string' &&
                Number.isFinite(Number(value?.stsTokenManager?.expirationTime))
              );
            const userIds = [...new Set(candidates.map((value) => value.uid))];
            if (userIds.length !== 1) return null;
            const value = candidates.find((candidate) => candidate.uid === userIds[0]);
            return {
              user_id: value.uid,
              id_token: value.stsTokenManager.accessToken,
              refresh_token: value.stsTokenManager.refreshToken,
              expires_at: Number(value.stsTokenManager.expirationTime) / 1000,
            };
          } finally {
            database.close();
          }
        }
        """
    )
    if not isinstance(raw, dict):
        raise ApiAccountError("the browser profile contains no reusable Firebase credentials")
    try:
        return ApiCredentials.model_validate(raw)
    except ValueError as error:
        raise ApiAccountError("the browser Firebase credential shape is unsupported") from error


async def enable_api_account(
    settings: AppSettings,
    *,
    headed: bool,
    timeout_seconds: float,
) -> ApiAccountEnableResult:
    existing = read_api_credentials(settings)
    if existing is not None:
        validate_api_credentials(settings)
        return ApiAccountEnableResult(
            identity=settings.identity,
            enabled=False,
            identity_continuity_verified=True,
        )

    async with open_account_context(settings, headed=headed) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await start_account_session(page, settings, timeout_seconds=timeout_seconds)
        credentials = await _extract_browser_api_credentials(page)
        metadata = read_account_metadata(settings)
        if metadata is None or metadata.auth_fingerprint is None:
            raise ApiAccountError("the browser account identity has not been verified")
        if _identity_fingerprint(credentials.user_id) != metadata.auth_fingerprint:
            raise ApiAccountError(
                "the extracted API identity differs from the ロキ-67 browser account"
            )
        _write_api_credentials(settings, credentials)
        validate_api_credentials(settings)
    return ApiAccountEnableResult(
        identity=settings.identity,
        enabled=True,
        identity_continuity_verified=True,
    )


def api_account_status(settings: AppSettings) -> dict[str, object]:
    credentials_present = os.path.lexists(api_token_path(settings))
    continuity_verified = False
    error: str | None = None
    if credentials_present:
        try:
            validate_api_credentials(settings)
            continuity_verified = True
        except ApiAccountError as caught:
            error = str(caught)
    return {
        "api_credentials_present": credentials_present,
        "api_identity_continuity_verified": continuity_verified,
        "api_credentials_error": error,
        "pygodfield_revision": PYGODFIELD_REVISION,
    }


def create_api_client(
    settings: AppSettings,
    *,
    timeout_seconds: float = 20,
    catalog: object | bool = False,
) -> GodfieldClient:
    """Create a side-effect-free client after validating the existing identity."""

    validate_api_credentials(settings)
    from godfield import GodfieldClient

    client = GodfieldClient(
        name=None,
        token_file=str(api_token_path(settings)),
        timeout=timeout_seconds,
        catalog=catalog,
    )
    client.name = settings.identity
    return client


@contextmanager
def open_api_client(
    settings: AppSettings,
    *,
    timeout_seconds: float = 20,
    catalog: object | bool = False,
) -> Iterator[GodfieldClient]:
    """Exclusively open the shared ロキ-67 identity for protocol control."""

    prepare_private_directory(settings.state_root)
    lock = FileLock(settings.identity_lock_file, timeout=0)
    try:
        with lock:
            os.chmod(settings.identity_lock_file, 0o600)
            client = create_api_client(
                settings,
                timeout_seconds=timeout_seconds,
                catalog=catalog,
            )
            try:
                yield client
            finally:
                client.close()
    except Timeout as error:
        raise ApiAccountError("the ロキ-67 identity is already in use") from error


def verify_api_connection(settings: AppSettings) -> ApiConnectionStatus:
    """Perform a read-only authenticated request without exposing account credentials."""

    from godfield import GodfieldError

    try:
        with open_api_client(settings, catalog=False) as client:
            user_id = client.user_id
            refreshed = validate_api_credentials(settings)
            if user_id != refreshed.user_id:
                raise ApiAccountError("the refreshed API identity failed its continuity check")
            raw_counts = client.user_count()
    except GodfieldError as error:
        raise ApiAccountError("pygodfield could not complete its authenticated read") from error
    counts = {
        mode: value
        for mode in ("training", "private", "duel")
        if isinstance((value := raw_counts.get(mode)), int)
        and not isinstance(value, bool)
        and value >= 0
    }
    return ApiConnectionStatus(
        identity=settings.identity,
        observed_at=datetime.now(UTC),
        online_by_mode=counts,
    )
