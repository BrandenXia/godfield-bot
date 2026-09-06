from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)
from godfield_bot.reference import (
    ReferenceExtractionError,
    ensure_expected_counts,
    longest_common_prefix,
    without_prefix,
)


def artifact(asset: str) -> ArtifactRecord:
    return ArtifactRecord(
        asset=asset,
        image_path=f"/images/items/weapons/{asset}.webp",
        detail=(asset, "ATK1"),
    )


def fingerprint() -> ClientFingerprint:
    return ClientFingerprint(url="https://example.test/client.js", sha256="a" * 64)


def test_common_category_notes_are_split_from_item_detail() -> None:
    rows = [
        ("Miracles cost MP.", "Reusable.", "<Fireball>", "+ATK2"),
        ("Miracles cost MP.", "Reusable.", "<Ice>", "ATK4"),
    ]

    prefix = longest_common_prefix(rows)

    assert prefix == ("Miracles cost MP.", "Reusable.")
    assert without_prefix(rows[0], prefix) == ("<Fireball>", "+ATK2")


def test_snapshot_rejects_incorrect_total() -> None:
    with pytest.raises(ValidationError, match="catalog contains 1"):
        BibleSnapshot(
            observed_at=datetime.now(UTC),
            source_url="https://godfield.net/",
            language="en",
            client=fingerprint(),
            reference_sections={},
            catalog={"weapons": ArtifactCategory(items=(artifact("bronze-club"),))},
            total_artifacts=2,
        )


def test_category_rejects_duplicate_assets() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        ArtifactCategory(items=(artifact("bronze-club"), artifact("bronze-club")))


def test_expected_count_guard_fails_closed() -> None:
    with pytest.raises(ReferenceExtractionError, match="weapons count drift"):
        ensure_expected_counts({"weapons": 106}, (("weapons", 107),))
