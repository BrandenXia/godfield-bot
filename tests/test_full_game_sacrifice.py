"""Post-Apocalypse shared removal, tagged replacements, reactions and rollback."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import PLAN, drain, hand, ids, load, step, tickets
from test_full_game_generated import game as raw_game

from godfield_bot.api_catalog import ApiCatalogItem, api_catalog_digest
from godfield_bot.full_game import SACRIFICE_SNAPSHOT_FIELDS, create_development_full_game_batch
from godfield_bot.full_game_discard import REMOVAL_ABILITY_NOTES, FullGameDiscardPlan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
QUIET_SEED = next(
    seed
    for seed in range(1000)
    if all(
        next_ticket >= 25
        for next_ticket in [
            n % 100 for _, n in zip(range(3), tickets(seed, 0, 0x24A19947B3916CF7), strict=False)
        ]
    )
)


def game(**options):
    return raw_game(
        **(
            dict(
                seed=QUIET_SEED,
                sacrifice_enabled=True,
                apocalypse_after_turns=1,
                gift_profiles=ids([[191, 1]]),
                max_turns=100,
                max_decisions=1000,
            )
            | options
        )
    )


def start(b, size=1):
    b.start_environments(ids(range(size)))
    step(b, [0] * size)
    assert (b.episode_snapshot()[:, 2:4] == [1, 1]).all()
    assert b.apocalypse_observations()[:, 1].all()


def sacrifice(b, choices=(1,)):
    step(b, [19])
    for choice in choices:
        step(b, [choice])
    step(b, [0])


def snapshot(b):
    return tuple(
        getattr(b, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "player_observations",
            "discard_observations",
            "discard_order",
            "discard_snapshot",
            "sacrifice_snapshot",
            "sacrifice_model_counts",
            "acquisition_snapshot",
            "attack_family_snapshot",
            "devil_snapshot",
            "revival_snapshot",
        )
    )


def same(a, b):
    for x, y in zip(a, b, strict=True):
        np.testing.assert_array_equal(x, y)


def test_current_translations_pin_same_catalog_and_distinct_replacement_notes():
    source = Path("data/snapshots/2026-10-17/i18n-en.json")
    raw = source.read_bytes().rstrip(b"\n")
    data = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == PLAN.discard.translation_sha256
    provenance = json.loads(source.with_name("i18n-en-provenance.json").read_text())
    assert provenance["body_sha256_excluding_archive_newline"] == PLAN.discard.translation_sha256
    client = source.parent / provenance["same_client_as"]
    assert hashlib.sha256(client.read_bytes()).hexdigest() == provenance["current_client_sha256"]
    assert provenance["current_client_sha256"] == PLAN.discard.bible_client_sha256
    assert (source.parent / provenance["same_catalog_as"]).is_file()
    assert (
        api_catalog_digest(
            tuple(ApiCatalogItem(model_id=i + 1, raw=r) for i, r in enumerate(data["items"]))
        )
        == PLAN.discard.catalog_sha256
    )
    for path, text in REMOVAL_ABILITY_NOTES:
        value = data
        for key in path.split("."):
            value = value[key]
        assert value == text
    assert (
        hashlib.sha256(
            json.dumps(REMOVAL_ABILITY_NOTES, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        == PLAN.discard.ability_notes_sha256
    )


@pytest.mark.parametrize("model", PLAN.discard.discard_model_ids)
@pytest.mark.parametrize("players", [2, 3, 9])
def test_all128_eligible_models_are_removed_not_used_and_receive_a_separate_replacement(
    model, players
):
    b = game(players=players)
    hand(b, [model], 1)
    start(b)
    before = b.diagnostic_players().copy()
    step(b, [19])
    assert b.discard_observations().tolist() == [[1, 0, 0, 64, 2]]
    assert b.policy_gradient_masks()[0, 0]
    step(b, [1])
    assert b.sacrifice_snapshot()[0, 6] == b.automatic_gift_count == 0
    step(b, [0])
    assert b.sacrifice_snapshot().tolist() == [[1, 1, 0, 1, 1, 0, 1, 1, 0]]
    assert b.sacrifice_model_counts()[0, 191 - 3] == 1
    assert not b.discard_snapshot().any()
    assert b.discard_count == b.discarded_card_count == 0
    assert b.consumed_count == b.miracle_use_count == b.mp_spent == b.removal_count == 0
    assert b.devil_count == 0 and b.automatic_gift_count == 1
    np.testing.assert_array_equal(before[:, :, :5], b.diagnostic_players()[:, :, :5])
    assert b.diagnostic_inventory()[0, 1, 0, 1:].tolist() == [191, 0, 0]
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 1] + [0] * (players - 2)
    assert b.episode_snapshot()[0, 4] == 2


@pytest.mark.parametrize("model", [m for m, c in PLAN.inventory.profiles if c == 1] + [208, 209])
def test_weapons_sun_and_mortar_stay_protected_after_apocalypse(model):
    b = game()
    hand(b, [model], 1)
    start(b)
    assert not b.choice_masks()[0, 19]
    old = snapshot(b)
    with pytest.raises(ValueError):
        step(b, [19])
    same(old, snapshot(b))


def test_multi_selection_undo_used_miracle_and_survivor_order_no_cost_or_performance():
    b = game()
    hand(b, [127, (237, 235, 1), 191, 208, 209], 1)
    start(b)
    sacrifice(b, (1, 2, 3, 1))
    assert b.sacrifice_snapshot()[0].tolist() == [1, 4, 0, 1, 2, 1, 2, 2, 0]
    assert b.diagnostic_inventory()[0, 1, :3, 1].tolist() == [127, 208, 209]
    assert b.diagnostic_inventory()[0, 1, 3:5, 1].tolist() == [191, 191]
    assert b.consumed_count == b.miracle_use_count == b.mp_spent == 0
    assert b.automatic_gift_count == 2


def test_selection_limit_retains_confirm_and_cancel_without_creating_gifts():
    b = game()
    hand(b, [127, 128], 1)
    start(b)
    step(b, [19])
    for _ in range(63):
        step(b, [1])
    step(b, [2])
    assert b.choice_masks()[0, [0, 1, 2, 19]].tolist() == [True, False, False, True]
    assert b.sacrifice_snapshot()[0, 6] == 0
    step(b, [19])
    assert b.sacrifice_snapshot()[0].tolist() == [1, 64, 1, 0, 0, 0, 0, 0, 0]
    assert b.automatic_gift_count == 0
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_discard_before_threshold_never_invents_sacrifice_replacements():
    b = game(apocalypse_after_turns=2)
    hand(b, [127])
    b.start_environments(ids([0]))
    sacrifice(b)
    assert b.discard_count == b.discarded_card_count == 1
    assert not b.sacrifice_snapshot().any()
    assert b.automatic_gift_count == 0 and not b.apocalypse_observations()[0, 1]


def test_late_hidden_protected_card_rolls_back_whole_batch_and_replacement_stream():
    b, reference = [game(size=2, gift_profiles=ids(PLAN.gifts.model_weights)) for _ in range(2)]
    for current in (b, reference):
        hand(current, [127], 1, 0)
        load(current, owner=1, env=0, mask=2)
        hand(current, [(208, 191, 0)], 1, 1)
        start(current, 2)
        step(current, [19, 19])
        step(current, [1, 1])
    old = snapshot(b)
    with pytest.raises(ValueError, match="actual sacrifice model is forbidden"):
        step(b, [0, 0])
    same(old, snapshot(b))
    step(b, [0], [0])
    step(reference, [0], [0])
    same(snapshot(b), snapshot(reference))


@pytest.mark.parametrize("players", [2, 3, 9])
def test_dead_owner_suppresses_replacements_without_extra_tick_or_devil_draw(players):
    b = game(players=players)
    hand(b, [127], 1)
    load(b, owner=1, hp=1, illness=3)
    start(b)
    sacrifice(b)
    assert b.sacrifice_snapshot()[0].tolist() == [1, 1, 0, 1, 1, 0, 1, 0, 1]
    assert b.automatic_gift_count == b.devil_count == 0
    assert b.suppressed_gift_count == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 1] + [0] * (players - 2)


@pytest.mark.parametrize("limits", [{"max_turns": 2}, {"max_decisions": 4}])
def test_absorbing_limit_reports_suppressed_replacement_not_successful_delivery(limits):
    b = game(**limits)
    hand(b, [127], 1)
    start(b)
    sacrifice(b)
    assert b.episode_snapshot()[0, 3] == 13
    assert b.sacrifice_snapshot()[0, 6:].tolist() == [1, 0, 1]
    assert b.automatic_gift_count == 0 and not b.discard_observations().any()


def test_devil_sun_bow_reactions_distinguish_tagged_and_ordinary_receipts():
    b = game(devil_profiles=ids([[240, 100, 1, 10]]), refill_on_use=True)
    hand(b, [127, 128, 129, 208, 112], 1)
    load(b, owner=1, hp=5)
    start(b)
    sacrifice(b, (1, 2, 3))
    assert b.episode_snapshot()[0, 3] == 4
    assert b.sacrifice_snapshot()[0, 6:].tolist() == [3, 2, 0]
    assert b.revival_count == b.ascension_count == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 1, 0]
    drain(b)
    assert b.sacrifice_snapshot()[0, 6:].tolist() == [3, 2, 1]
    assert b.automatic_gift_count == 2 and b.suppressed_gift_count == 3
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 1, 0]
    assert not b.attack_family_snapshot()[0, 13:].any()


def test_bow_decision_limit_keeps_tagged_receipt_pending_not_delivered_or_suppressed():
    b = game(devil_profiles=ids([[240, 100, 1, 10]]), refill_on_use=True, max_decisions=7)
    hand(b, [127, 128, 129, 208, 112], 1)
    load(b, owner=1, hp=5)
    start(b)
    sacrifice(b, (1, 2, 3))
    step(b, [0])
    assert b.episode_snapshot()[0, 3] == 13
    assert b.sacrifice_snapshot()[0, 6:].tolist() == [3, 2, 0]
    assert b.sacrifice_model_counts().sum() == 2
    assert b.attack_family_snapshot()[0, 13] > 0
    old = snapshot(b)
    with pytest.raises(ValueError):
        step(b, [0])
    same(old, snapshot(b))
    b.reset_environments(ids([0]))
    assert not b.sacrifice_snapshot().any()
    assert not b.attack_family_snapshot().any()


def test_snapshot_is_owned_readonly_and_reset_clears_only_episode_diagnostics():
    b = game()
    hand(b, [127], 1)
    start(b)
    sacrifice(b)
    old = b.sacrifice_snapshot()
    models = b.sacrifice_model_counts()
    assert not old.flags.writeable and old[0, 7] == 1
    b.reset_environments(ids([0]))
    assert not b.sacrifice_snapshot().any()
    assert not models.flags.writeable and not b.sacrifice_model_counts().any()
    assert models.sum() == 1
    assert old[0, 7] == 1


def test_sacrifice_triggered_self_renewing_sun_gifts_stop_at_atomic_native_bound():
    b = game(
        devil_profiles=ids([[240, 100, 1, 10]]),
        gift_profiles=ids([[208, 1]]),
        refill_on_use=True,
    )
    hand(b, [127], 1)
    load(b, owner=1, hp=5)
    start(b)
    step(b, [19])
    step(b, [1])
    old = snapshot(b)
    with pytest.raises(ValueError, match="post-turn receipt bound exceeded"):
        step(b, [0])
    same(old, snapshot(b))
    assert b.automatic_gift_count == b.revival_count == 0


@pytest.mark.parametrize(
    "change",
    [
        {"current_ability_notes": ()},
        {"sacrifice_virtual_model_id": 1},
        {"translation_sha256": "0" * 64},
        {"sacrifice_implemented": False},
        {"official_sacrifice_cardinality_and_timing_verified": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
    ],
)
def test_forged_source_and_readiness_scope_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameDiscardPlan.model_validate(PLAN.discard.model_dump() | change)


@pytest.mark.parametrize("missing", ["discard_model_ids", "gift_profiles"])
def test_raw_sacrifice_requires_explicit_removal_and_replacement_dependencies(missing):
    with pytest.raises(ValueError, match="Sacrifice requires"):
        game(apocalypse_after_turns=0, dream_defense_profiles=None, **{missing: None})


def test_confused_native_controller_can_sacrifice_without_learner_selection_or_gradient():
    seed = next(
        s
        for s in range(1000)
        if next(tickets(s, 0, 0xC5D1B023286085F0)) % 2 == 0
        and next(tickets(s, 0, 0x24A19947B3916CF7)) % 100 >= 25
    )
    b = game(seed=seed)
    hand(b, [127], 1)
    b.seed_confusion(ids([0]), ids([1]), ids([1]))
    start(b)
    assert np.flatnonzero(b.choice_masks()[0]).tolist() == [0]
    assert not b.policy_gradient_masks()[0, 0]
    step(b, [0])
    assert b.sacrifice_snapshot()[0].tolist() == [0, 0, 0, 1, 1, 0, 1, 1, 0]
    assert b.confusion_snapshot()[0, 12] == 1
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 1, 0]


def test_factory_enables_sacrifice_without_enabling_apocalypse_by_default():
    c = create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=1,
        capacity=18,
    )
    assert c.metadata.sacrifice_enabled and c.metadata.apocalypse_after_turns == 0
    assert c.metadata.sacrifice_snapshot_fields == SACRIFICE_SNAPSHOT_FIELDS
    assert not c.metadata.full_game_training_ready and not c.metadata.promotion_eligible
