import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from godfield import ApiError, ItemCatalog, RoomState, TransportError
from pydantic import ValidationError

from godfield_bot.api_account import PYGODFIELD_REVISION
from godfield_bot.api_catalog import (
    ApiCatalogItem,
    ApiCatalogSnapshot,
    api_catalog_digest,
    item_catalog_from_snapshot,
    read_api_catalog_snapshot,
    write_api_catalog_snapshot,
)
from godfield_bot.api_game import (
    ApiActionKind,
    ApiPolicyDecision,
    command_for_api_action,
    normalize_api_game_state,
    verified_api_actions,
    verified_api_tactical_actions,
)
from godfield_bot.api_runtime import (
    ACCEPTED_PRIVATE_BIBLE_CLIENT_SHA256,
    ApiPolicyName,
    ApiRuntimeError,
    PrivateApiRunConfig,
    _is_confirmed_command_rejection,
    _is_retryable_state_read_error,
    _read_password_file,
    _state_read_retry_delay,
    _within_wall_clock_limit,
    api_environment_fingerprint,
    decide_api_action,
    run_private_api_observer,
)
from godfield_bot.config import AppSettings
from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)
from godfield_bot.domain.run import EventKind, RunStatus
from godfield_bot.run_store import RunStore


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            {"name": "Club", "imageName": "club", "category": "weapons", "atk": 5},
            {
                "name": "Shield",
                "imageName": "shield",
                "category": "armor",
                "def": 8,
            },
            {"name": "Hidden", "category": "miracles", "atk": 99},
            {
                "name": "Strong Shield",
                "imageName": "strong-shield",
                "category": "armor",
                "def": 12,
            },
            {
                "name": "Cleanser",
                "category": "sundries",
                "ability": "removeAllCurses",
            },
            {
                "name": "Blowgun",
                "imageName": "blowgun",
                "category": "weapons",
                "atk": 3,
                "isPlusAtk": True,
            },
            {
                "name": "Romance Water",
                "imageName": "romance-water",
                "category": "sundries",
                "ability": "boostHP",
                "abilityValue": 15,
            },
            {
                "name": "Smile Flower",
                "imageName": "smile-flower",
                "category": "sundries",
                "ability": "boostMP",
                "abilityValue": 5,
            },
            {
                "name": "Dream",
                "imageName": "dream",
                "category": "miracles",
                "ability": "addCurse",
                "cost": 6,
                "element": "wood",
            },
            {
                "name": "Wall",
                "imageName": "wall",
                "category": "miracles",
                "ability": "blockWeapon",
                "cost": 6,
            },
            {
                "name": "Sell",
                "imageName": "sell",
                "category": "trade",
                "ability": "sell",
            },
        ]
    )


def combo_bible() -> BibleSnapshot:
    return BibleSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/",
        language="en",
        client=ClientFingerprint(
            url="https://godfield.net/main.dart.js",
            sha256=ACCEPTED_PRIVATE_BIBLE_CLIENT_SHA256,
        ),
        reference_sections={},
        catalog={
            "weapons": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="club",
                        image_path="/images/items/weapons/club.webp",
                        detail=("Club", "ATK5", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="blowgun",
                        image_path="/images/items/weapons/blowgun.webp",
                        detail=("Blowgun", "+ATK3", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
            "armor": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="shield",
                        image_path="/images/items/armor/shield.webp",
                        detail=("Shield", "DEF8", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="strong-shield",
                        image_path="/images/items/armor/strong-shield.webp",
                        detail=("Strong Shield", "DEF12", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
        },
        total_artifacts=4,
    )


def catalog_snapshot() -> ApiCatalogSnapshot:
    items = tuple(
        ApiCatalogItem(model_id=model.model_id, raw=dict(model.raw)) for model in catalog()
    )
    return ApiCatalogSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/i18n/en.json",
        language="en",
        upstream_revision=PYGODFIELD_REVISION,
        content_sha256=api_catalog_digest(items),
        total_items=len(items),
        items=items,
    )


def terminal_room() -> RoomState:
    return RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 12,
                        "mp": 4,
                        "cp": 9,
                        "team": 0,
                        "items": [{"id": 11, "modelId": 1}],
                    },
                    {
                        "id": 2,
                        "userId": "other-user",
                        "name": "Opponent",
                        "hp": 0,
                        "mp": 2,
                        "cp": 3,
                        "team": 0,
                        "items": [{"id": 99, "modelId": 3}],
                    },
                ],
                "attackTurnPlayerId": 1,
                "attacks": [],
                "gf": 11,
                "updateCount": 17,
                "isOver": True,
            }
        },
        catalog(),
    )


def active_room(*, opponent_hp: int = 35, update_count: int = 12) -> RoomState:
    room = terminal_room()
    room.raw["game"]["players"][1]["hp"] = opponent_hp
    room.raw["game"]["updateCount"] = update_count
    room.raw["game"]["isOver"] = False
    return room


