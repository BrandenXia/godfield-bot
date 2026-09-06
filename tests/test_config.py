import pytest
from pydantic import ValidationError

from godfield_bot.config import DEFAULT_IDENTITY, AppSettings


def test_default_identity_and_public_duel_gate() -> None:
    settings = AppSettings()

    assert settings.identity == DEFAULT_IDENTITY == "ロキ-67"
    assert settings.public_duel_enabled is False
    assert settings.profile_directory.name == "loki-67"


def test_identity_rejects_outer_whitespace() -> None:
    with pytest.raises(ValidationError):
        AppSettings(identity=" ロキ-67")
