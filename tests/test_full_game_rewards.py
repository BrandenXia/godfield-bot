"""Actual endings, explicit one-shot credit and no synthetic truncated losses."""

import gc
import itertools
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import game, hand, ids, load, step
from test_full_game_teams import teams

from godfield_bot.full_game import create_development_full_game_batch
from godfield_bot.full_game_episode_probe import (
    BoundedPublicRandomPolicy,
    FullGameEpisodeProbeReport,
    run_full_game_episode_probe,
)
from godfield_bot.full_game_rewards import FullGameRewardAdapter, FullGameRewardMetadata
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")


def configured(*, size=1, players=3, **options):
    return create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=size,
        player_count=players,
        capacity=18,
        **options,
    )


def commands(b, choices, envs=None):
    if envs is None:
        envs = range(len(choices))
    rows = b.episode_snapshot()
    return ids(
        [[env, *rows[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
    ).reshape(-1, 6)


@pytest.mark.parametrize("layout", tuple(itertools.product(range(5), repeat=3)))
@pytest.mark.parametrize("winner", [0, 1, 2])
def test_native_terminal_mapping_includes_every_dead_teammate_without_normalization(layout, winner):
    b = game(teams_enabled=True)
    teams(b, layout)
    for seat in range(3):
        load(b, owner=seat, hp=40 if seat == winner else 0, mask=0)
    assert not b.terminal_reward_masks().any()
    b.start_environments(ids([0]))
    expected = [
        1 if s == winner or (layout[winner] and layout[s] == layout[winner]) else -1
        for s in range(3)
    ]
    assert b.terminal_rewards().tolist() == [expected + [0] * 6]
    assert b.terminal_reward_masks().tolist() == [[True] * 3 + [False] * 6]
    before = b.episode_snapshot().copy()
    np.testing.assert_array_equal(b.terminal_rewards(), b.terminal_rewards())
    np.testing.assert_array_equal(before, b.episode_snapshot())
    assert native.FULL_GAME_REWARD_SCHEMA_VERSION == 1
    assert native.FULL_GAME_KERNEL_SCHEMA_VERSION == 32


@pytest.mark.parametrize("players", range(2, 10))
def test_native_draw_has_valid_zero_values_for_all_present_seats(players):
    b = game(players=players)
    for seat in range(players):
        load(b, owner=seat, hp=0, mask=0)
    b.start_environments(ids([0]))
    assert not b.terminal_rewards().any()
    assert b.terminal_reward_masks()[0].tolist() == [True] * players + [False] * (9 - players)


def test_mixed_native_terminal_draw_active_and_truncated_rows_keep_separate_masks():
    b = game(size=4, teams_enabled=True, max_decisions=1)
    teams(b, [1, 1, 2])
    for seat in range(3):
        load(b, env=0, owner=seat, hp=40 if seat == 0 else 0, mask=0)
        load(b, env=1, owner=seat, hp=0, mask=0)
    b.start_environments(ids(range(4)))
    step(b, [0], [3])
    assert b.episode_snapshot()[:, 3].tolist() == [12, 12, 1, 13]
    assert b.terminal_reward_masks().tolist() == [[True] * 3 + [False] * 6] * 2 + [[False] * 9] * 2
    values, masks = b.terminal_rewards(), b.terminal_reward_masks()
    assert values.tolist() == [[1, 1, -1] + [0] * 6, [0] * 9, [0] * 9, [0] * 9]
    assert not values.flags.writeable and not masks.flags.writeable
    b.reset_environments(ids([0]))
    assert values[0, 0] == 1 and not b.terminal_rewards()[0].any()
    del b
    gc.collect()
    assert masks[0, 0] and values[0, 2] == -1


def test_adapter_emits_each_epoch_once_and_requires_collection_before_reset():
    c = configured(teams=(1, 1, 2))
    b = c.batch
    adapter = FullGameRewardAdapter(c)
    for epoch in (1, 2):
        teams(b, [1, 1, 2])
        for seat in range(3):
            load(b, owner=seat, hp=40 if seat == 0 else 0, mask=0)
        b.start_environments(ids([0]))
        with pytest.raises(ValueError, match="collect"):
            adapter.reset_environments(ids([0]))
        payoff = adapter.poll()
        assert payoff.epochs.tolist() == [epoch]
        assert payoff.values[0, :3].tolist() == [1, 1, -1]
        assert payoff.valid[0, :3].all() and payoff.terminated[0]
        assert all(
            not array.flags.writeable
            for array in (
                payoff.epochs,
                payoff.decisions,
                payoff.values,
                payoff.valid,
                payoff.terminated,
                payoff.truncated,
            )
        )
        repeat = adapter.poll()
        assert repeat.terminated[0] and not repeat.valid.any() and not repeat.values.any()
        adapter.reset_environments(ids([0]))
        assert b.team_ids()[0, :3].tolist() == [0, 0, 0]
        assert not adapter.poll().valid.any()
        assert payoff.values[0, 0] == 1


def test_adapter_preserves_true_zero_draw_and_invalid_zero_truncation():
    draw = configured(players=2)
    adapter = FullGameRewardAdapter(draw)
    for seat in range(2):
        load(draw.batch, owner=seat, hp=0, mask=0)
    draw.batch.start_environments(ids([0]))
    payoff = adapter.poll()
    assert not payoff.values.any() and payoff.valid[0, :2].all() and payoff.terminated[0]

    c = configured(players=2, max_turns=1)
    c.batch.start_environments(ids([0]))
    adapter = FullGameRewardAdapter(c)
    result = adapter.step(commands(c.batch, [0]))
    assert result.actors.tolist() == [0] and result.policy_gradient_masks.tolist() == [[True]]
    assert not result.rewards.valid.any() and not result.rewards.values.any()
    assert result.rewards.truncated[0] and not result.rewards.terminated[0]
    adapter.reset_environments(ids([0]))
    assert c.batch.episode_snapshot()[0, 0] == 2


def test_forced_turn_has_zero_policy_weight_but_retains_its_true_outcome():
    c = configured(players=2, max_turns=1, max_decisions=1)
    b = c.batch
    load(b, hp=1, illness=1, mask=0)
    b.seed_confusion(ids([0]), ids([0]), ids([1]))
    b.start_environments(ids([0]))
    adapter = FullGameRewardAdapter(c)
    result = adapter.step(commands(b, [0]))
    assert result.actors.tolist() == [0] and not result.policy_gradient_masks.any()
    assert result.rewards.values[0, :2].tolist() == [-1, 1]
    assert result.rewards.valid[0, :2].all()
    assert not b.policy_gradient_masks().any()


@pytest.mark.parametrize("players", [2, 4])
def test_reward_waits_for_post_death_bows_and_preserves_real_draw_or_dead_team_credit(players):
    c = configured(players=players, teams=(1, 1, 2, 2) if players == 4 else None)
    b = c.batch
    victim = 2 if players == 4 else 1
    hand(b, [35])
    hand(b, [112], owner=victim)
    load(b, hp=40 if players == 4 else 10, mask=8)
    load(b, owner=victim, hp=5, mask=8)
    if players == 4:
        load(b, owner=1, hp=10, mask=8)
        load(b, owner=3, hp=0, mask=0)
    b.start_environments(ids([0]))
    adapter = FullGameRewardAdapter(c)
    for choice in (1, 0, 19 + victim, 0):
        result = adapter.step(commands(b, [choice]))
        assert not result.rewards.valid.any()
    assert b.episode_snapshot()[0, 3] == 4
    result = adapter.step(commands(b, [0]))
    if players == 4:
        assert not result.rewards.valid.any()
        result = adapter.step(commands(b, [0]))
        assert result.rewards.values[0, :4].tolist() == [1, 1, -1, -1]
        assert b.diagnostic_players()[0, 1, 0] == 0
    else:
        assert not result.rewards.values.any() and b.episode_snapshot()[0, 5] == 2
    assert result.rewards.valid[0, :players].all()
    assert result.rewards.terminated[0] and not result.rewards.truncated[0]


def test_partial_steps_do_not_invent_other_actors_or_policy_samples():
    c = configured(size=2)
    b = c.batch
    b.start_environments(ids([0, 1]))
    adapter = FullGameRewardAdapter(c)
    result = adapter.step(commands(b, [0], [1]))
    assert result.actors.tolist() == [-1, 0]
    assert result.policy_gradient_masks.tolist() == [[False], [True]]
    assert result.commands[:, 0].tolist() == [1]
    assert not result.commands.flags.writeable and not result.actors.flags.writeable
    assert not result.rewards.valid.any()


def test_hidden_unaffordable_batch_never_appends_a_rejected_action_or_credit():
    c = configured(size=2, initial_mp=6)
    b = c.batch
    for env, actual in enumerate((231, 235)):
        hand(b, [(actual, 228, 0)], env=env)
    b.start_environments(ids([0, 1]))
    adapter = FullGameRewardAdapter(c)
    adapter.step(commands(b, [1, 1]))
    before = b.episode_snapshot().copy(), b.diagnostic_inventory().copy()
    with pytest.raises(ValueError, match="unaffordable"):
        adapter.step(commands(b, [0, 0]))
    np.testing.assert_array_equal(before[0], b.episode_snapshot())
    np.testing.assert_array_equal(before[1], b.diagnostic_inventory())
    assert not adapter.poll().valid.any()
    result = adapter.step(commands(b, [0], [0]))
    assert result.commands[:, 0].tolist() == [0] and not result.rewards.valid.any()


@pytest.mark.parametrize("bypass", ["step", "reset"])
def test_untracked_native_steps_or_resets_fail_closed(bypass):
    c = configured()
    b = c.batch
    adapter = FullGameRewardAdapter(c)
    if bypass == "step":
        b.start_environments(ids([0]))
        step(b, [0])
    else:
        b.reset_environments(ids([0]))
    with pytest.raises(RuntimeError, match="untracked"):
        adapter.poll()


def test_active_reset_and_late_bad_command_leave_native_and_credit_cursor_unchanged():
    c = configured(size=2)
    b = c.batch
    b.start_environments(ids([0, 1]))
    adapter = FullGameRewardAdapter(c)
    before = b.episode_snapshot().copy()
    with pytest.raises(ValueError, match="active"):
        adapter.reset_environments(ids([0]))
    batch = commands(b, [0, 0])
    batch[1, 2] += 1
    with pytest.raises(ValueError, match="stale"):
        adapter.step(batch)
    np.testing.assert_array_equal(before, b.episode_snapshot())
    assert not adapter.poll().valid.any()


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"reward_schema_version": 2},
        {"shaping": "hp"},
        {"promotion_eligible": True},
        {"full_game_training_ready": True},
    ],
)
def test_reward_metadata_cannot_change_contract_or_claim_complete_training(change):
    metadata = FullGameRewardAdapter(configured()).metadata
    with pytest.raises(ValidationError):
        FullGameRewardMetadata.model_validate(metadata.model_dump() | change)


