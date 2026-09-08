from datetime import UTC, datetime

from godfield import Attack, ItemCatalog, RoomState

from godfield_bot.api_game import (
    ApiActionKind,
    ApiPhase,
    build_api_action_transition,
    command_for_api_action,
    normalize_api_game_state,
    verified_api_actions,
    verified_api_combo_actions,
    verified_api_tactical_actions,
)
from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            {"name": "Club", "imageName": "club", "category": "weapons", "atk": 5},
            {"name": "Shield", "imageName": "shield", "category": "armor", "def": 5},
            {
                "name": "Fire Shield",
                "imageName": "fire-shield",
                "category": "armor",
                "def": 5,
                "element": "fire",
            },
            {
                "name": "Heart Shell",
                "category": "sundries",
                "ability": "removeAllCurses",
            },
            {
                "name": "Blowgun",
                "imageName": "blowgun",
                "category": "weapons",
                "atk": 1,
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
                "name": "Flame",
                "imageName": "flame",
                "category": "miracles",
                "atk": 10,
                "cost": 5,
                "element": "fire",
            },
        ]
    )


def combo_bible() -> BibleSnapshot:
    return BibleSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/",
        language="en",
        client=ClientFingerprint(url="https://godfield.net/main.dart.js", sha256="a" * 64),
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
                        detail=("Blowgun", "+ATK1", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
            "armor": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="shield",
                        image_path="/images/items/armor/shield.webp",
                        detail=("Shield", "DEF5", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="fire-shield",
                        image_path="/images/items/armor/fire-shield.webp",
                        detail=("Fire Shield", "DEF5", "$1", "Gift Rate: 1/500"),
                        element_image_paths=("/images/elements/fire.webp",),
                    ),
                )
            ),
        },
        total_artifacts=4,
    )


def room_state(
    *,
    turn: int = 1,
    attacks: list[dict[str, object]] | None = None,
    self_items: list[dict[str, object]] | None = None,
    self_curses: list[str] | None = None,
) -> RoomState:
    return RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 40,
                        "mp": 10,
                        "cp": 20,
                        "team": 0,
                        "items": (
                            self_items
                            if self_items is not None
                            else [
                                {"id": 11, "modelId": 1},
                                {"id": 12, "modelId": 2},
                            ]
                        ),
                        "curses": self_curses if self_curses is not None else [],
                    },
                    {
                        "id": 2,
                        "userId": "other-user",
                        "name": "Opponent",
                        "hp": 35,
                        "mp": 8,
                        "cp": 19,
                        "team": 0,
                        "items": [{"id": 99, "modelId": 3}],
                    },
                ],
                "attackTurnPlayerId": turn,
                "attacks": attacks or [],
                "gf": 7,
                "updateCount": 12,
                "isOver": False,
            }
        },
        catalog(),
    )


def test_normalization_keeps_only_self_hand_card_identities() -> None:
    observed_at = datetime.now(UTC)

    state = normalize_api_game_state(
        room_state(),
        user_id="loki-user",
        observed_at=observed_at,
    )

    assert state.phase is ApiPhase.TURN
    assert state.observed_at == observed_at
    assert state.self_player_id == 1
    assert state.schema_version == 4
    assert state.has_active_curses is False
    assert [item.instance_id for item in state.hand] == [11, 12]
    assert [item.asset for item in state.hand] == ["club", "shield"]
    assert all(item.identity_reliable for item in state.hand)
    assert state.players[1].hand_count == 1
    serialized = state.model_dump_json()
    assert '"instance_id":99' not in serialized
    assert "Fire Shield" not in serialized


def test_normalization_exposes_tactical_item_values() -> None:
    state = normalize_api_game_state(
        room_state(self_items=[{"id": 16, "modelId": 6}]),
        user_id="loki-user",
    )

    assert state.hand[0].ability == "boostHP"
    assert state.hand[0].ability_value == 15
    assert state.hand[0].is_plus_attack is False


def test_turn_actions_use_only_safe_single_weapons_and_named_targets() -> None:
    actions = verified_api_actions(room_state(), user_id="loki-user")

    assert [action.kind for action in actions.actions] == [
        ApiActionKind.PASS,
        ApiActionKind.USE_ITEM,
    ]
    attack = actions.actions[1]
    assert attack.item_instance_ids == (11,)
    assert attack.item_model_ids == (1,)
    assert attack.target_player_id == 2
    assert command_for_api_action(attack).to_dict() == {
        "itemIds": [11],
        "targetPlayerId": 2,
    }


