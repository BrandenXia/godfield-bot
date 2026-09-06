import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, JsonValue

from godfield_bot.browser.profile import prepare_private_directory
from godfield_bot.domain.run import EventKind, RunEvent, RunMode, RunRecord, RunSpec, RunStatus

SCHEMA_VERSION = 1


class RunStoreError(RuntimeError):
    """Raised when run history cannot be recorded consistently."""


class RunStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        prepare_private_directory(self.path.parent)
        connection = sqlite3.connect(self.path)
        try:
            os.chmod(self.path, 0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    version INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    identity TEXT NOT NULL,
                    client_sha256 TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    model_id TEXT,
                    config_json TEXT NOT NULL,
                    outcome_json TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE RESTRICT,
                    sequence INTEGER NOT NULL,
                    occurred_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE (run_id, sequence)
                );

                CREATE INDEX IF NOT EXISTS events_run_sequence
                    ON events (run_id, sequence);
                """
            )
            rows = connection.execute("SELECT version FROM schema_meta").fetchall()
            if not rows:
                connection.execute(
                    "INSERT INTO schema_meta (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif len(rows) != 1 or rows[0]["version"] != SCHEMA_VERSION:
                raise RunStoreError("unsupported or inconsistent run-store schema")
            connection.commit()

    def start_run(self, spec: RunSpec, *, started_at: datetime | None = None) -> RunRecord:
        self.initialize()
        record = RunRecord(
            **spec.model_dump(),
            run_id=str(uuid4()),
            started_at=started_at or datetime.now(UTC),
            status=RunStatus.RUNNING,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, started_at, status, mode, identity, client_sha256,
                    policy_id, model_id, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.started_at.isoformat(),
                    record.status.value,
                    record.mode.value,
                    record.identity,
                    record.client_sha256,
                    record.policy_id,
                    record.model_id,
                    _json(record.config),
                ),
            )
            connection.commit()
        return record

    def append_event(
        self,
        run_id: str,
        kind: EventKind,
        payload: BaseModel | dict[str, JsonValue],
        *,
        occurred_at: datetime | None = None,
    ) -> RunEvent:
        serialized_payload = (
            cast(dict[str, JsonValue], payload.model_dump(mode="json"))
            if isinstance(payload, BaseModel)
            else payload
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT status FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise RunStoreError("cannot append an event to an unknown run")
            if run["status"] != RunStatus.RUNNING.value:
                raise RunStoreError("cannot append an event to a finished run")
            sequence = cast(
                int,
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0],
            )
            event = RunEvent(
                run_id=run_id,
                sequence=sequence,
                occurred_at=occurred_at or datetime.now(UTC),
                kind=kind,
                payload=serialized_payload,
            )
            connection.execute(
                """
                INSERT INTO events (run_id, sequence, occurred_at, kind, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.run_id,
                    event.sequence,
                    event.occurred_at.isoformat(),
                    event.kind.value,
                    _json(event.payload),
                ),
            )
            connection.commit()
        return event

    def finish_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        outcome: dict[str, JsonValue] | None = None,
        ended_at: datetime | None = None,
    ) -> RunRecord:
        if status is RunStatus.RUNNING:
            raise RunStoreError("a finished run cannot retain running status")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET ended_at = ?, status = ?, outcome_json = ?
                WHERE run_id = ? AND status = ?
                """,
                (
                    (ended_at or datetime.now(UTC)).isoformat(),
                    status.value,
                    _json(outcome) if outcome is not None else None,
                    run_id,
                    RunStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RunStoreError("run is unknown or already finished")
            connection.commit()
        record = self.get_run(run_id)
        if record is None:  # pragma: no cover - guarded by the update
            raise RunStoreError("finished run disappeared")
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return _run_record(row) if row is not None else None

    def recent_runs(self, *, limit: int = 20) -> tuple[RunRecord, ...]:
        if limit < 1:
            raise RunStoreError("run listing limit must be positive")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(_run_record(row) for row in rows)

    def events(self, run_id: str) -> tuple[RunEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return tuple(
            RunEvent(
                run_id=cast(str, row["run_id"]),
                sequence=cast(int, row["sequence"]),
                occurred_at=datetime.fromisoformat(cast(str, row["occurred_at"])),
                kind=EventKind(cast(str, row["kind"])),
                payload=cast(dict[str, JsonValue], json.loads(row["payload_json"])),
            )
            for row in rows
        )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _run_record(row: sqlite3.Row) -> RunRecord:
    raw_outcome: Any = json.loads(row["outcome_json"]) if row["outcome_json"] else None
    return RunRecord(
        run_id=cast(str, row["run_id"]),
        started_at=datetime.fromisoformat(cast(str, row["started_at"])),
        ended_at=(datetime.fromisoformat(cast(str, row["ended_at"])) if row["ended_at"] else None),
        status=RunStatus(cast(str, row["status"])),
        mode=RunMode(cast(str, row["mode"])),
        identity=cast(str, row["identity"]),
        client_sha256=cast(str, row["client_sha256"]),
        policy_id=cast(str, row["policy_id"]),
        model_id=cast(str | None, row["model_id"]),
        config=cast(dict[str, JsonValue], json.loads(row["config_json"])),
        outcome=cast(dict[str, JsonValue] | None, raw_outcome),
    )
