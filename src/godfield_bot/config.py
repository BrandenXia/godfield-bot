from pathlib import Path

from platformdirs import user_state_path
from pydantic import BaseModel, Field, HttpUrl, field_validator

APP_NAME = "godfield-bot"
DEFAULT_IDENTITY = "ロキ-67"


class AppSettings(BaseModel):
    """Validated settings shared by CLI and future local control plane."""

    identity: str = Field(default=DEFAULT_IDENTITY, min_length=1, max_length=18)
    base_url: HttpUrl = HttpUrl("https://godfield.net/")
    state_root: Path = Field(default_factory=lambda: user_state_path(APP_NAME, ensure_exists=False))
    public_duel_enabled: bool = False

    @field_validator("identity")
    @classmethod
    def identity_must_not_have_outer_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("identity must not start or end with whitespace")
        return value

    @property
    def profile_directory(self) -> Path:
        return self.state_root / "profiles" / "loki-67"

    @property
    def api_token_file(self) -> Path:
        return self.state_root / "api-identity.json"

    @property
    def identity_lock_file(self) -> Path:
        return self.state_root / ".identity.lock"
