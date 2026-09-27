import stat
from datetime import UTC, datetime
from pathlib import Path

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds, ScreenKind, ScreenObservation
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.run import EventKind, RunMode, RunSpec, RunStatus
from godfield_bot.features import (
    DREAM_FEATURE_SCHEMA_VERSION,
    DREAM_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
)
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.model_registry import initialize_model, load_model, save_candidate
from godfield_bot.outcomes import classify_two_player_terminal, sparse_terminal_reward
from godfield_bot.run_store import RunStore
from godfield_bot.simulation import SimulationMetadata
from godfield_bot.simulation_evaluation import (
    SimulationEvaluationConfig,
    SimulationEvaluationReport,
    SimulationMatchupEvaluation,
)
from godfield_bot.simulation_policy import DREAM_RESOURCE_HEURISTIC_POLICY_ID
from godfield_bot.training_shadow import DREAM_RULESET_ID, OfficialTrainingShadowPolicy
from godfield_bot.training_shadow_evaluation import (
    TrainingShadowReadinessConfig,
    evaluate_training_shadow_readiness,
)

SNAPSHOT = Path("data/snapshots/2026-09-20/bible.json")
BIBLE = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))


def _metadata(client_sha256: str, vocabulary_sha256: str) -> SimulationMetadata:
    return SimulationMetadata(
        kernel_schema_version=1,
        observation_schema_version=DREAM_FEATURE_SCHEMA_VERSION,
        ruleset_id=DREAM_RULESET_ID,
        client_sha256=client_sha256,
        vocabulary_sha256=vocabulary_sha256,
        rule_catalog_sha256="e" * 64,
        rule_catalog_size=196,
        action_count=21,
        hand_slots=9,
        global_feature_count=DREAM_GLOBAL_FEATURE_COUNT,
        action_semantics="sequential-combo-selection",
        sampling_distribution=(
            "elemental-dream-resource-2-1-2-1-1-1-1-initial-uniform-redraw-with-base-liveness"
        ),
    )


def _candidate(tmp_path: Path) -> tuple[Path, str]:
    vocabulary = ArtifactVocabulary.from_snapshot(BIBLE)
    root = tmp_path / "models"
    parent = initialize_model(
        root,
        vocabulary,
        client_sha256=BIBLE.client.sha256,
        feature_schema_version=DREAM_FEATURE_SCHEMA_VERSION,
        global_feature_count=DREAM_GLOBAL_FEATURE_COUNT,
    )
    _manifest, model = load_model(root / parent.model_id)
    candidate = save_candidate(
        root,
        model,
        vocabulary,
        parent=parent,
        seed=67,
        training_algorithm="dream-readiness-fixture",
        training_dataset_sha256="a" * 64,
        training_run_ids=(),
        metrics={},
        training_context={
            "simulation": _metadata(
                parent.client_sha256,
                parent.vocabulary_sha256,
            ).model_dump(mode="json"),
            "config": {"ruleset": "dream-resource-hand"},
        },
    )
    return root / candidate.model_id, candidate.model_id


def _matchup(kind: str, opponent_id: str) -> SimulationMatchupEvaluation:
    return SimulationMatchupEvaluation(
        opponent_kind=kind,  # type: ignore[arg-type]
        opponent_id=opponent_id,
        gate_kind=("paired-superiority" if kind == "model" else "paired-noninferiority"),
        games_per_seat=1,
        completed_games=2,
        incomplete_games=0,
        candidate_wins=1,
        candidate_losses=1,
        candidate_draws=0,
        candidate_score=0.5,
        wilson_lower_bound=0.1,
        paired_score=0.5,
        paired_score_standard_error=0.0,
        paired_score_lower_bound=0.5,
        required_paired_score=0.475,
        mean_decisions_per_completed_game=1.0,
        candidate_won_both_pairs=0,
        candidate_split_pairs=1,
        candidate_lost_both_pairs=0,
        incomplete_pairs=0,
        kernel_transitions=2,
        passed=True,
    )


