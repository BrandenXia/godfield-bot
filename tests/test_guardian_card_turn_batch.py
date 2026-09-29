"""Typed card attacks, exact MP spending, and reusable Wall/Turbulence defenses."""

from pathlib import Path

import pytest

from godfield_bot.guardian_batch import create_provisional_guardian_turn_batch

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def batch(*, size=4, players=3, mp=10):
    return native.GuardianTurnBatch(
        size,
        players,
        3,
        ids([[0, 101, 1], [1, 102, 1]]),
        ids([[101, 10, 0, 100, 0, 0, 0], [102, 0, 0, 100, 6, 5, 0]]),
        ids([[201, 3, 0, 0, 0], [202, 5, 2, 0, 0], [233, 0, 0, 1, 6], [234, 0, 0, 2, 5]]),
        hand_slots=6,
        initial_mp=mp,
        attack_profiles=ids(
            [
                [300, 10, 0, 0, 0],
                [301, 10, 1, 0, 0],
                [302, 4, 5, 0, 0],
                [303, 8, 1, 1, 2],
                [304, 4, 5, 1, 2],
                [305, 1, 6, 1, 5],
            ]
        ),
    )


def deal(game, env, player, models, *, first_instance=100):
    count = len(models)
    game.deal_cards(
        ids([env] * count),
        ids([player] * count),
        ids(list(range(count))),
        ids(list(range(first_instance, first_instance + count))),
        ids(models),
    )


def attack(game, envs, *, player=0, slot=0, target=1):
    count = len(envs)
    game.begin_card_attacks(
        ids(envs), ids([player] * count), ids([slot] * count), ids([target] * count)
    )


def step(game, envs, actions, *, player=1):
    game.step_defenses(ids(envs), ids([player] * len(envs)), ids(actions))


def rotate_back_to_zero(game, env=0):
    game.pass_turns(ids([env]), ids([1]))
    game.pass_turns(ids([env]), ids([2]))


def test_weapon_spent_at_declaration_and_wall_reused_until_mp_is_insufficient():
    game = batch(mp=12)
    deal(game, 0, 0, [300], first_instance=200)
    deal(game, 0, 1, [233])
    np.testing.assert_array_equal(
        game.attack_action_masks()[0], [True, False, False, False, False, False, True]
    )
    np.testing.assert_array_equal(game.attack_target_masks()[0], [False, True, True])
    for cast in range(2):
        attack(game, [0])
        assert not np.any(game.inventory_snapshot()[0, 0, 0])
        assert game.defense_action_masks()[0, 0]
        step(game, [0], [0])
        assert game.turn_snapshot()[0, 8] == 6
        assert game.resource_snapshot()[0, 1, 1] == 12 - cast * 6
        step(game, [0], [7])
        assert game.resource_snapshot()[0, 1, 1] == 12 - (cast + 1) * 6
        assert game.resource_snapshot()[0, 1, 0] == 40
        assert game.inventory_snapshot()[0, 1, 0, 0] == 100
        assert game.miracle_cast_count == cast + 1
        rotate_back_to_zero(game)
        deal(game, 0, 0, [300], first_instance=201 + cast)
    attack(game, [0])
    assert not game.defense_action_masks()[0, 0]
    assert game.mp_spent == 12 and game.consumed_card_count == 3
    step(game, [0], [6])
    assert game.resource_snapshot()[0, 1, 0] == 30
    assert game.resolved_effect_count == 3


def test_miracle_attack_retains_card_debits_exact_cost_and_masks_when_unaffordable():
    game = batch(mp=4)
    deal(game, 0, 0, [303], first_instance=200)
    for remaining in (2, 0):
        attack(game, [0])
        assert game.inventory_snapshot()[0, 0, 0, 0] == 200
        assert game.resource_snapshot()[0, 0, 1] == remaining
        assert game.turn_snapshot()[0, 9] == 1
        step(game, [0], [6])
        rotate_back_to_zero(game)
    assert not game.attack_action_masks()[0, 0]
    before = game.turn_snapshot()
    with pytest.raises(ValueError, match="unaffordable"):
        attack(game, [0])
    np.testing.assert_array_equal(game.turn_snapshot(), before)
    assert game.miracle_cast_count == 2 and game.mp_spent == 4
    assert game.consumed_card_count == 0


