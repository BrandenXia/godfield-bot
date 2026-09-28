from datetime import UTC, datetime
from pathlib import Path

import pytest

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary, FeatureEncodingError, StateFeatureEncoder
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.model_registry import (
    ModelStatus,
    initialize_model,
    load_model,
    migrate_hand_capacity,
)
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_policy import build_curriculum_heuristic, curriculum_heuristic_actions
from godfield_bot.simulation_training import SimulationTrainingConfig, train_simulation_candidate
from godfield_bot.training_shadow import TrainingShadowError, _validate_model

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")
SNAPSHOT = Path("data/snapshots/2026-09-20/bible.json")
WEIGHTED = "gift-weighted-dream-resource-hand"
WIDE = "wide-hand-gift-weighted-dream-resource-hand"
MAPPING = [*range(10), *range(19, 30)]


def bible_and_vocabulary():
    bible = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    return bible, ArtifactVocabulary.from_snapshot(bible)


def migrated_model(root: Path):
    bible, vocabulary = bible_and_vocabulary()
    source = initialize_model(
        root,
        vocabulary,
        client_sha256=bible.client.sha256,
        feature_schema_version=10,
        global_feature_count=24,
    )
    migrated = migrate_hand_capacity(
        root / source.model_id, root, vocabulary, client_sha256=bible.client.sha256
    )
    return source, migrated


def test_wide_layout_padding_and_deterministic_play() -> None:
    bible, vocabulary = bible_and_vocabulary()
    heuristic = build_curriculum_heuristic(bible, vocabulary, ruleset=WIDE)
    first = create_attack_defense_simulation(SNAPSHOT, batch_size=64, seed=197, ruleset=WIDE)
    second = create_attack_defense_simulation(SNAPSHOT, batch_size=64, seed=197, ruleset=WIDE)
    assert first.metadata.observation_schema_version == 11
    assert first.metadata.hand_slots == 18
    assert first.metadata.action_count == 30
    assert not first.metadata.promotion_eligible
    assert first.batch.forgive_action_index == 28
    assert first.batch.confirm_action_index == 29
    assert set(first.batch.hand_sizes.flatten()) == set(range(9, 19))
    completed = overflow_actions = 0
    for _ in range(512):
        a, b = first.batch, second.batch
        np.testing.assert_array_equal(a.hand_token_ids, b.hand_token_ids)
        np.testing.assert_array_equal(a.global_features, b.global_features)
        np.testing.assert_array_equal(a.action_mask, b.action_mask)
        size = a.hand_sizes[np.arange(64), a.active_players]
        padded = np.arange(18)[None, :] >= size[:, None]
        assert not np.any(a.hand_token_ids[padded])
        assert not np.any(a.hand_mask[padded])
        assert not np.any(a.action_mask[:, 1:19][padded])
        assert not np.any(a.action_mask[:, 19:28])  # Reserved multiplayer targets.
        actions = curriculum_heuristic_actions(first, np.arange(64), heuristic)
        assert np.all(a.action_mask[np.arange(64), actions])
        overflow_actions += int(np.count_nonzero((actions >= 10) & (actions <= 18)))
        a.step(actions)
        b.step(actions)
        done = a.reset_done()
        assert done == b.reset_done()
        completed += done
    assert completed > 64
    assert overflow_actions > 100


def test_nine_card_padded_trajectories_are_identical() -> None:
    old = create_attack_defense_simulation(SNAPSHOT, batch_size=32, seed=813, ruleset=WEIGHTED)
    wide = create_attack_defense_simulation(SNAPSHOT, batch_size=32, seed=813, ruleset=WEIGHTED)
    wide.batch.configure_hand_capacity(9, 9)
    bible, vocabulary = bible_and_vocabulary()
    heuristic = build_curriculum_heuristic(bible, vocabulary, ruleset=WEIGHTED)
    for _ in range(512):
        a, b = old.batch, wide.batch
        np.testing.assert_array_equal(a.global_features, b.global_features)
        np.testing.assert_array_equal(a.hand_token_ids, b.hand_token_ids[:, :9])
        np.testing.assert_array_equal(a.actual_hand_token_ids, b.actual_hand_token_ids[:, :9])
        np.testing.assert_array_equal(a.action_mask, b.action_mask[:, MAPPING])
        actions = curriculum_heuristic_actions(old, np.arange(32), heuristic)
        a.step(actions)
        b.step(np.asarray(MAPPING, dtype=np.int64)[actions])
        assert a.reset_done() == b.reset_done()


