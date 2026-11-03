"""Joined ten phenomena and forced control; independent tickets and atomicity."""

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan, create_development_full_game_batch
from godfield_bot.full_game_phenomena import FullGamePhenomenonPlan, build_full_game_phenomenon_plan

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def tickets(seed, env, stream, epoch=1):
    mask = 2**64 - 1
    word = (
        seed
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ stream
    )
    while True:
        word = (word + 0x9E3779B97F4A7C15) & mask
        value = word
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        yield value ^ (value >> 31)


def quiet(seed):
    rng = tickets(seed, 0, 0x9216D5D98979FB1B)
    return all(next(rng) % 100 >= 25 for _ in range(8))


QUIET_SEED = next(seed for seed in range(10000) if quiet(seed))


def game(
    *, size=1, players=3, seed=QUIET_SEED, profiles=PLAN.phenomena.profiles, fate=True, **options
):
    kwargs = dict(
        capacity=18,
        seed=seed,
        initial_hp=50,
        initial_mp=20,
        initial_cp=5,
        gift_profiles=ids(PLAN.gifts.model_weights),
        max_turns=100,
        max_decisions=1000,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        passive_profiles=ids(PLAN.passives.profiles),
        removal_profiles=ids(PLAN.removal.profiles),
        cost_reducer_profiles=ids(PLAN.costs.profiles),
        complex_weapon_profiles=ids(PLAN.weapons.profiles),
        danger_profiles=ids(PLAN.danger.profiles),
        dream_defense_profiles=ids(PLAN.dream_defense.profiles),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        area_profiles=ids(PLAN.area.profiles),
        discard_model_ids=ids(PLAN.discard.discard_model_ids),
        guardian_profiles=ids(PLAN.guardians.profiles),
        summon_profiles=ids(PLAN.guardians.summon_profiles),
    )
    kwargs.update(options)
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        phenomenon_profiles=None if profiles is None else ids(profiles).reshape(-1, 5),
        fate_model_ids=ids([207]) if fate else None,
        **kwargs,
    )


def force(model, **options):
    return game(profiles=(next(p for p in PLAN.phenomena.profiles if p[0] == model),), **options)


def hand(batch, values, *, env=0, owner=0):
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 100 + i + 1, *(v if isinstance(v, tuple) else (v, 0, 0))]
                for i, v in enumerate(values)
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=50, mp=20, cp=5, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids([[e, *rows[e, :4], c] for e, c in zip(envs, choices, strict=True)]).reshape(-1, 6)
    )
    stats = batch.attack_family_snapshot()
    np.testing.assert_array_equal(
        stats[:, 0], stats[:, 2] + stats[:, 3] + stats[:, 13] + (stats[:, 14] > 0)
    )


def cast(batch, env=0):
    step(batch, [1], [env])
    assert not batch.phenomenon_snapshot()[env].any()
    step(batch, [0], [env])


def drain(batch):
    for _ in range(100):
        envs = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4)
        if not len(envs):
            return
        step(batch, [0] * len(envs), envs)
    raise AssertionError("phenomenon drain exceeded bound")


def snapshot(batch):
    return tuple(
        getattr(batch, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "actor_hands",
            "player_observations",
            "control_observations",
            "confusion_snapshot",
            "policy_gradient_masks",
            "phenomenon_snapshot",
            "phenomenon_model_counts",
            "phenomenon_observations",
            "attack_family_snapshot",
            "guardian_snapshot",
            "guardian_statistics",
        )
    )


def same(a, b):
    for left, right in zip(a, b, strict=True):
        np.testing.assert_array_equal(left, right)