@pytest.mark.parametrize(
    "model,wall,turbulence",
    [
        (300, True, False),
        (301, False, False),
        (302, False, False),
        (303, False, True),
        (304, False, True),
        (305, False, True),
    ],
)
def test_effect_defense_legality_depends_on_attack_origin_and_element(model, wall, turbulence):
    game = batch()
    deal(game, 0, 0, [model], first_instance=200)
    deal(game, 0, 1, [233, 234])
    attack(game, [0])
    mask = game.defense_action_masks()[0]
    assert bool(mask[0]) == wall
    assert bool(mask[1]) == turbulence


def test_guardian_category_is_not_silently_inferred_as_weapon_or_miracle():
    game = batch()
    deal(game, 0, 1, [233, 234])
    game.summon(ids([0]), ids([0]), ids([1]), ids([0]), ids([0]))
    game.begin_effects(ids([0]), ids([0]), ids([1]), ids([1]), ids([0]), ids([0]))
    assert game.turn_snapshot()[0, 9] == 2
    assert not np.any(game.defense_action_masks()[0, :2])


def test_special_defenses_cannot_be_combined_and_selection_or_forgiveness_costs_nothing():
    game = batch()
    deal(game, 0, 0, [300], first_instance=200)
    deal(game, 0, 1, [233, 201])
    attack(game, [0])
    step(game, [0], [0])
    assert not game.defense_action_masks()[0, 1]
    with pytest.raises(ValueError, match="not legal"):
        step(game, [0], [1])
    step(game, [0], [0])
    step(game, [0], [1])
    assert not game.defense_action_masks()[0, 0]
    step(game, [0], [6])
    assert game.resource_snapshot()[0, 1, 1] == 10
    assert game.miracle_cast_count == game.mp_spent == 0
    assert game.inventory_snapshot()[0, 1, 0, 0] == 100


def test_turbulence_requires_explicit_target_and_spends_mp_only_after_valid_choice():
    game = batch(mp=5)
    deal(game, 0, 0, [303], first_instance=200)
    deal(game, 0, 1, [234])
    deal(game, 0, 2, [234, 202], first_instance=300)
    attack(game, [0])
    step(game, [0], [0])
    step(game, [0], [7])
    assert game.turn_snapshot()[0, 0] == 4
    assert not np.any(game.defense_action_masks()[0])
    assert not np.any(game.attack_action_masks()[0])
    np.testing.assert_array_equal(game.bounce_target_masks()[0], [True, False, True])
    assert game.resource_snapshot()[0, 1, 1] == 5
    with pytest.raises(ValueError, match="phase"):
        step(game, [0], [6])
    for target in (-1, 1, 3):
        with pytest.raises(ValueError, match="bounce"):
            game.resolve_bounces(ids([0]), ids([1]), ids([target]))
        assert game.resource_snapshot()[0, 1, 1] == 5
        assert game.turn_snapshot()[0, 0] == 4
    game.resolve_bounces(ids([0]), ids([1]), ids([2]))
    assert game.resource_snapshot()[0, 1, 1] == 0
    assert game.inventory_snapshot()[0, 1, 0, 0] == 100
    assert game.turn_snapshot()[0, 2] == 2
    assert game.turn_snapshot()[0, 10] == 1
    assert not game.defense_action_masks()[0, 0]  # Second bounce is not implemented.
    assert game.defense_action_masks()[0, 1]
    step(game, [0], [1], player=2)
    step(game, [0], [7], player=2)
    assert game.resource_snapshot()[0, 2, 0] == 37
    assert game.resource_snapshot()[0, 1, 0] == 40
    assert game.turn_snapshot()[0, 1] == 1  # Original turn advances exactly once.
    assert game.resolved_effect_count == 1
    assert game.miracle_cast_count == 2 and game.mp_spent == 7
    assert game.consumed_card_count == 1  # Only the numerical armor.


