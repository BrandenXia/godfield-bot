"""Source-pinned frozen opponents, private memories and learner-only policy loss."""

import hashlib
import json
import shutil
import stat
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from structlog.testing import capture_logs
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.guardian_league import (  # noqa: E402
    FrozenGuardianLeague,
    GuardianLeagueController,
    GuardianLeagueCounts,
    GuardianLeagueMember,
    GuardianLeagueSnapshot,
    create_guardian_league,
    guardian_arena_contract,
    load_guardian_league,
)
from godfield_bot.guardian_rollout import (  # noqa: E402
    GuardianRolloutArena,
    GuardianRolloutConfig,
)
from godfield_bot.guardian_training import (  # noqa: E402
    LEAGUE_ALGORITHM,
    MANIFEST_FILE,
    WEIGHTS_FILE,
    GuardianArenaManifest,
    GuardianDuelCollector,
    GuardianEvaluation,
    GuardianLeagueEvaluation,
    GuardianTrainingConfig,
    GuardianTrainingError,
    GuardianTrainingExposureReport,
    _runtime,
    evaluate_guardian_checkpoint,
    evaluate_guardian_league_checkpoint,
    load_guardian_checkpoint,
    replay_guardian_rollout,
    report_guardian_training_exposure,
    train_guardian_candidate,
    train_guardian_ppo,
)
from godfield_bot.model_registry import load_model  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def config(kind="discard", *, seed=67, league=False, **updates):
    utility = kind != "old"
    discard = kind == "discard"
    return GuardianTrainingConfig.model_validate(
        {
            "arena": GuardianRolloutConfig(
                batch_size=4,
                seed=seed,
                max_turns=8,
                max_decisions=32,
                inventory_utilities=utility,
                inventory_discards=discard,
                refill="weighted-discard-consumption-v1"
                if discard
                else "weighted-utility-consumption-v1"
                if utility
                else "none",
            ),
            "rollout_steps": 16,
            "updates": 1,
            "teacher_updates": 0,
            "ppo_epochs": 1,
            "environment_minibatch_size": 4,
            "evaluation_games": 4,
            "hidden_size": 32,
            "embedding_size": 8,
            "cpu_threads": 1,
            "opponent_mode": "frozen-guardian-league-v1" if league else "greedy-selfplay-v1",
            **updates,
        }
    )


def train(root, cfg, **kwargs):
    with capture_logs():
        return train_guardian_candidate(
            catalog_path=CATALOG, bible_path=BIBLE, checkpoint_root=root, config=cfg, **kwargs
        )


def arena(cfg):
    return GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena)


def sources(directory):
    return tuple(
        hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in (MANIFEST_FILE, WEIGHTS_FILE)
    )


@pytest.fixture(scope="module")
def checkpoints(tmp_path_factory):
    root = tmp_path_factory.mktemp("guardian-frozen-league")
    cache = {}

    def get(kind="discard"):
        if kind not in cache:
            reference, manifest = train(root, config(kind))
            peer, _ = train(root, config(kind, seed=73))
            path, snapshot = create_guardian_league(
                reference_checkpoint=reference,
                opponent_checkpoints=(peer,),
                catalog_path=CATALOG,
                bible_path=BIBLE,
                league_directory=root / "rosters",
            )
            cache[kind] = reference, peer, manifest, path, snapshot
        return cache[kind]

    return get


def frozen(checkpoints, kind="discard", cfg=None):
    reference, _, manifest, path, snapshot = checkpoints(kind)
    cfg = cfg or config(kind, league=True)
    game = arena(cfg)
    league = load_guardian_league(path, reference=manifest, arena=game.metadata)
    _, model = load_guardian_checkpoint(reference)
    return cfg, game, league, model, snapshot