@pytest.mark.parametrize("model", range(287, 297))
@pytest.mark.parametrize("players", [2, 3, 9])
def test_all10_joined_effects_counts_and_one_original_tick(model, players):
    batch = force(model, players=players)
    hand(batch, [207, (127, 142, 0), (238, 235, 1), 208])
    for owner in range(1, players):
        hand(batch, [127, 237, 208], owner=owner)
    for owner in range(players):
        load(batch, owner=owner, cp=99, mask=8)
    batch.start_environments(ids([0]))
    before = batch.diagnostic_inventory().copy()
    cast(batch)
    if model in (291, 292):
        assert batch.phenomenon_observations()[0, 0:2].tolist() == [1, model]
        assert batch.pending_observations()[0, 5] == 5
    drain(batch)
    s = batch.phenomenon_snapshot()[0]
    assert s[:2].tolist() == [1, 1]
    assert batch.phenomenon_model_counts()[0, model - 287] == 1
    assert batch.episode_snapshot()[0, 4] == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)
    assert not batch.phenomenon_observations().any()
    if model == 287:
        assert batch.diagnostic_players()[0, :, 3].tolist() == [2] * players
        assert batch.diagnostic_players()[0, :, 0].tolist() == [48] + [50] * (players - 1)
        assert s[8] == players
    elif model == 288:
        assert batch.diagnostic_players()[0, :, 4].tolist() == [9] * players
        assert s[9] == players
        assert batch.player_observations()[0, 1:, 2].sum() == 0
    elif model == 289:
        assert batch.confusion_snapshot()[0, :players].tolist() == [3] * players
        assert s[10] == 3 * players
        assert batch.choice_masks()[0].sum() == 1 and batch.choice_masks()[0, 0]
        assert not batch.policy_gradient_masks()[0, 0]
    elif model == 290:
        assert batch.diagnostic_players()[0, :, 0].tolist() == [1] * players
        assert s[11:13].tolist() == [players, 49 * players]
        assert batch.revival_count == batch.hp_damage == batch.guardian_departure_count == 0
    elif model in (291, 292):
        assert s[3:7].tolist() == [1, 1, 0, 0]
        assert s[7] == 50
        assert batch.hp_damage == 50 and batch.attack_count == 0
        assert batch.revival_count == 1
    elif model == 293:
        assert s[13] == 50
        assert batch.diagnostic_players()[0, :, 0].sum() == 50 * players + 50
    elif model == 294:
        assert s[14:17].tolist() == [99 * players, 100, 99 * players - 100]
        assert sorted(batch.diagnostic_players()[0, :, 2]) == [0] * (players - 1) + [100]
    elif model == 295:
        expected = Counter(
            int(row[1]) for row in before[0].reshape(-1, 4) if row[0] and row[1] != 207
        )
        actual = Counter(
            int(row[1]) for row in batch.diagnostic_inventory()[0].reshape(-1, 4) if row[0]
        )
        assert expected == actual
        assert s[17:21].tolist() == [1, 3 * players, 0, 1]
        assert not batch.diagnostic_inventory()[0, :, :, 3].any()
        assert [(batch.diagnostic_inventory()[0, p, :, 0] > 0).sum() for p in range(players)] == [
            3
        ] * players
    else:
        assert s[21] == players
        expected = [
            next_value % 10 + 1
            for _, next_value in zip(
                range(players), tickets(QUIET_SEED, 0, 0x3F84D5B5B5470917), strict=False
            )
        ]
        assert batch.guardian_snapshot()[0, :, 0].tolist() == expected
        assert batch.guardian_summon_count == players and batch.guardian_activation_count == 0


@pytest.mark.parametrize("stage", [0, 1, 2, 3, 4])
def test_afterglow_sets_fever_not_illness_infliction_or_worsening(stage):
    batch = force(287)
    hand(batch, [207, 208])
    load(batch, illness=stage, hp=10)
    load(batch, owner=1, illness=stage, hp=9)
    batch.start_environments(ids([0]))
    cast(batch)
    assert batch.diagnostic_players()[0, :2, 0].tolist() == [8, 9]
    assert batch.diagnostic_players()[0, :2, 3].tolist() == [2, 2]
    assert batch.revival_count == batch.illness_effect_damage == 0


