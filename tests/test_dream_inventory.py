"""Portable inventory operations, displayed-only boundary, and provisional pins."""

import json
from collections import Counter
from itertools import pairwise
from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.dream_inventory import (
    DREAM_INVENTORY_RULESET_ID,
    INVENTORY_PROFILE_SHA256,
    DreamInventoryMetadata,
    DreamInventoryPlan,
    build_dream_inventory_plan,
    create_provisional_dream_inventory_batch,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
# Synthetic registry; the pinned factory never classifies virtual 1/2 as weapons.
PROFILES = (
    (1, 1),
    (2, 1),
    (120, 2),
    (121, 2),
    (191, 3),
    (192, 3),
    (210, 4),
    (215, 4),
    (3, 5),
    (4, 5),
    (5, 5),
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def rows(values):
    return ids(values).reshape(-1, 4)


def game(*, size=2, players=3, capacity=8):
    return native.DreamInventoryBatch(size, players, ids(PROFILES), capacity)


def add(batch, *, env=0, owner=0, instance=1, model=1, mask=0, ticket=99, fake=0):
    batch.add_cards(
        ids([env]),
        ids([owner]),
        ids([instance]),
        ids([model]),
        ids([mask]),
        ids([ticket]),
        ids([fake]),
    )


def hand(batch, *, env=0, owner=0):
    raw = batch.snapshot()[env, owner]
    return raw[raw[:, 0] != 0]


def state(batch):
    return batch.snapshot(), (
        batch.gift_count,
        batch.consumed_count,
        batch.miracle_use_count,
        batch.removal_count,
        batch.restored_count,
    )


def unchanged(batch, before):
    after = state(batch)
    np.testing.assert_array_equal(after[0], before[0])
    assert after[1] == before[1]


def plan():
    return build_dream_inventory_plan(
        read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
    )


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("model,kind", PROFILES)
def test_every_category_masks_and_all_100_dream_tickets(players, model, kind):
    batch = game(size=1600, players=players, capacity=1)
    envs = ids(range(1600))
    masks = ids([mask for mask in range(16) for _ in range(100)])
    tickets = ids(list(range(100)) * 16)
    fake = sorted(model for model, category in PROFILES if category == kind)[1]
    batch.add_cards(
        envs,
        ids([players - 1] * 1600),
        ids([1] * 1600),
        ids([model] * 1600),
        masks,
        tickets,
        ids([1] * 1600),
    )
    expected = np.where((masks & 2 != 0) & (tickets < 50), fake, 0)
    np.testing.assert_array_equal(batch.snapshot()[:, players - 1, 0, 2], expected)
    view = batch.actor_hands(envs, ids([players - 1] * 1600))
    np.testing.assert_array_equal(view[:, 0, 1], np.where(expected != 0, expected, model))
    assert view.shape == (1600, 1, 3)
    assert batch.gift_count == 1600
    assert np.count_nonzero(batch.snapshot()[:, 0]) == 0


def test_same_model_fake_is_internally_retained_but_not_exposed():
    batch = game()
    add(batch, mask=2, ticket=0, fake=0)
    np.testing.assert_array_equal(hand(batch), rows([[1, 1, 1, 0]]))
    before = batch.actor_hands(ids([0]), ids([0]))
    batch.restore_displays(ids([0]), ids([0]))
    np.testing.assert_array_equal(batch.actor_hands(ids([0]), ids([0])), before)
    assert batch.restored_count == 1


def test_existing_cards_not_retroactively_disguised_and_restore_is_owner_local():
    batch = game()
    add(batch)
    add(batch, instance=2, mask=2, ticket=0, fake=1)
    add(batch, owner=1, instance=3, model=210, mask=2, ticket=49, fake=1)
    add(batch, env=1, instance=4, model=120, mask=2, ticket=0, fake=1)
    np.testing.assert_array_equal(hand(batch), rows([[1, 1, 0, 0], [2, 1, 2, 0]]))
    batch.restore_displays(ids([0]), ids([0]))
    np.testing.assert_array_equal(hand(batch), rows([[1, 1, 0, 0], [2, 1, 0, 0]]))
    np.testing.assert_array_equal(hand(batch, owner=1), rows([[3, 210, 215, 0]]))
    np.testing.assert_array_equal(hand(batch, env=1), rows([[4, 120, 121, 0]]))
    batch.restore_displays(ids([0]), ids([0]))
    assert batch.restored_count == 1


def test_mixed_selection_stable_compaction_and_miracle_reuse_input_order():
    batch = game()
    batch.seed_hand(
        0,
        0,
        rows(
            [
                [1, 210, 215, 0],
                [2, 1, 2, 0],
                [3, 191, 192, 0],
                [4, 215, 210, 1],
                [5, 120, 121, 0],
                [6, 1, 0, 0],
            ]
        ),
    )
    selected = rows([[4, 215, 210, 1], [2, 1, 2, 0], [1, 210, 215, 0], [5, 120, 121, 0]])
    batch.use_cards(ids([0] * 4), ids([0] * 4), selected)
    np.testing.assert_array_equal(
        hand(batch),
        rows(
            [
                [3, 191, 192, 0],
                [6, 1, 0, 0],
                [4, 215, 210, 1],
                [1, 210, 215, 1],
            ]
        ),
    )
    batch.use_cards(ids([0]), ids([0]), rows([[4, 215, 210, 1]]))
    np.testing.assert_array_equal(
        hand(batch),
        rows(
            [
                [3, 191, 192, 0],
                [6, 1, 0, 0],
                [1, 210, 215, 1],
                [4, 215, 210, 1],
            ]
        ),
    )
    assert batch.consumed_count == 2
    assert batch.miracle_use_count == 3
    assert batch.gift_count == 0
    assert batch.removal_count == 0
    assert np.count_nonzero(batch.snapshot()[0, 0, 4:]) == 0


def test_all_237_registered_cards_are_inventory_data_not_battle_effects():
    configured = create_provisional_dream_inventory_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=237
    )
    batch = configured.batch
    profiles = configured.metadata.plan.profiles
    batch.add_cards(
        ids([0] * 237),
        ids([0] * 237),
        ids(range(1, 238)),
        ids([model for model, _ in profiles]),
        ids([0] * 237),
        ids([99] * 237),
        ids([0] * 237),
    )
    before = hand(batch)
    batch.use_cards(ids([0] * 237), ids([0] * 237), before)
    expected = before[[kind == 4 for _, kind in profiles]].copy()
    expected[:, 3] = 1
    np.testing.assert_array_equal(hand(batch), expected)
    batch.use_cards(ids([0] * 30), ids([0] * 30), expected)
    np.testing.assert_array_equal(hand(batch), expected)
    assert batch.gift_count == 237
    assert batch.consumed_count == 207
    assert batch.miracle_use_count == 60
    assert not configured.metadata.item_registration_is_battle_effect_coverage
    assert not configured.metadata.full_game_training_ready


def test_actor_view_cannot_distinguish_hidden_identity_or_other_players():
    first, second = game(), game()
    first.seed_hand(0, 1, rows([[7, 1, 2, 0], [9, 210, 215, 1]]))
    second.seed_hand(0, 1, rows([[7, 2, 0, 0], [9, 215, 0, 1]]))
    first.seed_hand(0, 0, rows([[4, 191, 0, 0]]))
    second.seed_hand(0, 0, rows([[5, 120, 0, 0], [6, 215, 0, 1]]))
    first.seed_hand(1, 1, rows([[7, 121, 0, 0]]))
    assert not np.array_equal(first.snapshot(), second.snapshot())
    np.testing.assert_array_equal(
        first.actor_hands(ids([0, 0]), ids([1, 1])),
        second.actor_hands(ids([0, 0]), ids([1, 1])),
    )
    before = state(first)
    view = first.actor_hands(ids([0]), ids([1]))
    assert view.shape == (1, 8, 3)
    np.testing.assert_array_equal(view[0, :2], ids([[7, 2, 0], [9, 215, 1]]))
    assert np.count_nonzero(view[0, 2:]) == 0
    unchanged(first, before)


def test_explicit_removal_preserves_survivors_and_makes_no_replacement_inference():
    batch = game()
    batch.seed_hand(0, 0, rows([[1, 210, 215, 1], [2, 1, 0, 0], [3, 215, 0, 0]]))
    batch.remove_cards(ids([0, 0]), ids([0, 0]), rows([[3, 215, 0, 0], [1, 210, 215, 1]]))
    np.testing.assert_array_equal(hand(batch), rows([[2, 1, 0, 0]]))
    assert batch.removal_count == 2
    assert batch.miracle_use_count == 0
    assert batch.consumed_count == 0
    assert batch.gift_count == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("env", -1),
        ("env", 2),
        ("owner", -1),
        ("owner", 3),
        ("instance", 0),
        ("instance", 2**53),
        ("model", 0),
        ("model", 245),
        ("mask", -1),
        ("mask", 16),
        ("ticket", -1),
        ("ticket", 100),
        ("fake", -1),
        ("fake", 2),
    ],
)
def test_invalid_gift_rejected_without_any_mutation(field, value):
    batch = game()
    add(batch, instance=7)
    before = state(batch)
    with pytest.raises(ValueError):
        add(batch, **{field: value})
    unchanged(batch, before)


