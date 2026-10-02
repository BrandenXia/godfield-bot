"""Chance decisions are native, standalone, untargeted and atomic."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
    execute_full_game_commands,
    full_game_decision_contexts,
)
from godfield_bot.full_game_combat_plan import FullGameCombatPlan
from godfield_bot.full_game_protocol import FullGameCommand

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)
CHANCES = PLAN.combat.chance_profiles
ATTACKS = {row[0]: row[1:] for row in PLAN.combat.attack_profiles}


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *,
    size=1,
    players=3,
    seed=67,
    chances=CHANCES,
    boosts=True,
    refill=False,
    max_turns=1000,
    max_decisions=4000,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        seed=seed,
        max_turns=max_turns,
        max_decisions=max_decisions,
        initial_hp=40,
        initial_mp=100,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles) if boosts else None,
        special_profiles=ids(
            [row for row in PLAN.combat.special_profiles if boosts or row[0] not in (34, 56)]
        ),
        chance_profiles=ids(chances).reshape(-1, 2) if chances is not None else None,
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        gift_profiles=ids([(191, 1)]) if refill else None,
        refill_on_use=refill,
        hand_limit=18,
        oldest_overflow=refill,
    )


def seed(batch, models, *, env=0, owner=0):
    batch.seed_hand(
        env,
        owner,
        ids([(owner * 100 + i + 1, model, 0, 0) for i, model in enumerate(models)]).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=40, mp=100, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    envs = list(range(len(choices))) if envs is None else envs
    episodes = batch.episode_snapshot()
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def hand(batch, owner=0, env=0):
    result = batch.diagnostic_inventory()[env, owner]
    return result[result[:, 0] != 0]


def snapshot(batch):
    return (
        [
            getattr(batch, view)()
            for view in (
                "episode_snapshot",
                "actor_hands",
                "player_observations",
                "diagnostic_players",
                "diagnostic_inventory",
                "choice_masks",
                "pending_observations",
                "selected_attacks",
                "attack_order",
                "attack_selection_observations",
                "selected_defenses",
                "special_defense_observations",
                "acquisition_snapshot",
                "chance_observations",
                "chance_snapshot",
                "attack_effect_observations",
                "attack_effect_snapshot",
            )
        ],
        [
            getattr(batch, key)
            for key in (
                "action_count",
                "attack_count",
                "resolved_attack_count",
                "attack_confirm_count",
                "attack_component_count",
                "chance_count",
                "chance_hit_count",
                "chance_miss_count",
                "hp_damage",
                "mp_spent",
                "consumed_count",
                "miracle_use_count",
                "automatic_gift_count",
                "suppressed_gift_count",
                "reflection_count",
                "bounce_count",
                "block_count",
                "absorption_count",
                "absorbed_hp",
                "inflicted_curse_count",
                "inflicted_illness_count",
                "illness_effect_damage",
                "dark_cloud_hit_count",
            )
        ],
    )


def same(batch, before):
    after = snapshot(batch)
    for old, new in zip(before[0], after[0], strict=True):
        np.testing.assert_array_equal(old, new)
    assert after[1] == before[1]


def rank(env, stream, bound, *, seed=67, epoch=1):
    # Independent model of native bounded SplitMix, not caller tickets.
    mask = (1 << 64) - 1
    state = (
        seed
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ stream
    )
    threshold = (1 << 64) % bound
    for _ in range(16):
        state = (state + 0x9E3779B97F4A7C15) & mask
        word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
        word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
        word ^= word >> 31
        if word >= threshold:
            return word % bound
    raise AssertionError("reference rejection bound exhausted")


@pytest.mark.parametrize("model,rate", CHANCES)
def test_all_24_chance_cards_pay_use_once_and_resolve_exact_native_roll(model, rate):
    batch = game(size=128, refill=True)
    attack, element, origin, cost = ATTACKS[model]
    for env in range(128):
        seed(batch, [model, 194, 9], env=env)
        load(batch, env=env, illness=1)
    batch.start_environments(ids(range(128)))
    step(batch, [1] * 128)
    assert np.all(batch.chance_observations() == ids([1, rate, 0, 1]))
    assert batch.chance_count == 0 and batch.attack_count == 0
    assert np.all(~batch.choice_masks()[:, 3])  # No additive weapon on chance base.
    assert np.all(~batch.choice_masks()[:, 19:])  # No player target.
    step(batch, [0] * 128)
    hits = np.asarray([rank(env, 0xE19B01AA9D42C633, 100) < rate for env in range(128)])
    assert np.any(hits) and np.any(~hits)
    np.testing.assert_array_equal(
        batch.chance_snapshot(), np.column_stack((np.ones(128), hits, ~hits))
    )
    assert batch.chance_count == 128 and batch.chance_hit_count == int(hits.sum())
    assert batch.chance_miss_count == int((~hits).sum()) and batch.mp_spent == 128 * cost
    assert batch.attack_count == 128 and batch.resolved_attack_count == int((~hits).sum())
    assert batch.miracle_use_count == (128 if origin else 0)
    assert batch.consumed_count == (0 if origin else 128)
    np.testing.assert_array_equal(batch.episode_snapshot()[:, 3], np.where(hits, 4, 1))
    np.testing.assert_array_equal(batch.diagnostic_players()[:, 0, 5], (~hits).astype(int))
    assert batch.automatic_gift_count == int((~hits).sum())
    for env in range(128):
        remaining = hand(batch, env=env)
        expected = [194, 9] + ([model] if origin else []) + ([] if hits[env] else [191])
        assert remaining[:, 1].tolist() == expected
        if origin:
            assert remaining[2, 3] == 1
        if hits[env]:
            target = 1 + rank(env, 0xC6BC279692B5C323, 2)
            assert batch.episode_snapshot()[env, 2] == target
            assert batch.pending_observations()[env, :6].tolist() == [
                1,
                0,
                target,
                attack,
                element,
                origin,
            ]
            assert batch.chance_observations()[env].tolist() == [1, rate, 1, 1]
        else:
            assert batch.diagnostic_players()[env, 0, 0] == 39
            assert not np.any(batch.chance_observations()[env])
    envs = np.flatnonzero(hits).tolist()
    step(batch, [0] * len(envs), envs)
    assert batch.chance_count == batch.resolved_attack_count == 128
    assert batch.automatic_gift_count == 128 and batch.hp_damage == int(hits.sum()) * (
        40 if element == 6 else attack
    )
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_automatic_chance_targets_exclude_source_and_dead_players(players):
    batch = game(size=256, players=players)
    living = list(range(players if players == 2 else players - 1))
    for env in range(256):
        seed(batch, [95], env=env)
        if players > 2:
            load(batch, env=env, owner=players - 1, hp=0)
    batch.start_environments(ids(range(256)))
    step(batch, [1] * 256)
    step(batch, [0] * 256)
    hits = batch.episode_snapshot()[:, 3] == 4
    assert set(batch.episode_snapshot()[hits, 2]) == set(living[1:])
    assert not np.any(batch.diagnostic_players()[:, :, 5][hits])


@pytest.mark.parametrize("boosts", [False, True])
def test_chance_confirmation_and_cancel_work_without_optional_addition_map(boosts):
    batch = game(boosts=boosts)
    seed(batch, [95, 9, 210])
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.attack_order()[0, 0] == 1 and batch.attack_selection_observations()[0, 0] == 1
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0, 1]
    step(batch, [1])
    assert batch.episode_snapshot()[0, 3:5].tolist() == [1, 0]
    assert batch.chance_count == batch.attack_component_count == 0
    assert not np.any(batch.attack_order())
    step(batch, [1])
    step(batch, [0])
    assert batch.chance_count == batch.attack_component_count == 1


def test_jinn_defense_is_fixed_wood_def6_and_never_rolls():
    batch = game()
    seed(batch, [35])
    seed(batch, [108, 130], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20, 1, 2):
        step(batch, [choice])
    assert batch.pending_observations()[0, 6] == 10
    step(batch, [0])
    assert batch.hp_damage == 0 and batch.consumed_count == 3 and batch.chance_count == 0


def test_confirmed_chance_hit_never_rerolls_across_two_reflections():
    batch = game(size=128)
    for env in range(128):
        seed(batch, [95, 190], env=env)
        seed(batch, [190], owner=1, env=env)
        seed(batch, [190], owner=2, env=env)
    batch.start_environments(ids(range(128)))
    step(batch, [1] * 128)
    step(batch, [0] * 128)
    hit_envs = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
    counts = batch.chance_snapshot()
    for choice in (1, 0, 1, 0):
        step(batch, [choice] * len(hit_envs), hit_envs)
        np.testing.assert_array_equal(batch.chance_snapshot(), counts)
    assert np.all(batch.special_defense_observations()[hit_envs, 2] == 2)
    assert np.all(batch.chance_observations()[hit_envs] == ids([1, 75, 1, 1]))
    step(batch, [0] * len(hit_envs), hit_envs)
    assert batch.hp_damage == len(hit_envs) and batch.resolved_attack_count == 128
    assert batch.reflection_count == 2 * len(hit_envs) and batch.chance_count == 128


@pytest.mark.parametrize(
    "response,model", [(190, 95), (165, 227), (151, 225), (174, 229), (234, 226)]
)
def test_chance_success_enters_existing_block_reflect_and_bounce_responses_once(response, model):
    batch = game(size=128)
    for env in range(128):
        seed(batch, [model], env=env)
        for owner in (1, 2):
            seed(batch, [response], env=env, owner=owner)
    batch.start_environments(ids(range(128)))
    step(batch, [1] * 128)
    step(batch, [0] * 128)
    envs = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
    before = batch.chance_snapshot()
    for choice in (1, 0):
        step(batch, [choice] * len(envs), envs)
    np.testing.assert_array_equal(batch.chance_snapshot(), before)
    assert batch.block_count + batch.reflection_count + batch.bounce_count == len(envs)
    remaining = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
    step(batch, [0] * len(remaining), remaining)
    assert batch.resolved_attack_count == batch.chance_count == 128
    assert batch.mp_spent == 128 * ATTACKS[model][3] + (5 * len(envs) if response == 234 else 0)


def test_chance_darkness_fully_blocked_by_numeric_armor_does_not_finish_target():
    batch = game(size=128)
    for env in range(128):
        seed(batch, [96], env=env)
        for owner in (1, 2):
            seed(batch, [130], env=env, owner=owner)
    batch.start_environments(ids(range(128)))
    step(batch, [1] * 128)
    step(batch, [0] * 128)
    envs = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4).tolist()
    for choice in (1, 0):
        step(batch, [choice] * len(envs), envs)
    assert batch.hp_damage == batch.darkness_finish_count == 0
    assert batch.consumed_count == 128 + len(envs) and batch.chance_count == 128
    assert np.all(batch.diagnostic_players()[:, :, 0] == 40)


def test_chance_streams_ignore_fog_and_prior_gift_disguise_illness_draws():
    first, second = game(size=128), game(size=128, refill=True)
    for batch, noisy in ((first, False), (second, True)):
        for env in range(128):
            load(batch, env=env, hp=35, illness=1 if noisy else 0, mask=3 if noisy else 0)
            seed(batch, [191, 95], env=env)
        batch.start_environments(ids(range(128)))
        for choice in (1, 0, 0, 1, 0):
            step(batch, [choice] * 128)
    np.testing.assert_array_equal(first.chance_snapshot(), second.chance_snapshot())
    hit = first.episode_snapshot()[:, 3] == 4
    np.testing.assert_array_equal(
        first.episode_snapshot()[hit, 2], second.episode_snapshot()[hit, 2]
    )


def test_chance_reuse_pays_each_attempt_moves_tail_and_advances_only_its_roll_stream():
    # Duel removes target ambiguity; both attempts pay and remain reusable.
    batch = game(players=2)
    seed(batch, [225, 194])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [0])
    if batch.episode_snapshot()[0, 3] == 4:
        step(batch, [0])
    step(batch, [0])  # Opponent's ordinary turn.
    assert hand(batch).tolist() == [[2, 194, 0, 0], [1, 225, 0, 1]]
    step(batch, [2])
    step(batch, [0])
    assert batch.mp_spent == 8 and batch.miracle_use_count == batch.chance_count == 2
    assert hand(batch).tolist() == [[2, 194, 0, 0], [1, 225, 0, 1]]
    assert batch.chance_snapshot()[0, 0] == 2


def test_miss_terminal_illness_precedes_decision_limit_and_suppresses_gifts():
    seed_value = next(
        seed for seed in range(100) if rank(0, 0xE19B01AA9D42C633, 100, seed=seed) >= 25
    )
    batch = game(players=2, seed=seed_value, max_decisions=2, refill=True)
    load(batch, hp=1, illness=1)
    seed(batch, [227])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]
    assert batch.chance_miss_count == 1 and batch.hp_damage == 0
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 1


@pytest.mark.parametrize("limit", [1, 2])
def test_decision_limit_before_or_on_chance_confirmation_has_honest_receipts(limit):
    batch = game(size=128, max_decisions=limit, refill=True)
    for env in range(128):
        seed(batch, [95], env=env)
    batch.start_environments(ids(range(128)))
    step(batch, [1] * 128)
    if limit == 2:
        step(batch, [0] * 128)
    assert np.all(batch.episode_snapshot()[:, 3] == 13)
    assert not np.any(batch.chance_observations())
    assert batch.chance_count == (128 if limit == 2 else 0)
    assert batch.suppressed_gift_count == batch.chance_count and batch.automatic_gift_count == 0
    assert int(batch.episode_snapshot()[:, 4].sum()) == batch.chance_miss_count


@pytest.mark.parametrize(
    "true,display,error",
    [
        (112, 95, "not implemented"),
        (35, 95, "targeting mode"),
        (95, 35, "targeting mode"),
        (230, 225, "unaffordable"),
    ],
)
def test_hidden_target_role_effect_and_cost_fail_without_mask_leak_or_partial_roll(
    true, display, error
):
    first, second = game(), game()
    for batch in (first, second):
        seed(batch, [display])
        load(batch, mp=4)
    second.seed_hand(0, 0, ids([[1, true, display, 0]]))
    for batch in (first, second):
        batch.start_environments(ids([0]))
        step(batch, [1])
        if display == 35:
            step(batch, [0])
    for view in ("choice_masks", "chance_observations", "actor_hands", "pending_observations"):
        np.testing.assert_array_equal(getattr(first, view)(), getattr(second, view)())
    before = snapshot(second)
    with pytest.raises(ValueError, match=error):
        step(second, [20 if display == 35 else 0])
    same(second, before)


def test_failed_late_batch_chance_cast_rolls_back_both_streams_and_payment():
    batch, reference = game(size=64, refill=True), game(size=64, refill=True)
    for current in (batch, reference):
        for env in range(64):
            seed(current, [227], env=env)
        current.start_environments(ids(range(64)))
        step(current, [1] * 64)
    before = snapshot(batch)
    episodes = batch.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0 if env < 63 else 19] for env in range(64)])
    with pytest.raises(ValueError):
        batch.step(commands)
    same(batch, before)
    step(batch, [0] * 64)
    step(reference, [0] * 64)
    same(batch, snapshot(reference))


def test_chance_reset_changes_epoch_streams_and_keeps_lifetime_counts():
    batch = game(size=32)
    for epoch in (1, 2):
        for env in range(32):
            seed(batch, [95], env=env)
        batch.start_environments(ids(range(32)))
        step(batch, [1] * 32)
        step(batch, [0] * 32)
        expected = [rank(env, 0xE19B01AA9D42C633, 100, epoch=epoch) < 75 for env in range(32)]
        np.testing.assert_array_equal(batch.chance_snapshot()[:, 1], expected)
        assert batch.chance_count == 32 * epoch
        if epoch == 1:
            old = batch.chance_snapshot()
            batch.reset_environments(ids(range(32)))
            assert not np.any(batch.chance_snapshot()) and not np.any(batch.chance_observations())
            assert np.all(old[:, 0] == 1) and not old.flags.writeable


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        [(95, 0)],
        [(95, 100)],
        [(95, 101)],
        [(95, -1)],
        [(95, 75)] * 2,
        [(190, 75)],
        [(112, 25)],
        [(191, 75)],
        [(225, 75, 4)],
    ],
)
def test_invalid_native_chance_profiles_fail_closed(profiles):
    with pytest.raises((ValueError, TypeError)):
        game(chances=profiles)


def test_factory_command_adapter_has_no_fabricated_target_and_metadata_stays_gated():
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    batch = configured.batch
    seed(batch, [95, 9])
    batch.start_environments(ids([0]))
    for choice in (1, 0):
        context = full_game_decision_contexts(configured)[0]
        if choice == 0:
            assert context.phase == "attack-selection" and context.legal_choice_ids == (0, 1)
        execute_full_game_commands(
            configured,
            [FullGameCommand(**context.model_dump(exclude={"legal_choice_ids"}), choice_id=choice)],
        )
    assert batch.chance_count == 1 and configured.metadata.kernel_schema_version == 7
    assert PLAN.integrated_artifact_effect_count == 195
    assert (
        not configured.metadata.local_training_eligible
        and not configured.metadata.promotion_eligible
    )
    for change in (
        {"chance_target": "caller-selected"},
        {"chance_observation_fields": ("true_id",)},
        {"chance_snapshot_fields": ("caller-roll",)},
        {"full_game_training_ready": True},
    ):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate({**configured.metadata.model_dump(), **change})
    for change in (
        {"chance_profiles": ()},
        {"chance_fields": ("target_seat",)},
        {"excluded_chance_models": ()},
        {"chance_weapon_count": 18},
    ):
        with pytest.raises(ValidationError):
            FullGameCombatPlan.model_validate({**PLAN.combat.model_dump(), **change})
