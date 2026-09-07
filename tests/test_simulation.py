import gc
from pathlib import Path

import pytest

from godfield_bot.simulation import (
    benchmark_fixed_attack_simulation,
    create_fixed_attack_simulation,
    simulation_feature_tensors,
)

np = pytest.importorskip("numpy")
godfield_sim = pytest.importorskip("godfield_sim")
FixedAttackBatch = godfield_sim.FixedAttackBatch

SNAPSHOT_PATH = Path(__file__).parents[1] / "data" / "snapshots" / "2026-09-07" / "bible.json"


def native_batch(*, batch_size: int = 4, attack: int = 13) -> FixedAttackBatch:
    return FixedAttackBatch(
        batch_size,
        np.asarray([2], dtype=np.uint32),
        np.asarray([attack], dtype=np.uint16),
        67,
        40,
    )


def first_legal_actions(batch: FixedAttackBatch) -> np.ndarray:
    return batch.action_mask.argmax(axis=1).astype(np.int64)


def test_snapshot_factory_fingerprints_non_promotable_curriculum() -> None:
    simulation = create_fixed_attack_simulation(SNAPSHOT_PATH, batch_size=8)

    assert simulation.metadata.kernel_schema_version == 2
    assert simulation.metadata.ruleset_id == "plain-attack-redraw-duel-v1"
    assert simulation.metadata.rule_catalog_size == 18
    assert simulation.metadata.action_count == 21
    assert simulation.metadata.hand_slots == 9
    assert simulation.metadata.sampling_distribution == "uniform-redraw-with-replacement"
    assert simulation.metadata.promotion_eligible is False
    assert simulation.batch.batch_size == 8


def test_native_views_match_policy_shapes_and_are_read_only() -> None:
    batch = native_batch()

    assert batch.global_features.shape == (4, 4)
    assert batch.player_features.shape == (4, 2, 4)
    assert batch.player_mask.shape == (4, 2)
    assert batch.hand_token_ids.shape == (4, 9)
    assert batch.hand_mask.shape == (4, 9)
    assert batch.action_mask.shape == (4, 21)
    assert batch.terminal_returns.shape == (4, 2)
    assert batch.action_mask.dtype == np.bool_
    assert batch.global_features.dtype == np.float32
    assert not batch.global_features.flags.writeable
    assert not batch.action_mask.flags.writeable
    assert np.all(batch.action_mask[:, 1:10])
    assert not np.any(batch.action_mask[:, 0])
    assert not np.any(batch.action_mask[:, 10:])


def test_identical_seeds_produce_identical_batched_transitions() -> None:
    first = native_batch(batch_size=16)
    second = native_batch(batch_size=16)

    for _ in range(3):
        actions = first_legal_actions(first)
        first.step(actions)
        second.step(actions.copy())

    np.testing.assert_array_equal(first.active_players, second.active_players)
    np.testing.assert_array_equal(first.hand_token_ids, second.hand_token_ids)
    np.testing.assert_array_equal(first.global_features, second.global_features)
    np.testing.assert_array_equal(first.terminal_returns, second.terminal_returns)


def test_nonterminal_attacks_redraw_into_the_consumed_slot() -> None:
    batch = native_batch(batch_size=8, attack=1)

    batch.step(first_legal_actions(batch))
    batch.step(first_legal_actions(batch))

    assert not np.any(batch.terminated)
    assert np.all(batch.hand_mask)
    assert np.all(batch.hand_token_ids > 0)
    assert np.all(batch.action_mask[:, 1:10])


def test_curriculum_no_longer_ends_in_an_artificial_empty_hand_draw() -> None:
    batch = native_batch(batch_size=8, attack=1)

    for _ in range(18):
        batch.step(first_legal_actions(batch))

    assert not np.any(batch.terminated)
    assert np.all(batch.terminal_returns == 0)
    assert np.all(batch.action_mask[:, 1:10])


def test_terminal_step_emits_only_sparse_seat_returns() -> None:
    batch = native_batch(batch_size=32, attack=100)
    actors = batch.active_players.copy()

    batch.step(first_legal_actions(batch))

    assert np.all(batch.terminated)
    assert not np.any(batch.action_mask)
    for actor, returns in zip(actors, batch.terminal_returns, strict=True):
        assert returns[int(actor)] == 1.0
        assert returns[1 - int(actor)] == -1.0


def test_terminal_rows_must_be_consumed_before_reset() -> None:
    batch = native_batch(batch_size=3, attack=100)
    batch.step(first_legal_actions(batch))
    episode_ids = batch.episode_ids.copy()

    with pytest.raises(RuntimeError, match="call reset_done"):
        batch.step(np.ones(3, dtype=np.int64))

    assert batch.reset_done() == 3
    np.testing.assert_array_equal(batch.episode_ids, episode_ids + 1)
    assert not np.any(batch.terminated)
    assert np.all(batch.action_mask[:, 1:10])


def test_invalid_action_rejects_batch_without_partial_transition() -> None:
    batch = native_batch(batch_size=3)
    before = batch.global_features.copy()
    actions = first_legal_actions(batch)
    actions[1] = 20

    with pytest.raises(ValueError, match="environment 1 selected an action outside"):
        batch.step(actions)

    np.testing.assert_array_equal(batch.global_features, before)
    np.testing.assert_array_equal(batch.turn_numbers, np.zeros(3, dtype=np.uint16))


def test_native_catalog_rejects_duplicate_token_id_semantics() -> None:
    with pytest.raises(ValueError, match="catalog token IDs must be unique"):
        FixedAttackBatch(
            1,
            np.asarray([2, 2], dtype=np.uint32),
            np.asarray([3, 13], dtype=np.uint16),
        )


def test_view_keeps_native_owner_alive() -> None:
    batch = native_batch(batch_size=2)
    view = batch.global_features
    del batch
    gc.collect()

    assert view.shape == (2, 4)
    assert np.isfinite(view).all()


def test_pytorch_inference_views_share_native_buffers() -> None:
    torch = pytest.importorskip("torch")
    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.features import ArtifactVocabulary
    from godfield_bot.neural import RecurrentPolicyValueNet

    simulation = create_fixed_attack_simulation(SNAPSHOT_PATH, batch_size=8)
    global_array = simulation.batch.global_features

    tensors = simulation_feature_tensors(simulation)
    vocabulary = ArtifactVocabulary.from_snapshot(
        BibleSnapshot.model_validate_json(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    )
    model = RecurrentPolicyValueNet(vocabulary_size=len(vocabulary.tokens), action_count=21)
    logits, values, recurrent_state = model(*tensors)

    assert tensors[0].data_ptr() == global_array.__array_interface__["data"][0]
    assert tensors[0].dtype == torch.float32
    assert tensors[5].dtype == torch.bool
    assert tensors[5].shape == (8, 21)
    assert logits.shape == (8, 21)
    assert values.shape == (8,)
    assert recurrent_state.shape == (8, 128)


def test_benchmark_collects_full_batches() -> None:
    result = benchmark_fixed_attack_simulation(
        SNAPSHOT_PATH,
        batch_size=128,
        batch_steps=30,
    )

    assert result.transitions == 3840
    assert result.completed_episodes > 0
    assert result.transitions_per_second > 0
