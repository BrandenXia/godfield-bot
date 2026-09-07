from typing import Literal

from pydantic import BaseModel

from godfield_bot.domain.reference import ArtifactRecord


class ArtifactDelta(BaseModel):
    category: str
    asset: str
    change: Literal["added", "removed", "modified"]
    before: ArtifactRecord | None = None
    after: ArtifactRecord | None = None


class TextDelta(BaseModel):
    name: str
    before: tuple[str, ...]
    after: tuple[str, ...]


class BibleDiff(BaseModel):
    schema_version: int = 1
    baseline_client_sha256: str
    candidate_client_sha256: str
    client_changed: bool
    source_url_changed: bool
    language_changed: bool
    baseline_category_counts: dict[str, int]
    candidate_category_counts: dict[str, int]
    reference_section_changes: tuple[TextDelta, ...]
    category_note_changes: tuple[TextDelta, ...]
    artifact_changes: tuple[ArtifactDelta, ...]
    has_semantic_changes: bool
