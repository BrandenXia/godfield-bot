import json
from pathlib import Path

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.reference import (
    category_counts,
    plain_attack_weapon_values,
    plain_defense_armor_values,
    verified_attack_weapon_values,
)

SNAPSHOT_PATH = Path(__file__).parents[1] / "data" / "snapshots" / "2026-09-07" / "bible.json"


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
    plain_attacks = plain_attack_weapon_values(snapshot)
    assert snapshot.schema_version == 2
    assert len(plain_attacks) == 18
    assert plain_attacks["bronze-club"] == 1
    assert plain_attacks["gravity-mace"] == 11
    plain_defenses = plain_defense_armor_values(snapshot)
    assert len(plain_defenses) == 15
    assert plain_defenses["iron-shield"] == 4
    assert plain_defenses["steel-shield"] == 8
    assert "flame-shield" not in plain_defenses
    verified_attacks = verified_attack_weapon_values(snapshot)
    assert len(verified_attacks) == 32
    assert verified_attacks["bouncing-sword"] == 5
    assert verified_attacks["reflection-sword"] == 10
    assert verified_attacks["moonlight-axe"] == 10
    assert verified_attacks["angel-sword"] == 13
    assert verified_attacks["legendary-scabbard"] == 13
    assert verified_attacks["ghost-sword"] == 7
    assert verified_attacks["hell-scissors"] == 8
    assert verified_attacks["gale-sword"] == 9
    assert verified_attacks["bogus-spear"] == 10
    assert verified_attacks["hexagon-doom"] == 11
    assert verified_attacks["real-ghost-sword"] == 12
    assert verified_attacks["severe-gale-sword"] == 13
    assert "evil-broadsword" not in verified_attacks
    assert "saw-boom-boom" not in verified_attacks
    assert "spiritual-staff" not in verified_attacks
    assert "frozen-hammer" not in verified_attacks
    frozen_hammer = next(
        artifact
        for artifact in snapshot.catalog["weapons"].items
        if artifact.asset == "frozen-hammer"
    )
    assert frozen_hammer.element_image_paths == ("/images/elements/water.webp",)
