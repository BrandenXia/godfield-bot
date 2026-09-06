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


class VisibleText(BaseModel):
    text: str
    bounds: Bounds
    color: str | None = None


class VisibleImage(BaseModel):
    path: str
    bounds: Bounds
    hit_target_bounds: Bounds | None = None


class VisibleMarker(BaseModel):
    bounds: Bounds
    background_color: str


class ScreenObservation(BaseModel):
    schema_version: int = 3
    observed_at: datetime
    url: str
    title: str
    kind: ScreenKind
    viewport_width: int
    viewport_height: int
    text: tuple[str, ...]
    text_elements: tuple[VisibleText, ...]
    controls: tuple[VisibleControl, ...]
    images: tuple[VisibleImage, ...]
    markers: tuple[VisibleMarker, ...] = ()
