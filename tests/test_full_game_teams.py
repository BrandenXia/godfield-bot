"""Native faction ownership is shared by targeting, reactions and endings."""

import itertools
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import (
    PLAN,
    SEED,
    drain,
    game,
    hand,
    ids,
    load,
    profile,
    step,
    tickets,
)

from godfield_bot.full_game import FullGameMetadata, create_development_full_game_batch
from godfield_bot.full_game_teams import FullGameTeamPlan

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")


def teams(b, layout):
    size = len(b.episode_snapshot())
    b.seed_teams(
        ids(np.repeat(np.arange(size), len(layout))),
        ids(np.tile(np.arange(len(layout)), size)),
        ids(np.tile(layout, size)),
    )


def opponent(layout, source, target):
    return source != target and (layout[source] == 0 or layout[source] != layout[target])


def cast(b, target=2):
    step(b, [1])
    step(b, [0])
    if b.episode_snapshot()[0, 3] == 3:
        step(b, [19 + target])


@pytest.mark.parametrize("layout", tuple(itertools.product(range(5), repeat=3)))
def test_all_three_seat_team_maps_have_the_client_relation_and_faction_ending(layout):
    b = game(teams_enabled=True)
    teams(b, layout)
    expected = [
        [seat, 1, team, 1 if seat == 0 else 3 if opponent(layout, 0, seat) else 2]
        for seat, team in enumerate(layout)
    ]
    assert b.team_observations()[0, :3].tolist() == expected
    assert b.team_observations()[0, 3:].tolist() == [[-1, 0, -1, 0]] * 6
    assert b.team_ids().tolist() == [list(layout) + [-1] * 6]
    assert not b.winning_seats().any()
    b.start_environments(ids([0]))
    shared_win = len(set(layout)) == 1 and layout[0] != 0
    assert bool(b.episode_snapshot()[0, 3] == 12) == shared_win
    assert b.winning_seats()[0].tolist() == [shared_win] * 3 + [False] * 6


@pytest.mark.parametrize("players", range(2, 10))
@pytest.mark.parametrize("kind", ["solo", "pairs", "mixed", "four-teams"])
def test_every_supported_seat_count_exposes_only_enemy_voluntary_targets(players, kind):
    layout = {
        "solo": [0] * players,
        "pairs": [1 + seat % 2 for seat in range(players)],
        "mixed": [0 if seat % 2 else 1 for seat in range(players)],
        "four-teams": [1 + seat % 4 for seat in range(players)],
    }[kind]
    b = game(players=players, teams_enabled=True)
    teams(b, layout)
    hand(b, [35])
    b.start_environments(ids([0]))
    step(b, [1])
    step(b, [0])
    mask = b.choice_masks()[0]
    assert mask[19 : 19 + players].tolist() == [opponent(layout, 0, s) for s in range(players)]
    before = b.episode_snapshot().copy()
    for seat in range(players):
        if not opponent(layout, 0, seat):
            with pytest.raises(ValueError, match="unavailable"):
                step(b, [19 + seat])
            np.testing.assert_array_equal(b.episode_snapshot(), before)
    target = next(s for s in range(players) if opponent(layout, 0, s))
    step(b, [19 + target])
    assert b.pending_observations()[0, 2] == target


@pytest.mark.parametrize(
    "actual,display,fog", [(35, 35, True), (95, 95, False), (35, 95, False), (95, 35, False)]
)
@pytest.mark.parametrize("seed", [0, 1, 67])
def test_fixed_chance_fog_and_private_target_draws_share_enemy_eligibility(
    actual, display, fog, seed
):
    b = game(size=32, players=5, teams_enabled=True, seed=seed, resolve_hidden_targeting=True)
    teams(b, [1, 1, 2, 0, 3])
    for env in range(32):
        hand(b, [(actual, display, 0)], env=env)
        load(b, env=env, mask=1 if fog else 0)
        for seat in range(1, 5):
            load(b, env=env, owner=seat, mask=8)
    b.start_environments(ids(range(32)))
    step(b, [1] * 32)
    step(b, [0] * 32)
    if b.episode_snapshot()[0, 3] == 3:
        step(b, [21] * 32)
    assert set(b.pending_observations()[:, 2]) <= {2, 3, 4}
    assert set(b.episode_snapshot()[:, 2]) <= {2, 3, 4}


def test_area_attack_skips_allies_and_uses_one_original_tick():
    b = game(players=5, teams_enabled=True)
    teams(b, [1, 1, 2, 2, 0])
    hand(b, [35, 232])
    b.start_environments(ids([0]))
    for choice in (1, 2, 0, 21):
        step(b, [choice])
    recipients = []
    while b.episode_snapshot()[0, 3] == 4:
        recipients.append(int(b.episode_snapshot()[0, 2]))
        step(b, [0])
    assert recipients == [2, 3, 4]
    assert b.diagnostic_players()[0, :, 0].tolist() == [100, 100, 90, 90, 90]
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0, 0, 0]


