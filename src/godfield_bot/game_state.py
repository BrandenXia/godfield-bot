import re

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import (
    Bounds,
    ScreenKind,
    ScreenObservation,
    VisibleImage,
    VisibleText,
)

FIELD_PATTERN = re.compile(r"^G\.F\.(\d+)$")
ITEM_PATTERN = re.compile(r"^/images/items/([^/]+)/([^/]+)\.(?:png|svg|webp)$")
FOG_SCENE_PATH = "/images/screens/fog.webp"
FOG_CURSE_PATH = "/images/curses/small/fog.webp"
NEUTRAL_TEXT_COLOR = "rgb(79, 79, 79)"
ATTACK_DISPLAY_PATTERN = re.compile(r"^ATK\d+$")
REFLECTED_ATTACK_DISPLAY_PATTERN = re.compile(r"^(?:\d+%)?ATK\d+$")
DEFENSE_DISPLAY_PATTERN = re.compile(r"^DEF\d+$")
ROW_TOLERANCE = 1.5


class GameStateParseError(RuntimeError):
    """Raised when a screen cannot be normalized without guessing."""


def _elements_on_row(elements: tuple[VisibleText, ...], y: float) -> list[VisibleText]:
    return sorted(
        (element for element in elements if abs(element.bounds.y - y) <= ROW_TOLERANCE),
        key=lambda element: element.bounds.x,
    )


def _label_value(row: list[VisibleText], label: str, next_label: str | None) -> int:
    labels = [element for element in row if element.text == label]
    if len(labels) != 1:
        raise GameStateParseError(f"expected one {label!r} label on player row")
    start = labels[0].bounds.x + labels[0].bounds.width - 1
    end = float("inf")
    if next_label is not None:
        following = [element for element in row if element.text == next_label]
        if len(following) != 1:
            raise GameStateParseError(f"expected one {next_label!r} label on player row")
        end = following[0].bounds.x
    values = [
        element.text
        for element in row
        if start <= element.bounds.x < end and element.text.isdecimal()
    ]
    if len(values) != 1:
        raise GameStateParseError(f"expected one numeric value after {label!r}")
    return int(values[0])


def _current_player_hit_target(
    observation: ScreenObservation,
    *,
    row_y: float,
    maximum_name_x: float,
    hp_label_right: float,
) -> Bounds | None:
    hit_targets = [
        control.bounds
        for control in observation.controls
        if not control.text
        and 700 <= control.bounds.x <= maximum_name_x
        and abs(control.bounds.y - row_y) <= ROW_TOLERANCE
        and 250 <= control.bounds.width <= 400
        and 25 <= control.bounds.height <= 60
        and control.bounds.x + control.bounds.width >= hp_label_right
    ]
    return hit_targets[0] if len(hit_targets) == 1 else None


def _player_row_hit_targets(observation: ScreenObservation) -> tuple[Bounds, ...]:
    return tuple(
        sorted(
            (
                control.bounds
                for control in observation.controls
                if not control.text
                and 700 <= control.bounds.x <= 850
                and control.bounds.y < 400
                and 250 <= control.bounds.width <= 400
                and 25 <= control.bounds.height <= 60
            ),
            key=lambda bounds: bounds.y,
        )
    )


def _bounds_match(left: Bounds | None, right: Bounds) -> bool:
    if left is None:
        return False
    return (
        abs(left.x - right.x) <= ROW_TOLERANCE
        and abs(left.y - right.y) <= ROW_TOLERANCE
        and abs(left.width - right.width) <= ROW_TOLERANCE
        and abs(left.height - right.height) <= ROW_TOLERANCE
    )