@pytest.mark.parametrize("failure", ["ticket", "model", "duplicate", "owner", "capacity"])
def test_gift_last_row_failure_is_whole_batch_atomic(failure):
    batch = game(capacity=1)
    add(batch, env=1, owner=0, instance=8)
    before = state(batch)
    values = [[0, 1], [0, 1], [1, 2], [1, 210], [2, 2], [0, 0], [1, 1]]
    if failure == "ticket":
        values[6][1] = 2
    elif failure == "model":
        values[3][1] = 296
    elif failure == "duplicate":
        values[2][1] = 8
    elif failure == "owner":
        values[1][1] = 3
    else:
        values[1][1] = 0
    with pytest.raises(ValueError):
        batch.add_cards(*(ids(value) for value in values))
    unchanged(batch, before)


def test_instance_unique_across_owners_but_independent_between_environments():
    batch = game()
    add(batch, owner=1, instance=4)
    add(batch, env=1, owner=2, instance=4)
    before = state(batch)
    with pytest.raises(ValueError, match="duplicate"):
        add(batch, owner=0, instance=4)
    unchanged(batch, before)
    with pytest.raises(ValueError, match="duplicate"):
        batch.add_cards(
            ids([0, 0]),
            ids([0, 2]),
            ids([9, 9]),
            ids([1, 120]),
            ids([0, 0]),
            ids([99, 99]),
            ids([0, 0]),
        )
    unchanged(batch, before)
    # Seeding can replace its own state, but cannot impersonate another owner.
    batch.seed_hand(0, 1, rows([[4, 210, 215, 1]]))
    before = state(batch)
    with pytest.raises(ValueError, match="duplicate"):
        batch.seed_hand(0, 0, rows([[4, 1, 0, 0]]))
    unchanged(batch, before)


