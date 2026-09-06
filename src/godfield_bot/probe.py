from pydantic import JsonValue

from godfield_bot.domain.observation import ScreenObservation
from godfield_bot.domain.run import EventKind, RunMode, RunRecord, RunSpec, RunStatus
from godfield_bot.game_state import parse_game_state
from godfield_bot.legal_actions import observation_only_actions
from godfield_bot.policy import SafeObserverPolicy
from godfield_bot.run_store import RunStore


def record_observation_probe(
    store: RunStore,
    observation: ScreenObservation,
    *,
    identity: str,
    client_sha256: str,
) -> RunRecord:
    """Record a complete non-executing policy pass over one saved observation."""

    policy = SafeObserverPolicy()
    run = store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity=identity,
            client_sha256=client_sha256,
            policy_id=policy.policy_id,
            config={"source": "saved_observation", "external_actions": 0},
        )
    )
    try:
        state = parse_game_state(observation, identity=identity)
        legal_actions = observation_only_actions(state)
        decision = policy.decide(state, legal_actions)
        store.append_event(run.run_id, EventKind.OBSERVATION, observation)
        store.append_event(run.run_id, EventKind.GAME_STATE, state)
        store.append_event(run.run_id, EventKind.LEGAL_ACTIONS, legal_actions)
        store.append_event(run.run_id, EventKind.DECISION, decision)
    except Exception as error:
        outcome: dict[str, JsonValue] = {
            "reason": "probe_failed",
            "error_type": type(error).__name__,
        }
        store.finish_run(run.run_id, RunStatus.FAILED, outcome=outcome)
        raise
    return store.finish_run(
        run.run_id,
        RunStatus.ABORTED,
        outcome={"reason": "observation_only_policy", "external_actions": 0},
    )
