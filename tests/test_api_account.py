import asyncio
import hashlib
import json
import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from godfield_bot.account import AccountMetadata, metadata_path
from godfield_bot.api_account import (
    PYGODFIELD_REVISION,
    ApiAccountError,
    ApiCredentials,
    _extract_browser_api_credentials,
    _write_api_credentials,
    api_account_status,
    enable_api_account,
    read_api_credentials,
    validate_api_credentials,
    verify_api_connection,
)
from godfield_bot.config import AppSettings


def fingerprint(user_id: str) -> str:
    return hashlib.sha256(f"godfield-bot-firebase-v1:{user_id}".encode()).hexdigest()


def settings_with_account(tmp_path, *, user_id: str = "stable-user") -> AppSettings:
    settings = AppSettings(state_root=tmp_path)
    metadata_path(settings).write_text(
        AccountMetadata(
            identity=settings.identity,
            created_at=datetime.now(UTC),
            auth_fingerprint=fingerprint(user_id),
        ).model_dump_json(),
        encoding="utf-8",
    )
    return settings


def credentials(user_id: str = "stable-user") -> ApiCredentials:
    return ApiCredentials(
        user_id=user_id,
        id_token="id-token-secret",
        refresh_token="refresh-token-secret",
        expires_at=2_000_000_000,
    )


def test_api_credentials_are_owner_only_and_match_browser_identity(tmp_path) -> None:
    settings = settings_with_account(tmp_path)

    _write_api_credentials(settings, credentials())

    assert stat.S_IMODE(settings.api_token_file.stat().st_mode) == 0o600
    assert read_api_credentials(settings) == credentials()
    assert validate_api_credentials(settings) == credentials()
    serialized_status = json.dumps(api_account_status(settings))
    assert "id-token-secret" not in serialized_status
    assert "refresh-token-secret" not in serialized_status
    assert PYGODFIELD_REVISION in serialized_status


def test_api_credentials_fail_closed_on_identity_mismatch(tmp_path) -> None:
    settings = settings_with_account(tmp_path)
    _write_api_credentials(settings, credentials("different-user"))

    with pytest.raises(ApiAccountError, match="differs"):
        validate_api_credentials(settings)


def test_api_credentials_fail_closed_on_unsafe_permissions(tmp_path) -> None:
    settings = settings_with_account(tmp_path)
    _write_api_credentials(settings, credentials())
    settings.api_token_file.chmod(0o644)

    with pytest.raises(ApiAccountError, match="expected 600"):
        read_api_credentials(settings)


def test_api_credentials_fail_closed_on_symbolic_link(tmp_path) -> None:
    settings = settings_with_account(tmp_path)
    target = tmp_path / "elsewhere.json"
    target.write_text(credentials().model_dump_json(), encoding="utf-8")
    target.chmod(0o600)
    settings.api_token_file.symlink_to(target)

    with pytest.raises(ApiAccountError, match="safely"):
        read_api_credentials(settings)
    status = api_account_status(settings)
    assert status["api_credentials_present"] is True
    assert status["api_identity_continuity_verified"] is False


def test_existing_api_enablement_is_idempotent_without_browser_access(tmp_path) -> None:
    settings = settings_with_account(tmp_path)
    _write_api_credentials(settings, credentials())

    result = asyncio.run(enable_api_account(settings, headed=False, timeout_seconds=1))

    assert result.enabled is False
    assert result.identity_continuity_verified is True


def test_browser_credential_shape_is_normalized_without_logging_secrets() -> None:
    page = AsyncMock()
    page.evaluate.return_value = {
        "user_id": "stable-user",
        "id_token": "id-token-secret",
        "refresh_token": "refresh-token-secret",
        "expires_at": 2_000_000_000,
    }

    result = asyncio.run(_extract_browser_api_credentials(page))

    assert result == credentials()
    assert "id-token-secret" not in repr(result)
    assert "refresh-token-secret" not in repr(result)


def test_connection_verification_redacts_identity_and_validates_counts(
    tmp_path,
    monkeypatch,
) -> None:
    settings = settings_with_account(tmp_path)

    class FakeClient:
        user_id = "stable-user"

        @staticmethod
        def user_count():
            return {"training": 3, "private": 2, "duel": 1, "future": 999}

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield FakeClient()

    monkeypatch.setattr("godfield_bot.api_account.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_account.validate_api_credentials",
        lambda value: SimpleNamespace(user_id="stable-user"),
    )

    result = verify_api_connection(settings)
    serialized = result.model_dump_json()

    assert result.online_by_mode == {"training": 3, "private": 2, "duel": 1}
    assert "stable-user" not in serialized
