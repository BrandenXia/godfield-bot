import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.dream_probe import (
    DreamProbeCatalogIdentity,
    DreamProbeItemEvidence,
    DreamProbePhase,
    DreamProbeSample,
)
from godfield_bot.inventory_evidence import audit_inventory_run, audit_inventory_samples


@pytest.fixture(autouse=True)
def avoid_retaining_cli_runner_capture_streams(monkeypatch) -> None:
    # CLI logging otherwise binds its global factory to CliRunner's temporary
    # stderr, which is closed before unrelated training tests emit their logs.
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)


def sample(
    sequence: int,
    items: list[tuple[int | None, bool]],
    *,
    update: int | None = None,
    field: int = 7,
    player: int = 1,
    known: bool = True,
) -> DreamProbeSample:
    return DreamProbeSample(
        observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        source_sequence=sequence,
        update_count=sequence if update is None else update,
        field_number=field,
        phase=DreamProbePhase.TURN,
        self_player_id=player,
        dream_active=True,
        player_count=2,
        items=tuple(
            DreamProbeItemEvidence(
                instance_id=identity,
                raw_index=index,
                true_identity=(
                    DreamProbeCatalogIdentity(model_id=1, category="miracles") if known else None
                ),
                used=used,
                disguised=False,
            )
            for index, (identity, used) in enumerate(items)
        ),
        rendered_cards=(),
        hand_alignment="count_mismatch",
    )


def test_inventory_counts_instances_not_rendered_duplicates_or_used_flags() -> None:
    row = sample(1, [(i, i == 17) for i in range(1, 18)])
    report = audit_inventory_samples((row,))
    assert report.max_distinct_instances == 17
    assert report.max_unused_distinct_instances == 16
    assert report.max_known_unused_distinct_instances == 16
    assert report.max_used_distinct_instances == 1
    assert report.overflow_observation_count == 1
    assert report.adjacent_pair_count == 0
    assert not report.promotion_eligible
    assert not report.acquisition_rule_eligible
    assert "passed" not in report.model_dump()


def test_observed_retention_and_additions_are_not_causal_gift_labels() -> None:
    before = sample(1, [(1, False), (2, False)])
    used = sample(2, [(1, True), (3, False)])
    restored = sample(3, [(1, False), (3, False)])
    report = audit_inventory_samples((before, used, restored))
    assert report.adjacent_pair_count == 2
    assert report.changed_adjacent_pair_count == 2
    change = report.changes[0]
    assert change.added_instance_ids == (3,)
    assert change.removed_instance_ids == (2,)
    assert change.newly_used_retained_instance_ids == (1,)
    assert report.changes[1].no_longer_used_retained_instance_ids == (1,)
    assert "gift" not in change.model_dump()


@pytest.mark.parametrize("bad_items", [[(None, False)], [(1, False), (1, False)]])
def test_invalid_instances_cannot_bridge_two_valid_observations(bad_items) -> None:
    report = audit_inventory_samples(
        (sample(1, [(1, False)]), sample(2, bad_items), sample(3, [(2, False)]))
    )
    assert report.invalid_instance_sample_count == 1
    assert report.adjacent_pair_count == 0
    assert not report.changes


@pytest.mark.parametrize("sequence,update", [(3, 3), (2, 3), (3, 2)])
def test_missing_source_or_server_versions_never_form_transitions(sequence, update) -> None:
    report = audit_inventory_samples(
        (sample(1, [(1, False)]), sample(sequence, [(2, False)], update=update))
    )
    assert report.gap_pair_count == 1
    assert not report.changes


@pytest.mark.parametrize(
    "second",
    [sample(1, [(2, False)]), sample(3, [(2, False)], field=0), sample(3, [(2, False)], player=2)],
)
def test_game_or_probe_boundaries_never_form_transitions(second) -> None:
    report = audit_inventory_samples((sample(2, [(1, False)]), second))
    assert report.boundary_pair_count == 1
    assert not report.changes