@pytest.mark.parametrize(
    "method,kind",
    [
        ("terminal_rewards", "shape"),
        ("terminal_rewards", "wrong-value"),
        ("terminal_reward_masks", "false-mask"),
        ("winning_seats", "false-mask"),
        ("team_ids", "bad-team"),
    ],
)
def test_corrupt_native_read_cannot_consume_credit_or_relabel_an_ending(monkeypatch, method, kind):
    c = configured(teams=(1, 1, 2))
    b = c.batch
    adapter = FullGameRewardAdapter(c)
    for seat in range(3):
        load(b, owner=seat, hp=40 if seat == 0 else 0, mask=0)
    b.start_environments(ids([0]))
    original = getattr(native.FullGameBatch, method)

    def corrupted(batch):
        array = original(batch).copy()
        if kind == "shape":
            return array[:, :8]
        if kind in ("wrong-value", "false-mask"):
            array[0, 0] = 0
        elif kind == "bad-team":
            array[0, 0] = 5
        return array

    with monkeypatch.context() as context:
        context.setattr(native.FullGameBatch, method, corrupted)
        with pytest.raises(RuntimeError, match="differs"):
            adapter.poll()
    valid = adapter.poll()
    assert valid.valid[0, :3].all() and valid.values[0, :3].tolist() == [1, 1, -1]
    assert not adapter.poll().valid.any()


