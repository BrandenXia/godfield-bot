"""Full-pool PPO, forced value-only updates and frozen evaluation."""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

torch = pytest.importorskip("torch")
pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load, step  # noqa: E402
from test_full_game_neural import biased  # noqa: E402
from test_full_game_observation import PATHS, configured  # noqa: E402
from test_full_game_rollout import terminal_team_setup  # noqa: E402

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.full_game_evaluation import evaluate_full_game_candidate  # noqa: E402
from godfield_bot.full_game_greedy import GREEDY_POLICY_SHA256  # noqa: E402
from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyController,
    full_game_policy_inputs,
    transfer_full_game_attack_history,
)
from godfield_bot.full_game_observation import (  # noqa: E402
    ATTACK_HISTORY_OBSERVATION_ID,
    GLOBAL_FIELDS,
    FullGameObservationEncoder,
)
from godfield_bot.full_game_rollout import (  # noqa: E402
    collect_full_game_episodes,
    full_game_policy_sha256,
)
from godfield_bot.full_game_training import (  # noqa: E402
    FullGamePpoConfig,
    FullGameTrainingConfig,
    load_full_game_candidate,
    resume_full_game_training,
    run_full_game_training,
    save_full_game_candidate,
    train_full_game,
    train_full_game_ppo,
)


@pytest.fixture(scope="module", autouse=True)
def cpu_runtime():
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(2)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(67)
            yield
    finally:
        torch.set_num_threads(previous)


@pytest.fixture(scope="module")
def trained_candidate(tmp_path_factory):
    config = FullGameTrainingConfig(
        batch_size=2,
        player_count=4,
        teams=(1, 1, 2, 2),
        updates=1,
        ppo=FullGamePpoConfig(epochs=1, sequence_length=8),
    )
    report, policy = train_full_game(**PATHS, config=config)
    path = save_full_game_candidate(tmp_path_factory.mktemp("full-game"), report, policy)
    return config, report, policy, path


def test_native_team_training_changes_weights_and_checkpoint_restores_exactly(trained_candidate):
    config, report, policy, path = trained_candidate
    update = report.updates[0]
    assert update.terminal_target_decisions > 0 and update.actor_decisions > 0
    assert update.metrics is not None and update.metrics.gradient_norm > 0
    assert update.behavior_policy_sha256 != update.policy_sha256
    restored, model = load_full_game_candidate(path)
    assert restored.training == report
    assert full_game_policy_sha256(model) == full_game_policy_sha256(policy)
    repeated, _ = train_full_game(**PATHS, config=config)
    assert repeated == report


def test_frozen_evaluation_uses_held_out_games_for_both_team_assignments(trained_candidate):
    _, report, _, path = trained_candidate
    with pytest.raises(ValueError, match="held-out"):
        evaluate_full_game_candidate(path, **PATHS, seed=report.config.seed, games_per_faction=1)
    evaluation = evaluate_full_game_candidate(path, **PATHS, seed=100000, games_per_faction=2)
    assert [f.candidate_seats for f in evaluation.factions] == [(0, 1), (2, 3)]
    assert evaluation.wins + evaluation.losses + evaluation.draws + evaluation.truncations == 4
    assert evaluation.baseline_policy_sha256 == report.initial_collection.behavior_policy_sha256
    assert evaluation.candidate_policy_sha256 == report.final_policy_sha256
    assert not evaluation.promotion_eligible


def test_assigned_opponent_controls_its_own_native_actor():
    c = configured()
    hand(c.batch, [35], owner=1)
    candidate, baseline = FullGameActorCritic(), FullGameActorCritic()
    biased(candidate, 0)
    biased(baseline, 1)
    controller = FullGamePolicyController(c, candidate, opponent=baseline, opponent_seats=(1,))
    c.batch.start_environments(ids([0]))
    assert controller.step(ids([0]), deterministic=True).actions.tolist() == [0]
    assert controller.step(ids([0]), deterministic=True).actions.tolist() == [1]


def test_forced_only_episode_trains_value_without_actor_head_update():
    c = configured(max_turns=1, max_decisions=1)
    load(c.batch, hp=1, illness=1, mask=0)
    c.batch.seed_confusion(ids([0]), ids([0]), ids([1]))
    p = FullGameActorCritic()
    collection = collect_full_game_episodes(c, p)
    assert collection.eligible_decisions == 1 and collection.eligible_policy_decisions == 0
    actor, value = p.action_head.weight.detach().clone(), p.value_head.weight.detach().clone()
    metrics = train_full_game_ppo(
        p, torch.optim.Adam(p.parameters()), collection, FullGamePpoConfig()
    )
    assert metrics.value_loss > 0 and metrics.policy_loss == metrics.entropy == 0
    assert torch.equal(actor, p.action_head.weight)
    assert not torch.equal(value, p.value_head.weight)


