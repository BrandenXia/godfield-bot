import json
import stat
from datetime import UTC, datetime

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
from godfield_bot.replay import collect_replay_samples, export_replay_jsonl
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
            PlayerState(name="ロキ-67", hp=40, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=opponent_hp, mp=10, money=20, is_self=False),
        ),
        hand=(),
        scene_layers=(),
    )


def append_action_evidence(
    store: RunStore,
    run_id: str,
    *,
    before: GameState,
    after: GameState,
    embedded_after: GameState | None = None,
    omit_embedded_states: bool = False,
) -> None:
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
            blocked_reason="fixture covers one verified action",
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
    transition = build_action_transition(ACTION_ID, before, after)
    if embedded_after is not None:
        transition = transition.model_copy(update={"after_state": embedded_after})
    if omit_embedded_states:
        transition = transition.model_copy(update={"before_state": None, "after_state": None})
    store.append_event(run_id, EventKind.TRANSITION, transition)


def start_run(store: RunStore) -> str:
    return store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256=CLIENT_SHA256,
            policy_id="heuristic-v0",
            config={"max_games": 1},
        )
    ).run_id


def test_export_replay_writes_complete_accepted_sample(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run_id = start_run(store)
    before = game_state(field_number=1, opponent_hp=40)
    after = game_state(field_number=2, opponent_hp=35)
    append_action_evidence(store, run_id, before=before, after=after)
    store.finish_run(run_id, RunStatus.ABORTED, outcome={"reason": "action_limit"})

    destination = tmp_path / "exports" / "replay.jsonl"
    summary = export_replay_jsonl(store, destination)
    exported = json.loads(destination.read_text(encoding="utf-8"))

    assert summary.samples_exported == 1
    assert summary.transitions_seen == 1
    assert exported["run_id"] == run_id
    assert exported["chosen_action"]["action_id"] == ACTION_ID
    assert exported["before_state"]["field_number"] == 1
    assert exported["after_state"]["field_number"] == 2
    assert exported["transition"]["player_hp_deltas"] == {"CPU": -5}
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_replay_excludes_unchanged_and_failed_run_transitions(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    unchanged_run_id = start_run(store)
    unchanged = game_state(field_number=1, opponent_hp=40)
    append_action_evidence(
        store,
        unchanged_run_id,
        before=unchanged,
        after=unchanged.model_copy(update={"observed_at": datetime.now(UTC)}),
    )
    store.finish_run(unchanged_run_id, RunStatus.ABORTED)

    failed_run_id = start_run(store)
    append_action_evidence(
        store,
        failed_run_id,
        before=game_state(field_number=1, opponent_hp=40),
        after=game_state(field_number=2, opponent_hp=39),
    )
    store.finish_run(failed_run_id, RunStatus.FAILED)

    samples, summary = collect_replay_samples(store)

    assert samples == ()
    assert summary.transitions_seen == 2
    assert summary.skipped == {
        "run_status_failed": 1,
        "transition_not_accepted": 1,
    }


def test_replay_rejects_embedded_state_with_wrong_digest(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run_id = start_run(store)
    before = game_state(field_number=1, opponent_hp=40)
    after = game_state(field_number=2, opponent_hp=39)
    append_action_evidence(
        store,
        run_id,
        before=before,
        after=after,
        embedded_after=game_state(field_number=3, opponent_hp=12),
    )
    store.finish_run(run_id, RunStatus.ABORTED)

    samples, summary = collect_replay_samples(store)

    assert samples == ()
    assert summary.transitions_seen == 1
    assert summary.skipped == {"state_digest_mismatch": 1}


def test_replay_recovers_legacy_transition_from_adjacent_state_events(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    run_id = start_run(store)
    before = game_state(field_number=1, opponent_hp=40)
    after = game_state(field_number=2, opponent_hp=38)
    append_action_evidence(
        store,
        run_id,
        before=before,
        after=after,
        omit_embedded_states=True,
    )
    store.append_event(run_id, EventKind.GAME_STATE, after)
    store.finish_run(run_id, RunStatus.ABORTED)

    samples, summary = collect_replay_samples(store)

    assert len(samples) == 1
    assert samples[0].before_state == before
    assert samples[0].after_state == after
    assert summary.skipped == {}