@pytest.mark.parametrize(
    "batch",
    [
        np.zeros((1, 6), dtype=np.float64),
        np.zeros((1, 6), dtype=np.bool_),
        np.zeros((1, 5), dtype=np.int64),
        np.zeros((2, 6), dtype=np.int64),
        np.zeros((1, 12), dtype=np.int64)[:, ::2],
    ],
)
def test_command_interface_does_not_coerce_or_accept_bad_layouts(batch):
    c = configured()
    c.batch.start_environments(ids([0]))
    adapter = FullGameRewardAdapter(c)
    before = c.batch.episode_snapshot().copy()
    with pytest.raises(ValueError):
        adapter.step(batch)
    np.testing.assert_array_equal(before, c.batch.episode_snapshot())
    assert not adapter.poll().valid.any()


def test_exported_reward_version_is_explicit_without_changing_gameplay_schema():
    assert "FULL_GAME_REWARD_SCHEMA_VERSION" in native.__all__
    assert native.FULL_GAME_REWARD_SCHEMA_VERSION == 1
    assert native.FULL_GAME_RULESET_ID == "integrated-full-game-development-v32"


@pytest.mark.parametrize("schema", [None, True, 0, 2, "1"])
def test_adapter_rejects_missing_or_incompatible_native_reward_schema(monkeypatch, schema):
    c = configured()
    monkeypatch.setattr(native, "FULL_GAME_REWARD_SCHEMA_VERSION", schema)
    with pytest.raises(ProvisionalRuleUnavailableError, match="reward interface"):
        FullGameRewardAdapter(c)