@pytest.mark.parametrize("kind", ["old", "utility", "discard"])
def test_verified_rosters_preserve_sources_rng_and_private_files(checkpoints, kind):
    reference, peer, manifest, path, snapshot = checkpoints(kind)
    original = sources(reference), sources(peer)
    torch.manual_seed(987)
    state = torch.get_rng_state().clone()
    target = arena(config(kind, seed=101, league=True))
    loaded = load_guardian_league(path, reference=manifest, arena=target.metadata)
    torch.testing.assert_close(torch.get_rng_state(), state)
    assert len(loaded.models) == 3 and loaded.models[0] is None
    assert all(
        not model.training and not any(p.requires_grad for p in model.parameters())
        for model in loaded.models[1:]
    )
    assert sources(reference) == original[0] and sources(peer) == original[1]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert snapshot.reference_model_id == manifest.model_id
    assert snapshot.sha256 == GuardianLeagueSnapshot.model_validate_json(path.read_text()).sha256
    assert not snapshot.promotion_eligible and not snapshot.full_game_training_ready


@pytest.mark.parametrize(
    "change", ["duplicate_id", "duplicate_weights", "wrong_greedy", "parent", "gate"]
)
def test_roster_rejects_false_identity_and_gate_claims(checkpoints, change):
    data = checkpoints()[4].model_dump(mode="json")
    if change == "duplicate_id":
        data["members"][2]["opponent_id"] = data["members"][1]["opponent_id"]
    elif change == "duplicate_weights":
        data["members"][2]["weights_sha256"] = data["members"][1]["weights_sha256"]
    elif change == "wrong_greedy":
        data["members"][0]["opponent_id"] = "greedy-smoke-baseline-v1"
    elif change == "parent":
        data["reference_weights_sha256"] = "0" * 64
    else:
        data["promotion_eligible"] = True
    with pytest.raises(ValueError):
        GuardianLeagueSnapshot.model_validate(data)


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "greedy", "opponent_id": "g", "weight": True},
        {"kind": "greedy", "opponent_id": "g", "weight": 0},
        {"kind": "greedy", "opponent_id": "g", "weights_sha256": "a" * 64},
        {"kind": "model", "opponent_id": "m"},
        {
            "kind": "model",
            "opponent_id": "m",
            "checkpoint_directory": "relative",
            "manifest_sha256": "a" * 64,
            "weights_sha256": "b" * 64,
        },
    ],
)
def test_member_sources_are_explicit_and_weights_bounded(bad):
    with pytest.raises(ValueError):
        GuardianLeagueMember.model_validate(bad)


def test_creation_is_rng_neutral_and_rejects_aliases_before_writing(checkpoints, tmp_path):
    reference, peer, _, _, _ = checkpoints()
    state = torch.get_rng_state().clone()
    kwargs = dict(
        reference_checkpoint=reference,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        league_directory=tmp_path / "rosters",
    )
    create_guardian_league(opponent_checkpoints=(peer,), **kwargs)
    torch.testing.assert_close(state, torch.get_rng_state())
    kwargs["league_directory"] = tmp_path / "invalid"
    with pytest.raises(ValueError, match="distinct"):
        create_guardian_league(opponent_checkpoints=(reference,), **kwargs)
    assert not kwargs["league_directory"].exists()


@pytest.mark.parametrize("change", ["parent", "horizon", "reward", "schema", "manifest", "weights"])
def test_load_rejects_contract_and_pinned_file_changes(checkpoints, tmp_path, change):
    reference, peer, manifest, path, snapshot = checkpoints()
    target = arena(config(league=True))
    data = snapshot.model_dump(mode="json")
    if change == "parent":
        manifest = load_guardian_checkpoint(peer)[0]
    elif change in ("horizon", "reward", "schema"):
        cfg = config("utility" if change == "schema" else "discard", league=True)
        if change != "schema":
            cfg = cfg.model_copy(
                update={
                    "arena": cfg.arena.model_copy(
                        update={"max_turns": 9} if change == "horizon" else {"shaping_weight": 0.2}
                    )
                }
            )
        target = arena(cfg)
    else:
        copied = tmp_path / "peer"
        shutil.copytree(peer, copied)
        data["members"][2]["checkpoint_directory"] = str(copied)
        if change == "manifest":
            source = json.loads((copied / MANIFEST_FILE).read_text())
            source["created_at"] = "2026-01-01T00:00:00Z"
            (copied / MANIFEST_FILE).write_text(json.dumps(source))
        else:
            with (copied / WEIGHTS_FILE).open("ab") as sink:
                sink.write(b"changed")
        path = tmp_path / "changed.json"
        path.write_text(json.dumps(data))
    with pytest.raises((ValueError, GuardianTrainingError)):
        load_guardian_league(path, reference=manifest, arena=target.metadata)
    assert reference.is_dir()