@pytest.mark.parametrize("operation", ["use_cards", "remove_cards"])
@pytest.mark.parametrize(
    "selection",
    [
        [[1, 210, 0, 0], [2, 1, 0, 1]],  # stale last used bit
        [[1, 210, 0, 0], [2, 2, 0, 0]],  # stale true identity
        [[1, 210, 0, 0], [2, 1, 2, 0]],  # stale disguise
        [[1, 210, 0, 0], [3, 1, 0, 0]],  # unowned ID
        [[1, 210, 0, 0], [1, 210, 0, 0]],  # duplicate
    ],
)
def test_selected_rows_atomic_and_exact(operation, selection):
    batch = game()
    batch.seed_hand(0, 0, rows([[1, 210, 0, 0], [2, 1, 0, 0]]))
    before = state(batch)
    with pytest.raises(ValueError, match=r"stale|duplicate|owned"):
        getattr(batch, operation)(ids([0, 0]), ids([0, 0]), rows(selection))
    unchanged(batch, before)


def test_used_miracle_stale_first_use_rejected_and_cure_invalidates_fake_token():
    batch = game()
    original = rows([[1, 210, 215, 0]])
    batch.seed_hand(0, 0, original)
    batch.use_cards(ids([0]), ids([0]), original)
    before = state(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.use_cards(ids([0]), ids([0]), original)
    unchanged(batch, before)
    batch.restore_displays(ids([0]), ids([0]))
    before = state(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.use_cards(ids([0]), ids([0]), rows([[1, 210, 215, 1]]))
    unchanged(batch, before)


@pytest.mark.parametrize(
    "bad",
    [
        [[1, 1, 0, 0], [1, 2, 0, 0]],
        [[1, 1, 0, 1]],
        [[1, 1, 120, 0]],
        [[1, 1, 999, 0]],
        [[1, 296, 0, 0]],
        [[0, 1, 0, 0]],
        [[2**53, 1, 0, 0]],
        [[1, 210, -1, 0]],
        [[1, 210, 0, 2]],
    ],
)
def test_invalid_seed_keeps_original_hand_and_counters(bad):
    batch = game()
    add(batch)
    before = state(batch)
    with pytest.raises(ValueError):
        batch.seed_hand(0, 0, rows(bad))
    unchanged(batch, before)


@pytest.mark.parametrize("operation", ["restore_displays", "reset_environments"])
@pytest.mark.parametrize("envs", [[0, 2], [0, -1], [0, 0]])
def test_bulk_clear_is_atomic_on_invalid_or_duplicate_rows(operation, envs):
    batch = game()
    add(batch, mask=2, ticket=0, fake=1)
    before = state(batch)
    with pytest.raises(ValueError):
        if operation == "reset_environments":
            batch.reset_environments(ids(envs))
        else:
            batch.restore_displays(ids(envs), ids([0, 0]))
    unchanged(batch, before)


def test_independent_readonly_views_survive_mutation_reset_and_native_owner():
    batch = game()
    add(batch, mask=2, ticket=0, fake=1)
    add(batch, env=1, owner=1, instance=2, model=210)
    snapshot = batch.snapshot()
    view = batch.actor_hands(ids([0]), ids([0]))
    for array in (snapshot, view):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.flat[0] = 99
    batch.reset_environments(ids([0]))
    assert np.count_nonzero(batch.snapshot()[0]) == 0
    np.testing.assert_array_equal(hand(batch, env=1, owner=1), rows([[2, 210, 0, 0]]))
    assert batch.gift_count == 2
    # IDs may be reused only within a new caller epoch after reset.
    add(batch, instance=1, model=120)
    del batch
    np.testing.assert_array_equal(snapshot[0, 0, 0], ids([1, 1, 2, 0]))
    np.testing.assert_array_equal(view[0, 0], ids([1, 2, 0]))


def test_empty_operations_queries_and_seed_clear_have_defined_shapes():
    batch = game()
    add(batch)
    before = state(batch)
    batch.add_cards(*(ids([]) for _ in range(7)))
    batch.use_cards(ids([]), ids([]), rows([]))
    batch.remove_cards(ids([]), ids([]), rows([]))
    batch.restore_displays(ids([]), ids([]))
    batch.reset_environments(ids([]))
    assert batch.actor_hands(ids([]), ids([])).shape == (0, 8, 3)
    unchanged(batch, before)
    batch.seed_hand(0, 0, rows([]))
    assert hand(batch).shape == (0, 4)
    assert np.count_nonzero(batch.snapshot()[0, 0]) == 0


@pytest.mark.parametrize(
    "args",
    [
        (0, 2, 8),
        (1, 1, 8),
        (1, 10, 8),
        (1, 2, 0),
        (1, 2, 513),
        (10000, 9, 512),
    ],
)
def test_native_dimensions_bounded(args):
    size, players, capacity = args
    with pytest.raises(ValueError):
        game(size=size, players=players, capacity=capacity)


@pytest.mark.parametrize(
    "profiles", [[], [[1, 0]], [[1, 6]], [[0, 1]], [[297, 1]], [[1, 1], [1, 2]]]
)
def test_native_profile_rejects_events_duplicates_and_unknown_categories(profiles):
    with pytest.raises(ValueError):
        native.DreamInventoryBatch(1, 2, ids(profiles).reshape(-1, 2), 8)


def test_source_pins_exact_profiles_and_false_readiness_flags():
    pinned = plan()
    assert len(pinned.profiles) == 237
    assert Counter(kind for _, kind in pinned.profiles) == {1: 107, 2: 78, 3: 19, 4: 30, 5: 3}
    assert pinned.profile_sha256 == INVENTORY_PROFILE_SHA256
    assert native.DREAM_INVENTORY_SCHEMA_VERSION == 1
    assert native.DREAM_INVENTORY_RULESET_ID == DREAM_INVENTORY_RULESET_ID
    metadata = DreamInventoryMetadata(plan=pinned, batch_size=1, player_count=9, capacity=512)
    assert DreamInventoryMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    assert not metadata.local_training_eligible
    assert not metadata.official_fidelity_verified
    assert not metadata.action_observation_checkpoint_compatible
    assert not metadata.promotion_eligible


@pytest.mark.parametrize(
    "changes",
    [
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profiles": ((1, 1),)},
        {"profile_fields": ("true", "fake")},
        {"categories": (("weapons", 4),)},
        {"promotion_eligible": True},
        {"disguise_percent": 51},
    ],
)
def test_plan_cannot_relax_pins_or_claim_validation(changes):
    with pytest.raises(ValidationError):
        DreamInventoryPlan.model_validate({**plan().model_dump(), **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"batch_size": 100000, "player_count": 9},
        {"batch_size": True},
        {"capacity": 513},
        {"state_fields": ("hp",)},
        {"actor_hand_fields": ("actual_model_id",)},
        {"full_game_training_ready": True},
        {"local_training_eligible": True},
        {"item_registration_is_battle_effect_coverage": True},
        {"unknown_field": 1},
    ],
)
def test_metadata_cannot_overallocate_or_change_contract(changes):
    payload = DreamInventoryMetadata(
        plan=plan(), batch_size=1, player_count=2, capacity=8
    ).model_dump()
    with pytest.raises(ValidationError):
        DreamInventoryMetadata.model_validate({**payload, **changes})


def test_source_adapter_rechecks_unchecked_catalog_and_bible_drift():
    catalog = read_api_catalog_snapshot(CATALOG)
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    damaged = catalog.items[0].model_copy(
        update={"raw": {**catalog.items[0].raw, "category": "armor"}}
    )
    with pytest.raises(ValueError, match="checksum"):
        build_dream_inventory_plan(
            catalog.model_copy(update={"items": (damaged, *catalog.items[1:])}), bible
        )
    sections = {**bible.reference_sections, "curses": ("Dream", "different wording")}
    with pytest.raises(ValueError, match="help"):
        build_dream_inventory_plan(
            catalog, bible.model_copy(update={"reference_sections": sections})
        )
    categories = {
        **bible.catalog,
        "miracles": bible.catalog["miracles"].model_copy(update={"notes": ()}),
    }
    with pytest.raises(ValueError, match="help"):
        build_dream_inventory_plan(catalog, bible.model_copy(update={"catalog": categories}))


def test_factory_fails_closed_on_native_identity_drift(monkeypatch):
    monkeypatch.setattr(native, "DREAM_INVENTORY_RULESET_ID", "different")
    with pytest.raises(ProvisionalRuleUnavailableError, match="contract differs"):
        create_provisional_dream_inventory_batch(
            catalog_path=CATALOG, bible_path=BIBLE, batch_size=1
        )


def test_local_curse_composition_preserves_dream_on_mild_cure_and_restores_on_full():
    curses = native.CurseDynamicsBatch(1, 2, 40)
    inventory = game(size=1, players=2)
    curses.apply_curses(ids([0]), ids([0]), ids([2]))
    curses.apply_curses(ids([0]), ids([0]), ids([1]))
    add(inventory, mask=int(curses.snapshot()[0, 0, 2]), ticket=0, fake=1)
    curses.cure_players(ids([0]), ids([0]), ids([1]))
    assert curses.snapshot()[0, 0, 2] == 2
    assert hand(inventory)[0, 2] == 2
    curses.cure_players(ids([0]), ids([0]), ids([2]))
    inventory.restore_displays(ids([0]), ids([0]))
    np.testing.assert_array_equal(hand(inventory), rows([[1, 1, 0, 0]]))
    assert not DreamInventoryMetadata(
        plan=plan(), batch_size=1, player_count=2, capacity=8
    ).full_game_training_ready


def test_observed_flame_inventory_operations_match_without_claiming_complete_run():
    from godfield_bot.acquisition_probe import AcquisitionEvidenceBatch

    fixture = json.loads(Path("tests/fixtures/acquisition-v1-retained-flame.json").read_text())
    evidence = [
        AcquisitionEvidenceBatch.model_validate_json(json.dumps(item["payload"]))
        for item in fixture["evidence"]
    ]
    snapshots = [snapshot for batch in evidence for snapshot in batch.snapshots]
    configured = create_provisional_dream_inventory_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1
    )
    batch = configured.batch

    def raw(snapshot):
        return rows(
            [
                [item.instance_id, item.model_id, item.fake_model_id or 0, int(item.used is True)]
                for item in snapshot.self_items
            ]
        )

    for before, after in pairwise(snapshots):
        batch.seed_hand(0, 0, raw(before))
        flame = next(row for row in raw(before) if row[0] == 8)
        batch.use_cards(ids([0]), ids([0]), flame.reshape(1, 4))
        expected_without_gift = raw(after)[:-1]
        np.testing.assert_array_equal(hand(batch), expected_without_gift)
        gift = raw(after)[-1]
        # Reproduce the explicit display using a caller ticket, not official RNG.
        kind = dict(configured.metadata.plan.profiles)[int(gift[1])]
        pool = sorted(
            model for model, category in configured.metadata.plan.profiles if category == kind
        )
        add(
            batch,
            instance=int(gift[0]),
            model=int(gift[1]),
            mask=2 if gift[2] else 0,
            ticket=0 if gift[2] else 99,
            fake=pool.index(int(gift[2])) if gift[2] else 0,
        )
        np.testing.assert_array_equal(hand(batch), raw(after))
    assert batch.miracle_use_count == 2
    assert not fixture["event_complete"]
    assert not configured.metadata.official_fidelity_verified