def test_repeated_versions_are_deduplicated_and_inconsistent_versions_break_continuity() -> None:
    first = sample(1, [(1, False)])
    repeated = sample(2, [(1, False)], update=1)
    report = audit_inventory_samples((first, repeated, sample(3, [(2, False)], update=2)))
    assert report.repeated_version_observation_count == 1
    assert report.adjacent_pair_count == 1
    inconsistent = sample(2, [(2, False)], update=1)
    report = audit_inventory_samples((first, inconsistent, sample(3, [(3, False)], update=2)))
    assert report.inconsistent_version_pair_count == 1
    assert report.adjacent_pair_count == 0


def test_hidden_identity_counts_and_bounded_changes_remain_explicit() -> None:
    report = audit_inventory_samples(
        (sample(1, [(1, False)], known=False), sample(2, [(2, False)], known=False)),
        maximum_changes=0,
    )
    assert report.max_distinct_instances == 1
    assert report.max_known_unused_distinct_instances == 0
    assert report.changed_adjacent_pair_count == 1
    assert not report.changes
    assert report.changes_truncated
    assert audit_inventory_samples(()).sample_count == 0
    with pytest.raises(ValueError, match="maximum_changes"):
        audit_inventory_samples((), maximum_changes=-1)


def test_recycled_known_model_id_is_recorded_without_claiming_artifact_persistence() -> None:
    before = sample(1, [(1, False)])
    after = sample(2, [(1, False)])
    after = after.model_copy(
        update={
            "items": (
                after.items[0].model_copy(
                    update={"true_identity": DreamProbeCatalogIdentity(model_id=2)}
                ),
            )
        }
    )
    report = audit_inventory_samples((before, after))
    assert report.changed_adjacent_pair_count == 1
    assert report.changes[0].changed_known_model_instance_ids == (1,)
    assert not report.changes[0].added_instance_ids
    assert not report.changes[0].removed_instance_ids
    same_version = after.model_copy(update={"update_count": 1})
    assert audit_inventory_samples((before, same_version)).inconsistent_version_pair_count == 1


def test_database_reader_is_noncreating_readonly_and_fingerprinted(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        audit_inventory_run(path, "run")
    assert not path.exists()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE runs (run_id TEXT, mode TEXT, client_sha256 TEXT);"
            "CREATE TABLE events (run_id TEXT, sequence INTEGER, kind TEXT, payload_json TEXT);"
        )
        connection.execute("INSERT INTO runs VALUES (?, ?, ?)", ("run", "training", "a" * 64))
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            ("run", 1, "evidence", sample(1, [(1, False)]).model_dump_json()),
        )
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)", ("run", 2, "evidence", '{"unrelated":true}')
        )
    before = path.read_bytes()
    first = audit_inventory_run(path, "run")
    assert first == audit_inventory_run(path, "run")
    assert first["sample_count"] == 1
    assert len(str(first["input_sha256"])) == 64
    assert path.read_bytes() == before
    result = CliRunner().invoke(app, ["runs", "inventory-evidence", "run", "--database", str(path)])
    assert result.exit_code == 0
    assert json.loads(result.output) == first
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="unknown run"):
        audit_inventory_run(path, "missing")


def test_malformed_existing_evidence_fails_instead_of_becoming_a_rule(tmp_path: Path) -> None:
    path = tmp_path / "bad.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE runs (run_id TEXT, mode TEXT, client_sha256 TEXT);"
            "CREATE TABLE events (run_id TEXT, sequence INTEGER, kind TEXT, payload_json TEXT);"
        )
        connection.execute("INSERT INTO runs VALUES ('run', 'training', 'a')")
        connection.execute(
            "INSERT INTO events VALUES ('run', 1, 'evidence', ?)",
            ('{"dream_active":true,"items":"invalid"}',),
        )
    result = CliRunner().invoke(app, ["runs", "inventory-evidence", "run", "--database", str(path)])
    assert result.exit_code == 1
    assert "invalid inventory evidence" in result.output
