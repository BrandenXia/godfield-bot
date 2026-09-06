import hashlib

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState


def game_state_digest(state: GameState) -> str:
    canonical = state.model_dump_json(exclude={"observed_at"})
    return hashlib.sha256(canonical.encode()).hexdigest()


def observation_only_actions(state: GameState) -> LegalActionSet:
    """Return the sole proven-safe action until turn and card contracts are verified."""

    return LegalActionSet(
        state_digest=game_state_digest(state),
        actions=(
            LegalAction(
                action_id="wait",
                kind=ActionKind.WAIT,
                label="Capture another observation without clicking the game UI",
            ),
        ),
        coverage_complete=False,
        blocked_reason="turn ownership and in-match hit targets are not yet verified",
    )