def test_all_237_dream_models_use_exact_ascending_full_category_pools():
    configured = create_provisional_dream_inventory_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=237, player_count=9, capacity=1
    )
    batch = configured.batch
    profiles = configured.metadata.plan.profiles
    pools = {
        kind: sorted(model for model, category in profiles if category == kind)
        for kind in range(1, 6)
    }
    fake_tickets = [index % len(pools[kind]) for index, (_, kind) in enumerate(profiles)]
    batch.add_cards(
        ids(range(237)),
        ids([8] * 237),
        ids([1] * 237),
        ids([model for model, _ in profiles]),
        ids([2] * 237),
        ids([49] * 237),
        ids(fake_tickets),
    )
    expected = [
        pools[kind][ticket] for (_, kind), ticket in zip(profiles, fake_tickets, strict=True)
    ]
    np.testing.assert_array_equal(batch.snapshot()[:, 8, 0, 2], ids(expected))
    np.testing.assert_array_equal(
        batch.actor_hands(ids(range(237)), ids([8] * 237))[:, 0, 1], ids(expected)
    )
    batch.use_cards(ids(range(237)), ids([8] * 237), batch.snapshot()[:, 8, 0, :].copy())
    assert batch.consumed_count == 207
    assert batch.miracle_use_count == 30


