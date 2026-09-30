"""Explicit nine-feature utility episodes and a separately pinned gift stream."""

import json
from dataclasses import fields
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

from godfield_bot.api_catalog import read_api_catalog_snapshot  # noqa: E402
from godfield_bot.cli import app  # noqa: E402
from godfield_bot.domain.reference import BibleSnapshot  # noqa: E402
from godfield_bot.guardian_refill import REFILL_PROFILE_SHA256  # noqa: E402
from godfield_bot.guardian_rollout import (  # noqa: E402
    CONFIRM,
    FORGIVE,
    TARGET_START,
    GuardianRolloutArena,
    GuardianRolloutConfig,
    GuardianRolloutMetadata,
    collect_guardian_rollout,
    greedy_guardian_actions,
)
from godfield_bot.guardian_utility_refill import (  # noqa: E402
    UTILITY_REFILL_PROFILE_SHA256,
    GuardianUtilityRefillPlan,
    build_guardian_utility_refill_plan,
)

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def arena(**kwargs):
    return GuardianRolloutArena(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        config=GuardianRolloutConfig(
            **{
                "batch_size": 2,
                "inventory_utilities": True,
                "opening": "cards-only",
                **kwargs,
            }
        ),
    )


def prepare(game, hands):
    game._native.reset_environments(ids(range(game.config.batch_size)))
    for env in range(game.config.batch_size):
        for player, models in enumerate(hands):
            count = len(models)
            game._native.deal_cards(
                ids([env] * count),
                ids([player] * count),
                ids(range(count)),
                ids(range(100 + player * 18, 100 + player * 18 + count)),
                ids(models),
            )


def assert_equal_observations(left, right):
    for field in fields(left):
        np.testing.assert_array_equal(getattr(left, field.name), getattr(right, field.name))


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("refill", ["none", "weighted-utility-consumption-v1"])
def test_opening_projection_shapes_source_tags_and_hidden_hands(players, refill):
    game = arena(player_count=players, refill=refill)
    obs = game.observe()
    assert obs.hand_features.shape == (2, 18, 9)
    assert obs.global_features.shape == (2, 43) and obs.action_mask.shape == (2, 30)
    assert np.all(obs.hand_mask.sum(axis=1) == 9)
    assert np.all((obs.hand_features[:, :, 7] > 0).sum(axis=1) >= 2)
    assert np.all((obs.hand_features[:, :, 8] > 0).sum(axis=1) >= 1)
    raw = game._native.actor_hand_snapshot()
    np.testing.assert_allclose(obs.hand_features[:, :, 7:], raw[:, :, 9:] / 100)
    np.testing.assert_allclose(obs.hand_features[:, :, 0], raw[:, :, 3] / 7)
    assert game.metadata.schema_version == 2 and game.metadata.hand_feature_count == 9
    assert game.metadata.observation_schema_id == "actor-relative-guardian-utility-arena-v2"
    assert not game.metadata.full_game_training_ready and not game.metadata.promotion_eligible
    for field in fields(obs):
        assert not getattr(obs, field.name).flags.writeable
    game._native.deal_cards(ids([0]), ids([1]), ids([17]), ids([999]), ids([194]))
    assert_equal_observations(obs, game.observe())
    changed = game.step(ids([0, 0])).observation
    assert changed.hand_model_ids[0, 17] == 194
    assert changed.hand_features[0, 17, 7] == pytest.approx(0.2)


def test_immediate_utility_consumption_cost_and_potential_rewards():
    game = arena(initial_hp=96, initial_mp=7)
    prepare(game, [[191, 235], [195]])
    initial = game.observe()
    result = game.step(ids([1, 2]))
    assert result.observation.phases.tolist() == [0, 0]
    assert result.observation.actors.tolist() == [1, 1]
    np.testing.assert_array_equal(game._native.resource_snapshot()[:, 0, :2], [[100, 7], [100, 0]])
    assert game._native.inventory_snapshot()[0, 0, 0, 0] == 0
    assert game._native.inventory_snapshot()[1, 0, 1, 1] == 235
    np.testing.assert_allclose(result.rewards.sum(axis=1), 0, atol=1e-7)
    expected = 0.1 * 0.99 * np.asarray([0.04, 0.04 - 0.05 * 7 / 100])
    np.testing.assert_allclose(result.rewards[:, 0], expected, atol=1e-7)
    assert game.utility_statistics.model_dump() == {
        "uses": 2,
        "consumed_items": 1,
        "miracle_casts": 1,
        "mp_spent": 7,
        "hp_gained": 8,
        "mp_gained": 0,
    }
    assert initial.hand_model_ids[0, 0] == 191