def test_private_api_heuristic_uses_a_reliable_weapon_on_a_cursed_turn() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert state.has_active_curses is True
    assert chosen is not None
    assert chosen.kind is ApiActionKind.USE_ITEM
    assert chosen.item_instance_ids == (11,)
    assert decision.executable is True
    assert decision.rationale == "use the strongest conservative card with a reliable identity"


def test_private_api_heuristic_abstains_from_unverified_cursed_turn_pass() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    room.raw["game"]["players"][0]["items"] = [{"id": 11, "modelId": None, "fakeModelId": 1}]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert legal_actions.actions == ()
    assert chosen is None
    assert decision.executable is False
    assert decision.rationale == "no verified API action is available; abstain without submitting"


def test_private_api_heuristic_prefers_a_verified_curse_cleanser() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    room.raw["game"]["players"][0]["items"] = [{"id": 22, "modelId": 5}]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (22,)
    assert decision.rationale == "remove active curses with a verified cleanser"


def test_tactical_heuristic_uses_strict_attack_combo() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 16, "modelId": 6},
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (11, 16)
    assert decision.rationale == "use the strongest verified attack combination"


def test_tactical_heuristic_uses_least_sufficient_armor_combination() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 20, "modelId": 2},
        {"id": 21, "modelId": 4},
    ]
    room.raw["game"]["attacks"] = [
        {
            "playerId": 2,
            "targetPlayerId": 1,
            "itemModelIds": [1],
            "atk": 15,
        }
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (20, 21)
    assert decision.rationale == "use the least excessive verified defense that prevents all damage"


def test_tactical_heuristic_heals_at_low_hp_unless_attack_is_lethal() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["hp"] = 12
    room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 17, "modelId": 7},
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (17,)
    assert decision.rationale == "restore HP before it falls into common lethal range"

    room.raw["game"]["players"][1]["hp"] = 5
    lethal_state = normalize_api_game_state(room, user_id="loki-user")
    lethal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )
    lethal_decision, lethal = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        lethal_state,
        lethal_actions,
    )

    assert lethal is not None
    assert lethal.item_instance_ids == (11,)
    assert lethal_decision.rationale == "use the least costly attack with potentially lethal power"


def test_tactical_heuristic_uses_affordable_fixed_damage_miracle() -> None:
    room = active_room(opponent_hp=100)
    room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 13, "modelId": 3},
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "miracle-attack:13:3:2"
    assert decision.rationale == "use the strongest verified attack"


def test_tactical_heuristic_focuses_the_weakest_multiplayer_opponent() -> None:
    room = active_room()
    room.raw["game"]["players"].append(
        {
            "id": 3,
            "userId": "weak-user",
            "name": "Weak Opponent",
            "hp": 10,
            "mp": 10,
            "cp": 20,
            "team": 0,
            "items": [],
        }
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    _decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.target_player_id == 3


def test_tactical_heuristic_uses_targeted_curse_instead_of_stalling() -> None:
    room = active_room(opponent_hp=7)
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    room.raw["game"]["players"][0]["mp"] = 10
    room.raw["game"]["players"][0]["items"] = [{"id": 19, "modelId": 9}]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "miracle-curse:19:9:2"
    assert decision.rationale == "use a deterministic targeted curse instead of stalling"


def test_tactical_heuristic_values_verified_special_block_as_full_defense() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 20, "modelId": 2},
        {"id": 30, "modelId": 10},
    ]
    room.raw["game"]["players"][0]["mp"] = 10
    room.raw["game"]["attacks"] = [
        {
            "playerId": 2,
            "targetPlayerId": 1,
            "itemModelIds": [1],
            "atk": 10,
        }
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (30,)
    assert decision.rationale == "use the least excessive verified defense that prevents all damage"


def test_private_api_heuristic_preserves_excess_defense() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 20, "modelId": 2},
        {"id": 21, "modelId": 4},
    ]
    room.raw["game"]["attacks"] = [
        {
            "playerId": 2,
            "targetPlayerId": 1,
            "itemModelIds": [1],
            "atk": 7,
        }
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (20,)
    assert decision.rationale == "use the weakest sufficient conservative defense"


def test_tactical_heuristic_sells_weakest_plain_armor_in_cursed_dead_end() -> None:
    room = active_room()
    room.raw["game"]["players"][0].update(
        {
            "curses": ["dream"],
            "mp": 0,
            "items": [
                {"id": 20, "modelId": 11},
                {"id": 21, "modelId": 2},
                {"id": 22, "modelId": 4},
            ],
        }
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "trade-sell:20:21:2"
    assert chosen.item_instance_ids == (20, 21)
    assert decision.rationale == "offer the weakest verified plain armor rather than stall"


def test_latest_live_cursed_sell_dead_end_has_verified_escape() -> None:
    api_snapshot = read_api_catalog_snapshot(Path("data/snapshots/2026-09-09/api-catalog-en.json"))
    bible = BibleSnapshot.model_validate_json(
        Path("data/snapshots/2026-09-07/bible.json").read_text(encoding="utf-8")
    )
    room = RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "opponent-user",
                        "name": "Opponent",
                        "hp": 55,
                        "mp": 10,
                        "cp": 20,
                        "items": [],
                    },
                    {
                        "id": 2,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 14,
                        "mp": 4,
                        "cp": 20,
                        "curses": ["dream"],
                        "items": [
                            {"id": 3, "modelId": 118},
                            {"id": 5, "modelId": 87},
                            {"id": 6, "modelId": 4},
                            {"id": 7, "modelId": 230},
                            {"id": 8, "modelId": 113},
                            {"id": 9, "modelId": 126},
                            {"id": 4, "modelId": 130},
                            {"id": 1, "modelId": 5},
                            {"id": 2, "modelId": 222, "used": True},
                            {"id": 10, "modelId": 220},
                        ],
                    },
                ],
                "attackTurnPlayerId": 2,
                "attacks": [],
                "gf": 6,
                "updateCount": 12,
                "isOver": False,
            }
        },
        item_catalog_from_snapshot(api_snapshot),
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=bible,
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "trade-sell:6:8:1"
    assert chosen.item_instance_ids == (6, 8)
    assert decision.executable is True


