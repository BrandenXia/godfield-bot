import hashlib

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation


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


def verified_browser_actions(
    state: GameState,
    observation: ScreenObservation,
) -> LegalActionSet:
    """Expose only semantic in-match controls verified in the current DOM."""

    if observation.kind is not ScreenKind.GAME:
        raise ValueError("verified actions require a gameplay observation")
    actions = [
        LegalAction(
            action_id="wait",
            kind=ActionKind.WAIT,
            label="Capture another observation without clicking the game UI",
        )
    ]
    self_player = state.players[state.self_player_index]
    self_selection_phase = state.action_actor == self_player.name and state.action_display == "Pray"
    if self_selection_phase and all(
        artifact.hit_target_bounds is not None for artifact in state.hand
    ):
        actions.extend(
            LegalAction(
                action_id=f"artifact:{artifact.slot}:{artifact.category}/{artifact.slug}",
                kind=ActionKind.SELECT_ARTIFACT,
                label=f"Select {artifact.category}/{artifact.slug}",
                artifact_slot=artifact.slot,
                artifact_asset_path=artifact.asset_path,
            )
            for artifact in state.hand
        )
    return LegalActionSet(
        state_digest=game_state_digest(state),
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason="artifact use, target, confirm, and cancel phases remain unverified",
    )