def test_bounce_can_return_attack_to_original_caster_without_double_charging_attack_cost():
    game = batch()
    deal(game, 0, 0, [304], first_instance=200)
    deal(game, 0, 1, [234])
    attack(game, [0])
    step(game, [0], [0])
    step(game, [0], [7])
    game.resolve_bounces(ids([0]), ids([1]), ids([0]))
    step(game, [0], [6], player=0)
    assert game.resource_snapshot()[0, 0, 0] == 36
    assert game.resource_snapshot()[0, 0, 1] == 8
    assert game.resource_snapshot()[0, 1, 1] == 5
    assert game.turn_snapshot()[0, 3] == 1


def test_multirow_card_attack_and_bounce_errors_are_atomic_for_resources_and_inventory():
    game = batch(mp=5)
    deal(game, 0, 0, [300], first_instance=200)
    deal(game, 1, 0, [303], first_instance=200)
    before = game.inventory_snapshot()
    with pytest.raises(ValueError, match="target"):
        game.begin_card_attacks(ids([0, 1]), ids([0, 0]), ids([0, 0]), ids([1, 0]))
    np.testing.assert_array_equal(game.inventory_snapshot(), before)
    assert not np.any(game.turn_snapshot()[:, 3])
    assert game.mp_spent == game.consumed_card_count == 0
    for env in (1, 2):
        if env == 2:
            deal(game, env, 0, [303], first_instance=200)
        deal(game, env, 1, [234])
        attack(game, [env])
        step(game, [env], [0])
        step(game, [env], [7])
    turn, resources = game.turn_snapshot(), game.resource_snapshot()
    with pytest.raises(ValueError, match="bounce"):
        game.resolve_bounces(ids([1, 2]), ids([1, 1]), ids([0, 1]))
    np.testing.assert_array_equal(game.turn_snapshot(), turn)
    np.testing.assert_array_equal(game.resource_snapshot(), resources)


def test_invalid_guardian_batch_does_not_overwrite_prior_card_origin():
    game = batch()
    deal(game, 0, 0, [300], first_instance=200)
    attack(game, [0])
    step(game, [0], [6])
    rotate_back_to_zero(game)
    game.summon(ids([0, 1]), ids([0, 0]), ids([1, 1]), ids([0, 1]), ids([0, 0]))
    before = game.turn_snapshot()
    with pytest.raises(ValueError, match="turn owner"):
        game.begin_effects(
            ids([0, 1]), ids([0, 0]), ids([1, 1]), ids([1, 0]), ids([0, 0]), ids([0, 0])
        )
    np.testing.assert_array_equal(game.turn_snapshot(), before)


@pytest.mark.parametrize(
    "defenses",
    [
        [[233, 0, 0, 1, 0]],
        [[233, 0, 0, 1, 101]],
        [[233, 1, 0, 1, 6]],
        [[233, 0, 1, 1, 6]],
        [[234, 0, 0, 3, 5]],
        [[201, 3, 0, 0, 1]],
    ],
)
def test_reusable_defense_profiles_reject_invalid_costs_values_and_kinds(defenses):
    with pytest.raises(ValueError, match="profile"):
        native.GuardianTurnBatch(
            1, 2, 1, ids([[0, 101, 1]]), ids([[101, 10, 0, 100]]), ids(defenses)
        )


def test_defense_only_deal_rejects_an_attack_and_mp_gain_restores_affordability():
    game = batch(mp=0)
    with pytest.raises(ValueError, match="card"):
        game.deal_defenses(ids([0]), ids([0]), ids([0]), ids([1]), ids([303]))
    assert not np.any(game.inventory_snapshot())
    deal(game, 0, 0, [305], first_instance=200)
    assert not game.attack_action_masks()[0, 0]
    game.summon(ids([0]), ids([0]), ids([1]), ids([0]), ids([1]))
    game.begin_effects(ids([0]), ids([0]), ids([1]), ids([0]), ids([0]), ids([0]))
    assert game.resource_snapshot()[0, 0, 1] == 5
    rotate_back_to_zero(game)
    assert game.attack_action_masks()[0, 0]
    attack(game, [0])
    assert game.resource_snapshot()[0, 0, 1] == 0