def test_latest_live_cursed_chance_miracle_dead_end_has_verified_escape() -> None:
    api_snapshot = read_api_catalog_snapshot(Path("data/snapshots/2026-09-09/api-catalog-en.json"))
    bible = BibleSnapshot.model_validate_json(
        Path("data/snapshots/2026-09-07/bible.json").read_text(encoding="utf-8")
    )
    room = RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 35,
                        "mp": 10,
                        "cp": 20,
                        "curses": ["dream"],
                        "items": [
                            {"id": 3, "modelId": 118},
                            {"id": 4, "modelId": 5},
                            {"id": 6, "modelId": 236},
                            {"id": 7, "modelId": 163},
                            {"id": 8, "modelId": 5},
                            {"id": 9, "modelId": 207},
                            {"id": 5, "modelId": 202},
                            {"id": 2, "modelId": 227},
                            {"id": 1, "modelId": 25},
                        ],
                    },
                    {
                        "id": 2,
                        "userId": "opponent-user",
                        "name": "Opponent",
                        "hp": 28,
                        "mp": 18,
                        "cp": 20,
                        "items": [],
                    },
                ],
                "attackTurnPlayerId": 1,
                "attacks": [],
                "gf": 5,
                "updateCount": 8,
                "isOver": False,
            }
        },
        item_catalog_from_snapshot(api_snapshot),
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=bible,
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "chance-miracle-attack:2:227:untargeted"
    assert chosen.target_player_id is None
    assert command_for_api_action(chosen).to_dict() == {"itemIds": [2]}
    assert decision.rationale == "use a Bible-verified chance attack rather than stall"
    assert decision.executable is True


def test_latest_live_cursed_cp_miracle_dead_end_has_verified_escape() -> None:
    api_snapshot = read_api_catalog_snapshot(Path("data/snapshots/2026-09-09/api-catalog-en.json"))
    bible = BibleSnapshot.model_validate_json(
        Path("data/snapshots/2026-09-07/bible.json").read_text(encoding="utf-8")
    )
    displayed_items = (
        (1, 208),
        (3, 143),
        (4, 147),
        (5, 16),
        (6, 35),
        (7, 10),
        (8, 26),
        (9, 196),
    )
    room = RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 39,
                        "mp": 10,
                        "cp": 20,
                        "curses": ["dream"],
                        "items": [
                            *(
                                {"id": instance_id, "modelId": model_id, "fakeModelId": model_id}
                                for instance_id, model_id in displayed_items
                            ),
                            {"id": 2, "modelId": 236},
                        ],
                    },
                    {
                        "id": 2,
                        "userId": "opponent-user",
                        "name": "Opponent",
                        "hp": 35,
                        "mp": 10,
                        "cp": 20,
                        "items": [],
                    },
                ],
                "attackTurnPlayerId": 1,
                "attacks": [],
                "gf": 3,
                "updateCount": 16,
                "isOver": False,
            }
        },
        item_catalog_from_snapshot(api_snapshot),
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=bible,
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert sum(item.identity_reliable for item in state.hand) == 1
    assert chosen is not None
    assert chosen.action_id == "cp-utility:boostCP:2:236"
    assert chosen.target_player_id is None
    assert command_for_api_action(chosen).to_dict() == {"itemIds": [2]}
    assert decision.rationale == "gain verified CP rather than stall"
    assert decision.executable is True


