import asyncio
import json
import stat
from datetime import UTC, datetime

import pytest

from godfield_bot.account import (
    AccountMetadata,
    AccountStorageError,
    account_status,
    create_account,
    metadata_path,
    prepare_private_directory,
    read_account_metadata,
)
from godfield_bot.config import AppSettings


def test_private_profile_directory_has_owner_only_permissions(tmp_path) -> None:
    profile = tmp_path / "profile"

    prepare_private_directory(profile)

    assert stat.S_IMODE(profile.stat().st_mode) == 0o700


def test_account_metadata_is_read_without_exposing_profile_data(tmp_path) -> None:
    settings = AppSettings(state_root=tmp_path)
    metadata = AccountMetadata(identity=settings.identity, created_at=datetime.now(UTC))
    path = metadata_path(settings)
    path.write_text(metadata.model_dump_json(), encoding="utf-8")

    loaded = read_account_metadata(settings)
    status = account_status(settings)

    assert loaded == metadata
    assert status["identity"] == "ロキ-67"
    assert status["created"] is True
    assert "profile_directory" not in json.dumps(status)


def test_existing_metadata_without_profile_fails_closed(tmp_path) -> None:
    settings = AppSettings(state_root=tmp_path)
    metadata_path(settings).write_text(
        AccountMetadata(identity=settings.identity, created_at=datetime.now(UTC)).model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(AccountStorageError, match="profile is missing"):
        asyncio.run(create_account(settings, headed=False, timeout_seconds=1))
