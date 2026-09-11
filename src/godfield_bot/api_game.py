from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from godfield import Command, RoomState  # type: ignore[import-untyped]

    from godfield_bot.domain.reference import BibleSnapshot


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
    instance_id: int | None = Field(default=None, gt=0)
    model_id: int | None = Field(default=None, gt=0)
    name: str | None = None
    asset: str | None = None
    category: str | None = None
    element: str | None = None
    attack: int = Field(ge=0)
    defense: int = Field(ge=0)
    cost: int = Field(ge=0)
    ability: str | None = None
    ability_value: int = Field(default=0, ge=0)
    is_plus_attack: bool = False
    used: bool
    identity_reliable: bool = True


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
    schema_version: int = 4
    observed_at: datetime
    mode: str = "private"
    update_count: int = Field(ge=0)
    field_number: int = Field(ge=0)
    self_player_id: int = Field(gt=0)
    awaiting_player_id: int | None = Field(default=None, gt=0)
    phase: ApiPhase
    players: tuple[ApiPlayerState, ...]
    hand: tuple[ApiItemState, ...]
    has_active_curses: bool = False
    pending_attack: ApiAttackState | None = None
    buying_item_model_id: int | None = Field(default=None, gt=0)


class ApiLegalAction(BaseModel):
    action_id: str
    kind: ApiActionKind
    label: str
    item_instance_ids: tuple[int, ...] = ()
    item_model_ids: tuple[int, ...] = ()
    target_player_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def command_shape_is_consistent(self) -> ApiLegalAction:
        if self.kind is ApiActionKind.USE_ITEM:
            if not self.item_instance_ids or len(self.item_instance_ids) != len(
                self.item_model_ids
            ):
                raise ValueError("item action requires aligned instance and model IDs")
        elif self.item_instance_ids or self.item_model_ids or self.target_player_id is not None:
            raise ValueError("non-item action cannot contain item or target IDs")
        return self


class ApiLegalActionSet(BaseModel):
    schema_version: int = 1
    state_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    actions: tuple[ApiLegalAction, ...]
    coverage_complete: bool
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def action_set_is_consistent(self) -> ApiLegalActionSet:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("API legal action IDs must be unique")
        if not self.coverage_complete and not self.blocked_reason:
            raise ValueError("incomplete API action coverage requires a blocked reason")
        return self


class ApiPolicyDecision(BaseModel):
    schema_version: int = 2
    decided_at: datetime
    policy_id: str
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    chosen_action_id: str | None = None
    scores: dict[str, float]
    rationale: str
    executable: bool
    model_id: str | None = None
    model_weights_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    selection_action_indices: tuple[int, ...] = ()
    selection_probabilities: tuple[float, ...] = ()
    value_estimates: tuple[float, ...] = ()

    @model_validator(mode="after")
    def inference_trace_is_consistent(self) -> ApiPolicyDecision:
        if self.chosen_action_id is not None and self.chosen_action_id not in self.scores:
            raise ValueError("chosen API action requires a recorded score")
        trace_lengths = {
            len(self.selection_action_indices),
            len(self.selection_probabilities),
            len(self.value_estimates),
        }
        if trace_lengths != {0} and len(trace_lengths) != 1:
            raise ValueError("neural selection trace fields must have equal lengths")
        if trace_lengths != {0} and (self.model_id is None or self.model_weights_sha256 is None):
            raise ValueError("neural selection trace requires immutable model identity")
        return self


MILD_CURSE_NAMES = frozenset({"cold", "fever", "fog", "flash"})


class ApiActionExecutionResult(BaseModel):
    schema_version: int = 1
    executed_at: datetime
    action_id: str
    kind: ApiActionKind
    dispatched: bool
    server_acknowledged: bool | None = None
    latency_ms: float = Field(ge=0)