def test_nonfinite_optimizer_step_rolls_back_weights_and_adam_state(monkeypatch):
    p = FullGameActorCritic()
    collection = collect_full_game_episodes(terminal_team_setup(), p)
    before = full_game_policy_sha256(p)
    optimizer = torch.optim.Adam(p.parameters())
    step = optimizer.step

    def corrupt_step():
        step()
        with torch.no_grad():
            p.value_head.weight.fill_(float("nan"))

    monkeypatch.setattr(optimizer, "step", corrupt_step)
    with pytest.raises(ValueError, match="non-finite weights"):
        train_full_game_ppo(p, optimizer, collection, FullGamePpoConfig())
    assert full_game_policy_sha256(p) == before
    assert not optimizer.state


def test_cli_reports_zero_terminal_samples_and_creates_no_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    path = tmp_path / "candidates"
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-train",
            "--updates",
            "1",
            "--batch-size",
            "1",
            "--max-decisions",
            "1",
            "--checkpoint-root",
            str(path),
        ],
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["checkpoint"] is None and not path.exists()
    assert payload["training"]["updates"][0]["outcomes"][0]["status"] == "decision-limit"


@pytest.fixture(scope="module")
def resumable_candidate(tmp_path_factory):
    runner = CliRunner()
    # Keep the CLI's captured stderr from replacing global logging for other tests.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
        result = runner.invoke(
            app,
            [
                "simulation",
                "full-game-train",
                "--updates",
                "1",
                "--batch-size",
                "2",
                "--players",
                "4",
                "--teams",
                "1,1,2,2",
                "--checkpoint-root",
                str(tmp_path_factory.mktemp("resumable")),
            ],
        )
    assert result.exit_code == 0, result.output
    return Path(json.loads(result.stdout)["checkpoint"])


def test_cli_resume_matches_uninterrupted_training(resumable_candidate, monkeypatch, tmp_path):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    parent_manifest = (resumable_candidate / "manifest.json").read_bytes()
    parent_adam = (resumable_candidate / "adam.pt").read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-resume",
            str(resumable_candidate),
            "--additional-updates",
            "2",
            "--checkpoint-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    child = Path(json.loads(result.stdout)["checkpoint"])
    manifest, policy = load_full_game_candidate(child)
    assert manifest.schema_version == 2 and manifest.adam is not None
    uninterrupted = run_full_game_training(**PATHS, config=manifest.training.config)
    assert manifest.training == uninterrupted.report
    assert full_game_policy_sha256(policy) == full_game_policy_sha256(uninterrupted.policy)
    resumed_adam = torch.load(child / "adam.pt", map_location="cpu", weights_only=True)
    expected_adam = uninterrupted.optimizer.state_dict()
    assert resumed_adam["param_groups"] == expected_adam["param_groups"]
    assert resumed_adam["state"].keys() == expected_adam["state"].keys()
    for parameter, moments in expected_adam["state"].items():
        for name, moment in moments.items():
            assert torch.equal(resumed_adam["state"][parameter][name], moment)
    assert (resumable_candidate / "manifest.json").read_bytes() == parent_manifest
    assert (resumable_candidate / "adam.pt").read_bytes() == parent_adam


def test_version_one_still_loads_for_evaluation_but_cannot_resume(trained_candidate):
    _, _, _, directory = trained_candidate
    assert load_full_game_candidate(directory)[0].schema_version == 1
    with pytest.raises(ValueError, match="version 2 checkpoint"):
        resume_full_game_training(directory, **PATHS, additional_updates=1)


def test_zero_history_transfer_keeps_logits_values_and_memory_exact(trained_candidate):
    _, _, original, _ = trained_candidate
    migrated = transfer_full_game_attack_history(original)
    c = configured(player_count=4, teams=(1, 1, 2, 2))
    hand(c.batch, [35])
    c.batch.start_environments(ids([0]))
    for choice in (1, 0, 21):
        step(c.batch, [choice])
    base = FullGameObservationEncoder(c).encode()
    expanded = FullGameObservationEncoder(c, ATTACK_HISTORY_OBSERVATION_ID).encode()
    assert expanded.global_features[:, len(GLOBAL_FIELDS) :].any()
    previous = torch.linspace(-0.5, 0.5, original.architecture.hidden_size)[None, :]
    with torch.no_grad():
        before = original(full_game_policy_inputs(base), previous)
        after = migrated(full_game_policy_inputs(expanded), previous)
    assert all(torch.equal(a, b) for a, b in zip(before, after, strict=True))


