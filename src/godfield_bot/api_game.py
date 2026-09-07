from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from godfield import Command, RoomState  # type: ignore[import-untyped]


class ApiGameStateError(RuntimeError):
    """Raised when an API room state cannot satisfy the policy contract."""


class ApiPhase(StrEnum):
    WAIT = "wait"
    TURN = "turn"
    DEFENSE = "defense"
    PURCHASE = "purchase"
    TERMINAL = "terminal"


class ApiActionKind(StrEnum):
    PASS = "pass"
    USE_ITEM = "use_item"
    DECLINE_PURCHASE = "decline_purchase"


class ApiItemState(BaseModel):
    instance_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    name: str | None = None
    category: str | None = None
    element: str | None = None
    attack: int = Field(ge=0)
    defense: int = Field(ge=0)
    cost: int = Field(ge=0)
    ability: str | None = None
    used: bool


class ApiPlayerState(BaseModel):
    player_id: int = Field(gt=0)
    name: str
    hp: int = Field(ge=0)
    mp: int = Field(ge=0)
    cp: int = Field(ge=0)
    team: int | None = None
    is_self: bool
    is_bot: bool
    hand_count: int = Field(ge=0)


class ApiAttackState(BaseModel):
    player_id: int = Field(gt=0)
    target_player_id: int | None = Field(default=None, gt=0)
    item_model_ids: tuple[int, ...]
    attack: int = Field(ge=0)
    element: str | None = None
    category: str | None = None