def test_combo_actions_expose_only_base_plus_booster_macros() -> None:
    room = room_state(
        self_items=[
            {"id": 11, "modelId": 1},
            {"id": 15, "modelId": 5},
        ]
    )

    conservative = verified_api_actions(room, user_id="loki-user")
    actions = verified_api_combo_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    assert [action.action_id for action in conservative.actions] == [
        "pass",
        "use:11:1:2",
    ]
    assert [action.action_id for action in actions.actions] == [
        "pass",
        "use:11:1:2",
        "combo-attack:11-15:2",
    ]
    combo = actions.actions[-1]
    assert combo.item_instance_ids == (11, 15)
    assert command_for_api_action(combo).to_dict() == {
        "itemIds": [11, 15],
        "targetPlayerId": 2,
    }


def test_combo_actions_fail_closed_when_api_stats_differ_from_bible() -> None:
    room = room_state(
        self_items=[
            {"id": 11, "modelId": 1},
            {"id": 15, "modelId": 5},
        ]
    )
    room._catalog.get(5).raw["atk"] = 2

    actions = verified_api_combo_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    assert [action.action_id for action in actions.actions] == [
        "pass",
        "use:11:1:2",
    ]


def test_combo_actions_expose_compatible_multi_armor_macro() -> None:
    room = room_state(
        attacks=[
            {
                "playerId": 2,
                "targetPlayerId": 1,
                "itemModelIds": [1],
            }
        ],
        self_items=[
            {"id": 12, "modelId": 2},
            {"id": 13, "modelId": 3},
        ],
    )

    actions = verified_api_combo_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    assert [action.action_id for action in actions.actions] == [
        "pass",
        "defend:12:2",
        "defend:13:3",
        "combo-defense:12-13",
    ]
    assert command_for_api_action(actions.actions[-1]).to_dict() == {"itemIds": [12, 13]}


def test_tactical_actions_add_deterministic_utility_and_targeted_miracles() -> None:
    room = room_state(
        self_items=[
            {"id": 16, "modelId": 6},
            {"id": 17, "modelId": 7},
            {"id": 18, "modelId": 8},
        ]
    )

    actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    assert [action.action_id for action in actions.actions] == [
        "pass",
        "utility:boostHP:16:6",
        "utility:boostMP:17:7",
        "miracle-attack:18:8:2",
    ]
    assert command_for_api_action(actions.actions[-1]).to_dict() == {
        "itemIds": [18],
        "targetPlayerId": 2,
    }


def test_tactical_actions_exclude_unaffordable_or_disguised_cards() -> None:
    room = room_state(
        self_items=[
            {"id": 16, "modelId": 8},
            {"id": 17, "modelId": 6, "fakeModelId": 7},
        ]
    )
    room.raw["game"]["players"][0]["mp"] = 4

    actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    assert [action.action_id for action in actions.actions] == ["pass"]


def test_turn_actions_never_target_a_member_of_the_selected_team() -> None:
    room = room_state()
    room.raw["game"]["players"][0]["team"] = 2
    room.raw["game"]["players"][1]["team"] = 2
    room.raw["game"]["players"].append(
        {
            "id": 3,
            "userId": "enemy-user",
            "name": "Enemy",
            "hp": 35,
            "mp": 8,
            "cp": 19,
            "team": 1,
            "items": [],
        }
    )

    actions = verified_api_actions(room, user_id="loki-user")
    attack_targets = {
        action.target_player_id
        for action in actions.actions
        if action.kind is ApiActionKind.USE_ITEM
    }

    assert attack_targets == {3}


def test_disguised_cards_never_expose_or_act_on_the_true_model() -> None:
    room = room_state(self_items=[{"id": 11, "modelId": 1, "fakeModelId": 3}])

    state = normalize_api_game_state(room, user_id="loki-user")
    actions = verified_api_actions(room, user_id="loki-user")

    assert state.hand[0].model_id == 3
    assert state.hand[0].name == "Fire Shield"
    assert state.hand[0].category == "armor"
    assert state.hand[0].identity_reliable is False
    assert "Club" not in state.model_dump_json()
    assert [action.action_id for action in actions.actions] == ["pass"]


def test_transient_hand_placeholder_without_model_id_is_preserved_but_never_used() -> None:
    room = room_state(self_items=[{"id": 11, "modelId": None}])

    state = normalize_api_game_state(room, user_id="loki-user")
    actions = verified_api_actions(room, user_id="loki-user")

    assert state.hand[0].instance_id == 11
    assert state.hand[0].model_id is None
    assert state.hand[0].name is None
    assert [action.action_id for action in actions.actions] == ["pass"]


def test_disguised_placeholder_uses_only_its_visible_model_id() -> None:
    room = room_state(self_items=[{"id": 11, "modelId": None, "fakeModelId": 3}])

    state = normalize_api_game_state(room, user_id="loki-user")

    assert state.hand[0].model_id == 3
    assert state.hand[0].name == "Fire Shield"