def test_episode_selection_is_fixed_deterministic_and_batch_independent(checkpoints):
    _, game, league, _, _ = frozen(checkpoints)
    first = GuardianLeagueController(league, batch_size=4, seed=67)
    second = GuardianLeagueController(league, batch_size=4, seed=67)
    small = GuardianLeagueController(league, batch_size=2, seed=67)
    state = torch.get_rng_state().clone()
    obs = game.observe()
    for episode in range(30):
        projected = replace(obs, episode_ids=np.full(4, episode, dtype=np.int64))
        assert len(first.begin(projected)) == 4
        assert len(first.begin(projected)) == 0
        second.begin(projected)
        small.begin(replace(projected, episode_ids=projected.episode_ids[:2]))
        np.testing.assert_array_equal(first.assignments, second.assignments)
        np.testing.assert_array_equal(first.assignments[:2], small.assignments)
        for env in range(4):
            expected = np.random.default_rng(np.random.SeedSequence([67, env, episode, 6774]))
            assert first.assignments[env] == expected.choice(3, p=[1 / 3] * 3)
    torch.testing.assert_close(state, torch.get_rng_state())
    assert game.replacement_gifts == 0


def test_private_opponent_memories_reset_only_changed_episode_and_own_actor(checkpoints):
    _, game, league, _, _ = frozen(checkpoints)
    controller = GuardianLeagueController(league, batch_size=4, seed=67)
    obs = game.observe()
    controller.begin(obs)
    controller.assignments[:] = 1
    seen = []
    hook = league.models[1].register_forward_pre_hook(
        lambda _, args, kwargs: seen.append((args, kwargs)), with_kwargs=True
    )
    actions = controller.actions(obs, np.asarray([1, 3], dtype=np.int64))
    hook.remove()
    np.testing.assert_array_equal(actions[[0, 2]], [-1, -1])
    assert obs.action_mask[[1, 3], actions[[1, 3]]].all()
    torch.testing.assert_close(seen[0][0][4], torch.from_numpy(obs.hand_features[[1, 3]].copy()))
    assert not seen[0][1]["recurrent_state"].any()
    for env in (1, 3):
        assert controller.memories[1][env, obs.actors[env]].abs().sum() > 0
        assert not controller.memories[1][env, 1 - obs.actors[env]].any()
    for memory in controller.memories[1:]:
        memory[:] = 7
    episodes = obs.episode_ids.copy()
    episodes[2] += 1
    controller.begin(replace(obs, episode_ids=episodes))
    for memory in controller.memories[1:]:
        assert not memory[2].any()
        assert torch.all(memory[[0, 1, 3]] == 7)


def test_controller_rejects_unassigned_inactive_stale_or_duplicate_rows(checkpoints):
    _, game, league, _, _ = frozen(checkpoints)
    controller = GuardianLeagueController(league, batch_size=4, seed=67)
    obs = game.observe()
    with pytest.raises(ValueError, match="assigned"):
        controller.actions(obs, np.asarray([0], dtype=np.int64))
    controller.begin(obs)
    for rows in ([0, 0], [-1], [4]):
        with pytest.raises(ValueError):
            controller.actions(obs, np.asarray(rows, dtype=np.int64))
    with pytest.raises(ValueError):
        controller.actions(replace(obs, active=np.zeros(4, dtype=np.bool_)), np.asarray([0]))
    with pytest.raises(ValueError):
        controller.actions(replace(obs, episode_ids=obs.episode_ids + 1), np.asarray([0]))