def test_mixed_wall_bounce_armor_and_forgiveness_commit_independently():
    game = batch()
    for env, model, defense in ((0, 300, 233), (1, 303, 234), (2, 300, 201), (3, 300, 201)):
        deal(game, env, 0, [model], first_instance=200)
        deal(game, env, 1, [defense])
    attack(game, [0, 1, 2, 3])
    step(game, [0, 1, 2], [0, 0, 0])
    step(game, [0, 1, 2, 3], [7, 7, 7, 6])
    np.testing.assert_array_equal(game.turn_snapshot()[:, 0], [0, 4, 0, 0])
    np.testing.assert_array_equal(game.resource_snapshot()[:, 1, 0], [40, 40, 33, 30])
    np.testing.assert_array_equal(game.resource_snapshot()[:, 1, 1], [4, 10, 10, 10])
    assert game.resolved_effect_count == 3
    assert game.consumed_card_count == 4  # Three weapons and one armor.
    assert game.mp_spent == 8  # Attack miracle + Wall; bounce awaits target.


def test_hand_features_are_copied_readonly_and_reset_clears_card_and_bounce_state():
    game = batch()
    deal(game, 0, 0, [303, 300], first_instance=200)
    deal(game, 0, 1, [234, 201])
    features = game.hand_feature_snapshot()
    np.testing.assert_array_equal(features[0, 0, 0], [3, 8, 0, 1, 2, 1])
    np.testing.assert_array_equal(features[0, 0, 1], [2, 10, 0, 0, 0, 0])
    np.testing.assert_array_equal(features[0, 1, 0], [5, 0, 0, 0, 5, 1])
    assert not features.flags.writeable
    attack(game, [0])
    step(game, [0], [0])
    step(game, [0], [7])
    game.reset_environments(ids([0]))
    assert not np.any(game.hand_feature_snapshot()[0])
    assert game.turn_snapshot()[0, 9] == -1
    assert game.turn_snapshot()[0, 0] == 0
    assert not np.any(game.bounce_target_masks()[0])
    assert np.all(game.resource_snapshot()[0, :, 1] == 10)
    assert features[0, 1, 0, 4] == 5


@pytest.mark.parametrize(
    "profiles",
    [
        [[300, 10, 0, 0, 1]],
        [[300, 10, 0, 1, 0]],
        [[300, 10, 0, 2, 0]],
        [[300, 0, 0, 0, 0]],
        [[300, 10, 7, 0, 0]],
        [[201, 10, 0, 0, 0]],
        [[300, 10, 0, 0, 0], [300, 10, 0, 0, 0]],
        [[300, 10, 0]],
    ],
)
def test_invalid_attack_profiles_reject_duplicates_cross_roles_and_invalid_costs(profiles):
    with pytest.raises(ValueError, match="profile"):
        native.GuardianTurnBatch(
            1,
            2,
            1,
            ids([[0, 101, 1]]),
            ids([[101, 10, 0, 100]]),
            ids([[201, 3, 0]]),
            attack_profiles=ids(profiles),
        )


