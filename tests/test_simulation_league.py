import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest
import torch
from pydantic import ValidationError

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
    LEGACY_FEATURE_SCHEMA_VERSION,
    LEGACY_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
)
from godfield_bot.model_registry import initialize_model, load_model, save_candidate
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_league import (
    LEAGUE_ALGORITHM,
    FrozenSimulationLeague,
    SimulationLeagueSnapshot,
    create_simulation_league,
    load_simulation_league,
)
from godfield_bot.simulation_league_evaluation import (
    SimulationLeagueEvaluationConfig,
    SimulationLeagueEvaluationReport,
    evaluate_simulation_league_candidate,
)
from godfield_bot.simulation_policy import build_curriculum_heuristic
from godfield_bot.simulation_training import (
    SimulationTrainingConfig,
    collect_self_play_rollout,
    train_ppo_rollout,
    train_simulation_candidate,
)

pytest.importorskip("godfield_sim")
SNAPSHOT = Path("data/snapshots/2026-09-07/bible.json")


@pytest.fixture
def league_fixture(tmp_path: Path) -> tuple[Path, Path, FrozenSimulationLeague]:
    bible = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(bible)
    root = tmp_path / "models"
    models = [
        initialize_model(
            root,
            vocabulary,
            client_sha256=bible.client.sha256,
            feature_schema_version=LEGACY_FEATURE_SCHEMA_VERSION,
            global_feature_count=LEGACY_GLOBAL_FEATURE_COUNT,
            seed=seed,
        )
        for seed in (67, 68)
    ]
    base = root / models[0].model_id
    path, _ = create_simulation_league(
        base_model_directory=base,
        opponent_model_directories=(root / models[1].model_id,),
        snapshot_path=SNAPSHOT,
        league_directory=tmp_path / "leagues",
        ruleset="fixed-role",
    )
    frozen = load_simulation_league(
        path,
        reference=models[0],
        simulation=create_attack_defense_simulation(SNAPSHOT, batch_size=1, seed=67).metadata,
        heuristic=build_curriculum_heuristic(bible, vocabulary),
        ruleset="fixed-role",
        required_parent_id=models[0].model_id,
        device="cpu",
    )
    return base, path, frozen


def test_league_freezes_identities_and_rejects_duplicate_or_changed_members(league_fixture) -> None:
    base, path, frozen = league_fixture
    assert len(frozen.snapshot.members) == 3
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (
        frozen.snapshot.sha256
        == SimulationLeagueSnapshot.model_validate_json(path.read_text(encoding="utf-8")).sha256
    )
    with pytest.raises(ValidationError, match="duplicate opponents"):
        SimulationLeagueSnapshot(
            **{
                **frozen.snapshot.model_dump(),
                "members": (*frozen.snapshot.members, frozen.snapshot.members[1]),
            }
        )
    with pytest.raises(ValueError, match="identity or weights changed"):
        document = frozen.snapshot.model_dump(mode="json")
        document["members"][1]["weights_sha256"] = "a" * 64
        path.write_text(json.dumps(document), encoding="utf-8")
        manifest, _ = load_model(base)
        load_simulation_league(
            path,
            reference=manifest,
            simulation=frozen.snapshot.simulation,
            heuristic=frozen.heuristic,
            ruleset="fixed-role",
            required_parent_id=manifest.model_id,
            device="cpu",
        )


def test_league_rejects_wrong_contract_and_missing_parent(league_fixture) -> None:
    base, path, frozen = league_fixture
    manifest, _ = load_model(base)
    kwargs = {
        "reference": manifest,
        "simulation": frozen.snapshot.simulation,
        "heuristic": frozen.heuristic,
        "ruleset": "fixed-role",
        "required_parent_id": manifest.model_id,
        "device": "cpu",
    }
    with pytest.raises(ValueError, match="different simulator contract"):
        load_simulation_league(path, **{**kwargs, "ruleset": "mixed-hand"})
    with pytest.raises(ValueError, match="exact frozen training parent"):
        load_simulation_league(path, **{**kwargs, "required_parent_id": "absent-parent"})


