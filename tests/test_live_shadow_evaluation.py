import json
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from godfield_bot.api_game import (
    ApiActionKind,
    ApiAttackState,
    ApiGameState,
    ApiItemState,
    ApiLegalAction,
    ApiLegalActionSet,
    ApiPhase,
    ApiPlayerState,
    ApiPolicyDecision,
    api_game_state_digest,
)
from godfield_bot.api_neural import API_RESOURCE_SHADOW_POLICY_ID, RESOURCE_RULESET_ID
from godfield_bot.api_runtime import ApiPolicyName, ApiPrivateMatchOutcome
from godfield_bot.domain.outcome import MatchResult, SparseTerminalReward
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.features import RESOURCE_FEATURE_SCHEMA_VERSION, ArtifactVocabulary
from godfield_bot.live_shadow_evaluation import (
    LiveShadowEvaluationConfig,
    LiveShadowEvaluationError,
    LiveShadowEvaluationReport,
    evaluate_live_shadow_candidate,
)
from godfield_bot.model_registry import ModelManifest, initialize_model, load_model, save_candidate
from godfield_bot.run_store import RunStore
from godfield_bot.simulation import SimulationMetadata
from godfield_bot.simulation_evaluation import (
    SimulationEvaluationConfig,
    SimulationEvaluationReport,
    SimulationMatchupEvaluation,
)
from godfield_bot.simulation_policy import RESOURCE_HEURISTIC_POLICY_ID

SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")


def simulation_metadata(manifest: ModelManifest) -> SimulationMetadata:
    return SimulationMetadata(
        kernel_schema_version=1,
        observation_schema_version=5,
        ruleset_id=RESOURCE_RULESET_ID,
        client_sha256=manifest.client_sha256,
        vocabulary_sha256=manifest.vocabulary_sha256,
        rule_catalog_sha256="e" * 64,
        rule_catalog_size=10,
        action_count=21,
        hand_slots=9,
        global_feature_count=13,
        action_semantics="sequential-combo-selection",
        sampling_distribution=(
            "elemental-resource-3-1-2-2-1-initial-uniform-redraw-with-base-liveness"
        ),
    )


def candidate(tmp_path: Path) -> tuple[Path, ModelManifest]:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    root = tmp_path / "models"
    parent = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=RESOURCE_FEATURE_SCHEMA_VERSION,
    )
    _, model = load_model(root / parent.model_id)
    manifest = save_candidate(
        root,
        model,
        vocabulary,
        parent=parent,
        seed=67,
        training_algorithm="resource-fixture",
        training_dataset_sha256="a" * 64,
        training_run_ids=(),
        metrics={},
        training_context={
            "simulation": simulation_metadata(parent).model_dump(mode="json"),
            "config": {"ruleset": "resource-hand"},
        },
    )
    directory = root / manifest.model_id
    return directory, manifest


def matchup(kind: str, opponent_id: str) -> SimulationMatchupEvaluation:
    return SimulationMatchupEvaluation.model_validate(
        {
            "opponent_kind": kind,
            "opponent_id": opponent_id,
            "gate_kind": ("paired-superiority" if kind == "model" else "paired-noninferiority"),
            "games_per_seat": 8,
            "completed_games": 16,
            "incomplete_games": 0,
            "candidate_wins": 9,
            "candidate_losses": 7,
            "candidate_draws": 0,
            "candidate_score": 0.5625,
            "wilson_lower_bound": 0.5,
            "paired_score": 0.5625,
            "paired_score_standard_error": 0.01,
            "paired_score_lower_bound": 0.54,
            "required_paired_score": 0.5,
            "mean_decisions_per_completed_game": 20.0,
            "candidate_won_both_pairs": 2,
            "candidate_split_pairs": 5,
            "candidate_lost_both_pairs": 1,
            "incomplete_pairs": 0,
            "kernel_transitions": 320,
            "passed": True,
        }
    )