@pytest.mark.parametrize("model", [287, 288, 289, 290, 293, 294, 295, 296])
def test_global_effects_do_not_mutate_or_resurrect_dead_seats(model):
    batch = force(model, players=3)
    hand(batch, [207])
    hand(batch, [(238, 235, 1)], owner=2)
    load(batch, owner=2, hp=0, cp=99, illness=4, mask=15)
    batch.seed_guardians(ids([0]), ids([2]), ids([9]))
    batch.start_environments(ids([0]))
    before = batch.diagnostic_inventory()[0, 2].copy()
    cast(batch)
    drain(batch)
    assert batch.diagnostic_players()[0, 2].tolist() == [0, 20, 99, 4, 15, 0]
    np.testing.assert_array_equal(before, batch.diagnostic_inventory()[0, 2])
    assert batch.guardian_snapshot()[0, 2, 0] == 9


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("model", [291, 292, 293, 294])
def test_target_hit_and_resource_tickets_independent_of_fog(seed, model):
    batch = force(model, seed=seed, players=3)
    hand(batch, [207])
    load(batch, mask=1)
    batch.start_environments(ids([0]))
    cast(batch)
    pool = [1, 2] if model == 292 else [0, 1, 2]
    target = pool[next(tickets(seed, 0, 0x0D95748F728EB658)) % len(pool)]
    if model == 292:
        hit = next(tickets(seed, 0, 0x718BCD5882154AEE)) % 100 < 75
        assert (batch.episode_snapshot()[0, 3] == 4) == hit
        assert batch.phenomenon_snapshot()[0, 5] == int(not hit)
    elif model == 291:
        assert batch.episode_snapshot()[0, 2] == target
    elif model == 293:
        assert batch.diagnostic_players()[0, target, 0] == 100
    else:
        assert batch.diagnostic_players()[0, target, 2] == 15
    drain(batch)


def test_complete_uniform_sampler_keeps_unsupported_solar_guardians_and_rolls_back():
    batch = game(size=512, players=2, seed=67)
    for env in range(512):
        hand(batch, [207, 208], env=env)
        hand(batch, [208], env=env, owner=1)
    batch.start_environments(ids(range(512)))
    observed = set()
    failures = 0
    for env in range(512):
        expected = next(tickets(67, env, 0xA458FEA3F4933D7E)) % 10
        step(batch, [1], [env])
        before = snapshot(batch)
        try:
            step(batch, [0], [env])
        except ValueError as error:
            assert "Earth/Moon guardian producer" in str(error)
            assert expected == 9
            same(before, snapshot(batch))
            failures += 1
            continue
        assert batch.phenomenon_model_counts()[env, expected] == 1
        observed.add(expected)
        drain(batch)
    assert observed == set(range(10)) and failures > 0


def test_mushroom_control_is_added_after_old_forced_turn_is_consumed():
    seed = next(s for s in range(10000) if next(tickets(s, 0, 0xC5D1B023286085F0)) % 3 == 0)
    batch = force(289, seed=seed)
    hand(batch, [207])
    batch.seed_confusion(ids([0]), ids([0]), ids([3]))
    batch.start_environments(ids([0]))
    before_mask = batch.policy_gradient_masks()
    assert not before_mask[0, 0]
    step(batch, [0])
    assert batch.confusion_snapshot()[0, :3].tolist() == [5, 3, 3]
    assert batch.confusion_snapshot()[0, 9:].tolist() == [1, 1, 1, 0, 0, 0, 0, 1]
    assert not before_mask.flags.writeable and not before_mask[0, 0]


@pytest.mark.parametrize("model", [35, 94, 112, 181, 235, 196, 200])
def test_forced_turn_uses_native_actual_single_plays_or_discard_without_selection_loops(model):
    batch = game(seed=67)
    hand(batch, [model])
    load(batch, hp=40, mask=15, illness=1)
    batch.seed_confusion(ids([0]), ids([0]), ids([3]))
    batch.start_environments(ids([0]))
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]
    with pytest.raises(ValueError):
        step(batch, [1])
    before = batch.policy_gradient_masks()
    step(batch, [0])
    if batch.episode_snapshot()[0, 3] == 4:
        assert batch.policy_gradient_masks()[0, 0]  # Defensive decisions remain voluntary.
    drain(batch)
    assert not before[0, 0]
    assert batch.confusion_snapshot()[0, 0] == 2
    assert batch.confusion_snapshot()[0, 9] == 1
    assert batch.episode_snapshot()[0, 4] == 1
    assert batch.attack_toggle_count == batch.attack_confirm_count == 0


@pytest.mark.parametrize("model", [3, 4, 5])
def test_forced_controller_never_hides_unimplemented_trades(model):
    seed = next(s for s in range(10000) if next(tickets(s, 0, 0xC5D1B023286085F0)) % 3 == 0)
    batch = game(seed=seed)
    hand(batch, [model])
    batch.seed_confusion(ids([0]), ids([0]), ids([3]))
    batch.start_environments(ids([0]))
    before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [0])
    same(before, snapshot(batch))