def test_bulk_gift_same_owner_preserves_input_order_and_checks_cumulative_capacity():
    batch = game(capacity=2)
    batch.add_cards(
        ids([0, 0]),
        ids([0, 0]),
        ids([2, 1]),
        ids([210, 1]),
        ids([0, 0]),
        ids([99, 99]),
        ids([0, 0]),
    )
    np.testing.assert_array_equal(hand(batch), rows([[2, 210, 0, 0], [1, 1, 0, 0]]))
    before = state(batch)
    with pytest.raises(ValueError, match="capacity"):
        batch.add_cards(
            ids([1, 1, 1]),
            ids([0, 0, 0]),
            ids([1, 2, 3]),
            ids([1, 1, 1]),
            ids([0] * 3),
            ids([99] * 3),
            ids([0] * 3),
        )
    unchanged(batch, before)


def test_mixed_owner_use_and_remove_are_independent_and_wrong_ownership_is_atomic():
    batch = game()
    add(batch, instance=1)
    add(batch, owner=1, instance=2, model=215)
    add(batch, env=1, owner=2, instance=1, model=191)
    before = state(batch)
    with pytest.raises(ValueError, match="owned"):
        batch.use_cards(ids([0, 0]), ids([0, 2]), rows([[1, 1, 0, 0], [2, 215, 0, 0]]))
    unchanged(batch, before)
    batch.use_cards(
        ids([0, 1, 0]), ids([1, 2, 0]), rows([[2, 215, 0, 0], [1, 191, 0, 0], [1, 1, 0, 0]])
    )
    assert hand(batch).shape == (0, 4)
    assert hand(batch, env=1, owner=2).shape == (0, 4)
    np.testing.assert_array_equal(hand(batch, owner=1), rows([[2, 215, 0, 1]]))
    assert batch.consumed_count == 2
    assert batch.miracle_use_count == 1