def test_frozen_rollout_uses_episode_opponents_and_independent_memory(league_fixture) -> None:
    base, _, frozen = league_fixture
    _, learner = load_model(base)
    frozen_weights = [
        {name: value.clone() for name, value in model.state_dict().items()}
        if model is not None
        else None
        for model in frozen.models
    ]
    torch.manual_seed(670)
    rollout = collect_self_play_rollout(
        learner,
        create_attack_defense_simulation(SNAPSHOT, batch_size=24, seed=67),
        rollout_steps=64,
        gamma=0.99,
        gae_lambda=0.95,
        device=torch.device("cpu"),
        league=frozen,
    )
    assert rollout.opponents is not None and rollout.learner_seats is not None
    assert all(count > 0 for count in rollout.opponent_action_counts)
    assert sum(rollout.opponent_completed_games) == rollout.completed_episodes > 0
    assert sum(rollout.opponent_action_counts) == int((~rollout.policy_trainable).sum())
    assert torch.equal(rollout.policy_trainable, rollout.actors == rollout.learner_seats)
    assert rollout.action_mask.gather(2, rollout.actions.unsqueeze(-1)).all()
    for step in range(1, rollout.steps):
        continuing = ~rollout.terminated[step - 1]
        assert torch.equal(
            rollout.opponents[step, continuing], rollout.opponents[step - 1, continuing]
        )
        assert torch.equal(
            rollout.learner_seats[step, continuing], rollout.learner_seats[step - 1, continuing]
        )
        ended = rollout.terminated[step - 1]
        assert torch.equal(
            rollout.learner_seats[step, ended], 1 - rollout.learner_seats[step - 1, ended]
        )

    # Replay every neural opponent from its own memory; actions must match exactly.
    states = torch.zeros((rollout.batch_size, learner.hidden_size))
    for step in range(rollout.steps):
        if step:
            states[rollout.terminated[step - 1]] = 0.0
        for index, model in enumerate(frozen.models):
            if model is None:
                continue
            rows = (
                ((rollout.opponents[step] == index) & ~rollout.policy_trainable[step])
                .nonzero(as_tuple=False)
                .squeeze(1)
            )
            if not rows.numel():
                continue
            with torch.no_grad():
                logits, _, next_states = model(
                    *rollout.observations_at(step, rows), recurrent_state=states[rows]
                )
            states[rows] = next_states
            assert torch.equal(logits.argmax(dim=1), rollout.actions[step, rows])
    metrics = train_ppo_rollout(
        learner,
        torch.optim.Adam(learner.parameters(), lr=3e-4),
        rollout,
        SimulationTrainingConfig(
            batch_size=24, rollout_steps=64, updates=1, ppo_epochs=1, environment_minibatch_size=24
        ),
    )
    assert abs(metrics.approximate_kl) < 1e-6
    for model, before in zip(frozen.models, frozen_weights, strict=True):
        if model is not None and before is not None:
            assert not model.training
            assert all(not parameter.requires_grad for parameter in model.parameters())
            for name, value in model.state_dict().items():
                assert torch.equal(value, before[name])


def test_league_training_persists_roster_and_actual_opponent_counts(league_fixture) -> None:
    base, path, frozen = league_fixture
    manifest = train_simulation_candidate(
        base_model_directory=base,
        model_root=base.parent,
        snapshot_path=SNAPSHOT,
        league_path=path,
        config=SimulationTrainingConfig(
            batch_size=24,
            rollout_steps=32,
            updates=1,
            ppo_epochs=1,
            teacher_updates=0,
            environment_minibatch_size=24,
        ),
    )
    assert manifest.training_algorithm == LEAGUE_ALGORITHM
    assert manifest.training_context["league_sha256"] == frozen.snapshot.sha256
    assert manifest.training_context["league"] == frozen.snapshot.model_dump(mode="json")
    assert manifest.metrics["heuristic_opponent_fraction"] == pytest.approx(1 / 3)
    assert all(manifest.metrics[f"league_{index}_actions"] > 0 for index in range(3))


