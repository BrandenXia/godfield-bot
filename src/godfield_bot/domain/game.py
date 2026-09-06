from datetime import datetime

from pydantic import BaseModel, Field

from godfield_bot.domain.observation import Bounds


class PlayerState(BaseModel):
    name: str
    hp: int = Field(ge=0)
    mp: int = Field(ge=0)
    money: int = Field(ge=0)
    is_self: bool
    status_marker_color: str | None = None


class HandArtifact(BaseModel):
    slot: int = Field(ge=0)
    category: str
    slug: str
    asset_path: str
    bounds: Bounds
    hit_target_bounds: Bounds | None = None


class GameState(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    mode: str = "training"
    field_number: int = Field(ge=0)
    self_player_index: int = Field(ge=0)
    players: tuple[PlayerState, ...]
    hand: tuple[HandArtifact, ...]
    scene_layers: tuple[str, ...]
    action_actor: str | None = None
    action_display: str | None = None
