from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ClientFingerprint(BaseModel):
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    etag: str | None = None
    last_modified: str | None = None


class ArtifactRecord(BaseModel):
    asset: str = Field(pattern=r"^[a-z0-9-]+$")
    image_path: str
    detail: tuple[str, ...]
    element_image_paths: tuple[str, ...] = ()


class ArtifactCategory(BaseModel):
    notes: tuple[str, ...] = ()
    items: tuple[ArtifactRecord, ...]

    @model_validator(mode="after")
    def assets_are_unique(self) -> "ArtifactCategory":
        assets = [item.asset for item in self.items]
        if len(assets) != len(set(assets)):
            raise ValueError("artifact assets must be unique within a category")
        return self


class BibleSnapshot(BaseModel):
    schema_version: int = 2
    observed_at: datetime
    source_url: str
    language: str
    client: ClientFingerprint
    reference_sections: dict[str, tuple[str, ...]]
    catalog: dict[str, ArtifactCategory]
    total_artifacts: int

    @model_validator(mode="after")
    def total_matches_catalog(self) -> "BibleSnapshot":
        actual = sum(len(category.items) for category in self.catalog.values())
        if actual != self.total_artifacts:
            raise ValueError(
                f"total_artifacts={self.total_artifacts} but catalog contains {actual}"
            )
        return self
