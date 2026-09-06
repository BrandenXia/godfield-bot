from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ScreenKind(StrEnum):
    HOME = "home"
    MENU = "menu"
    BIBLE = "bible"
    TRAINING_SETUP = "training_setup"
    GAME = "game"
    UNKNOWN = "unknown"


class Bounds(BaseModel):
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class VisibleControl(BaseModel):
    text: str
    tag: str
    bounds: Bounds


class VisibleImage(BaseModel):
    path: str
    bounds: Bounds


class ScreenObservation(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    url: str
    title: str
    kind: ScreenKind
    viewport_width: int
    viewport_height: int
    text: tuple[str, ...]
    controls: tuple[VisibleControl, ...]
    images: tuple[VisibleImage, ...]
