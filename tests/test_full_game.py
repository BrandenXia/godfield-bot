"""Joined native state, command leases, resource/inventory atomicity and bounds."""

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    FULL_GAME_EFFECT_SHA256,
    FULL_GAME_PHASES,
    FULL_GAME_RULESET_ID,
    FullGameMetadata,
    FullGamePlan,
    FullGameSmokeReport,
    build_full_game_plan,
    create_development_full_game_batch,
    execute_full_game_commands,
    full_game_decision_contexts,
    pack_full_game_commands,
    run_full_game_development_smoke,
)
from godfield_bot.full_game_protocol import FullGameCommand, FullGameCommandError
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def rows(values):
    return ids(values).reshape(-1, 4)


def game(
    *,
    size=2,
    players=3,
    capacity=8,
    seed=67,
    max_turns=1000,
    max_decisions=4000,
    hp=40,
    mp=10,
    cp=0,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity,
        seed,
        max_turns,
        max_decisions,
        hp,
        mp,
        cp,
    )


def load(batch, *, env=0, owner=0, hp=40, mp=10, cp=0, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), rows([[hp, mp, cp, illness]]), ids([mask]))


def hand(batch, *, env=0, owner=0):
    raw = batch.diagnostic_inventory()[env, owner]
    return raw[raw[:, 0] != 0]


def command_rows(batch, choices, environments=None):
    episodes = batch.episode_snapshot()
    environments = list(range(len(choices))) if environments is None else environments
    return ids(
        [
            [env, *episodes[env, :4], choice]
            for env, choice in zip(environments, choices, strict=True)
        ]
    ).reshape(-1, 6)


def state(batch):
    return (
        batch.episode_snapshot(),
        batch.diagnostic_players(),
        batch.diagnostic_inventory(),
        batch.actor_hands(),
        batch.player_observations(),
        batch.choice_masks(),
        (
            batch.action_count,
            batch.pass_count,
            batch.utility_count,
            batch.mp_spent,
            batch.consumed_count,
            batch.miracle_use_count,
            batch.restored_count,
        ),
    )


def unchanged(batch, before):
    after = state(batch)
    for current, previous in zip(after[:-1], before[:-1], strict=True):
        np.testing.assert_array_equal(current, previous)
    assert after[-1] == before[-1]


def initial_illness_ticket(env, seed=67, epoch=1):
    """Independent arithmetic reference, not a policy feature or native override."""
    mask = 2**64 - 1
    first, second, third = 0x9E3779B97F4A7C15, 0xBF58476D1CE4E5B9, 0x94D049BB133111EB
    state = seed ^ (((env + 1) * first) & mask) ^ ((epoch * second) & mask)
    for _ in range(16):
        state = (state + first) & mask
        word = ((state ^ (state >> 30)) * second) & mask
        word = ((word ^ (word >> 27)) * third) & mask
        word ^= word >> 31
        if word >= (2**64 % 100):
            return word % 100
    raise AssertionError("reference rejection bound exhausted")


