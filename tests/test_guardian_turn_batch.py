"""Legal consumable armor and bounded, explicitly provisional guardian turns."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from godfield_bot.cli import app
from godfield_bot.guardian_batch import create_provisional_guardian_turn_batch
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def batch(*, size=3, players=3, hand=4, max_turns=1000):
    return native.GuardianTurnBatch(
        size,
        players,
        4,
        ids([[0, 101, 1], [1, 102, 1], [2, 103, 1], [3, 104, 1], [4, 105, 1]]),
        ids(
            [
                [101, 10, 1, 100, 0, 0, 0],
                [102, 4, 0, 100, 0, 0, 0],
                [103, 2, 5, 100, 0, 0, 0],
                [104, 1, 6, 100, 0, 0, 0],
                [105, 0, 0, 100, 5, 5, 0],
            ]
        ),
        ids([[201, 4, 2], [202, 7, 5], [203, 3, 1], [204, 5, 0]]),
        hand,
        max_turns,
    )


def summon(game, envs, *, group=0, owner=0, slot=0):
    count = len(envs)
    game.summon(
        ids(envs),
        ids([slot] * count),
        ids([slot + 1] * count),
        ids([owner] * count),
        ids([group] * count),
    )


def begin(game, envs, *, target=1, slot=0):
    count = len(envs)
    game.begin_effects(
        ids(envs),
        ids([slot] * count),
        ids([slot + 1] * count),
        ids([target] * count),
        ids([0] * count),
        ids([0] * count),
    )


def deal(game, envs, models, *, player=1, slots=None):
    slots = slots or list(range(len(envs)))
    game.deal_defenses(
        ids(envs),
        ids([player] * len(envs)),
        ids(slots),
        ids([100 + slot for slot in slots]),
        ids(models),
    )


def step(game, envs, actions, *, player=1):
    game.step_defenses(ids(envs), ids([player] * len(envs)), ids(actions))


def test_combo_selection_toggles_mask_and_consumes_only_on_confirmation():
    game = batch()
    summon(game, [0])
    deal(game, [0, 0, 0, 0], [201, 202, 203, 204])
    assert not np.any(game.defense_action_masks())
    begin(game, [0])
    np.testing.assert_array_equal(
        game.defense_action_masks()[0], [True, True, False, False, True, False]
    )
    assert game.turn_snapshot()[0, 2] == 1  # Defender, not turn owner.
    step(game, [0], [0])
    assert game.turn_snapshot()[0, 6] == 4
    assert game.defense_action_masks()[0, 5]
    step(game, [0], [0])  # Deselect.
    assert not game.defense_action_masks()[0, 5]
    step(game, [0], [0])
    step(game, [0], [1])
    before = game.inventory_snapshot()
    assert game.consumed_card_count == 0
    assert game.turn_snapshot()[0, 6] == 11
    step(game, [0], [5])
    after = game.inventory_snapshot()
    assert not np.any(after[0, 1, :2])
    np.testing.assert_array_equal(after[0, 1, 2:, :2], before[0, 1, 2:, :2])
    assert game.resource_snapshot()[0, 1, 0] == 40
    assert game.consumed_card_count == 2
    np.testing.assert_array_equal(game.turn_snapshot()[0], [0, 1, 1, 1, -1, 0, 0, 0, 0, 2, 0])
    assert not np.any(game.defense_action_masks())
    assert np.all(before[0, 1, :2, 0] > 0)


def test_forgiveness_clears_selection_without_spending_armor():
    game = batch()
    summon(game, [0])
    deal(game, [0], [201])
    begin(game, [0])
    step(game, [0], [0])
    step(game, [0], [4])
    assert game.resource_snapshot()[0, 1, 0] == 30
    assert game.inventory_snapshot()[0, 1, 0, 0] == 100
    assert not np.any(game.inventory_snapshot()[..., 2])
    assert game.consumed_card_count == 0


def test_multirow_action_validation_is_atomic_even_with_confirmation():
    game = batch()
    summon(game, [0, 1])
    deal(game, [0, 1], [201, 203], slots=[0, 0])
    begin(game, [0, 1])
    step(game, [0], [0])
    inventory, turn, resources = (
        game.inventory_snapshot(),
        game.turn_snapshot(),
        game.resource_snapshot(),
    )
    with pytest.raises(ValueError, match="not legal"):
        step(game, [0, 1], [5, 0])
    np.testing.assert_array_equal(game.inventory_snapshot(), inventory)
    np.testing.assert_array_equal(game.turn_snapshot(), turn)
    np.testing.assert_array_equal(game.resource_snapshot(), resources)
    assert game.resolved_effect_count == game.consumed_card_count == 0
    with pytest.raises(ValueError, match="duplicate"):
        step(game, [0, 0], [5, 4])
    with pytest.raises(ValueError, match="actor"):
        step(game, [0], [5], player=0)
    with pytest.raises(ValueError, match="selected"):
        step(game, [1], [5])


def test_light_masks_all_cards_and_pending_phase_locks_setup():
    game = batch()
    summon(game, [0], group=2)
    deal(game, [0, 0], [201, 202])
    begin(game, [0])
    assert np.flatnonzero(game.defense_action_masks()[0]).tolist() == [4]
    for call in (
        lambda: game.pass_turns(ids([0]), ids([0])),
        lambda: deal(game, [0], [204], slots=[3]),
        lambda: game.remove(ids([0]), ids([0]), ids([1])),
    ):
        with pytest.raises(ValueError, match="awaits defense"):
            call()
    step(game, [0], [4])
    assert game.resource_snapshot()[0, 1, 0] == 38


def test_darkness_death_skips_eliminated_player_and_ends_with_winner():
    game = batch()
    summon(game, [0], group=3)
    summon(game, [0], group=3, owner=2, slot=1)
    begin(game, [0])
    step(game, [0], [4])
    assert game.turn_snapshot()[0, 1] == 2
    assert game.resource_snapshot()[0, 1, 0] == 0
    with pytest.raises(ValueError, match="eliminated"):
        summon(game, [0], owner=1, slot=2)
    with pytest.raises(ValueError, match="defense card"):
        deal(game, [0], [201])
    begin(game, [0], target=0, slot=1)
    step(game, [0], [4], player=0)
    np.testing.assert_array_equal(game.turn_snapshot()[0, :6], [2, 2, -1, 2, 2, 0])
    assert not np.any(game.defense_action_masks()[0])
    with pytest.raises(ValueError, match="finished"):
        game.pass_turns(ids([0]), ids([2]))
    game.reset_environments(ids([0]))
    assert not np.any(game.inventory_snapshot()[0])
    assert not np.any(game.guardian_snapshot()[0])
    assert np.all(game.resource_snapshot()[0, :, 0] == 40)
    assert game.turn_snapshot()[0, 1] == 0


def test_immediate_owner_utility_rotates_turn_and_rejects_wrong_owner_atomically():
    game = batch()
    summon(game, [0], group=4)
    summon(game, [1], owner=1)
    with pytest.raises(ValueError, match="turn owner"):
        begin(game, [0, 1], target=0)
    assert np.all(game.resource_snapshot()[:, :, 0] == 40)
    assert game.resolved_effect_count == 0
    begin(game, [0], target=0)
    assert game.resource_snapshot()[0, 0, 0] == 45
    assert game.turn_snapshot()[0, 1] == 1
    assert game.resolved_effect_count == 1
    with pytest.raises(ValueError, match="turn owner"):
        begin(game, [0], target=0)


def test_pass_limit_and_selection_limit_both_terminate_without_hanging():
    game = batch(max_turns=2)
    with pytest.raises(ValueError, match="turn owner"):
        game.pass_turns(ids([0, 1]), ids([0, 1]))
    assert not np.any(game.turn_snapshot()[:, 3])
    game.pass_turns(ids([0]), ids([0]))
    game.pass_turns(ids([0]), ids([1]))
    np.testing.assert_array_equal(game.turn_snapshot()[0, :6], [3, 1, -1, 2, -1, 1])
    summon(game, [1])
    deal(game, [1], [201], slots=[0])
    begin(game, [1])
    for _ in range(64):
        step(game, [1], [0])
    state = game.turn_snapshot()[1]
    assert state[0] == 3 and state[2] == -1 and state[7] == 64
    assert not np.any(game.defense_action_masks()[1])
    assert game.consumed_card_count == 0
    with pytest.raises(ValueError, match="phase"):
        step(game, [1], [4])
    game.reset_environments(ids([1]))
    assert game.turn_snapshot()[1, 7] == 0


def test_deal_validates_all_rows_instances_and_slots_without_partial_mutation():
    game = batch()
    for models, slots, instances in (
        ([201, 999], [0, 1], [1, 2]),
        ([201, 201], [0, 0], [1, 2]),
        ([201, 201], [0, 1], [1, 1]),
        ([201, 201], [0, 4], [1, 2]),
    ):
        with pytest.raises(ValueError):
            game.deal_defenses(ids([0, 0]), ids([0, 0]), ids(slots), ids(instances), ids(models))
        assert not np.any(game.inventory_snapshot())
    deal(game, [0], [201])
    with pytest.raises(ValueError, match="already exists"):
        game.deal_defenses(ids([0]), ids([0]), ids([2]), ids([100]), ids([201]))
    assert not np.any(game.inventory_snapshot()[0, 0])


def test_copied_readonly_snapshots_survive_reset_and_bad_reset_is_atomic():
    game = batch()
    summon(game, [0])
    deal(game, [0], [201])
    begin(game, [0])
    step(game, [0], [0])
    snapshots = [
        game.inventory_snapshot(),
        game.turn_snapshot(),
        game.defense_action_masks(),
        game.resource_snapshot(),
        game.guardian_snapshot(),
        game.combat_snapshot(),
    ]
    assert all(not snapshot.flags.writeable for snapshot in snapshots)
    with pytest.raises(ValueError):
        game.reset_environments(ids([0, 3]))
    np.testing.assert_array_equal(game.inventory_snapshot(), snapshots[0])
    game.reset_environments(ids([0]))
    assert snapshots[0][0, 1, 0, 2] == 1
    assert snapshots[1][0, 0] == 1


@pytest.mark.parametrize(
    "kwargs", [{"hand": 0}, {"hand": 19}, {"max_turns": 0}, {"max_turns": 1_000_000_001}]
)
def test_invalid_dimensions_and_unbounded_episodes_are_rejected(kwargs):
    with pytest.raises(ValueError, match="configuration"):
        batch(**kwargs)


@pytest.mark.parametrize(
    "defenses",
    [
        [[201, 0, 0]],
        [[201, 65536, 0]],
        [[201, 2, 7]],
        [[0, 2, 0]],
        [[201, 2, 0], [201, 3, 0]],
        [[201, 2]],
    ],
)
def test_invalid_or_duplicate_defense_profiles_are_rejected(defenses):
    with pytest.raises(ValueError, match=r"configuration|profile"):
        native.GuardianTurnBatch(
            1,
            2,
            1,
            ids([[0, 101, 1]]),
            ids([[101, 4, 0, 100]]),
            ids(defenses),
        )


def test_win_on_last_allowed_turn_has_priority_over_truncation():
    game = batch(players=2, max_turns=1)
    summon(game, [0], group=3)
    begin(game, [0])
    step(game, [0], [4])
    assert game.turn_snapshot()[0, 0] == 2
    assert game.turn_snapshot()[0, 4] == 0
    assert game.turn_snapshot()[0, 5] == 0


def test_mixed_batch_can_confirm_forgive_and_toggle_independently():
    game = batch()
    summon(game, [0, 1, 2])
    deal(game, [0, 1, 2], [201, 201, 201], slots=[0, 0, 0])
    begin(game, [0, 1, 2])
    step(game, [0], [0])
    step(game, [0, 1, 2], [5, 4, 0])
    np.testing.assert_array_equal(game.turn_snapshot()[:, 0], [0, 0, 1])
    np.testing.assert_array_equal(game.resource_snapshot()[:, 1, 0], [34, 30, 40])
    assert game.consumed_card_count == 1
    assert game.inventory_snapshot()[2, 1, 0, 2] == 1


def test_nine_player_turn_rotation_and_supported_hit_tickets():
    game = batch(players=9, hand=18)
    assert game.action_count == 20
    for player in range(9):
        assert game.turn_snapshot()[0, 1] == player
        game.pass_turns(ids([0]), ids([player]))
    assert game.turn_snapshot()[0, 1] == 0
    assert game.turn_snapshot()[0, 3] == 9


def test_every_supported_pinned_effect_advances_exactly_one_turn():
    from godfield_bot.api_catalog import read_api_catalog_snapshot
    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.provisional_rules import build_provisional_guardian_plan

    plan = build_provisional_guardian_plan(
        read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
    )
    created = create_provisional_guardian_turn_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=39,
    )
    game = created.batch
    tickets = {}
    starts = {}
    for group, model, weight in plan.weighted_profiles:
        tickets[model] = (group, starts.get(group, 0))
        starts[group] = starts.get(group, 0) + weight
    models = created.metadata.supported_effect_model_ids
    envs = ids(list(range(39)))
    zeros = ids([0] * 39)
    ones = ids([1] * 39)
    game.summon(envs, zeros, ones, zeros, ids([tickets[model][0] for model in models]))
    # Owner utilities are explicitly targeted at the owner, not an enemy.
    self_effects = {275, 276, 277, 278, 279, 280, 283, 284}
    game.begin_effects(
        envs,
        zeros,
        ones,
        ids([0 if model in self_effects else 1 for model in models]),
        ids([tickets[model][1] for model in models]),
        zeros,
    )
    defensive = np.flatnonzero(game.turn_snapshot()[:, 0] == 1)
    game.step_defenses(ids(defensive), ids([1] * len(defensive)), ids([18] * len(defensive)))
    assert game.resolved_effect_count == 39
    assert np.all(game.turn_snapshot()[:, 3] == 1)
    assert np.all(game.turn_snapshot()[:, 0] != 1)


def test_seeded_parallel_mars_arenas_finish_and_replay_deterministically():
    # Synthetic no-redraw arenas exercise the scheduler, not official fidelity.
    def rollout(seed):
        created = create_provisional_guardian_turn_batch(
            catalog_path=CATALOG,
            bible_path=BIBLE,
            batch_size=32,
            player_count=3,
            slots_per_environment=3,
            hand_slots=18,
            max_turns=30,
        )
        game = created.batch
        rng = np.random.default_rng(seed)
        envs = np.repeat(np.arange(32, dtype=np.int64), 3)
        owners = np.tile(np.arange(3, dtype=np.int64), 32)
        game.summon(envs, owners, owners + 1, owners, np.zeros(96, dtype=np.int64))
        card_envs = np.repeat(np.arange(32, dtype=np.int64), 3 * 18)
        players = np.tile(np.repeat(np.arange(3, dtype=np.int64), 18), 32)
        slots = np.tile(np.arange(18, dtype=np.int64), 32 * 3)
        instances = np.tile(np.arange(1, 3 * 18 + 1, dtype=np.int64), 32)
        models = rng.choice(ids(created.metadata.defense_model_ids), len(card_envs))
        game.deal_defenses(card_envs, players, slots, instances, models)
        for _ in range(30 * 65 + 1):
            turns = game.turn_snapshot()
            if np.all(turns[:, 0] >= 2):
                break
            ready = np.flatnonzero(turns[:, 0] == 0)
            if len(ready):
                owners = turns[ready, 1].copy()
                hp = game.resource_snapshot()[..., 0]
                targets = ids(
                    [
                        next(
                            player for player in range(3) if player != owner and hp[env, player] > 0
                        )
                        for env, owner in zip(ready, owners, strict=True)
                    ]
                )
                game.begin_effects(
                    ids(ready),
                    owners,
                    owners + 1,
                    targets,
                    rng.integers(0, 20, len(ready), dtype=np.int64),
                    rng.integers(0, 100, len(ready), dtype=np.int64),
                )
            turns = game.turn_snapshot()
            defensive = np.flatnonzero(turns[:, 0] == 1)
            masks = game.defense_action_masks()
            actions = ids([rng.choice(np.flatnonzero(masks[env])) for env in defensive])
            game.step_defenses(ids(defensive), turns[defensive, 2].copy(), actions)
        else:
            pytest.fail("bounded arena did not finish")
        assert game.resolved_effect_count > 0
        return game.turn_snapshot(), game.resource_snapshot(), game.inventory_snapshot()

    first, second = rollout(67), rollout(67)
    for expected, actual in zip(first, second, strict=True):
        np.testing.assert_array_equal(expected, actual)


def test_pinned_factory_and_cli_keep_promotion_and_training_blocked(monkeypatch):
    created = create_provisional_guardian_turn_batch(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=16,
    )
    metadata = created.metadata
    assert metadata.ruleset_id == native.GUARDIAN_TURN_RULESET_ID
    assert metadata.kernel_schema_version == metadata.observation_schema_version == 2
    assert len(metadata.defense_model_ids) == 49
    assert len(metadata.armor_model_ids) == 47
    assert metadata.defense_miracle_model_ids == (233, 234)
    assert len(metadata.attack_weapon_model_ids) == 39
    assert len(metadata.attack_miracle_model_ids) == 6
    assert len(metadata.supported_effect_model_ids) == 39
    assert metadata.action_count == 20
    assert not metadata.local_training_eligible
    assert not metadata.full_game_training_ready
    assert not metadata.promotion_eligible
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        app, ["simulation", "guardian-batch-plan", "--turns", "--max-turns", "20"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["max_turns"] == 20
    monkeypatch.setattr(native, "GUARDIAN_TURN_RULESET_ID", "wrong-native-build")
    with pytest.raises(ProvisionalRuleUnavailableError, match="identity differs"):
        create_provisional_guardian_turn_batch(catalog_path=CATALOG, bible_path=BIBLE, batch_size=1)
