import hashlib
import re
from collections.abc import Mapping

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation

NEUTRAL_TEXT_COLOR = "rgb(79, 79, 79)"
WEAPON_ASSET_PATTERN = re.compile(r"^/images/items/weapons/([^/]+)\.(?:png|svg|webp)$")
ARMOR_ASSET_PATTERN = re.compile(r"^/images/items/armor/([^/]+)\.(?:png|svg|webp)$")


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
    *,
    plain_weapon_attacks: Mapping[str, int] | None = None,
    plain_armor_defenses: Mapping[str, int] | None = None,
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
    self_incoming_targeted_effect = (
        state.action_actor is not None
        and state.action_actor != self_player.name
        and state.action_target == self_player.name
        and state.action_artifact_asset_path is not None
    )
    self_incoming_response = (
        self_incoming_targeted_effect
        and state.phase_control == "Forgive"
        and state.phase_control_hit_target_bounds is not None
    )
    self_neutral_defense = (
        self_incoming_targeted_effect
        and state.action_display is not None
        and re.fullmatch(r"ATK\d+", state.action_display) is not None
        and state.action_display_color == NEUTRAL_TEXT_COLOR
    )
    living_opponents = [
        (index, player)
        for index, player in enumerate(state.players)
        if not player.is_self and player.hp > 0
    ]
    selected_weapon = (
        WEAPON_ASSET_PATTERN.fullmatch(state.action_artifact_asset_path)
        if state.action_artifact_asset_path is not None
        else None
    )
    selected_weapon_attack = (
        (plain_weapon_attacks or {}).get(selected_weapon.group(1))
        if selected_weapon is not None
        else None
    )
    selected_armor = (
        ARMOR_ASSET_PATTERN.fullmatch(state.phase_artifact_asset_path)
        if state.phase_artifact_asset_path is not None
        else None
    )
    selected_armor_defense = (
        (plain_armor_defenses or {}).get(selected_armor.group(1))
        if selected_armor is not None
        else None
    )
    self_plain_weapon_confirmation = (
        len(living_opponents) == 1
        and state.action_actor == self_player.name
        and state.action_target == living_opponents[0][1].name
        and selected_weapon_attack is not None
        and state.action_display == f"ATK{selected_weapon_attack}"
        and state.action_display_color == NEUTRAL_TEXT_COLOR
        and state.action_hit_target_bounds is not None
    )
    self_plain_armor_confirmation = (
        self_neutral_defense
        and selected_armor_defense is not None
        and state.phase_control == f"DEF{selected_armor_defense}"
        and state.phase_control_hit_target_bounds is not None
    )
    if self_attack_selection:
        candidates = [artifact for artifact in state.hand if artifact.category == "weapons"]
    elif self_neutral_defense and state.phase_control == "Forgive":
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
    if self_plain_weapon_confirmation and selected_weapon is not None:
        target_index, target = living_opponents[0]
        actions.append(
            LegalAction(
                action_id=f"confirm:attack:{selected_weapon.group(1)}:{target_index}:{target.name}",
                kind=ActionKind.CONFIRM,
                label=f"Confirm the selected attack on {target.name}",
                artifact_asset_path=state.action_artifact_asset_path,
                target_player_index=target_index,
                target_player_name=target.name,
                control_panel="left",
            )
        )
    if self_plain_armor_confirmation and selected_armor is not None:
        actions.append(
            LegalAction(
                action_id=(
                    f"confirm:defense:{selected_armor.group(1)}:"
                    f"{state.self_player_index}:{self_player.name}"
                ),
                kind=ActionKind.CONFIRM,
                label=f"Confirm the selected defense for {self_player.name}",
                artifact_asset_path=state.phase_artifact_asset_path,
                target_player_index=state.self_player_index,
                target_player_name=self_player.name,
                control_panel="right",
            )
        )
    if self_incoming_response:
        actions.append(
            LegalAction(
                action_id="forgive",
                kind=ActionKind.FORGIVE,
                label="Forgive the incoming attack without defending",
            )
        )
    return LegalActionSet(
        state_digest=game_state_digest(state),
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason=(
            "only plain weapon selection, sole-opponent targeting, and neutral plain armor "
            "selection are verified"
        ),
    )
