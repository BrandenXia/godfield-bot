"""Full catalog identity, owned/event route distinctions and honest evidence scope."""

import json
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("godfield_sim")

from godfield_bot.cli import app
from godfield_bot.full_game_integration_audit import (
    FullGameIntegrationAudit,
    build_full_game_integration_audit,
)

PATHS = dict(
    catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
    bible_path=Path("data/snapshots/2026-09-20/bible.json"),
)


@pytest.fixture(scope="module")
def audit():
    return build_full_game_integration_audit(**PATHS)


def test_every_catalog_entry_has_its_own_route_without_conflating_held_events_and_controls(audit):
    assert audit.catalog_entries == 296 and audit.bible_artifacts == 291
    assert audit.held_models == 237 and audit.virtual_controls == 2
    assert Counter(entry.kind for entry in audit.entries) == {
        "virtual-control": 2,
        "held-trade": 3,
        "held-artifact": 234,
        "devil": 5,
        "guardian": 42,
        "phenomenon": 10,
    }
    assert sum(entry.bible_artifact for entry in audit.entries) == 291
    assert sum(bool(entry.owned_role_bits) for entry in audit.entries) == 237
    rows = {entry.model_id: entry for entry in audit.entries}
    assert rows[1].primary_routes == ("discard.virtual_model_id",)
    assert rows[2].primary_routes == ("discard.sacrifice_virtual_model_id",)
    assert rows[3].primary_routes == ("trade.exchange_model_ids",)
    assert rows[4].primary_routes == ("trade.sell",)
    assert rows[5].primary_routes == ("trade.buy",)
    assert rows[127].primary_routes == ("combat.armor_profiles",)
    assert rows[127].generated_guardian_route == "drop-receipt"
    assert rows[285].primary_routes == ("guardians.earth_generated_actions",)
    assert rows[286].primary_routes == ("guardians.moon_generated_actions",)
    assert rows[285].generated_guardian_route is None and not rows[285].owned_role_bits
    assert len({(r.category, r.asset) for r in audit.entries if r.bible_artifact}) == 291
    assert audit.metadata.capacity == 18 and len(audit.encoder.hand_fields) == 69


def test_workflow_and_provisional_ledgers_point_to_real_implementation_and_tests(audit):
    assert len(audit.workflows) == 14
    assert all(Path(p).is_file() for w in audit.workflows for p in (*w.source_files, *w.test_files))
    required = {p for w in audit.workflows for p in w.test_files}
    assert {
        "tests/test_full_game_learning_probe.py",
        "tests/test_full_game_mechanic_learning.py",
    } <= required
    assert {"tests/test_full_game_generated.py", "tests/test_full_game_phenomena.py"} <= required
    assumptions = {row.metadata_path: row.rule for row in audit.provisional_assumptions}
    assert assumptions["overflow_policy"] == "oldest-held-provisional"
    assert "whole-selection-no-effects" in assumptions["hidden_cost_effects"]
    assert "provisional" in assumptions["plan.guardians.construction"]
    assert audit.source_routes_complete and not audit.execution_evidence_attached
    assert not audit.full_game_training_ready and not audit.official_fidelity_verified
    assert not audit.live_checkpoint_compatible and not audit.promotion_eligible
    assert FullGameIntegrationAudit.model_validate_json(audit.model_dump_json()) == audit


@pytest.mark.parametrize(
    "change",
    [
        "missing-model",
        "duplicate-model",
        "event-as-held",
        "trades-as-artifacts",
        "generated-as-owned",
        "wrong-role",
        "wrong-profile",
        "workflow",
        "assumptions",
        "source",
        "encoder",
        "execution",
        "ready",
    ],
)
def test_inclusion_cannot_be_reclassified_or_promoted_without_execution_evidence(audit, change):
    bad = audit.model_dump()
    entries = list(bad["entries"])
    if change == "missing-model":
        entries.pop()
    elif change == "duplicate-model":
        entries[0] = entries[1]
    elif change == "event-as-held":
        entries[239]["kind"] = "held-artifact"
    elif change == "trades-as-artifacts":
        entries[2]["bible_artifact"] = True
    elif change == "generated-as-owned":
        entries[126]["primary_routes"] = ("guardians.drop-receipt",)
    elif change == "wrong-role":
        entries[126]["owned_role_bits"] = 1
    elif change == "wrong-profile":
        entries[0]["primary_routes"] = ("trade.exchange_model_ids",)
    elif change == "workflow":
        bad["workflows"] = bad["workflows"][:-1]
    elif change == "assumptions":
        bad["provisional_assumptions"] = ()
    elif change == "source":
        bad["catalog_sha256"] = "0" * 64
    elif change == "encoder":
        bad["encoder"]["environment_metadata_sha256"] = "0" * 64
    elif change == "execution":
        bad["execution_evidence_attached"] = True
    else:
        bad["full_game_training_ready"] = True
    bad["entries"] = entries
    with pytest.raises(ValueError):
        FullGameIntegrationAudit.model_validate(bad)


def test_cli_audits_current_engine_without_starting_games(audit, monkeypatch):
    import godfield_bot.full_game_integration_audit as module

    original = module.create_development_full_game_batch
    instances = []

    def create(**options):
        result = original(**options)
        instances.append(result.batch)
        return result

    monkeypatch.setattr(module, "create_development_full_game_batch", create)
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(app, ["simulation", "full-game-integration-audit"])
    assert result.exit_code == 0, result.output
    assert FullGameIntegrationAudit.model_validate(json.loads(result.stdout)) == audit
    assert len(instances) == 1 and instances[0].action_count == 0
    assert instances[0].episode_snapshot()[0, 3] == 0
    assert not instances[0].diagnostic_inventory().any()
