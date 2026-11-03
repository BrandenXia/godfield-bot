"""Versioned counter families, source-pinned filters and provisional payments."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import FullGameMetadata, build_full_game_plan
from godfield_bot.full_game_combat_plan import FullGameCombatPlan
from godfield_bot.full_game_roles import build_full_game_role_manifest

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(Path("data/snapshots/2026-10-01/api-catalog-en.json")),
    BibleSnapshot.model_validate_json(Path("data/snapshots/2026-09-20/bible.json").read_text()),
)
DEFENSES = PLAN.combat.defense_effect_profiles
ARMOR = {row[0]: row[1] for row in PLAN.combat.armor_profiles}


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=1, players=3, seed=67, refill=False, max_decisions=4000, effects=DEFENSES):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        seed=seed,
        initial_hp=100,
        initial_mp=30,
        initial_cp=3,
        max_decisions=max_decisions,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(effects).reshape(-1, 5),
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, cards, *, owner=0, env=0):
    batch.seed_hand(
        env,
        owner,
        ids([(owner * 100 + index + 1, model, 0, 0) for index, model in enumerate(cards)]).reshape(
            -1, 4
        ),
    )


def load(batch, *, owner=0, env=0, hp=100, mp=30, cp=3, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    episodes = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def begin(batch, *, size=1, attack=35, response=(), source_response=(), cloud=True):
    for env in range(size):
        seed(batch, [attack, *source_response], env=env)
        seed(batch, response, env=env, owner=1)
        if cloud:
            load(batch, env=env, mask=8)
    batch.start_environments(ids(range(size)))
    for choice in (1, 0, 20):
        step(batch, [choice] * size)


def snapshot(batch):
    views = (
        "episode_snapshot",
        "diagnostic_players",
        "diagnostic_inventory",
        "actor_hands",
        "player_observations",
        "choice_masks",
        "pending_observations",
        "defense_order",
        "counter_observations",
        "counter_snapshot",
        "selected_defenses",
        "attack_order",
        "attack_effect_snapshot",
        "chance_snapshot",
        "acquisition_snapshot",
    )
    props = (
        "action_count",
        "hp_damage",
        "counter_count",
        "resolved_counter_count",
        "counter_miss_count",
        "suppressed_counter_count",
        "filtered_attack_count",
        "self_curse_count",
        "consumed_count",
        "automatic_gift_count",
        "mp_spent",
        "inflicted_curse_count",
        "inflicted_illness_count",
    )
    return [getattr(batch, name)() for name in views], [getattr(batch, name) for name in props]


def unchanged(before, after):
    assert before[1] == after[1]
    for left, right in zip(before[0], after[0], strict=True):
        np.testing.assert_array_equal(left, right)


@pytest.mark.parametrize("model,kind,value,element,rate", DEFENSES[1:9])
def test_every_ring_joins_one_response_family(model, kind, value, element, rate):
    batch = game(refill=True)
    begin(batch, response=[model])
    step(batch, [1])
    step(batch, [0])
    target = 1 if kind == 3 else 0
    assert batch.counter_observations()[0].tolist() == [1, kind, 1, target, 10, rate]
    assert batch.pending_observations()[0, 4:6].tolist() == [element, 2]
    assert batch.chance_observations()[0].tolist() == [0, 0, 0, 0]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [0, 0, 0]
    assert batch.automatic_gift_count == 0
    assert batch.counter_snapshot()[0, :3].tolist() == [1, 1, 0]
    step(batch, [0])
    states = batch.diagnostic_players()[0]
    assert states[1, 0] == 90
    if kind == 1:
        assert states[0, 0] == 100 - 10 * value
    elif kind == 2:
        assert states[0, 4] == 8 | value
    elif kind == 3:
        assert states[1, 1] == 50
    else:
        assert states[0, :3].tolist() == [100, 23, 0]
        assert states[1, 2] == 13
    assert batch.counter_snapshot()[0, :5].tolist() == [1, 1, 1, 0, 0]
    assert batch.attack_count == batch.resolved_attack_count == batch.resolved_counter_count == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.automatic_gift_count == batch.consumed_count == 2


@pytest.mark.parametrize(
    "cp,mp,hp,expected,credit,spill",
    [
        (20, 30, 100, (100, 30, 10), 10, 0),
        (3, 30, 100, (100, 23, 0), 10, 0),
        (3, 2, 100, (95, 0, 0), 10, 5),
        (0, 0, 4, (0, 0, 0), 10, 4),
    ],
)
def test_venus_shared_payment_waterfall_credits_requested_not_available(
    cp, mp, hp, expected, credit, spill
):
    batch = game(players=2)
    begin(batch, response=[188])
    # Reloading after start is disallowed, so configure a fresh episode.
    batch.reset_environments(ids([0]))
    load(batch, cp=cp, mp=mp, hp=hp)
    begin(batch, response=[188], cloud=False)
    for choice in (1, 0, 0):
        step(batch, [choice])
    assert tuple(batch.diagnostic_players()[0, 0, :3]) == expected
    assert batch.diagnostic_players()[0, 1, 2] == 3 + credit
    assert batch.counter_snapshot()[0, 7:9].tolist() == [credit, spill]
    assert batch.hp_damage == 10  # CP spill is separate from attack HP damage.
    if hp == 4:
        assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]


@pytest.mark.parametrize("model,resource", [(187, 1), (188, 2)])
def test_counter_resource_credits_obey_explicit_local_cap(model, resource):
    batch = game()
    load(batch, owner=1, mp=95, cp=95)
    begin(batch, response=[model])
    for choice in (1, 0, 0):
        step(batch, [choice])
    assert batch.diagnostic_players()[0, 1, resource] == 100
    assert batch.counter_snapshot()[0, 6 if model == 187 else 7] == 5


@pytest.mark.parametrize("model", [181, 182, 183, 184, 185, 186, 187, 188])
@pytest.mark.parametrize("defense,hp", [(37, 100), (None, 5)])
def test_zero_loss_or_dead_defender_cannot_counter(model, defense, hp):
    batch = game()
    load(batch, owner=1, hp=hp)
    begin(batch, response=[model, *([] if defense is None else [defense])])
    step(batch, [1])
    if defense:
        step(batch, [2])
    step(batch, [0])
    assert batch.counter_count == 0
    assert batch.episode_snapshot()[0, 4] == 1
    assert batch.suppressed_counter_count == (1 if defense is None else 0)


def test_click_order_depth_first_original_owner_ticks_and_gifts_once():
    batch = game(refill=True)
    begin(batch, response=[184, 182, 188], source_response=[189, 184])
    for choice in (2, 1, 3):
        step(batch, [choice])
    assert batch.defense_order()[0, :2].tolist() == [2, 1]
    step(batch, [0])  # Mercury first despite its higher held slot.
    assert batch.counter_observations()[0, 1] == 2
    step(batch, [0])  # Saturn sibling.
    assert batch.counter_observations()[0, :5].tolist() == [1, 1, 1, 0, 10]
    step(batch, [1])  # Filter Stone counter before selecting own Stone ring.
    step(batch, [2])
    step(batch, [0])  # Nested Saturn, based on 20 HP loss.
    assert batch.counter_observations()[0, :5].tolist() == [1, 1, 0, 1, 20]
    assert batch.automatic_gift_count == 0
    assert batch.diagnostic_players()[0, :, 5].tolist() == [0, 0, 0]
    step(batch, [0])
    assert batch.counter_observations()[0, 1] == 4  # Nested attack preceded Venus sibling.
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [80, 50, 100]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.counter_snapshot()[0, :6].tolist() == [4, 4, 4, 0, 0, 60]
    assert batch.automatic_gift_count == 6


def test_dead_queued_target_suppresses_later_reaction_without_posthumous_credit():
    batch = game(players=2)
    load(batch, hp=15)
    begin(batch, response=[184, 188], cloud=False)
    for choice in (1, 2, 0, 0):
        step(batch, [choice])
    assert batch.counter_snapshot()[0, :5].tolist() == [2, 1, 1, 0, 1]
    assert batch.diagnostic_players()[0, 1, 2] == 3
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]


@pytest.mark.parametrize("model", [182, 184, 187, 188])
def test_armor_origin_only_super_mirror_can_redirect_counter(model):
    batch = game()
    begin(batch, response=[model], source_response=[39, 42, 233, 190])
    for choice in (1, 0):
        step(batch, [choice])
    if model == 187:
        # Self MP benefit has no defense in this hand. Other assertions use enemy counters.
        step(batch, [0])
        return
    assert not any(batch.choice_masks()[0, 1:4])
    assert batch.choice_masks()[0, 4]
    for choice in (4, 0):
        step(batch, [choice])
    assert batch.counter_observations()[0, 2:4].tolist() == [0, 1]
    assert batch.episode_snapshot()[0, 4] == 0
    step(batch, [0])
    assert batch.resolved_counter_count == 1 and batch.reflection_count == 1
    if model == 188:
        assert batch.diagnostic_players()[0, 0, 2] == 13


@pytest.mark.parametrize("attack", [82, 85, 84])
def test_filter_prefix_clears_element_and_can_precede_numeric_or_special(attack):
    batch = game()
    begin(batch, attack=attack, response=[189, 37, 190])
    assert not batch.choice_masks()[0, 2]  # NE numeric armor incompatible before filtering.
    step(batch, [1])
    assert batch.pending_observations()[0, 4] == 0
    assert batch.choice_masks()[0, 2] and batch.choice_masks()[0, 3]
    step(batch, [2])
    assert not batch.choice_masks()[0, 3]
    step(batch, [0])
    assert batch.filtered_attack_count == 1
    assert batch.darkness_finish_count == 0


def test_filter_then_weapon_wall_blocks_previously_elemental_weapon():
    batch = game()
    begin(batch, attack=82, response=[189, 233])
    assert not batch.choice_masks()[0, 2]
    for choice in (1, 2):
        step(batch, [choice])
    assert batch.special_defense_observations()[0, 3:5].tolist() == [1, 6]
    step(batch, [0])
    assert batch.block_count == batch.filtered_attack_count == 1
    assert batch.hp_damage == 0 and batch.mp_spent == 6


def test_filter_removal_rebuilds_compatible_suffix_and_forbids_late_filter():
    batch = game()
    begin(batch, attack=82, response=[189, 37, 189, 132])
    for choice in (1, 3, 2):
        step(batch, [choice])
    step(batch, [1])
    assert batch.defense_order()[0, :2].tolist() == [3, 2]
    step(batch, [3])
    assert not batch.selected_defenses().any()
    assert batch.pending_observations()[0, 4] == 1
    step(batch, [4])  # Water armor compatible with Fire without filter.
    assert not batch.choice_masks()[0, 1] and not batch.choice_masks()[0, 3]


def test_filter_prevents_darkness_finish_even_without_numeric_defense():
    batch = game()
    begin(batch, attack=92, response=[189])
    for choice in (1, 0):
        step(batch, [choice])
    attack = next(row[1] for row in PLAN.combat.attack_profiles if row[0] == 92)
    assert batch.diagnostic_players()[0, 1, 0] == 100 - attack
    assert batch.darkness_finish_count == 0


@pytest.mark.parametrize(
    "attack,illness,expected_stage,expected_hp",
    [
        (35, 0, 2, 100),
        (33, 0, 2, 100),
        (48, 0, 2, 97),
        (35, 1, 2, 100),
        (35, 2, 3, 100),
        (35, 4, 4, 0),
    ],
)
def test_fever_after_incoming_effects_no_defender_periodic_tick(
    attack, illness, expected_stage, expected_hp
):
    batch = game()
    load(batch, owner=1, illness=illness)
    begin(batch, attack=attack, response=[168])
    for choice in (1, 0):
        step(batch, [choice])
    state = batch.diagnostic_players()[0, 1]
    assert state[0] == expected_hp and state[3] == expected_stage and state[5] == 0
    assert batch.self_curse_count == 1
    assert batch.inflicted_illness_count == (2 if attack == 48 else 1)


@pytest.mark.parametrize("model", [11, 17, 20, 24, 37, 49, 77])
def test_effect_free_dual_weapons_have_both_executable_roles(model):
    batch = game()
    begin(batch, attack=model, response=[model])
    assert batch.choice_masks()[0, 1] == (model != 77)  # Fire cannot defend Fire.
    if model != 77:
        step(batch, [1])
    step(batch, [0])
    expected = next(row[1] for row in PLAN.combat.attack_profiles if row[0] == model)
    assert batch.hp_damage == max(0, expected - (ARMOR[model] if model != 77 else 0))


def test_counter_decision_limit_is_explicit_truncation_no_tick_or_gifts():
    batch = game(refill=True, max_decisions=5)
    begin(batch, response=[184])
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.episode_snapshot()[0, 3:7].tolist() == [13, 0, 4, -1]
    assert batch.resolved_attack_count == 1 and batch.resolved_counter_count == 0
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 2


def test_late_hidden_failure_rolls_back_counter_queue_payments_and_randomness():
    batch = game(size=2, refill=True)
    begin(batch, size=2, response=[188, 184])
    for choice in (1, 2, 0):
        step(batch, [choice, choice])
    # Counter responder's apparent Super Mirror is actually an unsupported hat.
    # Set this in a fresh deterministic batch before startup.
    reference = game(size=2, refill=True)
    for env in range(2):
        load(reference, env=env, mask=8)
        seed(reference, [35], env=env)
        seed(reference, [188, 184], env=env, owner=1)
    reference.seed_hand(1, 0, ids([[1, 35, 0, 0], [2, 178, 190, 0]]))
    reference.start_environments(ids([0, 1]))
    for choice in (1, 0, 20, 1, 2, 0):
        step(reference, [choice, choice])
    step(reference, [1], [1])
    before = snapshot(reference)
    with pytest.raises(ValueError, match="not implemented"):
        step(reference, [0, 0])
    unchanged(before, snapshot(reference))
    # Remove the apparent mirror; identical environment zero now resolves identically.
    step(reference, [1], [1])
    step(reference, [0, 0])
    step(batch, [0, 0])
    np.testing.assert_array_equal(reference.counter_snapshot()[0], batch.counter_snapshot()[0])
    np.testing.assert_array_equal(reference.diagnostic_players()[0], batch.diagnostic_players()[0])


def test_counter_views_owned_read_only_reset_queue_and_episode_not_lifetime_metrics():
    batch = game()
    begin(batch, response=[184, 188])
    for choice in (1, 2, 0):
        step(batch, [choice])
    previous = batch.counter_snapshot()
    assert not previous.flags.writeable and previous[0, 11] == 1
    assert not batch.counter_observations().flags.writeable
    assert not batch.defense_order().flags.writeable
    batch.reset_environments(ids([0]))
    assert not batch.counter_snapshot().any() and not batch.counter_observations().any()
    assert previous[0, 11] == 1 and batch.counter_count == 1


def rank(env, *, epoch=1):
    mask = (1 << 64) - 1
    state = (
        67
        ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
        ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
        ^ 0x8F43C615B2EA970D
    )
    for _ in range(16):
        state = (state + 0x9E3779B97F4A7C15) & mask
        word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
        word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
        word ^= word >> 31
        if word >= (1 << 64) % 100:
            return word % 100
    raise AssertionError("reference rejection limit")


@pytest.mark.parametrize("epoch", [1, 2])
def test_mars_separate_rng_matches_independent_model_and_resets_by_epoch(epoch):
    batch = game(size=128, refill=True)
    if epoch == 2:
        batch.reset_environments(ids(range(128)))
    begin(batch, size=128, response=[181], cloud=False)
    for choice in (1, 0):
        step(batch, [choice] * 128)
    expected = np.asarray([rank(env, epoch=epoch) < 75 for env in range(128)])
    np.testing.assert_array_equal(batch.counter_observations()[:, 0], expected)
    assert batch.counter_count == 128 and batch.counter_miss_count == int((~expected).sum())
    assert batch.chance_count == 0
    hits = np.flatnonzero(expected)
    step(batch, [0] * len(hits), hits)
    assert batch.resolved_counter_count == 128 and batch.automatic_gift_count == 256
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)


def test_cloud_guaranteed_mars_hit_skips_ticket_for_later_noncloud_counter():
    batch = game(size=128)
    begin(batch, size=128, response=[181, 190], source_response=[190, 189, 181])
    for choice in (1, 0, 1, 0, 1, 0):
        step(batch, [choice] * 128)
    assert batch.reflection_count == 256 and batch.counter_miss_count == 0
    assert np.all(batch.counter_observations()[:, 2:4] == [1, 0])
    for choice in (1, 2, 0):
        step(batch, [choice] * 128)  # Filter Fire to NE, then counter with own Fire ring.
    expected = np.asarray([rank(env) < 75 for env in range(128)])
    np.testing.assert_array_equal(batch.counter_observations()[:, 0], expected)
    assert batch.counter_count == 256 and batch.counter_miss_count == int((~expected).sum())
    hits = np.flatnonzero(expected)
    assert np.all(batch.counter_observations()[hits, 2:4] == [0, 1])
    step(batch, [0] * len(hits), hits)
    assert batch.resolved_counter_count == 256 and batch.chance_count == 0
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)


def test_venus_self_transfer_after_root_self_bounce_is_noop():
    batch = game(size=128)
    begin(batch, size=128, response=[21], source_response=[188], cloud=False)
    for choice in (1, 0):
        step(batch, [choice] * 128)
    self_targets = np.flatnonzero(batch.episode_snapshot()[:, 2] == 0)
    assert len(self_targets)
    for choice in (1, 0):
        step(batch, [choice] * len(self_targets), self_targets)
    assert np.all(batch.counter_observations()[self_targets, 2:4] == [0, 0])
    step(batch, [0] * len(self_targets), self_targets)
    assert np.all(batch.diagnostic_players()[self_targets, 0, :3] == [90, 30, 3])
    assert not batch.counter_snapshot()[self_targets, 7:9].any()


@pytest.mark.parametrize(
    "true_cards,display_cards", [([130, 189], [189, 130]), ([189, 130], [130, 189])]
)
def test_hidden_filter_order_errors_are_atomic(true_cards, display_cards):
    batch = game()
    seed(batch, [35])
    batch.seed_hand(
        0,
        1,
        ids(
            [
                (100 + i, true, display, 0)
                for i, (true, display) in enumerate(zip(true_cards, display_cards, strict=True))
            ]
        ),
    )
    batch.start_environments(ids([0]))
    for choice in (1, 0, 20):
        step(batch, [choice])
    for choice in [1, 2] if display_cards[0] == 189 else [2, 1]:
        step(batch, [choice])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="filter must precede"):
        step(batch, [0])
    unchanged(before, snapshot(batch))


def test_flash_limits_filter_prefix_and_undo_restores_first_choice():
    batch = game()
    load(batch, owner=1, mask=4)
    begin(batch, attack=82, response=[189, 37])
    step(batch, [1])
    assert not batch.choice_masks()[0, 2] and batch.choice_masks()[0, 1]
    step(batch, [1])
    assert batch.choice_masks()[0, 1]


@pytest.mark.parametrize(
    "row,column,value", [(0, 1, 0), (1, 2, 3), (2, 2, 16), (8, 3, 1), (9, 4, 75)]
)
def test_malformed_native_defense_profiles_rejected(row, column, value):
    profiles = ids(DEFENSES)
    profiles[row, column] = value
    with pytest.raises(ValueError, match="defense effect profile"):
        game(effects=profiles)


def test_pinned_new_profiles_and_readiness_remain_fail_closed():
    assert len(PLAN.combat.attack_profiles) == 99 and len(PLAN.combat.armor_profiles) == 81
    assert len(DEFENSES) == 10 and PLAN.integrated_artifact_effect_count == 237
    assert not PLAN.local_training_eligible and not PLAN.full_game_training_ready
    for key, value in (
        ("defense_effect_kinds", ("x",)),
        ("defense_effect_fields", ("x",)),
        ("defense_effect_profiles", (*DEFENSES[:-1], (189, 5, 1, 0, 100))),
    ):
        with pytest.raises(ValidationError):
            FullGameCombatPlan.model_validate(PLAN.combat.model_dump() | {key: value})
    metadata = FullGameMetadata(
        roles=build_full_game_role_manifest(PLAN),
        resource_cap=100,
        plan=PLAN,
        batch_size=1,
        player_count=3,
        capacity=18,
        hand_limit=18,
        seed=67,
        max_turns=1000,
        max_decisions=4000,
        initial_hp=100,
        initial_mp=30,
        initial_cp=3,
    )
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(metadata.model_dump() | {"counter_snapshot_fields": ("x",)})
    assert not metadata.promotion_eligible and not metadata.official_fidelity_verified
