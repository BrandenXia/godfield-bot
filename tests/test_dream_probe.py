import asyncio
from datetime import UTC, datetime
from pathlib import Path

from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.dream_probe import (
    DreamProbePhase,
    install_dream_evidence_probe,
    normalize_dream_probe_payload,
    summarize_dream_evidence,
)

CATALOG_PATH = Path("data", "snapshots", "2026-09-21", "api-catalog-en.json")


def catalog() -> ApiCatalogSnapshot:
    return read_api_catalog_snapshot(CATALOG_PATH)


def model_id_for(*, asset: str) -> int:
    matches = [
        item.model_id for item in catalog().items if item.raw.get("imageName") == asset
    ]
    assert len(matches) == 1
    return matches[0]


def payload(
    *,
    items: list[dict[str, object]],
    rendered_paths: list[str],
    curses: list[str] | None = None,
    attack_turn_player_id: int = 1,
    attacks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "hook_errors": 0,
        "raw": {
            "source_sequence": 3,
            "field_number": 7,
            "update_count": 12,
            "attack_turn_player_id": attack_turn_player_id,
            "is_over": False,
            "player_count": 2,
            "self": {
                "player_id": 1,
                "curses": curses if curses is not None else ["dream"],
                "items": items,
            },
            "attacks": attacks or [],
        },
        "rendered_cards": [
            {
                "slot": slot,
                "path": path,
                "x": 100 + slot * 82,
                "y": 500,
                "selectable": slot == 0,
            }
            for slot, path in enumerate(rendered_paths)
        ],
    }


def test_probe_binds_true_and_displayed_cross_category_identity() -> None:
    true_id = model_id_for(asset="bronze-club")
    fake_id = model_id_for(asset="leather-cap")
    sample = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 41,
                    "model_id": true_id,
                    "fake_model_id": fake_id,
                    "used": False,
                }
            ],
            rendered_paths=["/images/items/armor/leather-cap.webp"],
        ),
        catalog(),
        observed_at=datetime(2030, 1, 1, tzinfo=UTC),
    )

    assert sample is not None
    assert sample.phase is DreamProbePhase.TURN
    assert sample.hand_alignment == "exact"
    item = sample.items[0]
    assert item.true_identity is not None
    assert item.true_identity.asset == "bronze-club"
    assert item.true_identity.category == "weapons"
    assert item.displayed_identity is not None
    assert item.displayed_identity.asset == "leather-cap"
    assert item.displayed_identity.category == "armor"
    assert item.selectable is True
    assert item.rendered_matches_displayed is True


def test_probe_preserves_server_hidden_true_identity() -> None:
    fake_id = model_id_for(asset="bronze-club")
    sample = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 42,
                    "model_id": None,
                    "fake_model_id": fake_id,
                    "used": False,
                }
            ],
            rendered_paths=["/images/items/weapons/bronze-club.webp"],
        ),
        catalog(),
    )

    assert sample is not None
    assert sample.items[0].true_identity is None
    assert sample.items[0].displayed_identity is not None
    assert sample.items[0].rendered_matches_displayed is True


def test_probe_aligns_raw_items_to_the_client_sorted_visual_hand() -> None:
    weapon_id = model_id_for(asset="bronze-club")
    armor_id = model_id_for(asset="leather-cap")
    sample = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 51,
                    "model_id": weapon_id,
                    "fake_model_id": None,
                    "used": False,
                },
                {
                    "instance_id": 52,
                    "model_id": armor_id,
                    "fake_model_id": None,
                    "used": False,
                },
            ],
            rendered_paths=[
                "/images/items/armor/leather-cap.webp",
                "/images/items/weapons/bronze-club.webp",
            ],
        ),
        catalog(),
    )

    assert sample.hand_alignment == "exact"
    assert sample.items[0].instance_id == 51
    assert sample.items[0].slot == 1
    assert sample.items[0].selectable is False
    assert sample.items[1].instance_id == 52
    assert sample.items[1].slot == 0
    assert sample.items[1].selectable is True


def test_probe_marks_duplicate_displayed_assets_as_ambiguous() -> None:
    weapon_id = model_id_for(asset="bronze-club")
    sample = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 53,
                    "model_id": weapon_id,
                    "fake_model_id": None,
                    "used": False,
                },
                {
                    "instance_id": 54,
                    "model_id": weapon_id,
                    "fake_model_id": None,
                    "used": False,
                },
            ],
            rendered_paths=[
                "/images/items/weapons/bronze-club.webp",
                "/images/items/weapons/bronze-club.webp",
            ],
        ),
        catalog(),
    )

    assert sample.hand_alignment == "ambiguous"
    assert all(item.slot is None for item in sample.items)
    assert all(item.selectable is None for item in sample.items)
    assert all(item.rendered_matches_displayed is True for item in sample.items)


def test_probe_classifies_defense_from_pending_attack() -> None:
    armor_id = model_id_for(asset="leather-cap")
    sample = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 43,
                    "model_id": armor_id,
                    "fake_model_id": armor_id,
                    "used": False,
                }
            ],
            rendered_paths=["/images/items/armor/leather-cap.webp"],
            attack_turn_player_id=2,
            attacks=[
                {
                    "player_id": 2,
                    "target_player_id": 1,
                    "buying_item_model_id": None,
                }
            ],
        ),
        catalog(),
    )

    assert sample is not None
    assert sample.phase is DreamProbePhase.DEFENSE
    assert sample.awaiting_player_id == 1


def test_probe_retains_one_eligible_health_sample_without_dream() -> None:
    model_id = model_id_for(asset="bronze-club")

    sample = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 44,
                    "model_id": model_id,
                    "fake_model_id": None,
                    "used": False,
                }
            ],
            rendered_paths=["/images/items/weapons/bronze-club.webp"],
            curses=[],
        ),
        catalog(),
    )

    assert sample is not None
    assert sample.dream_active is False
    assert all(not item.disguised for item in sample.items)


def test_report_counts_known_hidden_and_cross_category_evidence() -> None:
    weapon_id = model_id_for(asset="bronze-club")
    armor_id = model_id_for(asset="leather-cap")
    known = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 45,
                    "model_id": weapon_id,
                    "fake_model_id": armor_id,
                    "used": False,
                }
            ],
            rendered_paths=["/images/items/armor/leather-cap.webp"],
        ),
        catalog(),
    )
    hidden = normalize_dream_probe_payload(
        payload(
            items=[
                {
                    "instance_id": 46,
                    "model_id": None,
                    "fake_model_id": weapon_id,
                    "used": False,
                }
            ],
            rendered_paths=["/images/items/weapons/bronze-club.webp"],
        ),
        catalog(),
    )
    assert known is not None and hidden is not None

    report = summarize_dream_evidence((known, hidden))

    assert report.sample_count == 2
    assert report.dream_active_sample_count == 2
    assert report.exact_alignment_count == 2
    assert report.disguised_item_observation_count == 2
    assert report.distinct_disguised_instance_count == 2
    assert report.true_identity_known_count == 1
    assert report.true_identity_hidden_count == 1
    assert report.cross_category_disguise_count == 1
    assert report.self_action_phase_disguise_count == 2


def test_installed_probe_is_passive_and_scoped_to_identity() -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.script = ""

        async def add_init_script(self, *, script: str) -> None:
            self.script = script

    context = FakeContext()

    asyncio.run(install_dream_evidence_probe(context, identity="ロキ-67"))  # type: ignore[arg-type]

    assert "onSnapshot" in context.script
    assert "ロキ-67" in context.script
    assert ".click(" not in context.script
    assert "userId" not in context.script