def test_collection_replays_counts_masks_and_frozen_sources_across_windows(checkpoints):
    cfg = config(league=True, defense_feedback_weight=1)
    with _runtime(100, 1):
        _, game, league, model, snapshot = frozen(checkpoints, cfg=cfg)
        initial = [None if peer is None else deepcopy(peer.state_dict()) for peer in league.models]
        collector = GuardianDuelCollector(game, model, league=league)
        for window in range(3):
            rollout = collector.collect(cfg)
            counts = rollout.league_statistics
            assert counts.league_sha256 == snapshot.sha256
            assert sum(counts.learner_decisions) == int(rollout.policy_trainable.sum())
            assert sum(counts.opponent_decisions) == int((~rollout.policy_trainable).sum())
            assert sum(counts.completed_games) == rollout.completed_games
            assert sum(counts.truncated_games) == rollout.truncated_games
            assert sum(counts.episode_starts) >= (4 if window == 0 else 0)
            assert rollout.policy_trainable.any() and (~rollout.policy_trainable).any()
            assert rollout.observations[6].gather(-1, rollout.actions[..., None]).all()
            logits, values = replay_guardian_rollout(model, rollout, torch.arange(4))
            distribution = torch.distributions.Categorical(logits=logits)
            torch.testing.assert_close(
                distribution.log_prob(rollout.actions), rollout.old_log_probabilities
            )
            torch.testing.assert_close(values, rollout.old_values)
            metrics = train_guardian_ppo(model, torch.optim.Adam(model.parameters()), rollout, cfg)
            expected = rollout.policy_trainable & (rollout.observations[0][..., 1] > 0)
            assert metrics.defense_teacher_samples == int(expected.sum())
        for peer, state in zip(league.models, initial, strict=True):
            if peer is not None:
                assert not any(p.requires_grad or p.grad is not None for p in peer.parameters())
                for key, value in peer.state_dict().items():
                    torch.testing.assert_close(value, state[key], rtol=0, atol=0)


def test_opponent_advantages_and_likelihoods_do_not_enter_policy_gradient(checkpoints):
    cfg = config(league=True, value_weight=0, entropy_weight=0)
    with _runtime(137, 1):
        _, game, league, model, _ = frozen(checkpoints, cfg=cfg)
        rollout = GuardianDuelCollector(game, model, league=league).collect(cfg)
        left, right = deepcopy(model), deepcopy(model)
        advantages = rollout.advantages.clone()
        probabilities = rollout.old_log_probabilities.clone()
        advantages[~rollout.policy_trainable] = 1e8
        probabilities[~rollout.policy_trainable] = -1e8
        changed = replace(rollout, advantages=advantages, old_log_probabilities=probabilities)
        torch.manual_seed(117)
        original = train_guardian_ppo(left, torch.optim.Adam(left.parameters()), rollout, cfg)
        torch.manual_seed(117)
        modified = train_guardian_ppo(right, torch.optim.Adam(right.parameters()), changed, cfg)
        assert original == modified
        for key in left.state_dict():
            torch.testing.assert_close(
                left.state_dict()[key], right.state_dict()[key], rtol=0, atol=0
            )