def test_fog_hides_other_control_counts_not_own_forced_mask_or_defense_eligibility():
    batch = game()
    load(batch, mask=1)
    batch.seed_confusion(ids([0, 0]), ids([0, 1]), ids([3, 10]))
    batch.start_environments(ids([0]))
    view = batch.control_observations()[0]
    assert view[0].tolist() == [0, 1, 1, 3]
    assert view[1].tolist() == [1, 1, 0, 0]
    assert not batch.policy_gradient_masks()[0, 0]
    step(batch, [0])
    assert batch.confusion_snapshot()[0, :2].tolist() == [2, 10]


@pytest.mark.parametrize("bad", [-1, 1_000_000_001])
def test_setup_count_rejects_whole_batch(bad):
    batch = game(size=2)
    before = snapshot(batch)
    with pytest.raises(ValueError):
        batch.seed_confusion(ids([0, 1]), ids([0, 0]), ids([3, bad]))
    same(before, snapshot(batch))


def test_reset_views_lifetimes_and_closed_setup():
    batch = force(289)
    hand(batch, [207])
    batch.start_environments(ids([0]))
    cast(batch)
    old = snapshot(batch)
    copies = tuple(a.copy() for a in old)
    for a in old:
        assert not a.flags.writeable
    with pytest.raises(ValueError):
        batch.seed_confusion(ids([0]), ids([0]), ids([0]))
    batch.reset_environments(ids([0]))
    assert not batch.confusion_snapshot().any()
    assert not batch.phenomenon_snapshot().any()
    assert not batch.policy_gradient_masks().any()
    same(old, copies)


@pytest.mark.parametrize("model", [287, 288, 289, 290, 293, 294, 295])
def test_late_stale_row_rolls_back_whole_world_effect_and_random_streams(model):
    batch, reference = force(model, size=2), force(model, size=2)
    for b in (batch, reference):
        for env in (0, 1):
            hand(b, [207, (238, 235, 1)], env=env)
        b.start_environments(ids([0, 1]))
        step(b, [1, 1])
    before = snapshot(batch)
    rows = batch.episode_snapshot()
    with pytest.raises(ValueError):
        batch.step(ids([[0, *rows[0, :4], 0], [1, rows[1, 0], 999, *rows[1, 2:4], 0]]))
    same(before, snapshot(batch))
    step(batch, [0, 0])
    step(reference, [0, 0])
    same(snapshot(batch), snapshot(reference))


@pytest.mark.parametrize(
    "profiles",
    [
        (),
        ((286, 1, 2, 0, 100),),
        ((287, 2, 2, 0, 100),),
        ((287, 1, 3, 0, 100),),
        ((291, 5, 50, 0, 100),),
        ((292, 6, 30, 6, 0),),
        ((288, 2, 1, 0, 75),),
        ((287, 1, 2, 0, 100), (287, 1, 2, 0, 100)),
    ],
)
def test_raw_profile_invalid_or_duplicate(profiles):
    with pytest.raises(ValueError):
        game(profiles=profiles)


@pytest.mark.parametrize(
    "field,value",
    [
        ("full_game_training_ready", True),
        ("promotion_eligible", True),
        ("official_fidelity_verified", True),
        ("profile_fields", ()),
        ("fate_model_ids", ()),
        ("profiles", ((287, True, 2, 0, 100),)),
    ],
)
def test_source_plan_fails_closed(field, value):
    payload = PLAN.phenomena.model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        FullGamePhenomenonPlan.model_validate(payload)


@pytest.mark.parametrize("field", ["detail", "asset", "image_path", "element_image_paths"])
def test_complete_bible_contract_drift(field):
    payload = BibleSnapshot.model_validate_json(BIBLE.read_text()).model_dump()
    payload["catalog"]["phenomena"]["items"][0][field] = (
        ["wrong"] if field in ("detail", "element_image_paths") else "wrong"
    )
    with pytest.raises(ValueError):
        build_full_game_phenomenon_plan(
            read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate(payload)
        )