def test_typed_contiguous_inputs_and_length_checks_fail_before_mutation():
    batch = game()
    add(batch)
    before = state(batch)
    with pytest.raises(TypeError):
        batch.seed_hand(0, 0, np.asarray([[2, 1, 0, 0]], dtype=np.float64))
    with pytest.raises(TypeError):
        batch.use_cards(ids([0]), ids([0]), [[1, 1, 0, 0]])
    with pytest.raises(TypeError):
        batch.actor_hands(ids([0]), ids([0]).astype(np.int32))
    with pytest.raises(TypeError):
        batch.actor_hands(ids([0, 0, 0, 0])[::2], ids([0, 0]))
    with pytest.raises(ValueError, match="length"):
        batch.add_cards(ids([0]), ids([0]), ids([2]), ids([1]), ids([0]), ids([]), ids([0]))
    with pytest.raises(ValueError, match="length"):
        batch.use_cards(ids([0]), ids([0]), rows([]))
    with pytest.raises(ValueError, match="length"):
        batch.actor_hands(ids([0]), ids([]))
    unchanged(batch, before)


def test_maximum_instance_id_and_sparse_category_pool_work():
    batch = native.DreamInventoryBatch(1, 2, ids([[215, 4]]), 1)
    add(batch, instance=2**53 - 1, model=215, mask=2, ticket=0)
    np.testing.assert_array_equal(hand(batch), rows([[2**53 - 1, 215, 215, 0]]))
    batch.use_cards(ids([0]), ids([0]), hand(batch))
    assert batch.miracle_use_count == 1


