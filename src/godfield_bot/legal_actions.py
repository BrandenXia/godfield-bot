import hashlib
import re

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation

NEUTRAL_TEXT_COLOR = "rgb(79, 79, 79)"


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
    self_attack_selection = (
        state.action_actor == self_player.name and state.action_display == "Pray"
    )
    self_neutral_defense = (
        state.action_actor is not None
        and state.action_actor != self_player.name
        and state.action_target == self_player.name
        and state.action_display is not None
        and re.fullmatch(r"ATK\d+", state.action_display) is not None
        and state.action_display_color == NEUTRAL_TEXT_COLOR
        and state.phase_control == "Forgive"
    )
    if self_attack_selection:
        candidates = [artifact for artifact in state.hand if artifact.category == "weapons"]
    elif self_neutral_defense:
        candidates = [artifact for artifact in state.hand if artifact.category == "armor"]
    else:
        candidates = []
    if candidates and all(artifact.hit_target_bounds is not None for artifact in candidates):
        actions.extend(
            LegalAction(
                action_id=f"artifact:{artifact.slot}:{artifact.category}/{artifact.slug}",
                kind=ActionKind.SELECT_ARTIFACT,
                label=f"Select {artifact.category}/{artifact.slug}",
                artifact_slot=artifact.slot,
                artifact_asset_path=artifact.asset_path,
            )
            for artifact in candidates
        )
    return LegalActionSet(
        state_digest=game_state_digest(state),
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason="artifact use, target, confirm, and cancel phases remain unverified",
    )