def test_adapter_exposes_native_control_but_not_full_training_readiness():
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=18
    )
    assert configured.metadata.kernel_schema_version == 32
    assert configured.metadata.attack_family_schema_version == 8
    assert configured.metadata.plan.integrated_artifact_effect_count == 237
    assert not configured.metadata.full_game_training_ready
    assert not configured.metadata.action_observation_checkpoint_compatible


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("seed", range(12))
def test_shuffle_matches_independent_model_and_disguise_streams(players, seed):
    batch = force(295, players=players, seed=seed)
    hand(batch, [207, (127, 142, 0), (238, 235, 1), 208])
    expected_models = [127, 238, 208]
    for owner in range(1, players):
        values = [6 + owner, 237, 208] + ([238] if owner % 2 == 0 else [])
        hand(batch, values, owner=owner)
        expected_models.extend(values)
    for owner in range(players):
        load(batch, owner=owner, mask=2 if owner % 2 == 0 else 0)
    original = batch.diagnostic_inventory()[0]
    first_new_id = int(original[..., 0].max()) + 1
    batch.start_environments(ids([0]))
    cast(batch)
    rng = tickets(seed, 0, 0x7B54A41DC25A59B5)
    for i in range(len(expected_models) - 1):
        j = i + next(rng) % (len(expected_models) - i)
        expected_models[i], expected_models[j] = expected_models[j], expected_models[i]
    categories = dict(PLAN.inventory.profiles)
    pools = {c: [m for m, k in PLAN.inventory.profiles if c == k] for c in range(1, 6)}
    fake_rng = tickets(seed, 0, 0x9C30D5392AF26013)
    cursor = 0
    for owner in range(players):
        count = int(np.count_nonzero(original[owner, :, 0])) - (owner == 0)
        for slot in range(count):
            model = expected_models[cursor]
            fake = 0
            if owner % 2 == 0 and next(fake_rng) % 100 < 50:
                pool = pools[categories[model]]
                fake = pool[next(fake_rng) % len(pool)]
            assert batch.diagnostic_inventory()[0, owner, slot].tolist() == [
                first_new_id + cursor,
                model,
                fake,
                0,
            ]
            cursor += 1
    assert cursor == len(expected_models)


def test_reflection_reveals_phenomenon_and_preserves_original_turn_after_utility():
    seed = next(s for s in range(1000) if next(tickets(s, 0, 0x0D95748F728EB658)) % 2 == 1)
    batch = force(291, players=2, seed=seed)
    hand(batch, [207, 208])
    hand(batch, [190, 165], owner=1)
    batch.start_environments(ids([0]))
    cast(batch)
    assert batch.phenomenon_observations()[0].tolist() == [1, 291, 0, 1]
    assert batch.pending_observations()[0, :6].tolist() == [1, 0, 1, 50, 5, 5]
    assert batch.choice_masks()[0, 1] and not batch.choice_masks()[0, 2]
    step(batch, [1])
    step(batch, [0])
    assert batch.phenomenon_observations()[0].tolist() == [1, 291, 1, 0]
    assert batch.pending_observations()[0, 1] == 0
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [10, 50]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert batch.phenomenon_snapshot()[0, 7] == 50
    assert batch.revival_count == batch.reflection_count == 1


@pytest.mark.parametrize("sun", [False, True])
def test_final_death_clears_control_but_sun_retains_remaining_turns(sun):
    batch = game()
    load(batch, hp=1, illness=1)
    if sun:
        hand(batch, [208])
    batch.seed_confusion(ids([0]), ids([0]), ids([3]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.confusion_snapshot()[0, 0] == (2 if sun else 0)
    assert batch.revival_count == int(sun)
    assert batch.diagnostic_players()[0, 0, 0] == (10 if sun else 0)


def test_adapter_policy_weights_are_captured_before_step_without_mutating_state():
    from godfield_bot.full_game import (
        execute_full_game_commands,
        full_game_decision_contexts,
        full_game_policy_gradient_weights,
    )
    from godfield_bot.full_game_protocol import FullGameCommand, FullGameCommandError

    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=2, capacity=18
    )
    batch = configured.batch
    batch.seed_confusion(ids([1]), ids([0]), ids([1]))
    batch.start_environments(ids([0, 1]))
    contexts = full_game_decision_contexts(configured)
    commands = [
        FullGameCommand(**contexts[e].model_dump(exclude={"legal_choice_ids"}), choice_id=0)
        for e in (1, 0)
    ]
    before = snapshot(batch)
    weights = full_game_policy_gradient_weights(configured, commands)
    assert weights.tolist() == [0.0, 1.0] and weights.dtype == np.float32
    assert not weights.flags.writeable
    same(before, snapshot(batch))
    with pytest.raises(FullGameCommandError):
        full_game_policy_gradient_weights(configured, [commands[0], commands[0]])
    execute_full_game_commands(configured, commands)
    assert batch.confusion_snapshot()[1, 0] == 0
    assert weights.tolist() == [0.0, 1.0]