@pytest.mark.parametrize(
    "view",
    [
        "hand_token_ids",
        "actual_hand_token_ids",
        "hand_mask",
        "hand_card_kinds",
        "hand_elements",
        "action_mask",
        "selected_hand_mask",
    ],
)
def test_resize_rejects_exposed_views(view: str) -> None:
    batch = create_attack_defense_simulation(SNAPSHOT, batch_size=2, ruleset=WEIGHTED).batch
    held = getattr(batch, view)
    saved = held.copy()
    with pytest.raises(ValueError, match="exposed hand views"):
        batch.configure_hand_capacity()
    np.testing.assert_array_equal(held, saved)
    assert batch.hand_slots == 9


def test_configuration_rejects_invalid_ranges_and_repeated_configuration() -> None:
    batch = create_attack_defense_simulation(SNAPSHOT, batch_size=2, ruleset=WEIGHTED).batch
    for minimum, maximum in ((8, 18), (9, 19), (18, 9)):
        with pytest.raises(ValueError, match=r"9\.\.18"):
            batch.configure_hand_capacity(minimum, maximum)
        assert batch.hand_slots == 9
    batch.configure_hand_capacity()
    with pytest.raises(ValueError, match="unstepped"):
        batch.configure_hand_capacity()
    legacy = create_attack_defense_simulation(SNAPSHOT, batch_size=2, ruleset="dream-resource-hand")
    with pytest.raises(ValueError, match="gift-weighted"):
        legacy.batch.configure_hand_capacity()
    stepped = create_attack_defense_simulation(SNAPSHOT, batch_size=2, ruleset=WEIGHTED).batch
    stepped.step(stepped.action_mask.argmax(axis=1).astype(np.int64))
    with pytest.raises(ValueError, match="unstepped"):
        stepped.configure_hand_capacity()


def test_migration_preserves_weights_outputs_and_memory(tmp_path: Path) -> None:
    source, migrated = migrated_model(tmp_path)
    _, old_model = load_model(tmp_path / source.model_id)
    _, wide_model = load_model(tmp_path / migrated.model_id)
    assert migrated.status == ModelStatus.INITIALIZED
    assert migrated.parent_model_id == source.model_id
    assert migrated.feature_schema_version == 11
    assert migrated.architecture.action_count == 30
    assert migrated.metrics == {}
    assert "simulation" not in migrated.training_context
    assert migrated.training_context["action_mapping"] == MAPPING
    for name, value in old_model.state_dict().items():
        actual = wide_model.state_dict()[name]
        if name.startswith("policy_head."):
            torch.testing.assert_close(actual[MAPPING], value, rtol=0, atol=0)
            assert not torch.count_nonzero(actual[10:19])
        else:
            torch.testing.assert_close(actual, value, rtol=0, atol=0)
    torch.manual_seed(857)
    globals_ = torch.randn(8, 24)
    players = torch.randn(8, 2, 4)
    player_mask = torch.ones(8, 2, dtype=torch.bool)
    hand = torch.randint(1, source.architecture.vocabulary_size, (8, 9))
    mask = torch.ones(8, 9, dtype=torch.bool)
    actions = torch.ones(8, 21, dtype=torch.bool)
    padded = torch.cat((hand, torch.zeros(8, 9, dtype=torch.long)), dim=1)
    padded_mask = torch.cat((mask, torch.zeros(8, 9, dtype=torch.bool)), dim=1)
    expanded = torch.zeros(8, 30, dtype=torch.bool)
    expanded[:, MAPPING] = actions
    memory = torch.randn(8, source.architecture.hidden_size)
    with torch.no_grad():
        old = old_model(globals_, players, player_mask, hand, mask, actions, memory)
        new = wide_model(globals_, players, player_mask, padded, padded_mask, expanded, memory)
    torch.testing.assert_close(old[0], new[0][:, MAPPING], atol=1e-6, rtol=1e-6)
    torch.testing.assert_close(old[1], new[1], atol=1e-6, rtol=1e-6)
    torch.testing.assert_close(old[2], new[2], atol=1e-6, rtol=1e-6)
    torch.testing.assert_close(old[0].softmax(-1), new[0].softmax(-1)[:, MAPPING])
    # The same artifact scorer works in the final extra slot, without new weights.
    only_last = torch.zeros(8, 30, dtype=torch.bool)
    only_last[:, 18] = True
    padded[:, 17] = hand[:, 0]
    padded_mask[:, 17] = True
    assert torch.all(
        wide_model(globals_, players, player_mask, padded, padded_mask, only_last)[0].argmax(-1)
        == 18
    )


