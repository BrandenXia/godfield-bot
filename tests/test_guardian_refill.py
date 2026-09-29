"""Separate pinned acquisition hypothesis; no redraw while a defense is pending."""

import json
from dataclasses import fields
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")

from godfield_bot.api_catalog import read_api_catalog_snapshot  # noqa: E402
from godfield_bot.cli import app  # noqa: E402
from godfield_bot.domain.reference import BibleSnapshot  # noqa: E402
from godfield_bot.guardian_refill import (  # noqa: E402
    REFILL_PROFILE_SHA256,
    GuardianRefillPlan,
    build_guardian_refill_plan,
)
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
                "batch_size": 1,
                "opening": "cards-only",
                "refill": "weighted-consumption-v1",
                **kwargs,
            }
        ),
    )


def prepare(game, hands):
    game._native.reset_environments(ids(range(game.config.batch_size)))
    for env in range(game.config.batch_size):
        for owner, models in enumerate(hands):
            game._native.deal_cards(
                ids([env] * len(models)),
                ids([owner] * len(models)),
                ids(range(len(models))),
                ids(range(owner * 9 + 1, owner * 9 + len(models) + 1)),
                ids(models),
            )


def step(game, action):
    return game.step(ids([action] * game.config.batch_size))


def attack(game):
    step(game, 1)
    return step(game, TARGET_START + 1)


def equal(left, right):
    for field in fields(left):
        np.testing.assert_array_equal(getattr(left, field.name), getattr(right, field.name))


def test_profile_is_supported_only_cross_checked_and_content_pinned():
    game = arena()
    plan = game.metadata.refill_plan
    assert plan is not None
    assert len(plan.model_weights) == 94
    assert sum(weight for _, weight in plan.model_weights) == 227
    assert plan.profile_sha256 == REFILL_PROFILE_SHA256
    assert all(0 < weight <= 500 for _, weight in plan.model_weights)
    assert not plan.official_fidelity_verified and not plan.promotion_eligible
    supported = tuple(model for model, _ in plan.model_weights)
    repeated = build_guardian_refill_plan(
        read_api_catalog_snapshot(CATALOG),
        BibleSnapshot.model_validate_json(BIBLE.read_text()),
        supported,
    )
    assert repeated == plan
    changed = plan.model_dump()
    changed["model_weights"] = [(model, weight + 1) for model, weight in plan.model_weights]
    with pytest.raises(ValueError, match="pinned supported gift profile"):
        GuardianRefillPlan.model_validate(changed)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "malformed", "changed", "client"])
