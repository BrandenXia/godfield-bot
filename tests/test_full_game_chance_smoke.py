"""Native chance probe is reproducible one-turn evidence, never a learning gate."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_chance_smoke import (
    FullGameChanceSmokeReport,
    run_full_game_chance_smoke,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def probe(**options):
    return run_full_game_chance_smoke(catalog_path=CATALOG, bible_path=BIBLE, **options)


def test_default_probe_covers_all_plain_chance_models_but_not_full_matches():
    report = probe()
    assert report == probe()
    assert report.observed_model_count == 21
    assert report.chance_casts == report.resolved_attacks == report.completed_turns == 504
    assert report.hits == 309 and report.misses == 195 and report.actions == 1317
    assert report.real_terminal_endings == 0 and report.ready_after_one_turn == 504
    assert report.hp_damage == 2783 and report.mp_spent == 1440
    assert report.consumed_cards == 360 and report.retained_miracle_uses == 144
    assert (
        report.metadata_sha256 == "160b6ece6d1875d802c7f0c3338954683341f88765fcf93312e7cb48a00ac367"
    )
    assert (
        report.diagnostic_replay_sha256
        == "b8351112be01aee9dba2c26b3a9dc9e864914eef72fe56027ab9de6b03d51103"
    )
    assert not report.local_training_eligible and not report.teacher_or_reward_dataset_eligible
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("size", [1, 21, 64])
def test_small_probes_keep_unobserved_models_and_partial_episode_accounting(players, size):
    report = probe(batch_size=size, player_count=players)
    assert report.observed_model_count == min(size, 21) and len(report.model_results) == 21
    assert report.chance_casts == size and report.hits + report.misses == size
    assert report.real_terminal_endings + report.ready_after_one_turn == size
    if players > 2:
        assert report.real_terminal_endings == 0
    assert FullGameChanceSmokeReport.model_validate_json(report.model_dump_json()) == report


@pytest.mark.parametrize("size", [True, 0, 4097, 1.5])
def test_probe_rejects_invalid_sizes_before_allocating(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"chance_casts": 1},
        {"hits": 999},
        {"misses": 0},
        {"actions": 0},
        {"completed_turns": 0},
        {"resolved_attacks": 0},
        {"observed_model_count": 21},
        {"model_results": ()},
        {"result_fields": ("caller_roll",)},
        {"chance_profile_sha256": "0" * 64},
        {"real_terminal_endings": 999},
        {"consumed_cards": 0},
        {"batch_size": True},
        {"ruleset_id": "integrated-full-game-development-v5"},
        {"teacher_or_reward_dataset_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
    ],
)
def test_report_rejects_forged_profile_accounting_or_training_admission(change):
    report = probe(batch_size=4)
    with pytest.raises(ValidationError):
        FullGameChanceSmokeReport.model_validate({**report.model_dump(), **change})


def test_chance_probe_never_selects_using_true_inventory_or_resource_diagnostics(monkeypatch):
    import godfield_bot.full_game_chance_smoke as smoke

    reference = probe(batch_size=64)
    factory = smoke.create_development_full_game_batch

    class Redacted:
        def __init__(self, batch):
            self.batch = batch

        def __getattr__(self, name):
            return getattr(self.batch, name)

        def diagnostic_inventory(self):
            return np.zeros_like(self.batch.diagnostic_inventory())

        def diagnostic_players(self):
            return np.zeros_like(self.batch.diagnostic_players())

    def redacted_factory(**options):
        configured = factory(**options)
        return replace(configured, batch=Redacted(configured.batch))

    monkeypatch.setattr(smoke, "create_development_full_game_batch", redacted_factory)
    redacted = probe(batch_size=64)
    assert reference.diagnostic_replay_sha256 != redacted.diagnostic_replay_sha256
    assert reference.model_dump(exclude={"diagnostic_replay_sha256"}) == redacted.model_dump(
        exclude={"diagnostic_replay_sha256"}
    )


def test_cli_returns_the_same_explicitly_offline_one_turn_report(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app, ["simulation", "full-game-chance-smoke", "--batch-size", "21", "--players", "3"]
    )
    assert result.exit_code == 0, result.output
    report = FullGameChanceSmokeReport.model_validate(json.loads(result.output))
    assert report == probe(batch_size=21, player_count=3)
