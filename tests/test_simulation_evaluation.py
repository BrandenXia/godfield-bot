import json
import stat
from pathlib import Path

import numpy as np
import pytest

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
    LEGACY_FEATURE_SCHEMA_VERSION,
    LEGACY_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
)
from godfield_bot.model_registry import initialize_model, load_model, save_candidate
from godfield_bot.simulation_evaluation import (
    SimulationEvaluationConfig,
    SimulationEvaluationReport,
    evaluate_simulation_candidate,
    paired_score_statistics,
    wilson_lower_bound,
)
from godfield_bot.simulation_policy import HEURISTIC_POLICY_ID

pytest.importorskip("godfield_sim")

SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")


def unchanged_candidate(tmp_path: Path) -> tuple[Path, str]:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    model_root = tmp_path / "models"
    parent = initialize_model(
        model_root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=LEGACY_FEATURE_SCHEMA_VERSION,
        global_feature_count=LEGACY_GLOBAL_FEATURE_COUNT,
    )
    _, model = load_model(model_root / parent.model_id)
    candidate = save_candidate(
        model_root,
        model,
        vocabulary,
        parent=parent,
        seed=67,
        training_algorithm="evaluation-fixture",
        training_dataset_sha256="a" * 64,
        training_run_ids=(),
        metrics={},
    )
    return model_root / candidate.model_id, parent.model_id


def test_wilson_lower_bound_is_conservative() -> None:
    assert wilson_lower_bound(0, 0, 1.96) == 0.0
    assert wilson_lower_bound(50, 100, 1.96) == pytest.approx(0.4038, abs=1e-4)
    assert wilson_lower_bound(100, 100, 1.96) < 1.0


def test_evaluation_config_accepts_expanded_resource_ruleset() -> None:
    assert (
        SimulationEvaluationConfig(ruleset="expanded-resource-hand").ruleset
        == "expanded-resource-hand"
    )
    assert (
        SimulationEvaluationConfig(ruleset="reflection-resource-hand").ruleset
        == "reflection-resource-hand"
    )
    assert (
        SimulationEvaluationConfig(ruleset="reflection-weapon-resource-hand").ruleset
        == "reflection-weapon-resource-hand"
    )
    assert (
        SimulationEvaluationConfig(ruleset="dual-role-resource-hand").ruleset
        == "dual-role-resource-hand"
    )
    assert (
        SimulationEvaluationConfig(ruleset="chance-weapon-resource-hand").ruleset
        == "chance-weapon-resource-hand"
    )
    assert (
        SimulationEvaluationConfig(ruleset="absorption-weapon-resource-hand").ruleset
        == "absorption-weapon-resource-hand"
    )


def test_paired_score_statistics_use_seed_pairs_as_samples() -> None:
    scores = np.array([1.0, 0.5, 0.0, 0.5], dtype=np.float64)

    mean, standard_error, lower_bound = paired_score_statistics(scores, 1.96)

    assert mean == 0.5
    assert standard_error == pytest.approx(0.204124)
    assert lower_bound == pytest.approx(0.099917, abs=1e-6)


def test_single_pair_is_inconclusive() -> None:
    assert paired_score_statistics(np.array([1.0]), 1.96) == (1.0, 0.0, 0.0)


def test_paired_evaluation_persists_a_non_promoting_report(tmp_path) -> None:
    candidate_directory, parent_id = unchanged_candidate(tmp_path)

    stored = evaluate_simulation_candidate(
        candidate_model_directory=candidate_directory,
        snapshot_path=SNAPSHOT,
        evaluation_directory=tmp_path / "evaluations",
        config=SimulationEvaluationConfig(
            games_per_seat=8,
            max_decisions_per_game=512,
            minimum_score=0.0,
            seed=67,
        ),
    )

    report_path = Path(stored.report_path)
    reloaded = SimulationEvaluationReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    parent_matchup, heuristic_matchup = stored.report.matchups
    assert reloaded == stored.report
    assert stored.report.parent_model_id == parent_id
    assert stored.report.passed is True
    assert stored.report.promotion_eligible is False
    assert parent_matchup.opponent_id == parent_id
    assert parent_matchup.completed_games == 16
    assert parent_matchup.incomplete_games == 0
    assert parent_matchup.candidate_wins == 8
    assert parent_matchup.candidate_losses == 8
    assert parent_matchup.candidate_split_pairs == 8
    assert parent_matchup.candidate_won_both_pairs == 0
    assert parent_matchup.candidate_lost_both_pairs == 0
    assert parent_matchup.gate_kind == "paired-superiority"
    assert parent_matchup.paired_score == 0.5
    assert parent_matchup.paired_score_lower_bound == 0.5
    assert parent_matchup.required_paired_score == 0.0
    assert heuristic_matchup.opponent_id == HEURISTIC_POLICY_ID
    assert heuristic_matchup.gate_kind == "paired-noninferiority"
    assert heuristic_matchup.required_paired_score == 0.0
    assert heuristic_matchup.completed_games == 16
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


def test_unchanged_candidate_fails_strict_parent_superiority(tmp_path) -> None:
    candidate_directory, _ = unchanged_candidate(tmp_path)

    stored = evaluate_simulation_candidate(
        candidate_model_directory=candidate_directory,
        snapshot_path=SNAPSHOT,
        evaluation_directory=tmp_path / "evaluations",
        config=SimulationEvaluationConfig(games_per_seat=8, seed=67),
    )

    parent_matchup = stored.report.matchups[0]
    assert parent_matchup.paired_score_lower_bound == 0.5
    assert parent_matchup.passed is False
    assert stored.report.passed is False
    assert "does not exceed 0.5000" in stored.report.gate_reasons[0]


def test_evaluation_rejects_a_mismatched_parent_identity(tmp_path) -> None:
    candidate_directory, parent_id = unchanged_candidate(tmp_path)
    parent_manifest_path = candidate_directory.parent / parent_id / "manifest.json"
    parent_manifest = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    parent_manifest["model_id"] = "substituted-parent"
    parent_manifest_path.write_text(json.dumps(parent_manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="parent directory manifest identity"):
        evaluate_simulation_candidate(
            candidate_model_directory=candidate_directory,
            snapshot_path=SNAPSHOT,
            evaluation_directory=tmp_path / "evaluations",
            config=SimulationEvaluationConfig(games_per_seat=1),
        )
