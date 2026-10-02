"""Exclusive source-pinned defenses and provisional, decision-bounded chains."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_combat_plan import FullGameCombatPlan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
SPECIALS = PLAN.combat.special_profiles
ARMOR = dict((row[0], row[1]) for row in PLAN.combat.armor_profiles)
CATEGORIES = dict(PLAN.inventory.profiles)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *,
    size=1,
    players=3,
    seed=67,
    mp=80,
    max_decisions=4000,
    refill=False,
    specials=SPECIALS,
    element=None,
    origin=0,
):
    attacks = list(PLAN.combat.attack_profiles)
    if element is not None:
        model = 6 if origin == 0 else 211
        # Deliberate arithmetic fixture, not new source-verified card claims.
        attacks = [row for row in attacks if row[0] != model] + [
            (model, 10, element, origin, origin * 2)
        ]
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        seed=seed,
        max_decisions=max_decisions,
        initial_mp=mp,
        attack_profiles=ids(attacks),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(specials).reshape(-1, 5),
        gift_profiles=ids([(191, 1)]) if refill else None,
        refill_on_use=refill,
        hand_limit=18,
        oldest_overflow=refill,
    )


def seed(batch, models, *, owner=0, env=0):
    batch.seed_hand(
        env,
        owner,
        ids([(owner * 100 + i + 1, model, 0, 0) for i, model in enumerate(models)]).reshape(-1, 4),
    )


def load(batch, *, owner=0, env=0, hp=40, mp=80, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    envs = list(range(len(choices))) if envs is None else envs
    episodes = batch.episode_snapshot()
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def begin(batch, model=35, defense=(), *, size=1):
    for env in range(size):
        seed(batch, [model], env=env)
        seed(batch, defense, owner=1, env=env)
    batch.start_environments(ids(range(size)))
    for choice in (1, 0, 20):
        step(batch, [choice] * size)


def hand(batch, owner, env=0):
    cards = batch.diagnostic_inventory()[env, owner]
    return cards[cards[:, 0] != 0]


def snapshot(batch):
    return (
        [
            getattr(batch, view)()
            for view in (
                "episode_snapshot",
                "diagnostic_players",
                "diagnostic_inventory",
                "actor_hands",
                "player_observations",
                "choice_masks",
                "pending_observations",
                "selected_defenses",
                "special_defense_observations",
                "acquisition_snapshot",
                "selected_attacks",
                "attack_order",
                "attack_selection_observations",
            )
        ],
        [
            getattr(batch, counter)
            for counter in (
                "action_count",
                "block_count",
                "reflection_count",
                "bounce_count",
                "attack_count",
                "resolved_attack_count",
                "mp_spent",
                "hp_damage",
                "consumed_count",
                "miracle_use_count",
                "automatic_gift_count",
                "suppressed_gift_count",
                "overflow_count",
            )
        ],
    )


def same(batch, before):
    after = snapshot(batch)
    for old, new in zip(before[0], after[0], strict=True):
        np.testing.assert_array_equal(old, new)
    assert before[1] == after[1]


@pytest.mark.parametrize("profile", SPECIALS)
@pytest.mark.parametrize("element", range(7))
@pytest.mark.parametrize("origin", [0, 1])
def test_origin_element_matrix_uses_special_or_printed_armor_not_weapon_attack_value(
    profile, element, origin
):
    model, kind, source, neutral_only, cost = profile
    batch = game(element=element, origin=origin)
    begin(batch, model=6 if origin == 0 else 211, defense=[model])
    applicable = (source == -1 or source == origin) and (not neutral_only or element == 0)
    ordinary = model in ARMOR and element in (0, 6)
    assert bool(batch.choice_masks()[0, 1]) == (applicable or ordinary)
    if applicable or ordinary:
        step(batch, [1])
        observation = batch.special_defense_observations()[0]
        assert observation.tolist() == [
            1,
            0,
            0,
            kind if applicable else 0,
            cost if applicable else 0,
        ]
        assert batch.pending_observations()[0, 6] == (0 if applicable else ARMOR[model])
    else:
        before = snapshot(batch)
        with pytest.raises(ValueError, match="unavailable"):
            step(batch, [1])
        same(batch, before)


@pytest.mark.parametrize("profile", SPECIALS)
def test_every_special_confirm_consumes_or_retains_pays_and_gives_fresh_response(profile):
    model, kind, origin, _, cost = profile
    batch = game(refill=True)
    begin(batch, model=35 if origin != 1 else 218, defense=[model, 194])
    step(batch, [1])
    assert not batch.choice_masks()[0, 2]
    step(batch, [0])
    assert batch.mp_spent == cost + (12 if origin == 1 else 0)
    retained = CATEGORIES[model] == 4
    assert [value for value in hand(batch, 1)[:, 1].tolist() if value != 191] == (
        [194, model] if retained else [194]
    )
    if retained:
        assert hand(batch, 1)[1, 3] == 1 and batch.miracle_use_count == 1 + int(origin == 1)
    assert (batch.block_count, batch.reflection_count, batch.bounce_count) == tuple(
        int(kind == k) for k in (1, 2, 3)
    )
    if kind >= 2:
        assert batch.episode_snapshot()[0, 3:5].tolist() == [4, 0]
        assert batch.resolved_attack_count == 0 and batch.automatic_gift_count == 0
        assert batch.acquisition_snapshot()[0, :2, 0].tolist() == [1, 1]
        assert not np.any(batch.selected_defenses()) and batch.pending_observations()[0, 8] == 0
        assert batch.special_defense_observations()[0, 2] == 1
        if kind == 2:
            assert batch.episode_snapshot()[0, 2] == 0
            assert batch.special_defense_observations()[0, 1] == 1
        step(batch, [0])
    assert batch.episode_snapshot()[0, 4] == 1
    assert batch.resolved_attack_count == 1 and batch.automatic_gift_count == 2
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_multiple_reflections_transfer_current_source_and_tick_original_owner_once():
    batch = game(refill=True)
    load(batch, owner=0, illness=1)
    seed(batch, [35, 190], owner=0)
    seed(batch, [190], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 0):
        step(batch, [choice])
    assert batch.special_defense_observations()[0].tolist() == [1, 1, 1, 0, 0]
    assert batch.choice_masks()[0, 1]  # Second reflection is not silently masked.
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.special_defense_observations()[0].tolist() == [1, 0, 2, 0, 0]
    assert batch.pending_observations()[0, :6].tolist() == [1, 0, 1, 10, 0, 0]
    assert batch.diagnostic_players()[0, :, 0].tolist() == [40, 40, 40]
    assert batch.automatic_gift_count == 0
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [39, 30, 40]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.reflection_count == 2 and batch.automatic_gift_count == 3
    assert batch.episode_snapshot()[0, 2] == 1


def test_reflected_darkness_full_block_does_not_kill_original_attacker():
    batch = game(players=2)
    seed(batch, [86, 148], owner=0)
    seed(batch, [190], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 0, 1, 0):
        step(batch, [choice])
    assert batch.hp_damage == batch.darkness_finish_count == 0
    assert batch.diagnostic_players()[0, :, 0].tolist() == [40, 40]


@pytest.mark.parametrize("players", [2, 3, 9])
def test_bounce_samples_all_living_seats_including_self_but_never_dead(players):
    batch = game(size=96, players=players)
    if players > 2:
        for env in range(96):
            load(batch, owner=players - 1, env=env, hp=0)
    begin(batch, model=218, defense=[234], size=96)
    step(batch, [1] * 96)
    step(batch, [0] * 96)
    targets = set(batch.episode_snapshot()[:, 2])
    assert targets == set(range(players if players == 2 else players - 1))
    assert np.all(batch.special_defense_observations()[:, 1] == 0)
    assert np.all(batch.pending_observations()[:, 3] == 25)
    assert batch.bounce_count == 96 and batch.resolved_attack_count == 0


def test_bounce_stream_is_independent_of_prior_gifts_fog_and_disguise_draws():
    first, second = game(size=64), game(size=64, refill=True)
    for batch in (first, second):
        for env in range(64):
            load(batch, env=env, mask=2)
            seed(batch, [191, 218], env=env)
            seed(batch, [234], owner=1, env=env)
        batch.start_environments(ids(range(64)))
        step(batch, [1] * 64)  # Refill + Dream consumes two unrelated random streams.
        step(batch, [0] * 64)  # Seat 1 pass.
        step(batch, [0] * 64)  # Seat 2 pass.
        step(batch, [1] * 64)  # Flame remains first slot in both hands.
        step(batch, [0] * 64)
        step(batch, [20] * 64)
        step(batch, [1] * 64)
        step(batch, [0] * 64)
    np.testing.assert_array_equal(first.episode_snapshot()[:, 2], second.episode_snapshot()[:, 2])
    assert second.automatic_gift_count == 64 and first.automatic_gift_count == 0


@pytest.mark.parametrize("model,cost,origin", [(233, 6, 0), (234, 5, 1)])
def test_reusable_defense_affordability_inclusive_payment_and_tail_retention(model, cost, origin):
    for available in (cost - 1, cost):
        batch = game()
        load(batch, owner=1, mp=available)
        begin(batch, model=35 if origin == 0 else 218, defense=[model, 194])
        assert bool(batch.choice_masks()[0, 1]) == (available == cost)
        if available == cost:
            step(batch, [1])
            step(batch, [0])
            assert hand(batch, 1).tolist() == [[102, 194, 0, 0], [101, model, 0, 1]]
            assert batch.diagnostic_players()[0, 1, 1] == 0


def test_all_seat_reusable_bounce_chain_is_bounded_by_real_decisions_not_one_hop():
    batch = game(size=32, players=9, mp=100, max_decisions=31, refill=True)
    for env in range(32):
        for owner in range(9):
            seed(batch, [218, 234] if owner == 0 else [234], env=env, owner=owner)
    batch.start_environments(ids(range(32)))
    for choice in (1, 0, 20):
        step(batch, [choice] * 32)
    for hop in range(14):
        hands = batch.actor_hands()
        choices = [int(np.flatnonzero(hands[env, :, 1] == 234)[0]) + 1 for env in range(32)]
        assert all(batch.choice_masks()[env, choice] for env, choice in enumerate(choices))
        step(batch, choices)
        step(batch, [0] * 32)
        if hop < 13:
            assert np.all(batch.special_defense_observations()[:, 2] == hop + 1)
            assert batch.automatic_gift_count == 0
    assert np.all(batch.episode_snapshot()[:, 3] == 13)
    assert np.all(batch.episode_snapshot()[:, 4] == 0)
    assert np.all(batch.diagnostic_players()[:, :, 5] == 0)
    assert batch.bounce_count == 448 and batch.resolved_attack_count == 0
    assert batch.hp_damage == batch.automatic_gift_count == 0
    assert batch.suppressed_gift_count == 480 and batch.miracle_use_count == 480
    assert batch.mp_spent == 32 * (12 + 14 * 5)
    assert not np.any(batch.special_defense_observations()) and not np.any(
        batch.selected_defenses()
    )


def test_fog_target_sampling_does_not_advance_the_bounce_stream():
    first, second = game(size=64), game(size=64)
    for batch, fog in ((first, False), (second, True)):
        for env in range(64):
            load(batch, env=env, mask=1 if fog else 0)
            seed(batch, [218, 234], env=env)
            for owner in (1, 2):
                seed(batch, [234], env=env, owner=owner)
        batch.start_environments(ids(range(64)))
        for choice in (1, 0, 20, 1, 0):
            step(batch, [choice] * 64)
    np.testing.assert_array_equal(first.episode_snapshot()[:, 2], second.episode_snapshot()[:, 2])


def test_wall_can_be_reused_on_later_turn_with_new_cost_and_retention():
    batch = game()
    seed(batch, [35, 35])
    seed(batch, [233, 194], owner=1)
    load(batch, owner=1, mp=12)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 0, 0, 0, 1, 0, 20, 2, 0):
        step(batch, [choice])
    assert batch.block_count == batch.miracle_use_count == 2
    assert batch.mp_spent == 12 and batch.diagnostic_players()[0, 1, 1] == 0
    assert batch.hp_damage == 0 and hand(batch, 1).tolist() == [[102, 194, 0, 0], [101, 233, 0, 1]]


def test_exclusive_selection_undo_flash_and_64_toggle_confirm_bound():
    batch = game()
    load(batch, owner=1, mask=4)
    begin(batch, defense=[190, 148, 233])
    for index in range(64):
        step(batch, [1])
        assert bool(batch.choice_masks()[0, 2]) == (index % 2 == 1 and index < 63)
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]
    step(batch, [0])
    assert batch.reflection_count == 0 and batch.hp_damage == 10


def test_numeric_selection_blocks_special_until_undo_and_allows_numeric_combination():
    batch = game()
    begin(batch, defense=[148, 130, 190])
    step(batch, [1])
    assert batch.choice_masks()[0, 2] and not batch.choice_masks()[0, 3]
    step(batch, [1])
    assert batch.choice_masks()[0, 3]
    step(batch, [3])
    assert not batch.choice_masks()[0, 1] and not batch.choice_masks()[0, 2]
    step(batch, [3])
    assert batch.choice_masks()[0, 1] and batch.choice_masks()[0, 2]


def test_chain_limit_truncates_without_fake_damage_turn_tick_or_replacement_gifts():
    batch = game(size=32, max_decisions=7, refill=True)
    begin(batch, model=218, defense=[234], size=32)
    for _ in range(2):
        active = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
        actors = batch.episode_snapshot()[active, 2]
        # A bounce may hit any seat: only seat 1 owns Turbulence. Other seats forgive.
        choices = [1 if actor == 1 else 0 for actor in actors]
        step(batch, choices, active)
        active = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
        if active:
            step(batch, [0] * len(active), active)
    ended = batch.episode_snapshot()[:, 3] == 13
    assert np.any(ended)
    assert np.all(batch.episode_snapshot()[ended, 4] == 0)
    assert np.all(batch.diagnostic_players()[ended, :, 5] == 0)
    assert not np.any(batch.special_defense_observations()[ended])
    assert np.all(batch.acquisition_snapshot()[ended, :, 0] == 0)
    assert batch.suppressed_gift_count >= 3 * int(np.count_nonzero(ended))


@pytest.mark.parametrize("failure", ["unimplemented", "hidden-cost", "exclusive"])
def test_hidden_actual_defense_errors_are_atomic_and_do_not_leak_public_views(failure):
    options = {"element": 0, "origin": 1} if failure == "exclusive" else {}
    if failure == "hidden-cost":
        # Same-category cost fixture: actual Wall has Turbulence's applicability
        # but a higher cost. This is a native validation test, not an official rule.
        options = {"specials": [(233, 3, 1, 0, 6) if row[0] == 233 else row for row in SPECIALS]}
    first, second = game(**options), game(**options)
    for batch in (first, second):
        seed(batch, [35 if failure == "unimplemented" else 211])
        load(batch, owner=1, mp=5)
        seed(
            batch,
            [{"unimplemented": 190, "hidden-cost": 234, "exclusive": 130}[failure], 148],
            owner=1,
        )
    true_model, displayed = {
        "unimplemented": (189, 190),
        "hidden-cost": (233, 234),
        "exclusive": (165, 130),
    }[failure]
    second.seed_hand(0, 1, ids([(101, true_model, displayed, 0), (102, 148, 0, 0)]))
    for batch in (first, second):
        batch.start_environments(ids([0]))
        for choice in (1, 0, 20, 1):
            step(batch, [choice])
        if failure == "exclusive":
            step(batch, [2])
    for view in (
        "actor_hands",
        "choice_masks",
        "pending_observations",
        "special_defense_observations",
    ):
        np.testing.assert_array_equal(getattr(first, view)(), getattr(second, view)())
    before = snapshot(second)
    with pytest.raises(ValueError):
        step(second, [0])
    same(second, before)


def test_late_multibatch_invalid_redirect_rolls_back_native_rng_and_inventory():
    batch, reference = game(size=2, refill=True), game(size=2, refill=True)
    for current in (batch, reference):
        begin(current, model=218, defense=[234], size=2)
        step(current, [1, 1])
    before = snapshot(batch)
    episodes = batch.episode_snapshot()
    with pytest.raises(ValueError):
        batch.step(ids([[0, *episodes[0, :4], 0], [1, *episodes[1, :4], 18]]))
    same(batch, before)
    step(batch, [0, 0])
    step(reference, [0, 0])
    same(batch, snapshot(reference))


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(190, 2, -1, 0)],
        [(190, 2, -1, 0, 0)] * 2,
        [(190, 0, -1, 0, 0)],
        [(190, 4, -1, 0, 0)],
        [(190, 2, -2, 0, 0)],
        [(190, 2, 2, 0, 0)],
        [(190, 2, -1, 2, 0)],
        [(190, 2, -1, 1, 0)],
        [(190, 1, -1, 0, 0)],
        [(190, 2, -1, 0, 1)],
        [(191, 1, 0, 0, 0)],
        [(234, 3, 1, 0, 0)],
        [(234, 3, 1, 1, 5)],
        [(234, 3, 1, 0, 101)],
        [(41, 2, 0, 1, 0)],
        [(189, 2, 1, 0, 0)],
    ],
)
def test_malformed_native_special_profiles_fail_closed(profiles):
    with pytest.raises((ValueError, TypeError)):
        game(specials=profiles)


def test_factory_metadata_and_retained_public_snapshot_do_not_claim_full_readiness():
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    batch = configured.batch
    begin(batch, defense=[190])
    step(batch, [1])
    before = batch.special_defense_observations()
    assert before.tolist() == [[1, 0, 0, 2, 0]] and not before.flags.writeable
    step(batch, [0])
    batch.reset_environments(ids([0]))
    assert not np.any(batch.special_defense_observations())
    assert before.tolist() == [[1, 0, 0, 2, 0]] and batch.reflection_count == 1
    assert configured.metadata.kernel_schema_version == 6
    assert PLAN.integrated_artifact_effect_count == 175
    assert (
        not configured.metadata.full_game_training_ready
        and not configured.metadata.promotion_eligible
    )
    for change in (
        {"redirect_limit": "one-hop"},
        {"bounce": "caller-target"},
        {"special_defense_observation_fields": ("true_identity",)},
        {"full_game_training_ready": True},
    ):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate({**configured.metadata.model_dump(), **change})
    for change in (
        {"special_profiles": ()},
        {"special_fields": ("hidden_id",)},
        {"special_kinds": ("arbitrary",)},
        {"special_defense_count": 237},
    ):
        with pytest.raises(ValidationError):
            FullGameCombatPlan.model_validate({**PLAN.combat.model_dump(), **change})