def test_cli_trains_and_resumes_transferred_history_policy(
    trained_candidate, tmp_path, monkeypatch
):
    _, source, original, directory = trained_candidate
    parent_bytes = (directory / "manifest.json").read_bytes()
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-train",
            "--attack-history",
            "--initialize-from",
            str(directory),
            "--updates",
            "1",
            "--batch-size",
            "2",
            "--players",
            "4",
            "--teams",
            "1,1,2,2",
            "--seed",
            "302",
            "--checkpoint-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    child = Path(json.loads(result.stdout)["checkpoint"])
    manifest, policy = load_full_game_candidate(child)
    initialization = manifest.training.initialization
    assert initialization is not None
    assert initialization.source_policy_sha256 == source.final_policy_sha256
    assert initialization.initialized_policy_sha256 == full_game_policy_sha256(
        transfer_full_game_attack_history(original)
    )
    assert policy.history_encoder is not None and torch.count_nonzero(policy.history_encoder.weight)
    resumed = resume_full_game_training(child, **PATHS, additional_updates=1)
    continuous = run_full_game_training(
        **PATHS, config=resumed.report.config, initialize_from=directory
    )
    assert resumed.report == continuous.report
    assert (directory / "manifest.json").read_bytes() == parent_bytes
    with pytest.raises(ValueError, match="held-out"):
        evaluate_full_game_candidate(
            child,
            **PATHS,
            seed=source.config.seed,
            games_per_faction=1,
            baseline_directory=directory,
        )
    with pytest.raises(ValueError, match="explicit --baseline"):
        evaluate_full_game_candidate(child, **PATHS, seed=303000, games_per_faction=1)
    evaluated = evaluate_full_game_candidate(
        child, **PATHS, seed=303000, games_per_faction=1, baseline_directory=directory
    )
    assert evaluated.baseline_policy_sha256 == source.final_policy_sha256
    assert not evaluated.promotion_eligible


def test_frozen_evaluation_accepts_an_earlier_checkpoint(trained_candidate, resumable_candidate):
    _, baseline, _, directory = trained_candidate
    result = evaluate_full_game_candidate(
        resumable_candidate, **PATHS, seed=300000, games_per_faction=1, baseline_directory=directory
    )
    assert result.evaluation == "held-out-native-each-faction-vs-checkpoint-v1"
    assert result.baseline_policy_sha256 == baseline.final_policy_sha256
    assert result.candidate_policy_sha256 != result.baseline_policy_sha256
    assert result.wins + result.losses + result.draws + result.truncations == 2


def test_cli_evaluates_each_faction_against_fixed_tactics(trained_candidate, monkeypatch):
    _, _, _, path = trained_candidate
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-evaluate",
            str(path),
            "--greedy-baseline",
            "--games-per-faction",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["evaluation"] == "held-out-native-each-faction-vs-public-greedy-v1"
    assert report["baseline_policy_sha256"] == GREEDY_POLICY_SHA256
    assert [f["candidate_seats"] for f in report["factions"]] == [[0, 1], [2, 3]]
    assert sum(report[name] for name in ("wins", "losses", "draws", "truncations")) == 2
    assert not report["promotion_eligible"]
    with pytest.raises(ValueError, match="baseline selection"):
        evaluate_full_game_candidate(path, **PATHS, baseline_directory=path, greedy_baseline=True)


def test_checksummed_adam_state_with_wrong_step_count_is_rejected(resumable_candidate, tmp_path):
    manifest = json.loads((resumable_candidate / "manifest.json").read_bytes())
    (tmp_path / "weights.pt").write_bytes((resumable_candidate / "weights.pt").read_bytes())
    state = torch.load(resumable_candidate / "adam.pt", map_location="cpu", weights_only=True)
    next(iter(state["state"].values()))["step"].add_(1)
    path = tmp_path / "adam.pt"
    torch.save(state, path)
    manifest["adam"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Adam step count"):
        resume_full_game_training(tmp_path, **PATHS, additional_updates=1)