def test_collection_is_deterministic_and_alternates_only_the_learner_seat(checkpoints):
    cfg = config(league=True)
    windows = []
    for _ in range(2):
        with _runtime(167, 1):
            _, game, league, model, _ = frozen(checkpoints, cfg=cfg)
            collector = GuardianDuelCollector(game, model, league=league)
            first = collector.collect(cfg)
            second = collector.collect(cfg)
            windows.append((first, second))
    assert [w.digest for w in windows[0]] == [w.digest for w in windows[1]]
    assert [w.league_statistics for w in windows[0]] == [w.league_statistics for w in windows[1]]
    first = windows[0][0]
    episode_ids = first.starts.long().cumsum(0) - 1
    learner_seats = (torch.arange(4) + episode_ids) % 2
    torch.testing.assert_close(first.policy_trainable, first.actors == learner_seats)


def test_all_greedy_roster_schedule_preserves_legacy_one_learner_trajectory(
    checkpoints, monkeypatch
):
    cfg = config(league=True, defense_feedback_weight=1)
    legacy = config(baseline_opponent_fraction=1, defense_feedback_weight=1)
    reference = checkpoints()[0]
    with _runtime(197, 1):
        game = arena(legacy)
        _, model = load_guardian_checkpoint(reference)
        original = GuardianDuelCollector(game, model).collect(legacy)
    with _runtime(197, 1):
        _, game, league, model, _ = frozen(checkpoints, cfg=cfg)
        collector = GuardianDuelCollector(game, model, league=league)
        begin = collector.league.begin

        def force_greedy(observation):
            changed = begin(observation)
            collector.league.assignments[:] = 0
            return changed

        monkeypatch.setattr(collector.league, "begin", force_greedy)
        actual = collector.collect(cfg)
    for name in (
        "actions",
        "actors",
        "starts",
        "policy_trainable",
        "old_log_probabilities",
        "old_values",
        "rewards",
        "done",
        "advantages",
        "returns",
        "defense_teacher_actions",
    ):
        torch.testing.assert_close(getattr(original, name), getattr(actual, name), rtol=0, atol=0)
    for left, right in zip(original.observations, actual.observations, strict=True):
        torch.testing.assert_close(left, right, rtol=0, atol=0)
    assert actual.league_statistics.opponent_decisions[1:] == (0, 0)
    assert original.league_statistics is None and original.digest != actual.digest


def test_frozen_mode_rejects_learner_aliases_and_imitation(checkpoints):
    cfg, game, league, model, _ = frozen(checkpoints)
    with pytest.raises(GuardianTrainingError, match="aliasing"):
        GuardianDuelCollector(game, league.models[1], league=league)
    with pytest.raises(ValueError, match="gradient-frozen"):
        FrozenGuardianLeague(snapshot=league.snapshot, models=(None, model, league.models[2]))
    collector = GuardianDuelCollector(game, model, league=league)
    for bad in (cfg.model_copy(update={"opponent_mode": "greedy-selfplay-v1"}), cfg):
        with pytest.raises(GuardianTrainingError, match="mode"):
            collector.collect(bad, teacher=bad is cfg)


@pytest.mark.parametrize(
    "bad",
    [
        {"teacher_updates": 1},
        {"baseline_opponent_fraction": 1},
        {"updates": 0},
    ],
)
def test_league_configuration_rejects_inactive_or_conflicting_options(bad):
    with pytest.raises(ValueError):
        config(league=True, **bad)


def test_training_requires_exact_parent_and_no_implicit_migration(checkpoints, tmp_path):
    reference, peer, _, path, _ = checkpoints()
    for options in (
        {"league_path": path},
        {"resume": peer, "league_path": path},
        {"resume": reference},
        {"resume": reference, "league_path": path, "migrate_horizon_from": reference},
    ):
        with pytest.raises((ValueError, GuardianTrainingError)):
            train(tmp_path / "invalid", config(league=True), **options)
    assert not (tmp_path / "invalid").exists()


@pytest.fixture
def trained_league(checkpoints, tmp_path):
    reference, _, _, path, _ = checkpoints()
    return train(
        tmp_path / "child",
        config(league=True, defense_feedback_weight=1),
        resume=reference,
        league_path=path,
    )


