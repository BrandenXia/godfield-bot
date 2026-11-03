"""Independent near-cap oracles, diagnostic gates, compatibility and offline CLI."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import tickets
from typer.testing import CliRunner

from godfield_bot.full_game_resource_smoke import (
    FullGameResourceSmokeReport,
    run_full_game_resource_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_resource_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


@pytest.mark.parametrize(
    "cap,metadata,replay",
    [
        (
            99,
            "ee03885c80f2fd08ea13a06c3c8a9948557e1b73662e89901b36321e464a8da2",
            "1cdad7b41739b6154e4d4fbb7dd0bc0a09251ecd8e8cd08dbafb61672b4402f7",
        ),
        (
            100,
            "9bf4cae76ca997597281357d28f6f3322cf61f67a3dd1bfea09683180e22a33b",
            "00adac17bb640fef2713c267ed1220141df9fc5ce07e494cf86de7a5c8b169dc",
        ),
    ],
)
def test_default_probes_pin_cap_dependent_replays_without_claiming_full_games(
    cap, metadata, replay
):
    r = probe(resource_cap=cap)
    assert r == probe(resource_cap=cap)
    assert r.metadata_sha256 == metadata and r.diagnostic_replay_sha256 == replay
    assert r.commands == 8192 and r.original_owner_ticks == 4096
    assert r.sun_revivals_by_scenario == (0, 0, 0, 31, 0, 39)
    assert r.cp_credited == 683 * (cap - 98)
    assert not r.full_game_training_ready and r.full_games_completed == 0


@pytest.mark.parametrize("cap", [99, 100])
@pytest.mark.parametrize("size", [1, 2, 5, 6, 7, 32, 256])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_keep_exact_scenario_counts_and_one_tick(size, players, cap):
    r = probe(batch_size=size, player_count=players, resource_cap=cap)
    assert r == FullGameResourceSmokeReport.model_validate_json(r.model_dump_json())
    assert sum(r.scenario_counts) == size


@pytest.mark.parametrize("seed", [0, 1, 67, 68, 999, 2**64 - 1])
def test_heaven_revivals_match_the_independent_illness_stream(seed):
    r = probe(batch_size=256, player_count=9, seed=seed)
    expected = [0] * 6
    for env in range(256):
        if env % 6 in (3, 5) and next(tickets(seed, env, 0)) % 100 < 5:
            expected[env % 6] += 1
    assert r.sun_revivals_by_scenario == tuple(expected)


@pytest.mark.parametrize("case", range(6))
@pytest.mark.parametrize("column", range(3))
def test_each_resource_total_fails_closed_on_corruption(case, column):
    payload = probe(batch_size=32).model_dump(mode="json")
    payload["final_resource_totals"][case][column] += 1
    with pytest.raises(ValidationError):
        FullGameResourceSmokeReport.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"resource_cap": 98},
        {"resource_cap": 100},
        {"scenarios": ()},
        {"scenario_counts": ()},
        {"sun_revivals_by_scenario": ()},
        {"sun_revivals_by_scenario": (1, 0, 0, 0, 0, 0)},
        {"final_resource_totals": ()},
        {"commands": 0},
        {"original_owner_ticks": 0},
        {"consumed_cards": 0},
        {"utilities": 0},
        {"miracle_uses": 0},
        {"mp_spent": 0},
        {"cp_credited": 0},
        {"exchange_commits": 0},
        {"exchange_hp_to_mp": 0},
        {"revived_hp": 999},
        {"resource_bound_violations": 1},
        {"pending_families": 1},
        {"other_owner_ticks": 1},
        {"limit_truncations": 1},
        {"real_terminal_endings": 1},
        {"automatic_gifts": 1},
        {"full_games_completed": 1},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"private_ticket": 1},
    ],
)
def test_forged_counts_scope_and_readiness_are_rejected(change):
    with pytest.raises(ValidationError):
        FullGameResourceSmokeReport.model_validate(probe(batch_size=32).model_dump() | change)


@pytest.mark.parametrize("size", [True, 0, -1, 4097])
def test_invalid_batch_size_fails_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize("cap", [0, 98, 101, True])
def test_invalid_cap_does_not_fall_back_to_legacy(cap):
    with pytest.raises(ValueError):
        probe(batch_size=1, resource_cap=cap)


@pytest.mark.parametrize("cap", [99, 100])
def test_cli_defaults99_and_explicit100_roundtrip(monkeypatch, cap):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    args = ["simulation", "full-game-resource-smoke", "--batch-size", "32", "--players", "9"]
    if cap == 100:
        args += ["--resource-cap", "100"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert FullGameResourceSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=32, player_count=9, resource_cap=cap
    )


@pytest.mark.parametrize("cap", [98, 101])
def test_cli_rejects_unknown_caps(monkeypatch, cap):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app, ["simulation", "full-game-resource-smoke", "--resource-cap", str(cap)]
    )
    assert result.exit_code == 2