def _recover_fog_hidden_players(
    observation: ScreenObservation,
    identity: str,
    visible_players: list[PlayerState],
    previous_state: GameState | None,
) -> tuple[PlayerState, ...] | None:
    visible_self = visible_players[0] if len(visible_players) == 1 else None
    self_bounds = visible_self.hit_target_bounds if visible_self is not None else None
    visible_hp_labels = [
        element
        for element in observation.text_elements
        if element.text == "HP" and element.bounds.x >= 700 and element.bounds.y < 400
    ]
    self_fog_visible = any(
        image.path == FOG_CURSE_PATH
        and (
            (
                self_bounds is not None
                and self_bounds.x <= image.bounds.x <= self_bounds.x + self_bounds.width
                and self_bounds.y <= image.bounds.y <= self_bounds.y + self_bounds.height
            )
            or (
                self_bounds is None
                and len(visible_hp_labels) == 1
                and 780 <= image.bounds.x <= 1120
                and visible_hp_labels[0].bounds.y
                <= image.bounds.y
                <= visible_hp_labels[0].bounds.y + visible_hp_labels[0].bounds.height
            )
        )
        for image in observation.images
    )
    if (
        previous_state is None
        or FOG_SCENE_PATH not in {image.path for image in observation.images}
        or len(visible_players) != 1
        or not visible_players[0].is_self
        or not self_fog_visible
        or len(previous_state.players) < 2
        or sum(player.is_self for player in previous_state.players) != 1
    ):
        return None
    previous_self = previous_state.players[previous_state.self_player_index]
    if previous_self.name != identity or visible_players[0].name != identity:
        return None
    row_hit_targets = _player_row_hit_targets(observation)
    complete_row_targets = len(row_hit_targets) == len(previous_state.players) and _bounds_match(
        visible_players[0].hit_target_bounds,
        row_hit_targets[previous_state.self_player_index],
    )
    if not complete_row_targets:
        action_actor = _single_spatial_element(
            observation,
            minimum_x=100,
            maximum_x=450,
            minimum_y=40,
            maximum_y=80,
        )
        action_target = _single_spatial_element(
            observation,
            minimum_x=451,
            maximum_x=750,
            minimum_y=40,
            maximum_y=80,
        )
        phase_control = _single_spatial_element(
            observation,
            minimum_x=451,
            maximum_x=750,
            minimum_y=390,
            maximum_y=450,
        )
        action_display = _single_spatial_element(
            observation,
            minimum_x=100,
            maximum_x=450,
            minimum_y=390,
            maximum_y=450,
        )
        previous_opponents = [player for player in previous_state.players if not player.is_self]
        if len(previous_opponents) != 1:
            return None
        previous_opponent = previous_opponents[0]
        has_action_context = any(
            _item_coordinates(image) is not None
            and 100 <= image.bounds.x <= 450
            and 80 <= image.bounds.y <= 380
            for image in observation.images
        )
        selected_phase_armor = [
            image
            for image in observation.images
            if (coordinates := _item_coordinates(image)) is not None
            and coordinates[0] == "armor"
            and 450 <= image.bounds.x <= 750
            and 80 <= image.bounds.y <= 250
            and 60 <= image.bounds.width <= 100
            and 60 <= image.bounds.height <= 100
            and image.hit_target_bounds is None
        ]
        selected_phase_attacks = [
            image
            for image in observation.images
            if (coordinates := _item_coordinates(image)) is not None
            and coordinates[0] in {"weapons", "miracles"}
            and 450 <= image.bounds.x <= 750
            and 80 <= image.bounds.y <= 250
            and 60 <= image.bounds.width <= 100
            and 60 <= image.bounds.height <= 100
            and image.hit_target_bounds is None
        ]
        has_forgive_response = phase_control is not None and phase_control.text == "Forgive"
        has_neutral_armor_response = (
            action_display is not None
            and ATTACK_DISPLAY_PATTERN.fullmatch(action_display.text) is not None
            and action_display.color == NEUTRAL_TEXT_COLOR
            and phase_control is not None
            and DEFENSE_DISPLAY_PATTERN.fullmatch(phase_control.text) is not None
            and phase_control.color == NEUTRAL_TEXT_COLOR
            and len(selected_phase_armor) == 1
        )
        has_incoming_response = (
            action_actor is not None
            and action_actor.text == previous_opponent.name
            and action_target is not None
            and action_target.text == identity
            and (has_forgive_response or has_neutral_armor_response)
            and _phase_control_hit_target(observation) is not None
            and has_action_context
        )
        has_reflected_response = (
            action_actor is not None
            and action_actor.text == identity
            and action_target is not None
            and action_target.text == previous_opponent.name
            and action_display is not None
            and action_display.text == "Forgive"
            and phase_control is not None
            and REFLECTED_ATTACK_DISPLAY_PATTERN.fullmatch(phase_control.text) is not None
            and _action_hit_target(observation) is not None
            and len(selected_phase_attacks) == 1
        )
        if row_hit_targets or not (has_incoming_response or has_reflected_response):
            return None

    recovered: list[PlayerState] = []
    for index, previous in enumerate(previous_state.players):
        if previous.is_self:
            recovered.append(visible_players[0])
            continue
        recovered.append(
            previous.model_copy(
                update={
                    "stats_visible": False,
                    "status_marker_color": None,
                    "hit_target_bounds": (row_hit_targets[index] if complete_row_targets else None),
                }
            )
        )
    return tuple(recovered)


