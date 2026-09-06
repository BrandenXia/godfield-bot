from datetime import UTC, datetime

import pytest

from godfield_bot.domain.observation import (
    Bounds,
    ScreenKind,
    ScreenObservation,
    VisibleImage,
    VisibleText,
)
from godfield_bot.game_state import GameStateParseError, parse_game_state
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
            text("HP", 940, 264),
            text("35", 970, 264),
            text("MP", 1000, 264),
            text("8", 1030, 264),
            text("$", 1055, 264),
            text("12", 1085, 264),
        ),
        controls=(),
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
    assert state.players[1].model_dump(exclude={"is_self", "status_marker_color"}) == {
        "name": "CPU",
        "hp": 35,
        "mp": 8,
        "money": 12,
    }
    assert [artifact.slug for artifact in state.hand] == ["bronze-club", "iron-shield"]


def test_non_game_screen_fails_closed() -> None:
    observation = game_observation().model_copy(update={"kind": ScreenKind.TRAINING_SETUP})

    with pytest.raises(GameStateParseError, match="expected game observation"):
        parse_game_state(observation, identity="ロキ-67")


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
