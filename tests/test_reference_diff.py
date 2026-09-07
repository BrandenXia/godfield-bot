from datetime import UTC, datetime
from pathlib import Path

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.reference import diff_bible_snapshots

SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")


def load_snapshot() -> BibleSnapshot:
    return BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_diff_ignores_observation_timestamp() -> None:
    baseline = load_snapshot()
    candidate = baseline.model_copy(
        update={"observed_at": datetime(2030, 1, 1, tzinfo=UTC)}
    )

    result = diff_bible_snapshots(baseline, candidate)

    assert result.has_semantic_changes is False
    assert result.client_changed is False
    assert result.artifact_changes == ()
    assert result.reference_section_changes == ()


def test_snapshot_diff_reports_client_rules_notes_and_artifact_changes() -> None:
    baseline = load_snapshot()
    weapons = baseline.catalog["weapons"]
    first_weapon = weapons.items[0]
    modified_weapon = first_weapon.model_copy(
        update={"detail": (*first_weapon.detail[:-1], "Gift Rate: 4/500")}
    )
    catalog = dict(baseline.catalog)
    catalog["weapons"] = weapons.model_copy(
        update={
            "notes": (*weapons.notes, "Changed note"),
            "items": (modified_weapon, *weapons.items[1:]),
        }
    )
    reference_sections = dict(baseline.reference_sections)
    reference_sections["trade"] = (*reference_sections["trade"], "Changed rule")
    candidate = baseline.model_copy(
        update={
            "client": baseline.client.model_copy(update={"sha256": "b" * 64}),
            "catalog": catalog,
            "reference_sections": reference_sections,
        }
    )

    result = diff_bible_snapshots(baseline, candidate)

    assert result.has_semantic_changes is True
    assert result.client_changed is True
    assert result.reference_section_changes[0].name == "trade"
    assert result.category_note_changes[0].name == "weapons"
    assert len(result.artifact_changes) == 1
    assert result.artifact_changes[0].category == "weapons"
    assert result.artifact_changes[0].asset == first_weapon.asset
    assert result.artifact_changes[0].change == "modified"