def _parse_players(
    observation: ScreenObservation,
    identity: str,
    previous_state: GameState | None,
) -> tuple[PlayerState, ...]:
    hp_labels = sorted(
        (
            element
            for element in observation.text_elements
            if element.text == "HP" and element.bounds.x >= 700 and element.bounds.y < 400
        ),
        key=lambda element: element.bounds.y,
    )
    players: list[PlayerState] = []
    for hp_label in hp_labels:
        row = _elements_on_row(observation.text_elements, hp_label.bounds.y)
        names = [
            element
            for element in row
            if 780 <= element.bounds.x < hp_label.bounds.x
            and element.text not in {"HP", "MP", "$"}
            and not element.text.isdecimal()
        ]
        if len(names) != 1:
            raise GameStateParseError("expected one player name on stats row")
        name = names[0].text
        markers = [
            marker
            for marker in observation.markers
            if abs(
                marker.bounds.y
                + marker.bounds.height / 2
                - (hp_label.bounds.y + hp_label.bounds.height / 2)
            )
            <= 3
            and marker.bounds.x < hp_label.bounds.x
        ]
        players.append(
            PlayerState(
                name=name,
                hp=_label_value(row, "HP", "MP"),
                mp=_label_value(row, "MP", "$"),
                money=_label_value(row, "$", None),
                is_self=name == identity,
                status_marker_color=(markers[0].background_color if len(markers) == 1 else None),
                hit_target_bounds=_current_player_hit_target(
                    observation,
                    row_y=hp_label.bounds.y,
                    maximum_name_x=names[0].bounds.x,
                    hp_label_right=hp_label.bounds.x + hp_label.bounds.width,
                ),
            )
        )
    if len(players) < 2:
        recovered = _recover_fog_hidden_players(
            observation,
            identity,
            players,
            previous_state,
        )
        if recovered is not None:
            return recovered
        raise GameStateParseError("expected at least two player rows")
    if sum(player.is_self for player in players) != 1:
        raise GameStateParseError("expected exactly one player matching the configured identity")
    return tuple(players)


def _item_coordinates(image: VisibleImage) -> tuple[str, str] | None:
    match = ITEM_PATTERN.fullmatch(image.path)
    if match is None:
        return None
    return match.group(1), match.group(2)


def _parse_hand(observation: ScreenObservation) -> tuple[HandArtifact, ...]:
    hand_images = sorted(
        (
            image
            for image in observation.images
            if (coordinates := _item_coordinates(image)) is not None
            and coordinates[0] != "trade"
            and 100 <= image.bounds.x <= 850
            and 480 <= image.bounds.y <= 690
            and 60 <= image.bounds.width <= 100
            and 60 <= image.bounds.height <= 100
        ),
        key=lambda image: (image.bounds.y, image.bounds.x),
    )

    hand: list[HandArtifact] = []
    for slot, image in enumerate(hand_images):
        coordinates = _item_coordinates(image)
        if coordinates is None:  # pragma: no cover - filtered above
            raise GameStateParseError("invalid item path in hand cluster")
        category, slug = coordinates
        hand.append(
            HandArtifact(
                slot=slot,
                category=category,
                slug=slug,
                asset_path=image.path,
                bounds=image.bounds,
                hit_target_bounds=image.hit_target_bounds,
            )
        )
    return tuple(hand)


