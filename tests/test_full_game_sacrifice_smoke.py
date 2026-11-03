"""Complete weighted replacements, event conservation, source pins and offline CLI."""

import bisect
import itertools
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import PLAN, tickets
from typer.testing import CliRunner

from godfield_bot.full_game_sacrifice_smoke import (
    FullGameSacrificeSmokeReport,
    run_full_game_sacrifice_smoke,
)

pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def probe(**options):
    return run_full_game_sacrifice_smoke(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        **options,
    )


def test_default_report_pins_all237_receipt_models_and_five_devils_without_claiming_matches():
    r = probe()
    assert r == probe()
    assert r.statistic_totals == (4096, 12288, 0, 4096, 12288, 4096, 12288, 12288, 0)
    assert r.commands == 24576 and r.observed_models == 237
    assert r.observed_devil_models == 5 and r.devil_totals[2] == 3027
    assert r.devil_removed_cards == 1234 and r.devil_hp_damage == 30850
    assert r.metadata_sha256 == "aca4765cb523eeb4d9f4fe08d3915cc0c7a0a3f0a7b444060767693c975ff21f"
    assert r.diagnostic_replay_sha256 == (
        "dd223f0a0cfef038cae1e0bbdf47600f1f551e3f1a129366b0c5ef7d59801a4e"
    )
    assert r.full_games_completed == 0 and not r.full_game_training_ready


@pytest.mark.parametrize("size", [1, 2, 32, 256])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_keep_actual_observed_counts_and_separate_preparation_turns(size, players):
    r = probe(batch_size=size, player_count=players)
    assert r == FullGameSacrificeSmokeReport.model_validate_json(r.model_dump_json())
    assert r.preparation_turns == r.sacrifice_turns == size
    assert r.automatic_gifts == 3 * size


@pytest.mark.parametrize("seed", [0, 1, 67, 68, 999, 2**64 - 1])
def test_receipt_histogram_matches_independent_pinned_weight_ticket_oracle(seed):
    size = 256
    r = probe(batch_size=size, seed=seed, player_count=9)
    expected = [0] * 237
    weights = PLAN.gifts.model_weights
    cumulative = list(itertools.accumulate(w for _, w in weights))
    assert cumulative[-1] == 500
    for env in range(size):
        stream = tickets(seed, env, 0xCA5A826395121157)
        for _ in range(3):
            model = weights[bisect.bisect_right(cumulative, next(stream) % 500)][0]
            expected[model - 3] += 1
    assert r.model_counts == tuple(expected)
    assert r == probe(batch_size=size, seed=seed, player_count=9)


@pytest.mark.parametrize("column", range(9))
def test_every_sacrifice_statistic_column_is_checked(column):
    payload = probe(batch_size=32).model_dump()
    changed = list(payload["statistic_totals"])
    changed[column] += 1
    payload["statistic_totals"] = changed
    with pytest.raises(ValidationError):
        FullGameSacrificeSmokeReport.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"model_counts": ()},
        {"model_ids": ()},
        {"observed_models": 0},
        {"statistic_fields": ()},
        {"devil_totals": ()},
        {"devil_fields": ()},
        {"devil_model_counts": ()},
        {"devil_model_ids": ()},
        {"observed_devil_models": 0},
        {"commands": 0},
        {"preparation_turns": 0},
        {"sacrifice_turns": 0},
        {"preparation_owner_ticks": 0},
        {"sacrifice_owner_ticks": 0},
        {"automatic_gifts": 0},
        {"remaining_owner_cards": 0},
        {"devil_removed_cards": 999},
        {"remaining_owner_hp": 0},
        {"remaining_owner_mp": 0},
        {"remaining_owner_cp": 0},
        {"devil_hp_damage": 0},
        {"family_enqueued": 0},
        {"family_resolved": 0},
        {"family_suppressed": 1},
        {"pending_families": 1},
        {"other_owner_ticks": 1},
        {"consumed_cards": 1},
        {"miracle_uses": 1},
        {"mp_spent": 1},
        {"original_attacks": 1},
        {"limit_truncations": 1},
        {"real_terminal_endings": 1},
        {"full_games_completed": 1},
        {"official_apocalypse_threshold_verified": True},
        {"official_sacrifice_cardinality_and_timing_verified": True},
        {"official_fidelity_verified": True},
        {"full_game_training_ready": True},
        {"local_training_eligible": True},
        {"teacher_or_reward_dataset_eligible": True},
        {"promotion_eligible": True},
        {"schema_version": 2},
        {"queue_schema_version": 9},
        {"private_ticket": 1},
    ],
)
def test_forged_counts_scope_and_readiness_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameSacrificeSmokeReport.model_validate(probe(batch_size=256).model_dump() | change)


@pytest.mark.parametrize("size", [True, 0, -1, 4097])
def test_invalid_batch_bounds_reject_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


def test_cli_preserves_provisional_and_nontraining_scope(monkeypatch):
    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        ["simulation", "full-game-sacrifice-smoke", "--batch-size", "32", "--players", "9"],
    )
    assert result.exit_code == 0, result.output
    assert FullGameSacrificeSmokeReport.model_validate(json.loads(result.output)) == probe(
        batch_size=32, player_count=9
    )
