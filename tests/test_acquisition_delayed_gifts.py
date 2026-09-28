"""Real deferred ordinary gifts, not an inferred universal gift scheduler."""

import hashlib
import json
from pathlib import Path

import pytest
from test_acquisition_replay import audit, batch, event, fixture_database, snapshot
from test_acquisition_verified_models import rows
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches
from godfield_bot.acquisition_probe import AcquisitionCollectorSummary
from godfield_bot.acquisition_replay import (
    INVENTORY_NEUTRAL_ACTIONS,
    ORDINARY_MODELS,
    audit_acquisition_replay_batches,
    audit_acquisition_replay_run,
)
from godfield_bot.acquisition_v3 import AcquisitionEvidenceBatchV3
from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
FIXTURE = Path("tests/fixtures/acquisition-v3-cb9da594.json")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
INPUT_SHA256 = "18bfdec78b4b9fa7820a78793fe614ad725c4cec29270a093573a9e73b43d79b"
NEW_MODELS = (16, 40, 81, 130, 166, 195)


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


def snapshots():
    _, batches = official_batches()
    return [row for batch in batches for row in batch.snapshots]


def test_second_real_v3_fixture_keeps_hashes_redactions_and_transport_defects():
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
        saved.model_dump(mode="json") == record["payload"]
        for saved, record in zip(
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
    assert transport.batch_count == 24
    assert transport.snapshot_count == 13
    assert transport.adjacent_pair_count == 12
    assert transport.final_poll_succeeded
    assert transport.collection_issues == ("unresolved_item_ownership", "ambiguous_self_selections")
    assert transport.unresolved_item_owner_event_count == 1
    assert transport.ambiguous_self_selection_event_count == 2
    assert transport.client_empty_placeholder_observation_count == 1
    assert transport.owned_inventory_growth_pair_count == 1
    assert transport.raw_used_true_observation_count == 0
    assert transport.client_interpreted_used_activation_count == 0
    assert transport.self_overflow_item_event_count == 0
    # The growth is a deferred ordinary gift, NOT miracle evidence.
    assert not fixture["training_eligible"]
    assert not fixture["promotion_eligible"]
    assert not fixture["acquisition_rule_eligible"]


@pytest.mark.parametrize("model_id", NEW_MODELS)
def test_additional_single_ordinary_and_mp_utility_uses_match_native_pairs(model_id):
    captured = snapshots()
    catalog = {i.model_id: i.raw for i in read_api_catalog_snapshot(CATALOG).items}
    uses = [
        (index, operation)
        for index, current in enumerate(captured)
        for operation in current.events
        if operation.self_item_payload_bound
        and operation.action in {"useAttackItems", "useDefenseItems"}
        and len(operation.items) == 1
        and operation.items[0].model_id == model_id
    ]
    assert len(uses) == (3 if model_id == 16 else 1)
    for index, operation in uses:
        assert index > 0
        current = captured[index]
        wire = current.event_item_wire[operation.event_index]
        assert wire.items_kind == "array" and not wire.malformed
        assert catalog[model_id]["category"] in {"weapons", "armor", "sundries"}
        replay = native.OrderedInventoryReplay(
            rows(captured[index - 1].self_items), np.asarray(ORDINARY_MODELS, dtype=np.int64)
        )
        replay.consume(rows(operation.items))
        gifts = [e for e in current.events if e.self_item_payload_bound and e.action == "gift"]
        assert len(gifts) == 1
        assert gifts[0].item is not None and gifts[0].overflow_item is None
        replay.gift(rows([gifts[0].item])[0])
        np.testing.assert_array_equal(replay.snapshot(), rows(current.self_items))
        assert replay.consumed_item_count == replay.gift_item_count == 1
    if model_id == 195:
        assert catalog[model_id]["ability"] == "boostMP"


def test_native_consumption_does_not_redraw_before_the_explicit_deferred_gift():
    before, consumed, gifted = snapshots()[6:9]
    assert (before.source_sequence, consumed.source_sequence, gifted.source_sequence) == (7, 8, 9)
    selection = consumed.events[0]
    assert selection.self_item_payload_bound and selection.action == "useAttackItems"
    assert selection.items[0].model_id == 44
    assert consumed.events[-1].action == "reflect"
    assert not any(e.action == "gift" for e in consumed.events)
    placeholder = consumed.self_items[-1]
    assert placeholder.instance_id is placeholder.model_id is None
    assert consumed.self_item_wire[-1].client_empty_placeholder
    assert consumed.self_item_wire[-1].instance_id_kind == "zero"
    assert consumed.self_item_wire[-1].model_id_kind == "zero"
    replay = native.OrderedInventoryReplay(
        rows(before.self_items), np.asarray(ORDINARY_MODELS, dtype=np.int64)
    )
    replay.consume(rows(selection.items))
    np.testing.assert_array_equal(replay.snapshot(), rows(consumed.self_items[:-1]))
    assert replay.size == 8 and replay.gift_item_count == 0
    pending_snapshot = replay.snapshot()
    gift = next(e for e in gifted.events if e.self_item_payload_bound and e.action == "gift")
    assert gift.item is not None
    assert gift.item.instance_id == selection.items[0].instance_id == 4
    assert gift.item.model_id == 199
    replay.gift(rows([gift.item])[0])
    np.testing.assert_array_equal(replay.snapshot(), rows(gifted.self_items))
    assert replay.size == 9
    assert replay.consumed_item_count == replay.gift_item_count == 1
    # The primitive check above deliberately does not claim the unresolved
    # reflected-defense owner, or replay its redacted consumption selection.
    assert gifted.events[0].self_item_payload_bound is False
    assert gifted.events[0].items == ()
    assert gifted.event_item_wire[0].items_kind == "redacted"
    assert gifted.event_owners[0].item_owner_player_id is None
    assert pending_snapshot.shape == (8, 4)  # Independent native snapshot.


def test_full_run_reports_deferred_consumption_but_does_not_invent_reflected_ownership():
    _, batches = official_batches()
    report = audit_acquisition_replay_batches(batches, catalog=read_api_catalog_snapshot(CATALOG))
    assert report.matched_initial_snapshot_count == 1
    assert report.matched_transition_count == 9
    assert report.matched_consumed_item_count == 9
    assert report.matched_gift_item_count == 17
    assert report.unsupported_snapshot_count == 3
    assert report.reason_counts == {
        "ambiguous_self_selection_array": 2,
        "unresolved_item_owner": 1,
    }
    assert report.mismatch_count == report.skipped_snapshot_count == 0
    reflection = report.results[7]
    assert reflection.status == "matched"
    assert reflection.replayed_item_count == reflection.expected_item_count == 8
    assert reflection.consumed_item_count == 1 and reflection.gift_item_count == 0
    assert report.results[8].reason == "unresolved_item_owner"
    assert report.results[8].event_index == 0
    assert not report.event_item_wire_metadata_complete
    assert not report.complete_projection_replay
    for flag in (
        "combat_replay_verified",
        "gift_schedule_verified",
        "overflow_rule_verified",
        "training_eligible",
        "promotion_eligible",
        "acquisition_rule_eligible",
    ):
        assert report.model_dump()[flag] is False


def test_reflect_inventory_neutrality_is_not_phase_preservation_or_state_repair():
    assert "reflect" in INVENTORY_NEUTRAL_ACTIONS
    first = snapshot()
    unchanged = snapshot(2, previous=first, events=[event("reflect")])
    matched = audit(batch(first, unchanged))
    assert matched.results[-1].status == "matched"
    assert unchanged.phase_after.turn_player_id is None
    assert unchanged.phase_after.target_player_id is None
    changed = snapshot(2, previous=first, owned=[], events=[event("reflect")])
    report = audit(batch(first, changed))
    assert report.results[-1].reason == "ordered_inventory_differs"
    assert report.mismatch_count == 1
    after = snapshot(3, previous=unchanged, events=[event("useDefenseItems")])
    assert audit(batch(first, unchanged, after)).results[-1].reason == "unresolved_item_owner"


def test_real_deferred_gift_cli_is_read_only_and_preserves_complete_input_fingerprint(tmp_path):
    database, run_id, fingerprint = fixture_database(tmp_path, FIXTURE)
    original = database.read_bytes()
    report = audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report["input_sha256"] == fingerprint == INPUT_SHA256
    assert report == audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    result = CliRunner().invoke(
        app, ["runs", "acquisition-replay", run_id, "--database", str(database)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == report
    assert database.read_bytes() == original
    assert not report["complete_projection_replay"]
    assert "passed" not in report
