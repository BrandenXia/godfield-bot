"""Opt-in, catalog-derived booster curriculum stays isolated from verified models."""

from pathlib import Path

import pytest

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import initialize_model, migrate_hand_capacity
from godfield_bot.provisional_rules import provisional_strength_powder_boost
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_coverage import build_simulation_coverage_report
from godfield_bot.simulation_evaluation import SimulationEvaluationConfig
from godfield_bot.simulation_policy import build_curriculum_heuristic, curriculum_heuristic_actions
from godfield_bot.simulation_training import SimulationTrainingConfig, train_simulation_candidate

np = pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PROVISIONAL = "provisional-strength-powder-wide-hand"
BASE = "wide-hand-gift-weighted-dream-resource-hand"


def test_strength_powder_requires_exact_pinned_bible_and_catalog() -> None:
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text(encoding="utf-8"))
    assert provisional_strength_powder_boost(bible) == 10
    with pytest.raises(ValueError, match="pinned reviewed Bible"):
        wrong_client = bible.client.model_copy(update={"sha256": "0" * 64})
        provisional_strength_powder_boost(
            bible.model_copy(update={"client": wrong_client})
        )
    changed = bible.model_copy(deep=True)
    sundries = changed.catalog["sundries"]
    changed.catalog["sundries"] = sundries.model_copy(
        update={
            "items": tuple(
                item.model_copy(update={"detail": ("Strength Powder", "+ATK11")})
                if item.asset == "strength-powder"
                else item
                for item in sundries.items
            )
        }
    )
    with pytest.raises(ValueError, match="reviewed Strength Powder"):
        provisional_strength_powder_boost(changed)


def test_provisional_booster_is_trainable_locally_but_isolated() -> None:
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(bible)
    token = vocabulary.token_id("sundries", "strength-powder")
    assert SimulationTrainingConfig(ruleset=PROVISIONAL).ruleset == PROVISIONAL
    assert SimulationEvaluationConfig(ruleset=PROVISIONAL).ruleset == PROVISIONAL
    base = create_attack_defense_simulation(BIBLE, batch_size=1, ruleset=BASE)
    provisional = create_attack_defense_simulation(
        BIBLE, batch_size=1024, seed=67, ruleset=PROVISIONAL
    )
    assert token not in base.catalog_token_ids
    assert token in provisional.catalog_token_ids
    assert len(provisional.catalog_token_ids) == len(base.catalog_token_ids) + 1
    assert base.metadata.rule_catalog_sha256 == (
        "d29ec8edde5a270ab4738b06820e56f8c09dc91c22b42208e14fe10334d03eb6"
    )
    assert provisional.metadata.rule_catalog_sha256 != base.metadata.rule_catalog_sha256
    assert provisional.metadata.ruleset_id.startswith("provisional-strength-powder-v1-")
    assert not provisional.metadata.promotion_eligible
    assert provisional.metadata.hand_slots == 18
    powder_cards = provisional.batch.hand_token_ids == token
    assert np.count_nonzero(powder_cards) > 0
    assert set(np.unique(provisional.batch.hand_card_kinds[powder_cards]).tolist()) == {3}
    heuristic = build_curriculum_heuristic(bible, vocabulary, ruleset=PROVISIONAL)
    assert heuristic.boosters is not None
    assert heuristic.boosters[token] == 10
    actions = curriculum_heuristic_actions(provisional, np.arange(1024), heuristic)
    assert np.all(provisional.batch.action_mask[np.arange(1024), actions])
    provisional.batch.step(actions)

    report = build_simulation_coverage_report(BIBLE, ruleset=PROVISIONAL)
    assert report.included_artifact_count == 197
    assert report.missing_artifact_count == 94
    assert "strength-powder" not in report.missing_by_category["sundries"]
    assert not report.full_game_training_ready
    assert not report.official_fidelity_verified
    assert not report.promotion_eligible


def test_provisional_booster_candidate_runs_one_local_ppo_update(tmp_path: Path) -> None:
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(bible)
    source = initialize_model(
        tmp_path,
        vocabulary,
        client_sha256=bible.client.sha256,
        feature_schema_version=10,
        global_feature_count=24,
    )
    migrated = migrate_hand_capacity(
        tmp_path / source.model_id,
        tmp_path,
        vocabulary,
        client_sha256=bible.client.sha256,
    )
    candidate = train_simulation_candidate(
        base_model_directory=tmp_path / migrated.model_id,
        snapshot_path=BIBLE,
        model_root=tmp_path,
        config=SimulationTrainingConfig(
            ruleset=PROVISIONAL,
            batch_size=8,
            rollout_steps=16,
            updates=1,
            teacher_updates=0,
            ppo_epochs=1,
            minibatch_size=8,
            environment_minibatch_size=8,
            device="cpu",
        ),
    )
    assert candidate.metrics["ppo_transitions"] == 128
    assert candidate.training_context["simulation"]["ruleset_id"].startswith(
        "provisional-strength-powder-v1-"
    )
    assert candidate.training_context["simulation"]["rule_catalog_size"] == 197
