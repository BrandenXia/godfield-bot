import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from godfield_bot.domain.action import (
    ActionExecutionResult,
    ActionTransition,
    LegalActionSet,
    PolicyDecision,
)
from godfield_bot.domain.game import GameState
from godfield_bot.domain.replay import ReplayExportSummary, ReplaySample
from godfield_bot.domain.run import EventKind, RunEvent, RunRecord, RunStatus
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.run_store import RunStore


class ReplayExportError(RuntimeError):
    """Raised when verified replay data cannot be exported safely."""


class ReplayDatasetError(RuntimeError):
    """Raised when an exported replay dataset fails its typed contract."""


def _parse_events(
    events: tuple[RunEvent, ...],
) -> tuple[
    list[tuple[int, GameState]],
    list[tuple[int, LegalActionSet]],
    list[tuple[int, PolicyDecision]],
    list[tuple[int, ActionExecutionResult]],
    list[tuple[int, ActionTransition]],
    Counter[str],
]:
    states: list[tuple[int, GameState]] = []
    legal_sets: list[tuple[int, LegalActionSet]] = []
    decisions: list[tuple[int, PolicyDecision]] = []
    executions: list[tuple[int, ActionExecutionResult]] = []
    transitions: list[tuple[int, ActionTransition]] = []
    skipped: Counter[str] = Counter()
    for event in events:
        try:
            if event.kind is EventKind.GAME_STATE:
                states.append((event.sequence, GameState.model_validate(event.payload)))
            elif event.kind is EventKind.LEGAL_ACTIONS:
                legal_sets.append((event.sequence, LegalActionSet.model_validate(event.payload)))
            elif event.kind is EventKind.DECISION:
                decisions.append((event.sequence, PolicyDecision.model_validate(event.payload)))
            elif event.kind is EventKind.ACTION_RESULT:
                executions.append(
                    (event.sequence, ActionExecutionResult.model_validate(event.payload))
                )
            elif event.kind is EventKind.TRANSITION:
                transitions.append(
                    (event.sequence, ActionTransition.model_validate(event.payload))
                )
        except ValidationError:
            if event.kind is EventKind.TRANSITION:
                skipped["invalid_transition"] += 1
    return states, legal_sets, decisions, executions, transitions, skipped


def _state_before(
    states: list[tuple[int, GameState]],
    sequence: int,
    lower_bound: int,
    digest: str,
) -> GameState | None:
    for event_sequence, state in reversed(states):
        if lower_bound < event_sequence < sequence and game_state_digest(state) == digest:
            return state
    return None


def _state_after(
    states: list[tuple[int, GameState]],
    sequence: int,
    upper_bound: int | None,
    digest: str,
) -> GameState | None:
    for event_sequence, state in states:
        if (
            event_sequence > sequence
            and (upper_bound is None or event_sequence < upper_bound)
            and game_state_digest(state) == digest
        ):
            return state
    return None


def _legal_before(
    legal_sets: list[tuple[int, LegalActionSet]],
    sequence: int,
    lower_bound: int,
    digest: str,
) -> tuple[int, LegalActionSet] | None:
    for event_sequence, legal_actions in reversed(legal_sets):
        if (
            lower_bound < event_sequence < sequence
            and legal_actions.state_digest == digest
        ):
            return event_sequence, legal_actions
    return None


def _decision_before(
    decisions: list[tuple[int, PolicyDecision]],
    sequence: int,
    lower_bound: int,
    digest: str,
    action_id: str,
) -> tuple[int, PolicyDecision] | None:
    for event_sequence, decision in reversed(decisions):
        if (
            lower_bound < event_sequence < sequence
            and decision.state_digest == digest
            and decision.chosen_action_id == action_id
        ):
            return event_sequence, decision
    return None


def _execution_before(
    executions: list[tuple[int, ActionExecutionResult]],
    sequence: int,
    lower_bound: int,
    action_id: str,
) -> tuple[int, ActionExecutionResult] | None:
    for event_sequence, execution in reversed(executions):
        if lower_bound < event_sequence < sequence and execution.action_id == action_id:
            return event_sequence, execution
    return None


