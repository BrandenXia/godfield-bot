"""Forced-hit effect evidence is reproducible, diagnostic-only and bounded."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.full_game_attack_effect_smoke import (
    FullGameAttackEffectSmokeReport,
    run_full_game_attack_effect_smoke,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def probe(**options):
    return run_full_game_attack_effect_smoke(catalog_path=CATALOG, bible_path=BIBLE, **options)


def test_default_probe_covers_all_20_effects_without_claiming_full_games():
    report = probe()
    assert report == probe()
    assert report.observed_model_count == 20 and report.attacks_cast == 640
    assert report.actions == 2464 and report.completed_turns == report.resolved_attacks == 640
    assert report.absorption_count == 128 and report.absorbed_hp == 1024
    assert report.inflicted_curses == 320 and report.inflicted_illnesses == 192
    assert report.chance_casts == report.dark_cloud_hits == 96
    assert report.hp_damage == 3104 and report.mp_spent == 1536
    assert report.consumed_cards == 416 and report.retained_miracle_uses == 224
    assert report.ready_after_one_turn == 640 and report.real_terminal_endings == 0
    assert (
        report.metadata_sha256 == "1f6a7e864e5450cddbcf52a4b15b6f09be758728e8a16408dfeb94ec75d35040"
    )
    assert (
        report.diagnostic_replay_sha256
        == "21fec423a2335216d8153abefc80c9c9c9155aae4c728c04f6d761f8350a3ec7"
    )
    assert not report.teacher_or_reward_dataset_eligible and not report.local_training_eligible
    assert not report.full_game_training_ready and not report.promotion_eligible


@pytest.mark.parametrize("size", [1, 20, 64])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_partial_batches_preserve_unobserved_profiles_and_one_turn_accounting(size, players):
    report = probe(batch_size=size, player_count=players)
    assert len(report.model_results) == 20
    assert report.observed_model_count == min(size, 20)
    assert report.completed_turns == report.ready_after_one_turn == size
    assert FullGameAttackEffectSmokeReport.model_validate_json(report.model_dump_json()) == report


@pytest.mark.parametrize("size", [True, 0, 4097, 2.5])
def test_invalid_batch_bound_fails_before_allocation(size):
    with pytest.raises(ValueError):
        probe(batch_size=size)


@pytest.mark.parametrize(
    "change",
    [
        {"actions": 0},
        {"completed_turns": 0},
        {"attacks_cast": 0},
        {"resolved_attacks": 0},
        {"chance_casts": 0},
        {"dark_cloud_hits": 0},
        {"absorption_count": 0},
        {"inflicted_curses": 0},
        {"inflicted_illnesses": 0},
        {"ready_after_one_turn": 0},
        {"model_results": ()},
        {"observed_model_count": 1},
        {"consumed_cards": 0},
        {"illness_effect_damage": 1},
        {"real_terminal_endings": 1},
        {"absorbed_hp": 99999},
        {"teacher_or_reward_dataset_eligible": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"source_kind": "full-game-training"},
    ],
)
def test_report_cannot_relabel_diagnostics_or_forge_accounting(change):
    report = probe(batch_size=20)
    with pytest.raises(ValidationError):
        FullGameAttackEffectSmokeReport.model_validate({**report.model_dump(), **change})


def test_diagnostic_redaction_changes_replay_not_commands_or_native_effect_results(monkeypatch):
    import godfield_bot.full_game_attack_effect_smoke as module

    reference = probe(batch_size=20)
    factory = module.create_development_full_game_batch

    class Redacted:
        def __init__(self, batch):
            self.batch = batch

        def __getattr__(self, name):
            return getattr(self.batch, name)

        def diagnostic_players(self):
            return np.zeros_like(self.batch.diagnostic_players())

        def diagnostic_inventory(self):
            return np.zeros_like(self.batch.diagnostic_inventory())

    def create(**options):
        configured = factory(**options)
        return replace(configured, batch=Redacted(configured.batch))

    monkeypatch.setattr(module, "create_development_full_game_batch", create)
    redacted = probe(batch_size=20)
    assert reference.diagnostic_replay_sha256 != redacted.diagnostic_replay_sha256
    assert reference.model_dump(exclude={"diagnostic_replay_sha256"}) == redacted.model_dump(
        exclude={"diagnostic_replay_sha256"}
    )


def test_cli_uses_same_offline_probe(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app, ["simulation", "full-game-attack-effect-smoke", "--batch-size", "20"]
    )
    assert result.exit_code == 0
    assert FullGameAttackEffectSmokeReport.model_validate(json.loads(result.stdout)) == probe(
        batch_size=20
    )


def test_cli_surfaces_engine_failure_without_a_success_report(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)

    def fail(**_options):
        raise RuntimeError("simulated unavailable native engine")

    monkeypatch.setattr(
        "godfield_bot.full_game_attack_effect_smoke.run_full_game_attack_effect_smoke", fail
    )
    result = CliRunner().invoke(
        app, ["simulation", "full-game-attack-effect-smoke", "--batch-size", "20"]
    )
    assert result.exit_code == 1
    assert '"model_results"' not in result.stdout
