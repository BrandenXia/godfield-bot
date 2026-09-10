from datetime import UTC, datetime

import pytest

from godfield_bot.domain.observation import (
    Bounds,
    ScreenKind,
    ScreenObservation,
    VisibleControl,
    VisibleImage,
    VisibleText,
)
from godfield_bot.game_state import GameStateParseError, parse_game_state
from godfield_bot.legal_actions import verified_browser_actions
from godfield_bot.probe import record_observation_probe
from godfield_bot.run_store import RunStore


def bounds(x: float, y: float, width: float = 30, height: float = 26) -> Bounds:
    return Bounds(x=x, y=y, width=width, height=height)


def text(value: str, x: float, y: float) -> VisibleText:
    return VisibleText(text=value, bounds=bounds(x, y))


def game_observation() -> ScreenObservation:
    return ScreenObservation(
        observed_at=datetime.now(UTC),
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.0", "ロキ-67", "HP", "MP", "$", "CPU"),
        text_elements=(
            text("G.F.0", 580, 11),
            text("ロキ-67", 160, 53),
            text("Pray", 145, 403),
            text("ロキ-67", 810, 131),
            text("HP", 940, 131),
            text("40", 970, 131),
            text("MP", 1000, 131),
            text("10", 1030, 131),
            text("$", 1055, 131),
            text("20", 1085, 131),
            text("CPU", 810, 264),
            text("Incoming detail", 650, 264),
            text("HP", 940, 264),
            text("35", 970, 264),
            text("MP", 1000, 264),
            text("8", 1030, 264),
            text("$", 1055, 264),
            text("12", 1085, 264),
        ),
        controls=(
            VisibleControl(text="", tag="div", bounds=bounds(780, 131, 340, 40)),
            VisibleControl(text="", tag="div", bounds=bounds(780, 264, 340, 40)),
        ),
        images=(
            VisibleImage(path="/images/screens/room.webp", bounds=bounds(100, 38, 1080, 660)),
            VisibleImage(
                path="/images/items/weapons/bronze-club.webp",
                bounds=bounds(200, 493, 80, 80),
            ),
            VisibleImage(
                path="/images/items/armor/iron-shield.webp",
                bounds=bounds(282, 493, 80, 80),
            ),
            VisibleImage(
                path="/images/items/armor/iron-shield.webp",
                bounds=bounds(875, 463, 80, 80),
            ),
        ),
    )


def test_game_observation_normalizes_players_and_hand() -> None:
    state = parse_game_state(game_observation(), identity="ロキ-67")

    assert state.field_number == 0
    assert state.self_player_index == 0
    assert state.action_actor == "ロキ-67"
    assert state.action_display == "Pray"
    assert state.players[1].model_dump(
        exclude={"is_self", "status_marker_color", "hit_target_bounds"}
    ) == {
        "name": "CPU",
        "hp": 35,
        "mp": 8,
        "money": 12,
        "stats_visible": True,
    }
    assert state.players[1].hit_target_bounds == bounds(780, 264, 340, 40)
    assert [artifact.slug for artifact in state.hand] == ["bronze-club", "iron-shield"]


def test_wrapped_hand_is_spatially_ordered_and_excludes_trade_commands() -> None:
    initial = game_observation()
    observation = initial.model_copy(
        update={
            "images": (
                *initial.images,
                VisibleImage(
                    path="/images/items/trade/exchange.webp",
                    bounds=bounds(110, 493, 80, 80),
                    hit_target_bounds=bounds(110, 493, 80, 80),
                ),
                VisibleImage(
                    path="/images/items/weapons/hatchet.webp",
                    bounds=bounds(110, 595, 80, 80),
                    hit_target_bounds=bounds(110, 595, 80, 80),
                ),
                VisibleImage(
                    path="/images/items/fake.webp",
                    bounds=bounds(110, 595, 80, 80),
                    hit_target_bounds=bounds(110, 595, 80, 80),
                ),
            )
        }
    )

    state = parse_game_state(observation, identity="ロキ-67")

    assert [(artifact.slot, artifact.slug) for artifact in state.hand] == [
        (0, "bronze-club"),
        (1, "iron-shield"),
        (2, "hatchet"),
    ]


def test_fog_recovers_hidden_opponent_from_previous_observation() -> None:
    clear = game_observation()
    previous = parse_game_state(clear, identity="ロキ-67")
    fogged = clear.model_copy(
        update={
            "images": (
                *clear.images,
                VisibleImage(
                    path="/images/screens/fog.webp",
                    bounds=bounds(100, 38, 1080, 660),
                ),
                VisibleImage(
                    path="/images/curses/small/fog.webp",
                    bounds=bounds(1003, 155, 30, 16),
                ),
            ),
            "text_elements": tuple(
                element for element in clear.text_elements if abs(element.bounds.y - 264) > 1.5
            ),
            "text": tuple(value for value in clear.text if value != "CPU"),
        }
    )

    state = parse_game_state(
        fogged,
        identity="ロキ-67",
        previous_state=previous,
    )

    assert state.players[0].stats_visible is True
    assert state.players[1].model_dump() == {
        **previous.players[1].model_dump(),
        "stats_visible": False,
        "status_marker_color": None,
    }