def _samples_for_run(
    run: RunRecord,
    events: tuple[RunEvent, ...],
) -> tuple[list[ReplaySample], Counter[str], int]:
    states, legal_sets, decisions, executions, transitions, skipped = _parse_events(events)
    if run.status in {RunStatus.RUNNING, RunStatus.FAILED}:
        skipped[f"run_status_{run.status.value}"] += len(transitions)
        return [], skipped, len(transitions)

    samples: list[ReplaySample] = []
    transition_boundaries = [
        event.sequence for event in events if event.kind is EventKind.TRANSITION
    ]
    for sequence, transition in transitions:
        if transition.state_changed is not True or transition.after_state_digest is None:
            skipped["transition_not_accepted"] += 1
            continue
        before_digest = transition.before_state_digest
        after_digest = transition.after_state_digest
        action_id = transition.action_id
        previous_boundary = max(
            (boundary for boundary in transition_boundaries if boundary < sequence),
            default=-1,
        )
        next_boundary = next(
            (boundary for boundary in transition_boundaries if boundary > sequence),
            None,
        )
        execution_pair = _execution_before(
            executions,
            sequence,
            previous_boundary,
            action_id,
        )
        if execution_pair is None:
            skipped["incomplete_action_evidence"] += 1
            continue
        execution_sequence, execution = execution_pair
        decision_pair = _decision_before(
            decisions,
            execution_sequence,
            previous_boundary,
            before_digest,
            action_id,
        )
        if decision_pair is None:
            skipped["incomplete_action_evidence"] += 1
            continue
        decision_sequence, decision = decision_pair
        legal_pair = _legal_before(
            legal_sets,
            decision_sequence,
            previous_boundary,
            before_digest,
        )
        if legal_pair is None:
            skipped["incomplete_action_evidence"] += 1
            continue
        legal_sequence, legal_actions = legal_pair
        before_state = transition.before_state or _state_before(
            states,
            legal_sequence,
            previous_boundary,
            before_digest,
        )
        after_state = transition.after_state or _state_after(
            states,
            sequence,
            next_boundary,
            after_digest,
        )
        if before_state is None:
            skipped["missing_before_state"] += 1
            continue
        if after_state is None:
            skipped["missing_after_state"] += 1
            continue
        if (
            game_state_digest(before_state) != transition.before_state_digest
            or game_state_digest(after_state) != transition.after_state_digest
        ):
            skipped["state_digest_mismatch"] += 1
            continue
        chosen = next(
            (
                action
                for action in legal_actions.actions
                if action.action_id == action_id
            ),
            None,
        )
        if chosen is None:
            skipped["action_outside_legal_set"] += 1
            continue
        try:
            samples.append(
                ReplaySample(
                    run_id=run.run_id,
                    transition_sequence=sequence,
                    client_sha256=run.client_sha256,
                    policy_id=run.policy_id,
                    model_id=run.model_id,
                    before_state=before_state,
                    legal_actions=legal_actions,
                    chosen_action=chosen,
                    decision=decision,
                    execution=execution,
                    after_state=after_state,
                    transition=transition,
                )
            )
        except ValidationError:
            skipped["inconsistent_action_evidence"] += 1
    return samples, skipped, len(transitions)


def collect_replay_samples(
    store: RunStore,
) -> tuple[tuple[ReplaySample, ...], ReplayExportSummary]:
    runs = store.all_runs()
    samples: list[ReplaySample] = []
    skipped: Counter[str] = Counter()
    transitions_seen = 0
    for run in runs:
        run_samples, run_skipped, run_transition_count = _samples_for_run(
            run,
            store.events(run.run_id),
        )
        samples.extend(run_samples)
        skipped.update(run_skipped)
        transitions_seen += run_transition_count
    summary = ReplayExportSummary(
        destination=Path("."),
        runs_scanned=len(runs),
        transitions_seen=transitions_seen,
        samples_exported=len(samples),
        skipped=dict(sorted(skipped.items())),
    )
    return tuple(samples), summary


def load_replay_jsonl(source: Path) -> tuple[ReplaySample, ...]:
    samples: list[ReplaySample] = []
    try:
        with source.open(encoding="utf-8") as input_file:
            for line_number, raw_line in enumerate(input_file, start=1):
                if not raw_line.strip():
                    continue
                try:
                    sample = ReplaySample.model_validate_json(raw_line)
                except ValidationError as error:
                    raise ReplayDatasetError(
                        f"replay line {line_number} violates the dataset contract"
                    ) from error
                if (
                    game_state_digest(sample.before_state)
                    != sample.transition.before_state_digest
                    or game_state_digest(sample.after_state)
                    != sample.transition.after_state_digest
                ):
                    raise ReplayDatasetError(
                        f"replay line {line_number} has mismatched state digests"
                    )
                samples.append(sample)
    except OSError as error:
        raise ReplayDatasetError(f"could not read replay dataset: {error}") from error
    if not samples:
        raise ReplayDatasetError("replay dataset has no samples")
    identities = {(sample.run_id, sample.transition_sequence) for sample in samples}
    if len(identities) != len(samples):
        raise ReplayDatasetError("replay dataset contains duplicate transition identities")
    return tuple(samples)


def export_replay_jsonl(store: RunStore, destination: Path) -> ReplayExportSummary:
    """Atomically export accepted transitions as an owner-only JSONL dataset."""

    samples, summary = collect_replay_samples(store)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(raw_path)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            for sample in samples:
                output.write(
                    json.dumps(
                        sample.model_dump(mode="json"),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                )
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
        os.chmod(destination, 0o600)
    except OSError as error:
        raise ReplayExportError(f"could not write replay dataset: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return summary.model_copy(update={"destination": destination})
