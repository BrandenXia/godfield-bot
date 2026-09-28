import json
from pathlib import Path

import pytest

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.simulation import _with_gift_rates, create_attack_defense_simulation
from godfield_bot.simulation_policy import build_curriculum_heuristic, curriculum_heuristic_actions

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
SNAPSHOT = Path("data/snapshots/2026-09-20/bible.json")
WEIGHTED = "gift-weighted-dream-resource-hand"


def test_accepted_bible_gift_rates_match_official_raw_catalog() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    api = json.loads(Path("data/snapshots/2026-09-21/api-catalog-en.json").read_text())
    raw = {item["raw"]["imageName"]: item["raw"] for item in api["items"]}
    denominator = sum(item.get("giftRate", 0) for item in raw.values())
    assert denominator == 500
    for records in snapshot.catalog.values():
        for item in records.items:
            gift = [line for line in item.detail if line.startswith("Gift Rate:")]
            if gift:
                assert gift == [f"Gift Rate: {raw[item.asset]['giftRate']}/{denominator}"]


def test_weighted_contract_preserves_schema_but_changes_distribution_identity() -> None:
    legacy = create_attack_defense_simulation(SNAPSHOT, batch_size=2, ruleset="dream-resource-hand")
    weighted = create_attack_defense_simulation(SNAPSHOT, batch_size=2, ruleset=WEIGHTED)
    assert not legacy.batch.gift_weighted
    assert weighted.batch.gift_weighted
    assert weighted.metadata.observation_schema_version == 10
    assert weighted.metadata.rule_catalog_size == 196
    assert weighted.metadata.global_feature_count == 24
    assert weighted.metadata.ruleset_id == "gift-weighted-" + legacy.metadata.ruleset_id
    assert weighted.metadata.rule_catalog_sha256 != legacy.metadata.rule_catalog_sha256
    assert legacy.metadata.rule_catalog_sha256 == (
        "135904026bf45efbe31a2f5bd4c0c15ed2e252311b41b5d9cf804486f1e57afa"
    )
    assert not weighted.metadata.promotion_eligible
    assert np.all(weighted.batch.episode_ids == 1)


def test_native_configuration_rejects_bad_weights_without_changing_batch() -> None:
    simulation = create_attack_defense_simulation(
        SNAPSHOT, batch_size=4, ruleset="dream-resource-hand"
    )
    batch = simulation.batch
    initial_hand = batch.hand_token_ids.copy()
    cases = (
        ([1, 1], [1, 1], "unique"),
        ([1], [0], "positive"),
        ([1], [1, 2], "lengths"),
        ([1], [1], "exact Dream catalog"),
    )
    for tokens, weights, message in cases:
        with pytest.raises(ValueError, match=message):
            batch.configure_gift_weights(
                np.asarray(tokens, dtype=np.uint32), np.asarray(weights, dtype=np.uint16)
            )
        assert not batch.gift_weighted
        np.testing.assert_array_equal(batch.hand_token_ids, initial_hand)
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    all_tokens = np.asarray(
        [
            vocabulary.token_id(category, item.asset)
            for category, records in snapshot.catalog.items()
            for item in records.items
        ],
        dtype=np.uint32,
    )
    with pytest.raises(ValueError, match="unsupported tokens"):
        batch.configure_gift_weights(all_tokens, np.ones(len(all_tokens), dtype=np.uint16))
    assert not batch.gift_weighted
    np.testing.assert_array_equal(batch.hand_token_ids, initial_hand)
    batch.step(batch.action_mask.argmax(axis=1).astype(np.int64))
    with pytest.raises(ValueError, match="unstepped"):
        batch.configure_gift_weights(
            np.asarray([1], dtype=np.uint32), np.asarray([1], dtype=np.uint16)
        )
    weighted = create_attack_defense_simulation(SNAPSHOT, batch_size=1, ruleset=WEIGHTED)
    with pytest.raises(ValueError, match="unconfigured"):
        weighted.batch.configure_gift_weights(
            np.asarray([1], dtype=np.uint32), np.asarray([1], dtype=np.uint16)
        )


@pytest.mark.parametrize(
    "detail",
    [
        (),
        ("Gift Rate: 0/500",),
        ("Gift Rate: 1/501",),
        ("Gift Rate: 1/500", "Gift Rate: 1/500"),
        ("Gift Rate: nope",),
        ("Gift Rate: 65536/500",),
        ("Gift Rate: 501/500",),
    ],
)
def test_python_rates_fail_closed(detail: tuple[str, ...]) -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    item = snapshot.catalog["weapons"].items[0]
    item.detail = detail
    with pytest.raises(ValueError, match="invalid accepted gift rate"):
        _with_gift_rates([{"slug": item.asset, "token_id": 1}], snapshot)


def test_gift_ratios_follow_bible_instead_of_uniform_card_counts() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    common = vocabulary.token_id("weapons", "hatchet")
    rare = vocabulary.token_id("weapons", "silver-club")
    # Same initial role and same native family: official numerators are 6 and 1.
    for ruleset, expected in ((WEIGHTED, 6 / 7), ("dream-resource-hand", 0.5)):
        batch = create_attack_defense_simulation(
            SNAPSHOT, batch_size=16384, seed=719, ruleset=ruleset
        ).batch
        counts = [0, 0]
        for _ in range(2):
            counts[0] += int(np.count_nonzero(batch.hand_token_ids == common))
            counts[1] += int(np.count_nonzero(batch.hand_token_ids == rare))
            batch.reset()
        assert min(counts) > 100
        assert abs(counts[0] / sum(counts) - expected) < 0.025