@pytest.mark.parametrize("players", [2, 3, 9])
def test_setup_start_actor_relative_projection_and_dead_seat_skipping(players):
    batch = game(players=players)
    assert np.count_nonzero(batch.choice_masks()) == 0
    load(batch, owner=0, hp=0)
    if players == 2:
        batch.start_environments(ids([0]))
        assert batch.episode_snapshot()[0, 3] == 12
        assert batch.episode_snapshot()[0, 5:7].tolist() == [1, 1]
        return
    batch.start_environments(ids([0, 1]))
    assert batch.episode_snapshot()[0, 2] == 1
    assert batch.player_observations()[0, :players, 0].tolist() == [*range(1, players), 0]
    assert np.all(batch.player_observations()[:, players:, 0] == -1)
    assert np.count_nonzero(batch.player_observations()[:, players:, 1:]) == 0
    old = command_rows(batch, [0], [0])
    batch.step(old)
    assert batch.episode_snapshot()[0, 2] == 2
    assert batch.episode_snapshot()[0, 1] == 2
    assert batch.diagnostic_players()[0, 1, 5] == 1
    assert batch.diagnostic_players()[0, 0, 5] == 0
    before = state(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.step(old)
    unchanged(batch, before)


@pytest.mark.parametrize("model,kind,value,cost", PLAN.effect_profiles)
def test_all_12_effects_join_resources_curses_inventory_and_turns(model, kind, value, cost):
    batch = game()
    load(batch, hp=30, mp=30, cp=17, illness=3, mask=15)
    batch.seed_hand(0, 0, rows([[1, model, 0, 0], [2, 191, 0, 0]]))
    batch.start_environments(ids([0, 1]))
    assert batch.choice_masks()[0, 1]
    batch.step(command_rows(batch, [1], [0]))
    player = batch.diagnostic_players()[0, 0]
    hp = min(100, 30 + value) if kind == 1 else 30
    if kind != 4:
        hp -= 5  # Hell periodic effect follows utility/mild cure.
    mp = min(100, 30 - cost + value) if kind == 2 else 30 - cost
    assert player[0] == hp and player[1] == mp and player[2] == 17
    assert player[4] == (0 if kind == 4 else (10 if kind == 3 else 15))
    assert player[5] == 1
    assert batch.episode_snapshot()[0].tolist() == [1, 2, 1, 1, 1, 0, -1, 1, 1]
    reusable = dict(PLAN.inventory.profiles)[model] == 4
    expected = [[2, 191, 0, 0]] + ([[1, model, 0, 1]] if reusable else [])
    np.testing.assert_array_equal(hand(batch), rows(expected))
    assert batch.utility_count == 1 and batch.mp_spent == cost
    assert batch.miracle_use_count == int(reusable)
    assert batch.consumed_count == int(not reusable)
    assert batch.diagnostic_players()[1, 0, 5] == 0


@pytest.mark.parametrize("scope,model,cost", [(1, 199, 0), (2, 200, 0), (1, 237, 2), (2, 238, 5)])
def test_all_documented_cure_states_and_masks_in_one_engine(scope, model, cost):
    cases = [(stage, mask) for stage in range(5) for mask in range(16)]
    batch = game(size=len(cases))
    envs = ids(range(len(cases)))
    batch.seed_players(
        envs,
        ids([0] * len(cases)),
        rows([[40, 30, 5, stage] for stage, _ in cases]),
        ids([mask for _, mask in cases]),
    )
    for env in range(len(cases)):
        batch.seed_hand(env, 0, rows([[1, model, 0, 0], [2, 191, 194, 0]]))
    batch.start_environments(envs)
    for env, (stage, mask) in enumerate(cases):
        cured_stage = 0 if scope == 2 or stage <= 2 else stage
        cured_mask = 0 if scope == 2 else mask & ~5
        affected = (cured_stage, cured_mask) != (stage, mask)
        assert bool(batch.choice_masks()[env, 1]) == affected
        if not affected:
            before = state(batch)
            with pytest.raises(ValueError, match="unavailable"):
                batch.step(command_rows(batch, [1], [env]))
            unchanged(batch, before)
            continue
        batch.step(command_rows(batch, [1], [env]))
        after = batch.diagnostic_players()[env, 0]
        expected_hp = 45 if cured_stage == 4 else 40 - (0, 1, 2, 5)[cured_stage]
        expected_stage = cured_stage
        if cured_stage and initial_illness_ticket(env) < 5:
            if cured_stage == 4:
                expected_hp = 0
            else:
                expected_stage += 1
        assert after[0] == expected_hp and after[1] == 30 - cost
        assert after[3] == expected_stage
        assert after[4] == cured_mask and after[5] == 1
        actual_hand = hand(batch, env=env)
        expected_fake = 0 if scope == 2 and mask & 2 else 194
        assert actual_hand[0, 2] == expected_fake
    assert batch.restored_count == sum(bool(mask & 2) and scope == 2 for _, mask in cases)


def test_song_reuse_pays_each_time_and_cures_display_before_next_owner_tick():
    batch = game(mp=15)
    load(batch, illness=1, mask=2, mp=15)
    batch.seed_hand(0, 0, rows([[1, 238, 237, 0], [2, 191, 194, 0]]))
    # Display Tone can cure Cold; true Song also clears Dream and its fake IDs.
    batch.start_environments(ids([0]))
    original = command_rows(batch, [1], [0])
    batch.step(original)
    np.testing.assert_array_equal(hand(batch), rows([[2, 191, 0, 0], [1, 238, 0, 1]]))
    assert batch.diagnostic_players()[0, 0].tolist() == [40, 10, 0, 0, 0, 1]
    before = state(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.step(original)
    unchanged(batch, before)


def test_reusable_spring_cast_moves_to_tail_and_reuses_same_instance():
    batch = game(players=2, mp=21)
    load(batch, hp=40, mp=21, illness=3)
    batch.seed_hand(0, 0, rows([[1, 235, 0, 0], [2, 191, 0, 0]]))
    batch.start_environments(ids([0]))
    batch.step(command_rows(batch, [1], [0]))
    batch.step(command_rows(batch, [0], [0]))  # Opponent turn.
    batch.step(command_rows(batch, [2], [0]))
    assert batch.diagnostic_players()[0, 0, 1] == 7
    assert batch.miracle_use_count == 2 and batch.mp_spent == 14
    assert hand(batch)[-1].tolist() == [1, 235, 0, 1]
    assert batch.action_count == 3 and batch.pass_count == 1


def test_cap_and_displayed_affordability_are_checked_without_true_identity_leak():
    first, second = game(mp=3), game(mp=3)
    for batch, actual in ((first, 237), (second, 238)):
        load(batch, mp=3, illness=2)
        batch.seed_hand(0, 0, rows([[1, actual, 237, 0]]))
        batch.start_environments(ids([0]))
    np.testing.assert_array_equal(first.actor_hands(), second.actor_hands())
    np.testing.assert_array_equal(first.player_observations(), second.player_observations())
    np.testing.assert_array_equal(first.choice_masks(), second.choice_masks())
    before = state(second)
    with pytest.raises(ValueError, match="actual miracle cost"):
        second.step(command_rows(second, [1], [0]))
    unchanged(second, before)
    first.step(command_rows(first, [1], [0]))
    assert first.diagnostic_players()[0, 0, 1] == 1


def test_unimplemented_true_effect_is_explicit_atomic_error_not_silent_success():
    batch = game()
    load(batch, illness=1)
    batch.seed_hand(0, 0, rows([[1, 215, 237, 0]]))  # Flame displayed as Tone.
    batch.start_environments(ids([0]))
    assert batch.choice_masks()[0, 1]
    before = state(batch)
    with pytest.raises(ValueError, match="not implemented"):
        batch.step(command_rows(batch, [1], [0]))
    unchanged(batch, before)


@pytest.mark.parametrize(
    "failure",
    ["epoch", "decision", "actor", "phase", "choice", "unavailable", "unsupported", "cost"],
)
def test_late_failed_row_does_not_partly_pay_cure_use_or_advance_any_environment(failure):
    batch = game(size=2)
    for env in range(2):
        load(
            batch,
            env=env,
            hp=35,
            mp=3 if failure == "cost" and env == 1 else 10,
            illness=2,
            mask=15,
        )
        model, fake = (
            (215, 237)
            if failure == "unsupported" and env == 1
            else ((238, 237) if failure == "cost" and env == 1 else (237, 0))
        )
        batch.seed_hand(env, 0, rows([[1, model, fake, 0]]))
    batch.start_environments(ids([0, 1]))
    commands = command_rows(batch, [1, 1])
    if failure in ("epoch", "decision", "actor", "phase", "choice"):
        columns = {"epoch": 1, "decision": 2, "actor": 3, "phase": 4, "choice": 5}
        commands[1, columns[failure]] += 1
    if failure == "unavailable":
        commands[1, 5] = -1
    before = state(batch)
    with pytest.raises(ValueError):
        batch.step(commands)
    unchanged(batch, before)


def test_duplicate_command_environments_rejected_before_commit():
    batch = game()
    load(batch, illness=1)
    batch.start_environments(ids([0]))
    row = command_rows(batch, [0], [0])
    before = state(batch)
    with pytest.raises(ValueError, match="duplicate"):
        batch.step(np.concatenate([row, row]))
    unchanged(batch, before)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_bounded_pass_only_loops_truncate_explicitly_and_never_draw(players):
    batch = game(size=16, players=players, max_turns=31)
    batch.start_environments(ids(range(16)))
    for _ in range(31):
        batch.step(command_rows(batch, [0] * 16))
    episode = batch.episode_snapshot()
    assert np.all(episode[:, 3] == 13) and np.all(episode[:, 5] == 3)
    assert np.all(episode[:, 6] == -1) and np.all(episode[:, 4] == 31)
    assert batch.action_count == 496 and batch.pass_count == 496
    assert np.count_nonzero(batch.choice_masks()) == 0
    before = state(batch)
    with pytest.raises(ValueError, match="noninteractive"):
        batch.step(command_rows(batch, [0], [0]))
    unchanged(batch, before)


@pytest.mark.parametrize("turns,decisions,expected", [(10, 2, 4), (2, 10, 3), (2, 2, 3)])
def test_turn_and_decision_limits_have_distinct_outcomes(turns, decisions, expected):
    batch = game(max_turns=turns, max_decisions=decisions)
    batch.start_environments(ids([0]))
    batch.step(command_rows(batch, [0], [0]))
    batch.step(command_rows(batch, [0], [0]))
    assert batch.episode_snapshot()[0, 3:6].tolist() == [13, 2, expected]


def test_real_terminal_winner_precedes_limit_and_dead_seats_are_not_turn_candidates():
    batch = game(players=2, max_turns=1, max_decisions=1)
    load(batch, hp=1, illness=1)
    batch.start_environments(ids([0]))
    batch.step(command_rows(batch, [0], [0]))
    assert batch.diagnostic_players()[0, 0, 0] == 0
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]
    assert np.count_nonzero(batch.choice_masks()[0]) == 0


@pytest.mark.parametrize("remaining,outcome", [(0, 2), (1, 1)])
def test_setup_all_dead_draw_and_one_survivor_are_explicit(remaining, outcome):
    batch = game(players=3)
    batch.seed_players(
        ids([0, 0, 0]),
        ids([0, 1, 2]),
        rows([[0, 10, 5, 0], [0, 10, 0, 0], [40 if remaining else 0, 10, 0, 0]]),
        ids([0, 0, 0]),
    )
    batch.start_environments(ids([0]))
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 0, outcome, 2 if remaining else -1]