def test_missing_or_changed_bible_weights_fail_closed(mutation):
    game = arena()
    plan = game.metadata.refill_plan
    assert plan is not None
    record = json.loads(BIBLE.read_text())
    entry = next(
        item
        for category in record["catalog"].values()
        for item in category["items"]
        if item["asset"] == "bronze-club"
    )
    rates = [line for line in entry["detail"] if not line.startswith("Gift Rate:")]
    entry["detail"] = (
        rates
        + {
            "missing": [],
            "duplicate": ["Gift Rate: 3/500", "Gift Rate: 3/500"],
            "malformed": ["Gift Rate: 3/499"],
            "changed": ["Gift Rate: 4/500"],
            "client": ["Gift Rate: 3/500"],
        }[mutation]
    )
    if mutation == "client":
        record["client"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        build_guardian_refill_plan(
            read_api_catalog_snapshot(CATALOG),
            BibleSnapshot.model_validate(record),
            tuple(model for model, _ in plan.model_weights),
        )


@pytest.mark.parametrize("opening", ["cards-only", "mixed", "mars-opening"])
def test_refill_does_not_change_initial_deals_openings_or_observation_contract(opening):
    weighted = arena(batch_size=4, opening=opening)
    original = arena(batch_size=4, opening=opening, refill="none")
    equal(weighted.observe(), original.observe())
    assert weighted.metadata.curriculum_id != original.metadata.curriculum_id
    assert original.metadata.refill_plan is None
    assert weighted.metadata.observation_schema_id == original.metadata.observation_schema_id
    assert weighted.replacement_gifts == original.replacement_gifts == 0


def test_weapon_is_replaced_only_after_defense_and_has_a_unique_instance():
    game = arena()
    prepare(game, [[6], []])  # ordinary ATK1 weapon
    declared = attack(game)
    assert declared.observation.phases[0] == 1
    assert game._native.inventory_snapshot()[0, 0, 0, 0] == 0
    assert game._pending_refills == [{(0, 0)}]
    assert game.replacement_gifts == 0
    step(game, FORGIVE)
    inventory = game._native.inventory_snapshot()
    assert inventory[0, 0, 0, 0] == 19
    assert inventory[0, 0, 0, 1] in game._refill_models
    assert game.replacement_gifts == 1 and game._pending_refills == [set()]
    assert game._native.resource_snapshot()[0, 1, 0] == 39
    assert not np.any(inventory[0, :, 9:])


def test_confirmed_armor_refills_each_consumed_slot_but_forgiveness_keeps_armor():
    for action, expected in ((CONFIRM, 3), (FORGIVE, 1)):
        game = arena()
        prepare(game, [[6], [113, 118]])
        attack(game)
        step(game, 1)
        step(game, 2)
        assert game.replacement_gifts == 0
        step(game, action)
        inventory = game._native.inventory_snapshot()
        assert game.replacement_gifts == expected
        if action == CONFIRM:
            assert inventory[0, 1, :2, 0].tolist() == [20, 21]
            assert game._native.consumed_card_count == 3
        else:
            assert inventory[0, 1, :2, 0].tolist() == [10, 11]
            assert game._native.consumed_card_count == 1
        occupied = inventory[0, :, :, 0]
        assert len(np.unique(occupied[occupied > 0])) == np.count_nonzero(occupied)


def test_wall_is_retained_and_deferred_weapon_gift_arrives_after_block():
    game = arena()
    prepare(game, [[6], [233]])
    attack(game)
    step(game, 1)
    step(game, CONFIRM)
    inventory = game._native.inventory_snapshot()
    assert game.replacement_gifts == 1
    assert inventory[0, 1, 0, :2].tolist() == [10, 233]
    assert game._native.resource_snapshot()[0, 1, :2].tolist() == [40, 4]


def test_miracles_are_retained_and_do_not_receive_replacements_across_bounce():
    game = arena()
    prepare(game, [[211, 119], [234]])  # fire armor is legal against water attacks
    attack(game)
    step(game, 1)
    bounced = step(game, CONFIRM)
    assert bounced.observation.phases[0] == 4 and game.replacement_gifts == 0
    step(game, TARGET_START + 1)  # seat1 relative1 -> original caster0
    selected = step(game, 2)
    assert selected.observation.phases[0] == 1 and game.replacement_gifts == 0
    step(game, CONFIRM)
    inventory = game._native.inventory_snapshot()
    assert game.replacement_gifts == 1  # only the original caster's ordinary armor
    assert inventory[0, 0, 0, :2].tolist() == [1, 211]
    assert inventory[0, 1, 0, :2].tolist() == [10, 234]
    assert inventory[0, 0, 1, 0] == 19
    assert game._native.miracle_cast_count == 2


def test_dead_defender_is_not_refilled_when_other_players_keep_game_active():
    game = arena(player_count=3, initial_hp=1)
    prepare(game, [[10], [113], []])  # ATK2, DEF1: defender dies after confirming
    attack(game)
    step(game, 1)
    end = step(game, CONFIRM)
    assert not end.terminated[0] and not end.truncated[0]
    assert end.observation.active[0]
    assert game._native.resource_snapshot()[0, 1, 0] == 0
    assert not np.any(game._native.inventory_snapshot()[0, 1])
    assert game.replacement_gifts == 1  # living attacker's weapon only
    assert game._pending_refills == [set()]


@pytest.mark.parametrize("boundary", ["winner", "turn_limit", "decision_limit", "toggle_limit"])
def test_finished_rows_discard_pending_gifts_without_drawing_or_replacing(boundary):
    options = {
        "winner": {"initial_hp": 1},
        "turn_limit": {"max_turns": 1},
        "decision_limit": {"max_decisions": 3},
        "toggle_limit": {},
    }[boundary]
    game = arena(**options)
    prepare(game, [[6], [113]])
    original_rng = json.dumps(game._refill_rngs[0].bit_generator.state, sort_keys=True)
    attack(game)
    if boundary == "toggle_limit":
        for _ in range(64):
            end = step(game, 1)
    else:
        end = step(game, FORGIVE)
    assert end.terminated[0] or end.truncated[0]
    assert game.replacement_gifts == 0
    assert game._pending_refills == [set()]
    assert game._native.inventory_snapshot()[0, 0, 0, 0] == 0
    assert json.dumps(game._refill_rngs[0].bit_generator.state, sort_keys=True) == original_rng
    game.reset_done()
    assert game._pending_refills == [set()] and game._next_instances[0] == 19
    assert game.observe().hand_mask.sum() == 9


def test_invalid_mixed_batch_action_does_not_change_state_queue_or_randomness():
    game, twin = arena(batch_size=2), arena(batch_size=2)
    for current in (game, twin):
        prepare(current, [[6], [113]])
        attack(current)
    before = game.observe()
    rng = [
        json.dumps(value.bit_generator.state, sort_keys=True)
        for value in game._refill_rngs.values()
    ]
    with pytest.raises(ValueError, match="illegal"):
        game.step(ids([FORGIVE, 0]))
    equal(before, game.observe())
    assert game._pending_refills == [{(0, 0)}, {(0, 0)}]
    assert rng == [
        json.dumps(value.bit_generator.state, sort_keys=True)
        for value in game._refill_rngs.values()
    ]
    step(game, FORGIVE)
    step(twin, FORGIVE)
    np.testing.assert_array_equal(
        game._native.inventory_snapshot(), twin._native.inventory_snapshot()
    )


@pytest.mark.parametrize("players", [2, 3, 9])
def test_multiplayer_refills_are_legal_bounded_and_reports_reproduce(players):
    first, second = (
        arena(batch_size=4, player_count=players),
        arena(batch_size=4, player_count=players),
    )
    first_report, second_report = (
        collect_guardian_rollout(first, steps=200),
        collect_guardian_rollout(second, steps=200),
    )
    assert first_report == second_report and first_report.replacement_gifts > 0
    assert not first_report.metadata.promotion_eligible
    assert first_report.replacement_gifts == first.replacement_gifts
    first._reset(ids([0, 1]))
    second._reset(ids([1]))
    second._reset(ids([0]))
    # Reset the remaining rows too, then prove gift streams do not depend on reset order.
    first._reset(ids([2, 3]))
    second._reset(ids([3, 2]))
    for _ in range(20):
        left, right = first.observe(), second.observe()
        equal(left, right)
        first.step(greedy_guardian_actions(left))
        second.step(greedy_guardian_actions(right))
    # Reporting a new window counts its gifts, not the lifetime total.
    previous = first.replacement_gifts
    extra = collect_guardian_rollout(first, steps=10)
    assert extra.replacement_gifts == first.replacement_gifts - previous


def test_curriculum_metadata_cannot_silently_add_or_remove_refills():
    weighted, original = arena().metadata.model_dump(), arena(refill="none").metadata.model_dump()
    del weighted["refill_plan"]
    with pytest.raises(ValueError, match="explicit separate curriculum"):
        GuardianRolloutMetadata.model_validate(weighted)
    original["config"]["refill"] = "weighted-consumption-v1"
    with pytest.raises(ValueError, match="explicit separate curriculum"):
        GuardianRolloutMetadata.model_validate(original)
    legacy = arena(refill="none").metadata.model_dump()
    for key in ("curriculum_id", "refill_plan"):
        del legacy[key]
    del legacy["config"]["refill"]
    assert GuardianRolloutMetadata.model_validate(legacy).config.refill == "none"


def test_cli_explicit_refill_is_local_only_and_unknown_mode_fails(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "guardian-rollout",
            "--batch-size",
            "2",
            "--steps",
            "40",
            "--refill",
            "weighted-consumption-v1",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["replacement_gifts"] > 0
    assert report["metadata"]["config"]["refill"] == "weighted-consumption-v1"
    assert not report["metadata"]["promotion_eligible"]
    invalid = CliRunner().invoke(app, ["simulation", "guardian-rollout", "--refill", "official"])
    assert invalid.exit_code == 1


def test_cli_invalid_catalog_is_a_reported_setup_failure(tmp_path, monkeypatch):
    from structlog.testing import capture_logs

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    invalid_catalog = tmp_path / "catalog.json"
    invalid_catalog.write_text("{}")
    with capture_logs() as logs:
        result = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-rollout",
                "--catalog",
                str(invalid_catalog),
                "--refill",
                "weighted-consumption-v1",
            ],
        )
    assert result.exit_code == 1
    assert any(record["event"] == "guardian_rollout_failed" for record in logs)