def native_evaluation(tmp_path: Path, manifest: ModelManifest) -> Path:
    assert manifest.parent_model_id is not None
    parent, _model = load_model(tmp_path / "models" / manifest.parent_model_id)
    report = SimulationEvaluationReport(
        evaluation_id="native-resource-gate",
        created_at=datetime.now(UTC),
        candidate_model_id=manifest.model_id,
        candidate_weights_sha256=manifest.weights_sha256,
        parent_model_id=parent.model_id,
        parent_weights_sha256=parent.weights_sha256,
        input_sha256="d" * 64,
        simulation=simulation_metadata(manifest),
        config=SimulationEvaluationConfig(ruleset="resource-hand", games_per_seat=8),
        matchups=(
            matchup("model", parent.model_id),
            matchup("heuristic", RESOURCE_HEURISTIC_POLICY_ID),
        ),
        passed=True,
        gate_reasons=(),
    )
    path = tmp_path / "native.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def players(*, self_hp: int = 40, opponent_hp: int = 40) -> tuple[ApiPlayerState, ...]:
    return (
        ApiPlayerState(
            player_id=1,
            name="ロキ-67",
            hp=self_hp,
            mp=20,
            cp=20,
            is_self=True,
            is_bot=False,
            hand_count=4,
        ),
        ApiPlayerState(
            player_id=2,
            name="Opponent",
            hp=opponent_hp,
            mp=20,
            cp=20,
            is_self=False,
            is_bot=False,
            hand_count=0,
        ),
    )


def resource_items() -> tuple[ApiItemState, ...]:
    return (
        ApiItemState(
            instance_id=11,
            model_id=101,
            name="HP",
            asset="romance-water",
            category="sundries",
            attack=0,
            defense=0,
            cost=0,
            ability="boostHP",
            ability_value=15,
            used=False,
        ),
        ApiItemState(
            instance_id=12,
            model_id=102,
            name="MP",
            asset="smile-flower",
            category="sundries",
            attack=0,
            defense=0,
            cost=0,
            ability="boostMP",
            ability_value=5,
            used=False,
        ),
        ApiItemState(
            instance_id=13,
            model_id=103,
            name="Flame",
            asset="flame",
            category="miracles",
            element="fire",
            attack=10,
            defense=0,
            cost=5,
            used=False,
        ),
        ApiItemState(
            instance_id=14,
            model_id=104,
            name="Spring",
            asset="spring",
            category="miracles",
            attack=0,
            defense=0,
            ability="boostHP",
            ability_value=10,
            cost=7,
            used=False,
        ),
    )


def decision(
    *,
    state_digest: str,
    policy_id: str,
    action_id: str | None,
    model_id: str | None = None,
    weights_sha256: str | None = None,
    executable: bool,
    neural_trace: bool = False,
) -> ApiPolicyDecision:
    return ApiPolicyDecision(
        decided_at=datetime.now(UTC),
        policy_id=policy_id,
        state_digest=state_digest,
        chosen_action_id=action_id,
        scores={action_id: 1.0} if action_id is not None else {},
        rationale="fixture",
        executable=executable,
        model_id=model_id,
        model_weights_sha256=weights_sha256,
        selection_action_indices=((1,) if neural_trace else ()),
        selection_probabilities=((1.0,) if neural_trace else ()),
        value_estimates=((0.0,) if neural_trace else ()),
    )


def append_state_pair(
    store: RunStore,
    run_id: str,
    state: ApiGameState,
    legal: ApiLegalActionSet,
    *,
    model_id: str,
    weights_sha256: str,
    action_id: str | None,
) -> None:
    digest = api_game_state_digest(state)
    store.append_events(
        run_id,
        (
            (EventKind.GAME_STATE, state),
            (EventKind.LEGAL_ACTIONS, legal),
            (
                EventKind.DECISION,
                decision(
                    state_digest=digest,
                    policy_id=API_RESOURCE_SHADOW_POLICY_ID,
                    action_id=action_id,
                    model_id=model_id,
                    weights_sha256=weights_sha256,
                    executable=False,
                    neural_trace=action_id is not None,
                ),
            ),
            (
                EventKind.DECISION,
                decision(
                    state_digest=digest,
                    policy_id=ApiPolicyName.TACTICAL_HEURISTIC.value,
                    action_id=action_id,
                    executable=action_id is not None,
                ),
            ),
        ),
    )