def test_setup_is_sealed_and_reset_epoch_blocks_old_reused_card_ids():
    batch = game()
    load(batch, illness=1)
    batch.seed_hand(0, 0, rows([[1, 237, 0, 0]]))
    batch.start_environments(ids([0]))
    old = command_rows(batch, [1], [0])
    before = state(batch)
    for operation in (
        lambda: load(batch),
        lambda: batch.seed_hand(0, 0, rows([])),
        lambda: batch.deal_cards(ids([0]), ids([0]), ids([2]), ids([191])),
        lambda: batch.start_environments(ids([0])),
    ):
        with pytest.raises(ValueError, match="sealed"):
            operation()
        unchanged(batch, before)
    batch.reset_environments(ids([0]))
    assert batch.episode_snapshot()[0].tolist() == [2, 1, 0, 0, 0, 0, -1, 0, -1]
    assert hand(batch).shape == (0, 4)
    load(batch, illness=1)
    batch.seed_hand(0, 0, rows([[1, 237, 0, 0]]))
    batch.start_environments(ids([0]))
    before = state(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.step(old)
    unchanged(batch, before)
    batch.step(command_rows(batch, [1], [0]))
    assert batch.utility_count == 1


def test_fog_observations_hide_all_other_resources_status_and_inventory():
    first, second = game(), game()
    for batch in (first, second):
        load(batch, mask=1)
        batch.seed_hand(0, 0, rows([[1, 191, 194, 0]]))
    load(first, owner=1, hp=10, mp=0, cp=100, illness=3, mask=15)
    load(second, owner=1, hp=99, mp=100, cp=0, illness=4, mask=0)
    second.seed_hand(0, 1, rows([[2, 238, 0, 1], [3, 120, 0, 0]]))
    for batch in (first, second):
        batch.start_environments(ids([0]))
    np.testing.assert_array_equal(first.player_observations(), second.player_observations())
    np.testing.assert_array_equal(first.actor_hands(), second.actor_hands())
    np.testing.assert_array_equal(first.choice_masks(), second.choice_masks())
    assert first.player_observations()[0, 1:3, :3].tolist() == [[1, 1, 0], [2, 1, 0]]
    assert np.count_nonzero(first.player_observations()[0, 1:, 3:]) == 0


def test_all_237_setup_gifts_and_dream_are_deterministic_without_fake_leak():
    first, second = game(size=1, capacity=237), game(size=1, capacity=237)
    models = [model for model, _ in PLAN.inventory.profiles]
    for batch in (first, second):
        load(batch, mask=2)
        batch.deal_cards(ids([0] * 237), ids([0] * 237), ids(range(1, 238)), ids(models))
        batch.start_environments(ids([0]))
    np.testing.assert_array_equal(first.diagnostic_inventory(), second.diagnostic_inventory())
    inventory = hand(first)
    assert 80 < np.count_nonzero(inventory[:, 2]) < 160
    categories = dict(PLAN.inventory.profiles)
    assert all(
        categories[int(actual)] == categories[int(fake)] for _, actual, fake, _ in inventory if fake
    )
    assert first.actor_hands().shape == (1, 237, 3)
    np.testing.assert_array_equal(
        first.actor_hands()[0, :, 1], np.where(inventory[:, 2], inventory[:, 2], inventory[:, 1])
    )


def test_rejected_gift_and_rejected_step_preserve_hidden_random_streams():
    first, second = game(size=2), game(size=2)
    for batch in (first, second):
        for env in range(2):
            load(batch, env=env, illness=3, mask=2)
    with pytest.raises(ValueError, match="duplicate"):
        first.deal_cards(ids([0, 0]), ids([0, 1]), ids([1, 1]), ids([191, 237]))
    for batch in (first, second):
        batch.deal_cards(ids([0, 1]), ids([0, 0]), ids([1, 1]), ids([191, 237]))
        batch.start_environments(ids([0, 1]))
    bad = command_rows(first, [0, 0])
    bad[1, 2] += 1
    with pytest.raises(ValueError, match="stale"):
        first.step(bad)
    for _ in range(60):
        active = np.flatnonzero(first.episode_snapshot()[:, 3] == 1)
        if not len(active):
            break
        for batch in (first, second):
            batch.step(command_rows(batch, [0] * len(active), active.tolist()))
        unchanged(first, state(second))


def test_setup_gift_overflow_duplicate_seed_start_reset_and_load_batches_are_atomic():
    batch = game(capacity=1)
    load(batch, mask=2)
    batch.seed_hand(1, 0, rows([[1, 191, 0, 0]]))
    before = state(batch)
    with pytest.raises(ValueError, match="capacity"):
        batch.deal_cards(ids([0, 1]), ids([0, 0]), ids([1, 2]), ids([191, 237]))
    unchanged(batch, before)
    with pytest.raises(ValueError):
        batch.seed_players(
            ids([0, 1]), ids([0, 0]), rows([[10, 0, 0, 0], [101, 0, 0, 0]]), ids([0, 0])
        )
    unchanged(batch, before)
    with pytest.raises(ValueError, match="duplicate"):
        batch.start_environments(ids([0, 0]))
    unchanged(batch, before)
    with pytest.raises(ValueError):
        batch.reset_environments(ids([0, 2]))
    unchanged(batch, before)


def test_readonly_copied_views_empty_batches_and_native_input_types():
    batch = game()
    load(batch, illness=1)
    batch.seed_hand(0, 0, rows([[1, 237, 0, 0]]))
    batch.deal_cards(ids([]), ids([]), ids([]), ids([]))
    batch.start_environments(ids([0]))
    before = state(batch)
    batch.step(ids([]).reshape(0, 6))
    batch.reset_environments(ids([]))
    unchanged(batch, before)
    for array in before[:-1]:
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.flat[0] = 9
    with pytest.raises(TypeError):
        batch.step(command_rows(batch, [0], [0]).astype(np.int32))
    with pytest.raises(TypeError):
        batch.step(command_rows(batch, [0], [0]).tolist())
    with pytest.raises(TypeError):
        batch.step(ids([[0] * 12])[:, ::2])
    unchanged(batch, before)
    batch.step(command_rows(batch, [1], [0]))
    batch.reset_environments(ids([0]))
    assert batch.utility_count == 1 and batch.mp_spent == 2
    del batch
    assert before[1][0, 0, 1] == 10
    assert before[2][0, 0, 0, 3] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"size": 0},
        {"players": 1},
        {"players": 10},
        {"capacity": 0},
        {"capacity": 513},
        {"size": 10000, "players": 9, "capacity": 512},
        {"max_turns": 0},
        {"max_decisions": 0},
        {"max_turns": 1_000_000_001},
        {"hp": 0},
        {"hp": 101},
        {"mp": 101},
        {"cp": 101},
    ],
)
def test_native_constructor_bounded(changes):
    with pytest.raises(ValueError):
        game(**changes)


