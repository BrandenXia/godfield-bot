from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from godfield_bot.api_account import (
    PYGODFIELD_REVISION,
    ApiAccountError,
    open_api_client,
    validate_api_credentials,
)
from godfield_bot.api_catalog import (
    ApiCatalogSnapshot,
    item_catalog_from_snapshot,
    read_api_catalog_snapshot,
)
from godfield_bot.api_game import (
    ApiActionExecutionResult,
    ApiActionKind,
    ApiGameState,
    ApiGameStateError,
    ApiItemState,
    ApiLegalAction,
    ApiLegalActionSet,
    ApiPhase,
    ApiPolicyDecision,
    api_game_state_digest,
    build_api_action_transition,
    command_for_api_action,
    normalize_api_game_state,
    verified_api_actions,
    verified_api_tactical_actions,
)
from godfield_bot.config import AppSettings
from godfield_bot.domain.outcome import MatchResult, SparseTerminalReward
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.run import EventKind, RunMode, RunRecord, RunSpec, RunStatus
from godfield_bot.run_store import RunStore

log = structlog.get_logger()
TACTICAL_HEAL_THRESHOLD = 25
ACCEPTED_PRIVATE_BIBLE_CLIENT_SHA256 = (
    "764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd"
)
RETRYABLE_STATE_READ_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_STATE_READ_RETRY_DELAY_SECONDS = 30.0


class ApiRuntimeError(RuntimeError):
    """Raised when private API observation cannot continue safely."""


class ApiPolicyName(StrEnum):
    OBSERVER = "api-observer-v0"
    HEURISTIC = "api-heuristic-v0"
    TACTICAL_HEURISTIC = "api-combo-utility-heuristic-v4"
    NEURAL_SHADOW = "api-combo-neural-shadow-v1"


class PrivateApiRunConfig(BaseModel):
    database: Path = Path("runs", "godfield.sqlite")
    catalog_snapshot: Path = Path(
        "data",
        "snapshots",
        "2026-09-09",
        "api-catalog-en.json",
    )
    room_id: str | None = Field(default=None, min_length=1, max_length=256)
    password_file: Path | None = None
    enter_match: bool = False
    entry_team: int = Field(default=0, ge=0, le=4)
    policy: ApiPolicyName = ApiPolicyName.OBSERVER
    model_directory: Path | None = None
    bible_snapshot: Path = Path("data", "snapshots", "2026-09-07", "bible.json")
    max_in_match_actions: int = Field(default=0, ge=0, le=1000)
    max_seconds: float = Field(default=90.0, ge=0.0, le=3600.0)
    poll_seconds: float = Field(default=1.0, ge=0.25, le=10.0)
    no_progress_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    request_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    state_read_retries: int = Field(default=5, ge=0, le=20)
    state_read_retry_seconds: float = Field(default=1.0, ge=0.1, le=30.0)

    @field_validator("room_id")
    @classmethod
    def room_id_has_no_outer_whitespace(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip():
            raise ValueError("room ID must not start or end with whitespace")
        return value

    @model_validator(mode="after")
    def executable_policy_has_safe_bounds(self) -> PrivateApiRunConfig:
        if 0 < self.max_seconds < 10:
            raise ValueError("max seconds must be zero (unlimited) or at least 10")
        if self.policy is ApiPolicyName.OBSERVER and self.max_in_match_actions != 0:
            raise ValueError("api-observer-v0 requires a zero in-match action budget")
        if not self.enter_match and self.entry_team != 0:
            raise ValueError("a non-solo entry team requires explicit match entry")
        if self.policy in {
            ApiPolicyName.HEURISTIC,
            ApiPolicyName.TACTICAL_HEURISTIC,
            ApiPolicyName.NEURAL_SHADOW,
        }:
            if not self.enter_match:
                raise ValueError(f"{self.policy.value} requires explicit match entry")
            if self.max_in_match_actions < 1:
                raise ValueError(f"{self.policy.value} requires a positive action budget")
        if self.policy is ApiPolicyName.NEURAL_SHADOW and self.model_directory is None:
            raise ValueError("neural shadow mode requires a model directory")
        if self.policy is not ApiPolicyName.NEURAL_SHADOW and self.model_directory is not None:
            raise ValueError("a model directory is only valid for neural shadow policy")
        return self


def _within_wall_clock_limit(*, elapsed: float, max_seconds: float) -> bool:
    """Return whether a session may continue; zero disables this one limit."""

    return max_seconds == 0 or elapsed < max_seconds


class ApiPrivateMatchOutcome(BaseModel):
    schema_version: int = 1
    observed_at: datetime
    mode: str = "private"
    classification: str = "two_player_hp_terminal"
    terminal_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    self_player_name: str
    opponent_player_names: tuple[str, ...] = Field(min_length=1, max_length=1)
    result: MatchResult


def _read_password_file(path: Path | None) -> str | None:
    if path is None:
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ApiRuntimeError("the private-room password file cannot be opened safely") from error
    try:
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode):
            raise ApiRuntimeError("the private-room password path must be a regular file")
        actual_mode = stat.S_IMODE(file_status.st_mode)
        if actual_mode != 0o600:
            raise ApiRuntimeError(
                f"private-room password permissions are {actual_mode:o}, expected 600"
            )
        with os.fdopen(descriptor, encoding="utf-8") as password_file:
            descriptor = -1
            raw_password = password_file.read(259)
    except ApiRuntimeError:
        raise
    except (OSError, UnicodeError) as error:
        raise ApiRuntimeError("the private-room password file is unreadable") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return _validate_room_password(raw_password, source="password file")