@pytest.mark.parametrize("sequence", [9, 11])
def test_event_backed_flame_first_use_and_reuse_match_new_inventory(sequence):
    from godfield_bot.acquisition_v4 import AcquisitionEvidenceBatchV4

    fixture = json.loads(Path("tests/fixtures/acquisition-v4-32d8eeeb.json").read_text())
    evidence = [
        AcquisitionEvidenceBatchV4.model_validate_json(json.dumps(record["payload"]))
        for record in fixture["evidence"]
        if record["payload"]["source_kind"] == "official-acquisition-evidence-v4"
    ]
    captured = [snapshot for batch in evidence for snapshot in batch.snapshots]
    before, after = captured[sequence - 2 : sequence]
    selection = after.events[0]
    assert selection.action == "useAttackItems" and selection.self_item_payload_bound
    assert after.event_owners[0].item_owner_player_id == after.self_player_id == 2
    configured = create_provisional_dream_inventory_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, player_count=3
    )

    def raw(items):
        return rows(
            [
                [item.instance_id, item.model_id, item.fake_model_id or 0, int(item.used is True)]
                for item in items
            ]
        )

    batch = configured.batch
    batch.seed_hand(0, 1, raw(before.self_items))
    batch.use_cards(ids([0]), ids([1]), raw(selection.items))
    assert batch.miracle_use_count == 1
    assert batch.gift_count == 0
    assert hand(batch, owner=1)[-1].tolist() == [4, 215, 0, 1]
    gifts = [
        event for event in after.events if event.action == "gift" and event.self_item_payload_bound
    ]
    assert len(gifts) == 1 and gifts[0].overflow_item is None
    gift = raw([gifts[0].item])[0]
    assert gift[2] == gift[3] == 0
    add(batch, owner=1, instance=int(gift[0]), model=int(gift[1]))
    np.testing.assert_array_equal(hand(batch, owner=1), raw(after.self_items))
    assert not configured.metadata.official_fidelity_verified


def test_real_trade_cards_are_registered_but_virtual_and_event_models_are_not():
    configured = create_provisional_dream_inventory_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=5
    )
    batch = configured.batch
    assert configured.metadata.plan.handable_model_count == 237
    assert dict(configured.metadata.plan.profiles)[3] == 5
    assert dict(configured.metadata.plan.profiles)[4] == 5
    assert dict(configured.metadata.plan.profiles)[5] == 5
    for model in (3, 4, 5):
        add(batch, instance=model, model=model)
    for model in (1, 2, 240, 245, 287):
        before = state(batch)
        with pytest.raises(ValueError, match="registered"):
            add(batch, instance=99, model=model)
        unchanged(batch, before)
    batch.use_cards(ids([0] * 3), ids([0] * 3), hand(batch))
    assert batch.consumed_count == 3  # Inventory lifecycle hypothesis, not economic effects.
    assert not configured.metadata.transfer_economy_and_removal_rules_implemented