@pytest.mark.parametrize(
    "effects",
    [
        [],
        [[191, 0, 5, 0]],
        [[191, 5, 5, 0]],
        [[191, 1, 0, 0]],
        [[191, 1, 101, 0]],
        [[199, 3, 1, 0]],
        [[191, 1, 5, 1]],
        [[237, 3, 0, -1]],
        [[237, 3, 0, 101]],
        [[120, 1, 10, 0]],
        [[245, 1, 10, 0]],
        [[191, 1, 5, 0], [191, 2, 5, 0]],
    ],
)
def test_native_effect_profile_validation_is_not_artifact_registration(effects):
    with pytest.raises(ValueError):
        native.FullGameBatch(1, 2, ids(PLAN.inventory.profiles), rows(effects), 8)


def test_source_factory_and_protocol_native_parity_recheck_leases_at_commit():
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, capacity=8
    )
    batch = configured.batch
    setup = full_game_decision_contexts(configured)
    assert setup[0].phase == "setup" and not setup[0].legal_choice_ids
    load(batch, illness=1)
    batch.seed_hand(0, 0, rows([[1, 237, 0, 0]]))
    batch.start_environments(ids([0, 1]))
    context = full_game_decision_contexts(configured)[0]
    command = FullGameCommand(**context.model_dump(exclude={"legal_choice_ids"}), choice_id=1)
    assert pack_full_game_commands([command]).tolist() == [[0, 1, 1, 0, 1, 1]]
    execute_full_game_commands(configured, [command])
    before = state(batch)
    with pytest.raises(FullGameCommandError, match="stale"):
        execute_full_game_commands(configured, [command])
    with pytest.raises(ValueError, match="stale"):
        batch.step(pack_full_game_commands([command]))
    unchanged(batch, before)
    assert not configured.metadata.full_game_training_ready
    assert not configured.metadata.local_training_eligible
    assert not configured.metadata.action_observation_checkpoint_compatible


