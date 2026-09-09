import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
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
from godfield_bot.api_game import (
    ApiActionKind,
    ApiPolicyDecision,
    normalize_api_game_state,
    verified_api_actions,
    verified_api_tactical_actions,
)
from godfield_bot.api_runtime import (
    ACCEPTED_PRIVATE_BIBLE_CLIENT_SHA256,
    ApiPolicyName,
    ApiRuntimeError,
    PrivateApiRunConfig,
    _read_password_file,
    _within_wall_clock_limit,
    api_environment_fingerprint,
    decide_api_action,
    run_private_api_observer,
)
from godfield_bot.config import AppSettings
from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)
from godfield_bot.domain.run import EventKind, RunStatus
from godfield_bot.run_store import RunStore


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            {"name": "Club", "imageName": "club", "category": "weapons", "atk": 5},
            {
                "name": "Shield",
                "imageName": "shield",
                "category": "armor",
                "def": 8,
            },
            {"name": "Hidden", "category": "miracles", "atk": 99},
            {
                "name": "Strong Shield",
                "imageName": "strong-shield",
                "category": "armor",
                "def": 12,
            },
            {
                "name": "Cleanser",
                "category": "sundries",
                "ability": "removeAllCurses",
            },
            {
                "name": "Blowgun",
                "imageName": "blowgun",
                "category": "weapons",
                "atk": 3,
                "isPlusAtk": True,
            },
            {
                "name": "Romance Water",
                "imageName": "romance-water",
                "category": "sundries",
                "ability": "boostHP",
                "abilityValue": 15,
            },
            {
                "name": "Smile Flower",
                "imageName": "smile-flower",
                "category": "sundries",
                "ability": "boostMP",
                "abilityValue": 5,
            },
            {
                "name": "Dream",
                "imageName": "dream",
                "category": "miracles",
                "ability": "addCurse",
                "cost": 6,
                "element": "wood",
            },
            {
                "name": "Wall",
                "imageName": "wall",
                "category": "miracles",
                "ability": "blockWeapon",
                "cost": 6,
            },
        ]
    )


def combo_bible() -> BibleSnapshot:
    return BibleSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/",
        language="en",
        client=ClientFingerprint(
            url="https://godfield.net/main.dart.js",
            sha256=ACCEPTED_PRIVATE_BIBLE_CLIENT_SHA256,
        ),
        reference_sections={},
        catalog={
            "weapons": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="club",
                        image_path="/images/items/weapons/club.webp",
                        detail=("Club", "ATK5", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="blowgun",
                        image_path="/images/items/weapons/blowgun.webp",
                        detail=("Blowgun", "+ATK3", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
            "armor": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="shield",
                        image_path="/images/items/armor/shield.webp",
                        detail=("Shield", "DEF8", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="strong-shield",
                        image_path="/images/items/armor/strong-shield.webp",
                        detail=("Strong Shield", "DEF12", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
        },
        total_artifacts=4,
    )


def catalog_snapshot() -> ApiCatalogSnapshot:
    items = tuple(
        ApiCatalogItem(model_id=model.model_id, raw=dict(model.raw)) for model in catalog()
    )
    return ApiCatalogSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/i18n/en.json",
        language="en",
        upstream_revision="b33a31276b7e4dbaea962ff0df3ad3d1089a719d",
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


def test_private_api_heuristic_uses_a_reliable_weapon_on_a_cursed_turn() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert state.has_active_curses is True
    assert chosen is not None
    assert chosen.kind is ApiActionKind.USE_ITEM
    assert chosen.item_instance_ids == (11,)
    assert decision.executable is True
    assert decision.rationale == "use the strongest conservative card with a reliable identity"


def test_private_api_heuristic_abstains_from_unverified_cursed_turn_pass() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    room.raw["game"]["players"][0]["items"] = [{"id": 11, "modelId": None, "fakeModelId": 1}]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert legal_actions.actions == ()
    assert chosen is None
    assert decision.executable is False
    assert decision.rationale == "no verified API action is available; abstain without submitting"


def test_private_api_heuristic_prefers_a_verified_curse_cleanser() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    room.raw["game"]["players"][0]["items"] = [{"id": 22, "modelId": 5}]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (22,)
    assert decision.rationale == "remove active curses with a verified cleanser"


def test_tactical_heuristic_uses_strict_attack_combo() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 16, "modelId": 6},
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (11, 16)
    assert decision.rationale == "use the strongest verified attack combination"


def test_tactical_heuristic_uses_least_sufficient_armor_combination() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 20, "modelId": 2},
        {"id": 21, "modelId": 4},
    ]
    room.raw["game"]["attacks"] = [
        {
            "playerId": 2,
            "targetPlayerId": 1,
            "itemModelIds": [1],
            "atk": 15,
        }
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (20, 21)
    assert decision.rationale == "use the least excessive verified defense that prevents all damage"


def test_tactical_heuristic_heals_at_low_hp_unless_attack_is_lethal() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["hp"] = 12
    room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 17, "modelId": 7},
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (17,)
    assert decision.rationale == "restore HP before it falls into common lethal range"

    room.raw["game"]["players"][1]["hp"] = 5
    lethal_state = normalize_api_game_state(room, user_id="loki-user")
    lethal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )
    lethal_decision, lethal = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        lethal_state,
        lethal_actions,
    )

    assert lethal is not None
    assert lethal.item_instance_ids == (11,)
    assert lethal_decision.rationale == "use the least costly attack with potentially lethal power"