def test_latest_live_additive_weapon_dead_end_uses_absorption_instead_of_pass() -> None:
    api_snapshot = read_api_catalog_snapshot(Path("data/snapshots/2026-09-09/api-catalog-en.json"))
    bible = BibleSnapshot.model_validate_json(
        Path("data/snapshots/2026-09-07/bible.json").read_text(encoding="utf-8")
    )
    room = RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 50,
                        "mp": 10,
                        "cp": 20,
                        "items": [
                            {"id": 1, "modelId": 204},
                            {"id": 2, "modelId": 161},
                            {"id": 7, "modelId": 3},
                            {"id": 8, "modelId": 199},
                            {"id": 9, "modelId": 216},
                            {"id": 4, "modelId": 150},
                            {"id": 3, "modelId": 113},
                            {"id": 6, "modelId": 161},
                            {"id": 5, "modelId": 113},
                            {"id": 10, "modelId": 230},
                            {"id": 11, "modelId": 28},
                        ],
                    },
                    {
                        "id": 2,
                        "userId": "opponent-user",
                        "name": "Opponent",
                        "hp": 47,
                        "mp": 40,
                        "cp": 20,
                        "items": [],
                    },
                ],
                "attackTurnPlayerId": 1,
                "attacks": [],
                "gf": 15,
                "updateCount": 23,
                "isOver": False,
            }
        },
        item_catalog_from_snapshot(api_snapshot),
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=bible,
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert "pass" not in {action.action_id for action in legal_actions.actions}
    assert chosen is not None
    assert chosen.action_id == "effect-miracle-attack:9:216:2"
    assert command_for_api_action(chosen).to_dict() == {
        "itemIds": [9],
        "targetPlayerId": 2,
    }
    assert decision.executable is True


def empty_lobby() -> RoomState:
    return RoomState(
        {
            "users": [{"id": "loki-user", "name": "ロキ-67"}],
            "entries": [],
            "userCount": 1,
        },
        catalog(),
    )


def entered_lobby(*, team: int | None) -> RoomState:
    room = empty_lobby()
    room.raw["entries"] = [{"userId": "loki-user", "team": team}]
    return room


class FakeClient:
    user_id = "loki-user"

    def __init__(self) -> None:
        self.joined = False
        self.entered = False
        self.keepalive = False
        self.left = False
        self.matched = False
        self.cancelled_entries = 0
        self.entry_teams: list[int] = []

    def join_room(self, room_id, *, mode, password) -> None:
        assert room_id == "private-room"
        assert str(mode) == "private"
        assert password is None
        self.joined = True

    def enter(self, mode, *, password, lang) -> str:
        assert str(mode) == "private"
        assert password == "astra-vs-humans"
        assert lang == "en"
        self.matched = True
        return "opaque-internal-room-id"

    def make_entry(self, *, team) -> None:
        self.entry_teams.append(team)
        self.entered = True

    def cancel_entry(self) -> None:
        self.cancelled_entries += 1

    def start_keepalive(self) -> None:
        self.keepalive = True

    def state(self) -> RoomState:
        return terminal_room()

    def leave_room(self) -> None:
        self.left = True