def test_source_plan_metadata_pins_and_serialization():
    assert PLAN.effect_sha256 == FULL_GAME_EFFECT_SHA256
    assert len(PLAN.effect_profiles) == 12
    assert Counter(kind for _, kind, _, _ in PLAN.effect_profiles) == {1: 5, 2: 3, 3: 2, 4: 2}
    assert native.FULL_GAME_KERNEL_SCHEMA_VERSION == 1
    assert native.FULL_GAME_RULESET_ID == FULL_GAME_RULESET_ID
    assert FULL_GAME_PHASES[0] == "setup" and FULL_GAME_PHASES[12] == "terminal"
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, capacity=8
    )
    assert (
        FullGameMetadata.model_validate_json(configured.metadata.model_dump_json())
        == configured.metadata
    )
    assert configured.metadata.joined_transactions_implemented
    assert configured.metadata.native_command_tokens_rechecked
    assert not configured.metadata.complete_mechanics_and_acquisition
    assert not configured.metadata.team_rules_and_rewards_implemented
    assert not configured.metadata.promotion_eligible


@pytest.mark.parametrize(
    "changes",
    [
        {"effect_profiles": ((191, 1, 6, 0),)},
        {"effect_fields": ("cost",)},
        {"implemented_phases": tuple(range(14))},
        {"implemented_effect_count": 237},
        {"local_training_eligible": True},
        {"official_fidelity_verified": True},
    ],
)
def test_plan_cannot_relabel_effects_or_claim_more_than_implemented(changes):
    with pytest.raises(ValidationError):
        FullGamePlan.model_validate({**PLAN.model_dump(), **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"batch_size": True},
        {"max_decisions": 0},
        {"seed": 2**64},
        {"batch_size": 10000, "player_count": 9, "capacity": 512},
        {"phase_names": ("ready",)},
        {"command_fields": ("actual_model_id",)},
        {"player_observation_fields": ("true_inventory",)},
        {"diagnostic_fields": ()},
        {"outcome_names": ("winner", "draw", "draw", "draw", "draw")},
        {"complete_action_observation_contract": True},
        {"full_game_training_ready": True},
        {"local_training_eligible": True},
        {"promotion_eligible": True},
    ],
)
def test_metadata_keeps_incomplete_engine_isolated_and_bounded(changes):
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, capacity=8
    )
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate({**configured.metadata.model_dump(), **changes})