def test_league_checkpoint_roundtrip_statistics_and_closed_gates(checkpoints, trained_league):
    directory, manifest = trained_league
    snapshot = checkpoints()[4]
    assert manifest.algorithm == LEAGUE_ALGORITHM and manifest.league_sha256 == snapshot.sha256
    assert manifest.league_snapshot == snapshot
    assert manifest.parent_weights_sha256 == snapshot.reference_weights_sha256
    loaded, _ = load_guardian_checkpoint(directory)
    assert loaded == manifest
    metric = manifest.update_metrics[0]
    counts = metric.league_statistics
    assert metric.learner_decisions == sum(counts.learner_decisions)
    assert metric.baseline_decisions == counts.opponent_decisions[0]
    assert metric.frozen_opponent_decisions == sum(counts.opponent_decisions[1:])
    assert not manifest.full_game_training_ready and not manifest.promotion_eligible
    with pytest.raises((OSError, ValueError)):
        load_model(directory)


def test_training_report_sums_verified_roster_counters_without_playing(trained_league):
    directory, manifest = trained_league
    state = torch.get_rng_state().clone()
    report = report_guardian_training_exposure(directory)
    torch.testing.assert_close(state, torch.get_rng_state())
    assert report.opponent_mode == "frozen-guardian-league-v1"
    assert report.league_sha256 == manifest.league_sha256
    assert report.league_statistics == manifest.update_metrics[0].league_statistics
    assert report.ppo.decisions == sum(report.league_statistics.learner_decisions) + sum(
        report.league_statistics.opponent_decisions
    )
    assert report.teacher.windows == 0
    data = report.model_dump(mode="json")
    data["league_statistics"]["learner_decisions"][0] += 1
    with pytest.raises(ValueError, match="complete PPO"):
        GuardianTrainingExposureReport.model_validate(data)


@pytest.mark.parametrize(
    "change", ["league_hash", "parent", "algorithm", "missing_counts", "learner", "opponents"]
)
def test_manifest_rejects_misaccounted_or_aliased_league_training(trained_league, change):
    data = trained_league[1].model_dump(mode="json")
    if change == "league_hash":
        data["league_sha256"] = "0" * 64
    elif change == "parent":
        data["parent_weights_sha256"] = "0" * 64
    elif change == "algorithm":
        data["algorithm"] = "provisional-guardian-duel-recurrent-imitation-ppo-v1"
    elif change == "missing_counts":
        data["update_metrics"][0]["league_statistics"] = None
    else:
        field = "learner_decisions" if change == "learner" else "opponent_decisions"
        data["update_metrics"][0]["league_statistics"][field][0] += 1
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)


def test_historical_checkpoint_without_new_fields_remains_unknown(checkpoints):
    data = checkpoints()[2].model_dump(mode="json")
    data.pop("league_snapshot")
    data.pop("league_sha256")
    data["training"].pop("opponent_mode")
    for metric in data["update_metrics"]:
        metric.pop("league_statistics")
        metric.pop("frozen_opponent_decisions")
    for name in ("evaluation_before", "evaluation_after", "evaluation_baseline"):
        if data.get(name):
            data[name].pop("opponent_model_id")
            data[name].pop("opponent_weights_sha256")
    restored = GuardianArenaManifest.model_validate(data)
    assert restored.league_snapshot is None
    assert restored.training.opponent_mode == "greedy-selfplay-v1"
    assert restored.update_metrics[0].frozen_opponent_decisions is None


def test_paired_neural_self_match_is_symmetric_readonly_and_identity_labeled(checkpoints):
    reference, _, manifest, _, _ = checkpoints()
    original = sources(reference)
    arguments = dict(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        games=8,
        seed=802,
        cpu_threads=1,
        opponent_checkpoint=reference,
    )
    result = evaluate_guardian_checkpoint(reference, **arguments)
    assert result.opponent == "frozen-guardian-neural-v1"
    assert result.opponent_model_id == manifest.model_id
    assert result.opponent_weights_sha256 == manifest.weights_sha256
    assert result.wins == result.losses
    assert result.wins_by_learner_seat[0] == result.losses_by_learner_seat[1]
    assert result == evaluate_guardian_checkpoint(reference, **arguments)
    assert sources(reference) == original