class ApiActionTransition(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    action_id: str
    before_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_state_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    state_changed: bool | None
    update_count_delta: int | None = None
    player_hp_deltas: dict[int, int] = Field(default_factory=dict)
    before_state: ApiGameState
    after_state: ApiGameState | None = None


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
    true_model_id = _optional_positive_int(item.model_id, "item model ID")
    visible_model_id = _optional_positive_int(item.fake_model_id, "fake item model ID")
    model_id = visible_model_id or true_model_id
    catalog = getattr(item, "_catalog", None)
    model = catalog.get(model_id) if catalog is not None and model_id is not None else None
    raw_model = model.raw if model is not None and isinstance(model.raw, dict) else {}
    return ApiItemState(
        instance_id=_optional_positive_int(item.id, "item instance ID"),
        model_id=model_id,
        name=model.name if model is not None and isinstance(model.name, str) else None,
        asset=(raw_model.get("imageName") if isinstance(raw_model.get("imageName"), str) else None),
        category=(
            model.category if model is not None and isinstance(model.category, str) else None
        ),
        element=model.element if model is not None and isinstance(model.element, str) else None,
        attack=_nonnegative_int(model.atk if model is not None else 0, "item attack"),
        defense=_nonnegative_int(model.def_ if model is not None else 0, "item defense"),
        cost=_nonnegative_int(model.cost if model is not None else 0, "item cost"),
        ability=model.ability if model is not None and isinstance(model.ability, str) else None,
        ability_value=_nonnegative_int(
            model.ability_value if model is not None else 0,
            "item ability value",
        ),
        is_plus_attack=bool(model.is_plus_atk) if model is not None else False,
        used=bool(item.used),
        identity_reliable=not bool(item.fake_model_id),
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
    raw_curses = me.raw.get("curses")
    return ApiGameState(
        observed_at=observed_at or datetime.now(UTC),
        update_count=_nonnegative_int(game.update_count, "game update count"),
        field_number=_nonnegative_int(game.gf, "game field number"),
        self_player_id=self_player_id,
        awaiting_player_id=awaiting_player_id,
        phase=phase,
        players=players,
        hand=tuple(_item_state(item) for item in me.items),
        has_active_curses=bool(raw_curses),
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
    has_curses = state.has_active_curses
    raw_curses = me.raw.get("curses")
    mild_curse_active = isinstance(raw_curses, list) and any(
        isinstance(curse, str) and curse.casefold() in MILD_CURSE_NAMES
        for curse in raw_curses
    )
    if state.phase is ApiPhase.PURCHASE:
        actions.append(
            ApiLegalAction(
                action_id="purchase:decline",
                kind=ApiActionKind.DECLINE_PURCHASE,
                label="Decline the purchase",
            )
        )
    visible_usable_weapon = any(item.category == "weapons" and not item.used for item in state.hand)
    if state.phase is ApiPhase.DEFENSE or (
        state.phase is ApiPhase.TURN and not has_curses and not visible_usable_weapon
    ):
        actions.append(
            ApiLegalAction(
                action_id="pass",
                kind=ApiActionKind.PASS,
                label="Use no items",
            )
        )

    if state.phase is ApiPhase.TURN:
        opponents = game.opponents_of(me)
        if has_curses:
            for item in me.usable_items():
                model = item.model
                item_instance_id = _optional_positive_int(item.id, "item instance ID")
                item_model_id = _optional_positive_int(item.model_id, "item model ID")
                if (
                    model is not None
                    and item_instance_id is not None
                    and item_model_id is not None
                    and not item.fake_model_id
                    and (
                        model.ability == "removeAllCurses"
                        or (model.ability == "removeMildCurses" and mild_curse_active)
                    )
                    and model.can_start_turn
                    and item.cost <= me.mp
                ):
                    actions.append(
                        ApiLegalAction(
                            action_id=f"use:{item_instance_id}:{item_model_id}:untargeted",
                            kind=ApiActionKind.USE_ITEM,
                            label=f"Remove curses with {item.name or f'model {item.model_id}'}",
                            item_instance_ids=(item_instance_id,),
                            item_model_ids=(item_model_id,),
                        )
                    )
        for item in me.weapons():
            model = item.model
            item_instance_id = _optional_positive_int(item.id, "item instance ID")
            item_model_id = _optional_positive_int(item.model_id, "item model ID")
            if (
                model is None
                or item_instance_id is None
                or item_model_id is None
                or item.fake_model_id
                or model.category != "weapons"
                or model.is_plus_atk
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
                            f"use:{item_instance_id}:{item_model_id}:"
                            f"{target_id if target_id is not None else 'untargeted'}"
                        ),
                        kind=ApiActionKind.USE_ITEM,
                        label=f"Use {item.name or f'model {item.model_id}'}",
                        item_instance_ids=(item_instance_id,),
                        item_model_ids=(item_model_id,),
                        target_player_id=target_id,
                    )
                )
    elif state.phase is ApiPhase.DEFENSE:
        attack = game.pending_attack
        if attack is None:
            raise ApiGameStateError("defense phase has no pending attack")
        for item in me.defense_options(attack):
            item_instance_id = _optional_positive_int(item.id, "item instance ID")
            item_model_id = _optional_positive_int(item.model_id, "item model ID")
            if item.fake_model_id or item_instance_id is None or item_model_id is None:
                continue
            actions.append(
                ApiLegalAction(
                    action_id=f"defend:{item_instance_id}:{item_model_id}",
                    kind=ApiActionKind.USE_ITEM,
                    label=f"Defend with {item.name or f'model {item.model_id}'}",
                    item_instance_ids=(item_instance_id,),
                    item_model_ids=(item_model_id,),
                )
            )

    return ApiLegalActionSet(
        state_digest=api_game_state_digest(state),
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason=(
            "pygodfield verifies conservative single-card attacks, defenses, and "
            "curse removal; cursed attack turns expose only individually reliable cards and "
            "empty attack-turn commands are exposed only when the visible hand has no weapon, "
            "while multi-card combinations, purchases, and unknown future effects remain "
            "excluded"
        ),
    )


def verified_api_combo_actions(
    room: RoomState,
    *,
    user_id: str,
    bible_snapshot: BibleSnapshot,
) -> ApiLegalActionSet:
    """Extend the reviewed live surface with strict plain-card combinations.

    The command protocol accepts several item IDs at once. This adapter only
    exposes combinations represented by the native combo curriculum: one
    effect-free base weapon followed by effect-free additive weapons, or two
    or more independently compatible effect-free armor cards.
    """

    from godfield_bot.reference import (
        plain_attack_booster_cards,
        plain_attack_weapon_cards,
        plain_defense_armor_cards,
    )

    conservative = verified_api_actions(room, user_id=user_id)
    state = normalize_api_game_state(room, user_id=user_id)
    game = room.game
    if game is None:  # pragma: no cover - normalized above
        raise ApiGameStateError("private room has no active game")
    me = game.player_by_user(user_id)
    if me is None:  # pragma: no cover - normalized above
        raise ApiGameStateError("the API identity has no active player")

    base_cards = plain_attack_weapon_cards(bible_snapshot)
    booster_cards = plain_attack_booster_cards(bible_snapshot)
    armor_cards = plain_defense_armor_cards(bible_snapshot)

    def rule_matches(
        model: Any,
        rules: Mapping[str, tuple[int, str]],
        *,
        stat: str,
    ) -> bool:
        asset = model.raw.get("imageName")
        expected = rules.get(asset)
        if expected is None or model.ability is not None or model.cost != 0:
            return False
        expected_value, expected_element = expected
        actual_element = model.element or "non-element"
        return getattr(model, stat) == expected_value and actual_element == expected_element

    def card_identity(item: Any) -> tuple[int, int, Any] | None:
        instance_id = _optional_positive_int(item.id, "item instance ID")
        model_id = _optional_positive_int(item.model_id, "item model ID")
        model = item.model
        if (
            instance_id is None
            or model_id is None
            or item.fake_model_id
            or model is None
            or not isinstance(model.raw, dict)
        ):
            return None
        return instance_id, model_id, model

    actions = list(conservative.actions)
    if state.phase is ApiPhase.TURN and not state.has_active_curses:
        strict_bases: list[tuple[Any, tuple[int, int, Any]]] = []
        strict_boosters: list[tuple[Any, tuple[int, int, Any]]] = []
        for item in me.usable_items():
            identity = card_identity(item)
            if identity is None:
                continue
            model = identity[2]
            if (
                model.category == "weapons"
                and model.can_start_turn
                and rule_matches(model, base_cards, stat="atk")
                and not model.is_plus_atk
            ):
                strict_bases.append((item, identity))
            elif (
                model.category == "weapons"
                and rule_matches(model, booster_cards, stat="atk")
                and model.is_plus_atk
            ):
                strict_boosters.append((item, identity))

        for base, base_identity in strict_bases:
            targets = game.opponents_of(me) if base_identity[2].needs_target else (None,)
            for count in range(1, len(strict_boosters) + 1):
                for selected_boosters in combinations(strict_boosters, count):
                    selected = ((base, base_identity), *selected_boosters)
                    if sum(item.cost for item, _identity in selected) > me.mp:
                        continue
                    instance_ids = tuple(identity[0] for _item, identity in selected)
                    model_ids = tuple(identity[1] for _item, identity in selected)
                    names = " + ".join(
                        item.name or f"model {identity[1]}" for item, identity in selected
                    )
                    for target in targets:
                        target_id = (
                            _required_positive_int(target.id, "target player ID")
                            if target is not None
                            else None
                        )
                        ids = "-".join(str(value) for value in instance_ids)
                        actions.append(
                            ApiLegalAction(
                                action_id=(
                                    f"combo-attack:{ids}:"
                                    f"{target_id if target_id is not None else 'untargeted'}"
                                ),
                                kind=ApiActionKind.USE_ITEM,
                                label=f"Use {names}",
                                item_instance_ids=instance_ids,
                                item_model_ids=model_ids,
                                target_player_id=target_id,
                            )
                        )
    elif state.phase is ApiPhase.DEFENSE and not state.has_active_curses:
        attack = game.pending_attack
        if attack is None:  # pragma: no cover - normalized above
            raise ApiGameStateError("defense phase has no pending attack")
        strict_armor: list[tuple[Any, tuple[int, int, Any]]] = []
        for item in me.defense_options(attack):
            identity = card_identity(item)
            if identity is None:
                continue
            model = identity[2]
            if model.category == "armor" and rule_matches(
                model,
                armor_cards,
                stat="def_",
            ):
                strict_armor.append((item, identity))
        for count in range(2, len(strict_armor) + 1):
            for selected in combinations(strict_armor, count):
                if sum(item.cost for item, _identity in selected) > me.mp:
                    continue
                instance_ids = tuple(identity[0] for _item, identity in selected)
                model_ids = tuple(identity[1] for _item, identity in selected)
                ids = "-".join(str(value) for value in instance_ids)
                names = " + ".join(
                    item.name or f"model {identity[1]}" for item, identity in selected
                )
                actions.append(
                    ApiLegalAction(
                        action_id=f"combo-defense:{ids}",
                        kind=ApiActionKind.USE_ITEM,
                        label=f"Defend with {names}",
                        item_instance_ids=instance_ids,
                        item_model_ids=model_ids,
                    )
                )

    return ApiLegalActionSet(
        state_digest=conservative.state_digest,
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason=(
            "the reviewed surface includes conservative single-card actions and "
            "strict plain base-plus-booster attacks or compatible armor combinations; "
            "purchases, cursed combinations, resource prompts, and special effects remain "
            "excluded"
        ),
    )


def verified_api_tactical_actions(
    room: RoomState,
    *,
    user_id: str,
    bible_snapshot: BibleSnapshot,
) -> ApiLegalActionSet:
    """Add reviewed utility, miracle, and plain-armor sale actions."""

    from godfield_bot.reference import (
        plain_defense_armor_cards,
        verified_chance_attack_miracle_cards,
        verified_cp_utility_miracle_cards,
        verified_effect_attack_miracle_cards,
        verified_stochastic_hp_sundries,
    )

    combo_actions = verified_api_combo_actions(
        room,
        user_id=user_id,
        bible_snapshot=bible_snapshot,
    )
    state = normalize_api_game_state(room, user_id=user_id)
    game = room.game
    if game is None:  # pragma: no cover - normalized above
        raise ApiGameStateError("private room has no active game")
    me = game.player_by_user(user_id)
    if me is None:  # pragma: no cover - normalized above
        raise ApiGameStateError("the API identity has no active player")

    actions = list(combo_actions.actions)
    existing_action_ids = {action.action_id for action in actions}
    if state.phase is ApiPhase.TURN:
        sell_cards: list[tuple[Any, int, int]] = []
        sellable_armor: list[tuple[Any, int, int]] = []
        plain_armor = plain_defense_armor_cards(bible_snapshot)
        chance_attack_miracles = verified_chance_attack_miracle_cards(bible_snapshot)
        cp_utility_miracles = verified_cp_utility_miracle_cards(bible_snapshot)
        effect_attack_miracles = verified_effect_attack_miracle_cards(bible_snapshot)
        stochastic_hp_sundries = verified_stochastic_hp_sundries(bible_snapshot)
        for item in me.usable_items():
            instance_id = _optional_positive_int(item.id, "item instance ID")
            model_id = _optional_positive_int(item.model_id, "item model ID")
            model = item.model
            if (
                instance_id is None
                or model_id is None
                or item.fake_model_id
                or model is None
                or item.cost > me.mp
            ):
                continue
            asset = model.raw.get("imageName") if isinstance(model.raw, dict) else None
            expected_armor = plain_armor.get(asset) if isinstance(asset, str) else None
            if (
                model.category == "armor"
                and model.ability is None
                and model.cost == 0
                and expected_armor is not None
                and model.def_ == expected_armor[0]
                and (model.element or "non-element") == expected_armor[1]
            ):
                sellable_armor.append((item, instance_id, model_id))
            if not model.can_start_turn:
                continue
            if (
                model.category == "trade"
                and model.ability == "sell"
                and asset == "sell"
                and model.needs_target
            ):
                sell_cards.append((item, instance_id, model_id))
            if (
                model.category in {"sundries", "miracles"}
                and model.ability in {"boostHP", "boostMP"}
                and not model.needs_target
            ):
                action = ApiLegalAction(
                    action_id=f"utility:{model.ability}:{instance_id}:{model_id}",
                    kind=ApiActionKind.USE_ITEM,
                    label=f"Use {item.name or f'model {model_id}'}",
                    item_instance_ids=(instance_id,),
                    item_model_ids=(model_id,),
                )
                if action.action_id not in existing_action_ids:
                    actions.append(action)
                    existing_action_ids.add(action.action_id)
            elif (
                model.category == "sundries"
                and model.ability == "boostHPOrDealDamage"
                and not model.needs_target
            ):
                stochastic_expected = (
                    stochastic_hp_sundries.get(asset) if isinstance(asset, str) else None
                )
                if stochastic_expected != (model.ability_value, model.ability_value):
                    continue
                action = ApiLegalAction(
                    action_id=(
                        f"random-utility:{model.ability}:{instance_id}:{model_id}"
                    ),
                    kind=ApiActionKind.USE_ITEM,
                    label=f"Use {item.name or f'model {model_id}'}",
                    item_instance_ids=(instance_id,),
                    item_model_ids=(model_id,),
                )
                if action.action_id not in existing_action_ids:
                    actions.append(action)
                    existing_action_ids.add(action.action_id)
            elif (
                model.category == "miracles"
                and model.ability == "boostCP"
                and not model.needs_target
            ):
                cp_expected = cp_utility_miracles.get(asset) if isinstance(asset, str) else None
                if cp_expected != (model.ability_value, model.cost):
                    continue
                action = ApiLegalAction(
                    action_id=f"cp-utility:{model.ability}:{instance_id}:{model_id}",
                    kind=ApiActionKind.USE_ITEM,
                    label=f"Use {item.name or f'model {model_id}'}",
                    item_instance_ids=(instance_id,),
                    item_model_ids=(model_id,),
                )
                if action.action_id not in existing_action_ids:
                    actions.append(action)
                    existing_action_ids.add(action.action_id)
            elif model.category == "miracles" and model.atk > 0 and not model.is_plus_atk:
                if model.needs_target:
                    if model.ability is not None:
                        effect_expected = (
                            effect_attack_miracles.get(asset) if isinstance(asset, str) else None
                        )
                        if effect_expected != (
                            model.atk,
                            model.cost,
                            model.element or "non-element",
                            model.ability,
                        ):
                            continue
                    targets = game.opponents_of(me)
                    action_prefix = (
                        "effect-miracle-attack" if model.ability is not None else "miracle-attack"
                    )
                else:
                    if model.ability is not None:
                        continue
                    chance_expected = (
                        chance_attack_miracles.get(asset) if isinstance(asset, str) else None
                    )
                    if chance_expected != (
                        model.hit_rate,
                        model.atk,
                        model.cost,
                        model.element or "non-element",
                    ):
                        continue
                    targets = (None,)
                    action_prefix = "chance-miracle-attack"
                for target in targets:
                    target_id = (
                        _required_positive_int(target.id, "target player ID")
                        if target is not None
                        else None
                    )
                    action = ApiLegalAction(
                        action_id=(
                            f"{action_prefix}:{instance_id}:{model_id}:"
                            f"{target_id if target_id is not None else 'untargeted'}"
                        ),
                        kind=ApiActionKind.USE_ITEM,
                        label=f"Use {item.name or f'model {model_id}'}",
                        item_instance_ids=(instance_id,),
                        item_model_ids=(model_id,),
                        target_player_id=target_id,
                    )
                    if action.action_id not in existing_action_ids:
                        actions.append(action)
                        existing_action_ids.add(action.action_id)
            elif (
                model.category == "miracles" and model.ability == "addCurse" and model.needs_target
            ):
                for target in game.opponents_of(me):
                    target_id = _required_positive_int(target.id, "target player ID")
                    action = ApiLegalAction(
                        action_id=f"miracle-curse:{instance_id}:{model_id}:{target_id}",
                        kind=ApiActionKind.USE_ITEM,
                        label=f"Use {item.name or f'model {model_id}'}",
                        item_instance_ids=(instance_id,),
                        item_model_ids=(model_id,),
                        target_player_id=target_id,
                    )
                    if action.action_id not in existing_action_ids:
                        actions.append(action)
                        existing_action_ids.add(action.action_id)

        for sell_item, sell_instance_id, sell_model_id in sell_cards:
            for armor_item, armor_instance_id, armor_model_id in sellable_armor:
                for target in game.opponents_of(me):
                    target_id = _required_positive_int(target.id, "target player ID")
                    action = ApiLegalAction(
                        action_id=(
                            f"trade-sell:{sell_instance_id}:{armor_instance_id}:{target_id}"
                        ),
                        kind=ApiActionKind.USE_ITEM,
                        label=(
                            f"Use {sell_item.name or f'model {sell_model_id}'} to offer "
                            f"{armor_item.name or f'model {armor_model_id}'}"
                        ),
                        item_instance_ids=(sell_instance_id, armor_instance_id),
                        item_model_ids=(sell_model_id, armor_model_id),
                        target_player_id=target_id,
                    )
                    if action.action_id not in existing_action_ids:
                        actions.append(action)
                        existing_action_ids.add(action.action_id)

    return ApiLegalActionSet(
        state_digest=combo_actions.state_digest,
        actions=tuple(actions),
        coverage_complete=False,
        blocked_reason=(
            "the tactical surface includes verified single cards, strict plain combinations, "
            "deterministic HP/MP/CP utility, audited self-targeting HP-or-damage sundries, "
            "targeted fixed-damage and audited automatic-effect "
            "miracles, Bible-verified untargeted chance miracles, and targeted curse miracles, "
            "plus Sell paired with verified plain armor; other random effects, trades, purchase "
            "acceptance, and unmodeled choices remain excluded"
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


def build_api_action_transition(
    action: ApiLegalAction,
    before: ApiGameState,
    after: ApiGameState | None,
) -> ApiActionTransition:
    before_digest = api_game_state_digest(before)
    if after is None:
        return ApiActionTransition(
            observed_at=datetime.now(UTC),
            action_id=action.action_id,
            before_state_digest=before_digest,
            state_changed=None,
            before_state=before,
        )
    after_digest = api_game_state_digest(after)
    before_hp = {player.player_id: player.hp for player in before.players}
    hp_deltas = {
        player.player_id: player.hp - before_hp[player.player_id]
        for player in after.players
        if player.player_id in before_hp and player.hp != before_hp[player.player_id]
    }
    return ApiActionTransition(
        observed_at=after.observed_at,
        action_id=action.action_id,
        before_state_digest=before_digest,
        after_state_digest=after_digest,
        state_changed=after_digest != before_digest,
        update_count_delta=after.update_count - before.update_count,
        player_hp_deltas=hp_deltas,
        before_state=before,
        after_state=after,
    )