def test_factory_fails_closed_on_native_identity_drift(monkeypatch):
    monkeypatch.setattr(native, "FULL_GAME_RULESET_ID", "different")
    with pytest.raises(ProvisionalRuleUnavailableError, match="contract differs"):
        create_development_full_game_batch(catalog_path=CATALOG, bible_path=BIBLE, batch_size=2)


@pytest.mark.parametrize("model,resource", [(191, 0), (195, 1), (235, 0)])
def test_resource_gains_cap_and_full_resources_hide_irrelevant_utility_choices(model, resource):
    batch = game(size=2)
    load(batch, env=0, hp=99, mp=99)
    load(batch, env=1, hp=100, mp=100)
    for env in range(2):
        batch.seed_hand(env, 0, rows([[1, model, 0, 0]]))
    batch.start_environments(ids([0, 1]))
    assert batch.choice_masks()[0, 1] and not batch.choice_masks()[1, 1]
    batch.step(command_rows(batch, [1], [0]))
    assert batch.diagnostic_players()[0, 0, resource] == 100


@pytest.mark.parametrize(
    "kind", ["hp", "mp", "cp", "illness", "mask", "owner", "length", "duplicate", "row_limit"]
)
def test_setup_player_batches_fail_closed_before_mutating_a_valid_first_row(kind):
    batch = game(size=2, players=3)
    envs, owners = ids([0, 1]), ids([0, 0])
    values, masks = rows([[25, 7, 3, 2], [25, 7, 3, 2]]), ids([2, 2])
    if kind in ("hp", "mp", "cp", "illness"):
        values[1, {"hp": 0, "mp": 1, "cp": 2, "illness": 3}[kind]] = 101
    elif kind == "mask":
        masks[1] = 16
    elif kind == "owner":
        owners[1] = 3
    elif kind == "length":
        masks = ids([2])
    elif kind == "duplicate":
        envs[1] = 0
    else:
        envs, owners, values, masks = (
            ids([0] * 7),
            ids([0] * 7),
            rows([[40, 10, 0, 0]] * 7),
            ids([0] * 7),
        )
    before = state(batch)
    with pytest.raises(ValueError):
        batch.seed_players(envs, owners, values, masks)
    unchanged(batch, before)