def test_tactical_heuristic_uses_affordable_fixed_damage_miracle() -> None:
    room = active_room(opponent_hp=100)
    room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 13, "modelId": 3},
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "miracle-attack:13:3:2"
    assert decision.rationale == "use the strongest verified attack"


def test_tactical_heuristic_focuses_the_weakest_multiplayer_opponent() -> None:
    room = active_room()
    room.raw["game"]["players"].append(
        {
            "id": 3,
            "userId": "weak-user",
            "name": "Weak Opponent",
            "hp": 10,
            "mp": 10,
            "cp": 20,
            "team": 0,
            "items": [],
        }
    )
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    _decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.target_player_id == 3


def test_tactical_heuristic_uses_targeted_curse_instead_of_stalling() -> None:
    room = active_room(opponent_hp=7)
    room.raw["game"]["players"][0]["curses"] = ["dream"]
    room.raw["game"]["players"][0]["mp"] = 10
    room.raw["game"]["players"][0]["items"] = [{"id": 19, "modelId": 9}]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.action_id == "miracle-curse:19:9:2"
    assert decision.rationale == "use a deterministic targeted curse instead of stalling"


def test_tactical_heuristic_values_verified_special_block_as_full_defense() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 20, "modelId": 2},
        {"id": 30, "modelId": 10},
    ]
    room.raw["game"]["players"][0]["mp"] = 10
    room.raw["game"]["attacks"] = [
        {
            "playerId": 2,
            "targetPlayerId": 1,
            "itemModelIds": [1],
            "atk": 10,
        }
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_tactical_actions(
        room,
        user_id="loki-user",
        bible_snapshot=combo_bible(),
    )

    decision, chosen = decide_api_action(
        ApiPolicyName.TACTICAL_HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (30,)
    assert decision.rationale == "use the least excessive verified defense that prevents all damage"


def test_private_api_heuristic_preserves_excess_defense() -> None:
    room = active_room()
    room.raw["game"]["players"][0]["items"] = [
        {"id": 20, "modelId": 2},
        {"id": 21, "modelId": 4},
    ]
    room.raw["game"]["attacks"] = [
        {
            "playerId": 2,
            "targetPlayerId": 1,
            "itemModelIds": [1],
            "atk": 7,
        }
    ]
    state = normalize_api_game_state(room, user_id="loki-user")
    legal_actions = verified_api_actions(room, user_id="loki-user")

    decision, chosen = decide_api_action(
        ApiPolicyName.HEURISTIC,
        state,
        legal_actions,
    )

    assert chosen is not None
    assert chosen.item_instance_ids == (20,)
    assert decision.rationale == "use the weakest sufficient conservative defense"


def empty_lobby() -> RoomState:
    return RoomState(
        {
            "users": [{"id": "loki-user", "name": "ロキ-67"}],
            "entries": [],
            "userCount": 1,
        },
        catalog(),
    )


def entered_lobby(*, team: int | None) -> RoomState:
    room = empty_lobby()
    room.raw["entries"] = [{"userId": "loki-user", "team": team}]
    return room


class FakeClient:
    user_id = "loki-user"

    def __init__(self) -> None:
        self.joined = False
        self.entered = False
        self.keepalive = False
        self.left = False
        self.matched = False
        self.cancelled_entries = 0
        self.entry_teams: list[int] = []

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
        self.entry_teams.append(team)
        self.entered = True

    def cancel_entry(self) -> None:
        self.cancelled_entries += 1

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
    with pytest.raises(ValidationError, match="explicit match entry"):
        PrivateApiRunConfig(
            room_id="private-room",
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match=r"zero \(unlimited\) or at least 10"):
        PrivateApiRunConfig(room_id="private-room", max_seconds=1)
    with pytest.raises(ValidationError, match="less than or equal to 4"):
        PrivateApiRunConfig(room_id="private-room", entry_team=5)
    with pytest.raises(ValidationError, match="requires explicit match entry"):
        PrivateApiRunConfig(room_id="private-room", entry_team=2)
    with pytest.raises(ValidationError, match="requires a model directory"):
        PrivateApiRunConfig(
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.NEURAL_SHADOW,
            max_in_match_actions=1,
        )
    with pytest.raises(ValidationError, match="only valid for neural shadow policy"):
        PrivateApiRunConfig(
            room_id="private-room",
            model_directory=Path("models/candidate"),
        )


def test_zero_max_seconds_disables_only_the_wall_clock_limit() -> None:
    config = PrivateApiRunConfig(room_id="private-room", max_seconds=0)

    assert config.max_seconds == 0
    assert _within_wall_clock_limit(elapsed=10_000_000, max_seconds=config.max_seconds)
    assert _within_wall_clock_limit(elapsed=9.9, max_seconds=10)
    assert not _within_wall_clock_limit(elapsed=10, max_seconds=10)


def test_tactical_policy_rejects_an_unaccepted_bible_snapshot(tmp_path) -> None:
    catalog_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), catalog_path)
    bible_path = tmp_path / "bible.json"
    unaccepted = combo_bible().model_copy(
        update={
            "client": ClientFingerprint(
                url="https://godfield.net/main.dart.js",
                sha256="f" * 64,
            )
        }
    )
    bible_path.write_text(unaccepted.model_dump_json(), encoding="utf-8")

    with pytest.raises(ApiRuntimeError, match="not been accepted"):
        run_private_api_observer(
            AppSettings(state_root=tmp_path / "state"),
            PrivateApiRunConfig(
                database=tmp_path / "runs.sqlite",
                catalog_snapshot=catalog_path,
                bible_snapshot=bible_path,
                room_id="private-room",
                enter_match=True,
                policy=ApiPolicyName.TACTICAL_HEURISTIC,
                max_in_match_actions=1,
            ),
        )


