"""Protected hidden removals retain custody, never create free replacements."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import PLAN, hand, ids, load, step
from test_full_game_sacrifice import game

from godfield_bot.full_game import FullGameMetadata, create_development_full_game_batch

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
DISPLAYS = [m for m, category in PLAN.inventory.profiles if category == 3 and m not in (208, 209)]


def scenario(actual=208, display=196, *, sacrifice=False, extra=(), enabled=True, **options):
    b = game(
        resolve_hidden_removals=enabled,
        apocalypse_after_turns=1 if sacrifice else 0,
        **options,
    )
    for env in range(len(b.episode_snapshot())):
        hand(b, [(actual, display, 0), *extra], owner=1, env=env)
    envs = ids(range(len(b.episode_snapshot())))
    b.start_environments(envs)
    step(b, [0] * len(envs))
    return b


def remove(b, choices=(1,)):
    step(b, [19])
    for choice in choices:
        step(b, [choice])
    step(b, [0])


@pytest.mark.parametrize("actual", [208, 209])
@pytest.mark.parametrize("display", DISPLAYS)
@pytest.mark.parametrize("sacrifice", [False, True])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_every_protected_disguise_is_retained_without_use_cost_or_replacement(
    actual, display, sacrifice, players
):
    b = scenario(actual, display, sacrifice=sacrifice, players=players)
    before = b.diagnostic_inventory().copy()
    remove(b)
    np.testing.assert_array_equal(b.diagnostic_inventory(), before)
    expected = [int(not sacrifice), int(sacrifice), 1, 0, 1, int(actual == 208), int(actual == 209)]
    assert b.hidden_removal_snapshot().tolist() == [expected]
    assert b.automatic_gift_count == b.consumed_count == b.miracle_use_count == b.mp_spent == 0
    assert b.discarded_card_count == b.sacrifice_snapshot()[0, 6] == 0
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 1] + [0] * (players - 2)
    assert b.episode_snapshot()[0, 4] == 2


@pytest.mark.parametrize("sacrifice", [False, True])
@pytest.mark.parametrize("choices", [(1, 2, 3, 4), (4, 3, 2, 1), (2, 1, 4, 3)])
def test_mixed_selection_retains_protected_order_and_replaces_only_actual_removals(
    sacrifice, choices
):
    b = scenario(208, 191, sacrifice=sacrifice, extra=(127, (209, 196, 0), (237, 235, 1)))
    remove(b, choices)
    assert b.diagnostic_inventory()[0, 1, :2].tolist() == [[101, 208, 191, 0], [103, 209, 196, 0]]
    assert b.hidden_removal_snapshot()[0].tolist() == [
        int(not sacrifice),
        int(sacrifice),
        2,
        2,
        0,
        1,
        1,
    ]
    stats = b.sacrifice_snapshot() if sacrifice else b.discard_snapshot()
    assert stats[0, [3, 4, 5]].tolist() == [1, 2, 1]
    assert b.automatic_gift_count == (2 if sacrifice else 0)
    assert b.sacrifice_snapshot()[0, 6] == (2 if sacrifice else 0)
    assert b.consumed_count == b.miracle_use_count == b.mp_spent == 0
    assert b.discarded_card_count == (0 if sacrifice else 2)


@pytest.mark.parametrize("sacrifice", [False, True])
def test_undo_and_cancel_do_not_record_an_unconfirmed_private_failure(sacrifice):
    b = scenario(sacrifice=sacrifice)
    step(b, [19])
    step(b, [1])
    assert not b.hidden_removal_snapshot().any()
    step(b, [1])
    step(b, [19])
    assert not b.hidden_removal_snapshot().any() and b.episode_snapshot()[0, 4] == 1


@pytest.mark.parametrize("actual", [208, 209])
def test_actual_protection_is_invisible_until_confirmation(actual):
    hidden, reference = scenario(actual, 196), scenario(196, 196)
    for b in (hidden, reference):
        step(b, [19])
        step(b, [1])
    for name in ("actor_hands", "choice_masks", "discard_observations", "discard_order"):
        np.testing.assert_array_equal(getattr(hidden, name)(), getattr(reference, name)())
    assert not hidden.hidden_removal_snapshot().any()


@pytest.mark.parametrize("sacrifice", [False, True])
def test_raw_strict_default_still_rolls_back_hidden_protection(sacrifice):
    b = scenario(enabled=False, sacrifice=sacrifice)
    step(b, [19])
    step(b, [1])
    before = b.diagnostic_inventory().copy(), b.episode_snapshot().copy()
    with pytest.raises(ValueError, match="model is forbidden"):
        step(b, [0])
    np.testing.assert_array_equal(b.diagnostic_inventory(), before[0])
    np.testing.assert_array_equal(b.episode_snapshot(), before[1])
    assert not b.resolve_hidden_removals and not b.hidden_removal_snapshot().any()


def test_late_stale_command_rolls_back_retention_and_all_removal_receipts():
    b = scenario(size=2, sacrifice=True, extra=(127,))
    step(b, [19, 19])
    step(b, [1, 1])
    state = b.episode_snapshot()
    commands = ids([[env, *state[env, :4], 0] for env in range(2)])
    commands[1, 2] -= 1
    before = b.diagnostic_inventory().copy()
    with pytest.raises(ValueError, match="stale"):
        b.step(commands)
    np.testing.assert_array_equal(b.diagnostic_inventory(), before)
    np.testing.assert_array_equal(b.episode_snapshot(), state)
    assert not b.hidden_removal_snapshot().any() and b.automatic_gift_count == 0


def test_reset_clears_owned_readonly_private_diagnostics():
    b = scenario()
    remove(b)
    snapshot = b.hidden_removal_snapshot()
    assert not snapshot.flags.writeable
    b.reset_environments(ids([0]))
    assert snapshot.any() and not b.hidden_removal_snapshot().any()


def test_retention_does_not_skip_the_normal_tick_or_sun_death_edge():
    b = game(resolve_hidden_removals=True, apocalypse_after_turns=0)
    hand(b, [(208, 191, 0)], owner=1)
    load(b, owner=1, hp=1, illness=1, mask=0)
    b.start_environments(ids([0]))
    step(b, [0])
    remove(b)
    assert b.hidden_removal_snapshot()[0, [0, 2, 4, 5]].tolist() == [1, 1, 1, 1]
    assert b.revival_count == 1 and b.diagnostic_players()[0, 1, 0] == 10
    assert b.diagnostic_players()[0, 1, 5] == 1
    assert not b.diagnostic_inventory()[0, 1].any()
    assert b.discarded_card_count == 0


def test_factory_pins_new_rule_and_diagnostic_boundary_without_enabling_learning():
    c = create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=1,
        player_count=3,
        capacity=18,
    )
    assert c.batch.resolve_hidden_removals and c.metadata.resolve_hidden_removals
    assert c.metadata.kernel_schema_version == 32
    assert not c.metadata.local_training_eligible and not c.metadata.promotion_eligible
    for change in ({"resolve_hidden_removals": False}, {"hidden_removal_snapshot_fields": ()}):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate(c.metadata.model_dump() | change)