def _parse_action_artifact(observation: ScreenObservation) -> str | None:
    candidates = [
        image.path
        for image in observation.images
        if _item_coordinates(image) is not None
        and 100 <= image.bounds.x <= 450
        and 80 <= image.bounds.y <= 380
        and 60 <= image.bounds.width <= 100
        and 60 <= image.bounds.height <= 100
        and image.hit_target_bounds is None
    ]
    return candidates[0] if len(candidates) == 1 else None


def _parse_phase_artifact(observation: ScreenObservation) -> str | None:
    candidates = [
        image.path
        for image in observation.images
        if _item_coordinates(image) is not None
        and 450 <= image.bounds.x <= 750
        and 80 <= image.bounds.y <= 250
        and 60 <= image.bounds.width <= 100
        and 60 <= image.bounds.height <= 100
        and image.hit_target_bounds is None
    ]
    return candidates[0] if len(candidates) == 1 else None


def _single_spatial_element(
    observation: ScreenObservation,
    *,
    minimum_x: float,
    maximum_x: float,
    minimum_y: float,
    maximum_y: float,
) -> VisibleText | None:
    matches = [
        element
        for element in observation.text_elements
        if minimum_x <= element.bounds.x <= maximum_x and minimum_y <= element.bounds.y <= maximum_y
    ]
    return matches[0] if len(matches) == 1 else None


def _phase_control_hit_target(observation: ScreenObservation) -> Bounds | None:
    candidates = [
        control.bounds
        for control in observation.controls
        if not control.text
        and 450 <= control.bounds.x <= 500
        and 80 <= control.bounds.y <= 120
        and 250 <= control.bounds.width <= 350
        and 250 <= control.bounds.height <= 350
    ]
    return candidates[0] if len(candidates) == 1 else None


def _action_hit_target(observation: ScreenObservation) -> Bounds | None:
    candidates = [
        control.bounds
        for control in observation.controls
        if not control.text
        and 100 <= control.bounds.x <= 150
        and 80 <= control.bounds.y <= 120
        and 250 <= control.bounds.width <= 350
        and 250 <= control.bounds.height <= 350
    ]
    return candidates[0] if len(candidates) == 1 else None


def parse_game_state(
    observation: ScreenObservation,
    *,
    identity: str,
    previous_state: GameState | None = None,
) -> GameState:
    if observation.kind is not ScreenKind.GAME:
        raise GameStateParseError(f"expected game observation, got {observation.kind}")
    field_matches = [
        match
        for element in observation.text_elements
        if (match := FIELD_PATTERN.fullmatch(element.text)) is not None
    ]
    if len(field_matches) != 1:
        raise GameStateParseError("expected exactly one G.F. field counter")
    players = _parse_players(observation, identity, previous_state)
    action_actor = _single_spatial_element(
        observation,
        minimum_x=100,
        maximum_x=450,
        minimum_y=40,
        maximum_y=80,
    )
    action_target = _single_spatial_element(
        observation,
        minimum_x=451,
        maximum_x=750,
        minimum_y=40,
        maximum_y=80,
    )
    action_display = _single_spatial_element(
        observation,
        minimum_x=100,
        maximum_x=450,
        minimum_y=390,
        maximum_y=450,
    )
    phase_control = _single_spatial_element(
        observation,
        minimum_x=451,
        maximum_x=750,
        minimum_y=390,
        maximum_y=450,
    )
    return GameState(
        observed_at=observation.observed_at,
        field_number=int(field_matches[0].group(1)),
        self_player_index=next(index for index, player in enumerate(players) if player.is_self),
        players=players,
        hand=_parse_hand(observation),
        scene_layers=tuple(
            image.path for image in observation.images if image.path.startswith("/images/screens/")
        ),
        action_actor=action_actor.text if action_actor else None,
        action_target=action_target.text if action_target else None,
        action_display=action_display.text if action_display else None,
        action_display_color=action_display.color if action_display else None,
        action_artifact_asset_path=_parse_action_artifact(observation),
        action_hit_target_bounds=_action_hit_target(observation),
        phase_control=phase_control.text if phase_control else None,
        phase_control_color=phase_control.color if phase_control else None,
        phase_artifact_asset_path=_parse_phase_artifact(observation),
        phase_control_hit_target_bounds=(
            _phase_control_hit_target(observation) if phase_control else None
        ),
    )