@pytest.mark.parametrize("dead_ally", [False, True])
def test_last_enemy_bow_family_finishes_before_team_victory_and_includes_dead_winners(dead_ally):
    b = game(players=4, teams_enabled=True)
    teams(b, [1, 1, 2, 2])
    hand(b, [35])
    hand(b, [112], owner=2)
    load(b, owner=0, hp=40, mask=8)
    load(b, owner=1, hp=10 if dead_ally else 40, mask=8)
    load(b, owner=2, hp=5, mask=8)
    load(b, owner=3, hp=0, mask=0)
    b.start_environments(ids([0]))
    cast(b)
    step(b, [0])
    assert b.episode_snapshot()[0, 3] == 4 and not b.winning_seats().any()
    drain(b)
    assert b.episode_snapshot()[0, [3, 5, 6]].tolist() == [12, 1, 0]
    assert b.winning_seats()[0].tolist() == [True, True, False, False] + [False] * 5
    assert (b.diagnostic_players()[0, 1, 0] == 0) == dead_ally
    assert b.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0, 0]


def test_post_tick_allied_bow_does_not_attack_the_last_living_teammate():
    b = game(players=3, teams_enabled=True)
    teams(b, [1, 1, 2])
    hand(b, [35, 112])
    load(b, hp=1, illness=1, mask=0)
    load(b, owner=2, hp=5, mask=8)
    b.start_environments(ids([0]))
    cast(b)
    step(b, [0])
    assert b.episode_snapshot()[0, [3, 5, 6]].tolist() == [12, 1, 1]
    assert b.diagnostic_players()[0, 1, 0] == 100
    assert b.ascension_count == 1 and b.attack_family_snapshot()[0, 8] == 0
    assert b.winning_seats()[0, :3].tolist() == [True, True, False]


def test_guardians_do_not_roll_after_allied_turns_but_enemy_guardians_still_act():
    b = game(teams_enabled=True, seed=SEED)
    teams(b, [1, 1, 2])
    b.seed_guardians(ids([0, 0]), ids([1, 2]), ids([1, 1]))
    b.start_environments(ids([0]))
    step(b, [0])
    assert b.guardian_statistics()[0, 2] == 1
    assert b.guardian_activation_count == 1
    assert b.episode_snapshot()[0, 2] in (0, 1)
    drain(b)


@pytest.mark.parametrize("model", [35, 232, 4, 5, 231])
def test_generated_guardian_enemy_routes_cannot_select_its_teammate(model):
    b = game(players=4, teams_enabled=True, seed=SEED, pool=(profile(model),))
    teams(b, [1, 2, 2, 1])
    b.seed_guardians(ids([0]), ids([1]), ids([profile(model)[0]]))
    b.start_environments(ids([0]))
    step(b, [0])
    while b.episode_snapshot()[0, 3] in (4, 6):
        # The buyer can be the guardian owner; only revealed incoming targets
        # must be enemies. No ally guard1→seat2 enemy action is admitted.
        if b.episode_snapshot()[0, 3] == 4:
            assert b.pending_observations()[0, 2] in (0, 3)
        step(b, [0])
    assert b.guardian_generated_execution_counts()[0, model - 3] == 1


def test_bounce_can_hit_a_defenders_ally_without_global_queue_filtering():
    seed = next(s for s in range(1000) if next(tickets(s, 0, 0x8CB92BAA3F3D8DD7)) % 4 == 3)
    b = game(players=4, teams_enabled=True, seed=seed)
    teams(b, [1, 1, 2, 2])
    hand(b, [35])
    hand(b, [21], owner=2)
    b.start_environments(ids([0]))
    cast(b)
    step(b, [1])
    step(b, [0])
    assert b.episode_snapshot()[0, [2, 3]].tolist() == [3, 4]
    step(b, [0])
    assert b.diagnostic_players()[0, 3, 0] == 90


def test_terminal_team_receipts_are_suppressed_even_with_multiple_living_winners():
    b = game(
        teams_enabled=True,
        refill_on_use=True,
        gift_profiles=ids([[191, 1]]),
        apocalypse_after_turns=1,
    )
    teams(b, [1, 1, 2])
    hand(b, [35])
    load(b, owner=2, hp=5, mask=8)
    b.start_environments(ids([0]))
    cast(b)
    step(b, [0])
    assert b.episode_snapshot()[0, 3] == 12
    assert b.winning_seats()[0, :3].tolist() == [True, True, False]
    assert b.automatic_gift_count == b.devil_count == 0
    assert not b.acquisition_snapshot()[:, :, 0].any()


