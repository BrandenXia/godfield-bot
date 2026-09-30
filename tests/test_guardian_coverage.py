"""Window-local terminal exposure, episode boundaries, and historical unknowns."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")

from godfield_bot.guardian_coverage import (  # noqa: E402
    GuardianWindowOutcomeCoverage,
    count_guardian_window_outcomes,
)


def flags(rows):
    return torch.tensor(rows, dtype=torch.bool)


def test_multiple_episodes_and_unfinished_tails_are_partitioned():
    terminated = flags([[0, 0], [1, 0], [0, 0], [0, 1], [0, 0], [0, 0]])
    truncated = flags([[0, 0], [0, 0], [0, 0], [1, 0], [0, 0], [0, 0]])
    trainable = flags([[1, 0], [0, 1], [1, 0], [0, 1], [1, 0], [0, 1]])
    original = [t.clone() for t in (terminated, truncated, trainable)]
    random_before = torch.random.get_rng_state().clone()
    result = count_guardian_window_outcomes(
        terminated=terminated, truncated=truncated, trainable=trainable
    )
    assert result.model_dump(exclude={"schema_version", "scope"}) == {
        "decisions": 12,
        "completed_episodes": 2,
        "truncated_episodes": 1,
        "winner_covered_decisions": 6,
        "truncation_covered_decisions": 2,
        "open_decisions": 4,
        "trainable_decisions": 6,
        "trainable_winner_covered_decisions": 3,
        "trainable_truncation_covered_decisions": 1,
        "trainable_open_decisions": 2,
    }
    for before, after in zip(original, (terminated, truncated, trainable), strict=True):
        torch.testing.assert_close(before, after)
    torch.testing.assert_close(random_before, torch.random.get_rng_state())


def test_a_later_window_must_not_backfill_earlier_unknown_outcomes():
    first = count_guardian_window_outcomes(
        terminated=flags([[0], [0]]), truncated=flags([[0], [0]]), trainable=flags([[1], [1]])
    )
    second = count_guardian_window_outcomes(
        terminated=flags([[0], [1]]), truncated=flags([[0], [0]]), trainable=flags([[1], [1]])
    )
    assert first.open_decisions == 2 and first.winner_covered_decisions == 0
    assert second.winner_covered_decisions == 2 and second.open_decisions == 0
    assert first.open_decisions == 2  # No mutable episode accumulation.


@pytest.mark.parametrize("bad", ["rank", "empty", "shape", "dtype", "overlap"])
def test_invalid_windows_reject(bad):
    terminated, truncated, trainable = flags([[1, 0]]), flags([[0, 0]]), flags([[1, 1]])
    if bad == "rank":
        terminated = terminated.flatten()
    elif bad == "empty":
        terminated = torch.zeros(0, 2, dtype=torch.bool)
    elif bad == "shape":
        trainable = trainable[:, :1]
    elif bad == "dtype":
        truncated = truncated.to(torch.int64)
    else:
        truncated[0, 0] = True
    with pytest.raises(ValueError, match="disjoint matching"):
        count_guardian_window_outcomes(
            terminated=terminated, truncated=truncated, trainable=trainable
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"decisions": 5},
        {"trainable_decisions": 0},
        {"trainable_open_decisions": 1},
        {"completed_episodes": 3},
        {"completed_episodes": 0},
        {"truncated_episodes": 1},
        {"open_decisions": -1},
        {"decisions": True},
    ],
)
def test_summary_validation_accounts_for_all_decisions(mutation):
    original = count_guardian_window_outcomes(
        terminated=flags([[0], [1]]), truncated=flags([[0], [0]]), trainable=flags([[1], [1]])
    )
    with pytest.raises(ValueError):
        GuardianWindowOutcomeCoverage.model_validate({**original.model_dump(), **mutation})


def test_random_windows_match_independent_forward_boundary_oracle():
    rng = np.random.default_rng(67)
    for _ in range(100):
        steps, batch = int(rng.integers(1, 33)), int(rng.integers(1, 9))
        events = rng.integers(0, 3, size=(steps, batch))
        trainable = rng.integers(0, 2, size=(steps, batch)).astype(bool)
        labels = np.zeros_like(events)
        for env in range(batch):
            for step in range(steps):
                ends = np.flatnonzero(events[step:, env])
                if len(ends):
                    labels[step, env] = events[step + ends[0], env]
        result = count_guardian_window_outcomes(
            terminated=torch.from_numpy(events == 1),
            truncated=torch.from_numpy(events == 2),
            trainable=torch.from_numpy(trainable),
        )
        assert result.winner_covered_decisions == np.count_nonzero(labels == 1)
        assert result.truncation_covered_decisions == np.count_nonzero(labels == 2)
        assert result.open_decisions == np.count_nonzero(labels == 0)
        assert result.trainable_winner_covered_decisions == np.count_nonzero(
            (labels == 1) & trainable
        )
        assert result.trainable_truncation_covered_decisions == np.count_nonzero(
            (labels == 2) & trainable
        )
        assert result.trainable_open_decisions == np.count_nonzero((labels == 0) & trainable)


CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def config(**kwargs):
    from godfield_bot.guardian_rollout import GuardianRolloutConfig
    from godfield_bot.guardian_training import GuardianTrainingConfig

    return GuardianTrainingConfig(
        arena=GuardianRolloutConfig(batch_size=4, max_turns=8, max_decisions=16),
        hidden_size=32,
        embedding_size=8,
        rollout_steps=16,
        updates=1,
        teacher_updates=1,
        ppo_epochs=1,
        environment_minibatch_size=2,
        evaluation_games=4,
        cpu_threads=1,
        **kwargs,
    )


@pytest.mark.parametrize("teacher", [True, False])
def test_collected_coverage_agrees_with_episode_and_trainable_totals(teacher):
    pytest.importorskip("godfield_sim")
    from godfield_bot.guardian_neural import GuardianArenaPolicy, GuardianPolicyArchitecture
    from godfield_bot.guardian_rollout import GuardianRolloutArena
    from godfield_bot.guardian_training import (
        GuardianDuelCollector,
        _runtime,
        train_guardian_teacher,
    )

    cfg = config()
    with _runtime(67, 1):
        model = GuardianArenaPolicy(
            GuardianPolicyArchitecture(vocabulary_size=297, hidden_size=32, embedding_size=8)
        )
        arena = GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena)
        rollout = GuardianDuelCollector(arena, model).collect(cfg, teacher=teacher)
        result = rollout.outcome_coverage
        assert result.decisions == 64 and result.trainable_decisions == int(
            rollout.policy_trainable.sum()
        )
        assert result.completed_episodes == rollout.completed_games
        assert result.truncated_episodes == rollout.truncated_games
        assert (
            result.open_decisions
            + result.winner_covered_decisions
            + result.truncation_covered_decisions
            == 64
        )
        if teacher:
            metric = train_guardian_teacher(
                model, torch.optim.Adam(model.parameters()), rollout, cfg
            )
            assert metric.outcome_coverage == result


def test_observability_does_not_change_replay_or_optimizer_result():
    pytest.importorskip("godfield_sim")
    from godfield_bot.guardian_neural import GuardianArenaPolicy, GuardianPolicyArchitecture
    from godfield_bot.guardian_rollout import GuardianRolloutArena
    from godfield_bot.guardian_training import GuardianDuelCollector, _runtime, train_guardian_ppo

    cfg = config()
    with _runtime(67, 1):
        left = GuardianArenaPolicy(
            GuardianPolicyArchitecture(vocabulary_size=297, hidden_size=32, embedding_size=8)
        )
        right = GuardianArenaPolicy(left.architecture)
        right.load_state_dict(left.state_dict())
        arena = GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena)
        rollout = GuardianDuelCollector(arena, left).collect(cfg)
        random_state = torch.random.get_rng_state()
        measured = train_guardian_ppo(left, torch.optim.Adam(left.parameters()), rollout, cfg)
        torch.random.set_rng_state(random_state)
        unmeasured = train_guardian_ppo(
            right,
            torch.optim.Adam(right.parameters()),
            replace(rollout, outcome_coverage=None),
            cfg,
        )
        assert measured == unmeasured
        for name, value in left.state_dict().items():
            torch.testing.assert_close(value, right.state_dict()[name], rtol=0, atol=0)


@pytest.fixture
def checkpoint(tmp_path):
    pytest.importorskip("godfield_sim")
    from godfield_bot.guardian_training import train_guardian_candidate

    return train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "arena", config=config()
    )


@pytest.mark.parametrize("mutation", ["decisions", "learner", "completed", "truncated", "teacher"])
def test_manifest_cross_checks_coverage_against_the_collected_window(checkpoint, mutation):
    from godfield_bot.guardian_training import GuardianArenaManifest

    data = checkpoint[1].model_dump()
    if mutation == "teacher":
        data["teacher_metrics"][0]["outcome_coverage"]["trainable_decisions"] = 0
    else:
        key = {
            "decisions": "decisions",
            "learner": "learner_decisions",
            "completed": "completed_games",
            "truncated": "truncated_games",
        }[mutation]
        if mutation == "decisions":
            data["update_metrics"][0]["outcome_coverage"][key] += 1
        else:
            data["update_metrics"][0][key] += 1
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)


def test_legacy_checkpoint_measurements_remain_unknown(checkpoint):
    from godfield_bot.guardian_training import GuardianArenaManifest

    data = checkpoint[1].model_dump()
    for phase in ("teacher_metrics", "update_metrics"):
        del data[phase][0]["outcome_coverage"]
    loaded = GuardianArenaManifest.model_validate(data)
    assert loaded.teacher_metrics[0].outcome_coverage is None
    assert loaded.update_metrics[0].outcome_coverage is None


@pytest.mark.parametrize(
    "bad",
    [
        {"updates": 0, "teacher_updates": 0},
        {"updates": 0, "defense_feedback_weight": 1},
    ],
)
def test_imitation_only_rejects_no_training_or_inapplicable_feedback(bad):
    from godfield_bot.guardian_training import GuardianTrainingConfig

    with pytest.raises(ValueError, match="imitation-only"):
        GuardianTrainingConfig.model_validate({**config().model_dump(), **bad})


def test_imitation_only_exports_verified_model_without_ppo(checkpoint, tmp_path):
    from godfield_bot.guardian_training import (
        IMITATION_ALGORITHM,
        GuardianTrainingConfig,
        evaluate_guardian_checkpoint,
        load_guardian_checkpoint,
        train_guardian_candidate,
    )

    cfg = GuardianTrainingConfig.model_validate({**config().model_dump(), "updates": 0})
    directory, saved = train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "teacher", config=cfg
    )
    assert saved.algorithm == IMITATION_ALGORITHM
    assert not saved.update_metrics and len(saved.teacher_metrics) == 1
    assert saved.evaluation_teacher == saved.evaluation_after
    assert saved.evaluation_teacher is not None
    assert saved.teacher_metrics[0].outcome_coverage is not None
    assert not saved.promotion_eligible and not saved.live_checkpoint_compatible
    loaded, _ = load_guardian_checkpoint(directory)
    assert loaded == saved
    result = evaluate_guardian_checkpoint(
        directory,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        games=4,
        seed=saved.evaluation_after.seed,
        cpu_threads=1,
    )
    assert result == saved.evaluation_after
    # The new stage evaluation must not consume policy RNG or alter the PPO result.
    assert checkpoint[1].evaluation_teacher is not None


@pytest.mark.parametrize(
    "mutation", ["seed", "games", "opponent", "absent-stage", "algorithm", "different-final"]
)
def test_teacher_stage_metadata_fails_closed(checkpoint, mutation):
    from godfield_bot.guardian_training import GuardianArenaManifest

    data = checkpoint[1].model_dump()
    if mutation == "seed":
        data["evaluation_teacher"]["seed"] += 1
    elif mutation == "games":
        data["evaluation_teacher"]["games"] += 2
    elif mutation == "opponent":
        data["evaluation_teacher"]["opponent"] = "greedy-discard-smoke-baseline-v3"
    elif mutation == "absent-stage":
        data["training"]["teacher_updates"] = 0
    elif mutation == "algorithm":
        data["algorithm"] = "provisional-guardian-duel-recurrent-imitation-only-v1"
    else:
        data["training"]["updates"] = 0
        data["algorithm"] = "provisional-guardian-duel-recurrent-imitation-only-v1"
        data["update_metrics"] = []
        data["evaluation_teacher"]["seed"] += 1
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)


def test_historical_teacher_evaluation_stays_unknown(checkpoint):
    from godfield_bot.guardian_training import GuardianArenaManifest

    data = checkpoint[1].model_dump()
    del data["evaluation_teacher"]
    assert GuardianArenaManifest.model_validate(data).evaluation_teacher is None


def test_stage_evaluation_does_not_change_training_rng_or_weights(tmp_path, monkeypatch):
    pytest.importorskip("godfield_sim")
    import godfield_bot.guardian_training as module

    cfg = config()
    _, first = module.train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "first", config=cfg
    )
    original = module.evaluate_guardian_policy
    calls = 0
    before = None

    def without_teacher(*args, **kwargs):
        nonlocal calls, before
        calls += 1
        if calls == 1:
            before = original(*args, **kwargs)
            return before
        if calls == 3:
            return before  # Simulate the historical absence of the mid-stage rollout.
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "evaluate_guardian_policy", without_teacher)
    _, second = module.train_guardian_candidate(
        catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=tmp_path / "second", config=cfg
    )
    assert first.weights_sha256 == second.weights_sha256
    assert first.teacher_metrics == second.teacher_metrics
    assert first.update_metrics == second.update_metrics
    assert first.rollout_sha256 == second.rollout_sha256
    assert first.evaluation_after == second.evaluation_after


def test_report_sums_only_known_windows_and_checks_weight_integrity(checkpoint, monkeypatch):
    import godfield_bot.guardian_training as module

    directory, manifest = checkpoint
    random_before = torch.random.get_rng_state().clone()
    report = module.report_guardian_training_exposure(directory)
    torch.testing.assert_close(random_before, torch.random.get_rng_state())
    assert report.teacher.measured_windows == report.ppo.measured_windows == 1
    assert report.teacher.measured_window_totals == manifest.teacher_metrics[0].outcome_coverage
    assert report.ppo.measured_window_totals == manifest.update_metrics[0].outcome_coverage
    known = report.ppo.measured_window_totals
    assert (
        report.ppo.winner_covered_trainable_fraction
        == known.trainable_winner_covered_decisions / known.trainable_decisions
    )
    assert report.checkpoint_weights_verified and not report.promotion_eligible
    assert report.evaluation_teacher == manifest.evaluation_teacher
    # One known window and one historical unknown: neither fabricate zeros nor
    # divide by unmeasured decisions when computing measured-outcome coverage.
    historical = manifest.model_copy(
        update={
            "teacher_metrics": (
                manifest.teacher_metrics[0],
                manifest.teacher_metrics[0].model_copy(update={"outcome_coverage": None}),
            )
        }
    )
    model = module.load_guardian_checkpoint(directory)[1]
    monkeypatch.setattr(module, "load_guardian_checkpoint", lambda _: (historical, model))
    partial = module.report_guardian_training_exposure(directory)
    assert partial.teacher.windows == 2 and partial.teacher.decisions == 128
    assert partial.teacher.measured_windows == partial.teacher.unmeasured_windows == 1
    assert partial.teacher.measured_window_totals == report.teacher.measured_window_totals
    assert (
        partial.teacher.winner_covered_trainable_fraction
        == report.teacher.winner_covered_trainable_fraction
    )


def test_report_legacy_unknowns_and_empty_ppo_phase(checkpoint, monkeypatch):
    import godfield_bot.guardian_training as module

    directory, manifest = checkpoint
    model = module.load_guardian_checkpoint(directory)[1]
    historical = manifest.model_copy(
        update={
            "teacher_metrics": tuple(
                m.model_copy(update={"outcome_coverage": None}) for m in manifest.teacher_metrics
            ),
            "update_metrics": (),
        }
    )
    monkeypatch.setattr(module, "load_guardian_checkpoint", lambda _: (historical, model))
    report = module.report_guardian_training_exposure(directory)
    assert report.teacher.unmeasured_windows == 1 and report.teacher.measured_windows == 0
    assert report.teacher.measured_window_totals is None
    assert report.teacher.winner_covered_trainable_fraction is None
    assert report.ppo.windows == report.ppo.decisions == 0
    assert report.ppo.measured_window_totals is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("windows", 2),
        ("decisions", 65),
        ("measured_windows", 0),
        ("unmeasured_windows", 1),
        ("winner_covered_trainable_fraction", 0.99999),
        ("measured_window_totals", None),
    ],
)
def test_aggregate_report_rejects_misleading_counts_or_denominators(checkpoint, field, value):
    from godfield_bot.guardian_training import (
        GuardianTrainingPhaseExposure,
        report_guardian_training_exposure,
    )

    data = report_guardian_training_exposure(checkpoint[0]).ppo.model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        GuardianTrainingPhaseExposure.model_validate(data)


def test_cli_report_is_readonly_and_imitation_only_flag_is_exposed(
    checkpoint, tmp_path, monkeypatch
):
    from structlog.testing import capture_logs

    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    directory = checkpoint[0]
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    result = CliRunner().invoke(
        app, ["simulation", "guardian-training-report", "--checkpoint", str(directory)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ppo"]["measured_windows"] == 1
    assert original == {p.name: p.read_bytes() for p in directory.iterdir()}
    with capture_logs():
        trained = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--checkpoint-root",
                str(tmp_path / "cli"),
                "--batch-size",
                "2",
                "--rollout-steps",
                "8",
                "--teacher-updates",
                "1",
                "--updates",
                "0",
                "--hidden-size",
                "32",
                "--embedding-size",
                "8",
                "--evaluation-games",
                "2",
                "--cpu-threads",
                "1",
            ],
        )
    assert trained.exit_code == 0, trained.output
    data = json.loads(trained.output)
    assert data["manifest"]["training"]["updates"] == 0
    assert data["manifest"]["algorithm"] == "provisional-guardian-duel-recurrent-imitation-only-v1"
    assert data["manifest"]["evaluation_teacher"] is not None


def test_report_refuses_a_weight_checksum_mismatch(checkpoint, monkeypatch):
    import godfield_bot.guardian_training as module

    monkeypatch.setattr(module, "_file_digest", lambda _: "0" * 64)
    with pytest.raises(module.GuardianTrainingError, match="checksum differs"):
        module.report_guardian_training_exposure(checkpoint[0])
