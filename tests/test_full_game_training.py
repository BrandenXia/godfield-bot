"""Full-pool PPO, forced value-only updates and frozen evaluation."""

import json

import pytest
from typer.testing import CliRunner

torch = pytest.importorskip("torch")
pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load  # noqa: E402
from test_full_game_neural import biased  # noqa: E402
from test_full_game_observation import PATHS, configured  # noqa: E402
from test_full_game_rollout import terminal_team_setup  # noqa: E402

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.full_game_evaluation import evaluate_full_game_candidate  # noqa: E402
from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyController,
)
from godfield_bot.full_game_rollout import (  # noqa: E402
    collect_full_game_episodes,
    full_game_policy_sha256,
)
from godfield_bot.full_game_training import (  # noqa: E402
    FullGamePpoConfig,
    FullGameTrainingConfig,
    load_full_game_candidate,
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