def test_start_late_sealed_row_is_atomic_for_the_remaining_setup_environment():
    batch = game()
    batch.start_environments(ids([1]))
    before = state(batch)
    with pytest.raises(ValueError, match="sealed"):
        batch.start_environments(ids([0, 1]))
    unchanged(batch, before)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_every_illness_stage_hp_boundary_and_seeded_progression_in_the_engine(players):
    cases = [(hp, stage) for hp in (1, 2, 5, 6, 96, 100) for stage in range(5)]
    batch = game(size=len(cases), players=players)
    envs = ids(range(len(cases)))
    batch.seed_players(
        envs,
        ids([0] * len(cases)),
        rows([[hp, 10, 3, stage] for hp, stage in cases]),
        ids([15] * len(cases)),
    )
    batch.start_environments(envs)
    batch.step(command_rows(batch, [0] * len(cases)))
    for env, (hp, stage) in enumerate(cases):
        expected_hp = min(100, hp + 5) if stage == 4 else max(0, hp - (0, 1, 2, 5)[stage])
        expected_stage = stage
        if expected_hp and stage and initial_illness_ticket(env) < 5:
            if stage == 4:
                expected_hp = 0
            else:
                expected_stage += 1
        assert batch.diagnostic_players()[env, 0].tolist() == [
            expected_hp,
            10,
            3,
            expected_stage,
            15,
            1,
        ]
        if expected_hp == 0 and players == 2:
            assert batch.episode_snapshot()[env, 3:7].tolist() == [12, 1, 1, 1]
        else:
            assert batch.episode_snapshot()[env, 2:4].tolist() == [1, 1]


