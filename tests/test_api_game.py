from datetime import UTC, datetime

from godfield import Attack, ItemCatalog, RoomState

from godfield_bot.api_game import (
    ApiActionKind,
    ApiPhase,
    build_api_action_transition,
    command_for_api_action,
    normalize_api_game_state,
    verified_api_actions,
)


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            {"name": "Club", "category": "weapons", "atk": 5},
            {"name": "Shield", "category": "armor", "def": 5},
            {"name": "Fire Shield", "category": "armor", "def": 5, "element": "fire"},
            {
                "name": "Heart Shell",
                "category": "sundries",
                "ability": "removeAllCurses",
            },
        ]
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
    assert [item.instance_id for item in state.hand] == [11, 12]
    assert state.players[1].hand_count == 1
    serialized = state.model_dump_json()
    assert '"instance_id":99' not in serialized
    assert "Fire Shield" not in serialized


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


def test_disguised_cards_never_expose_or_act_on_the_true_model() -> None:
    room = room_state(self_items=[{"id": 11, "modelId": 1, "fakeModelId": 3}])

    state = normalize_api_game_state(room, user_id="loki-user")
    actions = verified_api_actions(room, user_id="loki-user")

    assert state.hand[0].model_id == 3
    assert state.hand[0].name == "Fire Shield"
    assert state.hand[0].category == "armor"
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


def test_unknown_curse_state_blocks_pass_and_attack_actions() -> None:
    actions = verified_api_actions(
        room_state(self_curses=["future-curse"]),
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

    assert [action.action_id for action in actions.actions] == ["use:14:4:untargeted"]
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
