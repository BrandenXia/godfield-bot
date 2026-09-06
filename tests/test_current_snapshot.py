import json
from pathlib import Path

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.reference import category_counts

SNAPSHOT_PATH = Path(__file__).parents[1] / "data" / "snapshots" / "2026-09-06" / "bible.json"


def test_committed_snapshot_matches_validated_live_catalog() -> None:
    snapshot = BibleSnapshot.model_validate(json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")))

    assert snapshot.total_artifacts == 291
    assert snapshot.client.sha256 == (
        "764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd"
    )
    assert category_counts(snapshot) == {
        "weapons": 107,
        "armor": 78,
        "sundries": 19,
        "miracles": 30,
        "devils": 5,
        "guardians": 42,
        "phenomena": 10,
    }
