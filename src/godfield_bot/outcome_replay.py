import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from godfield_bot.domain.action import ActionTransition
from godfield_bot.domain.game import GameState
from godfield_bot.domain.outcome import MatchOutcome, SparseTerminalReward
from godfield_bot.domain.outcome_replay import (
    OutcomeReplayEpisode,
    OutcomeReplayExportSummary,
)
from godfield_bot.domain.run import EventKind, RunEvent, RunRecord, RunStatus
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.outcomes import classify_two_player_terminal
from godfield_bot.replay import collect_run_replay_samples
from godfield_bot.run_store import RunStore


class OutcomeReplayExportError(RuntimeError):
    """Raised when terminal-labeled replay cannot be exported safely."""


class OutcomeReplayDatasetError(RuntimeError):
    """Raised when terminal-labeled replay violates its typed contract."""


def _terminal_evidence(
    events: tuple[RunEvent, ...],
) -> tuple[MatchOutcome | None, SparseTerminalReward | None, bool]:
    outcomes: list[tuple[int, MatchOutcome]] = []
    rewards: list[tuple[int, SparseTerminalReward]] = []
    invalid = False
    for event in events:
        try:
            if event.kind is EventKind.MATCH_END:
                outcomes.append((event.sequence, MatchOutcome.model_validate(event.payload)))
            elif event.kind is EventKind.REWARD:
                rewards.append(
                    (event.sequence, SparseTerminalReward.model_validate(event.payload))
                )
        except ValidationError:
            invalid = True
    if invalid or len(outcomes) != 1 or len(rewards) != 1:
        return None, None, invalid
    outcome_sequence, outcome = outcomes[0]
    reward_sequence, reward = rewards[0]
    if reward_sequence != outcome_sequence + 1:
        return None, None, True
    if (
        reward.result is not outcome.result
        or reward.terminal_state_digest != outcome.terminal_state_digest
    ):
        return None, None, True
    return outcome, reward, False


def _terminal_state(
    events: tuple[RunEvent, ...],
    outcome: MatchOutcome,
) -> GameState | None:
    candidates: list[GameState] = []
    for event in events:
        try:
            if event.kind is EventKind.GAME_STATE:
                candidates.append(GameState.model_validate(event.payload))
            elif event.kind is EventKind.TRANSITION:
                transition = ActionTransition.model_validate(event.payload)
                if transition.after_state is not None:
                    candidates.append(transition.after_state)
        except ValidationError:
            continue
    for state in reversed(candidates):
        if game_state_digest(state) != outcome.terminal_state_digest:
            continue
        classified = classify_two_player_terminal(state)
        if classified is not None and classified.result is outcome.result:
            return state
    return None


def _outcome_matches_run(
    run: RunRecord,
    outcome: MatchOutcome,
    reward: SparseTerminalReward,
) -> bool:
    return run.outcome is not None and (
        run.outcome.get("reason") == "classified_terminal"
        and run.outcome.get("result") == outcome.result.value
        and run.outcome.get("reward") == reward.value
        and run.outcome.get("terminal_state_digest") == outcome.terminal_state_digest
    )


def collect_outcome_replay(
    store: RunStore,
) -> tuple[tuple[OutcomeReplayEpisode, ...], OutcomeReplayExportSummary]:
    runs = store.all_runs()
    episodes: list[OutcomeReplayEpisode] = []
    skipped: Counter[str] = Counter()
    completed_runs_seen = 0
    for run in runs:
        if run.status is not RunStatus.COMPLETED:
            skipped[f"run_status_{run.status.value}"] += 1
            continue
        completed_runs_seen += 1
        events = store.events(run.run_id)
        outcome, reward, invalid_terminal = _terminal_evidence(events)
        if outcome is None or reward is None:
            skipped[
                "invalid_terminal_evidence" if invalid_terminal else "missing_terminal_evidence"
            ] += 1
            continue
        if not _outcome_matches_run(run, outcome, reward):
            skipped["run_outcome_mismatch"] += 1
            continue
        terminal_state = _terminal_state(events, outcome)
        if terminal_state is None:
            skipped["missing_terminal_state"] += 1
            continue
        samples, sample_skips, transitions_seen = collect_run_replay_samples(run, events)
        if sample_skips or transitions_seen != len(samples):
            skipped["incomplete_transition_evidence"] += 1
            continue
        if not samples:
            skipped["no_trainable_steps"] += 1
            continue
        try:
            episodes.append(
                OutcomeReplayEpisode(
                    run_id=run.run_id,
                    client_sha256=run.client_sha256,
                    policy_id=run.policy_id,
                    model_id=run.model_id,
                    steps=samples,
                    terminal_state=terminal_state,
                    outcome=outcome,
                    reward=reward,
                )
            )
        except ValidationError:
            skipped["inconsistent_episode_evidence"] += 1
    summary = OutcomeReplayExportSummary(
        destination=Path("."),
        runs_scanned=len(runs),
        completed_runs_seen=completed_runs_seen,
        episodes_exported=len(episodes),
        steps_exported=sum(len(episode.steps) for episode in episodes),
        skipped=dict(sorted(skipped.items())),
    )
    return tuple(episodes), summary


def _validate_episode(episode: OutcomeReplayEpisode, line_number: int) -> None:
    if game_state_digest(episode.terminal_state) != episode.outcome.terminal_state_digest:
        raise OutcomeReplayDatasetError(
            f"outcome replay line {line_number} has a mismatched terminal state digest"
        )
    classified = classify_two_player_terminal(episode.terminal_state)
    if classified is None or classified.result is not episode.outcome.result:
        raise OutcomeReplayDatasetError(
            f"outcome replay line {line_number} has an unclassifiable terminal state"
        )


def load_outcome_replay_jsonl(source: Path) -> tuple[OutcomeReplayEpisode, ...]:
    episodes: list[OutcomeReplayEpisode] = []
    try:
        with source.open(encoding="utf-8") as input_file:
            for line_number, raw_line in enumerate(input_file, start=1):
                if not raw_line.strip():
                    continue
                try:
                    episode = OutcomeReplayEpisode.model_validate_json(raw_line)
                except ValidationError as error:
                    raise OutcomeReplayDatasetError(
                        f"outcome replay line {line_number} violates the dataset contract"
                    ) from error
                _validate_episode(episode, line_number)
                episodes.append(episode)
    except OSError as error:
        raise OutcomeReplayDatasetError(f"could not read outcome replay: {error}") from error
    if not episodes:
        raise OutcomeReplayDatasetError("outcome replay has no episodes")
    run_ids = {episode.run_id for episode in episodes}
    if len(run_ids) != len(episodes):
        raise OutcomeReplayDatasetError("outcome replay contains duplicate run IDs")
    return tuple(episodes)


def export_outcome_replay_jsonl(
    store: RunStore,
    destination: Path,
) -> OutcomeReplayExportSummary:
    """Atomically export complete terminal-labeled episodes as owner-only JSONL."""

    episodes, summary = collect_outcome_replay(store)
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
            for episode in episodes:
                output.write(
                    json.dumps(
                        episode.model_dump(mode="json"),
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
        raise OutcomeReplayExportError(f"could not write outcome replay: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return summary.model_copy(update={"destination": destination})
