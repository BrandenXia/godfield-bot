import pytest
from pydantic import ValidationError

from godfield_bot.config import DEFAULT_IDENTITY, AppSettings


def test_default_identity_and_public_duel_gate() -> None:
    settings = AppSettings()

    assert settings.identity == DEFAULT_IDENTITY == "ロキ-67"
    assert settings.public_duel_enabled is False
    assert settings.profile_directory.name == "loki-67"
    assert settings.api_token_file.name == "api-identity.json"
    assert settings.identity_lock_file.name == ".identity.lock"


def test_identity_rejects_outer_whitespace() -> None:
    with pytest.raises(ValidationError):
        AppSettings(identity=" ロキ-67")
