import hashlib
import re
from collections.abc import Mapping

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation
from godfield_bot.weapon_rules import WeaponAttackRule, resolved_weapon_attack_displays

NEUTRAL_TEXT_COLOR = "rgb(79, 79, 79)"
WEAPON_ASSET_PATTERN = re.compile(r"^/images/items/weapons/([^/]+)\.(?:png|svg|webp)$")
MIRACLE_ASSET_PATTERN = re.compile(r"^/images/items/miracles/([^/]+)\.(?:png|svg|webp)$")
ARMOR_ASSET_PATTERN = re.compile(r"^/images/items/armor/([^/]+)\.(?:png|svg|webp)$")
ITEM_ASSET_PATTERN = re.compile(r"^/images/items/[^/]+/[^/]+\.(?:png|svg|webp)$")
PROBABILISTIC_ATTACK_PATTERN = re.compile(r"^\d+%ATK(\d+)$")
VERIFIED_RANDOM_TARGET_WEAPONS = frozenset({"dangerous-pestle"})


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
    verified_weapon_attacks: Mapping[str, WeaponAttackRule] | None = None,
    verified_miracle_attacks: Mapping[str, tuple[int, int, str]] | None = None,
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
    observed_action_assets = tuple(
        image.path
        for image in observation.images
        if ITEM_ASSET_PATTERN.fullmatch(image.path) is not None
        and 100 <= image.bounds.x <= 450
        and 80 <= image.bounds.y <= 380
        and 60 <= image.bounds.width <= 100
        and 60 <= image.bounds.height <= 100
        and image.hit_target_bounds is None
    )
    incoming_context_assets = observed_action_assets or (
        (state.action_artifact_asset_path,) if state.action_artifact_asset_path is not None else ()
    )
    self_attack_selection = (
        state.action_actor == self_player.name and state.action_display == "Pray"
    )
    self_targeted_interaction = (
        state.action_actor is not None
        and state.action_actor != self_player.name
        and state.action_target == self_player.name
    )
    self_incoming_targeted_effect = (
        self_targeted_interaction and state.action_artifact_asset_path is not None
    )
    self_incoming_response = (
        self_targeted_interaction
        and bool(incoming_context_assets)
        and state.phase_control == "Forgive"
        and state.phase_control_hit_target_bounds is not None
    )
    reflected_context_assets = (
        (state.phase_artifact_asset_path,)
        if state.phase_artifact_asset_path is not None
        else ()
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
    self_reflected_response = (
        len(living_opponents) == 1
        and state.action_actor == self_player.name
        and state.action_target == living_opponents[0][1].name
        and state.action_display == "Forgive"
        and state.action_hit_target_bounds is not None
        and bool(reflected_context_assets)
        and state.phase_control is not None
        and re.fullmatch(r"(?:\d+%)?ATK\d+", state.phase_control) is not None
        and state.phase_control_hit_target_bounds is None
    )
    selected_weapon = (
        WEAPON_ASSET_PATTERN.fullmatch(state.action_artifact_asset_path)
        if state.action_artifact_asset_path is not None
        else None
    )
    selected_weapon_rule = (
        (verified_weapon_attacks or {}).get(selected_weapon.group(1))
        if selected_weapon is not None
        else None
    )
    selected_miracle = (
        MIRACLE_ASSET_PATTERN.fullmatch(state.action_artifact_asset_path)
        if state.action_artifact_asset_path is not None
        else None
    )
    selected_miracle_rule = (
        (verified_miracle_attacks or {}).get(selected_miracle.group(1))
        if selected_miracle is not None
        else None
    )
    selected_attack_slug = (
        selected_weapon.group(1)
        if selected_weapon is not None and selected_weapon_rule is not None
        else selected_miracle.group(1)
        if selected_miracle is not None and selected_miracle_rule is not None
        else None
    )
    selected_attack_displays: tuple[str, ...] = ()
    if selected_weapon_rule is not None:
        selected_attack_displays = resolved_weapon_attack_displays(
            selected_weapon_rule,
            mp=self_player.mp,
        )
        chance = PROBABILISTIC_ATTACK_PATTERN.fullmatch(selected_weapon_rule[0])
        if chance is not None:
            selected_attack_displays += (f"ATK{chance.group(1)}",)
    elif selected_miracle_rule is not None and selected_miracle_rule[1] <= self_player.mp:
        selected_attack_displays = (f"ATK{selected_miracle_rule[0]}",)
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
    self_fixed_attack_confirmation = (
        len(living_opponents) == 1
        and state.action_actor == self_player.name
        and state.action_target == living_opponents[0][1].name
        and selected_attack_slug is not None
        and state.action_display in selected_attack_displays
        and state.action_hit_target_bounds is not None
    )
    self_untargeted_attack_confirmation = (
        len(living_opponents) == 1
        and state.action_actor == self_player.name
        and state.action_target is None
        and selected_weapon is not None
        and selected_weapon_rule is not None
        and (
            PROBABILISTIC_ATTACK_PATTERN.fullmatch(selected_weapon_rule[0]) is not None
            or selected_weapon.group(1) in VERIFIED_RANDOM_TARGET_WEAPONS
        )
        and state.action_display in selected_attack_displays
        and state.action_hit_target_bounds is not None
    )
    self_plain_armor_confirmation = (
        self_neutral_defense
        and selected_armor_defense is not None
        and state.phase_control == f"DEF{selected_armor_defense}"
        and state.phase_control_hit_target_bounds is not None
    )
    if self_attack_selection:
        candidates = [
            artifact
            for artifact in state.hand
            if (
                artifact.category == "weapons"
                and artifact.slug in (verified_weapon_attacks or {})
                and artifact.hit_target_bounds is not None
            )
            or (
                artifact.category == "miracles"
                and (rule := (verified_miracle_attacks or {}).get(artifact.slug)) is not None
                and rule[1] <= self_player.mp
                and artifact.hit_target_bounds is not None
            )
        ]
        if (
            state.action_hit_target_bounds is not None
            and not any(
                artifact.category == "weapons"
                and artifact.slug in (verified_weapon_attacks or {})
                and artifact.hit_target_bounds is not None
                for artifact in state.hand
            )
        ):
            actions.append(
                LegalAction(
                    action_id="pass",
                    kind=ActionKind.PASS,
                    label="Confirm Pray with no usable verified standalone attack weapon",
                    actor_player_name=self_player.name,
                    control_panel="left",
                )
            )
    elif self_neutral_defense and state.phase_control == "Forgive":
        candidates = [
            artifact
            for artifact in state.hand
            if artifact.category == "armor"
            and artifact.slug in (plain_armor_defenses or {})
            and artifact.hit_target_bounds is not None
        ]
    else:
        candidates = []
    if candidates:
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
    if self_fixed_attack_confirmation and selected_attack_slug is not None:
        target_index, target = living_opponents[0]
        actions.append(
            LegalAction(
                action_id=f"confirm:attack:{selected_attack_slug}:{target_index}:{target.name}",
                kind=ActionKind.CONFIRM,
                label=f"Confirm the selected attack on {target.name}",
                artifact_asset_path=state.action_artifact_asset_path,
                target_player_index=target_index,
                target_player_name=target.name,
                control_panel="left",
            )
        )
    if self_untargeted_attack_confirmation and selected_weapon is not None:
        slug = selected_weapon.group(1)
        assert selected_weapon_rule is not None
        chance_attack = PROBABILISTIC_ATTACK_PATTERN.fullmatch(selected_weapon_rule[0]) is not None
        actions.append(
            LegalAction(
                action_id=f"confirm:{'chance' if chance_attack else 'untargeted'}:{slug}",
                kind=ActionKind.CONFIRM_CHANCE,
                label=f"Resolve the selected untargeted attack {slug}",
                artifact_asset_path=state.action_artifact_asset_path,
                actor_player_name=self_player.name,
                expected_action_display=state.action_display,
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
                label="Forgive the incoming targeted interaction",
                artifact_asset_path=state.action_artifact_asset_path,
                target_player_index=state.self_player_index,
                target_player_name=self_player.name,
                control_panel="right",
                context_asset_paths=incoming_context_assets,
            )
        )
    if self_reflected_response:
        target_index, target = living_opponents[0]
        actions.append(
            LegalAction(
                action_id="forgive:reflected",
                kind=ActionKind.FORGIVE,
                label="Forgive the reflected outgoing attack",
                artifact_asset_path=state.phase_artifact_asset_path,
                target_player_index=target_index,
                target_player_name=target.name,
                control_panel="left",
                context_asset_paths=reflected_context_assets,
            )
        )
    return LegalActionSet(
        state_digest=game_state_digest(state),
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason=(
            "only verified one-click weapon or fixed miracle selection and confirmation, "
            "weapon-free Pray, incoming or reflected Forgive, and neutral plain-armor "
            "selection and confirmation are supported"
        ),
    )