def test_all_45_pinned_basic_attack_models_have_correct_origin_cost_and_consumption():
    created = create_provisional_guardian_turn_batch(
        catalog_path=Path("data/snapshots/2026-09-21/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=45,
        initial_mp=100,
    )
    game, metadata = created.batch, created.metadata
    models = metadata.attack_weapon_model_ids + metadata.attack_miracle_model_ids
    envs = ids(list(range(45)))
    zeros, ones = ids([0] * 45), ids([1] * 45)
    game.deal_cards(envs, zeros, zeros, ones, ids(models))
    features = game.hand_feature_snapshot()
    game.begin_card_attacks(envs, zeros, zeros, ones)
    np.testing.assert_array_equal(game.resource_snapshot()[:, 0, 1], 100 - features[:, 0, 0, 4])
    assert not np.any(game.inventory_snapshot()[:39, 0, 0])
    assert np.all(game.inventory_snapshot()[39:, 0, 0, 0] == 1)
    game.step_defenses(envs, ones, ids([18] * 45))
    assert np.all(game.turn_snapshot()[:, 3] == 1)
    assert game.consumed_card_count == 39
    assert game.miracle_cast_count == 6
    assert game.mp_spent == 31
    assert not metadata.local_training_eligible and not metadata.promotion_eligible


def test_seeded_card_arenas_handle_bounce_phase_and_finish_reproducibly():
    def rollout(seed):
        created = create_provisional_guardian_turn_batch(
            catalog_path=Path("data/snapshots/2026-09-21/api-catalog-en.json"),
            bible_path=Path("data/snapshots/2026-09-20/bible.json"),
            batch_size=8,
            player_count=3,
            initial_mp=20,
            max_turns=30,
        )
        game, metadata = created.batch, created.metadata
        rng = np.random.default_rng(seed)
        all_models = (
            metadata.defense_model_ids
            + metadata.attack_weapon_model_ids
            + metadata.attack_miracle_model_ids
        )
        models = rng.choice(ids(all_models), (8, 3, 18))
        models[:, :, 0] = ids([6 if env % 2 == 0 else 211 for env in range(8)])[:, None]
        models[:, :, 1] = 233
        models[:, :, 2] = 234
        game.deal_cards(
            np.repeat(np.arange(8, dtype=np.int64), 54),
            np.tile(np.repeat(np.arange(3, dtype=np.int64), 18), 8),
            np.tile(np.arange(18, dtype=np.int64), 24),
            np.tile(np.arange(1, 55, dtype=np.int64), 8),
            models.ravel(),
        )
        bounce_choices = 0
        for _ in range(30 * 68 + 1):
            turns = game.turn_snapshot()
            if np.all(np.isin(turns[:, 0], [2, 3])):
                break
            ready = np.flatnonzero(turns[:, 0] == 0)
            actions, targets = game.attack_action_masks(), game.attack_target_masks()
            for env in ready:
                actor = int(turns[env, 2])
                legal = np.flatnonzero(actions[env, :18])
                if not len(legal):
                    game.pass_turns(ids([env]), ids([actor]))
                else:
                    game.begin_card_attacks(
                        ids([env]),
                        ids([actor]),
                        ids([legal[0]]),
                        ids([rng.choice(np.flatnonzero(targets[env]))]),
                    )
            turns = game.turn_snapshot()
            defensive = np.flatnonzero(turns[:, 0] == 1)
            masks, features = game.defense_action_masks(), game.hand_feature_snapshot()
            for env in defensive:
                actor = int(turns[env, 2])
                legal = np.flatnonzero(masks[env, :18])
                if masks[env, 19]:
                    action = 19
                elif len(legal):
                    # Prefer the new reusable effects before numerical armor.
                    special = [slot for slot in legal if features[env, actor, slot, 0] in (4, 5)]
                    action = special[0] if special else legal[0]
                else:
                    action = 18
                game.step_defenses(ids([env]), ids([actor]), ids([action]))
            turns, targets = game.turn_snapshot(), game.bounce_target_masks()
            for env in np.flatnonzero(turns[:, 0] == 4):
                game.resolve_bounces(
                    ids([env]),
                    ids([turns[env, 2]]),
                    ids([rng.choice(np.flatnonzero(targets[env]))]),
                )
                bounce_choices += 1
            assert np.all(game.resource_snapshot()[..., 1] >= 0)
        else:
            pytest.fail("bounded card arena did not finish")
        assert bounce_choices > 0 and game.miracle_cast_count > 0 and game.mp_spent > 0
        return (
            game.turn_snapshot(),
            game.resource_snapshot(),
            game.inventory_snapshot(),
            (game.miracle_cast_count, game.mp_spent, game.consumed_card_count, bounce_choices),
        )

    first, second = rollout(67), rollout(67)
    for expected, actual in zip(first, second, strict=True):
        np.testing.assert_array_equal(expected, actual)
