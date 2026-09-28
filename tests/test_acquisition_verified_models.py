"""Official v3 lifecycle fixtures; no combat, acquisition, or training gate."""

import hashlib
import json
from pathlib import Path

import pytest
from test_acquisition_replay import audit, batch, event, fixture_database, item, snapshot
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches
from godfield_bot.acquisition_probe import AcquisitionCollectorSummary
from godfield_bot.acquisition_replay import (
    INVENTORY_NEUTRAL_ACTIONS,
    ORDINARY_MODELS,
    REPLAY_PROJECTION_ID,
    audit_acquisition_replay_batches,
    audit_acquisition_replay_run,
)
from godfield_bot.acquisition_v3 import AcquisitionEvidenceBatchV3
from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
FIXTURE = Path("tests/fixtures/acquisition-v3-60fe19b4.json")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
INPUT_SHA256 = "502ab0aca105ea5ea085bdfe229736ad8e9fa8692e9af7e7523eeef6de0421d1"
NEW_MODELS = (26, 29, 32, 41, 44, 55, 123, 135, 192)


@pytest.fixture(autouse=True)
def avoid_retaining_cli_capture(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)


def official_batches():
    fixture = json.loads(FIXTURE.read_text())
    batches = tuple(
        AcquisitionEvidenceBatchV3.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-evidence-v3"
    )
    return fixture, batches


def rows(items):
    return np.asarray(
        [[i.instance_id, i.model_id, i.fake_model_id or 0, int(i.used is True)] for i in items],
        dtype=np.int64,
    ).reshape(-1, 4)


def test_official_v3_fixture_keeps_original_digests_and_missing_defense_arrays():
    fixture, batches = official_batches()
    fingerprint = {key: fixture[key] for key in ("run_id", "mode", "client_sha256", "evidence")}
    assert (
        hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == fixture["input_sha256"]
        == INPUT_SHA256
    )
    assert all(
        batch.model_dump(mode="json") == record["payload"]
        for batch, record in zip(
            batches,
            [
                r
                for r in fixture["evidence"]
                if r["payload"]["source_kind"] == "official-acquisition-evidence-v3"
            ],
            strict=True,
        )
    )
    summaries = tuple(
        AcquisitionCollectorSummary.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-collector-summary-v1"
    )
    transport = audit_acquisition_batches(batches, summaries=summaries)
    assert transport.capture_schema_versions == (3,)
    assert transport.batch_count == 23
    assert transport.snapshot_count == 12
    assert transport.adjacent_pair_count == 11
    assert transport.self_bound_attack_item_count == 7
    assert transport.self_bound_defense_item_count == 2
    assert transport.self_event_wire_metadata_count == 29
    assert transport.final_poll_succeeded
    assert transport.collection_issues == ("ambiguous_self_selections",)
    assert transport.ambiguous_self_selection_event_count == 2
    assert transport.self_overflow_item_event_count == 0
    assert transport.raw_used_true_observation_count == 0
    assert transport.owned_inventory_growth_pair_count == 0
    snapshots = [row for batch in batches for row in batch.snapshots]
    for sequence in (7, 12):
        row = snapshots[sequence - 1]
        assert row.events[0].action == "useDefenseItems"
        assert row.events[0].items == ()
        assert row.event_item_wire[0].items_kind == "missing"
    assert not fixture["training_eligible"]
    assert not fixture["promotion_eligible"]
    assert not fixture["acquisition_rule_eligible"]


@pytest.mark.parametrize("model_id", NEW_MODELS)
def test_each_new_ordinary_model_has_an_explicit_official_native_inventory_pair(model_id):
    _, batches = official_batches()
    snapshots = [row for batch in batches for row in batch.snapshots]
    catalog = {item.model_id: item.raw for item in read_api_catalog_snapshot(CATALOG).items}
    # No selection is inferred from the two resulting inventories. The stored
    # self-bound item event is required, including its original wire sidecar.
    selected = [
        (index, event)
        for index, row in enumerate(snapshots)
        for event in row.events
        if event.self_item_payload_bound
        and event.action in {"useAttackItems", "useDefenseItems"}
        and len(event.items) == 1
        and event.items[0].model_id == model_id
    ]
    assert len(selected) == 1
    index, consumed = selected[0]
    assert index > 0
    current = snapshots[index]
    wire = current.event_item_wire[consumed.event_index]
    assert wire.items_kind == "array" and not wire.malformed
    assert catalog[model_id]["category"] in {"weapons", "armor", "sundries"}
    replay = native.OrderedInventoryReplay(
        rows(snapshots[index - 1].self_items), np.asarray(ORDINARY_MODELS, dtype=np.int64)
    )
    replay.consume(rows(consumed.items))
    # Supply only the explicit gifts, not a replacement inferred from missing
    # inventory. This isolated primitive check does not simulate other effects.
    gifts = [e for e in current.events if e.self_item_payload_bound and e.action == "gift"]
    assert len(gifts) == 1
    assert gifts[0].item is not None and gifts[0].overflow_item is None
    replay.gift(rows([gifts[0].item])[0])
    np.testing.assert_array_equal(replay.snapshot(), rows(current.self_items))
    assert replay.consumed_item_count == replay.gift_item_count == 1
    assert replay.retained_miracle_use_count == 0
    assert replay.size == 9