def _validate_room_password(raw_password: str, *, source: str) -> str:
    if len(raw_password) > 258:
        raise ApiRuntimeError(f"the private-room {source} has an invalid value")
    if raw_password.endswith("\r\n"):
        password = raw_password[:-2]
    elif raw_password.endswith("\n"):
        password = raw_password[:-1]
    else:
        password = raw_password
    if not password or len(password) > 256 or "\n" in password or "\r" in password:
        raise ApiRuntimeError(f"the private-room {source} has an invalid value")
    return password


def api_environment_fingerprint(snapshot: ApiCatalogSnapshot) -> str:
    material = f"pygodfield:{PYGODFIELD_REVISION}:catalog:{snapshot.content_sha256}"
    return hashlib.sha256(material.encode()).hexdigest()


def _lobby_observation(room: Any, *, user_id: str) -> dict[str, JsonValue]:
    user_ids = room.user_ids()
    entry_ids = room.entry_ids()
    game = room.game
    return {
        "schema_version": 1,
        "mode": "private",
        "phase": "lobby",
        "user_count": int(room.user_count),
        "entry_count": len(entry_ids),
        "identity_present": user_id in user_ids,
        "identity_entered": user_id in entry_ids,
        "identity_entry_team": _identity_entry_team(room, user_id=user_id),
        "active_game": game is not None,
        "active_game_over": bool(game.is_over) if game is not None else None,
        "active_player_count": len(game.players) if game is not None else 0,
        "active_game_update_count": (
            int(game.update_count)
            if game is not None
            and isinstance(game.update_count, int)
            and not isinstance(game.update_count, bool)
            and game.update_count >= 0
            else None
        ),
    }


def _lobby_digest(observation: dict[str, JsonValue]) -> str:
    canonical = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _safe_runtime_error_reason(error: Exception) -> str:
    if isinstance(error, (ApiRuntimeError, ApiAccountError, ApiGameStateError)):
        return str(error).splitlines()[0]
    return "pygodfield private-room operation failed"


def _safe_runtime_error_payload(error: Exception) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "error_type": type(error).__name__,
        "reason": _safe_runtime_error_reason(error),
    }
    action = getattr(error, "action", None)
    status = getattr(error, "status", None)
    if action in {
        "create-room",
        "join-room",
        "make-entry",
        "keep-alive",
        "leave-room",
        "submit-command",
    }:
        payload["api_action"] = action
    if isinstance(status, int) and not isinstance(status, bool):
        payload["http_status"] = status
    return payload


