import stat

import pytest

from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.run_store import RunStore, RunStoreError

CLIENT_SHA256 = "a" * 64


def spec() -> RunSpec:
    return RunSpec(
        mode=RunMode.TRAINING,
        identity="ロキ-67",
        client_sha256=CLIENT_SHA256,
        policy_id="heuristic-v0",
        config={"max_games": 1},
    )


def test_run_events_are_ordered_and_round_trip(tmp_path) -> None:
    store = RunStore(tmp_path / "private" / "runs.sqlite")
    run = store.start_run(spec())

    first = store.append_event(run.run_id, EventKind.GAME_STATE, {"field_number": 0})
    second = store.append_event(run.run_id, EventKind.DECISION, {"action": "wait"})
    finished = store.finish_run(
        run.run_id,
        RunStatus.ABORTED,
        outcome={"reason": "probe_complete"},
    )

    assert [event.sequence for event in store.events(run.run_id)] == [0, 1]
    assert first.payload == {"field_number": 0}
    assert second.kind is EventKind.DECISION
    assert finished.status is RunStatus.ABORTED
    assert finished.outcome == {"reason": "probe_complete"}
    assert store.recent_runs() == (finished,)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_finished_run_rejects_more_events(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.start_run(spec())
    store.finish_run(run.run_id, RunStatus.COMPLETED)

    with pytest.raises(RunStoreError, match="finished run"):
        store.append_event(run.run_id, EventKind.REWARD, {"reward": 1})


def test_unknown_run_cannot_be_finished(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    store.initialize()

    with pytest.raises(RunStoreError, match="unknown or already finished"):
        store.finish_run("missing", RunStatus.FAILED)