def test_private_api_observer_records_terminal_sparse_outcome(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    snapshot = catalog_snapshot()
    write_api_catalog_snapshot(snapshot, snapshot_path)
    client = FakeClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["result"] == "win"
    assert run.outcome["reward"] == 1.0
    assert run.outcome["in_match_actions"] == 0
    assert client.joined and client.keepalive and client.left
    assert client.entered is False
    events = RunStore(database).events(run.run_id)
    assert [event.kind for event in events] == [
        EventKind.OBSERVATION,
        EventKind.GAME_STATE,
        EventKind.LEGAL_ACTIONS,
        EventKind.DECISION,
        EventKind.MATCH_END,
        EventKind.REWARD,
    ]
    state_payload = events[1].payload
    assert state_payload["players"][0]["name"] == "ロキ-67"
    assert state_payload["players"][1]["hand_count"] == 1
    assert state_payload["hand"][0]["instance_id"] == 11
    assert "items" not in state_payload["players"][1]
    assert run.client_sha256 == api_environment_fingerprint(snapshot)


def test_private_api_observer_supports_keyed_matchmaking_without_storing_key(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    client = FakeClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert client.matched is True
    assert client.entered is False
    serialized = run.model_dump_json() + "".join(
        event.model_dump_json() for event in RunStore(database).events(run.run_id)
    )
    assert "astra-vs-humans" not in serialized
    assert "opaque-internal-room-id" not in serialized


def test_password_file_must_be_owner_only(tmp_path) -> None:
    password_file = tmp_path / "room-password"
    password_file.write_text("secret\n", encoding="utf-8")
    password_file.chmod(0o644)

    with pytest.raises(ApiRuntimeError, match="expected 600"):
        _read_password_file(password_file)

    password_file.chmod(0o600)
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600
    assert _read_password_file(password_file) == "secret"


def test_api_policy_configuration_requires_explicit_safe_bounds() -> None:
    with pytest.raises(ValidationError, match="zero in-match action budget"):
        PrivateApiRunConfig(
            room_id="private-room",
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match="explicit match entry"):
        PrivateApiRunConfig(
            room_id="private-room",
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match="explicit match entry"):
        PrivateApiRunConfig(
            room_id="private-room",
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match=r"zero \(unlimited\) or at least 10"):
        PrivateApiRunConfig(room_id="private-room", max_seconds=1)
    with pytest.raises(ValidationError, match="less than or equal to 4"):
        PrivateApiRunConfig(room_id="private-room", entry_team=5)
    with pytest.raises(ValidationError, match="requires explicit match entry"):
        PrivateApiRunConfig(room_id="private-room", entry_team=2)
    with pytest.raises(ValidationError, match="requires a model directory"):
        PrivateApiRunConfig(
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.NEURAL_SHADOW,
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match="only valid for neural shadow policy"):
        PrivateApiRunConfig(
            room_id="private-room",
            model_directory=Path("models/candidate"),
        )
    with pytest.raises(ValidationError, match="less than or equal to 5"):
        PrivateApiRunConfig(room_id="private-room", command_retries=6)
    with pytest.raises(ValidationError, match="less than or equal to 300"):
        PrivateApiRunConfig(room_id="private-room", command_reconcile_seconds=301)


def test_zero_max_seconds_disables_only_the_wall_clock_limit() -> None:
    config = PrivateApiRunConfig(room_id="private-room", max_seconds=0)

    assert config.max_seconds == 0
    assert _within_wall_clock_limit(elapsed=10_000_000, max_seconds=config.max_seconds)
    assert _within_wall_clock_limit(elapsed=9.9, max_seconds=10)
    assert not _within_wall_clock_limit(elapsed=10, max_seconds=10)


def test_tactical_policy_rejects_an_unaccepted_bible_snapshot(tmp_path) -> None:
    catalog_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), catalog_path)
    bible_path = tmp_path / "bible.json"
    unaccepted = combo_bible().model_copy(
        update={
            "client": ClientFingerprint(
                url="https://godfield.net/main.dart.js",
                sha256="f" * 64,
            )
        }
    )
    bible_path.write_text(unaccepted.model_dump_json(), encoding="utf-8")

    with pytest.raises(ApiRuntimeError, match="not been accepted"):
        run_private_api_observer(
            AppSettings(state_root=tmp_path / "state"),
            PrivateApiRunConfig(
                database=tmp_path / "runs.sqlite",
                catalog_snapshot=catalog_path,
                bible_snapshot=bible_path,
                room_id="private-room",
                enter_match=True,
                policy=ApiPolicyName.TACTICAL_HEURISTIC,
                max_in_match_actions=1,
            ),
        )