def test_query_and_operation_output_bounds_checked_before_allocating():
    batch = game(capacity=512)
    before = state(batch)
    with pytest.raises(ValueError, match="slot limit"):
        batch.actor_hands(ids([0] * 3907), ids([0] * 3907))
    with pytest.raises(ValueError, match="row limit"):
        batch.restore_displays(ids([0] * 1_000_001), ids([0] * 1_000_001))
    unchanged(batch, before)


def test_seed_dimensions_and_profile_inputs_do_not_mutate_on_failure():
    batch = game(capacity=1)
    add(batch)
    before = state(batch)
    for env, owner, items in (
        (2, 0, [[2, 1, 0, 0]]),
        (0, 3, [[2, 1, 0, 0]]),
        (0, 0, [[2, 1, 0, 0], [3, 2, 0, 0]]),
    ):
        with pytest.raises(ValueError, match="dimensions"):
            batch.seed_hand(env, owner, rows(items))
        unchanged(batch, before)
    with pytest.raises(TypeError):
        native.DreamInventoryBatch(1, 2, ids(PROFILES).astype(np.float64), 1)
    with pytest.raises(ValueError, match="profile count"):
        native.DreamInventoryBatch(1, 2, ids([[1, 1]] * 297), 1)


def test_seeded_mixed_lifecycle_matches_independent_ordered_reference():
    batch = game(size=8, players=3, capacity=16)
    rng = np.random.default_rng(67)
    reference = [[[] for _ in range(3)] for _ in range(8)]
    categories = dict(PROFILES)
    pools = {
        kind: sorted(model for model, category in PROFILES if category == kind)
        for kind in range(1, 6)
    }
    counters = [0] * 5
    instance = 0
    for _ in range(512):
        env, owner = int(rng.integers(8)), int(rng.integers(3))
        current = reference[env][owner]
        operation = int(rng.integers(6))
        if operation == 0 and len(current) < 16:
            instance += 1
            model, kind = PROFILES[int(rng.integers(len(PROFILES)))]
            mask, ticket = int(rng.integers(16)), int(rng.integers(100))
            fake_ticket = int(rng.integers(len(pools[kind])))
            add(
                batch,
                env=env,
                owner=owner,
                instance=instance,
                model=model,
                mask=mask,
                ticket=ticket,
                fake=fake_ticket,
            )
            fake = pools[kind][fake_ticket] if mask & 2 and ticket < 50 else 0
            current.append([instance, model, fake, 0])
            counters[0] += 1
        elif operation in (1, 2) and current:
            count = min(len(current), int(rng.integers(1, 4)))
            selection = [
                current[int(slot)].copy() for slot in rng.choice(len(current), count, replace=False)
            ]
            selected_ids = {item[0] for item in selection}
            current[:] = [item for item in current if item[0] not in selected_ids]
            getattr(batch, "use_cards" if operation == 1 else "remove_cards")(
                ids([env] * count), ids([owner] * count), rows(selection)
            )
            if operation == 1:
                for item in selection:
                    if categories[item[1]] == 4:
                        item[3] = 1
                        current.append(item)
                        counters[2] += 1
                    else:
                        counters[1] += 1
            else:
                counters[3] += count
        elif operation == 3:
            batch.restore_displays(ids([env]), ids([owner]))
            for item in current:
                counters[4] += int(item[2] != 0)
                item[2] = 0
        elif operation == 4:
            batch.reset_environments(ids([env]))
            reference[env] = [[], [], []]
        else:
            instance += 1
            current[:] = [[instance, 215, 210, 1], [instance + 1, 1, 2, 0]]
            instance += 1
            batch.seed_hand(env, owner, rows(current))
        expected = np.zeros((8, 3, 16, 4), dtype=np.int64)
        for env_index in range(8):
            for owner_index in range(3):
                items = reference[env_index][owner_index]
                expected[env_index, owner_index, : len(items)] = rows(items)
        np.testing.assert_array_equal(batch.snapshot(), expected)
        assert state(batch)[1] == tuple(counters)