def test_fog_recovers_targeted_response_when_player_rows_are_not_clickable() -> None:
    clear = game_observation()
    previous = parse_game_state(clear, identity="ロキ-67")
    retained = tuple(
        element
        for element in clear.text_elements
        if abs(element.bounds.y - 264) > 1.5
        and not (40 <= element.bounds.y <= 80 or 390 <= element.bounds.y <= 450)
    )
    fogged_response = clear.model_copy(
        update={
            "images": (
                *clear.images,
                VisibleImage(
                    path="/images/screens/fog.webp",
                    bounds=bounds(100, 38, 1080, 660),
                ),
                VisibleImage(
                    path="/images/items/sundries/nocturnal-broom.webp",
                    bounds=bounds(125, 103, 80, 80),
                ),
                VisibleImage(
                    path="/images/curses/small/fog.webp",
                    bounds=bounds(1003, 155, 30, 16),
                ),
            ),
            "controls": (VisibleControl(text="", tag="div", bounds=bounds(455, 93, 310, 300)),),
            "text_elements": (
                *retained,
                text("CPU", 160, 53),
                text("ロキ-67", 500, 53),
                text("Forgive", 480, 403),
            ),
        }
    )

    state = parse_game_state(
        fogged_response,
        identity="ロキ-67",
        previous_state=previous,
    )

    assert state.action_actor == "CPU"
    assert state.action_target == "ロキ-67"
    assert state.phase_control == "Forgive"
    assert state.phase_control_hit_target_bounds == bounds(455, 93, 310, 300)
    assert state.players[0].stats_visible is True
    assert state.players[0].hit_target_bounds is None
    assert state.players[1].stats_visible is False
    assert state.players[1].hit_target_bounds is None
    assert [
        action.action_id for action in verified_browser_actions(state, fogged_response).actions
    ] == ["wait", "forgive"]

    mismatched_target = fogged_response.model_copy(
        update={
            "text_elements": tuple(
                element
                if element.text != "ロキ-67" or element.bounds.x != 500
                else text("Other", 500, 53)
                for element in fogged_response.text_elements
            )
        }
    )
    with pytest.raises(GameStateParseError, match="expected at least two player rows"):
        parse_game_state(
            mismatched_target,
            identity="ロキ-67",
            previous_state=previous,
        )


def test_fog_recovers_selected_neutral_armor_when_opponent_row_is_hidden() -> None:
    clear = game_observation()
    previous = parse_game_state(clear, identity="ロキ-67")
    retained = tuple(
        element
        for element in clear.text_elements
        if abs(element.bounds.y - 264) > 1.5
        and not (40 <= element.bounds.y <= 80 or 390 <= element.bounds.y <= 450)
    )
    fogged_defense = clear.model_copy(
        update={
            "images": (
                *clear.images,
                VisibleImage(
                    path="/images/screens/fog.webp",
                    bounds=bounds(100, 38, 1080, 660),
                ),
                VisibleImage(
                    path="/images/items/weapons/crossbow.webp",
                    bounds=bounds(125, 103, 80, 80),
                ),
                VisibleImage(
                    path="/images/items/armor/energy-helm.webp",
                    bounds=bounds(465, 103, 80, 80),
                ),
                VisibleImage(
                    path="/images/curses/small/fog.webp",
                    bounds=bounds(1003, 155, 30, 16),
                ),
            ),
            "controls": (VisibleControl(text="", tag="div", bounds=bounds(455, 93, 310, 300)),),
            "text_elements": (
                *retained,
                text("CPU", 160, 53),
                text("ロキ-67", 500, 53),
                VisibleText(
                    text="ATK2",
                    bounds=bounds(145, 403, 250, 40),
                    color="rgb(79, 79, 79)",
                ),
                VisibleText(
                    text="DEF10",
                    bounds=bounds(485, 403, 250, 40),
                    color="rgb(79, 79, 79)",
                ),
            ),
        }
    )

    state = parse_game_state(
        fogged_defense,
        identity="ロキ-67",
        previous_state=previous,
    )

    assert state.action_actor == "CPU"
    assert state.action_target == "ロキ-67"
    assert state.action_display == "ATK2"
    assert state.phase_control == "DEF10"
    assert state.phase_artifact_asset_path == "/images/items/armor/energy-helm.webp"
    assert state.phase_control_hit_target_bounds == bounds(455, 93, 310, 300)
    assert state.players[0].stats_visible is True
    assert state.players[0].hit_target_bounds is None
    assert state.players[1].stats_visible is False
    assert state.players[1].hit_target_bounds is None
    assert [
        action.action_id
        for action in verified_browser_actions(
            state,
            fogged_defense,
            plain_armor_defenses={"energy-helm": 10},
        ).actions
    ] == ["wait", "confirm:defense:energy-helm:0:ロキ-67"]

    elemental_defense = fogged_defense.model_copy(
        update={
            "text_elements": tuple(
                element.model_copy(update={"color": "rgb(68, 68, 221)"})
                if element.text == "DEF10"
                else element
                for element in fogged_defense.text_elements
            )
        }
    )
    with pytest.raises(GameStateParseError, match="expected at least two player rows"):
        parse_game_state(
            elemental_defense,
            identity="ロキ-67",
            previous_state=previous,
        )