def test_public_only_complete_pool_episodes_pay_each_participant_once():
    c = configured(
        size=4,
        players=4,
        teams=(1, 1, 2, 2),
        acquisition_mode="all-held-weighted",
        max_turns=256,
        max_decisions=2048,
        apocalypse_after_turns=64,
    )
    b = c.batch
    adapter = FullGameRewardAdapter(c)
    b.start_environments(ids(range(4)))
    policy = BoundedPublicRandomPolicy(4, 901)
    seen = np.zeros((4, 9), dtype=np.int64)
    for _ in range(2048):
        state, masks = b.episode_snapshot(), b.choice_masks()
        active = np.flatnonzero(~np.isin(state[:, 3], (12, 13)))
        if not len(active):
            break
        batch = ids(
            [
                [env, *state[env, :4], policy.choose(int(env), state[env], masks[env])]
                for env in active
            ]
        )
        result = adapter.step(batch)
        seen += result.rewards.valid.astype(np.int64)
        for env in np.flatnonzero(result.rewards.valid.any(axis=1)):
            expected = np.where(b.winning_seats()[env, :4], 1, -1)
            np.testing.assert_array_equal(result.rewards.values[env, :4], expected)
    assert (b.episode_snapshot()[:, 3] == 12).all()
    assert seen.tolist() == [[1] * 4 + [0] * 5] * 4
    assert not adapter.poll().valid.any()
    assert not adapter.metadata.local_training_eligible


def reward_probe(**options):
    return run_full_game_episode_probe(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


@pytest.mark.parametrize(
    "players,layout,seed",
    [(2, (0, 0), 0), (4, (1, 1, 2, 2), 67), (9, (1, 2, 3, 4, 1, 2, 3, 4, 0), 67)],
)
def test_opt_in_credit_probe_preserves_all_gameplay_and_excludes_error_epochs(
    players, layout, seed
):
    options = dict(batch_size=32, player_count=players, teams=layout, seed=seed)
    native_report = reward_probe(**options)
    rewarded = reward_probe(**options, terminal_rewards=True)
    assert rewarded.outcomes == native_report.outcomes
    assert rewarded.diagnostic_replay_sha256 == native_report.diagnostic_replay_sha256
    assert rewarded.metadata_sha256 == native_report.metadata_sha256
    assert rewarded.accepted_commands == native_report.accepted_commands
    assert rewarded.terminal_reward_valid_counts == (rewarded.games_completed,) * players + (0,) * (
        9 - players
    )
    assert not rewarded.teacher_or_reward_dataset_eligible
    assert rewarded == FullGameEpisodeProbeReport.model_validate_json(rewarded.model_dump_json())
    if seed == 0:
        assert rewarded.engine_errors == 1 and rewarded.games_completed == 31


def test_rewarded_zero_command_faction_and_truncations_do_not_invent_policy_samples():
    ended = reward_probe(batch_size=2, player_count=3, teams=(1, 1, 1), terminal_rewards=True)
    assert ended.accepted_commands == 0
    assert ended.terminal_reward_totals == (2, 2, 2, 0, 0, 0, 0, 0, 0)
    assert ended.terminal_reward_valid_counts == (2, 2, 2, 0, 0, 0, 0, 0, 0)
    truncated = reward_probe(batch_size=2, max_decisions=1, terminal_rewards=True)
    assert truncated.decision_limit_games == 2
    assert truncated.terminal_reward_totals == truncated.terminal_reward_valid_counts == (0,) * 9
    untracked = reward_probe(batch_size=1, max_decisions=1)
    assert untracked.terminal_reward_totals is untracked.terminal_reward_valid_counts is None


@pytest.mark.parametrize(
    "change",
    [
        {"reward_schema_version": True},
        {"reward_schema_version": 2},
        {"reward_metadata_sha256": "0" * 64},
        {"terminal_reward_totals": (0,) * 9},
        {"terminal_reward_valid_counts": (0,) * 9},
        {"terminal_rewards_tracked": False},
    ],
)
def test_reward_probe_counts_and_contract_cannot_be_forged(change):
    report = reward_probe(batch_size=1, player_count=2, teams=(1, 1), terminal_rewards=True)
    with pytest.raises(ValidationError):
        FullGameEpisodeProbeReport.model_validate(report.model_dump() | change)


def test_cli_reward_tracking_is_opt_in_and_does_not_change_logging_for_later_training(monkeypatch):
    import structlog
    from typer.testing import CliRunner

    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    factory = structlog.get_config()["logger_factory"]
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-episode-probe",
            "--players",
            "2",
            "--teams",
            "1,1",
            "--batch-size",
            "1",
            "--terminal-rewards",
        ],
    )
    assert result.exit_code == 0, result.output
    report = FullGameEpisodeProbeReport.model_validate_json(result.output)
    assert report.terminal_rewards_tracked and report.reward_schema_version == 1
    assert report.terminal_reward_totals == (1, 1, 0, 0, 0, 0, 0, 0, 0)
    assert structlog.get_config()["logger_factory"] is factory
