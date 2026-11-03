"""Terminal-only teacher credit, recurrent fitting, provenance and PPO resume."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load  # noqa: E402
from test_full_game_observation import PATHS, configured  # noqa: E402

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.full_game_evaluation import evaluate_full_game_candidate  # noqa: E402
from godfield_bot.full_game_greedy import FullGameGreedyPolicy  # noqa: E402
from godfield_bot.full_game_imitation import (  # noqa: E402
    FullGameImitationConfig,
    collect_full_game_demonstrations,
    fit_full_game_demonstrations,
)
from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyArchitecture,
)
from godfield_bot.full_game_observation import (  # noqa: E402
    ATTACK_HISTORY_OBSERVATION_ID,
    OBSERVATION_ID,
)
from godfield_bot.full_game_rollout import full_game_policy_sha256  # noqa: E402
from godfield_bot.full_game_training import (  # noqa: E402
    FullGamePpoConfig,
    FullGameTrainingConfig,
    FullGameTrainingReport,
    load_full_game_candidate,
    resume_full_game_training,
    run_full_game_training,
    save_full_game_training,
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


def test_terminal_teacher_demonstrations_exclude_truncations_and_keep_seats_separate():
    c = configured(size=2, player_count=3, max_decisions=12)
    for owner in range(3):
        hand(c.batch, [35], env=0, owner=owner)
    for owner in (1, 2):
        load(c.batch, env=0, owner=owner, hp=1, illness=3, mask=0)
    data = collect_full_game_demonstrations(c, ATTACK_HISTORY_OBSERVATION_ID)
    assert sum(data.summary.outcomes[:2]) == 1
    assert data.summary.outcomes[3] == 1
    assert data.summary.accepted_decisions > data.summary.terminal_decisions > 0
    assert set(data.observation.leases[:, 0]) == {0}
    np.testing.assert_array_equal(
        data.actions, FullGameGreedyPolicy(c.metadata).actions(data.observation)
    )
    for rows in data.sequences:
        assert len(set(data.observation.leases[rows, 3])) == 1
        assert (np.diff(data.observation.leases[rows, 2]) > 0).all()
    with pytest.raises(ValueError, match="fresh"):
        collect_full_game_demonstrations(c, ATTACK_HISTORY_OBSERVATION_ID)


def test_forced_terminal_decisions_are_recorded_but_not_supervised():
    c = configured(player_count=2, max_turns=1, max_decisions=1)
    load(c.batch, hp=1, illness=1, mask=0)
    c.batch.seed_confusion(ids([0]), ids([0]), ids([1]))
    data = collect_full_game_demonstrations(c, OBSERVATION_ID)
    assert data.summary.terminal_decisions == 1
    assert data.summary.actor_decisions == 0
    model = FullGameActorCritic()
    with pytest.raises(ValueError, match="voluntary terminal"):
        fit_full_game_demonstrations(
            model, torch.optim.Adam(model.parameters()), data, FullGameImitationConfig()
        )


def test_imitation_fits_complete_recurrent_sequences_without_value_head_updates(monkeypatch):
    c = configured(size=4, player_count=2, acquisition_mode="all-held-weighted", seed=1020000)
    data = collect_full_game_demonstrations(c, OBSERVATION_ID)
    model = FullGameActorCritic()
    config = FullGameImitationConfig(epochs=8, sequence_length=4, sequences_per_group=2)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    value = {k: v.clone() for k, v in model.value_head.state_dict().items()}
    before, after = fit_full_game_demonstrations(model, optimizer, data, config)
    assert after.cross_entropy < before.cross_entropy
    assert after.accuracy > before.accuracy
    for key, tensor in value.items():
        assert torch.equal(tensor, model.value_head.state_dict()[key])
    # Invalid action labels and mixing seats cannot enter recurrent supervision.
    with pytest.raises(ValueError, match="decisions or seat"):
        fit_full_game_demonstrations(
            model, optimizer, replace(data, actions=np.full_like(data.actions, 28)), config
        )
    with pytest.raises(ValueError, match="decisions or seat"):
        fit_full_game_demonstrations(
            model, optimizer, replace(data, sequences=(np.arange(len(data.actions)),)), config
        )
    original = full_game_policy_sha256(model)
    state = {k: v["step"].clone() for k, v in optimizer.state_dict()["state"].items()}

    def fail():
        with torch.no_grad():
            model.action_head.bias.fill_(float("nan"))

    monkeypatch.setattr(optimizer, "step", fail)
    with pytest.raises(ValueError, match="non-finite"):
        fit_full_game_demonstrations(model, optimizer, data, config)
    assert full_game_policy_sha256(model) == original
    assert all(torch.equal(v, optimizer.state_dict()["state"][k]["step"]) for k, v in state.items())


@pytest.fixture(scope="module")
def warmed_candidate(tmp_path_factory):
    config = FullGameTrainingConfig(
        batch_size=2,
        player_count=2,
        updates=1,
        seed=1050000,
        ppo=FullGamePpoConfig(epochs=1, sequence_length=8),
        architecture=FullGamePolicyArchitecture(
            schema_version=2, observation_id=ATTACK_HISTORY_OBSERVATION_ID
        ),
    )
    imitation = FullGameImitationConfig(batches=1, epochs=2, seed=config.seed + 4)
    run = run_full_game_training(**PATHS, config=config, imitation=imitation)
    directory = save_full_game_training(tmp_path_factory.mktemp("full-game-imitation"), run)
    return run, directory


def test_imitation_provenance_and_adam_resume_are_exact(warmed_candidate):
    run, directory = warmed_candidate
    warmup = run.report.imitation
    assert warmup is not None
    restored, policy = load_full_game_candidate(directory)
    assert restored.training == run.report
    assert full_game_policy_sha256(policy) == run.report.final_policy_sha256
    assert warmup.after_policy_sha256 == run.report.initial_collection.behavior_policy_sha256
    assert warmup.before_policy_sha256 != warmup.after_policy_sha256
    resumed = resume_full_game_training(directory, **PATHS, additional_updates=1)
    whole = run_full_game_training(
        **PATHS, config=run.report.config.model_copy(update={"updates": 2}), imitation=warmup.config
    )
    assert resumed.report == whole.report
    assert full_game_policy_sha256(resumed.policy) == full_game_policy_sha256(whole.policy)
    assert resumed.report.imitation == warmup
    # Extending PPO into a teacher seed is forbidden before collecting any more games.
    with pytest.raises(ValueError, match="disjoint"):
        resume_full_game_training(directory, **PATHS, additional_updates=2)
    tampered = run.report.model_dump()
    tampered["imitation"]["after_policy_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        FullGameTrainingReport.model_validate(tampered)


def test_evaluation_and_cli_require_separate_training_seeds(
    warmed_candidate, tmp_path, monkeypatch
):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    run, directory = warmed_candidate
    warmup = run.report.imitation
    assert warmup is not None
    with pytest.raises(ValueError, match="held-out"):
        evaluate_full_game_candidate(
            directory, **PATHS, greedy_baseline=True, seed=warmup.config.seed, games_per_faction=1
        )
    with pytest.raises(ValueError, match="explicit --baseline"):
        evaluate_full_game_candidate(directory, **PATHS, seed=1060000, games_per_faction=1)
    result = evaluate_full_game_candidate(
        directory, **PATHS, greedy_baseline=True, seed=1060000, games_per_faction=1
    )
    assert result.wins + result.losses + result.draws + result.truncations == 2
    args = [
        "simulation",
        "full-game-train",
        "--players",
        "2",
        "--batch-size",
        "2",
        "--updates",
        "1",
        "--seed",
        "1070000",
        "--imitation-batches",
        "1",
        "--imitation-epochs",
        "1",
        "--imitation-seed",
        "1080000",
        "--checkpoint-root",
        str(tmp_path),
    ]
    cli = CliRunner().invoke(app, args)
    assert cli.exit_code == 0, cli.output
    report = json.loads(cli.stdout)
    assert Path(report["checkpoint"]).is_dir()
    assert report["training"]["imitation"]["config"]["seed"] == 1080000
    assert not report["training"]["promotion_eligible"]
    args[args.index("1080000")] = "1070000"
    cli = CliRunner().invoke(app, args)
    assert cli.exit_code == 1 and "disjoint" in cli.output


@pytest.mark.parametrize("teams", [(0, 0, 0), (1, 1, 2, 2), (1, 1, 2, 2, 3, 3, 4, 4, 0)])
def test_multiplayer_warmup_and_terminal_ppo_share_the_native_roster(teams):
    config = FullGameTrainingConfig(
        batch_size=2,
        player_count=len(teams),
        teams=teams,
        updates=1,
        seed=1110000,
        ppo=FullGamePpoConfig(epochs=1),
    )
    run = run_full_game_training(
        **PATHS, config=config, imitation=FullGameImitationConfig(batches=1, epochs=1, seed=1120000)
    )
    assert run.report.imitation.environment.initial_teams == teams
    assert sum(run.report.imitation.updates[0].demonstration.outcomes[:2]) == 2
    assert run.report.updates[0].collection_error is None
    assert run.report.updates[0].metrics is not None
    assert not run.report.promotion_eligible