def _native_evaluation(candidate_directory: Path, destination: Path) -> None:
    candidate, _model = load_model(candidate_directory)
    assert candidate.parent_model_id is not None
    parent, _parent_model = load_model(candidate_directory.parent / candidate.parent_model_id)
    report = SimulationEvaluationReport(
        evaluation_id="dream-native-fixture",
        created_at=datetime.now(UTC),
        candidate_model_id=candidate.model_id,
        candidate_weights_sha256=candidate.weights_sha256,
        parent_model_id=parent.model_id,
        parent_weights_sha256=parent.weights_sha256,
        input_sha256="d" * 64,
        simulation=_metadata(candidate.client_sha256, candidate.vocabulary_sha256),
        config=SimulationEvaluationConfig(
            ruleset="dream-resource-hand",
            games_per_seat=1,
            seed=67,
        ),
        matchups=(
            _matchup("model", parent.model_id),
            _matchup("heuristic", DREAM_RESOURCE_HEURISTIC_POLICY_ID),
        ),
        passed=True,
        gate_reasons=(),
    )
    destination.mkdir(parents=True)
    (destination / "native.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def _observation(observed_at: datetime) -> ScreenObservation:
    return ScreenObservation(
        observed_at=observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training",),
        text_elements=(),
        controls=(),
        images=(),
    )


def _state(*, terminal: bool = False) -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=4,
        self_player_index=0,
        players=(
            PlayerState(
                name="ロキ-67",
                hp=35,
                mp=10,
                money=20,
                is_self=True,
                dreaming=True,
            ),
            PlayerState(
                name="CPU",
                hp=0 if terminal else 28,
                mp=7,
                money=20,
                is_self=False,
            ),
        ),
        hand=(
            HandArtifact(
                slot=0,
                category="weapons",
                slug="bronze-club",
                asset_path="/images/items/weapons/bronze-club.webp",
                bounds=Bounds(x=110, y=493, width=80, height=80),
            ),
        ),
        scene_layers=("/images/screens/room.webp",),
    )


def _action_inputs(state: GameState) -> tuple[LegalActionSet, PolicyDecision]:
    digest = game_state_digest(state)
    action = LegalAction(
        action_id="artifact:0:weapons/bronze-club",
        kind=ActionKind.SELECT_ARTIFACT,
        label="Select Bronze Club",
        artifact_slot=0,
        artifact_asset_path=state.hand[0].asset_path,
    )
    legal = LegalActionSet(
        state_digest=digest,
        actions=(
            LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),
            action,
        ),
        coverage_complete=False,
        blocked_reason="fixture",
    )
    behavior = PolicyDecision(
        decided_at=state.observed_at,
        policy_id="heuristic-v0",
        state_digest=digest,
        chosen_action_id=action.action_id,
        scores={action.action_id: 1.0},
        rationale="fixture",
        executable=True,
    )
    return legal, behavior


def _terminal_inputs(state: GameState) -> tuple[LegalActionSet, PolicyDecision]:
    digest = game_state_digest(state)
    legal = LegalActionSet(
        state_digest=digest,
        actions=(LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),),
        coverage_complete=True,
    )
    behavior = PolicyDecision(
        decided_at=state.observed_at,
        policy_id="heuristic-v0",
        state_digest=digest,
        chosen_action_id="wait",
        scores={"wait": 1.0},
        rationale="terminal fixture",
        executable=False,
    )
    return legal, behavior


