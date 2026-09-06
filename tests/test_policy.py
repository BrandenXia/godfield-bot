from datetime import UTC, datetime

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.legal_actions import game_state_digest, observation_only_actions
from godfield_bot.policy import SafeObserverPolicy


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