@pytest.mark.parametrize("model", [291, 292])
def test_global_tub_and_enemy_black_hole_keep_different_team_scopes(model):
    phenomenon = next(row for row in PLAN.phenomena.profiles if row[0] == model)
    seed = next(s for s in range(1000) if next(tickets(s, 0, 0x0D95748F728EB658)) % 3 == 1)
    b = game(teams_enabled=True, seed=seed, phenomenon_profiles=ids([phenomenon]))
    teams(b, [1, 1, 2])
    hand(b, [207])
    load(b, owner=2, mask=8)
    b.start_environments(ids([0]))
    cast(b)
    recipients = []
    while b.episode_snapshot()[0, 3] == 4:
        recipients.append(int(b.episode_snapshot()[0, 2]))
        step(b, [0])
    assert recipients == ([1] if model == 291 else [2])


def test_pestle_mortar_can_still_attract_to_an_ally():
    pestle = next(row[0] for row in PLAN.danger.profiles if row[1] == 1)
    mortar = next(row[0] for row in PLAN.danger.profiles if row[1] == 2)
    b = game(teams_enabled=True)
    teams(b, [1, 1, 2])
    hand(b, [pestle])
    hand(b, [mortar], owner=1)
    b.start_environments(ids([0]))
    cast(b)
    assert b.diagnostic_players()[0, 1, 0] == 1
    assert b.diagnostic_players()[0, 2, 0] == 100
    assert b.consumed_count == 2 and b.episode_snapshot()[0, 4] == 1


def test_counter_from_bounced_friendly_damage_can_target_its_allied_source():
    seed = next(s for s in range(1000) if next(tickets(s, 0, 0x8CB92BAA3F3D8DD7)) % 4 == 1)
    counter = next(row[0] for row in PLAN.combat.defense_effect_profiles if row[1] == 1)
    b = game(players=4, teams_enabled=True, seed=seed)
    teams(b, [1, 1, 2, 2])
    hand(b, [35])
    hand(b, [counter], owner=1)
    hand(b, [21], owner=2)
    load(b, mask=8)
    b.start_environments(ids([0]))
    cast(b)
    for choice in (1, 0):
        step(b, [choice])
    assert b.episode_snapshot()[0, 2] == 1
    for choice in (1, 0):
        step(b, [choice])
    assert b.episode_snapshot()[0, [2, 3]].tolist() == [0, 4]
    step(b, [0])
    assert b.counter_count == 1 and b.diagnostic_players()[0, 0, 0] < 100


def test_setup_is_opt_in_bounded_atomic_sealed_and_reset_clears_epoch_teams():
    with pytest.raises(ValueError, match="teams_enabled"):
        teams(game(), [1, 1, 2])
    b = game(size=2, teams_enabled=True)
    before = b.team_ids().copy()
    for envs, owners, values in (
        ([0, 1], [0, 0], [1, 5]),
        ([0, 0], [0, 0], [1, 2]),
        ([0], [0], []),
    ):
        with pytest.raises(ValueError):
            b.seed_teams(ids(envs), ids(owners), ids(values))
        np.testing.assert_array_equal(b.team_ids(), before)
    teams(b, [1, 1, 2])
    old = b.team_ids()
    assert not old.flags.writeable and not b.team_observations().flags.writeable
    assert not b.winning_seats().flags.writeable
    b.start_environments(ids([0]))
    with pytest.raises(ValueError, match="sealed"):
        b.seed_teams(ids([1, 0]), ids([0, 0]), ids([2, 2]))
    np.testing.assert_array_equal(b.team_ids(), old)
    b.reset_environments(ids([0]))
    assert b.team_ids()[0, :3].tolist() == [0, 0, 0]
    assert b.team_ids()[1, :3].tolist() == [1, 1, 2] and old[0, 0] == 1


def test_factory_records_initial_layout_and_keeps_learning_and_live_gates_closed():
    c = create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=2,
        player_count=3,
        teams=(1, 1, 0),
    )
    assert c.metadata.initial_teams == (1, 1, 0)
    assert c.batch.team_ids()[:, :3].tolist() == [[1, 1, 0]] * 2
    assert c.metadata.native_team_rules_implemented and c.metadata.native_team_victory_implemented
    assert (
        not c.metadata.complete_team_rewards_implemented and not c.metadata.full_game_training_ready
    )
    for change in (
        {"initial_teams": (1, 2)},
        {"initial_teams": (True, 1, 2)},
        {"teams_enabled": False},
        {"team_observation_fields": ()},
    ):
        with pytest.raises(ValidationError):
            FullGameMetadata.model_validate(c.metadata.model_dump() | change)
    with pytest.raises(ValidationError):
        FullGameTeamPlan(official_ending_and_timing_verified=True)