def _transport_http_status(error: Exception) -> int | None:
    status = getattr(error, "status", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _is_retryable_state_read_error(error: Exception) -> bool:
    """Classify safe-to-repeat room reads without retrying client or auth errors."""

    raw_status = getattr(error, "status", None)
    if raw_status is None:
        return True
    return (
        isinstance(raw_status, int)
        and not isinstance(raw_status, bool)
        and raw_status in RETRYABLE_STATE_READ_HTTP_STATUSES
    )


def _state_read_retry_delay(*, failure_number: int, base_seconds: float) -> float:
    return min(
        base_seconds * (2.0 ** max(0, failure_number - 1)),
        MAX_STATE_READ_RETRY_DELAY_SECONDS,
    )


def _state_read_error_payload(
    error: Exception,
    *,
    failure_number: int,
    retry_budget: int,
    retry_scheduled: bool,
    retry_delay_seconds: float | None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "schema_version": 1,
        "error_type": type(error).__name__,
        "reason": "private room-state read failed",
        "operation": "read-room-state",
        "consecutive_failure": failure_number,
        "retry_budget": retry_budget,
        "retry_scheduled": retry_scheduled,
    }
    status = _transport_http_status(error)
    if status is not None:
        payload["http_status"] = status
    if retry_delay_seconds is not None:
        payload["retry_delay_seconds"] = retry_delay_seconds
    return payload


def _identity_entry_team(room: Any, *, user_id: str) -> int | None:
    """Return the identity's lobby team, normalizing a legacy null team to solo."""

    matching_entries = [
        entry
        for entry in room.entries
        if isinstance(entry, dict) and entry.get("userId") == user_id
    ]
    if not matching_entries:
        return None
    raw_team = matching_entries[0].get("team")
    if raw_team is None:
        return 0
    if not isinstance(raw_team, int) or isinstance(raw_team, bool) or not 0 <= raw_team <= 4:
        raise ApiRuntimeError("the API identity has an invalid lobby team")
    return raw_team


def _should_request_match_entry(room: Any, *, user_id: str, entry_team: int) -> bool:
    game = room.game
    if game is not None and not game.is_over:
        return False
    return _identity_entry_team(room, user_id=user_id) != entry_team


def _decide_tactical_api_action(
    state: ApiGameState,
    legal_actions: ApiLegalActionSet,
) -> tuple[ApiPolicyDecision, ApiLegalAction | None]:
    """Choose a deterministic resource-aware action from the reviewed live surface."""

    hand_by_instance = {item.instance_id: item for item in state.hand}

    def action_items(action: ApiLegalAction) -> tuple[ApiItemState, ...]:
        resolved: list[ApiItemState] = []
        for instance_id in action.item_instance_ids:
            item = hand_by_instance.get(instance_id)
            if item is None:
                return ()
            resolved.append(item)
        return tuple(resolved)

    def attack_value(action: ApiLegalAction) -> int:
        items = action_items(action)
        if not items:
            return 0
        value = items[0].attack
        for item in items[1:]:
            value = value * 2 if item.ability == "doubleAtk" else value + item.attack
        return value

    def defense_value(action: ApiLegalAction) -> int:
        items = action_items(action)
        if any(
            item.ability
            in {
                "blockWeapon",
                "bounceWeapon",
                "reflectWeapon",
                "blockMiracle",
                "bounceMiracle",
                "reflectMiracle",
                "reflectAnything",
            }
            for item in items
        ):
            return state.pending_attack.attack if state.pending_attack is not None else 0
        return sum(item.defense for item in items)

    def action_cost(action: ApiLegalAction) -> int:
        return sum(item.cost for item in action_items(action))

    players_by_id = {player.player_id: player for player in state.players}

    def target_hp(action: ApiLegalAction) -> int:
        target = (
            players_by_id.get(action.target_player_id)
            if action.target_player_id is not None
            else None
        )
        return target.hp if target is not None else 101

    def best_utility(actions: list[ApiLegalAction]) -> ApiLegalAction | None:
        return (
            max(
                actions,
                key=lambda action: (
                    action_items(action)[0].ability_value,
                    -action_cost(action),
                    -action.item_instance_ids[0],
                ),
            )
            if actions
            else None
        )

    chosen: ApiLegalAction | None = None
    rationale = "the server is not awaiting an action from ロキ-67"
    if state.phase is ApiPhase.PURCHASE:
        chosen = next(
            (
                action
                for action in legal_actions.actions
                if action.kind is ApiActionKind.DECLINE_PURCHASE
            ),
            None,
        )
        if chosen is not None:
            rationale = "decline an unmodeled purchase"
    elif state.phase is ApiPhase.DEFENSE:
        defenses = [
            action
            for action in legal_actions.actions
            if action.kind is ApiActionKind.USE_ITEM and defense_value(action) > 0
        ]
        pending_attack = state.pending_attack.attack if state.pending_attack is not None else 0
        sufficient = [action for action in defenses if defense_value(action) >= pending_attack]
        if sufficient:
            chosen = min(
                sufficient,
                key=lambda action: (
                    defense_value(action),
                    action_cost(action),
                    len(action.item_instance_ids),
                    action.item_instance_ids,
                ),
            )
            rationale = "use the least excessive verified defense that prevents all damage"
        elif defenses:
            chosen = max(
                defenses,
                key=lambda action: (
                    defense_value(action),
                    -action_cost(action),
                    -len(action.item_instance_ids),
                    tuple(-value for value in action.item_instance_ids),
                ),
            )
            rationale = "use the strongest verified defense to reduce incoming damage"
        else:
            chosen = next(
                (action for action in legal_actions.actions if action.kind is ApiActionKind.PASS),
                None,
            )
            if chosen is not None:
                rationale = "accept damage because no verified defense is compatible"
    elif state.phase is ApiPhase.TURN:
        candidates = [
            action
            for action in legal_actions.actions
            if (
                action.kind is ApiActionKind.USE_ITEM
                and action.item_instance_ids
                and action_items(action)
            )
        ]
        cleansers = [
            action for action in candidates if action_items(action)[0].ability == "removeAllCurses"
        ]
        chance_attacks = [
            action for action in candidates if action.action_id.startswith("chance-miracle-attack:")
        ]
        attacks = [
            action
            for action in candidates
            if attack_value(action) > 0
            and not action.action_id.startswith("chance-miracle-attack:")
        ]
        heals = [action for action in candidates if action_items(action)[0].ability == "boostHP"]
        mana = [action for action in candidates if action_items(action)[0].ability == "boostMP"]
        capital = [action for action in candidates if action_items(action)[0].ability == "boostCP"]
        curse_attacks = [
            action for action in candidates if action_items(action)[0].ability == "addCurse"
        ]
        armor_sales = [
            action
            for action in candidates
            if len(action_items(action)) == 2
            and action_items(action)[0].ability == "sell"
            and action_items(action)[1].category == "armor"
        ]
        lethal = [
            action
            for action in attacks
            if action.target_player_id is not None
            and (target := players_by_id.get(action.target_player_id)) is not None
            and attack_value(action) >= target.hp
        ]
        me = next(player for player in state.players if player.is_self)
        if state.has_active_curses and cleansers:
            chosen = min(
                cleansers,
                key=lambda action: (action_cost(action), action.item_instance_ids),
            )
            rationale = "remove all active curses before committing another action"
        elif lethal:
            chosen = min(
                lethal,
                key=lambda action: (
                    attack_value(action),
                    action_cost(action),
                    target_hp(action),
                    len(action.item_instance_ids),
                    action.item_instance_ids,
                ),
            )
            rationale = "use the least costly attack with potentially lethal power"
        elif me.hp <= TACTICAL_HEAL_THRESHOLD and (chosen := best_utility(heals)) is not None:
            rationale = "restore HP before it falls into common lethal range"
        elif attacks:
            chosen = max(
                attacks,
                key=lambda action: (
                    attack_value(action),
                    -action_cost(action),
                    -target_hp(action),
                    -len(action.item_instance_ids),
                    tuple(-value for value in action.item_instance_ids),
                ),
            )
            rationale = (
                "use the strongest verified attack combination"
                if len(chosen.item_instance_ids) > 1
                else "use the strongest verified attack"
            )
        elif curse_attacks:
            chosen = min(
                curse_attacks,
                key=lambda action: (
                    target_hp(action),
                    action_cost(action),
                    action.item_instance_ids,
                ),
            )
            rationale = "use a deterministic targeted curse instead of stalling"
        elif me.mp <= 5 and (chosen := best_utility(mana)) is not None:
            rationale = "restore MP while no verified attack is available"
        elif (chosen := best_utility(heals)) is not None:
            rationale = "convert an otherwise idle turn into verified HP recovery"
        elif (chosen := best_utility(mana)) is not None:
            rationale = "convert an otherwise idle turn into verified MP recovery"
        elif chance_attacks:
            chosen = max(
                chance_attacks,
                key=lambda action: (
                    attack_value(action),
                    -action_cost(action),
                    tuple(-value for value in action.item_instance_ids),
                ),
            )
            rationale = "use a Bible-verified chance attack rather than stall"
        elif (chosen := best_utility(capital)) is not None:
            rationale = "gain verified CP rather than stall"
        elif armor_sales:
            chosen = min(
                armor_sales,
                key=lambda action: (
                    action_items(action)[1].defense,
                    -target_hp(action),
                    action.item_instance_ids,
                ),
            )
            rationale = "offer the weakest verified plain armor rather than stall"
        else:
            chosen = next(
                (action for action in legal_actions.actions if action.kind is ApiActionKind.PASS),
                None,
            )
            if chosen is not None:
                rationale = "pass because no reviewed tactical action is available"

    executable = chosen is not None
    if (
        chosen is None
        and state.phase in {ApiPhase.TURN, ApiPhase.DEFENSE, ApiPhase.PURCHASE}
        and state.awaiting_player_id == state.self_player_id
    ):
        rationale = "no verified API action is available; abstain without submitting"
    return (
        ApiPolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=ApiPolicyName.TACTICAL_HEURISTIC.value,
            state_digest=legal_actions.state_digest,
            chosen_action_id=chosen.action_id if chosen is not None else None,
            scores={
                action.action_id: float(chosen is not None and action.action_id == chosen.action_id)
                for action in legal_actions.actions
            },
            rationale=rationale,
            executable=executable,
        ),
        chosen,
    )


