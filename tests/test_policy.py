from datetime import UTC, datetime

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import (
    Bounds,
    ScreenKind,
    ScreenObservation,
)
from godfield_bot.legal_actions import (
    game_state_digest,
    observation_only_actions,
    verified_browser_actions,
)
from godfield_bot.policy import HeuristicV0Policy, SafeObserverPolicy


def state() -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=0,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=40, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=40, mp=10, money=20, is_self=False),
        ),
        hand=(
            HandArtifact(
                slot=0,
                category="weapons",
                slug="bronze-club",
                asset_path="/images/items/weapons/bronze-club.webp",
                bounds=Bounds(x=200, y=493, width=80, height=80),
            ),
        ),
        scene_layers=("/images/screens/fog.webp",),
    )


def test_state_digest_ignores_observation_time() -> None:
    first = state()
    second = first.model_copy(update={"observed_at": datetime(2030, 1, 1, tzinfo=UTC)})

    assert game_state_digest(first) == game_state_digest(second)


def test_safe_policy_only_selects_non_executable_wait() -> None:
    game_state = state()
    actions = observation_only_actions(game_state)

    decision = SafeObserverPolicy().decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait"]
    assert actions.coverage_complete is False
    assert decision.chosen_action_id == "wait"
    assert decision.executable is False
    assert decision.state_digest == actions.state_digest


def test_heuristic_selects_weapon_only_in_verified_self_phase() -> None:
    initial = state()
    weapon = initial.hand[0].model_copy(update={"hit_target_bounds": initial.hand[0].bounds})
    game_state = initial.model_copy(
        update={
            "hand": (weapon,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy().decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "artifact:0:weapons/bronze-club",
    ]
    assert decision.chosen_action_id == "artifact:0:weapons/bronze-club"
    assert decision.executable is True