def test_transient_hand_placeholder_without_instance_id_is_never_actionable() -> None:
    room = room_state(self_items=[{"id": None, "modelId": 1}])

    state = normalize_api_game_state(room, user_id="loki-user")
    actions = verified_api_actions(room, user_id="loki-user")

    assert state.hand[0].instance_id is None
    assert state.hand[0].model_id == 1
    assert state.hand[0].name == "Club"
    assert [action.action_id for action in actions.actions] == ["pass"]


def test_empty_transient_hand_placeholder_is_preserved_as_unknown() -> None:
    room = room_state(self_items=[{}])

    state = normalize_api_game_state(room, user_id="loki-user")

    assert state.hand[0].instance_id is None
    assert state.hand[0].model_id is None
    assert state.hand[0].name is None


def test_unknown_curse_state_keeps_reliable_weapon_and_omits_unverified_pass() -> None:
    state = normalize_api_game_state(
        room_state(self_curses=["future-curse"]),
        user_id="loki-user",
    )
    actions = verified_api_actions(
        room_state(self_curses=["future-curse"]),
        user_id="loki-user",
    )

    assert state.has_active_curses is True
    assert [action.action_id for action in actions.actions] == ["use:11:1:2"]
    assert command_for_api_action(actions.actions[0]).to_dict() == {
        "itemIds": [11],
        "targetPlayerId": 2,
    }


def test_unknown_curse_state_abstains_when_every_card_identity_is_unreliable() -> None:
    actions = verified_api_actions(
        room_state(
            self_curses=["future-curse"],
            self_items=[{"id": 11, "modelId": None, "fakeModelId": 1}],
        ),
        user_id="loki-user",
    )

    assert actions.actions == ()


def test_cursed_turn_can_use_reviewed_untargeted_curse_removal() -> None:
    actions = verified_api_actions(
        room_state(
            self_curses=["future-curse"],
            self_items=[
                {"id": 11, "modelId": 1},
                {"id": 14, "modelId": 4},
            ],
        ),
        user_id="loki-user",
    )

    assert [action.action_id for action in actions.actions] == [
        "use:14:4:untargeted",
        "use:11:1:2",
    ]
    assert command_for_api_action(actions.actions[0]).to_dict() == {"itemIds": [14]}


def test_defense_actions_delegate_element_legality_to_pygodfield() -> None:
    room = room_state(
        attacks=[
            {
                "playerId": 2,
                "targetPlayerId": 1,
                "itemModelIds": [1],
            }
        ]
    )
    actions = verified_api_actions(room, user_id="loki-user")

    assert normalize_api_game_state(room, user_id="loki-user").phase is ApiPhase.DEFENSE
    assert [action.action_id for action in actions.actions] == ["pass", "defend:12:2"]
    assert command_for_api_action(actions.actions[0]).to_dict() == {}
    assert command_for_api_action(actions.actions[1]).to_dict() == {"itemIds": [12]}


def test_purchase_and_wait_phases_never_guess() -> None:
    purchase = room_state(
        attacks=[
            {
                "playerId": 1,
                "targetPlayerId": 2,
                "buyingItemModelId": 3,
            }
        ]
    )
    purchase_actions = verified_api_actions(purchase, user_id="loki-user")
    waiting_actions = verified_api_actions(room_state(turn=2), user_id="loki-user")

    assert normalize_api_game_state(purchase, user_id="loki-user").phase is ApiPhase.PURCHASE
    assert len(purchase_actions.actions) == 1
    assert purchase_actions.actions[0].kind is ApiActionKind.DECLINE_PURCHASE
    assert command_for_api_action(purchase_actions.actions[0]).to_dict() == {"bought": False}
    assert normalize_api_game_state(room_state(turn=2), user_id="loki-user").phase is ApiPhase.WAIT
    assert waiting_actions.actions == ()


def test_pending_attack_uses_pygodfield_aggregation() -> None:
    room = room_state(
        attacks=[
            {
                "playerId": 2,
                "targetPlayerId": 1,
                "itemModelIds": [1],
                "atk": 9,
            }
        ]
    )

    state = normalize_api_game_state(room, user_id="loki-user")

    assert isinstance(room.game.pending_attack, Attack)
    assert state.pending_attack is not None
    assert state.pending_attack.attack == 9
    assert state.pending_attack.item_model_ids == (1,)


def test_api_action_transition_records_state_and_public_hp_delta() -> None:
    before_room = room_state()
    after_room = room_state()
    after_room.raw["game"]["players"][1]["hp"] = 30
    after_room.raw["game"]["updateCount"] = 13
    action = verified_api_actions(before_room, user_id="loki-user").actions[1]

    transition = build_api_action_transition(
        action,
        normalize_api_game_state(before_room, user_id="loki-user"),
        normalize_api_game_state(after_room, user_id="loki-user"),
    )

    assert transition.state_changed is True
    assert transition.update_count_delta == 1
    assert transition.player_hp_deltas == {2: -5}
    assert transition.after_state is not None
