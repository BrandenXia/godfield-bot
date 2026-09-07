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
    ApiLegalAction,
    ApiLegalActionSet,
    ApiPhase,
    ApiPolicyDecision,
    api_game_state_digest,
    build_api_action_transition,
    command_for_api_action,
    normalize_api_game_state,
    verified_api_actions,
)
from godfield_bot.config import AppSettings
from godfield_bot.domain.outcome import MatchResult, SparseTerminalReward
from godfield_bot.domain.run import EventKind, RunMode, RunRecord, RunSpec, RunStatus
from godfield_bot.run_store import RunStore

log = structlog.get_logger()


class ApiRuntimeError(RuntimeError):
    """Raised when private API observation cannot continue safely."""


class ApiPolicyName(StrEnum):
    OBSERVER = "api-observer-v0"
    HEURISTIC = "api-heuristic-v0"


class PrivateApiRunConfig(BaseModel):
    database: Path = Path("runs", "godfield.sqlite")
    catalog_snapshot: Path = Path(
        "data",
        "snapshots",
        "2026-09-07",
        "api-catalog-en.json",
    )
    room_id: str | None = Field(default=None, min_length=1, max_length=256)
    password_file: Path | None = None
    enter_match: bool = False
    policy: ApiPolicyName = ApiPolicyName.OBSERVER
    max_in_match_actions: int = Field(default=0, ge=0, le=1000)
    max_seconds: float = Field(default=90.0, ge=0.0, le=3600.0)
    poll_seconds: float = Field(default=1.0, ge=0.25, le=10.0)
    no_progress_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    request_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)

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
        if self.policy is ApiPolicyName.HEURISTIC:
            if not self.enter_match:
                raise ValueError("api-heuristic-v0 requires explicit match entry")
            if self.max_in_match_actions < 1:
                raise ValueError("api-heuristic-v0 requires a positive action budget")
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


def _should_request_match_entry(room: Any, *, user_id: str) -> bool:
    game = room.game
    if game is not None and not game.is_over:
        return False
    return not room.is_entered(user_id)


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
            if action.kind is ApiActionKind.USE_ITEM and action.item_instance_ids
        ]
        hand_by_instance = {item.instance_id: item for item in state.hand}

        def action_value(action: ApiLegalAction) -> tuple[int, int]:
            item = hand_by_instance.get(action.item_instance_ids[0])
            if item is None:
                return (-1, -action.item_instance_ids[0])
            value = item.attack if state.phase is ApiPhase.TURN else item.defense
            return (value, -action.item_instance_ids[0])

        if candidates:
            chosen = max(candidates, key=action_value)
        else:
            chosen = next(
                (action for action in legal_actions.actions if action.kind is ApiActionKind.PASS),
                None,
            )
    executable = chosen is not None
    rationale = (
        "decline an unmodeled purchase"
        if chosen is not None and chosen.kind is ApiActionKind.DECLINE_PURCHASE
        else "use the strongest conservative single-card action"
        if chosen is not None and chosen.kind is ApiActionKind.USE_ITEM
        else "pass because no conservative card action is available"
        if chosen is not None
        else "the server is not awaiting an action from ロキ-67"
    )
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
    environment_fingerprint = api_environment_fingerprint(snapshot)
    store = RunStore(config.database)
    run_config: dict[str, JsonValue] = {
        "max_games": 0 if config.max_seconds == 0 else 1,
        "max_seconds": config.max_seconds,
        "poll_seconds": config.poll_seconds,
        "no_progress_seconds": config.no_progress_seconds,
        "max_in_match_actions": config.max_in_match_actions,
        "enter_match": config.enter_match,
        "policy": config.policy.value,
        "pygodfield_revision": PYGODFIELD_REVISION,
        "catalog_sha256": snapshot.content_sha256,
        "room_selector": "room_id" if config.room_id is not None else "matchmaking_key",
    }
    if config.room_id is not None:
        run_config["room_fingerprint"] = hashlib.sha256(config.room_id.encode()).hexdigest()
    run = store.start_run(
        RunSpec(
            mode=RunMode.PRIVATE,
            identity=settings.identity,
            client_sha256=environment_fingerprint,
            policy_id=config.policy.value,
            config=run_config,
        )
    )
    states_recorded = 0
    in_match_actions = 0
    games_completed = 0
    outcome_reason = "wall_clock_limit"
    pending_action: tuple[ApiLegalAction, ApiGameState] | None = None
    try:
        from godfield import Mode  # type: ignore[import-untyped]

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
                entry_request_digest: str | None = None
                terminal_recorded = False
                while _within_wall_clock_limit(
                    elapsed=time.monotonic() - started,
                    max_seconds=config.max_seconds,
                ):
                    room = client.state()
                    game = room.game
                    me = game.player_by_user(user_id) if game is not None else None
                    if game is None or me is None:
                        terminal_recorded = False
                        lobby = _lobby_observation(room, user_id=user_id)
                        digest = _lobby_digest(lobby)
                        if (
                            config.enter_match
                            and _should_request_match_entry(room, user_id=user_id)
                            and digest != entry_request_digest
                        ):
                            client.make_entry(team=0)
                            entry_request_digest = digest
                            store.append_event(
                                run.run_id,
                                EventKind.OBSERVATION,
                                {
                                    "schema_version": 1,
                                    "mode": "private",
                                    "phase": "entry_requested",
                                },
                            )
                        if digest != previous_digest:
                            store.append_event(run.run_id, EventKind.OBSERVATION, lobby)
                            previous_digest = digest
                            last_progress_at = time.monotonic()
                    else:
                        entry_request_digest = None
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
                            legal_actions: ApiLegalActionSet = verified_api_actions(
                                room,
                                user_id=user_id,
                            )
                            decision, chosen_action = decide_api_action(
                                config.policy,
                                state,
                                legal_actions,
                            )
                            store.append_events(
                                run.run_id,
                                (
                                    (EventKind.GAME_STATE, state),
                                    (EventKind.LEGAL_ACTIONS, legal_actions),
                                    (EventKind.DECISION, decision),
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
