"""Mirage: source contracts, private fanout, nested reactions and atomic replay."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import (
    ApiCatalogItem,
    ApiCatalogSnapshot,
    api_catalog_digest,
    read_api_catalog_snapshot,
)
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    AREA_FIELDS,
    AREA_SNAPSHOT_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_area import FullGameAreaPlan, build_full_game_area_plan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(
    *,
    size=1,
    players=3,
    seed=67,
    refill=False,
    decisions=1000,
    profiles=((232, 5),),
    missing_armor=None,
    danger_profiles=PLAN.danger.profiles,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        seed=seed,
        max_turns=100,
        max_decisions=decisions,
        initial_hp=100,
        initial_mp=30,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(tuple(r for r in PLAN.combat.armor_profiles if r[0] != missing_armor)),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        passive_profiles=ids(PLAN.passives.profiles),
        removal_profiles=ids(PLAN.removal.profiles),
        cost_reducer_profiles=ids(PLAN.costs.profiles),
        complex_weapon_profiles=ids(PLAN.weapons.profiles),
        danger_profiles=ids(danger_profiles),
        dream_defense_profiles=ids(PLAN.dream_defense.profiles),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        area_profiles=None if profiles is None else ids(profiles).reshape(-1, 2),
        gift_profiles=ids([[191, 1]]),
        refill_on_use=refill,
    )


def hand(batch, models, *, owner=0, env=0, displays=None):
    displays = [0] * len(models) if displays is None else displays
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + i + 1, m, f, 0]
                for i, (m, f) in enumerate(zip(models, displays, strict=True))
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=100, mp=30, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids([[env, *rows[env, :4], c] for env, c in zip(envs, choices, strict=True)]).reshape(-1, 6)
    )
    stats = batch.attack_family_snapshot()
    np.testing.assert_array_equal(
        stats[:, 0], stats[:, 2] + stats[:, 3] + stats[:, 13] + (stats[:, 14] > 0)
    )
    area = batch.area_snapshot()
    assert np.all(area[:, 3] >= area[:, 4] + area[:, 5])


def cast(batch, *, additions=(2,), size=1, target=1):
    batch.start_environments(ids(range(size)))
    step(batch, [1] * size)
    for slot in additions:
        step(batch, [slot] * size)
    step(batch, [0] * size)
    step(batch, [19 + target] * size)


def drain(batch):
    actors = []
    for _ in range(200):
        rows = batch.episode_snapshot()
        envs = np.flatnonzero(rows[:, 3] == 4)
        if not len(envs):
            return actors
        actors.append(int(rows[envs[0], 2]))
        step(batch, [0] * len(envs), envs)
    raise AssertionError("area response drain exceeded its bound")


def snapshot(batch):
    return (
        tuple(
            getattr(batch, name)()
            for name in (
                "episode_snapshot",
                "diagnostic_players",
                "diagnostic_inventory",
                "actor_hands",
                "player_observations",
                "choice_masks",
                "pending_observations",
                "area_observations",
                "area_snapshot",
                "attack_family_snapshot",
                "danger_snapshot",
                "counter_snapshot",
                "complex_weapon_observations",
                "complex_weapon_snapshot",
                "revival_snapshot",
                "dream_defense_snapshot",
                "acquisition_snapshot",
                "attack_order",
                "defense_order",
            )
        ),
        tuple(
            getattr(batch, name)
            for name in (
                "action_count",
                "attack_count",
                "resolved_attack_count",
                "area_count",
                "area_hp_damage",
                "hp_damage",
                "mp_spent",
                "consumed_count",
                "miracle_use_count",
                "counter_count",
                "ascension_count",
                "automatic_gift_count",
                "darkness_finish_count",
            )
        ),
    )


def same(left, right):
    assert left[1] == right[1]
    for a, b in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("mask", range(16))
@pytest.mark.parametrize(
    "weapon,damage,repeats,spent", [(35, 10, 1, 5), (14, 3, 2, 5), (58, 50, 1, 30)]
)
def test_fanout_fixed_cast_payload_fog_bypass_and_single_original_tick(
    players, mask, weapon, damage, repeats, spent
):
    batch = game(players=players)
    hand(batch, [weapon, 232])
    load(batch, mask=mask)
    cast(batch, target=players - 1)
    assert batch.area_observations().tolist() == [[1, 1, 1]]
    assert batch.episode_snapshot()[0, 2] == 1  # Requested target is only a placeholder.
    actors = drain(batch)
    assert actors == [seat for seat in range(1, players) for _ in range(repeats)]
    state = batch.diagnostic_players()[0]
    assert state[:, 0].tolist() == [100] + [100 - damage * repeats] * (players - 1)
    assert state[:, 5].tolist() == [1] + [0] * (players - 1)
    assert batch.mp_spent == spent and batch.attack_count == batch.resolved_attack_count == 1
    assert batch.area_count == 1 and batch.area_hp_damage == damage * repeats * (players - 1)
    assert batch.hp_damage == batch.area_hp_damage and not batch.area_observations().any()
    assert batch.area_snapshot().tolist() == [
        [
            1,
            1,
            players - 1,
            repeats * (players - 1),
            repeats * (players - 1),
            0,
            batch.hp_damage,
            int(bool(mask & 1)),
        ]
    ]
    assert batch.consumed_count == 1 and batch.miracle_use_count == 1
    assert batch.diagnostic_inventory()[0, 0, 0, 1:4].tolist() == [232, 0, 1]


@pytest.mark.parametrize("count", [1, 2, 3])
def test_duplicate_mirages_charge_each_copy_but_not_extra_recipient_waves(count):
    batch = game()
    hand(batch, [35] + [232] * count)
    cast(batch, additions=tuple(range(2, count + 2)))
    assert batch.area_observations().tolist() == [[1, count, 1]]
    assert drain(batch) == [1, 2]
    assert batch.mp_spent == 5 * count and batch.miracle_use_count == count
    assert batch.area_snapshot()[0, :6].tolist() == [1, count, 2, 2, 2, 0]


@pytest.mark.parametrize("leader", [112, 216, 218, 225])
def test_area_is_not_standalone_or_addition_to_chance_weapon_or_primary_miracle(leader):
    batch = game()
    hand(batch, [leader, 232])
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 2]
    step(batch, [1])
    assert not batch.choice_masks()[0, 2]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [2])
    same(before, snapshot(batch))


@pytest.mark.parametrize("leader", [35, 58])
def test_adjacent_waiver_and_undo_rebuild_preview_without_early_cost_or_receipts(leader):
    batch = game()
    hand(batch, [leader, 232, 204, 217])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [4])
    step(batch, [2])
    preview = batch.attack_selection_observations().copy()
    assert preview[0, 2] == 0 and preview[0, 3] == 12
    assert batch.area_observations().tolist() == [[1, 1, 1]]
    assert batch.mp_spent == batch.consumed_count == 0
    step(batch, [3])
    assert batch.attack_selection_observations()[0, 3] == 7
    step(batch, [2])  # The reducer now validly follows Meteor instead.
    assert batch.attack_order()[0, :3].tolist() == [1, 4, 3]
    assert batch.attack_selection_observations()[0, 3] == 0
    assert not batch.area_observations().any()
    step(batch, [3])
    step(batch, [2])
    step(batch, [3])
    step(batch, [0])
    step(batch, [20])
    assert batch.pending_observations()[0, 4] == 0
    drain(batch)
    assert batch.mp_spent == (30 if leader == 58 else 7)
    assert batch.cost_snapshot()[0, :2].tolist() == [1, 5]
    assert batch.hp_damage == (56 if leader == 58 else 20) * 2


@pytest.mark.parametrize(
    "leader,addition,element,attack",
    [
        (94, None, 5, 30),
        (35, 83, 2, 15),
        (35, 66, 1, 12),
        (68, None, 3, 2),
    ],
)
def test_mirage_preserves_preceding_element_and_attack(leader, addition, element, attack):
    batch = game(seed=67)
    models = [leader] + ([] if addition is None else [addition]) + [232]
    hand(batch, models)
    batch.start_environments(ids([0]))
    step(batch, [1])
    if addition is not None:
        step(batch, [2])
    before = batch.attack_selection_observations()[0, 1:3].copy()
    step(batch, [len(models)])
    np.testing.assert_array_equal(batch.attack_selection_observations()[0, 1:3], before)
    assert before.tolist() == [attack, element]


def test_dead_setup_excluded_from_recipient_snapshot():
    batch = game(players=9)
    hand(batch, [35, 232])
    for owner in (2, 4, 6, 8):
        load(batch, owner=owner, hp=0)
    cast(batch, target=7)
    assert drain(batch) == [1, 3, 5, 7]
    assert batch.area_snapshot()[0, 2:6].tolist() == [4, 4, 4, 0]


def test_counter_kills_source_then_suppresses_remaining_original_recipients():
    batch = game(refill=True)
    hand(batch, [57, 232])
    hand(batch, [184], owner=1)
    load(batch, hp=1, mask=8)
    cast(batch)
    step(batch, [1])
    step(batch, [0])
    assert batch.counter_observations()[0, 0] == 1
    assert batch.area_snapshot()[0, 4] == 1 and batch.automatic_gift_count == 0
    step(batch, [0])
    assert batch.area_snapshot()[0, 3:7].tolist() == [2, 1, 1, 30]
    assert batch.attack_count == batch.resolved_attack_count == 1
    assert batch.diagnostic_players()[0, :, 0].tolist() == [0, 70, 100]
    assert batch.suppressed_gift_count == 2 and batch.automatic_gift_count == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_nested_bow_finishes_before_next_original_and_one_tick():
    batch = game(refill=True)
    hand(batch, [57, 232])
    hand(batch, [112], owner=1)
    load(batch, owner=1, hp=1)
    load(batch, mask=8)
    load(batch, owner=2, mask=8)
    cast(batch)
    step(batch, [0])
    assert batch.episode_snapshot()[0, 2:4].tolist() == [0, 4]
    assert batch.attack_family_snapshot()[0, 14] == 3
    step(batch, [0])
    assert batch.attack_family_snapshot()[0, 14] == 3
    assert batch.episode_snapshot()[0, 2] == 2
    step(batch, [0])
    assert batch.attack_family_snapshot()[0, 14] == 2
    assert batch.area_hp_damage == 1 and batch.automatic_gift_count == 0
    step(batch, [0])
    assert batch.area_hp_damage == 31 and batch.ascension_hp_damage == 60
    assert batch.diagnostic_players()[0, :, 0].tolist() == [70, 0, 40]
    assert batch.automatic_gift_count == 2 and batch.suppressed_gift_count == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_reflection_changes_only_current_recipient_not_siblings_or_original_owner():
    batch = game()
    hand(batch, [35, 232])
    hand(batch, [190], owner=1)
    cast(batch)
    step(batch, [1])
    step(batch, [0])
    assert batch.episode_snapshot()[0, 2] == 0
    step(batch, [0])
    assert batch.episode_snapshot()[0, 2] == 2
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [90, 100, 90]
    assert batch.reflection_count == 1 and batch.area_hp_damage == 20


@pytest.mark.parametrize("weapon", [27, 41, 53])
def test_payload_effects_reapplied_per_original_recipient(weapon):
    batch = game()
    hand(batch, [weapon, 232])
    load(batch, hp=50)
    cast(batch)
    drain(batch)
    state = batch.diagnostic_players()[0]
    if weapon == 27:
        assert state[:, 0].tolist() == [64, 93, 93] and batch.absorbed_hp == 14
    elif weapon == 41:
        assert state[:, 0].tolist() == [50, 89, 89]
        assert state[:, 4].tolist() == [0, 8, 8]
    else:
        assert state[:, 0].tolist() == [22, 86, 86] and batch.recoil_hp_damage == 28


def tickets(seed, env, stream):
    mask = 2**64 - 1
    word = seed ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
    word ^= 0xBF58476D1CE4E5B9 ^ stream
    while True:
        word = (word + 0x9E3779B97F4A7C15) & mask
        value = word
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        yield value ^ (value >> 31)


@pytest.mark.parametrize("players", [2, 3])
@pytest.mark.parametrize("seed", [0, 67, 999])
def test_pestle_area_per_shot_independent_target_oracle_and_single_cast(players, seed):
    size = 32
    batch = game(size=size, players=players, seed=seed)
    expected = np.full((size, players), 100)
    self_hits = 0
    for env in range(size):
        hand(batch, [94, 232], env=env)
        stream = tickets(seed, env, 0xA4093822299F31D0)
        for _ in range(players - 1):
            target = next(stream) % players
            expected[env, target] -= 30
            self_hits += target == 0
    cast(batch, size=size)
    drain(batch)
    np.testing.assert_array_equal(batch.diagnostic_players()[:, :, 0], expected)
    assert batch.danger_count == batch.area_count == batch.attack_count == size
    assert batch.area_hp_damage == batch.hp_damage == size * (players - 1) * 30
    assert batch.automatic_danger_hp_damage == self_hits * 30
    assert np.all(batch.danger_snapshot()[:, 1] == players - 1)


def test_multiple_attracted_direct_losses_and_revivals_preserve_queue_damage_accounting():
    batch = game()
    hand(batch, [94, 232])
    hand(batch, [209, 209, 208], owner=1)
    cast(batch)
    assert batch.episode_snapshot()[0, 3] == 1  # Both attracted shots are automatic.
    assert batch.diagnostic_players()[0, :, 0].tolist() == [100, 10, 100]
    assert batch.hp_damage == batch.area_hp_damage == batch.automatic_danger_hp_damage == 100
    assert batch.danger_snapshot()[0, 3] == 2 and batch.revival_count == 1
    assert batch.area_snapshot()[0, 3:7].tolist() == [2, 2, 0, 100]


@pytest.mark.parametrize("seed", [0, 1, 67, 68, 999])
def test_large_pestle_roster_oracle_skips_later_dead_nominal_targets_and_sources(seed):
    size, players = 32, 9
    batch = game(size=size, players=players, seed=seed)
    expected = np.full((size, players), 100)
    resolved, suppressed, damage, self_damage = [], [], 0, 0
    for env in range(size):
        hand(batch, [94, 232], env=env)
        stream = tickets(seed, env, 0xA4093822299F31D0)
        hits = 0
        for nominal in range(1, players):
            if expected[env, 0] == 0 or expected[env, nominal] == 0:
                continue
            living = np.flatnonzero(expected[env] > 0)
            target = living[next(stream) % len(living)]
            loss = min(30, expected[env, target])
            expected[env, target] -= loss
            damage += loss
            self_damage += loss if target == 0 else 0
            hits += 1
        resolved.append(hits)
        suppressed.append(players - 1 - hits)
    cast(batch, size=size, target=8)
    drain(batch)
    np.testing.assert_array_equal(batch.diagnostic_players()[:, :, 0], expected)
    np.testing.assert_array_equal(batch.area_snapshot()[:, 4], resolved)
    np.testing.assert_array_equal(batch.area_snapshot()[:, 5], suppressed)
    assert batch.hp_damage == batch.area_hp_damage == damage
    assert batch.automatic_danger_hp_damage == self_damage
    assert batch.resolved_attack_count == size


@pytest.mark.parametrize("weapon", [35, 14])
def test_hat_and_sun_defense_finish_before_later_original_recipients(weapon):
    batch = game(refill=True)
    hand(batch, [weapon, 232])
    hand(batch, [178, 208, 35], owner=1)
    load(batch, owner=1, hp=1)
    cast(batch)
    step(batch, [1])
    step(batch, [0])  # Neutral attack permits Hat; no damage, redraws surviving hand.
    assert batch.redraw_count == 1 and batch.redrawn_count == 2
    assert batch.automatic_gift_count == 0
    drain(batch)
    assert batch.diagnostic_players()[0, 1, 5] == 0
    assert batch.diagnostic_players()[0, 0, 5] == 1
    assert batch.area_snapshot()[0, 4:6].sum() == (4 if weapon == 14 else 2)


def test_actual_sun_revives_first_recipient_then_area_continues_once():
    batch = game()
    hand(batch, [57, 232])
    hand(batch, [208], owner=1)
    load(batch, owner=1, hp=1)
    cast(batch)
    step(batch, [0])
    assert batch.revival_count == 1 and batch.episode_snapshot()[0, 2] == 2
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [100, 10, 70]
    assert batch.area_hp_damage == 31 and batch.ascension_count == 0


def test_two_automatic_darkness_finishes_in_one_command_are_not_boolean_collapsed():
    seed = next(
        s
        for s in range(1000)
        if [v % 3 for v in list_take(tickets(s, 0, 0xA4093822299F31D0), 2)] == [0, 0]
    )
    # Raw development profiles exercise generic accounting, not pinned Pestle's Light role.
    batch = game(seed=seed, danger_profiles=((94, 1, 30, 6), (209, 2, 99, 0)))
    hand(batch, [94, 232, 208, 208])
    cast(batch)
    assert batch.darkness_finish_count == 2 and batch.revival_count == 2
    assert batch.area_hp_damage == batch.hp_damage == 110
    assert batch.diagnostic_players()[0, 0, 0] == 10


def list_take(stream, count):
    return [next(stream) for _ in range(count)]


def test_fog_response_observations_do_not_reveal_future_recipient_count():
    batches = [game(players=9), game(players=9)]
    for index, batch in enumerate(batches):
        hand(batch, [14, 232])
        load(batch, owner=1, mask=1)
        if index:
            for owner in range(2, 9):
                load(batch, owner=owner, hp=0)
        cast(batch)
    assert batches[0].attack_family_snapshot()[0, 13] != batches[1].attack_family_snapshot()[0, 13]
    for name in (
        "actor_hands",
        "player_observations",
        "choice_masks",
        "pending_observations",
        "area_observations",
        "complex_weapon_observations",
        "attack_effect_observations",
    ):
        np.testing.assert_array_equal(getattr(batches[0], name)(), getattr(batches[1], name)())
    assert batches[0].complex_weapon_observations().tolist() == [[1, 3, 3, 2]]


@pytest.mark.parametrize("actual,display,fanout,cost", [(232, 217, 2, 5), (217, 232, 1, 7)])
def test_displayed_area_is_not_true_role_or_cost_until_cast(actual, display, fanout, cost):
    batch = game()
    hand(batch, [35, actual], displays=[0, display])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [2])
    assert batch.area_observations()[0, 0] == int(display == 232)
    step(batch, [0])
    step(batch, [20])
    assert batch.area_observations()[0, 0] == int(actual == 232)
    assert len(drain(batch)) == fanout and batch.mp_spent == cost


def test_reset_clears_area_episode_and_queue_but_preserves_lifetime_counters():
    batch = game()
    hand(batch, [35, 232])
    cast(batch)
    step(batch, [0])
    old = batch.area_snapshot()
    assert not old.flags.writeable
    with pytest.raises(ValueError):
        old[0, 0] = 2
    batch.reset_environments(ids([0]))
    assert not batch.area_snapshot().any() and not batch.area_observations().any()
    assert not batch.attack_family_snapshot().any()
    assert batch.area_count == 1 and batch.area_hp_damage == 10 and old[0, 0] == 1


@pytest.mark.parametrize("leader", [35, 94])
def test_late_hidden_cost_failure_rolls_back_all_batch_casts_then_replays(leader):
    batch, reference = game(size=2), game(size=2)
    for item in (batch, reference):
        for env in range(2):
            hand(
                item,
                [leader, 232 if env == 0 else 217],
                env=env,
                displays=[0, 0 if env == 0 else 232],
            )
            load(item, env=env, mp=5)
        item.start_environments(ids([0, 1]))
        step(item, [1, 1])
        step(item, [2, 2])
        step(item, [0, 0])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="unaffordable"):
        step(batch, [20, 20])
    same(before, snapshot(batch))
    step(batch, [20], [0])
    step(reference, [20], [0])
    same(snapshot(batch), snapshot(reference))


def test_late_hidden_defense_failure_rolls_back_queue_and_early_area_damage():
    batch = game(size=2, missing_armor=128)
    for env in range(2):
        hand(batch, [35, 232], env=env)
        hand(batch, [128], owner=1, env=env, displays=[127])
    cast(batch, size=2)
    step(batch, [1], [1])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [0, 0])
    same(before, snapshot(batch))
    step(batch, [1], [1])
    step(batch, [0, 0])
    assert np.all(batch.area_snapshot()[:, 4] == 1)


@pytest.mark.parametrize(
    "profiles",
    [(), ((232, 0),), ((232, 101),), ((232, 5), (232, 5)), ((35, 5),), ((237, 5),), ((217, 5),)],
)
def test_raw_area_profile_rejects_empty_invalid_categories_collisions_and_duplicates(profiles):
    with pytest.raises(ValueError, match="area profile"):
        game(profiles=profiles)


def test_factory_and_pins_preserve_versioning_and_fail_closed_gates():
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    assert configured.metadata.area_observation_fields == AREA_FIELDS
    assert configured.metadata.area_snapshot_fields == AREA_SNAPSHOT_FIELDS
    assert PLAN.integrated_artifact_effect_count == 237 and PLAN.area.profiles == ((232, 5),)
    assert configured.metadata.kernel_schema_version == 33
    assert configured.metadata.attack_family_schema_version == 8
    assert not configured.metadata.full_game_training_ready and not PLAN.area.promotion_eligible
    assert (
        FullGameMetadata.model_validate_json(configured.metadata.model_dump_json())
        == configured.metadata
    )
    assert (
        build_full_game_area_plan(
            read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
        )
        == PLAN.area
    )


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((232, 4),)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profile_fields": ("private-target",)},
        {"official_fidelity_verified": True},
        {"promotion_eligible": True},
        {"official_multiplayer_and_compound_timing_verified": True},
        {"schema_version": 2},
    ],
)
def test_forged_area_source_contracts_and_fidelity_relabeling_fail(change):
    with pytest.raises(ValidationError):
        FullGameAreaPlan.model_validate(PLAN.area.model_dump() | change)


@pytest.mark.parametrize(
    "change",
    [
        {"area_observation_fields": ("future-seats",)},
        {"area_snapshot_fields": ("native-ticket",)},
        {"area_observation_boundary": "private-queue-policy"},
        {"full_game_training_ready": True},
        {"local_training_eligible": True},
    ],
)
def test_metadata_area_projection_and_learning_relabeling_fail_closed(change):
    metadata = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    ).metadata
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(metadata.model_dump() | change)


@pytest.mark.parametrize(
    "change",
    [
        {"cost": 4},
        {"isPlusAtk": False},
        {"ability": "attackTwice"},
        {"giftRate": 2},
        {"name": "Another Mirage"},
        {"atk": 1},
    ],
)
def test_exact_raw_mirage_contract_rejects_rehashed_source_drift(change):
    catalog = read_api_catalog_snapshot(CATALOG)
    items = tuple(
        ApiCatalogItem(model_id=i.model_id, raw=dict(i.raw) | change) if i.model_id == 232 else i
        for i in catalog.items
    )
    altered = ApiCatalogSnapshot.model_validate(
        catalog.model_dump()
        | {
            "items": [i.model_dump() for i in items],
            "content_sha256": api_catalog_digest(items),
        }
    )
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_area_plan(altered, BibleSnapshot.model_validate_json(BIBLE.read_text()))


@pytest.mark.parametrize(
    "change",
    [
        {"detail": ("<Mirage>", "Attack", "all the enemies", "Cost", "4MP", "Gift Rate: 1/500")},
        {"image_path": "/images/items/miracles/another.webp"},
        {"element_image_paths": ("/images/elements/light.webp",)},
    ],
)
def test_exact_bible_mirage_contract_rejects_asset_text_or_element_drift(change):
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    miracles = bible.catalog["miracles"]
    altered = bible.model_copy(
        update={
            "catalog": bible.catalog
            | {
                "miracles": miracles.model_copy(
                    update={
                        "items": tuple(
                            item.model_copy(update=change) if item.asset == "mirage" else item
                            for item in miracles.items
                        )
                    }
                ),
            }
        }
    )
    with pytest.raises(ValueError, match="API and Bible"):
        build_full_game_area_plan(read_api_catalog_snapshot(CATALOG), altered)
