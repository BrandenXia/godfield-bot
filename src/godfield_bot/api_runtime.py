from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field, JsonValue, field_validator

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
    ApiGameState,
    ApiLegalActionSet,
    ApiPhase,
    api_game_state_digest,
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


class PrivateApiRunConfig(BaseModel):
    database: Path = Path("runs", "godfield.sqlite")
    catalog_snapshot: Path = Path(
        "data",
        "snapshots",
        "2026-09-07",
        "api-catalog-en.json",
    )
    room_id: str = Field(min_length=1, max_length=256)
    password_file: Path | None = None
    max_seconds: float = Field(default=90.0, ge=10.0, le=3600.0)
    poll_seconds: float = Field(default=1.0, ge=0.25, le=10.0)
    no_progress_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    request_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)

    @field_validator("room_id")
    @classmethod
    def room_id_has_no_outer_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("room ID must not start or end with whitespace")
        return value


class ApiObserverDecision(BaseModel):
    schema_version: int = 1
    decided_at: datetime
    policy_id: str = "api-observer-v0"
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    chosen_action_id: None = None
    executable: bool = False
    rationale: str = "observation-only private API safety gate"


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
    if len(raw_password) > 258:
        raise ApiRuntimeError("the private-room password file has an invalid value")
    if raw_password.endswith("\r\n"):
        password = raw_password[:-2]
    elif raw_password.endswith("\n"):
        password = raw_password[:-1]
    else:
        password = raw_password
    if not password or len(password) > 256 or "\n" in password or "\r" in password:
        raise ApiRuntimeError("the private-room password file has an invalid value")
    return password


def api_environment_fingerprint(snapshot: ApiCatalogSnapshot) -> str:
    material = f"pygodfield:{PYGODFIELD_REVISION}:catalog:{snapshot.content_sha256}"
    return hashlib.sha256(material.encode()).hexdigest()


def _lobby_observation(room: Any, *, user_id: str) -> dict[str, JsonValue]:
    user_ids = room.user_ids()
    entry_ids = room.entry_ids()
    return {
        "schema_version": 1,
        "mode": "private",
        "phase": "lobby",
        "user_count": int(room.user_count),
        "entry_count": len(entry_ids),
        "identity_present": user_id in user_ids,
        "identity_entered": user_id in entry_ids,
        "active_game": room.game is not None,
    }


def _lobby_digest(observation: dict[str, JsonValue]) -> str:
    canonical = json.dumps(observation, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _safe_runtime_error_reason(error: Exception) -> str:
    if isinstance(error, (ApiRuntimeError, ApiAccountError)):
        return str(error).splitlines()[0]
    return "pygodfield private-room operation failed"


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


def _finish_terminal_run(
    store: RunStore,
    run: RunRecord,
    outcome: ApiPrivateMatchOutcome,
    *,
    states_recorded: int,
) -> RunRecord:
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
    return store.finish_run(
        run.run_id,
        RunStatus.COMPLETED,
        outcome={
            "reason": "classified_terminal",
            "result": outcome.result.value,
            "reward": reward.value,
            "terminal_state_digest": outcome.terminal_state_digest,
            "states_recorded": states_recorded,
            "in_match_actions": 0,
        },
    )


def run_private_api_observer(
    settings: AppSettings,
    config: PrivateApiRunConfig,
) -> RunRecord:
    """Join one existing private room and record bounded, observation-only state."""

    if settings.public_duel_enabled:
        raise ApiRuntimeError("private API observer requires public Duel to remain disabled")
    password = _read_password_file(config.password_file)
    snapshot = read_api_catalog_snapshot(config.catalog_snapshot)
    if snapshot.upstream_revision != PYGODFIELD_REVISION:
        raise ApiRuntimeError("catalog snapshot was captured by a different pygodfield revision")
    catalog = item_catalog_from_snapshot(snapshot)
    environment_fingerprint = api_environment_fingerprint(snapshot)
    store = RunStore(config.database)
    run = store.start_run(
        RunSpec(
            mode=RunMode.PRIVATE,
            identity=settings.identity,
            client_sha256=environment_fingerprint,
            policy_id="api-observer-v0",
            config={
                "max_games": 1,
                "max_seconds": config.max_seconds,
                "poll_seconds": config.poll_seconds,
                "no_progress_seconds": config.no_progress_seconds,
                "max_in_match_actions": 0,
                "pygodfield_revision": PYGODFIELD_REVISION,
                "catalog_sha256": snapshot.content_sha256,
                "room_fingerprint": hashlib.sha256(config.room_id.encode()).hexdigest(),
            },
        )
    )
    states_recorded = 0
    outcome_reason = "wall_clock_limit"
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
            client.join_room(
                config.room_id,
                mode=Mode.PRIVATE,
                password=password,
            )
            try:
                client.make_entry(team=0)
                client.start_keepalive()
                started = time.monotonic()
                last_progress_at = started
                previous_digest: str | None = None
                while time.monotonic() - started < config.max_seconds:
                    room = client.state()
                    game = room.game
                    me = game.player_by_user(user_id) if game is not None else None
                    if game is None or me is None:
                        lobby = _lobby_observation(room, user_id=user_id)
                        digest = _lobby_digest(lobby)
                        if digest != previous_digest:
                            store.append_event(run.run_id, EventKind.OBSERVATION, lobby)
                            previous_digest = digest
                            last_progress_at = time.monotonic()
                    else:
                        state = normalize_api_game_state(room, user_id=user_id)
                        digest = api_game_state_digest(state)
                        if digest != previous_digest:
                            legal_actions: ApiLegalActionSet = verified_api_actions(
                                room,
                                user_id=user_id,
                            )
                            decision = ApiObserverDecision(
                                decided_at=datetime.now(UTC),
                                state_digest=digest,
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
                                return _finish_terminal_run(
                                    store,
                                    run,
                                    terminal,
                                    states_recorded=states_recorded,
                                )
                            if state.phase is ApiPhase.TERMINAL:
                                outcome_reason = "unclassified_terminal"
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
        payload: dict[str, JsonValue] = {
            "error_type": type(error).__name__,
            "reason": _safe_runtime_error_reason(error),
        }
        store.append_event(run.run_id, EventKind.ERROR, payload)
        return store.finish_run(run.run_id, RunStatus.FAILED, outcome=payload)
    return store.finish_run(
        run.run_id,
        RunStatus.ABORTED,
        outcome={
            "reason": outcome_reason,
            "states_recorded": states_recorded,
            "in_match_actions": 0,
        },
    )