def test_schema_eleven_layout_validation_and_live_rejection(tmp_path: Path) -> None:
    bible, vocabulary = bible_and_vocabulary()
    with pytest.raises(ValueError, match="18 hand slots"):
        initialize_model(
            tmp_path,
            vocabulary,
            client_sha256=bible.client.sha256,
            feature_schema_version=11,
            global_feature_count=24,
        )
    with pytest.raises(ValueError, match="18 hand slots"):
        StateFeatureEncoder(vocabulary, bible, feature_schema_version=11)
    encoder = StateFeatureEncoder(vocabulary, bible, feature_schema_version=11, max_hand_slots=18)
    assert 3 + encoder.max_hand_slots + encoder.max_players == 30
    source, migrated = migrated_model(tmp_path)
    with pytest.raises(ValueError, match="21-action schema-v10"):
        migrate_hand_capacity(
            tmp_path / migrated.model_id, tmp_path, vocabulary, client_sha256=bible.client.sha256
        )
    with pytest.raises(ValueError, match="fingerprint"):
        migrate_hand_capacity(
            tmp_path / source.model_id, tmp_path, vocabulary, client_sha256="a" * 64
        )
    candidate = migrated.model_copy(update={"status": ModelStatus.CANDIDATE})
    with pytest.raises(TrainingShadowError, match="schema-v10"):
        _validate_model(candidate, vocabulary, bible)


def test_wide_candidate_can_train_locally(tmp_path: Path) -> None:
    _, migrated = migrated_model(tmp_path)
    candidate = train_simulation_candidate(
        base_model_directory=tmp_path / migrated.model_id,
        snapshot_path=SNAPSHOT,
        model_root=tmp_path,
        config=SimulationTrainingConfig(
            ruleset=WIDE,
            batch_size=8,
            rollout_steps=16,
            updates=1,
            teacher_updates=0,
            ppo_epochs=1,
            minibatch_size=8,
            environment_minibatch_size=8,
            device="cpu",
        ),
    )
    assert candidate.feature_schema_version == 11
    assert candidate.architecture.action_count == 30
    assert candidate.training_context["simulation"]["hand_slots"] == 18
    assert candidate.metrics["ppo_transitions"] == 128
    assert 0 <= candidate.metrics["extra_slot_action_fraction"] <= 1
    assert candidate.metrics["extra_slot_action_count"] == (
        candidate.metrics["extra_slot_action_fraction"] * 128
    )


def test_schema_eleven_encodes_extra_slots_and_rejects_selectable_overflow() -> None:
    bible, vocabulary = bible_and_vocabulary()
    encoder = StateFeatureEncoder(vocabulary, bible, feature_schema_version=11, max_hand_slots=18)
    artifact = HandArtifact(
        slot=0,
        category="weapons",
        slug="hatchet",
        asset_path="/images/items/weapons/hatchet.webp",
        bounds=Bounds(x=0, y=0, width=80, height=80),
    )
    state = GameState(
        observed_at=datetime.now(UTC),
        field_number=0,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=40, mp=10, money=0, is_self=True),
            PlayerState(name="CPU", hp=40, mp=10, money=0, is_self=False),
        ),
        hand=tuple(artifact.model_copy(update={"slot": slot}) for slot in range(18)),
        scene_layers=(),
    )
    action = LegalAction(
        action_id="last-card",
        kind=ActionKind.SELECT_ARTIFACT,
        label="Select last card",
        artifact_slot=17,
        artifact_asset_path=artifact.asset_path,
    )
    legal = LegalActionSet(
        state_digest=game_state_digest(state), actions=(action,), coverage_complete=True
    )
    features = encoder.encode(state, legal)
    assert features.schema_version == 11
    assert len(features.global_features) == 24
    assert len(features.hand_token_ids) == 18
    assert all(features.hand_mask)
    assert sum(features.action_mask) == 1 and features.action_mask[18]
    with pytest.raises(FeatureEncodingError, match="selectable overflow"):
        StateFeatureEncoder(vocabulary, bible, feature_schema_version=10).encode(state, legal)
    overflow = state.model_copy(
        update={
            "hand": (
                *state.hand,
                artifact.model_copy(update={"slot": 18}),
            )
        }
    )
    legal = LegalActionSet(
        state_digest=game_state_digest(overflow),
        actions=(action.model_copy(update={"artifact_slot": 18}),),
        coverage_complete=True,
    )
    with pytest.raises(FeatureEncodingError, match="selectable overflow"):
        encoder.encode(overflow, legal)


def test_schema_eleven_loading_rejects_a_mislabeled_action_layout(tmp_path: Path) -> None:
    _, migrated = migrated_model(tmp_path)
    invalid = migrated.model_copy(
        update={"architecture": (migrated.architecture.model_copy(update={"action_count": 21}))}
    )
    (tmp_path / migrated.model_id / "manifest.json").write_text(invalid.model_dump_json())
    with pytest.raises(ValueError, match="30-action"):
        load_model(tmp_path / migrated.model_id)