def test_consumed_utility_refills_once_in_same_slot_but_spring_is_retained():
    game = arena(refill="weighted-utility-consumption-v1")
    prepare(game, [[191, 235], [195]])
    game._refill_models = ids([197])
    game._refill_cumulative = ids([1])
    game.step(ids([1, 2]))
    inventory = game._native.inventory_snapshot()
    assert inventory[0, 0, 0, 1] == 197 and inventory[0, 0, 0, 0] == 19
    assert inventory[1, 0, 1, 1] == 235
    assert game.replacement_gifts == 1 and not any(game._pending_refills)
    game.step(ids([1, 1]))
    assert game.replacement_gifts == 3 and game.utility_statistics.uses == 4
    assert game.utility_statistics.mp_gained == 10


@pytest.mark.parametrize("limit", ["turn", "decision"])
def test_terminal_utility_drops_refill_without_sampling_and_resets_explicitly(limit):
    config = {"max_turns": 1} if limit == "turn" else {"max_decisions": 1}
    game = arena(refill="weighted-utility-consumption-v1", **config)
    prepare(game, [[191], [195]])
    rng_states = [game._refill_rngs[e].bit_generator.state for e in range(2)]
    result = game.step(ids([1, 1]))
    assert np.all(result.truncated) and not np.any(result.observation.action_mask)
    assert not np.any(result.observation.hand_features)
    assert game.replacement_gifts == 0 and not any(game._pending_refills)
    assert [game._refill_rngs[e].bit_generator.state for e in range(2)] == rng_states
    before = game.utility_statistics
    game.step(ids([-1, -1]))
    assert game.utility_statistics == before
    fresh = game.reset_done()
    assert np.all(fresh.active) and np.all(fresh.episode_ids == 1)
    assert game.utility_statistics == before


def test_failed_second_row_does_not_use_first_utility_or_advance_rng():
    game = arena(refill="weighted-utility-consumption-v1", initial_mp=6)
    prepare(game, [[191, 235], [195]])
    before = game.observe()
    resources = game._native.resource_snapshot()
    rng_states = [game._refill_rngs[e].bit_generator.state for e in range(2)]
    with pytest.raises(ValueError, match="illegal arena action"):
        game.step(ids([1, 2]))
    assert_equal_observations(before, game.observe())
    np.testing.assert_array_equal(resources, game._native.resource_snapshot())
    assert game.utility_statistics.uses == game.replacement_gifts == 0
    assert [game._refill_rngs[e].bit_generator.state for e in range(2)] == rng_states


def test_attack_target_and_defense_selection_preserve_feature_index_six():
    game = arena()
    prepare(game, [[6, 191], [113, 195]])
    targeting = game.step(ids([1, 1])).observation
    assert np.all(targeting.phases == 5) and np.all(targeting.hand_features[:, 0, 6] == 1)
    assert np.allclose(targeting.hand_features[:, 1, 7], 0.05)
    defending = game.step(ids([TARGET_START + 1] * 2)).observation
    assert np.all(defending.actors == 1)
    assert np.all(defending.action_mask[:, 1])
    selected = game.step(ids([1, FORGIVE])).observation
    assert selected.hand_features[0, 0, 6] == 1
    assert selected.hand_features[0, 1, 8] == pytest.approx(0.05)
    game.step(ids([CONFIRM, 0]))
    assert game.utility_statistics.uses == 0