def test_ppo_can_learn_values_from_a_minibatch_with_only_frozen_actions(league_fixture) -> None:
    base, _, frozen = league_fixture
    _, model = load_model(base)
    rollout = collect_self_play_rollout(
        model,
        create_attack_defense_simulation(SNAPSHOT, batch_size=4, seed=67),
        rollout_steps=4,
        gamma=0.99,
        gae_lambda=0.95,
        device=torch.device("cpu"),
        league=frozen,
    )
    mask = rollout.policy_trainable.clone()
    mask[:, 0] = False
    metrics = train_ppo_rollout(
        model,
        torch.optim.Adam(model.parameters(), lr=3e-4),
        replace(rollout, policy_trainable=mask),
        SimulationTrainingConfig(
            batch_size=4, rollout_steps=4, updates=1, ppo_epochs=1, environment_minibatch_size=1
        ),
    )
    assert all(torch.isfinite(torch.tensor(value)) for value in metrics.model_dump().values())


def test_league_gate_rejects_unchanged_parent_and_every_incomplete_member(
    league_fixture, tmp_path: Path
) -> None:
    base, path, frozen = league_fixture
    parent, model = load_model(base)
    bible = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))
    candidate = save_candidate(
        base.parent,
        model,
        ArtifactVocabulary.from_snapshot(bible),
        parent=parent,
        seed=67,
        training_algorithm="league-evaluation-fixture",
        training_dataset_sha256="a" * 64,
        training_run_ids=(),
        metrics={},
        training_context={"league_sha256": frozen.snapshot.sha256},
    )
    result = evaluate_simulation_league_candidate(
        candidate_model_directory=base.parent / candidate.model_id,
        league_path=path,
        snapshot_path=SNAPSHOT,
        evaluation_directory=tmp_path / "evaluations",
        config=SimulationLeagueEvaluationConfig(ruleset="fixed-role", games_per_seat=8),
    )
    assert len(result.report.matchups) == 3
    parent_matchup = result.report.matchups[1]
    assert parent_matchup.paired_score_lower_bound == 0.5
    assert not parent_matchup.passed and not result.report.passed
    assert all(matchup.gate_kind == "paired-superiority" for matchup in result.report.matchups)
    assert all(matchup.required_paired_score == 0.5 for matchup in result.report.matchups)
    assert result.report.league_sha256 == frozen.snapshot.sha256
    assert not result.report.promotion_eligible
    assert stat.S_IMODE(Path(result.report_path).stat().st_mode) == 0o600
    assert (
        SimulationLeagueEvaluationReport.model_validate_json(
            Path(result.report_path).read_text(encoding="utf-8")
        )
        == result.report
    )
    incomplete = evaluate_simulation_league_candidate(
        candidate_model_directory=base.parent / candidate.model_id,
        league_path=path,
        snapshot_path=SNAPSHOT,
        evaluation_directory=tmp_path / "evaluations",
        config=SimulationLeagueEvaluationConfig(
            ruleset="fixed-role", games_per_seat=8, max_decisions_per_game=2
        ),
    )
    assert not incomplete.report.passed
    assert all(matchup.incomplete_games > 0 for matchup in incomplete.report.matchups)

    # Keeping the same opponents but altering sampling creates a different frozen experiment.
    changed = frozen.snapshot.model_dump(mode="json")
    changed["members"][0]["weight"] = 2.0
    different_path = tmp_path / "different-league.json"
    different_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the candidate's frozen training league"):
        evaluate_simulation_league_candidate(
            candidate_model_directory=base.parent / candidate.model_id,
            league_path=different_path,
            snapshot_path=SNAPSHOT,
            evaluation_directory=tmp_path / "evaluations",
            config=SimulationLeagueEvaluationConfig(ruleset="fixed-role", games_per_seat=8),
        )