def test_seeded_weighted_trajectories_complete_and_reset_deterministically() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    heuristic = build_curriculum_heuristic(
        snapshot, ArtifactVocabulary.from_snapshot(snapshot), ruleset=WEIGHTED
    )
    first = create_attack_defense_simulation(SNAPSHOT, batch_size=64, seed=829, ruleset=WEIGHTED)
    second = create_attack_defense_simulation(SNAPSHOT, batch_size=64, seed=829, ruleset=WEIGHTED)
    completed = 0
    for _ in range(512):
        a, b = first.batch, second.batch
        np.testing.assert_array_equal(a.hand_token_ids, b.hand_token_ids)
        np.testing.assert_array_equal(a.actual_hand_token_ids, b.actual_hand_token_ids)
        np.testing.assert_array_equal(a.global_features, b.global_features)
        np.testing.assert_array_equal(a.action_mask, b.action_mask)
        actions = curriculum_heuristic_actions(first, np.arange(a.batch_size), heuristic)
        assert np.all(a.action_mask[np.arange(a.batch_size), actions])
        a.step(actions)
        b.step(actions)
        done = a.reset_done()
        assert done == b.reset_done()
        completed += done
    assert completed > 64


def test_consumed_cards_redraw_from_the_full_weighted_supported_pool() -> None:
    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    simulation = create_attack_defense_simulation(
        SNAPSHOT, batch_size=32768, seed=927, initial_hp=100, ruleset=WEIGHTED
    )
    batch = simulation.batch
    supported = np.unique(batch.hand_token_ids)
    assert len(supported) == simulation.metadata.rule_catalog_size
    rates = {}
    for category, records in snapshot.catalog.items():
        for item in records.items:
            gift = [line for line in item.detail if line.startswith("Gift Rate:")]
            if gift:
                rates[vocabulary.token_id(category, item.asset)] = int(
                    gift[0].split(": ")[1].split("/")[0]
                )
    rows = np.arange(batch.batch_size)
    first_actor = batch.active_players.copy()
    first_actions = batch.action_mask.argmax(axis=1).astype(np.int64)
    slots = first_actions - 1
    assert np.all((slots >= 0) & (slots < 9))
    # Track only ordinary attacks by both seats: no curse, miss, bounce, or kill.
    tracked = batch.hand_card_kinds[rows, slots] == 1

    def advance(actions) -> None:
        nonlocal tracked
        batch.step(actions)
        tracked &= ~batch.terminated
        batch.reset_done()

    advance(first_actions)
    advance(np.where(batch.action_mask[:, 20], 20, batch.action_mask.argmax(axis=1)))
    advance(np.where(batch.action_mask[:, 19], 19, batch.action_mask.argmax(axis=1)))
    other_actions = batch.action_mask.argmax(axis=1).astype(np.int64)
    safe_slots = np.clip(other_actions - 1, 0, 8)
    tracked &= batch.hand_card_kinds[rows, safe_slots] == 1
    advance(other_actions)
    advance(np.where(batch.action_mask[:, 20], 20, batch.action_mask.argmax(axis=1)))
    tracked &= (batch.phases == 1) & (batch.active_players == first_actor)
    received = batch.actual_hand_token_ids[rows[tracked], slots[tracked]]
    assert len(received) > 1000
    assert set(received) <= set(supported)
    expected_weights = np.asarray([rates[int(token)] for token in supported])
    expected = len(received) * expected_weights / expected_weights.sum()
    counts = np.asarray([np.count_nonzero(received == token) for token in supported])
    # Independent role-conditioned deals should not leak into ordinary redraws.
    assert np.max(np.abs(counts - expected) / np.sqrt(expected)) < 6


def test_weighted_league_training_preserves_sampler_provenance(tmp_path: Path) -> None:
    from godfield_bot.model_registry import initialize_model
    from godfield_bot.simulation_league import create_simulation_league, load_simulation_league
    from godfield_bot.simulation_training import (
        SimulationTrainingConfig,
        train_simulation_candidate,
    )

    snapshot = BibleSnapshot.model_validate_json(SNAPSHOT.read_text())
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    root = tmp_path / "models"
    parent = initialize_model(
        root,
        vocabulary,
        client_sha256=snapshot.client.sha256,
        feature_schema_version=10,
        global_feature_count=24,
    )
    base = root / parent.model_id
    path, league = create_simulation_league(
        base_model_directory=base,
        opponent_model_directories=(),
        snapshot_path=SNAPSHOT,
        league_directory=tmp_path / "leagues",
        ruleset=WEIGHTED,
    )
    with pytest.raises(ValueError, match="simulator contract"):
        load_simulation_league(
            path,
            reference=parent,
            simulation=create_attack_defense_simulation(
                SNAPSHOT, batch_size=1, ruleset="dream-resource-hand"
            ).metadata,
            heuristic=build_curriculum_heuristic(snapshot, vocabulary, ruleset=WEIGHTED),
            ruleset=WEIGHTED,
            device="cpu",
            required_parent_id=parent.model_id,
        )
    child = train_simulation_candidate(
        base_model_directory=base,
        model_root=root,
        snapshot_path=SNAPSHOT,
        league_path=path,
        config=SimulationTrainingConfig(
            ruleset=WEIGHTED,
            batch_size=8,
            rollout_steps=6,
            updates=1,
            teacher_updates=0,
            ppo_epochs=1,
            environment_minibatch_size=4,
        ),
    )
    assert child.training_context["league_sha256"] == league.sha256
    assert child.training_context["simulation"] == league.simulation.model_dump(mode="json")
    assert child.training_context["config"]["ruleset"] == WEIGHTED