def test_fog_without_a_previous_opponent_fails_closed() -> None:
    clear = game_observation()
    fogged = clear.model_copy(
        update={
            "images": (
                *clear.images,
                VisibleImage(
                    path="/images/screens/fog.webp",
                    bounds=bounds(100, 38, 1080, 660),
                ),
                VisibleImage(
                    path="/images/curses/small/fog.webp",
                    bounds=bounds(1003, 155, 30, 16),
                ),
            ),
            "text_elements": tuple(
                element for element in clear.text_elements if abs(element.bounds.y - 264) > 1.5
            ),
        }
    )

    with pytest.raises(GameStateParseError, match="expected at least two player rows"):
        parse_game_state(fogged, identity="ロキ-67")


def test_non_game_screen_fails_closed() -> None:
    observation = game_observation().model_copy(update={"kind": ScreenKind.TRAINING_SETUP})

    with pytest.raises(GameStateParseError, match="expected game observation"):
        parse_game_state(observation, identity="ロキ-67")


def test_defense_phase_spatial_roles_are_distinct() -> None:
    initial = game_observation()
    retained = tuple(
        element
        for element in initial.text_elements
        if not (40 <= element.bounds.y <= 80 or 390 <= element.bounds.y <= 450)
    )
    observation = initial.model_copy(
        update={
            "controls": (
                *initial.controls,
                VisibleControl(text="", tag="div", bounds=bounds(455, 93, 310, 300)),
            ),
            "text_elements": (
                *retained,
                text("CPU", 160, 53),
                text("ロキ-67", 500, 53),
                VisibleText(
                    text="ATK13",
                    bounds=bounds(145, 403, 250, 40),
                    color="rgb(79, 79, 79)",
                ),
                text("Forgive", 480, 403),
            ),
        }
    )

    state = parse_game_state(observation, identity="ロキ-67")

    assert state.action_actor == "CPU"
    assert state.action_target == "ロキ-67"
    assert state.action_display == "ATK13"
    assert state.action_display_color == "rgb(79, 79, 79)"
    assert state.phase_control == "Forgive"
    assert state.phase_control_hit_target_bounds == bounds(455, 93, 310, 300)


def test_selected_action_artifact_is_separate_from_the_hand() -> None:
    initial = game_observation()
    observation = initial.model_copy(
        update={
            "controls": (
                *initial.controls,
                VisibleControl(text="", tag="div", bounds=bounds(115, 93, 310, 300)),
            ),
            "images": (
                *initial.images,
                VisibleImage(
                    path="/images/items/weapons/bronze-club.webp",
                    bounds=bounds(125, 103, 80, 80),
                ),
            ),
        }
    )

    state = parse_game_state(observation, identity="ロキ-67")

    assert state.action_artifact_asset_path == "/images/items/weapons/bronze-club.webp"
    assert state.action_hit_target_bounds == bounds(115, 93, 310, 300)


def test_low_action_artifact_is_not_lost_below_a_large_guardian() -> None:
    initial = game_observation()
    observation = initial.model_copy(
        update={
            "images": (
                *initial.images,
                VisibleImage(
                    path="/images/guardians/large/uranus.webp",
                    bounds=bounds(120, 93, 300, 300),
                ),
                VisibleImage(
                    path="/images/items/guardians/blessing.webp",
                    bounds=bounds(125, 303, 80, 80),
                ),
            )
        }
    )

    state = parse_game_state(observation, identity="ロキ-67")

    assert state.action_artifact_asset_path == "/images/items/guardians/blessing.webp"


def test_selected_phase_artifact_is_separate_from_the_hand() -> None:
    initial = game_observation()
    observation = initial.model_copy(
        update={
            "controls": (
                *initial.controls,
                VisibleControl(text="", tag="div", bounds=bounds(455, 93, 310, 300)),
            ),
            "images": (
                *initial.images,
                VisibleImage(
                    path="/images/items/armor/iron-shield.webp",
                    bounds=bounds(465, 103, 80, 80),
                ),
            ),
            "text_elements": (*initial.text_elements, text("DEF4", 485, 403)),
        }
    )

    state = parse_game_state(observation, identity="ロキ-67")

    assert state.phase_artifact_asset_path == "/images/items/armor/iron-shield.webp"
    assert state.phase_control_hit_target_bounds == bounds(455, 93, 310, 300)


def test_observation_probe_records_full_non_executing_policy_pass(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")

    run = record_observation_probe(
        store,
        game_observation(),
        identity="ロキ-67",
        client_sha256="a" * 64,
    )

    assert run.status.value == "aborted"
    assert run.outcome == {"reason": "observation_only_policy", "external_actions": 0}
    assert [event.kind.value for event in store.events(run.run_id)] == [
        "observation",
        "game_state",
        "legal_actions",
        "decision",
    ]