def test_unlimited_session_stays_in_room_after_a_terminal_match(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakePersistentClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([terminal_room(), empty_lobby()])

        def state(self) -> RoomState:
            try:
                return next(self.states)
            except StopIteration:
                raise KeyboardInterrupt from None

    client = FakePersistentClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            max_seconds=0,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.ABORTED
    assert run.outcome is not None
    assert run.outcome["reason"] == "operator_interrupt"
    assert run.outcome["games_completed"] == 1
    assert [event.kind for event in RunStore(database).events(run.run_id)].count(
        EventKind.MATCH_END
    ) == 1
    assert client.left is True


def test_private_api_heuristic_enters_lobby_and_records_accepted_action(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakePlayingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter(
                [
                    empty_lobby(),
                    active_room(),
                    terminal_room(),
                ]
            )
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakePlayingClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert client.entered is True
    assert client.entry_teams == [0]
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    events = RunStore(database).events(run.run_id)
    assert EventKind.ACTION_RESULT in {event.kind for event in events}
    transitions = [event for event in events if event.kind is EventKind.TRANSITION]
    assert len(transitions) == 1
    assert transitions[0].payload["state_changed"] is True
    assert transitions[0].payload["player_hp_deltas"] == {"2": -35}


def test_private_api_state_read_recovers_without_losing_pending_action(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeFlakyReadClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.responses = iter(
                [
                    active_room(),
                    TransportError("connection exposed-secret"),
                    terminal_room(),
                ]
            )
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            response = next(self.responses)
            if isinstance(response, Exception):
                raise response
            return response

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeFlakyReadClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    sleep_delays: list[float] = []
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", sleep_delays.append)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
            state_read_retries=2,
            state_read_retry_seconds=0.25,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    assert sleep_delays == [1.0, 0.25]
    events = RunStore(database).events(run.run_id)
    read_errors = [event for event in events if event.payload.get("operation") == "read-room-state"]
    assert len(read_errors) == 1
    assert read_errors[0].kind is EventKind.ERROR
    assert read_errors[0].payload["consecutive_failure"] == 1
    assert read_errors[0].payload["retry_scheduled"] is True
    assert "exposed-secret" not in read_errors[0].model_dump_json()
    transitions = [event for event in events if event.kind is EventKind.TRANSITION]
    assert len(transitions) == 1
    assert transitions[0].payload["state_changed"] is True


def test_private_api_state_read_retry_budget_exhaustion_is_explicit(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeFailedReadClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.read_count = 0

        def state(self) -> RoomState:
            self.read_count += 1
            raise TransportError("network failed")

    client = FakeFailedReadClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    sleep_delays: list[float] = []
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", sleep_delays.append)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            max_seconds=10,
            no_progress_seconds=10,
            state_read_retries=1,
            state_read_retry_seconds=0.5,
        ),
    )

    assert run.status is RunStatus.FAILED
    assert run.outcome == {
        "error_type": "ApiRuntimeError",
        "reason": "room-state read retry budget exhausted",
    }
    assert client.read_count == 2
    assert client.left is True
    assert sleep_delays == [0.5]
    read_errors = [
        event
        for event in RunStore(database).events(run.run_id)
        if event.payload.get("operation") == "read-room-state"
    ]
    assert [event.payload["retry_scheduled"] for event in read_errors] == [True, False]


def test_state_read_retry_classification_and_backoff_are_bounded() -> None:
    assert _is_retryable_state_read_error(TransportError("timeout"))
    assert _is_retryable_state_read_error(TransportError("busy", status=503))
    assert not _is_retryable_state_read_error(TransportError("forbidden", status=403))
    assert not _is_retryable_state_read_error(TransportError("invalid", status="503"))
    assert _state_read_retry_delay(failure_number=1, base_seconds=1.0) == 1.0
    assert _state_read_retry_delay(failure_number=20, base_seconds=1.0) == 30.0


def test_command_rejection_retry_classification_is_narrow() -> None:
    assert _is_confirmed_command_rejection(ApiError("submit-command", 400))
    assert not _is_confirmed_command_rejection(ApiError("submit-command", 403))
    assert not _is_confirmed_command_rejection(ApiError("make-entry", 400))
    assert not _is_confirmed_command_rejection(TransportError("ambiguous", status=400))


def test_private_api_retries_confirmed_rejection_after_unchanged_read(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    pass_room = active_room()
    pass_room.raw["game"]["players"][0]["items"] = [{"id": 12, "modelId": 2}]

    class FakeRejectedOnceClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([pass_room, pass_room, terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())
            if len(self.commands) == 1:
                raise ApiError("submit-command", 400, "must-not-be-stored")

    client = FakeRejectedOnceClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
            command_retries=2,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert run.config["command_retries"] == 2
    assert client.commands == [{}, {}]
    events = RunStore(database).events(run.run_id)
    action_results = [event.payload for event in events if event.kind is EventKind.ACTION_RESULT]
    assert [result["server_acknowledged"] for result in action_results] == [False, True]
    rejection_errors = [
        event.payload
        for event in events
        if event.kind is EventKind.ERROR and event.payload.get("operation") == "submit-command"
    ]
    assert rejection_errors == [
        {
            "schema_version": 1,
            "error_type": "ApiError",
            "reason": "private submit command was rejected",
            "operation": "submit-command",
            "action_id": "pass",
            "consecutive_failure": 1,
            "retry_budget": 2,
            "retry_scheduled": True,
            "http_status": 400,
        }
    ]
    assert "must-not-be-stored" not in "".join(event.model_dump_json() for event in events)
    transitions = [event.payload for event in events if event.kind is EventKind.TRANSITION]
    assert [transition["state_changed"] for transition in transitions] == [False, True]
    decisions = [event for event in events if event.kind is EventKind.DECISION]
    assert [
        event.payload["chosen_action_id"]
        for event in decisions
        if event.payload["chosen_action_id"] == "pass"
    ] == ["pass"]


def test_private_api_reconciles_ambiguous_submit_without_retry(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    unchanged = active_room()

    class FakeAmbiguousSubmitClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter(
                [
                    unchanged,
                    TransportError("read must-not-be-stored"),
                    unchanged,
                    terminal_room(),
                ]
            )
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            response = next(self.states)
            if isinstance(response, Exception):
                raise response
            return response

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())
            raise TransportError("ambiguous must-not-be-stored")

    client = FakeAmbiguousSubmitClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert run.config["command_reconcile_seconds"] == 30.0
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    events = RunStore(database).events(run.run_id)
    action_results = [event.payload for event in events if event.kind is EventKind.ACTION_RESULT]
    assert [result["server_acknowledged"] for result in action_results] == [None]
    ambiguous_errors = [
        event.payload
        for event in events
        if event.kind is EventKind.ERROR
        and event.payload.get("reason") == "private submit response was ambiguous"
    ]
    assert ambiguous_errors == [
        {
            "schema_version": 1,
            "error_type": "TransportError",
            "reason": "private submit response was ambiguous",
            "operation": "submit-command",
            "action_id": "use:11:1:2",
            "reconciliation_scheduled": True,
            "reconcile_seconds": 30.0,
        }
    ]
    transitions = [event.payload for event in events if event.kind is EventKind.TRANSITION]
    assert [transition["state_changed"] for transition in transitions] == [True]
    read_errors = [
        event.payload
        for event in events
        if event.kind is EventKind.ERROR and event.payload.get("operation") == "read-room-state"
    ]
    assert [event["retry_scheduled"] for event in read_errors] == [True]
    assert "must-not-be-stored" not in "".join(event.model_dump_json() for event in events)


def test_private_api_ambiguous_submit_reconciliation_is_bounded(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    unchanged = active_room()

    class FakeUnresolvedSubmitClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.state_calls = 0
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            self.state_calls += 1
            return unchanged

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())
            raise TransportError("unresolved must-not-be-stored")

    class AdvancingClock:
        def __init__(self) -> None:
            self.value = 0.0

        def __call__(self) -> float:
            self.value += 0.25
            return self.value

    client = FakeUnresolvedSubmitClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.monotonic", AdvancingClock())
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
            command_reconcile_seconds=1,
        ),
    )

    assert run.status is RunStatus.FAILED
    assert run.outcome == {
        "error_type": "ApiRuntimeError",
        "reason": "ambiguous submit could not be reconciled before timeout",
    }
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    assert client.state_calls >= 2
    events = RunStore(database).events(run.run_id)
    action_results = [event.payload for event in events if event.kind is EventKind.ACTION_RESULT]
    assert [result["server_acknowledged"] for result in action_results] == [None]
    transitions = [event.payload for event in events if event.kind is EventKind.TRANSITION]
    assert [transition["state_changed"] for transition in transitions] == [None]
    assert "must-not-be-stored" not in "".join(event.model_dump_json() for event in events)


def test_private_api_cancels_rejected_command_retry_when_state_changes(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeChangedAfterRejectionClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([active_room(), terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())
            raise ApiError("submit-command", 400)

    client = FakeChangedAfterRejectionClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 0
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    events = RunStore(database).events(run.run_id)
    action_results = [event.payload for event in events if event.kind is EventKind.ACTION_RESULT]
    assert [result["server_acknowledged"] for result in action_results] == [False]
    transitions = [event.payload for event in events if event.kind is EventKind.TRANSITION]
    assert [transition["state_changed"] for transition in transitions] == [True]


def test_private_api_command_rejection_retries_are_bounded(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    unchanged = active_room()

    class FakeRejectedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.state_calls = 0
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            self.state_calls += 1
            return unchanged

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())
            raise ApiError("submit-command", 400)

    client = FakeRejectedClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
            command_retries=2,
        ),
    )

    assert run.status is RunStatus.FAILED
    assert run.outcome is not None
    assert run.outcome["error_type"] == "ApiError"
    assert run.outcome["http_status"] == 400
    assert len(client.commands) == 3
    assert client.state_calls == 3
    events = RunStore(database).events(run.run_id)
    retry_events = [
        event.payload
        for event in events
        if event.kind is EventKind.ERROR and event.payload.get("operation") == "submit-command"
    ]
    assert [event["consecutive_failure"] for event in retry_events] == [1, 2, 3]
    assert [event["retry_scheduled"] for event in retry_events] == [True, True, False]


def test_private_api_tactical_policy_dispatches_verified_combo(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    bible_path = tmp_path / "bible.json"
    bible_path.write_text(combo_bible().model_dump_json(), encoding="utf-8")
    combo_room = active_room()
    combo_room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 16, "modelId": 6},
    ]

    class FakeTacticalClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([combo_room, terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeTacticalClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            bible_snapshot=bible_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.policy_id == ApiPolicyName.TACTICAL_HEURISTIC.value
    assert client.commands == [{"itemIds": [11, 16], "targetPlayerId": 2}]


def test_private_api_tactical_policy_aborts_immediately_on_unsupported_self_turn(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    bible_path = tmp_path / "bible.json"
    bible_path.write_text(combo_bible().model_dump_json(), encoding="utf-8")
    unsupported_room = active_room()
    unsupported_room.raw["game"]["players"][0]["curses"] = ["dream"]
    unsupported_room.raw["game"]["players"][0]["items"] = [
        {"id": 31, "modelId": None, "fakeModelId": 1}
    ]

    class FakeUnsupportedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.state_calls = 0
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            self.state_calls += 1
            return unsupported_room

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeUnsupportedClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            bible_snapshot=bible_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.ABORTED
    assert run.outcome is not None
    assert run.outcome["reason"] == "unsupported_self_turn"
    assert run.outcome["states_recorded"] == 1
    assert client.state_calls == 1
    assert client.commands == []
    events = RunStore(database).events(run.run_id)
    decisions = [event for event in events if event.kind is EventKind.DECISION]
    assert len(decisions) == 1
    assert decisions[0].payload["executable"] is False


def test_private_api_neural_shadow_records_proposal_but_dispatches_heuristic(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakePlayingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([active_room(), terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    class FakeShadowPolicy:
        def __init__(self) -> None:
            self.snapshot = combo_bible()
            self.manifest = SimpleNamespace(
                feature_schema_version=4,
                model_id="shadow-candidate",
                weights_sha256="b" * 64,
            )
            self.policy_id = ApiPolicyName.NEURAL_SHADOW.value
            self.behaviors: list[tuple[str | None, str | None]] = []

        def reset(self) -> None:
            pass

        def decide(self, state, legal_actions):
            proposal = next(
                (
                    action
                    for action in legal_actions.actions
                    if action.kind is ApiActionKind.USE_ITEM
                ),
                None,
            )
            return (
                ApiPolicyDecision(
                    decided_at=state.observed_at,
                    policy_id=ApiPolicyName.NEURAL_SHADOW.value,
                    state_digest=legal_actions.state_digest,
                    chosen_action_id=proposal.action_id if proposal is not None else None,
                    scores={
                        action.action_id: float(action is proposal)
                        for action in legal_actions.actions
                    },
                    rationale="fixture shadow proposal",
                    executable=False,
                    model_id=self.manifest.model_id,
                    model_weights_sha256=self.manifest.weights_sha256,
                ),
                proposal,
            )

        def observe_behavior(self, proposal, behavior) -> None:
            self.behaviors.append(
                (
                    proposal.action_id if proposal is not None else None,
                    behavior.action_id if behavior is not None else None,
                )
            )

    client = FakePlayingClient()
    shadow = FakeShadowPolicy()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr(
        "godfield_bot.api_neural.load_api_combo_shadow_policy",
        lambda model_directory, bible_snapshot: shadow,
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.NEURAL_SHADOW,
            model_directory=tmp_path / "model",
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.config["behavior_policy"] == ApiPolicyName.TACTICAL_HEURISTIC.value
    assert run.config["shadow_policy_id"] == ApiPolicyName.NEURAL_SHADOW.value
    assert run.config["shadow_feature_schema_version"] == 4
    assert run.config["shadow_model_id"] == "shadow-candidate"
    assert run.model_id == "shadow-candidate"
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    assert shadow.behaviors == [("use:11:1:2", "use:11:1:2")]
    decisions = [
        event.payload
        for event in RunStore(database).events(run.run_id)
        if event.kind is EventKind.DECISION
    ]
    assert [decision["policy_id"] for decision in decisions[:2]] == [
        ApiPolicyName.NEURAL_SHADOW.value,
        ApiPolicyName.TACTICAL_HEURISTIC.value,
    ]
    assert decisions[0]["executable"] is False
    assert decisions[1]["executable"] is True


def test_private_api_heuristic_dispatches_reliable_weapon_for_cursed_turn(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    cursed_room = active_room()
    cursed_room.raw["game"]["players"][0]["curses"] = ["dream"]

    class FakeCursedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([cursed_room, terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeCursedClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]


def test_private_api_heuristic_enters_selected_multiplayer_team(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeTeamClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([empty_lobby(), terminal_room()])

        def state(self) -> RoomState:
            return next(self.states)

    client = FakeTeamClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            enter_match=True,
            entry_team=3,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert run.config["entry_team"] == 3
    assert client.entry_teams == [3]
    requested = [
        event.payload
        for event in RunStore(database).events(run.run_id)
        if event.kind is EventKind.OBSERVATION and event.payload.get("phase") == "entry_requested"
    ]
    assert requested == [
        {
            "schema_version": 1,
            "mode": "private",
            "phase": "entry_requested",
            "team": 3,
        }
    ]


def test_private_api_heuristic_switches_an_existing_lobby_team(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeTeamSwitchClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([entered_lobby(team=1), terminal_room()])

        def state(self) -> RoomState:
            return next(self.states)

    client = FakeTeamSwitchClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            enter_match=True,
            entry_team=4,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert client.cancelled_entries == 1
    assert client.entry_teams == [4]


def test_private_api_team_entry_is_not_retried_before_acknowledgement(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    changed_lobby = empty_lobby()
    changed_lobby.raw["users"].append({"id": "other-user", "name": "Opponent"})
    changed_lobby.raw["userCount"] = 2

    class FakeDelayedEntryClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([empty_lobby(), changed_lobby, terminal_room()])

        def state(self) -> RoomState:
            return next(self.states)

    client = FakeDelayedEntryClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            enter_match=True,
            entry_team=2,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert client.entry_teams == [2]
