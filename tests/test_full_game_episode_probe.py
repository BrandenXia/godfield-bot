"""Whole episodes, independent public policies and honest error/truncation reports."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.full_game_episode_probe import (
    BoundedPublicRandomPolicy,
    FullGameEpisodeProbeReport,
    FullGameEpisodeResult,
    run_full_game_episode_probe,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_episode_probe(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


@pytest.fixture(scope="module")
def report():
    return probe()


@pytest.fixture(scope="module")
def error_report():
    return probe(player_count=2, batch_size=32, seed=0)


def test_complete_pool_default_records_real_endings_and_remaining_errors_separately(report):
    assert report == probe()
    assert report.games_completed == report.winner_games == 64
    assert (
        report.engine_errors == 0
        and report.draws == report.turn_limit_games == report.decision_limit_games == 0
    )
    assert report.accepted_commands == 16015
    assert (
        report.metadata_sha256 == "2c0230e82480057661b7444af0d9e003cc2f657add6184d74599d315f88520d2"
    )
    assert (
        report.diagnostic_replay_sha256
        == "97f7aafe112bc0e4e906590cf17a4f3d2f4281b9b7f14f5e8e554096e23da826"
    )
    assert not any(r.error_reason for r in report.outcomes)
    assert report.hidden_targeting_totals == (2, 0, 2, 2)
    assert report.hidden_trade_totals == (3, 1, 1, 1, 1, 1, 1, 0, 2)
    assert report.ineffective_totals == (2, 0, 4, 1, 1, 6, 7, 1, 6, 1, 1, 2, 0, 2)
    assert not report.local_training_eligible and not report.full_game_training_ready
    assert report == FullGameEpisodeProbeReport.model_validate_json(report.model_dump_json())


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("size", [1, 2, 9])
@pytest.mark.parametrize("seed", [0, 67])
def test_bounded_partial_batches_account_for_every_environment(players, size, seed):
    r = probe(
        batch_size=size,
        player_count=players,
        seed=seed,
        max_turns=12,
        max_decisions=64,
        apocalypse_after_turns=4,
    )
    assert r == probe(
        batch_size=size,
        player_count=players,
        seed=seed,
        max_turns=12,
        max_decisions=64,
        apocalypse_after_turns=4,
    )
    assert r.games_completed + r.turn_limit_games + r.decision_limit_games + r.engine_errors == size
    assert r.accepted_commands <= size * 64 and all(row.winner < players for row in r.outcomes)


@pytest.mark.parametrize(
    "turns,decisions,status,commands", [(1, 100, "turn-limit", 6), (256, 1, "decision-limit", 1)]
)
def test_real_native_limits_are_not_recorded_as_draws_or_games_completed(
    turns, decisions, status, commands
):
    r = probe(batch_size=1, player_count=2, max_turns=turns, max_decisions=decisions)
    assert r.outcomes[0].status == status and r.accepted_commands == commands
    assert not r.games_completed and not r.draws and not r.engine_errors


def test_public_policy_is_environment_independent_bounded_and_has_no_hidden_inputs():
    first, second = BoundedPublicRandomPolicy(2, 901), BoundedPublicRandomPolicy(2, 901)
    row = np.asarray([1, 1, 0, 2, 0, 0, -1, 0, -1], dtype=np.int64)
    mask = np.asarray([True, True, True, False], dtype=np.bool_)
    for _ in range(10):
        first.choose(0, row, mask)
    assert [first.choose(1, row, mask) for _ in range(5)] == [
        second.choose(1, row, mask) for _ in range(5)
    ]
    policy = BoundedPublicRandomPolicy(1, 901)
    assert policy.choose(0, row, mask) in (0, 1, 2)
    assert policy.choose(0, row, mask) in (0, 1, 2)
    assert policy.choose(0, row, mask) == 0
    with pytest.raises(RuntimeError, match="no legal public"):
        policy.choose(0, row, np.zeros(4, dtype=np.bool_))


@pytest.mark.parametrize("mode", ["empty-error", "partial-mutation", "nonreproducing"])
def test_injected_failures_preserve_errors_or_fail_closed_on_broken_atomicity(monkeypatch, mode):
    import godfield_bot.full_game_episode_probe as module

    factory = module.create_development_full_game_batch

    class Wrapped:
        def __init__(self, batch):
            self.batch = batch

        def __getattr__(self, name):
            return getattr(self.batch, name)

        def step(self, commands):
            if mode == "nonreproducing" and len(commands) > 1:
                raise ValueError("batch only")
            if mode in ("empty-error", "partial-mutation") and 0 in commands[:, 0]:
                if mode == "partial-mutation":
                    self.batch.step(commands[:1])
                raise ValueError("")
            return self.batch.step(commands)

    def wrapped(**options):
        from godfield_bot.full_game import DevelopmentFullGameBatch

        configured = factory(**options)
        return DevelopmentFullGameBatch(Wrapped(configured.batch), configured.metadata)

    monkeypatch.setattr(module, "create_development_full_game_batch", wrapped)
    if mode == "empty-error":
        r = probe(batch_size=2, max_turns=1, max_decisions=100)
        assert r.outcomes[0].error_reason == "ValueError" and r.outcomes[0].accepted_commands == 0
        assert r.outcomes[1].status == "turn-limit"
    else:
        with pytest.raises(
            RuntimeError, match="mutated" if mode == "partial-mutation" else "did not reproduce"
        ):
            probe(batch_size=2, max_turns=1, max_decisions=100)


def test_failed_environment_never_changes_other_environment_policy_or_results(monkeypatch, report):
    import godfield_bot.full_game_episode_probe as module
    from godfield_bot.full_game import DevelopmentFullGameBatch

    factory = module.create_development_full_game_batch

    class Wrapped:
        def __init__(self, batch):
            self.batch = batch

        def __getattr__(self, name):
            return getattr(self.batch, name)

        def step(self, commands):
            if 0 in commands[:, 0]:
                raise ValueError("injected_environment_failure")
            self.batch.step(commands)

    def wrapped(**options):
        configured = factory(**options)
        return DevelopmentFullGameBatch(Wrapped(configured.batch), configured.metadata)

    monkeypatch.setattr(module, "create_development_full_game_batch", wrapped)
    r = probe()
    assert r.outcomes[0].status == "engine-error" and r.outcomes[0].accepted_commands == 0
    assert r.outcomes[1:] == report.outcomes[1:]


@pytest.mark.parametrize(
    "change",
    [
        {"games_completed": 1},
        {"winner_games": 1},
        {"draws": 6},
        {"engine_errors": 1},
        {"turn_limit_games": 1},
        {"decision_limit_games": 1},
        {"rejected_batches": 1},
        {"accepted_commands": 0},
        {"forced_commands": 999999},
        {"accepted_commands_by_phase": ()},
        {"hidden_targeting_fields": ()},
        {"hidden_targeting_totals": ()},
        {"hidden_trade_fields": ()},
        {"hidden_trade_totals": (0, 1, 0, 0, 0, 0, 0, 0, 0)},
        {"fingerprint_views": ()},
        {"resource_cap": 100},
        {"acquisition_mode": "manual"},
        {"schema_version": 1},
        {"schema_version": 2},
        {"hidden_removal_fields": ()},
        {"hidden_removal_totals": (0, 0, 1, 0, 1, 0, 0)},
        {"ineffective_fields": ()},
        {"ineffective_totals": (0,) * 14},
        {"ineffective_model_counts": (0,) * 237},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"error_recovery": "pass"},
        {"unknown": 1},
    ],
)
def test_report_cannot_hide_errors_change_scope_or_claim_training(report, change):
    with pytest.raises(ValidationError):
        FullGameEpisodeProbeReport.model_validate(report.model_dump() | change)


@pytest.mark.parametrize(
    "status,phase,outcome,winner",
    [
        ("winner", 12, 1, 0),
        ("draw", 12, 2, -1),
        ("turn-limit", 13, 3, -1),
        ("decision-limit", 13, 4, -1),
    ],
)
def test_result_contract_distinguishes_all_native_endings(status, phase, outcome, winner):
    row = FullGameEpisodeResult(
        environment=0,
        episode=1,
        decision=3,
        actor=0,
        native_phase=phase,
        native_outcome=outcome,
        winner=winner,
        completed_turns=1,
        accepted_commands=2,
        status=status,
    )
    assert row == FullGameEpisodeResult.model_validate_json(row.model_dump_json())
    for change in (
        {"accepted_commands": 3},
        {"native_phase": 1},
        {"native_outcome": 0},
        {"error_reason": "hidden"},
    ):
        with pytest.raises(ValidationError):
            FullGameEpisodeResult.model_validate(row.model_dump() | change)


@pytest.mark.parametrize("bad", [True, "1", 1.0, -1, 2**53])
@pytest.mark.parametrize("column", range(6))
def test_error_command_tokens_are_strict_bounded_and_preserve_the_failed_context(
    error_report, bad, column
):
    payload = next(row for row in error_report.outcomes if row.error_reason).model_dump()
    command = list(payload["error_command"])
    command[column] = bad
    payload["error_command"] = command
    with pytest.raises(ValidationError):
        FullGameEpisodeResult.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"batch_size": True},
        {"batch_size": 0},
        {"batch_size": 4097},
        {"player_count": 1},
        {"player_count": 10},
        {"seed": -1},
        {"seed": 2**64},
        {"policy_seed": True},
        {"policy_seed": -1},
        {"max_turns": 0},
        {"max_turns": 10001},
        {"max_decisions": 0},
        {"max_decisions": 40001},
        {"apocalypse_after_turns": 10001},
    ],
)
def test_invalid_configuration_fails_before_native_allocation(monkeypatch, change):
    import godfield_bot.full_game_episode_probe as module

    def forbidden(**_):
        raise AssertionError("must validate before allocation")

    monkeypatch.setattr(module, "create_development_full_game_batch", forbidden)
    with pytest.raises(ValueError):
        probe(**change)


@pytest.mark.parametrize("errors", [False, True])
def test_cli_returns_nonzero_for_engine_errors_but_keeps_structured_report(
    monkeypatch, report, error_report, errors
):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    args = ["simulation", "full-game-episode-probe"]
    expected = report
    if errors:
        args += ["--batch-size", "32", "--players", "2", "--seed", "0"]
        expected = error_report
    if not errors:
        args += [
            "--batch-size",
            "1",
            "--players",
            "2",
            "--max-turns",
            "1",
            "--max-decisions",
            "100",
        ]
        expected = probe(batch_size=1, player_count=2, max_turns=1, max_decisions=100)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == int(errors), result.output
    assert FullGameEpisodeProbeReport.model_validate(json.loads(result.output)) == expected
