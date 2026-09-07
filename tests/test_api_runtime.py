import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from godfield import ItemCatalog, RoomState
from pydantic import ValidationError

from godfield_bot.api_catalog import (
    ApiCatalogItem,
    ApiCatalogSnapshot,
    api_catalog_digest,
    write_api_catalog_snapshot,
)
from godfield_bot.api_runtime import (
    ApiPolicyName,
    ApiRuntimeError,
    PrivateApiRunConfig,
    _read_password_file,
    api_environment_fingerprint,
    run_private_api_observer,
)
from godfield_bot.config import AppSettings
from godfield_bot.domain.run import EventKind, RunStatus
from godfield_bot.run_store import RunStore


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            {"name": "Club", "category": "weapons", "atk": 5},
            {"name": "Shield", "category": "armor", "def": 5},
            {"name": "Hidden", "category": "miracles", "atk": 99},
        ]
    )


def catalog_snapshot() -> ApiCatalogSnapshot:
    items = tuple(
        ApiCatalogItem(model_id=model.model_id, raw=dict(model.raw)) for model in catalog()
    )
    return ApiCatalogSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/i18n/en.json",
        language="en",
        upstream_revision="679527115909cf9b516e6365b28c3221a33f3855",
        content_sha256=api_catalog_digest(items),
        total_items=len(items),
        items=items,
    )


def terminal_room() -> RoomState:
    return RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 12,
                        "mp": 4,
                        "cp": 9,
                        "team": 0,
                        "items": [{"id": 11, "modelId": 1}],
                    },
                    {
                        "id": 2,
                        "userId": "other-user",
                        "name": "Opponent",
                        "hp": 0,
                        "mp": 2,
                        "cp": 3,
                        "team": 0,
                        "items": [{"id": 99, "modelId": 3}],
                    },
                ],
                "attackTurnPlayerId": 1,
                "attacks": [],
                "gf": 11,
                "updateCount": 17,
                "isOver": True,
            }
        },
        catalog(),
    )


def active_room(*, opponent_hp: int = 35, update_count: int = 12) -> RoomState:
    room = terminal_room()
    room.raw["game"]["players"][1]["hp"] = opponent_hp
    room.raw["game"]["updateCount"] = update_count
    room.raw["game"]["isOver"] = False
    return room


def empty_lobby() -> RoomState:
    return RoomState(
        {
            "users": [{"id": "loki-user", "name": "ロキ-67"}],
            "entries": [],
            "userCount": 1,
        },
        catalog(),
    )


class FakeClient:
    user_id = "loki-user"

    def __init__(self) -> None:
        self.joined = False
        self.entered = False
        self.keepalive = False
        self.left = False
        self.matched = False

    def join_room(self, room_id, *, mode, password) -> None:
        assert room_id == "private-room"
        assert str(mode) == "private"
        assert password is None
        self.joined = True

    def enter(self, mode, *, password, lang) -> str:
        assert str(mode) == "private"
        assert password == "astra-vs-humans"
        assert lang == "en"
        self.matched = True
        return "opaque-internal-room-id"

    def make_entry(self, *, team) -> None:
        assert team == 0
        self.entered = True

    def start_keepalive(self) -> None:
        self.keepalive = True

    def state(self) -> RoomState:
        return terminal_room()

    def leave_room(self) -> None:
        self.left = True


def test_private_api_observer_records_terminal_sparse_outcome(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    snapshot = catalog_snapshot()
    write_api_catalog_snapshot(snapshot, snapshot_path)
    client = FakeClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["result"] == "win"
    assert run.outcome["reward"] == 1.0
    assert run.outcome["in_match_actions"] == 0
    assert client.joined and client.keepalive and client.left
    assert client.entered is False
    events = RunStore(database).events(run.run_id)
    assert [event.kind for event in events] == [
        EventKind.OBSERVATION,
        EventKind.GAME_STATE,
        EventKind.LEGAL_ACTIONS,
        EventKind.DECISION,
        EventKind.MATCH_END,
        EventKind.REWARD,
    ]
    state_payload = events[1].payload
    assert state_payload["players"][0]["name"] == "ロキ-67"
    assert state_payload["players"][1]["hand_count"] == 1
    assert state_payload["hand"][0]["instance_id"] == 11
    assert "items" not in state_payload["players"][1]
    assert run.client_sha256 == api_environment_fingerprint(snapshot)


def test_private_api_observer_supports_keyed_matchmaking_without_storing_key(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    client = FakeClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert client.matched is True
    assert client.entered is False
    serialized = run.model_dump_json() + "".join(
        event.model_dump_json() for event in RunStore(database).events(run.run_id)
    )
    assert "astra-vs-humans" not in serialized
    assert "opaque-internal-room-id" not in serialized


def test_password_file_must_be_owner_only(tmp_path) -> None:
    password_file = tmp_path / "room-password"
    password_file.write_text("secret\n", encoding="utf-8")
    password_file.chmod(0o644)

    with pytest.raises(ApiRuntimeError, match="expected 600"):
        _read_password_file(password_file)

    password_file.chmod(0o600)
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600
    assert _read_password_file(password_file) == "secret"


def test_api_policy_configuration_requires_explicit_safe_bounds() -> None:
    with pytest.raises(ValidationError, match="zero in-match action budget"):
        PrivateApiRunConfig(
            room_id="private-room",
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match="explicit match entry"):
        PrivateApiRunConfig(
            room_id="private-room",
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=1,
        )


def test_private_api_heuristic_enters_lobby_and_records_accepted_action(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakePlayingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter(
                [
                    empty_lobby(),
                    active_room(),
                    terminal_room(),
                ]
            )
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakePlayingClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert client.entered is True
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    events = RunStore(database).events(run.run_id)
    assert EventKind.ACTION_RESULT in {event.kind for event in events}
    transitions = [event for event in events if event.kind is EventKind.TRANSITION]
    assert len(transitions) == 1
    assert transitions[0].payload["state_changed"] is True
    assert transitions[0].payload["player_hp_deltas"] == {"2": -35}
