from godfield_bot.domain.game import GameState
from godfield_bot.domain.outcome import MatchOutcome, MatchResult, SparseTerminalReward
from godfield_bot.domain.run import EventKind
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.run_store import RunStore


def classify_two_player_terminal(state: GameState) -> MatchOutcome | None:
    """Classify only an explicit two-player Training HP terminal state."""

    if state.mode != "training" or len(state.players) != 2:
        return None
    if state.self_player_index >= len(state.players):
        return None
    self_players = [player for player in state.players if player.is_self]
    self_player = state.players[state.self_player_index]
    if len(self_players) != 1 or not self_player.is_self:
        return None
    opponents = tuple(player for player in state.players if not player.is_self)
    if len(opponents) != 1:
        return None

    opponent = opponents[0]
    if self_player.hp > 0 and opponent.hp > 0:
        return None
    if self_player.hp > 0:
        result = MatchResult.WIN
    elif opponent.hp > 0:
        result = MatchResult.LOSS
    else:
        result = MatchResult.DRAW
    return MatchOutcome(
        observed_at=state.observed_at,
        terminal_state_digest=game_state_digest(state),
        self_player_name=self_player.name,
        opponent_player_names=(opponent.name,),
        result=result,
    )


def sparse_terminal_reward(outcome: MatchOutcome) -> SparseTerminalReward:
    value = {
        MatchResult.WIN: 1.0,
        MatchResult.LOSS: -1.0,
        MatchResult.DRAW: 0.0,
    }[outcome.result]
    return SparseTerminalReward(
        observed_at=outcome.observed_at,
        terminal_state_digest=outcome.terminal_state_digest,
        result=outcome.result,
        value=value,
    )


def append_sparse_terminal_events(
    store: RunStore,
    run_id: str,
    state: GameState,
) -> tuple[MatchOutcome, SparseTerminalReward] | None:
    """Append a terminal outcome and its sole reward, or append nothing."""

    outcome = classify_two_player_terminal(state)
    if outcome is None:
        return None
    reward = sparse_terminal_reward(outcome)
    store.append_events(
        run_id,
        (
            (EventKind.MATCH_END, outcome),
            (EventKind.REWARD, reward),
        ),
    )
    return outcome, reward