def test_neural_evaluation_rejects_incompatible_source_schema(checkpoints):
    with pytest.raises(GuardianTrainingError, match="architecture"):
        evaluate_guardian_checkpoint(
            checkpoints()[0],
            catalog_path=CATALOG,
            bible_path=BIBLE,
            games=4,
            seed=67,
            cpu_threads=1,
            opponent_checkpoint=checkpoints("utility")[0],
        )


def test_league_report_accounts_each_matchup_and_cannot_claim_promotion(
    checkpoints, trained_league
):
    reference, _, _, path, snapshot = checkpoints()
    arguments = dict(
        league_path=path, catalog_path=CATALOG, bible_path=BIBLE, games=4, seed=901, cpu_threads=1
    )
    result = evaluate_guardian_league_checkpoint(trained_league[0], **arguments)
    assert result.league == snapshot and len(result.matchups) == 3
    assert result.candidate_model_id == trained_league[1].model_id
    assert result.matchups[0].opponent == "greedy-discard-smoke-baseline-v3"
    assert result.matchups[1].opponent_model_id == snapshot.reference_model_id
    assert not result.promotion_eligible
    assert (
        evaluate_guardian_league_checkpoint(reference, **arguments).matchups[1].wins
        == evaluate_guardian_league_checkpoint(reference, **arguments).matchups[1].losses
    )
    for change in ("identity", "hash", "seed", "games", "gate", "policy"):
        data = result.model_dump(mode="json")
        if change == "identity":
            data["matchups"][1]["opponent_model_id"] = "unrelated"
        elif change == "hash":
            data["league_sha256"] = "0" * 64
        elif change == "seed":
            data["matchups"][0]["seed"] += 1
        elif change == "games":
            data["games_per_member"] += 2
        elif change == "gate":
            data["promotion_eligible"] = True
        else:
            data["matchups"][0]["policy_kind"] = "greedy-reference"
        with pytest.raises(ValueError):
            GuardianLeagueEvaluation.model_validate(data)


def test_child_resume_requires_new_roster_and_evaluation_cannot_swap_training_roster(
    checkpoints, trained_league, tmp_path
):
    reference, peer, _, path, _ = checkpoints()
    with pytest.raises(ValueError, match="parent"):
        train(tmp_path / "invalid", config(league=True), resume=trained_league[0], league_path=path)
    other, _ = create_guardian_league(
        reference_checkpoint=reference,
        opponent_checkpoints=(peer,),
        catalog_path=CATALOG,
        bible_path=BIBLE,
        league_directory=tmp_path / "rosters",
        greedy_weight=2,
    )
    with pytest.raises(GuardianTrainingError, match="training league"):
        evaluate_guardian_league_checkpoint(
            trained_league[0],
            league_path=other,
            catalog_path=CATALOG,
            bible_path=BIBLE,
            games=4,
            seed=901,
            cpu_threads=1,
        )
    new, snapshot = create_guardian_league(
        reference_checkpoint=trained_league[0],
        opponent_checkpoints=(peer,),
        catalog_path=CATALOG,
        bible_path=BIBLE,
        league_directory=tmp_path / "rosters",
    )
    child, manifest = train(
        tmp_path / "next", config(league=True), resume=trained_league[0], league_path=new
    )
    assert child.is_dir() and manifest.league_sha256 == snapshot.sha256
    assert manifest.parent_weights_sha256 == trained_league[1].weights_sha256