def test_allowlist_is_exactly_witnessed_models_not_catalog_categories():
    assert tuple(sorted((23, 142, *NEW_MODELS))) == ORDINARY_MODELS
    assert REPLAY_PROJECTION_ID == "observed-inventory-projection-verified-ordinary-wire-aware-v3"
    # Flare Axe occurs as an opaque gift, but this trace never consumes it.
    first = snapshot(
        owned=[item(1, 110)],
        events=[
            event("startGame"),
            event("gift", actor=2, gift=item(1, 110)),
            event("advanceGF", actor=2),
        ],
    )
    second = snapshot(
        2, previous=first, owned=[], events=[event("useAttackItems", items=[item(1, 110)])]
    )
    report = audit(batch(first, second))
    assert report.results[-1].reason == "unsupported_selection_model_or_combination"
    assert report.matched_consumed_item_count == 0


def test_full_v3_audit_preserves_unsupported_curse_trade_and_missing_selection_rows():
    _, batches = official_batches()
    report = audit_acquisition_replay_batches(batches, catalog=read_api_catalog_snapshot(CATALOG))
    assert report.matched_initial_snapshot_count == 1
    assert report.matched_transition_count == 8
    assert report.matched_consumed_item_count == 8
    assert report.matched_gift_item_count == 17
    assert report.mismatch_count == report.skipped_snapshot_count == 0
    assert report.unsupported_snapshot_count == 3
    assert report.reason_counts == {
        "ambiguous_self_selection_array": 2,
        "unsupported_inventory_event": 1,
    }
    assert [row.source_sequence for row in report.results if row.status == "unsupported"] == [
        6,
        7,
        12,
    ]
    assert report.results[5].event_index == 4  # addCurse may change Dream views.
    assert report.results[6].event_index == report.results[11].event_index == 0
    assert report.event_item_wire_metadata_complete
    assert not report.complete_projection_replay
    assert report.matched_retained_miracle_use_count == 0
    assert not report.combat_replay_verified
    assert not report.gift_schedule_verified
    assert not report.overflow_rule_verified
    assert not report.training_eligible
    assert not report.promotion_eligible
    assert not report.acquisition_rule_eligible


def test_official_v3_cli_is_read_only_and_missing_fields_are_not_rewritten(tmp_path):
    database, run_id, fingerprint = fixture_database(tmp_path, FIXTURE)
    original = database.read_bytes()
    report = audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report["input_sha256"] == fingerprint == INPUT_SHA256
    assert report == audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report["transport_audit"]["collection_issues"] == ["ambiguous_self_selections"]
    assert report["transport_audit"]["declared_capture_schema_version"] == 3
    assert report["transport_audit"]["capture_schema_matches_run_config"]
    result = CliRunner().invoke(
        app,
        ["runs", "acquisition-replay", run_id, "--database", str(database)],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == report
    assert database.read_bytes() == original
    assert "passed" not in report


@pytest.mark.parametrize("action", ["boostHP", "boostMP"])
def test_reviewed_resource_events_do_not_hide_inventory_changes(action):
    assert action in INVENTORY_NEUTRAL_ACTIONS
    first = snapshot()
    unchanged = snapshot(2, previous=first, events=[event(action)])
    assert audit(batch(first, unchanged)).results[-1].status == "matched"
    changed = snapshot(2, previous=first, owned=[], events=[event(action)])
    report = audit(batch(first, changed))
    assert report.results[-1].status == "mismatch"
    assert report.results[-1].reason == "ordered_inventory_differs"
    assert not report.complete_projection_replay


@pytest.mark.parametrize("action", ["addCurse", "buy", "setBought", "boostCP"])
def test_other_effects_do_not_gain_inventory_neutrality_from_the_new_fixture(action):
    assert action not in INVENTORY_NEUTRAL_ACTIONS
    first = snapshot()
    second = snapshot(2, previous=first, events=[event(action)])
    report = audit(batch(first, second))
    assert report.results[-1].reason == "unsupported_inventory_event"
    assert not report.complete_projection_replay


@pytest.mark.parametrize("models", [(23, 142), (32, 44), (123, 135), (192, 23)])
def test_multi_item_selections_are_not_promoted_from_single_item_witnesses(models):
    selected = [item(index, model) for index, model in enumerate(models, start=1)]
    first = snapshot(
        owned=selected,
        events=[
            event("startGame"),
            *[event("gift", actor=2, gift=i) for i in selected],
            event("advanceGF", actor=2),
        ],
    )
    second = snapshot(2, previous=first, owned=[], events=[event("useAttackItems", items=selected)])
    report = audit(batch(first, second))
    assert report.results[-1].reason == "unsupported_selection_model_or_combination"
    assert report.matched_consumed_item_count == 0
    assert not report.complete_projection_replay
