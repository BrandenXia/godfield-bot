import json
import stat
from datetime import UTC, datetime

import pytest

from godfield_bot.domain.action import (
    ActionExecutionResult,
    ActionKind,
    LegalAction,
    LegalActionSet,
    PolicyDecision,
)
from godfield_bot.domain.game import GameState, PlayerState
from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.outcome_replay import (
    OutcomeReplayDatasetError,
    collect_outcome_replay,
    export_outcome_replay_jsonl,
    load_outcome_replay_jsonl,
)
from godfield_bot.outcomes import append_sparse_terminal_events
from godfield_bot.run_store import RunStore
from godfield_bot.runner import build_action_transition

CLIENT_SHA256 = "a" * 64
ACTION_ID = "forgive"


def game_state(*, field_number: int, opponent_hp: int) -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=field_number,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=20, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=opponent_hp, mp=10, money=20, is_self=False),
        ),
        hand=(),
        scene_layers=(),
    )


def start_run(
    store: RunStore,
    *,
    mode: RunMode = RunMode.TRAINING,
    model_id: str | None = None,
) -> str:
    return store.start_run(
        RunSpec(
            mode=mode,
            identity="ロキ-67",
            client_sha256=CLIENT_SHA256,
            policy_id="heuristic-v0",
            model_id=model_id,
        )
    ).run_id


def append_complete_episode(store: RunStore, run_id: str) -> None:
    before = game_state(field_number=8, opponent_hp=5)
    terminal_state = game_state(field_number=9, opponent_hp=0)
    digest = game_state_digest(before)
    action = LegalAction(
        action_id=ACTION_ID,
        kind=ActionKind.FORGIVE,
        label="Forgive verified incoming effect",
        artifact_asset_path="/images/items/weapons/bronze-club.webp",
        target_player_index=0,
        target_player_name="ロキ-67",
        control_panel="right",
    )
    store.append_event(run_id, EventKind.GAME_STATE, before)
    store.append_event(
        run_id,
        EventKind.LEGAL_ACTIONS,
        LegalActionSet(
            state_digest=digest,
            actions=(action,),
            coverage_complete=False,
            blocked_reason="fixture",
        ),
    )
    store.append_event(
        run_id,
        EventKind.DECISION,
        PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id="heuristic-v0",
            state_digest=digest,
            chosen_action_id=ACTION_ID,
            scores={ACTION_ID: 1.0},
            rationale="fixture",
            executable=True,
        ),
    )
    store.append_event(
        run_id,
        EventKind.ACTION_RESULT,
        ActionExecutionResult(
            executed_at=datetime.now(UTC),
            action_id=ACTION_ID,
            kind=ActionKind.FORGIVE,
            dispatched=True,
            latency_ms=1,
        ),
    )
    store.append_event(
        run_id,
        EventKind.TRANSITION,
        build_action_transition(ACTION_ID, before, terminal_state),
    )
    terminal = append_sparse_terminal_events(store, run_id, terminal_state)
    assert terminal is not None
    outcome, reward = terminal
    store.finish_run(
        run_id,
        RunStatus.COMPLETED,
        outcome={
            "reason": "classified_terminal",
            "result": outcome.result.value,
            "reward": reward.value,
            "terminal_state_digest": outcome.terminal_state_digest,
            "in_match_actions": 1,
        },
    )


def test_exports_and_loads_complete_terminal_labeled_episode(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run_id = start_run(store)
    append_complete_episode(store, run_id)

    destination = tmp_path / "exports" / "outcomes.jsonl"
    summary = export_outcome_replay_jsonl(store, destination)
    episodes = load_outcome_replay_jsonl(destination)

    assert summary.runs_scanned == 1
    assert summary.completed_runs_seen == 1
    assert summary.episodes_exported == 1
    assert summary.steps_exported == 1
    assert summary.skipped == {}
    assert len(episodes) == 1
    assert episodes[0].schema_version == 2
    assert episodes[0].mode is RunMode.TRAINING
    assert episodes[0].run_id == run_id
    assert episodes[0].reward.value == 1.0
    assert episodes[0].steps[0].transition.player_hp_deltas == {"CPU": -5}
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_excludes_aborted_and_completed_runs_without_terminal_evidence(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    aborted_id = start_run(store)
    store.finish_run(aborted_id, RunStatus.ABORTED)
    missing_id = start_run(store)
    store.finish_run(missing_id, RunStatus.COMPLETED)

    episodes, summary = collect_outcome_replay(store)

    assert episodes == ()
    assert summary.episodes_exported == 0
    assert summary.skipped == {
        "missing_terminal_evidence": 1,
        "run_status_aborted": 1,
    }


def test_loader_rejects_tampered_terminal_state(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run_id = start_run(store)
    append_complete_episode(store, run_id)
    destination = tmp_path / "outcomes.jsonl"
    export_outcome_replay_jsonl(store, destination)
    payload = json.loads(destination.read_text(encoding="utf-8"))
    payload["terminal_state"]["field_number"] = 99
    destination.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(OutcomeReplayDatasetError, match="terminal state digest"):
        load_outcome_replay_jsonl(destination)


def test_export_can_filter_outcomes_to_one_model(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    included_id = start_run(store, model_id="candidate-a")
    append_complete_episode(store, included_id)
    excluded_id = start_run(store, model_id="candidate-b")
    append_complete_episode(store, excluded_id)

    destination = tmp_path / "candidate-a.jsonl"
    summary = export_outcome_replay_jsonl(
        store,
        destination,
        model_id="candidate-a",
    )
    episodes = load_outcome_replay_jsonl(destination)

    assert [episode.run_id for episode in episodes] == [included_id]
    assert summary.skipped == {"model_id_mismatch": 1}