class ApiGameState(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    mode: str = "private"
    update_count: int = Field(ge=0)
    field_number: int = Field(ge=0)
    self_player_id: int = Field(gt=0)
    awaiting_player_id: int | None = Field(default=None, gt=0)
    phase: ApiPhase
    players: tuple[ApiPlayerState, ...]
    hand: tuple[ApiItemState, ...]
    pending_attack: ApiAttackState | None = None
    buying_item_model_id: int | None = Field(default=None, gt=0)


class ApiLegalAction(BaseModel):
    action_id: str
    kind: ApiActionKind
    label: str
    item_instance_ids: tuple[int, ...] = ()
    item_model_ids: tuple[int, ...] = ()
    target_player_id: int | None = Field(default=None, gt=0)


class ApiLegalActionSet(BaseModel):
    schema_version: int = 1
    state_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    actions: tuple[ApiLegalAction, ...]
    coverage_complete: bool
    blocked_reason: str | None = None


def api_game_state_digest(state: ApiGameState) -> str:
    canonical = state.model_dump_json(exclude={"observed_at"})
    return hashlib.sha256(canonical.encode()).hexdigest()


def _required_positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ApiGameStateError(f"API state has no valid {field}")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ApiGameStateError(f"API state has no valid {field}")
    return value


def _optional_positive_int(value: object, field: str) -> int | None:
    if value is None or value == 0:
        return None
    return _required_positive_int(value, field)


def _item_state(item: Any) -> ApiItemState:
    true_model_id = _required_positive_int(item.model_id, "item model ID")
    visible_model_id = _optional_positive_int(item.fake_model_id, "fake item model ID")
    model_id = visible_model_id or true_model_id
    catalog = getattr(item, "_catalog", None)
    model = catalog.get(model_id) if catalog is not None else None
    return ApiItemState(
        instance_id=_required_positive_int(item.id, "item instance ID"),
        model_id=model_id,
        name=model.name if model is not None and isinstance(model.name, str) else None,
        category=(
            model.category if model is not None and isinstance(model.category, str) else None
        ),
        element=model.element if model is not None and isinstance(model.element, str) else None,
        attack=_nonnegative_int(model.atk if model is not None else 0, "item attack"),
        defense=_nonnegative_int(model.def_ if model is not None else 0, "item defense"),
        cost=_nonnegative_int(model.cost if model is not None else 0, "item cost"),
        ability=model.ability if model is not None and isinstance(model.ability, str) else None,
        used=bool(item.used),
    )


def _player_state(player: Any, *, self_player_id: int) -> ApiPlayerState:
    player_id = _required_positive_int(player.id, "player ID")
    team = player.team
    if team is not None and (not isinstance(team, int) or isinstance(team, bool)):
        raise ApiGameStateError("API state has an invalid player team")
    return ApiPlayerState(
        player_id=player_id,
        name=player.name if isinstance(player.name, str) else "",
        hp=_nonnegative_int(player.hp, "player HP"),
        mp=_nonnegative_int(player.mp, "player MP"),
        cp=_nonnegative_int(player.cp, "player CP"),
        team=team,
        is_self=player_id == self_player_id,
        is_bot=bool(player.is_bot),
        hand_count=len(player.items),
    )


def _attack_state(attack: Any) -> ApiAttackState:
    model_ids = tuple(
        _required_positive_int(value, "attack item model ID") for value in attack.item_model_ids
    )
    return ApiAttackState(
        player_id=_required_positive_int(attack.player_id, "attacking player ID"),
        target_player_id=_optional_positive_int(
            attack.target_player_id,
            "attack target player ID",
        ),
        item_model_ids=model_ids,
        attack=_nonnegative_int(attack.atk, "attack power"),
        element=attack.element if isinstance(attack.element, str) else None,
        category=attack.category if isinstance(attack.category, str) else None,
    )


def normalize_api_game_state(
    room: RoomState,
    *,
    user_id: str,
    observed_at: datetime | None = None,
) -> ApiGameState:
    """Normalize public state while discarding opponents' hidden card identities."""

    game = room.game
    if game is None:
        raise ApiGameStateError("private room has no active game")
    me = game.player_by_user(user_id)
    if me is None:
        raise ApiGameStateError("the API identity has no player in the active game")
    self_player_id = _required_positive_int(me.id, "self player ID")
    players = tuple(_player_state(player, self_player_id=self_player_id) for player in game.players)
    if len(players) < 2:
        raise ApiGameStateError("an active private game must contain at least two players")

    buying_item_model_id = _optional_positive_int(
        game.buying_item_model_id,
        "buying item model ID",
    )
    awaiting_player_id = _optional_positive_int(
        game.awaiting_player_id,
        "awaiting player ID",
    )
    if game.is_over:
        phase = ApiPhase.TERMINAL
    elif awaiting_player_id != self_player_id:
        phase = ApiPhase.WAIT
    elif buying_item_model_id is not None:
        phase = ApiPhase.PURCHASE
    elif game.is_defending:
        phase = ApiPhase.DEFENSE
    else:
        phase = ApiPhase.TURN

    pending = game.pending_attack
    return ApiGameState(
        observed_at=observed_at or datetime.now(UTC),
        update_count=_nonnegative_int(game.update_count, "game update count"),
        field_number=_nonnegative_int(game.gf, "game field number"),
        self_player_id=self_player_id,
        awaiting_player_id=awaiting_player_id,
        phase=phase,
        players=players,
        hand=tuple(_item_state(item) for item in me.items),
        pending_attack=_attack_state(pending) if pending is not None else None,
        buying_item_model_id=buying_item_model_id,
    )


def verified_api_actions(room: RoomState, *, user_id: str) -> ApiLegalActionSet:
    """Expose the conservative single-card subset verified by pygodfield."""

    state = normalize_api_game_state(room, user_id=user_id)
    game = room.game
    if game is None:  # pragma: no cover - normalized above
        raise ApiGameStateError("private room has no active game")
    me = game.player_by_user(user_id)
    if me is None:  # pragma: no cover - normalized above
        raise ApiGameStateError("the API identity has no active player")

    actions: list[ApiLegalAction] = []
    if state.phase is ApiPhase.PURCHASE:
        actions.append(
            ApiLegalAction(
                action_id="purchase:decline",
                kind=ApiActionKind.DECLINE_PURCHASE,
                label="Decline the purchase",
            )
        )
    elif state.phase in {ApiPhase.TURN, ApiPhase.DEFENSE}:
        actions.append(
            ApiLegalAction(
                action_id="pass",
                kind=ApiActionKind.PASS,
                label="Use no items",
            )
        )

    if state.phase is ApiPhase.TURN:
        opponents = game.opponents_of(me)
        has_curses = bool(me.raw.get("curses"))
        for item in me.weapons():
            model = item.model
            if (
                model is None
                or item.fake_model_id
                or has_curses
                or model.category != "weapons"
                or not model.can_start_turn
                or item.cost > me.mp
            ):
                continue
            targets = opponents if model.needs_target else (None,)
            for target in targets:
                target_id = (
                    _required_positive_int(target.id, "target player ID")
                    if target is not None
                    else None
                )
                actions.append(
                    ApiLegalAction(
                        action_id=(
                            f"use:{item.id}:{item.model_id}:"
                            f"{target_id if target_id is not None else 'untargeted'}"
                        ),
                        kind=ApiActionKind.USE_ITEM,
                        label=f"Use {item.name or f'model {item.model_id}'}",
                        item_instance_ids=(_required_positive_int(item.id, "item instance ID"),),
                        item_model_ids=(_required_positive_int(item.model_id, "item model ID"),),
                        target_player_id=target_id,
                    )
                )
    elif state.phase is ApiPhase.DEFENSE:
        attack = game.pending_attack
        if attack is None:
            raise ApiGameStateError("defense phase has no pending attack")
        for item in me.defense_options(attack):
            if item.fake_model_id:
                continue
            actions.append(
                ApiLegalAction(
                    action_id=f"defend:{item.id}:{item.model_id}",
                    kind=ApiActionKind.USE_ITEM,
                    label=f"Defend with {item.name or f'model {item.model_id}'}",
                    item_instance_ids=(_required_positive_int(item.id, "item instance ID"),),
                    item_model_ids=(_required_positive_int(item.model_id, "item model ID"),),
                )
            )

    return ApiLegalActionSet(
        state_digest=api_game_state_digest(state),
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason=(
            "pygodfield verifies conservative single-card attacks and defenses; "
            "multi-card combinations, purchases, and unknown future effects remain excluded"
        ),
    )


def command_for_api_action(action: ApiLegalAction) -> Command:
    """Convert one validated policy action to pygodfield's command builder."""

    from godfield import Command

    if action.kind is ApiActionKind.PASS:
        return Command.pass_turn()
    if action.kind is ApiActionKind.DECLINE_PURCHASE:
        return Command.buy(False)
    if action.kind is ApiActionKind.USE_ITEM and action.item_instance_ids:
        return Command.use(
            list(action.item_instance_ids),
            target=action.target_player_id,
        )
    raise ApiGameStateError("API action cannot be represented as a pygodfield command")