def test_unlimited_session_stays_in_room_after_a_terminal_match(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakePersistentClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([terminal_room(), empty_lobby()])

        def state(self) -> RoomState:
            try:
                return next(self.states)
            except StopIteration:
                raise KeyboardInterrupt from None

    client = FakePersistentClient()

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
            room_id="private-room",
            max_seconds=0,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.ABORTED
    assert run.outcome is not None
    assert run.outcome["reason"] == "operator_interrupt"
    assert run.outcome["games_completed"] == 1
    assert [event.kind for event in RunStore(database).events(run.run_id)].count(
        EventKind.MATCH_END
    ) == 1
    assert client.left is True


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
    assert client.entry_teams == [0]
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    events = RunStore(database).events(run.run_id)
    assert EventKind.ACTION_RESULT in {event.kind for event in events}
    transitions = [event for event in events if event.kind is EventKind.TRANSITION]
    assert len(transitions) == 1
    assert transitions[0].payload["state_changed"] is True
    assert transitions[0].payload["player_hp_deltas"] == {"2": -35}


def test_private_api_tactical_policy_dispatches_verified_combo(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    bible_path = tmp_path / "bible.json"
    bible_path.write_text(combo_bible().model_dump_json(), encoding="utf-8")
    combo_room = active_room()
    combo_room.raw["game"]["players"][0]["items"] = [
        {"id": 11, "modelId": 1},
        {"id": 16, "modelId": 6},
    ]

    class FakeTacticalClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([combo_room, terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeTacticalClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            bible_snapshot=bible_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.policy_id == ApiPolicyName.TACTICAL_HEURISTIC.value
    assert client.commands == [{"itemIds": [11, 16], "targetPlayerId": 2}]


def test_private_api_tactical_policy_aborts_immediately_on_unsupported_self_turn(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    bible_path = tmp_path / "bible.json"
    bible_path.write_text(combo_bible().model_dump_json(), encoding="utf-8")
    unsupported_room = active_room()
    unsupported_room.raw["game"]["players"][0]["curses"] = ["dream"]
    unsupported_room.raw["game"]["players"][0]["items"] = [
        {"id": 31, "modelId": None, "fakeModelId": 1}
    ]

    class FakeUnsupportedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.state_calls = 0
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            self.state_calls += 1
            return unsupported_room

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeUnsupportedClient()

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
            bible_snapshot=bible_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.TACTICAL_HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.ABORTED
    assert run.outcome is not None
    assert run.outcome["reason"] == "unsupported_self_turn"
    assert run.outcome["states_recorded"] == 1
    assert client.state_calls == 1
    assert client.commands == []
    events = RunStore(database).events(run.run_id)
    decisions = [event for event in events if event.kind is EventKind.DECISION]
    assert len(decisions) == 1
    assert decisions[0].payload["executable"] is False


def test_private_api_neural_shadow_records_proposal_but_dispatches_heuristic(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakePlayingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([active_room(), terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    class FakeShadowPolicy:
        def __init__(self) -> None:
            self.snapshot = combo_bible()
            self.manifest = SimpleNamespace(
                feature_schema_version=4,
                model_id="shadow-candidate",
                weights_sha256="b" * 64,
            )
            self.policy_id = ApiPolicyName.NEURAL_SHADOW.value
            self.behaviors: list[tuple[str | None, str | None]] = []

        def reset(self) -> None:
            pass

        def decide(self, state, legal_actions):
            proposal = next(
                (
                    action
                    for action in legal_actions.actions
                    if action.kind is ApiActionKind.USE_ITEM
                ),
                None,
            )
            return (
                ApiPolicyDecision(
                    decided_at=state.observed_at,
                    policy_id=ApiPolicyName.NEURAL_SHADOW.value,
                    state_digest=legal_actions.state_digest,
                    chosen_action_id=proposal.action_id if proposal is not None else None,
                    scores={
                        action.action_id: float(action is proposal)
                        for action in legal_actions.actions
                    },
                    rationale="fixture shadow proposal",
                    executable=False,
                    model_id=self.manifest.model_id,
                    model_weights_sha256=self.manifest.weights_sha256,
                ),
                proposal,
            )

        def observe_behavior(self, proposal, behavior) -> None:
            self.behaviors.append(
                (
                    proposal.action_id if proposal is not None else None,
                    behavior.action_id if behavior is not None else None,
                )
            )

    client = FakePlayingClient()
    shadow = FakeShadowPolicy()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr(
        "godfield_bot.api_neural.load_api_combo_shadow_policy",
        lambda model_directory, bible_snapshot: shadow,
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)
    database = tmp_path / "runs" / "api.sqlite"

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=database,
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.NEURAL_SHADOW,
            model_directory=tmp_path / "model",
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.config["behavior_policy"] == ApiPolicyName.TACTICAL_HEURISTIC.value
    assert run.config["shadow_policy_id"] == ApiPolicyName.NEURAL_SHADOW.value
    assert run.config["shadow_feature_schema_version"] == 4
    assert run.config["shadow_model_id"] == "shadow-candidate"
    assert run.model_id == "shadow-candidate"
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]
    assert shadow.behaviors == [("use:11:1:2", "use:11:1:2")]
    decisions = [
        event.payload
        for event in RunStore(database).events(run.run_id)
        if event.kind is EventKind.DECISION
    ]
    assert [decision["policy_id"] for decision in decisions[:2]] == [
        ApiPolicyName.NEURAL_SHADOW.value,
        ApiPolicyName.TACTICAL_HEURISTIC.value,
    ]
    assert decisions[0]["executable"] is False
    assert decisions[1]["executable"] is True


def test_private_api_heuristic_dispatches_reliable_weapon_for_cursed_turn(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    cursed_room = active_room()
    cursed_room.raw["game"]["players"][0]["curses"] = ["dream"]

    class FakeCursedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([cursed_room, terminal_room()])
            self.commands: list[dict[str, object]] = []

        def state(self) -> RoomState:
            return next(self.states)

        def submit(self, command) -> None:
            self.commands.append(command.to_dict())

    client = FakeCursedClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            room_id="private-room",
            enter_match=True,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
    )

    assert run.status is RunStatus.COMPLETED
    assert run.outcome is not None
    assert run.outcome["in_match_actions"] == 1
    assert client.commands == [{"itemIds": [11], "targetPlayerId": 2}]


def test_private_api_heuristic_enters_selected_multiplayer_team(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeTeamClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([empty_lobby(), terminal_room()])

        def state(self) -> RoomState:
            return next(self.states)

    client = FakeTeamClient()

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
            entry_team=3,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert run.config["entry_team"] == 3
    assert client.entry_teams == [3]
    requested = [
        event.payload
        for event in RunStore(database).events(run.run_id)
        if event.kind is EventKind.OBSERVATION and event.payload.get("phase") == "entry_requested"
    ]
    assert requested == [
        {
            "schema_version": 1,
            "mode": "private",
            "phase": "entry_requested",
            "team": 3,
        }
    ]


def test_private_api_heuristic_switches_an_existing_lobby_team(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)

    class FakeTeamSwitchClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([entered_lobby(team=1), terminal_room()])

        def state(self) -> RoomState:
            return next(self.states)

    client = FakeTeamSwitchClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            enter_match=True,
            entry_team=4,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert client.cancelled_entries == 1
    assert client.entry_teams == [4]


def test_private_api_team_entry_is_not_retried_before_acknowledgement(
    tmp_path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "catalog.json"
    write_api_catalog_snapshot(catalog_snapshot(), snapshot_path)
    changed_lobby = empty_lobby()
    changed_lobby.raw["users"].append({"id": "other-user", "name": "Opponent"})
    changed_lobby.raw["userCount"] = 2

    class FakeDelayedEntryClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.states = iter([empty_lobby(), changed_lobby, terminal_room()])

        def state(self) -> RoomState:
            return next(self.states)

    client = FakeDelayedEntryClient()

    @contextmanager
    def fake_open_api_client(*args, **kwargs):
        yield client

    monkeypatch.setattr("godfield_bot.api_runtime.open_api_client", fake_open_api_client)
    monkeypatch.setattr(
        "godfield_bot.api_runtime.validate_api_credentials",
        lambda settings: SimpleNamespace(user_id="loki-user"),
    )
    monkeypatch.setattr("godfield_bot.api_runtime.time.sleep", lambda seconds: None)

    run = run_private_api_observer(
        AppSettings(state_root=tmp_path / "state"),
        PrivateApiRunConfig(
            database=tmp_path / "runs" / "api.sqlite",
            catalog_snapshot=snapshot_path,
            enter_match=True,
            entry_team=2,
            policy=ApiPolicyName.HEURISTIC,
            max_in_match_actions=5,
            max_seconds=10,
            no_progress_seconds=10,
        ),
        room_password="astra-vs-humans",
    )

    assert run.status is RunStatus.COMPLETED
    assert client.entry_teams == [2]
