from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from godfield_bot.domain.game import GameState, PlayerState
from godfield_bot.domain.outcome import MatchResult, SparseTerminalReward
from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.outcomes import (
    append_sparse_terminal_events,
    classify_two_player_terminal,
    sparse_terminal_reward,
)
from godfield_bot.run_store import RunStore


def game_state(
    *,
    self_hp: int,
    opponent_hp: int,
    mode: str = "training",
    extra_opponent: bool = False,
) -> GameState:
    players = [
        PlayerState(name="ロキ-67", hp=self_hp, mp=10, money=20, is_self=True),
        PlayerState(name="CPU", hp=opponent_hp, mp=10, money=20, is_self=False),
    ]
    if extra_opponent:
        players.append(
            PlayerState(name="CPU-2", hp=0, mp=0, money=0, is_self=False)
        )
    return GameState(
        observed_at=datetime.now(UTC),
        mode=mode,
        field_number=7,
        self_player_index=0,
        players=tuple(players),
        hand=(),
        scene_layers=(),
    )


@pytest.mark.parametrize(
    ("self_hp", "opponent_hp", "expected"),
    [
        (12, 0, MatchResult.WIN),
        (0, 12, MatchResult.LOSS),
        (0, 0, MatchResult.DRAW),
    ],
)
def test_classifies_explicit_two_player_hp_terminal(
    self_hp: int,
    opponent_hp: int,
    expected: MatchResult,
) -> None:
    outcome = classify_two_player_terminal(
        game_state(self_hp=self_hp, opponent_hp=opponent_hp)
    )

    assert outcome is not None
    assert outcome.result is expected
    assert outcome.self_player_name == "ロキ-67"
    assert outcome.opponent_player_names == ("CPU",)
    assert len(outcome.terminal_state_digest) == 64


@pytest.mark.parametrize(
    "state",
    [
        game_state(self_hp=12, opponent_hp=9),
        game_state(self_hp=12, opponent_hp=0, mode="private"),
        game_state(self_hp=12, opponent_hp=0, extra_opponent=True),
    ],
)
def test_refuses_nonterminal_or_unsupported_state(state: GameState) -> None:
    assert classify_two_player_terminal(state) is None


def test_hidden_stale_opponent_stats_are_not_terminal_evidence() -> None:
    state = game_state(self_hp=12, opponent_hp=0)
    state = state.model_copy(
        update={
            "players": (
                state.players[0],
                state.players[1].model_copy(update={"stats_visible": False}),
            )
        }
    )

    assert classify_two_player_terminal(state) is None


@pytest.mark.parametrize(
    ("self_hp", "opponent_hp", "expected"),
    [(12, 0, 1.0), (0, 12, -1.0), (0, 0, 0.0)],
)
def test_sparse_reward_maps_only_the_terminal_result(
    self_hp: int,
    opponent_hp: int,
    expected: float,
) -> None:
    outcome = classify_two_player_terminal(
        game_state(self_hp=self_hp, opponent_hp=opponent_hp)
    )

    assert outcome is not None
    reward = sparse_terminal_reward(outcome)
    assert reward.result is outcome.result
    assert reward.value == expected
    assert reward.terminal_state_digest == outcome.terminal_state_digest


def test_sparse_reward_rejects_result_value_mismatch() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        SparseTerminalReward(
            observed_at=datetime.now(UTC),
            terminal_state_digest="a" * 64,
            result=MatchResult.LOSS,
            value=1.0,
        )


def test_event_pair_is_appended_only_for_a_classified_terminal(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256="a" * 64,
            policy_id="heuristic-v0",
        )
    )

    assert (
        append_sparse_terminal_events(
            store,
            run.run_id,
            game_state(self_hp=10, opponent_hp=10),
        )
        is None
    )
    terminal = append_sparse_terminal_events(
        store,
        run.run_id,
        game_state(self_hp=10, opponent_hp=0),
    )
    store.finish_run(run.run_id, RunStatus.COMPLETED)

    assert terminal is not None
    events = store.events(run.run_id)
    assert [event.kind for event in events] == [EventKind.MATCH_END, EventKind.REWARD]
    assert events[0].payload["result"] == "win"
    assert events[1].payload["value"] == 1.0