def test_gift_sampling_is_independent_of_illness_stream_and_reset_is_reproducible():
    first, second = game(size=1, capacity=64), game(size=1, capacity=64)
    for epoch in (1, 2):
        for batch in (first, second):
            load(batch, illness=4, mask=2)
        first.deal_cards(ids([0] * 32), ids([0] * 32), ids(range(1, 33)), ids([191] * 32))
        assert first.gift_count == epoch * 32
        for batch in (first, second):
            batch.start_environments(ids([0]))
            batch.step(command_rows(batch, [0], [0]))
        np.testing.assert_array_equal(first.diagnostic_players(), second.diagnostic_players())
        assert first.diagnostic_players()[0, 0, 0] == (
            0 if initial_illness_ticket(0, epoch=epoch) < 5 else 45
        )
        for batch in (first, second):
            batch.reset_environments(ids([0]))


@pytest.mark.parametrize("players", [2, 3, 9])
def test_development_smoke_is_deterministic_bounded_and_not_a_strength_gate(players):
    options = dict(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=16,
        player_count=players,
        seed=67,
        max_turns=64,
    )
    first = run_full_game_development_smoke(**options)
    second = run_full_game_development_smoke(**options)
    assert first == second
    assert first.winners + first.all_dead_draws + first.turn_limit_truncations == 16
    assert first.actions == first.passes + first.utilities
    assert first.actions <= 16 * 64 and first.utilities > 0 and first.mp_spent > 0
    assert first.consumed_cards + first.retained_miracle_uses == first.utilities
    assert not first.teacher_or_reward_dataset_eligible
    assert not first.local_training_eligible and not first.full_game_training_ready
    assert not first.promotion_eligible and not first.official_fidelity_verified
    assert FullGameSmokeReport.model_validate_json(first.model_dump_json()) == first


def test_development_smoke_cli_is_offline_and_preserves_existing_arena_readiness(monkeypatch):
    import json

    from typer.testing import CliRunner

    from godfield_bot.cli import app

    # Match other CLI tests: don't leave a closed CliRunner stream in global loggers.
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-development-smoke",
            "--batch-size",
            "4",
            "--players",
            "3",
            "--max-turns",
            "24",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["batch_size"] == 4 and payload["ruleset_id"] == FULL_GAME_RULESET_ID
    assert payload["unfinished"] == 0 and not payload["full_game_training_ready"]


@pytest.mark.parametrize(
    "changes",
    [
        {"batch_size": 0},
        {"batch_size": 4097},
        {"batch_size": True},
        {"max_turns": 0},
        {"max_turns": 4097},
        {"max_turns": True},
    ],
)
def test_development_smoke_is_bounded_before_constructing_an_engine(changes):
    with pytest.raises(ValueError):
        run_full_game_development_smoke(catalog_path=CATALOG, bible_path=BIBLE, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"turn_limit_truncations": 0},
        {"actions": 0},
        {"utilities": 0},
        {"unfinished": 1},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"teacher_or_reward_dataset_eligible": True},
    ],
)
def test_development_smoke_cannot_hide_unfinished_or_relabel_truncations(changes):
    report = run_full_game_development_smoke(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, player_count=3, max_turns=8
    )
    with pytest.raises(ValidationError):
        FullGameSmokeReport.model_validate({**report.model_dump(), **changes})
