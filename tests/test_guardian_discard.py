"""Atomic native discard, source restrictions, and caller-driven recovery."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")

from godfield_bot.api_catalog import read_api_catalog_snapshot  # noqa: E402
from godfield_bot.cli import app  # noqa: E402
from godfield_bot.domain.reference import BibleSnapshot  # noqa: E402
from godfield_bot.guardian_discard import (  # noqa: E402
    DISCARD_PROFILE_SHA256,
    DISCARD_RULESET_ID,
    GuardianDiscardPlan,
    GuardianDiscardTurnMetadata,
    build_guardian_discard_plan,
    create_provisional_guardian_discard_turn_batch,
)
from godfield_bot.guardian_utility import (  # noqa: E402
    create_provisional_guardian_utility_turn_batch,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
MODELS = (
    113,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    122,
    123,
    126,
    127,
    128,
    129,
    130,
    131,
    132,
    133,
    134,
    135,
    138,
    139,
    140,
    141,
    142,
    144,
    145,
    146,
    147,
    148,
    149,
    152,
    153,
    154,
    155,
    157,
    158,
    159,
    160,
    161,
    166,
    169,
    170,
    172,
    175,
    176,
    180,
    191,
    192,
    193,
    194,
    195,
    196,
    197,
    211,
    212,
    213,
    214,
    215,
    218,
    233,
    234,
    235,
)


def ids(values):
    return np.ascontiguousarray(values, dtype=np.int64)


def create(**kwargs):
    return create_provisional_guardian_discard_turn_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        **{"batch_size": 2, "player_count": 2, "initial_mp": 0, **kwargs},
    )


def deal(batch, models, *, owner=0, slot=0):
    size = len(models)
    batch.deal_cards(
        ids(range(size)),
        ids([owner] * size),
        ids([slot] * size),
        ids([100 + owner * 18 + slot] * size),
        ids(models),
    )


def state(batch):
    return (
        batch.inventory_snapshot(),
        batch.turn_snapshot(),
        batch.resource_snapshot(),
        batch.combat_snapshot(),
        batch.guardian_snapshot(),
        batch.actor_hand_snapshot(),
        (
            batch.discarded_card_count,
            batch.consumed_card_count,
            batch.miracle_cast_count,
            batch.utility_use_count,
            batch.hp_gained,
            batch.mp_gained,
            batch.mp_spent,
        ),
    )


def unchanged(batch, before):
    for actual, expected in zip(state(batch)[:-1], before[:-1], strict=True):
        np.testing.assert_array_equal(actual, expected)
    assert state(batch)[-1] == before[-1]


@pytest.mark.parametrize("model", MODELS)
def test_each_supported_nonweapon_discards_without_cost_or_resource_effect(model):
    batch = create().batch
    deal(batch, [model, model])
    before = batch.resource_snapshot().copy()
    assert batch.discard_action_masks()[:, 0].all()
    assert not batch.discard_action_masks().flags.writeable
    batch.discard_cards(ids([0, 1]), ids([0, 0]), ids([0, 0]))
    assert not batch.inventory_snapshot()[:, 0, 0].any()
    np.testing.assert_array_equal(batch.resource_snapshot(), before)
    assert batch.turn_snapshot()[:, 1].tolist() == [1, 1]
    assert batch.turn_snapshot()[:, 3].tolist() == [1, 1]
    assert batch.turn_snapshot()[:, 9].tolist() == [4, 4]
    assert batch.discarded_card_count == 2
    assert state(batch)[-1][1:] == (0,) * 6
    batch.reset_environments(ids([0, 1]))
    assert batch.discarded_card_count == 2 and not batch.discard_action_masks().any()


def test_pass_only_state_recovers_through_explicit_same_slot_gift():
    batch = create().batch
    deal(batch, [113, 113])
    deal(batch, [235, 235], slot=1)
    deal(batch, [113, 113], owner=1)
    deal(batch, [235, 235], owner=1, slot=1)
    assert not batch.ready_action_masks()[:, :18].any()
    batch.discard_cards(ids([0, 1]), ids([0, 0]), ids([0, 0]))
    # There is no native auto-gift, compaction, revival, or resource conversion.
    assert not batch.inventory_snapshot()[:, 0, 0].any()
    assert batch.inventory_snapshot()[:, 0, 1, 1].tolist() == [235, 235]
    batch.deal_cards(ids([0, 1]), ids([0, 0]), ids([0, 0]), ids([300, 300]), ids([197, 197]))
    batch.pass_turns(ids([0, 1]), ids([1, 1]))
    assert batch.utility_action_masks()[:, 0].all()
    batch.use_utility_cards(ids([0, 1]), ids([0, 0]), ids([0, 0]))
    batch.pass_turns(ids([0, 1]), ids([1, 1]))
    assert batch.utility_action_masks()[:, 1].all()
    batch.use_utility_cards(ids([0, 1]), ids([0, 0]), ids([1, 1]))
    assert batch.resource_snapshot()[:, 0, :2].tolist() == [[50, 8], [50, 8]]
    assert batch.discarded_card_count == 2 and batch.utility_use_count == 4
    assert batch.miracle_cast_count == 2 and batch.mp_spent == 14


@pytest.mark.parametrize("mutation", ["owner", "slot", "weapon", "empty", "env", "duplicate"])
def test_bad_last_row_is_atomic(mutation):
    batch = create().batch
    deal(batch, [113, 6 if mutation == "weapon" else 113])
    envs, owners, slots = [0, 1], [0, 0], [0, 0]
    if mutation == "owner":
        owners[-1] = 1
    if mutation == "slot":
        slots[-1] = -1
    if mutation == "empty":
        slots[-1] = 1
    if mutation == "env":
        envs[-1] = 2
    if mutation == "duplicate":
        envs[-1] = 0
    before = state(batch)
    with pytest.raises(ValueError):
        batch.discard_cards(ids(envs), ids(owners), ids(slots))
    unchanged(batch, before)


def test_discard_rejects_defense_bounce_and_finished_rows():
    batch = create(initial_mp=10, max_turns=1).batch
    deal(batch, [211, 211])
    deal(batch, [234, 234], owner=1)
    batch.begin_card_attacks(ids([0, 1]), ids([0, 0]), ids([0, 0]), ids([1, 1]))
    assert not batch.discard_action_masks().any()
    before = state(batch)
    with pytest.raises(ValueError):
        batch.discard_cards(ids([0]), ids([1]), ids([0]))
    unchanged(batch, before)
    batch.step_defenses(ids([0, 1]), ids([1, 1]), ids([0, 0]))
    batch.step_defenses(ids([0, 1]), ids([1, 1]), ids([19, 19]))
    assert batch.turn_snapshot()[:, 0].tolist() == [4, 4]
    assert not batch.discard_action_masks().any()
    before = state(batch)
    with pytest.raises(ValueError):
        batch.discard_cards(ids([0]), ids([0]), ids([0]))
    unchanged(batch, before)
    batch.resolve_bounces(ids([0, 1]), ids([1, 1]), ids([0, 0]))
    batch.step_defenses(ids([0, 1]), ids([0, 0]), ids([18, 18]))
    assert batch.turn_snapshot()[:, 0].tolist() == [3, 3]
    before = state(batch)
    with pytest.raises(ValueError):
        batch.discard_cards(ids([0]), ids([0]), ids([0]))
    unchanged(batch, before)


def test_empty_call_and_turn_limit_no_terminal_replacement():
    batch = create(max_turns=1).batch
    deal(batch, [113, 113])
    before = state(batch)
    batch.discard_cards(ids([]), ids([]), ids([]))
    unchanged(batch, before)
    batch.discard_cards(ids([0, 1]), ids([0, 0]), ids([0, 0]))
    assert batch.turn_snapshot()[:, 0].tolist() == [3, 3]
    assert not batch.discard_action_masks().any()
    before = state(batch)
    with pytest.raises(ValueError):
        batch.deal_cards(ids([0]), ids([0]), ids([0]), ids([300]), ids([197]))
    unchanged(batch, before)


def test_winner_cannot_discard_a_retained_armor_after_elimination():
    batch = create(initial_hp=1).batch
    deal(batch, [113, 113])
    deal(batch, [6, 6], slot=1)
    batch.begin_card_attacks(ids([0, 1]), ids([0, 0]), ids([1, 1]), ids([1, 1]))
    batch.step_defenses(ids([0, 1]), ids([1, 1]), ids([18, 18]))
    assert batch.turn_snapshot()[:, 0].tolist() == [2, 2]
    assert not batch.discard_action_masks().any()
    before = state(batch)
    with pytest.raises(ValueError):
        batch.discard_cards(ids([0]), ids([0]), ids([0]))
    unchanged(batch, before)


@pytest.mark.parametrize("mutation", ["dtype", "float", "rank", "length", "stride"])
def test_invalid_array_contracts_do_not_mutate(mutation):
    batch = create().batch
    deal(batch, [113, 113])
    envs, owners, slots = ids([0, 1]), ids([0, 0]), ids([0, 0])
    if mutation == "dtype":
        slots = slots.astype(np.int32)
    elif mutation == "float":
        slots = slots.astype(np.float64)
    elif mutation == "rank":
        slots = slots[:, None]
    elif mutation == "length":
        slots = slots[:1]
    elif mutation == "stride":
        slots = ids([0, 0, 0, 0])[::2]
    before = state(batch)
    with pytest.raises((TypeError, ValueError)):
        batch.discard_cards(envs, owners, slots)
    unchanged(batch, before)


@pytest.mark.parametrize("models", [[], [113, 113], [6], [999], [208], [209]])
def test_native_constructor_rejects_unusable_allowlists(models):
    with pytest.raises(ValueError):
        native.GuardianDiscardTurnBatch(
            1,
            2,
            1,
            ids([[0, 245, 1]]),
            ids([[245, 10, 0, 100, 0, 0, 0]]),
            ids([[113, 4, 0, 0, 0]]),
            ids([[6, 1, 0, 0, 0]]),
            ids([[191, 0, 5, 0, 0], [208, 0, 1, 0, 0], [209, 0, 1, 0, 0]]),
            ids(models),
        )


def test_large_multiplayer_batch_matches_removal_oracle_and_preserves_other_owners():
    batch = create(batch_size=512, player_count=9).batch
    deal(batch, [113] * 512, slot=3)
    deal(batch, [235] * 512, owner=8, slot=2)
    before = batch.inventory_snapshot().copy()
    batch.discard_cards(ids(range(512)), ids([0] * 512), ids([3] * 512))
    before[:, 0, 3] = 0
    np.testing.assert_array_equal(batch.inventory_snapshot(), before)
    assert batch.turn_snapshot()[:, 1].tolist() == [1] * 512
    assert batch.discarded_card_count == 512


def test_exact_pins_and_old_native_surface_unchanged():
    created = create()
    plan = created.metadata.discard_plan
    assert plan.discard_model_ids == MODELS and plan.profile_sha256 == DISCARD_PROFILE_SHA256
    assert created.metadata.ruleset_id == DISCARD_RULESET_ID
    assert not created.metadata.local_training_eligible and not created.metadata.promotion_eligible
    assert created.metadata.pending_neural_action_count == 48
    old = create_provisional_guardian_utility_turn_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, initial_mp=0
    )
    assert created.metadata.utility_base == old.metadata
    assert not hasattr(old.batch, "discard_cards")
    assert created.batch.actor_hand_snapshot().shape == old.batch.actor_hand_snapshot().shape


@pytest.mark.parametrize(
    "field,value",
    [
        ("catalog_sha256", "0" * 64),
        ("bible_client_sha256", "0" * 64),
        ("discard_model_ids", (113,)),
        ("forbidden_categories", ()),
        ("forbidden_exception_model_ids", (207, 209)),
        ("documented_restrictions", ()),
        ("promotion_eligible", True),
    ],
)
def test_plan_tampering_fails_closed(field, value):
    raw = create().metadata.discard_plan.model_dump()
    raw[field] = value
    with pytest.raises(ValueError):
        GuardianDiscardPlan.model_validate(raw)


def test_missing_documented_restriction_and_native_identity_fail_closed(monkeypatch):
    catalog = read_api_catalog_snapshot(CATALOG)
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    changed = bible.model_copy(update={"reference_sections": {}})
    with pytest.raises(ValueError, match="restrictions"):
        build_guardian_discard_plan(catalog, changed)
    monkeypatch.setattr(native, "GUARDIAN_DISCARD_TURN_KERNEL_SCHEMA_VERSION", 99)
    with pytest.raises(ProvisionalRuleUnavailableError, match="identity"):
        create()


@pytest.mark.parametrize("mutation", ["models", "weapons", "layout"])
def test_component_metadata_rejects_mismatched_contracts(mutation):
    raw = create().metadata.model_dump()
    if mutation == "models":
        raw["utility_base"]["defense_model_ids"] = ()
    elif mutation == "weapons":
        raw["utility_base"]["attack_weapon_model_ids"] = (113,)
    else:
        raw["pending_neural_action_layout"] = ()
    with pytest.raises(ValueError, match="metadata"):
        GuardianDiscardTurnMetadata.model_validate(raw)


def test_cli_requires_explicit_component_flags(monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    runner = CliRunner()
    for flags in ([], ["--turns"], ["--inventory-utilities"]):
        result = runner.invoke(
            app, ["simulation", "guardian-batch-plan", "--inventory-discards", *flags]
        )
        assert result.exit_code == 1
    result = runner.invoke(
        app,
        [
            "simulation",
            "guardian-batch-plan",
            "--turns",
            "--inventory-utilities",
            "--inventory-discards",
            "--batch-size",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ruleset_id"] == DISCARD_RULESET_ID