def decide_api_action(
    policy: ApiPolicyName,
    state: ApiGameState,
    legal_actions: ApiLegalActionSet,
) -> tuple[ApiPolicyDecision, ApiLegalAction | None]:
    if policy is ApiPolicyName.OBSERVER:
        return (
            ApiPolicyDecision(
                decided_at=datetime.now(UTC),
                policy_id=policy.value,
                state_digest=legal_actions.state_digest,
                scores={action.action_id: 0.0 for action in legal_actions.actions},
                rationale="observation-only private API safety gate",
                executable=False,
            ),
            None,
        )
    if policy is ApiPolicyName.TACTICAL_HEURISTIC:
        return _decide_tactical_api_action(state, legal_actions)

    chosen: ApiLegalAction | None = None
    if state.phase is ApiPhase.PURCHASE:
        chosen = next(
            (
                action
                for action in legal_actions.actions
                if action.kind is ApiActionKind.DECLINE_PURCHASE
            ),
            None,
        )
    elif state.phase in {ApiPhase.TURN, ApiPhase.DEFENSE}:
        candidates = [
            action
            for action in legal_actions.actions
            if action.kind is ApiActionKind.USE_ITEM and len(action.item_instance_ids) == 1
        ]
        hand_by_instance = {item.instance_id: item for item in state.hand}

        def action_value(action: ApiLegalAction) -> tuple[int, int]:
            item = hand_by_instance.get(action.item_instance_ids[0])
            if item is None:
                return (-1, -action.item_instance_ids[0])
            value = item.attack if state.phase is ApiPhase.TURN else item.defense
            return (value, -action.item_instance_ids[0])

        curse_cleansers = [
            action
            for action in candidates
            if (
                (item := hand_by_instance.get(action.item_instance_ids[0])) is not None
                and item.ability == "removeAllCurses"
            )
        ]
        if state.phase is ApiPhase.TURN and state.has_active_curses and curse_cleansers:
            chosen = min(curse_cleansers, key=lambda action: action.item_instance_ids[0])
        elif candidates and state.phase is ApiPhase.DEFENSE:
            pending_attack = state.pending_attack.attack if state.pending_attack is not None else 0
            sufficient = [
                action for action in candidates if action_value(action)[0] >= pending_attack
            ]
            chosen = (
                min(
                    sufficient,
                    key=lambda action: (
                        action_value(action)[0],
                        action.item_instance_ids[0],
                    ),
                )
                if sufficient
                else max(candidates, key=action_value)
            )
        elif candidates:
            chosen = max(candidates, key=action_value)
        else:
            chosen = next(
                (action for action in legal_actions.actions if action.kind is ApiActionKind.PASS),
                None,
            )
    executable = chosen is not None
    chosen_item = (
        next(
            (item for item in state.hand if item.instance_id == chosen.item_instance_ids[0]),
            None,
        )
        if chosen is not None and chosen.item_instance_ids
        else None
    )
    if chosen is None:
        if (
            state.phase in {ApiPhase.TURN, ApiPhase.DEFENSE, ApiPhase.PURCHASE}
            and state.awaiting_player_id == state.self_player_id
        ):
            rationale = "no verified API action is available; abstain without submitting"
        else:
            rationale = "the server is not awaiting an action from ロキ-67"
    elif chosen.kind is ApiActionKind.DECLINE_PURCHASE:
        rationale = "decline an unmodeled purchase"
    elif chosen.kind is ApiActionKind.PASS:
        rationale = "pass because no conservative card action is available"
    elif (
        state.has_active_curses
        and chosen_item is not None
        and chosen_item.ability == "removeAllCurses"
    ):
        rationale = "remove active curses with a verified cleanser"
    elif state.phase is ApiPhase.TURN and state.has_active_curses:
        rationale = "use the strongest conservative card with a reliable identity"
    elif state.phase is ApiPhase.DEFENSE:
        pending_attack = state.pending_attack.attack if state.pending_attack is not None else 0
        rationale = (
            "use the weakest sufficient conservative defense"
            if chosen_item is not None and chosen_item.defense >= pending_attack
            else "use the strongest available conservative defense"
        )
    else:
        rationale = "use the strongest conservative single-card action"
    return (
        ApiPolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=policy.value,
            state_digest=legal_actions.state_digest,
            chosen_action_id=chosen.action_id if chosen is not None else None,
            scores={
                action.action_id: float(chosen is not None and action.action_id == chosen.action_id)
                for action in legal_actions.actions
            },
            rationale=rationale,
            executable=executable,
        ),
        chosen,
    )


