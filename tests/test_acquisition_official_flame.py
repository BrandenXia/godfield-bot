"""Event-backed official Flame first use/reuse, not a universal acquisition rule."""

import hashlib
import json
from pathlib import Path

import pytest
from test_acquisition_replay import fixture_database
from test_acquisition_verified_models import rows
from typer.testing import CliRunner

from godfield_bot.acquisition_evidence import audit_acquisition_batches, audit_acquisition_run
from godfield_bot.acquisition_policy import ACQUISITION_POLICY_ID
from godfield_bot.acquisition_probe import AcquisitionCollectorSummary
from godfield_bot.acquisition_replay import (
    ORDINARY_MODELS,
    RETAINED_MODELS,
    audit_acquisition_replay_batches,
    audit_acquisition_replay_run,
)
from godfield_bot.acquisition_v4 import AcquisitionEvidenceBatchV4
from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.cli import app

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
FIXTURE = Path("tests/fixtures/acquisition-v4-32d8eeeb.json")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
INPUT_SHA256 = "c640ac037072e63ea616ae450a2d31c27123747394ba750e592c7fe9fc0f837a"


def official_batches():
    fixture = json.loads(FIXTURE.read_text())
    batches = tuple(
        AcquisitionEvidenceBatchV4.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-evidence-v4"
    )
    return fixture, batches


def snapshots():
    return [row for batch in official_batches()[1] for row in batch.snapshots]


