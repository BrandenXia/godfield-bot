import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import LEGACY_FEATURE_SCHEMA_VERSION, ArtifactVocabulary
from godfield_bot.model_registry import initialize_model
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_diagnostics import (
    UINT64_MAX,
    SimulationGameTrace,
    SimulationTraceConfig,
    _visible_hp,
    environment_seed,
    trace_simulation_game,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
SNAPSHOT = Path("data/snapshots/2026-09-20/bible.json")


@pytest.mark.parametrize("actor", [0, 1])
@pytest.mark.parametrize("fog", [False, True])
def test_trace_hp_maps_visible_perspective_to_physical_seats(actor, fog) -> None:
    batch = SimpleNamespace(
        active_players=np.array([actor]),
        player_features=np.array([[[0.45], [0.23]]], dtype=np.float32),
        fog_flags=np.array([[fog if actor == 0 else False, fog if actor == 1 else False]]),
    )
    other = None if fog else 23
    assert _visible_hp(batch) == ((45, other) if actor == 0 else (other, 45))


@pytest.mark.parametrize("seed", [67, UINT64_MAX])
@pytest.mark.parametrize("environment", [0, 5, 15])
def test_singleton_seed_matches_batched_rng_through_actions_and_resets(seed, environment) -> None:
    kwargs = {"ruleset": "wide-hand-gift-weighted-dream-resource-hand"}
    batch = create_attack_defense_simulation(SNAPSHOT, batch_size=16, seed=seed, **kwargs).batch
    single = create_attack_defense_simulation(
        SNAPSHOT, batch_size=1, seed=environment_seed(seed, environment), **kwargs
    ).batch
    for _ in range(64):
        for view in (
            "global_features",
            "hand_token_ids",
            "hand_mask",
            "action_mask",
            "episode_ids",
            "active_players",
        ):
            np.testing.assert_array_equal(
                getattr(single, view)[0], getattr(batch, view)[environment]
            )
        actions = batch.action_mask.argmax(axis=1).astype(np.int64)
        batch.step(actions)
        single.step(actions[environment : environment + 1].copy())
        batch.reset_done()
        single.reset_done()


@pytest.mark.parametrize(
    "seed,environment", [(-1, 0), (UINT64_MAX + 1, 0), (0, -1), (0, 1_000_000)]
)
def test_seed_mapping_rejects_out_of_range_inputs(seed, environment) -> None:
    with pytest.raises(ValueError, match="native range"):
        environment_seed(seed, environment)


def test_trace_is_fingerprinted_private_deterministic_and_never_a_gate(tmp_path: Path) -> None:
    bible = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    root = tmp_path / "models"
    manifest = initialize_model(
        root,
        ArtifactVocabulary.from_snapshot(bible),
        client_sha256=bible.client.sha256,
        feature_schema_version=LEGACY_FEATURE_SCHEMA_VERSION,
        global_feature_count=6,
    )
    directory = root / manifest.model_id
    before = (directory / "manifest.json").read_bytes()
    kwargs = {
        "candidate_model_directory": directory,
        "snapshot_path": SNAPSHOT,
        "trace_directory": tmp_path / "traces",
        "config": SimulationTraceConfig(ruleset="fixed-role", max_decisions=2),
    }
    path, trace = trace_simulation_game(**kwargs)
    _, second = trace_simulation_game(**kwargs)
    stored = SimulationGameTrace.model_validate_json(path.read_text())
    assert stored == trace
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert trace.decisions == second.decisions
    assert trace.input_sha256 == second.input_sha256
    assert trace.trace_id != second.trace_id
    assert trace.completed is False
    assert trace.candidate_outcome is None
    assert len(trace.decisions) == 2
    assert trace.source_kind == "native-game-diagnostic-not-gate"
    assert trace.promotion_eligible is False
    assert "passed" not in trace.model_dump()
    assert (directory / "manifest.json").read_bytes() == before
    assert all(row.action_name in row.legal_action_names for row in trace.decisions)
    _, versus_self = trace_simulation_game(
        **{**kwargs, "config": SimulationTraceConfig(ruleset="fixed-role", max_decisions=512)},
        opponent_model_directory=directory,
    )
    assert versus_self.opponent_weights_sha256 == manifest.weights_sha256
    assert versus_self.completed
    assert versus_self.candidate_outcome in (-1, 0, 1)


def test_trace_rejects_checkpoint_layout_mismatch_before_writing(tmp_path: Path) -> None:
    bible = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    manifest = initialize_model(
        tmp_path,
        ArtifactVocabulary.from_snapshot(bible),
        client_sha256=bible.client.sha256,
        feature_schema_version=LEGACY_FEATURE_SCHEMA_VERSION,
        global_feature_count=6,
    )
    with pytest.raises(ValueError, match="observation schema"):
        trace_simulation_game(
            candidate_model_directory=tmp_path / manifest.model_id,
            snapshot_path=SNAPSHOT,
            trace_directory=tmp_path / "traces",
            config=SimulationTraceConfig(),
        )
    assert not (tmp_path / "traces").exists()