def classify_api_two_player_terminal(state: ApiGameState) -> ApiPrivateMatchOutcome | None:
    if state.phase is not ApiPhase.TERMINAL or len(state.players) != 2:
        return None
    self_players = [player for player in state.players if player.is_self]
    opponents = [player for player in state.players if not player.is_self]
    if len(self_players) != 1 or len(opponents) != 1:
        return None
    me = self_players[0]
    opponent = opponents[0]
    if me.hp > 0 and opponent.hp > 0:
        return None
    result = (
        MatchResult.WIN if me.hp > 0 else MatchResult.LOSS if opponent.hp > 0 else MatchResult.DRAW
    )
    return ApiPrivateMatchOutcome(
        observed_at=state.observed_at,
        terminal_state_digest=api_game_state_digest(state),
        self_player_name=me.name,
        opponent_player_names=(opponent.name,),
        result=result,
    )


def _record_terminal_outcome(
    store: RunStore,
    run: RunRecord,
    outcome: ApiPrivateMatchOutcome,
) -> SparseTerminalReward:
    reward = SparseTerminalReward(
        observed_at=outcome.observed_at,
        terminal_state_digest=outcome.terminal_state_digest,
        result=outcome.result,
        value={
            MatchResult.WIN: 1.0,
            MatchResult.LOSS: -1.0,
            MatchResult.DRAW: 0.0,
        }[outcome.result],
    )
    store.append_events(
        run.run_id,
        (
            (EventKind.MATCH_END, outcome),
            (EventKind.REWARD, reward),
        ),
        occurred_at=outcome.observed_at,
    )
    return reward


def _finish_terminal_run(
    store: RunStore,
    run: RunRecord,
    outcome: ApiPrivateMatchOutcome,
    *,
    states_recorded: int,
    in_match_actions: int,
) -> RunRecord:
    reward = _record_terminal_outcome(store, run, outcome)
    return store.finish_run(
        run.run_id,
        RunStatus.COMPLETED,
        outcome={
            "reason": "classified_terminal",
            "result": outcome.result.value,
            "reward": reward.value,
            "terminal_state_digest": outcome.terminal_state_digest,
            "states_recorded": states_recorded,
            "in_match_actions": in_match_actions,
        },
    )