def evidence_database(tmp_path: Path, manifest: object) -> Path:
    database = tmp_path / "runs.sqlite"
    store = RunStore(database)
    run = store.start_run(
        RunSpec(
            mode=RunMode.PRIVATE,
            identity="ロキ-67",
            client_sha256="f" * 64,
            policy_id=ApiPolicyName.NEURAL_SHADOW.value,
            model_id=manifest.model_id,
            config={
                "behavior_policy": ApiPolicyName.TACTICAL_HEURISTIC.value,
                "shadow_policy_id": API_RESOURCE_SHADOW_POLICY_ID,
                "shadow_feature_schema_version": RESOURCE_FEATURE_SCHEMA_VERSION,
                "shadow_model_id": manifest.model_id,
                "shadow_model_weights_sha256": manifest.weights_sha256,
            },
        )
    )
    turn = ApiGameState(
        observed_at=datetime.now(UTC),
        update_count=1,
        field_number=1,
        self_player_id=1,
        awaiting_player_id=1,
        phase=ApiPhase.TURN,
        players=players(),
        hand=resource_items(),
    )
    resource_actions = (
        ApiLegalAction(
            action_id="utility:boostHP:11:101",
            kind=ApiActionKind.USE_ITEM,
            label="HP",
            item_instance_ids=(11,),
            item_model_ids=(101,),
        ),
        ApiLegalAction(
            action_id="utility:boostMP:12:102",
            kind=ApiActionKind.USE_ITEM,
            label="MP",
            item_instance_ids=(12,),
            item_model_ids=(102,),
        ),
        ApiLegalAction(
            action_id="miracle-attack:13:103:2",
            kind=ApiActionKind.USE_ITEM,
            label="Flame",
            item_instance_ids=(13,),
            item_model_ids=(103,),
            target_player_id=2,
        ),
        ApiLegalAction(
            action_id="utility:boostHP:14:104",
            kind=ApiActionKind.USE_ITEM,
            label="Spring",
            item_instance_ids=(14,),
            item_model_ids=(104,),
        ),
    )
    append_state_pair(
        store,
        run.run_id,
        turn,
        ApiLegalActionSet(
            state_digest=api_game_state_digest(turn),
            actions=resource_actions,
            coverage_complete=False,
            blocked_reason="fixture",
        ),
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        action_id=resource_actions[0].action_id,
    )
    defense = turn.model_copy(
        update={
            "observed_at": datetime.now(UTC),
            "update_count": 2,
            "phase": ApiPhase.DEFENSE,
            "pending_attack": ApiAttackState(
                player_id=2,
                target_player_id=1,
                item_model_ids=(999,),
                attack=10,
            ),
        }
    )
    pass_action = ApiLegalAction(
        action_id="pass",
        kind=ApiActionKind.PASS,
        label="Forgive",
    )
    append_state_pair(
        store,
        run.run_id,
        defense,
        ApiLegalActionSet(
            state_digest=api_game_state_digest(defense),
            actions=(pass_action,),
            coverage_complete=False,
            blocked_reason="fixture",
        ),
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        action_id=pass_action.action_id,
    )
    terminal = turn.model_copy(
        update={
            "observed_at": datetime.now(UTC),
            "update_count": 3,
            "phase": ApiPhase.TERMINAL,
            "awaiting_player_id": None,
            "players": players(opponent_hp=0),
        }
    )
    append_state_pair(
        store,
        run.run_id,
        terminal,
        ApiLegalActionSet(
            state_digest=api_game_state_digest(terminal),
            actions=(),
            coverage_complete=False,
            blocked_reason="terminal",
        ),
        model_id=manifest.model_id,
        weights_sha256=manifest.weights_sha256,
        action_id=None,
    )
    outcome = ApiPrivateMatchOutcome(
        observed_at=terminal.observed_at,
        terminal_state_digest=api_game_state_digest(terminal),
        self_player_name="ロキ-67",
        opponent_player_names=("Opponent",),
        result=MatchResult.WIN,
    )
    reward = SparseTerminalReward(
        observed_at=terminal.observed_at,
        terminal_state_digest=outcome.terminal_state_digest,
        result=MatchResult.WIN,
        value=1.0,
    )
    store.append_events(
        run.run_id,
        ((EventKind.MATCH_END, outcome), (EventKind.REWARD, reward)),
    )
    store.finish_run(
        run.run_id,
        RunStatus.COMPLETED,
        outcome={
            "reason": "classified_terminal",
            "result": "win",
            "reward": 1.0,
            "terminal_state_digest": outcome.terminal_state_digest,
        },
    )
    return database


def permissive_config() -> LiveShadowEvaluationConfig:
    return LiveShadowEvaluationConfig(
        minimum_completed_games=1,
        minimum_turn_opportunities=1,
        minimum_defense_opportunities=1,
        minimum_resource_opportunities=1,
        minimum_each_resource_kind=1,
        minimum_completion_lower_bound=0,
        minimum_coverage_lower_bound=0,
        minimum_agreement_lower_bound=0,
        minimum_resource_coverage_lower_bound=0,
        minimum_resource_agreement_lower_bound=0,
    )