def test_neural_evaluation_labels_cannot_be_omitted_or_faked(checkpoints):
    original = checkpoints()[2].evaluation_after.model_dump(mode="json")
    for changes in (
        {"opponent": "frozen-guardian-neural-v1"},
        {"opponent_model_id": "fake"},
        {"opponent_weights_sha256": "0" * 64},
    ):
        with pytest.raises(ValueError):
            GuardianEvaluation.model_validate({**original, **changes})


@pytest.mark.parametrize("change", ["length", "negative", "boolean", "duplicate"])
def test_counter_deltas_are_strict_and_can_finish_preceding_window_episodes(change):
    data = dict(
        league_sha256="a" * 64,
        member_ids=["a", "b"],
        episode_starts=[0, 0],
        learner_decisions=[4, 4],
        opponent_decisions=[5, 5],
        completed_games=[1, 1],
        truncated_games=[0, 0],
    )
    assert sum(GuardianLeagueCounts.model_validate(data).completed_games) == 2
    if change == "length":
        data["episode_starts"] = [0]
    elif change == "negative":
        data["learner_decisions"][0] = -1
    elif change == "boolean":
        data["opponent_decisions"][0] = True
    else:
        data["member_ids"] = ["a", "a"]
    with pytest.raises(ValueError):
        GuardianLeagueCounts.model_validate(data)


def test_cli_create_train_evaluate_and_explicit_neural_opponent(checkpoints, tmp_path, monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    reference, peer, _, _, _ = checkpoints("old")
    runner = CliRunner()
    with capture_logs():
        created = runner.invoke(
            app,
            [
                "simulation",
                "guardian-create-league",
                "--reference-checkpoint",
                str(reference),
                "--opponent-checkpoint",
                str(peer),
                "--league-directory",
                str(tmp_path / "rosters"),
            ],
        )
    assert created.exit_code == 0, created.output
    roster = json.loads(created.output)
    with capture_logs():
        trained = runner.invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--resume",
                str(reference),
                "--league",
                roster["league_path"],
                "--teacher-updates",
                "0",
                "--checkpoint-root",
                str(tmp_path / "child"),
                "--batch-size",
                "4",
                "--max-turns",
                "8",
                "--max-decisions",
                "32",
                "--rollout-steps",
                "16",
                "--updates",
                "1",
                "--ppo-epochs",
                "1",
                "--evaluation-games",
                "4",
                "--hidden-size",
                "32",
                "--embedding-size",
                "8",
                "--cpu-threads",
                "1",
            ],
        )
    assert trained.exit_code == 0, trained.output
    child = json.loads(trained.output)
    assert child["manifest"]["algorithm"] == LEAGUE_ALGORITHM
    for command, extra in (
        ("guardian-evaluate", ["--opponent-checkpoint", str(peer)]),
        ("guardian-evaluate-league", ["--league", roster["league_path"]]),
    ):
        with capture_logs():
            evaluated = runner.invoke(
                app,
                [
                    "simulation",
                    command,
                    "--checkpoint",
                    child["checkpoint_directory"],
                    "--games",
                    "4",
                    "--seed",
                    "800",
                    "--cpu-threads",
                    "1",
                    *extra,
                ],
            )
        assert evaluated.exit_code == 0, evaluated.output
        result = json.loads(evaluated.output)
        if command == "guardian-evaluate":
            assert result["opponent_model_id"] == load_guardian_checkpoint(peer)[0].model_id
        else:
            assert result["league_sha256"] == roster["league_sha256"]
            assert not result["promotion_eligible"]


def test_contract_excludes_only_seed_and_batch_not_rules_or_horizons(checkpoints):
    cfg = config(league=True)
    changed = cfg.model_copy(
        update={"arena": cfg.arena.model_copy(update={"seed": 201, "batch_size": 6})}
    )
    assert guardian_arena_contract(arena(cfg).metadata) == guardian_arena_contract(
        arena(changed).metadata
    )
    original = checkpoints()[4]
    changed_snapshot = original.model_copy(update={"league_id": "another"})
    assert original.sha256 != changed_snapshot.sha256
