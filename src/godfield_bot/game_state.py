import re

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation, VisibleImage, VisibleText

FIELD_PATTERN = re.compile(r"^G\.F\.(\d+)$")
ITEM_PATTERN = re.compile(r"^/images/items/([^/]+)/([^/]+)\.(?:png|svg|webp)$")
ROW_TOLERANCE = 1.5
HAND_Y_BUCKET = 5.0


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


def _parse_players(observation: ScreenObservation, identity: str) -> tuple[PlayerState, ...]:
    hp_labels = [
        element
        for element in observation.text_elements
        if element.text == "HP" and element.bounds.x >= 700 and element.bounds.y < 400
    ]
    players: list[PlayerState] = []
    for hp_label in hp_labels:
        row = _elements_on_row(observation.text_elements, hp_label.bounds.y)
        names = [
            element.text
            for element in row
            if element.bounds.x < hp_label.bounds.x
            and element.text not in {"HP", "MP", "$"}
            and not element.text.isdecimal()
        ]
        if len(names) != 1:
            raise GameStateParseError("expected one player name on stats row")
        name = names[0]
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
            )
        )
    if len(players) < 2:
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
    candidates = [
        image
        for image in observation.images
        if _item_coordinates(image) is not None
        and 60 <= image.bounds.width <= 100
        and 60 <= image.bounds.height <= 100
    ]
    buckets: dict[int, list[VisibleImage]] = {}
    for image in candidates:
        key = round(image.bounds.y / HAND_Y_BUCKET)
        buckets.setdefault(key, []).append(image)
    if not buckets:
        raise GameStateParseError("no hand artifact image cluster was found")
    hand_images = max(buckets.values(), key=len)
    if len(hand_images) < 2:
        raise GameStateParseError("hand artifact cluster is unexpectedly small")

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


def parse_game_state(observation: ScreenObservation, *, identity: str) -> GameState:
    if observation.kind is not ScreenKind.GAME:
        raise GameStateParseError(f"expected game observation, got {observation.kind}")
    field_matches = [
        match
        for element in observation.text_elements
        if (match := FIELD_PATTERN.fullmatch(element.text)) is not None
    ]
    if len(field_matches) != 1:
        raise GameStateParseError("expected exactly one G.F. field counter")
    players = _parse_players(observation, identity)
    return GameState(
        observed_at=observation.observed_at,
        field_number=int(field_matches[0].group(1)),
        self_player_index=next(index for index, player in enumerate(players) if player.is_self),
        players=players,
        hand=_parse_hand(observation),
        scene_layers=tuple(
            image.path for image in observation.images if image.path.startswith("/images/screens/")
        ),
    )
