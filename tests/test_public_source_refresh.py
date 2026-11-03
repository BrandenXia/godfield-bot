"""A dated public-source refresh is evidence, not permission to repin models."""

import hashlib
import json
from pathlib import Path

from godfield_bot.api_catalog import read_api_catalog_snapshot

ROOT = Path("data/snapshots/2026-11-03")


def test_archived_public_files_match_provenance_without_local_run_dependencies():
    provenance = json.loads((ROOT / "source-provenance.json").read_text())
    for source in provenance["sources"]:
        file = Path(source["snapshot_file"])
        assert file.is_relative_to(ROOT)
        body = file.read_bytes()
        assert hashlib.sha256(body).hexdigest() == source["archive_sha256"]
        downloaded = body[: source["bytes"]]
        assert hashlib.sha256(downloaded).hexdigest() == source["body_sha256"]
        assert source["last_modified"] == "Tue, 03 Nov 2026 05:01:41 GMT"
    assert provenance["engine_pins_changed"] is False
    assert provenance["official_fidelity_verified"] is False
    assert provenance["promotion_eligible"] is False


def test_complete_catalog_changes_exactly_three_labels_not_other_item_fields():
    old = read_api_catalog_snapshot(Path("data/snapshots/2026-10-01/api-catalog-en.json"))
    new = read_api_catalog_snapshot(ROOT / "api-catalog-en.json")
    assert old.total_items == new.total_items == 296
    assert new.content_sha256 == "cf011ec0874c8ee7e9403d2559d4d60380d0347e99a38a5db06a63a619f3170d"
    expected = {
        19: ("Kusarigama", "kusarigama"),
        26: ("Naginata Classic", "naginata-classic"),
        117: ("Stone Tablet", "stone-tablet"),
    }
    changes = {}
    for a, b in zip(old.items, new.items, strict=True):
        assert a.model_id == b.model_id
        assert {k: v for k, v in a.raw.items() if k not in ("name", "imageName")} == {
            k: v for k, v in b.raw.items() if k not in ("name", "imageName")
        }
        if a.raw != b.raw:
            changes[b.model_id] = (b.raw["name"], b.raw["imageName"])
    assert changes == expected
    assert json.loads((ROOT / "i18n-en.json").read_text())["items"] == [r.raw for r in new.items]


def test_mechanics_help_unchanged_but_display_labels_and_language_credit_changed():
    old = json.loads(Path("data/snapshots/2026-10-17/i18n-en.json").read_text())["texts"]
    new = json.loads((ROOT / "i18n-en.json").read_text())["texts"]
    for key in (
        "reference",
        "abilities",
        "elementDescriptions",
        "curseDescriptions",
        "guardianDescriptions",
        "alerts",
        "effects",
    ):
        assert old[key] == new[key]

    def leaves(value, path=""):
        if isinstance(value, dict):
            return {
                key: item
                for k, v in value.items()
                for key, item in leaves(v, path + "." + k).items()
            }
        return {path: value}

    a, b = leaves(old), leaves(new)
    assert {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)} == {
        ".game.cost",
        ".game.costMP",
        ".game.price",
        ".game.priceCP",
        ".langNames.es",
        ".settings.esTranslation",
        ".settings.esTranslationCredit",
    }


def test_current_reviewed_team_predicate_and_ending_membership_are_present():
    client = (ROOT / "official-client.js").read_text()
    assert (
        hashlib.sha256(client.encode()).hexdigest()
        == "5ece06c224b6a7a5d877eb45d22ea18b82a03aaf1b7161cbbdf6a1e23ceab2cd"
    )
    assert "ce(a){var s=this.r\nreturn s===B.p&&this!==a||s!==a.r}" in client
    assert "lU(){var s,r,q,p,o=this.aG()" in client
    assert "if(s.r===B.p)r=A.u([s],t.r)" in client
    assert "$1(a){return t.q.a(a).r===this.a.r}" in client
    for variable, team, name in (
        ("p", 0, "solo"),
        ("ad", 1, "team1"),
        ("ae", 2, "team2"),
        ("af", 3, "team3"),
        ("ag", 4, "team4"),
    ):
        assert f'B.{variable}=new A.bO({team},{team},"{name}")' in client