def test_live_shadow_gate_persists_reproducible_non_promoting_report(tmp_path: Path) -> None:
    model_directory, manifest = candidate(tmp_path)
    native_path = native_evaluation(tmp_path, manifest)
    database = evidence_database(tmp_path, manifest)

    stored = evaluate_live_shadow_candidate(
        candidate_model_directory=model_directory,
        bible_snapshot_path=SNAPSHOT,
        native_evaluation_path=native_path,
        database_path=database,
        evaluation_directory=tmp_path / "evaluations",
        config=permissive_config(),
    )

    report_path = Path(stored.report_path)
    reloaded = LiveShadowEvaluationReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    assert reloaded == stored.report
    assert stored.report.schema_version == 5
    assert stored.report.gate_id == "live-resource-shadow-readiness-v5"
    assert stored.report.behavior_policy_id == "api-combo-utility-heuristic-v5"
    assert stored.report.passed is True
    assert stored.report.ready_for_controlled_trial is True
    assert stored.report.promotion_eligible is False
    assert stored.report.metrics.completed_games == 1
    assert stored.report.metrics.turn_opportunities == 1
    assert stored.report.metrics.defense_opportunities == 1
    assert stored.report.metrics.resource_kind_opportunities == {
        "hp-sundry": 1,
        "mp-sundry": 1,
        "attack-miracle": 1,
        "hp-miracle": 1,
    }
    assert stored.report.metrics.behavior_agreement == 1.0
    assert stored.report.metrics.evidence_error_count == 0
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


def test_live_shadow_gate_reports_missing_schema_v5_evidence(tmp_path: Path) -> None:
    model_directory, manifest = candidate(tmp_path)
    native_path = native_evaluation(tmp_path, manifest)
    database = tmp_path / "empty.sqlite"
    RunStore(database).initialize()

    stored = evaluate_live_shadow_candidate(
        candidate_model_directory=model_directory,
        bible_snapshot_path=SNAPSHOT,
        native_evaluation_path=native_path,
        database_path=database,
        evaluation_directory=tmp_path / "evaluations",
        config=LiveShadowEvaluationConfig(),
    )

    assert stored.report.passed is False
    assert stored.report.ready_for_controlled_trial is False
    assert stored.report.metrics.matching_runs == 0
    assert stored.report.metrics.completed_games == 0
    assert "no schema-v5 resource shadow runs" in stored.report.gate_reasons[0]


def test_live_shadow_gate_fails_closed_on_tampered_decision_identity(tmp_path: Path) -> None:
    model_directory, manifest = candidate(tmp_path)
    native_path = native_evaluation(tmp_path, manifest)
    database = evidence_database(tmp_path, manifest)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT event_id, payload_json FROM events
            WHERE kind = 'decision'
              AND json_extract(payload_json, '$.policy_id') = ?
            ORDER BY event_id LIMIT 1
            """,
            (API_RESOURCE_SHADOW_POLICY_ID,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[1])
        payload["model_weights_sha256"] = "0" * 64
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            (json.dumps(payload), row[0]),
        )
        connection.commit()

    stored = evaluate_live_shadow_candidate(
        candidate_model_directory=model_directory,
        bible_snapshot_path=SNAPSHOT,
        native_evaluation_path=native_path,
        database_path=database,
        evaluation_directory=tmp_path / "evaluations",
        config=permissive_config(),
    )

    assert stored.report.passed is False
    assert stored.report.metrics.evidence_error_count == 1
    assert "wrong model identity" in stored.report.metrics.evidence_errors[0]
    assert "1 shadow evidence integrity errors found" in stored.report.gate_reasons


def test_live_shadow_gate_rejects_tampered_native_opponent(tmp_path: Path) -> None:
    model_directory, manifest = candidate(tmp_path)
    native_path = native_evaluation(tmp_path, manifest)
    report = json.loads(native_path.read_text(encoding="utf-8"))
    report["matchups"][1]["opponent_id"] = "different-heuristic"
    native_path.write_text(json.dumps(report), encoding="utf-8")
    database = tmp_path / "empty.sqlite"
    RunStore(database).initialize()

    with pytest.raises(LiveShadowEvaluationError, match="different gate opponents"):
        evaluate_live_shadow_candidate(
            candidate_model_directory=model_directory,
            bible_snapshot_path=SNAPSHOT,
            native_evaluation_path=native_path,
            database_path=database,
            evaluation_directory=tmp_path / "evaluations",
            config=LiveShadowEvaluationConfig(),
        )
