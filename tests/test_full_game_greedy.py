"""Public tactical play and bounded phase progress."""

import pytest
from test_full_game_generated import hand, ids, load, step
from test_full_game_observation import configured, equal_features

from godfield_bot.full_game_greedy import FullGameGreedyPolicy
from godfield_bot.full_game_observation import FullGameObservationEncoder

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def test_combination_targets_weakest_enemy_and_reflection_advances_response():
    c = configured(player_count=4, teams=(1, 1, 2, 3))
    b = c.batch
    hand(b, [35, 15])
    hand(b, [190], owner=3)
    load(b, owner=1, hp=1, mask=0)
    load(b, owner=3, hp=12, mask=0)
    b.start_environments(ids([0]))
    encoder = FullGameObservationEncoder(c)
    opponent = FullGameGreedyPolicy(c.metadata)

    for expected in (1, 2, 0, 22, 1, 0):
        choice = opponent.actions(encoder.encode())
        assert choice.tolist() == [expected]
        step(b, choice.tolist())
    assert b.episode_snapshot()[0, 2:4].tolist() == [0, 4]
    assert b.pending_observations()[0, 3] == 13
    assert b.reflection_count == 1


def test_cost_reducer_completes_a_displayed_unaffordable_heal():
    c = configured(player_count=2, initial_hp=20, initial_mp=0)
    b = c.batch
    hand(b, [235, 204])
    b.start_environments(ids([0]))
    encoder = FullGameObservationEncoder(c)
    opponent = FullGameGreedyPolicy(c.metadata)
    for expected in (1, 2, 0):
        choice = opponent.actions(encoder.encode())
        assert choice.tolist() == [expected]
        step(b, choice.tolist())
    assert b.diagnostic_players()[0, 0, :2].tolist() == [30, 0]
    assert b.mp_spent == 0


def test_fog_and_dream_counterfactuals_leave_tactical_choices_equal():
    observations = []
    choices = []
    for variant in (0, 1):
        c = configured(player_count=3)
        b = c.batch
        hand(b, [(59 if variant else 6, 35, 0), 15])
        hand(b, [90 if variant else 31], owner=1)
        load(b, owner=0, hp=40, mask=3)
        load(b, owner=1, hp=50 if variant else 2, mp=1 if variant else 20, mask=0)
        b.start_environments(ids([0]))
        observation = FullGameObservationEncoder(c).encode()
        observations.append(observation)
        choices.append(FullGameGreedyPolicy(c.metadata).actions(observation))
    equal_features(*observations)
    np.testing.assert_array_equal(*choices)


def test_exchange_and_sacrifice_edits_commit_without_toggle_cycles():
    c = configured(player_count=2, initial_hp=35, initial_cp=20, apocalypse_after_turns=1)
    b = c.batch
    hand(b, [3, 206])
    b.start_environments(ids([0]))
    encoder = FullGameObservationEncoder(c)
    opponent = FullGameGreedyPolicy(c.metadata)
    for expected in (1, 8, 8, 0):
        choice = opponent.actions(encoder.encode())
        assert choice.tolist() == [expected]
        step(b, choice.tolist())
    assert b.diagnostic_players()[0, 0, :3].tolist() == [55, 10, 0]
    step(b, [0])
    assert b.apocalypse_observations()[0, 1] == 1
    for expected in (19, 1, 0):
        choice = opponent.actions(encoder.encode())
        assert choice.tolist() == [expected]
        step(b, choice.tolist())
    assert b.sacrifice_snapshot()[0, 3] == 1


def test_two_mp_miracle_uses_reducer_instead_of_canceling_forever():
    c = configured(player_count=2, initial_mp=0)
    b = c.batch
    hand(b, [211, 143])
    b.start_environments(ids([0]))
    encoder = FullGameObservationEncoder(c)
    opponent = FullGameGreedyPolicy(c.metadata)
    for expected in (1, 2, 0, 20):
        choice = opponent.actions(encoder.encode())
        assert choice.tolist() == [expected]
        step(b, choice.tolist())
    assert b.episode_snapshot()[0, 3] == 4
    assert b.mp_spent == 0