def run_private_api_observer(
    settings: AppSettings,
    config: PrivateApiRunConfig,
    *,
    room_password: str | None = None,
) -> RunRecord:
    """Run one safeguarded private-room API session under an explicit policy."""

    if settings.public_duel_enabled:
        raise ApiRuntimeError("private API runner requires public Duel to remain disabled")
    if room_password is not None and config.password_file is not None:
        raise ApiRuntimeError("provide the private-room key through only one input")
    password = (
        _validate_room_password(room_password, source="key")
        if room_password is not None
        else _read_password_file(config.password_file)
    )
    if config.room_id is None and password is None:
        raise ApiRuntimeError("private matchmaking requires a room key")
    snapshot = read_api_catalog_snapshot(config.catalog_snapshot)
    if snapshot.upstream_revision != PYGODFIELD_REVISION:
        raise ApiRuntimeError("catalog snapshot was captured by a different pygodfield revision")
    catalog = item_catalog_from_snapshot(snapshot)
    shadow_policy: Any | None = None
    tactical_snapshot: BibleSnapshot | None = None
    if config.policy is ApiPolicyName.NEURAL_SHADOW:
        try:
            from godfield_bot.api_neural import (
                ApiNeuralPolicyError,
                load_api_combo_shadow_policy,
            )
        except ImportError as error:
            raise ApiRuntimeError(
                "neural shadow dependencies are unavailable; run `uv sync --extra training`"
            ) from error

        if config.model_directory is None:  # pragma: no cover - config validation
            raise ApiRuntimeError("neural shadow policy has no model directory")
        try:
            shadow_policy = load_api_combo_shadow_policy(
                config.model_directory,
                config.bible_snapshot,
            )
        except ApiNeuralPolicyError as error:
            raise ApiRuntimeError(str(error)) from error
        tactical_snapshot = shadow_policy.snapshot
    elif config.policy is ApiPolicyName.TACTICAL_HEURISTIC:
        try:
            tactical_snapshot = BibleSnapshot.model_validate_json(
                config.bible_snapshot.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise ApiRuntimeError("the tactical Bible snapshot is unreadable or invalid") from error
    if (
        tactical_snapshot is not None
        and tactical_snapshot.client.sha256 != ACCEPTED_PRIVATE_BIBLE_CLIENT_SHA256
    ):
        raise ApiRuntimeError("the tactical Bible snapshot has not been accepted for live play")
    environment_fingerprint = api_environment_fingerprint(snapshot)
    store = RunStore(config.database)
    run_config: dict[str, JsonValue] = {
        "max_games": 0 if config.max_seconds == 0 else 1,
        "max_seconds": config.max_seconds,
        "poll_seconds": config.poll_seconds,
        "no_progress_seconds": config.no_progress_seconds,
        "request_timeout_seconds": config.request_timeout_seconds,
        "state_read_retries": config.state_read_retries,
        "state_read_retry_seconds": config.state_read_retry_seconds,
        "max_in_match_actions": config.max_in_match_actions,
        "enter_match": config.enter_match,
        "entry_team": config.entry_team,
        "policy": config.policy.value,
        "pygodfield_revision": PYGODFIELD_REVISION,
        "catalog_sha256": snapshot.content_sha256,
        "room_selector": "room_id" if config.room_id is not None else "matchmaking_key",
    }
    if shadow_policy is not None:
        run_config.update(
            {
                "behavior_policy": ApiPolicyName.TACTICAL_HEURISTIC.value,
                "shadow_policy_id": shadow_policy.policy_id,
                "shadow_feature_schema_version": (
                    shadow_policy.manifest.feature_schema_version
                ),
                "shadow_model_id": shadow_policy.manifest.model_id,
                "shadow_model_weights_sha256": shadow_policy.manifest.weights_sha256,
                "shadow_bible_client_sha256": shadow_policy.snapshot.client.sha256,
            }
        )
    if tactical_snapshot is not None:
        run_config["tactical_bible_client_sha256"] = tactical_snapshot.client.sha256
    if config.room_id is not None:
        run_config["room_fingerprint"] = hashlib.sha256(config.room_id.encode()).hexdigest()
    run = store.start_run(
        RunSpec(
            mode=RunMode.PRIVATE,
            identity=settings.identity,
            client_sha256=environment_fingerprint,
            policy_id=config.policy.value,
            model_id=(shadow_policy.manifest.model_id if shadow_policy is not None else None),
            config=run_config,
        )
    )
    states_recorded = 0
    in_match_actions = 0
    games_completed = 0
    outcome_reason = "wall_clock_limit"
    pending_action: tuple[ApiLegalAction, ApiGameState] | None = None
    try:
        from godfield import Mode, TransportError  # type: ignore[import-untyped]

        with open_api_client(
            settings,
            timeout_seconds=config.request_timeout_seconds,
            catalog=catalog,
        ) as client:
            user_id = client.user_id
            refreshed_credentials = validate_api_credentials(settings)
            if user_id != refreshed_credentials.user_id:
                raise ApiAccountError("the refreshed API identity failed its continuity check")
            if config.room_id is not None:
                client.join_room(
                    config.room_id,
                    mode=Mode.PRIVATE,
                    password=password,
                )
                joined_room_id = config.room_id
            else:
                joined_room_id = client.enter(
                    Mode.PRIVATE,
                    password=password,
                    lang=snapshot.language,
                )
            if not isinstance(joined_room_id, str) or not joined_room_id:
                raise ApiRuntimeError("pygodfield returned no valid private room ID")
            store.append_event(
                run.run_id,
                EventKind.OBSERVATION,
                {
                    "schema_version": 1,
                    "mode": "private",
                    "phase": "joined",
                    "room_fingerprint": hashlib.sha256(joined_room_id.encode()).hexdigest(),
                },
            )
            try:
                client.start_keepalive()
                started = time.monotonic()
                last_progress_at = started
                previous_digest: str | None = None
                entry_request_pending = False
                terminal_recorded = False
                consecutive_state_read_failures = 0
                while _within_wall_clock_limit(
                    elapsed=time.monotonic() - started,
                    max_seconds=config.max_seconds,
                ):
                    try:
                        room = client.state()
                    except TransportError as error:
                        consecutive_state_read_failures += 1
                        retryable = _is_retryable_state_read_error(error)
                        retry_scheduled = (
                            retryable
                            and consecutive_state_read_failures <= config.state_read_retries
                        )
                        retry_delay_seconds = (
                            _state_read_retry_delay(
                                failure_number=consecutive_state_read_failures,
                                base_seconds=config.state_read_retry_seconds,
                            )
                            if retry_scheduled
                            else None
                        )
                        store.append_event(
                            run.run_id,
                            EventKind.ERROR,
                            _state_read_error_payload(
                                error,
                                failure_number=consecutive_state_read_failures,
                                retry_budget=config.state_read_retries,
                                retry_scheduled=retry_scheduled,
                                retry_delay_seconds=retry_delay_seconds,
                            ),
                        )
                        if not retryable:
                            raise ApiRuntimeError(
                                "room-state read received a non-retryable transport response"
                            ) from error
                        if not retry_scheduled:
                            raise ApiRuntimeError(
                                "room-state read retry budget exhausted"
                            ) from error
                        assert retry_delay_seconds is not None
                        log.warning(
                            "api_private_state_read_retry",
                            run_id=run.run_id,
                            consecutive_failure=consecutive_state_read_failures,
                            retry_budget=config.state_read_retries,
                            retry_delay_seconds=retry_delay_seconds,
                            http_status=_transport_http_status(error),
                        )
                        time.sleep(retry_delay_seconds)
                        continue
                    consecutive_state_read_failures = 0
                    game = room.game
                    me = game.player_by_user(user_id) if game is not None else None
                    if game is None or me is None:
                        if shadow_policy is not None:
                            shadow_policy.reset()
                        terminal_recorded = False
                        lobby = _lobby_observation(room, user_id=user_id)
                        digest = _lobby_digest(lobby)
                        current_entry_team = _identity_entry_team(room, user_id=user_id)
                        if current_entry_team == config.entry_team:
                            entry_request_pending = False
                        if (
                            config.enter_match
                            and _should_request_match_entry(
                                room,
                                user_id=user_id,
                                entry_team=config.entry_team,
                            )
                            and not entry_request_pending
                        ):
                            previous_team = current_entry_team
                            if previous_team is not None:
                                client.cancel_entry()
                                store.append_event(
                                    run.run_id,
                                    EventKind.OBSERVATION,
                                    {
                                        "schema_version": 1,
                                        "mode": "private",
                                        "phase": "entry_cancelled",
                                        "previous_team": previous_team,
                                        "requested_team": config.entry_team,
                                    },
                                )
                            client.make_entry(team=config.entry_team)
                            entry_request_pending = True
                            store.append_event(
                                run.run_id,
                                EventKind.OBSERVATION,
                                {
                                    "schema_version": 1,
                                    "mode": "private",
                                    "phase": "entry_requested",
                                    "team": config.entry_team,
                                },
                            )
                        if digest != previous_digest:
                            store.append_event(run.run_id, EventKind.OBSERVATION, lobby)
                            previous_digest = digest
                            last_progress_at = time.monotonic()
                    else:
                        entry_request_pending = False
                        state = normalize_api_game_state(room, user_id=user_id)
                        digest = api_game_state_digest(state)
                        if digest != previous_digest:
                            if pending_action is not None:
                                previous_action, previous_state = pending_action
                                store.append_event(
                                    run.run_id,
                                    EventKind.TRANSITION,
                                    build_api_action_transition(
                                        previous_action,
                                        previous_state,
                                        state,
                                    ),
                                    occurred_at=state.observed_at,
                                )
                                pending_action = None
                            shadow_decision: ApiPolicyDecision | None = None
                            proposed_action: ApiLegalAction | None = None
                            if tactical_snapshot is not None:
                                legal_actions = verified_api_tactical_actions(
                                    room,
                                    user_id=user_id,
                                    bible_snapshot=tactical_snapshot,
                                )
                            else:
                                legal_actions = verified_api_actions(
                                    room,
                                    user_id=user_id,
                                )
                            if shadow_policy is not None:
                                shadow_decision, proposed_action = shadow_policy.decide(
                                    state,
                                    legal_actions,
                                )
                                decision, chosen_action = decide_api_action(
                                    ApiPolicyName.TACTICAL_HEURISTIC,
                                    state,
                                    legal_actions,
                                )
                            else:
                                decision, chosen_action = decide_api_action(
                                    config.policy,
                                    state,
                                    legal_actions,
                                )
                            decision_events: tuple[tuple[EventKind, BaseModel], ...] = (
                                ((EventKind.DECISION, shadow_decision),)
                                if shadow_decision is not None
                                else ()
                            ) + ((EventKind.DECISION, decision),)
                            store.append_events(
                                run.run_id,
                                (
                                    (EventKind.GAME_STATE, state),
                                    (EventKind.LEGAL_ACTIONS, legal_actions),
                                    *decision_events,
                                ),
                                occurred_at=state.observed_at,
                            )
                            states_recorded += 1
                            previous_digest = digest
                            last_progress_at = time.monotonic()
                            log.info(
                                "api_private_state_recorded",
                                run_id=run.run_id,
                                phase=state.phase.value,
                                field_number=state.field_number,
                                states_recorded=states_recorded,
                            )
                            terminal = classify_api_two_player_terminal(state)
                            if terminal is not None:
                                if shadow_policy is not None:
                                    shadow_policy.reset()
                                if config.max_seconds != 0:
                                    return _finish_terminal_run(
                                        store,
                                        run,
                                        terminal,
                                        states_recorded=states_recorded,
                                        in_match_actions=in_match_actions,
                                    )
                                if not terminal_recorded:
                                    _record_terminal_outcome(store, run, terminal)
                                    games_completed += 1
                                    terminal_recorded = True
                            elif state.phase is ApiPhase.TERMINAL:
                                if shadow_policy is not None:
                                    shadow_policy.reset()
                                if config.max_seconds != 0:
                                    outcome_reason = "unclassified_terminal"
                                    break
                                if not terminal_recorded:
                                    store.append_event(
                                        run.run_id,
                                        EventKind.MATCH_END,
                                        {
                                            "schema_version": 1,
                                            "observed_at": state.observed_at.isoformat(),
                                            "terminal_state_digest": digest,
                                            "result": "unclassified",
                                            "player_count": len(state.players),
                                        },
                                        occurred_at=state.observed_at,
                                    )
                                    games_completed += 1
                                    terminal_recorded = True
                            else:
                                terminal_recorded = False
                            if state.phase is not ApiPhase.TERMINAL and decision.executable:
                                if chosen_action is None:
                                    raise ApiRuntimeError(
                                        "executable API decision has no legal action"
                                    )
                                if in_match_actions >= config.max_in_match_actions:
                                    outcome_reason = "action_limit"
                                    break
                                if shadow_policy is not None:
                                    shadow_policy.observe_behavior(
                                        proposed_action,
                                        chosen_action,
                                    )
                                action_started = time.perf_counter()
                                try:
                                    client.submit(command_for_api_action(chosen_action))
                                except Exception:
                                    execution = ApiActionExecutionResult(
                                        executed_at=datetime.now(UTC),
                                        action_id=chosen_action.action_id,
                                        kind=chosen_action.kind,
                                        dispatched=True,
                                        server_acknowledged=None,
                                        latency_ms=(time.perf_counter() - action_started) * 1000,
                                    )
                                    store.append_events(
                                        run.run_id,
                                        (
                                            (EventKind.ACTION_RESULT, execution),
                                            (
                                                EventKind.TRANSITION,
                                                build_api_action_transition(
                                                    chosen_action,
                                                    state,
                                                    None,
                                                ),
                                            ),
                                        ),
                                    )
                                    raise
                                execution = ApiActionExecutionResult(
                                    executed_at=datetime.now(UTC),
                                    action_id=chosen_action.action_id,
                                    kind=chosen_action.kind,
                                    dispatched=True,
                                    server_acknowledged=True,
                                    latency_ms=(time.perf_counter() - action_started) * 1000,
                                )
                                store.append_event(
                                    run.run_id,
                                    EventKind.ACTION_RESULT,
                                    execution,
                                )
                                pending_action = (chosen_action, state)
                                in_match_actions += 1
                                log.info(
                                    "api_private_action_dispatched",
                                    run_id=run.run_id,
                                    action=chosen_action.action_id,
                                    action_count=in_match_actions,
                                )
                            elif (
                                config.policy is not ApiPolicyName.OBSERVER
                                and state.phase
                                in {ApiPhase.TURN, ApiPhase.DEFENSE, ApiPhase.PURCHASE}
                                and state.awaiting_player_id == state.self_player_id
                            ):
                                outcome_reason = "unsupported_self_turn"
                                log.warning(
                                    "api_private_unsupported_self_turn",
                                    run_id=run.run_id,
                                    phase=state.phase.value,
                                    field_number=state.field_number,
                                )
                                break
                    if time.monotonic() - last_progress_at >= config.no_progress_seconds:
                        outcome_reason = "no_progress_limit"
                        break
                    time.sleep(config.poll_seconds)
            finally:
                try:
                    client.leave_room()
                except Exception as error:
                    log.warning(
                        "api_private_leave_failed",
                        error_type=type(error).__name__,
                        reason="private-room cleanup request failed",
                    )
    except KeyboardInterrupt:
        outcome_reason = "operator_interrupt"
    except Exception as error:
        if pending_action is not None:
            action, before_state = pending_action
            store.append_event(
                run.run_id,
                EventKind.TRANSITION,
                build_api_action_transition(action, before_state, None),
            )
            pending_action = None
        payload = _safe_runtime_error_payload(error)
        store.append_event(run.run_id, EventKind.ERROR, payload)
        return store.finish_run(run.run_id, RunStatus.FAILED, outcome=payload)
    if pending_action is not None:
        action, before_state = pending_action
        store.append_event(
            run.run_id,
            EventKind.TRANSITION,
            build_api_action_transition(action, before_state, None),
        )
    return store.finish_run(
        run.run_id,
        RunStatus.ABORTED,
        outcome={
            "reason": outcome_reason,
            "states_recorded": states_recorded,
            "in_match_actions": in_match_actions,
            "games_completed": games_completed,
        },
    )