def _record_run(
    database: Path,
    candidate_directory: Path,
    *,
    corrupt_identity: bool = False,
) -> None:
    candidate, _model = load_model(candidate_directory)
    policy = OfficialTrainingShadowPolicy(candidate_directory, BIBLE)
    store = RunStore(database)
    run = store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256=candidate.client_sha256,
            policy_id="heuristic-v0",
            config={
                "shadow_policy_id": policy.policy_id,
                "shadow_model_id": candidate.model_id,
                "shadow_weights_sha256": candidate.weights_sha256,
                "shadow_feature_schema_version": DREAM_FEATURE_SCHEMA_VERSION,
            },
        )
    )
    state = _state()
    legal, behavior = _action_inputs(state)
    evidence = policy.evaluate(state, legal, behavior)
    if corrupt_identity:
        evidence = evidence.model_copy(update={"model_weights_sha256": "f" * 64})
    store.append_events(
        run.run_id,
        (
            (EventKind.OBSERVATION, _observation(state.observed_at)),
            (EventKind.GAME_STATE, state),
            (EventKind.LEGAL_ACTIONS, legal),
            (EventKind.DECISION, behavior),
            (EventKind.EVIDENCE, evidence),
        ),
    )

    hidden = state.model_copy(
        update={
            "observed_at": datetime.now(UTC),
            "players": (
                state.players[0],
                state.players[1].model_copy(update={"stats_visible": False}),
            ),
        }
    )
    hidden_legal, hidden_behavior = _action_inputs(hidden)
    hidden_evidence = policy.evaluate(hidden, hidden_legal, hidden_behavior)
    store.append_events(
        run.run_id,
        (
            (EventKind.OBSERVATION, _observation(hidden.observed_at)),
            (EventKind.GAME_STATE, hidden),
            (EventKind.LEGAL_ACTIONS, hidden_legal),
            (EventKind.DECISION, hidden_behavior),
            (EventKind.EVIDENCE, hidden_evidence),
        ),
    )

    terminal = _state(terminal=True)
    terminal_legal, terminal_behavior = _terminal_inputs(terminal)
    terminal_evidence = policy.evaluate(terminal, terminal_legal, terminal_behavior)
    store.append_events(
        run.run_id,
        (
            (EventKind.OBSERVATION, _observation(terminal.observed_at)),
            (EventKind.GAME_STATE, terminal),
            (EventKind.LEGAL_ACTIONS, terminal_legal),
            (EventKind.DECISION, terminal_behavior),
            (EventKind.EVIDENCE, terminal_evidence),
        ),
    )
    outcome = classify_two_player_terminal(terminal)
    assert outcome is not None
    reward = sparse_terminal_reward(outcome)
    store.append_events(
        run.run_id,
        (
            (EventKind.MATCH_END, outcome),
            (EventKind.REWARD, reward),
        ),
    )
    store.finish_run(
        run.run_id,
        RunStatus.COMPLETED,
        outcome={
            "reason": "classified_terminal",
            "result": outcome.result.value,
            "reward": reward.value,
            "terminal_state_digest": outcome.terminal_state_digest,
            "in_match_actions": 1,
        },
    )


def _config() -> TrainingShadowReadinessConfig:
    return TrainingShadowReadinessConfig(
        minimum_native_evaluations=1,
        minimum_completed_games=1,
        minimum_completion_lower_bound=0,
        minimum_exact_view_opportunities=1,
        minimum_exact_view_coverage_lower_bound=0,
        maximum_encoding_gaps=0,
        minimum_illness_opportunities=0,
        minimum_flash_opportunities=0,
        minimum_dark_cloud_opportunities=0,
        minimum_dream_opportunities=1,
        minimum_visibility_abstentions=0,
        minimum_each_action_family=0,
    )


def test_training_shadow_readiness_writes_immutable_adapter_report(tmp_path: Path) -> None:
    candidate_directory, _model_id = _candidate(tmp_path)
    native_directory = tmp_path / "native"
    _native_evaluation(candidate_directory, native_directory)
    database = tmp_path / "runs.sqlite"
    _record_run(database, candidate_directory)

    result = evaluate_training_shadow_readiness(
        candidate_model_directory=candidate_directory,
        bible_snapshot_path=SNAPSHOT,
        native_evaluation_directory=native_directory,
        database_path=database,
        evaluation_directory=tmp_path / "reports",
        config=_config(),
    )

    assert result.report.passed is True
    assert result.report.ready_for_guarded_intervention is True
    assert result.report.metrics.completed_games == 1
    assert result.report.metrics.exact_view_opportunities == 1
    assert result.report.metrics.exact_view_proposals == 1
    assert result.report.metrics.visibility_abstentions == 1
    assert result.report.metrics.status_opportunities["dream"] == 1
    assert result.report.promotion_eligible is False
    assert stat.S_IMODE(Path(result.report_path).stat().st_mode) == 0o600


def test_training_shadow_readiness_rejects_wrong_evidence_identity(tmp_path: Path) -> None:
    candidate_directory, _model_id = _candidate(tmp_path)
    native_directory = tmp_path / "native"
    _native_evaluation(candidate_directory, native_directory)
    database = tmp_path / "runs.sqlite"
    _record_run(database, candidate_directory, corrupt_identity=True)

    result = evaluate_training_shadow_readiness(
        candidate_model_directory=candidate_directory,
        bible_snapshot_path=SNAPSHOT,
        native_evaluation_directory=native_directory,
        database_path=database,
        evaluation_directory=tmp_path / "reports",
        config=_config(),
    )

    assert result.report.passed is False
    assert result.report.ready_for_guarded_intervention is False
    assert result.report.metrics.evidence_error_count == 1
    assert "shadow evidence has the wrong model identity" in (
        result.report.metrics.evidence_errors[0]
    )
