import json
import stat
from pathlib import Path

import pytest

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import initialize_model, load_model, save_candidate
from godfield_bot.simulation_evaluation import (
    HEURISTIC_POLICY_ID,
    SimulationEvaluationConfig,
    SimulationEvaluationReport,
    evaluate_simulation_candidate,
    wilson_lower_bound,
)

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
    assert heuristic_matchup.opponent_id == HEURISTIC_POLICY_ID
    assert heuristic_matchup.completed_games == 16
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


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