@pytest.mark.parametrize("refill", ["none", "weighted-utility-consumption-v1"])
def test_seeded_rollouts_reproduce_and_count_bounded_mechanics(refill):
    first = collect_guardian_rollout(arena(refill=refill), steps=128)
    second = collect_guardian_rollout(arena(refill=refill), steps=128)
    assert first == second and first.transitions == 256
    assert first.utility_statistics.uses > 0
    assert first.collection_policy == "greedy-utility-smoke-baseline-v2"
    assert not first.learning_performed
    if refill != "none":
        assert first.replacement_gifts > 0


def test_utility_teacher_uses_only_legal_own_visible_features():
    game = arena(initial_mp=0)
    prepare(game, [[235, 195], [191]])
    obs = game.observe()
    assert greedy_guardian_actions(obs).tolist() == [2, 2]
    assert not np.any(obs.action_mask[:, 1])
    game.step(ids([2, 2]))
    assert greedy_guardian_actions(game.observe()).tolist() == [1, 1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 1),
        ("hand_feature_count", 7),
        ("observation_schema_id", "actor-relative-guardian-arena-v1"),
        ("acquisition_policy", "synthetic-balanced-deal-deferred-weighted-refill"),
        ("source_kind", "provisional-guardian-refill-arena-rollout-v1"),
        ("hand_fields", ("role/5", "attack/100")),
        ("refill_plan", None),
    ],
)
def test_utility_metadata_rejects_mixed_or_missing_contracts(field, value):
    record = arena(refill="weighted-utility-consumption-v1").metadata.model_dump()
    record[field] = value
    with pytest.raises(ValueError):
        GuardianRolloutMetadata.model_validate(record)


@pytest.mark.parametrize(
    "utilities,refill",
    [(True, "weighted-consumption-v1"), (False, "weighted-utility-consumption-v1")],
)
def test_refill_requires_matching_inventory_curriculum(utilities, refill):
    with pytest.raises(ValueError, match="selected separately"):
        GuardianRolloutConfig(inventory_utilities=utilities, refill=refill)


def test_expanded_weights_are_pinned_and_old_plan_is_unchanged():
    game = arena(refill="weighted-utility-consumption-v1")
    plan = game.metadata.refill_plan
    assert isinstance(plan, GuardianUtilityRefillPlan)
    assert plan.supported_models == 102 and plan.total_weight == 277
    assert plan.profile_sha256 == UTILITY_REFILL_PROFILE_SHA256
    assert dict(plan.model_weights)[191] == 12 and dict(plan.model_weights)[235] == 1
    assert plan.random_stream.endswith("6772-v1")
    meta = game.metadata.native
    supported = (
        meta.defense_model_ids + meta.attack_weapon_model_ids + meta.attack_miracle_model_ids
    )
    rebuilt = build_guardian_utility_refill_plan(
        read_api_catalog_snapshot(CATALOG),
        BibleSnapshot.model_validate_json(BIBLE.read_text()),
        supported + tuple(r[0] for r in meta.utility_plan.profiles),
    )
    assert rebuilt == plan
    old = arena(inventory_utilities=False, refill="weighted-consumption-v1")
    assert old.metadata.refill_plan.profile_sha256 == REFILL_PROFILE_SHA256
    assert old.metadata.refill_plan.total_weight == 227
    assert old.observe().hand_features.shape[-1] == 7 and old.utility_statistics is None
    with pytest.raises(ValueError):
        build_guardian_utility_refill_plan(
            read_api_catalog_snapshot(CATALOG),
            BibleSnapshot.model_validate_json(BIBLE.read_text()),
            supported,
        )
    with pytest.raises(ValueError):
        GuardianUtilityRefillPlan.model_validate(
            {**plan.model_dump(), "model_weights": tuple(reversed(plan.model_weights))}
        )


def test_cli_exercises_only_the_explicit_utility_curriculum(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "guardian-rollout",
            "--inventory-utilities",
            "--refill",
            "weighted-utility-consumption-v1",
            "--batch-size",
            "2",
            "--steps",
            "32",
        ],
    )
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert record["metadata"]["hand_feature_count"] == 9
    assert record["utility_statistics"]["uses"] > 0 and record["learning_performed"] is False