def test_official_flame_fixture_preserves_full_checksums_and_raw_unknown_flags():
    fixture, batches = official_batches()
    fingerprint = {key: fixture[key] for key in ("run_id", "mode", "client_sha256", "evidence")}
    assert (
        hashlib.sha256(
            json.dumps(
                fingerprint,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        == fixture["input_sha256"]
        == INPUT_SHA256
    )
    assert len(fixture["evidence"]) == 31
    assert all(
        saved.model_dump(mode="json") == record["payload"]
        for saved, record in zip(
            batches,
            [
                r
                for r in fixture["evidence"]
                if r["payload"]["source_kind"] == "official-acquisition-evidence-v4"
            ],
            strict=True,
        )
    )
    assert fixture["policy_id"] == ACQUISITION_POLICY_ID
    assert fixture["collection_only"] and fixture["run_status"] == "completed"
    assert not fixture["training_eligible"] and not fixture["promotion_eligible"]
    summaries = tuple(
        AcquisitionCollectorSummary.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-collector-summary-v1"
    )
    audit = audit_acquisition_batches(batches, summaries=summaries)
    assert audit.batch_count == 30 and audit.snapshot_count == 15
    assert audit.adjacent_pair_count == 14 and audit.capture_schema_versions == (4,)
    assert audit.final_poll_succeeded and audit.terminal_snapshot_seen
    assert audit.unknown_used_flag_count == 130
    assert audit.raw_used_true_observation_count == 7  # Observations, not seven casts.
    assert audit.client_interpreted_used_activation_count == 1
    assert audit.self_overflow_item_event_count == 0
    assert audit.unresolved_item_owner_event_count == 2
    assert audit.ambiguous_self_selection_event_count == 4
    for name in (
        "missing_source_sequence_count",
        "server_gap_pair_count",
        "dropped_snapshot_count",
        "rejected_snapshot_count",
        "hook_error_count",
        "read_error_count",
        "ack_error_count",
        "malformed_self_event_wire_count",
        "inconsistent_server_version_count",
    ):
        assert getattr(audit, name) == 0


def test_flame_arrives_by_an_explicit_self_gift_not_an_inventory_diff_or_intended_click():
    previous, gifted = snapshots()[6:8]
    assert previous.source_sequence == 7 and gifted.source_sequence == 8
    assert not any(item.model_id == 215 for item in previous.self_items)
    gift = next(
        event for event in gifted.events if event.action == "gift" and event.self_item_payload_bound
    )
    assert gift.player_id == gifted.self_player_id == 2  # Self is not always player 1.
    assert gift.item.instance_id == 4 and gift.item.model_id == 215
    assert gift.item.used is None and gift.overflow_item is None
    assert gifted.event_item_wire[gift.event_index].item.used_kind == "missing"
    # An ordinary armor/model 161 disappears in this same update. Until it is
    # separately admitted, the full acquisition update must stay unsupported.
    assert gifted.events[0].items[0].model_id == 161
    report = audit_acquisition_replay_batches(
        official_batches()[1], catalog=read_api_catalog_snapshot(CATALOG)
    )
    assert report.results[7].reason == "unsupported_selection_model_or_combination"


@pytest.mark.parametrize(
    "sequence,previous_used,population,gift_id,gift_model",
    [
        (9, None, 8, 5, 161),
        (11, True, 9, 10, 76),
    ],
)
def test_actual_first_use_and_reuse_match_native_retention_then_explicit_gift(
    sequence,
    previous_used,
    population,
    gift_id,
    gift_model,
):
    captured = snapshots()
    previous, current = captured[sequence - 2 : sequence]
    assert current.source_sequence == sequence and current.phase_input_status == "consecutive"
    selection = current.events[0]
    assert selection.action == "useAttackItems" and selection.self_item_payload_bound
    assert current.event_owners[0].item_owner_player_id == current.self_player_id == 2
    assert len(selection.items) == 1 and selection.items[0].instance_id == 4
    assert selection.items[0].model_id == 215 and selection.items[0].used is previous_used
    wire = current.event_item_wire[0]
    assert wire.items_kind == "array" and not wire.malformed
    assert wire.items[0].used_kind == ("missing" if previous_used is None else "boolean")
    gifts = [e for e in current.events if e.action == "gift" and e.self_item_payload_bound]
    assert len(gifts) == 1 and gifts[0].overflow_item is None
    assert gifts[0].item.instance_id == gift_id and gifts[0].item.model_id == gift_model
    replay = native.OrderedInventoryReplay(
        rows(previous.self_items), np.asarray(ORDINARY_MODELS, dtype=np.int64)
    )
    replay.configure_retained_miracles(np.asarray(RETAINED_MODELS, dtype=np.int64))
    replay.perform_retained_miracle(rows(selection.items)[0])
    retained = replay.snapshot()
    assert replay.size == population and replay.gift_item_count == 0
    assert replay.consumed_item_count == 0 and replay.retained_miracle_use_count == 1
    assert retained[-1].tolist() == [4, 215, 0, 1]
    replay.gift(rows([gifts[0].item])[0])
    np.testing.assert_array_equal(replay.snapshot(), rows(current.self_items))
    assert replay.size == population + 1 and replay.gift_item_count == 1
    assert retained.shape == (population, 4)  # Native snapshots remain independent.


def test_reuse_moves_the_retained_instance_to_the_tail_without_replacing_its_identity():
    previous, current = snapshots()[9:11]
    assert previous.self_items[-2].instance_id == 4 and previous.self_items[-1].instance_id == 5
    assert current.self_items[-3].instance_id == 5 and current.self_items[-2].instance_id == 4
    assert current.self_items[-1].instance_id == 10
    assert current.self_items[-2].model_id == 215 and current.self_items[-2].used is True
    assert len({item.instance_id for item in current.self_items}) == len(current.self_items)


def test_stale_first_use_payload_after_retention_is_rejected_atomically():
    previous, current = snapshots()[7:9]
    expected = rows(current.events[0].items)[0]
    replay = native.OrderedInventoryReplay(
        rows(previous.self_items), np.asarray(ORDINARY_MODELS, dtype=np.int64)
    )
    replay.configure_retained_miracles(np.asarray(RETAINED_MODELS, dtype=np.int64))
    replay.perform_retained_miracle(expected)
    before = replay.snapshot()
    with pytest.raises(ValueError, match="differs from owned"):
        replay.perform_retained_miracle(expected)
    np.testing.assert_array_equal(replay.snapshot(), before)
    assert replay.retained_miracle_use_count == 1 and replay.gift_item_count == 0


def test_two_casts_match_but_omitted_defenses_and_other_models_stay_unsupported():
    report = audit_acquisition_replay_batches(
        official_batches()[1], catalog=read_api_catalog_snapshot(CATALOG)
    )
    assert report.matched_initial_snapshot_count == 1 and report.matched_transition_count == 5
    assert report.matched_retained_miracle_use_count == 2
    assert report.matched_consumed_item_count == 3 and report.matched_gift_item_count == 14
    assert report.mismatch_count == 0 and report.unsupported_snapshot_count == 9
    assert report.reason_counts == {
        "ambiguous_self_selection_array": 4,
        "unresolved_item_owner": 1,
        "unsupported_selection_model_or_combination": 4,
    }
    for sequence in (9, 11):
        assert report.results[sequence - 1].status == "matched"
        assert report.results[sequence - 1].retained_miracle_use_count == 1
    assert report.results[9].reason == "ambiguous_self_selection_array"
    assert not report.complete_projection_replay and not report.event_item_wire_metadata_complete
    assert not report.training_eligible and not report.promotion_eligible
    assert not report.gift_schedule_verified and not report.overflow_rule_verified
    assert not report.combat_replay_verified and not report.acquisition_rule_eligible
    assert snapshots()[-1].is_over is True
    assert any(
        item.instance_id == 4 and item.model_id == 215 for item in snapshots()[-1].self_items
    )


def test_official_flame_cli_audits_are_deterministic_read_only_and_preserve_input_fingerprint(
    tmp_path, monkeypatch
):
    database, run_id, fingerprint = fixture_database(tmp_path, FIXTURE)
    before = database.read_bytes()
    report = audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    assert report["input_sha256"] == fingerprint == INPUT_SHA256
    assert report == audit_acquisition_replay_run(database, run_id, catalog_path=CATALOG)
    transport = audit_acquisition_run(database, run_id)
    assert (
        transport["capture_schema_matches_run_config"]
        and transport["declared_capture_schema_version"] == 4
    )
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    for command in ("acquisition-evidence", "acquisition-replay"):
        result = CliRunner().invoke(app, ["runs", command, run_id, "--database", str(database)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["input_sha256"] == INPUT_SHA256
    assert database.read_bytes() == before
