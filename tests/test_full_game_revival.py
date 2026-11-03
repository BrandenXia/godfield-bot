"""Passive owned-item lifecycle in joined transactions, not manual resurrection."""

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
from godfield_bot.full_game_passives import FullGamePassivePlan, build_full_game_passive_plan

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
    max_turns=1000,
    max_decisions=4000,
    passives=PLAN.passives.profiles,
):
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
        max_turns=max_turns,
        max_decisions=max_decisions,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        chance_profiles=ids(PLAN.combat.chance_profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        passive_profiles=ids(passives).reshape(-1, 2) if passives is not None else None,
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, models, *, env=0, owner=0):
    batch.seed_hand(
        env,
        owner,
        ids([(owner * 100 + index + 1, model, 0, 0) for index, model in enumerate(models)]).reshape(
            -1, 4
        ),
    )


def load(batch, *, env=0, owner=0, hp=100, mp=30, cp=3, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, cp, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    episodes = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids(
            [[env, *episodes[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def start_attack(batch, *, size=1):
    batch.start_environments(ids(range(size)))
    for choice in (1, 0, 20):
        step(batch, [choice] * size)


def hand(batch, *, owner=1, env=0):
    rows = batch.diagnostic_inventory()[env, owner]
    return rows[rows[:, 0] != 0]


def rank(env=0, *, seed=67, epoch=1):
    # Independent first-ticket SplitMix model for owner illness, no caller RNG.
    mask = (1 << 64) - 1
    state = seed ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
    state ^= (epoch * 0xBF58476D1CE4E5B9) & mask
    state = (state + 0x9E3779B97F4A7C15) & mask
    word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
    word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
    return (word ^ (word >> 31)) % 100


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
        "passive_observations",
        "revival_snapshot",
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
        "suppressed_counter_count",
        "consumed_count",
        "automatic_gift_count",
        "suppressed_gift_count",
        "mp_spent",
        "inflicted_illness_count",
        "revival_count",
        "revived_hp",
        "overflow_count",
        "absorbed_hp",
    )
    return [getattr(batch, name)() for name in views], [getattr(batch, name) for name in props]


def same(left, right):
    assert left[1] == right[1]
    for before, after in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(before, after)


@pytest.mark.parametrize("model,hp", [(35, 5), (35, 10), (64, 100), (92, 20)])
def test_lethal_attack_revives_before_outcomes_retaining_non_hp_state(model, hp):
    batch = game(players=2)
    seed(batch, [model])
    seed(batch, [191, 208, 194, 208], owner=1)
    load(batch, owner=1, hp=hp, mp=23, cp=7, illness=4, mask=2)
    start_attack(batch)
    step(batch, [0])
    assert batch.diagnostic_players()[0, 1].tolist() == [10, 23, 7, 4, 2, 0]
    assert hand(batch).tolist() == [[101, 191, 0, 0], [103, 194, 0, 0], [104, 208, 0, 0]]
    assert batch.revival_snapshot()[0].tolist() == [1, 10, 1, 0, 0, 0, 0, 0, 0, 0]
    assert batch.revival_count == 1 and batch.revived_hp == 10
    assert batch.episode_snapshot()[0, 3:7].tolist() == [1, 1, 0, -1]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert batch.consumed_count == 2  # Attack plus exactly one Amulet.


@pytest.mark.parametrize("hp,armor,expected_hp", [(11, None, 1), (5, 37, 5)])
def test_nonlethal_or_fully_blocked_damage_does_not_consume_passive(hp, armor, expected_hp):
    batch = game()
    seed(batch, [35])
    seed(batch, [208, *([armor] if armor else [])], owner=1)
    load(batch, owner=1, hp=hp)
    start_attack(batch)
    if armor:
        step(batch, [2])
    step(batch, [0])
    assert batch.revival_count == 0 and not batch.revival_snapshot().any()
    assert hand(batch)[0, 1] == 208
    assert batch.diagnostic_players()[0, 1, 0] == expected_hp


@pytest.mark.parametrize("model", [219, 220])
def test_infliction_onto_heaven_revives_without_curing_illness(model):
    batch = game(players=2)
    seed(batch, [model])
    seed(batch, [208, 191], owner=1)
    load(batch, owner=1, hp=9, illness=4)
    start_attack(batch)
    step(batch, [0])
    assert batch.diagnostic_players()[0, 1, [0, 3, 5]].tolist() == [10, 4, 0]
    assert batch.revival_snapshot()[0].tolist() == [1, 10, 0, 1, 0, 0, 0, 0, 0, 0]
    assert batch.hp_damage == 0 and batch.illness_effect_damage == 9
    assert hand(batch)[0, 1] == 191


@pytest.mark.parametrize("copies,expected_hp,revivals", [(1, 0, 1), (2, 10, 2), (3, 10, 2)])
def test_separate_zero_edges_in_one_command_consume_separate_copies(copies, expected_hp, revivals):
    batch = game(players=2)
    seed(batch, [30])  # HP damage then illness infliction.
    seed(batch, [208] * copies, owner=1)
    load(batch, owner=1, hp=2, illness=4)
    start_attack(batch)
    step(batch, [0])
    assert batch.diagnostic_players()[0, 1, 0] == expected_hp
    assert batch.revival_snapshot()[0].tolist() == [
        revivals,
        10 * revivals,
        1,
        revivals - 1,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert batch.illness_effect_damage == 10
    assert len(hand(batch)) == copies - revivals
    assert batch.episode_snapshot()[0, 3] == (12 if copies == 1 else 1)


@pytest.mark.parametrize(
    "cp,mp,hp,expected_hp,revivals",
    [(0, 0, 4, 10, 1), (3, 2, 5, 10, 1), (3, 2, 6, 1, 0), (10, 0, 4, 4, 0)],
)
def test_shared_payment_spill_revives_without_resetting_or_reversing_credit(
    cp, mp, hp, expected_hp, revivals
):
    batch = game(players=2)
    load(batch, hp=hp, cp=cp, mp=mp)
    seed(batch, [35, 208])
    seed(batch, [188], owner=1)
    start_attack(batch)
    for choice in (1, 0, 0):
        step(batch, [choice])
    assert batch.diagnostic_players()[0, 0, :3].tolist() == [expected_hp, 0, 0]
    assert batch.diagnostic_players()[0, 1, :3].tolist() == [90, 30, 13]
    assert batch.revival_snapshot()[0].tolist() == [
        revivals,
        10 * revivals,
        0,
        0,
        revivals,
        0,
        0,
        0,
        0,
        0,
    ]
    assert batch.counter_snapshot()[0, 7:9].tolist() == [10, min(hp, max(0, 10 - cp - mp))]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]


@pytest.mark.parametrize("stage,hp", [(1, 1), (2, 1), (2, 2), (3, 1), (3, 5)])
def test_periodic_illness_revives_once_and_keeps_native_worsening_ticket(stage, hp):
    batch = game()
    seed(batch, [208, 191, 208])
    load(batch, hp=hp, illness=stage)
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.diagnostic_players()[0, 0, [0, 3, 5]].tolist() == [10, stage + (rank() < 5), 1]
    assert batch.revival_snapshot()[0].tolist() == [1, 10, 0, 0, 0, 1, 0, 0, 0, 0]
    assert hand(batch, owner=0).tolist() == [[2, 191, 0, 0], [3, 208, 0, 0]]


def test_native_heaven_worsening_ticket_can_revive_and_repeats_with_reset_epoch():
    batch = game(size=256)
    for epoch in (1, 2):
        for env in range(256):
            seed(batch, [208, 208], env=env)
            load(batch, env=env, hp=6, illness=4)
        batch.start_environments(ids(range(256)))
        step(batch, [0] * 256)
        expected = np.asarray([rank(env, epoch=epoch) < 5 for env in range(256)])
        assert expected.any()
        np.testing.assert_array_equal(
            batch.diagnostic_players()[:, 0, 0], np.where(expected, 10, 11)
        )
        np.testing.assert_array_equal(batch.revival_snapshot()[:, 6], expected.astype(int))
        assert np.all(batch.diagnostic_players()[:, 0, [3, 5]] == [4, 1])
        if epoch == 1:
            total = batch.revival_count
            batch.reset_environments(ids(range(256)))
            assert not batch.revival_snapshot().any()
            assert batch.revival_count == total
    assert batch.revival_count == total + int(expected.sum())


@pytest.mark.parametrize("ring,kind", [(184, 1), (187, 3), (188, 4)])
def test_revived_reactor_joins_counter_family_without_intermediate_gifts(ring, kind):
    batch = game(refill=True)
    seed(batch, [35])
    seed(batch, [ring, 208], owner=1)
    load(batch, owner=1, hp=5)
    start_attack(batch)
    step(batch, [1])
    step(batch, [0])
    assert batch.revival_count == 1 and batch.automatic_gift_count == 0
    assert batch.counter_observations()[0, :4].tolist() == [1, kind, 1, 1 if kind == 3 else 0]
    assert batch.diagnostic_players()[0, 1, 0] == 10
    assert not hand(batch).size
    assert batch.diagnostic_players()[0, :, 5].tolist() == [0, 0, 0]
    step(batch, [0])
    assert batch.automatic_gift_count == batch.consumed_count == 3
    assert batch.resolved_counter_count == 1 and batch.suppressed_counter_count == 0
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_payment_revival_keeps_pending_sibling_live_but_no_revive_suppresses_it():
    for copies in (0, 1):
        batch = game()
        seed(batch, [35, *([208] * copies)])
        seed(batch, [188, 184], owner=1)
        load(batch, hp=4, mp=0, cp=0)
        start_attack(batch)
        for choice in (1, 2, 0, 0):
            step(batch, [choice])
        if copies:
            assert batch.counter_observations()[0, 1] == 1
            step(batch, [0])  # The second ring then kills the revived source.
        assert batch.diagnostic_players()[0, 0, 0] == 0
        assert batch.revival_count == copies
        assert batch.resolved_counter_count == 1 + copies
        assert batch.suppressed_counter_count == 1 - copies
        assert batch.counter_snapshot()[0, 11] == 0


def test_reflected_attack_revives_original_owner_before_its_periodic_tick():
    batch = game()
    seed(batch, [35, 208])
    seed(batch, [190], owner=1)
    load(batch, hp=2, illness=3)
    start_attack(batch)
    for choice in (1, 0, 0):
        step(batch, [choice])
    assert batch.reflection_count == 1 and batch.revival_count == 1
    assert batch.diagnostic_players()[0, 0, [0, 5]].tolist() == [5, 1]
    assert batch.revival_snapshot()[0, 2] == 1


def test_self_bounced_absorption_heals_only_after_owned_revive():
    batch = game(size=128)
    for env in range(128):
        seed(batch, [27, 21], env=env)
        seed(batch, [190, 208], env=env, owner=1)
        load(batch, env=env, owner=1, hp=2)
    start_attack(batch, size=128)
    for choice in (1, 0, 1, 0):
        step(batch, [choice] * 128)
    targets = batch.episode_snapshot()[:, 2].copy()
    step(batch, [0] * 128)
    self_targets = targets == 1
    assert self_targets.any()
    assert np.all(batch.diagnostic_players()[self_targets, 1, 0] == 12)
    assert np.all(batch.revival_snapshot()[self_targets, 2] == 1)
    assert np.all(batch.attack_effect_snapshot()[self_targets, :2] == [1, 2])
    assert np.all(batch.diagnostic_players()[:, 0, 5] == 1)


@pytest.mark.parametrize("true,fake,revives", [(208, 191, True), (191, 208, False)])
def test_actual_owned_identity_not_display_decides_passive_trigger(true, fake, revives):
    batch = game(players=2)
    seed(batch, [35])
    batch.seed_hand(0, 1, ids([[101, true, fake, 0], [102, 194, 0, 0]]))
    load(batch, owner=1, hp=2, mask=1)
    start_attack(batch)
    assert batch.passive_observations()[0, 0].tolist() == ([1, 10] if fake == 208 else [0, 0])
    step(batch, [0])
    assert batch.revival_count == int(revives)
    assert batch.diagnostic_players()[0, 1, 0] == (10 if revives else 0)
    assert hand(batch)[:, 1].tolist() == ([194] if revives else [191, 194])


@pytest.mark.parametrize("mask", [0, 1, 2, 3])
def test_passive_projection_is_current_actor_display_only_owned_readonly(mask):
    batch = game()
    batch.seed_hand(0, 0, ids([[1, 208, 191, 0], [2, 191, 208, 0], [3, 208, 0, 0]]))
    seed(batch, [208, 208, 208], owner=1)
    load(batch, mask=mask)
    assert not batch.passive_observations().any()
    batch.start_environments(ids([0]))
    view = batch.passive_observations()
    assert view.shape == (1, 18, 2) and not view.flags.writeable
    # Stored fake identities remain displayed even if the current Dream mask
    # has since cleared. Fog must not reveal those real identities either.
    assert view[0, :3].tolist() == [[0, 0], [1, 10], [1, 10]]
    assert not view[0, 3:].any()
    assert not batch.choice_masks()[0, 3]  # Displayed Sun is not a ready action leader.
    step(batch, [0])
    assert np.all(batch.passive_observations()[0, :3] == [1, 10])
    assert view[0, :3].tolist() != batch.passive_observations()[0, :3].tolist()


@pytest.mark.parametrize("setup_action", ["seed", "deal"])
def test_already_dead_setup_deal_and_other_owner_idle_never_revive(setup_action):
    batch = game()
    load(batch, owner=1, hp=0, illness=4)
    if setup_action == "seed":
        seed(batch, [208], owner=1)
    else:
        batch.deal_cards(ids([0]), ids([1]), ids([101]), ids([208]))
    batch.start_environments(ids([0]))
    for _ in range(3):
        step(batch, [0])
    assert batch.diagnostic_players()[0, 1, [0, 5]].tolist() == [0, 0]
    assert batch.revival_count == 0 and hand(batch)[0, 1] == 208


@pytest.mark.parametrize("limit", ["turn", "decision"])
def test_revived_liveness_precedes_limits_and_queued_receipts_are_suppressed(limit):
    batch = game(
        players=2,
        refill=True,
        max_turns=1 if limit == "turn" else 1000,
        max_decisions=4 if limit == "decision" else 4000,
    )
    seed(batch, [35])
    seed(batch, [208], owner=1)
    load(batch, owner=1, hp=2)
    start_attack(batch)
    step(batch, [0])
    assert batch.revival_count == 1 and batch.episode_snapshot()[0, 3] == 13
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 2
    assert not batch.passive_observations().any()


@pytest.mark.parametrize("limit", ["turn", "decision"])
def test_real_winner_after_revived_owner_tick_still_precedes_limit(limit):
    batch = game(
        players=2,
        refill=True,
        max_turns=1 if limit == "turn" else 1000,
        max_decisions=4 if limit == "decision" else 4000,
    )
    seed(batch, [219, 208])
    load(batch, hp=1, illness=1)
    load(batch, owner=1, hp=2, illness=4)
    start_attack(batch)
    step(batch, [0])
    assert batch.revival_snapshot()[0].tolist() == [1, 10, 0, 0, 0, 1, 0, 0, 0, 0]
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 0]
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 2


def test_late_hidden_failure_rolls_back_revive_receipts_and_rng_with_equivalent_retry():
    def prepare():
        batch = game(size=2, refill=True)
        for env in range(2):
            seed(batch, [35], env=env)
            seed(batch, [208], env=env, owner=1)
            load(batch, env=env, owner=1, hp=2)
            load(batch, env=env, illness=4)
        batch.seed_hand(1, 1, ids([[101, 208, 0, 0], [102, 178, 190, 0]]))
        load(batch, env=1, owner=1, hp=2, mask=1)
        start_attack(batch, size=2)
        step(batch, [2], [1])
        return batch

    batch, reference = prepare(), prepare()
    before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [0, 0])
    same(before, snapshot(batch))
    for candidate in (batch, reference):
        step(candidate, [2], [1])
        step(candidate, [0, 0])
    same(snapshot(batch), snapshot(reference))
    assert batch.revival_count == 2 and batch.automatic_gift_count == 4
    assert batch.revival_snapshot().flags.writeable is False


@pytest.mark.parametrize("passives", [None, ((208, 10),)])
def test_explicit_raw_batch_without_passive_profiles_keeps_old_death_behavior(passives):
    batch = game(players=2, passives=passives)
    seed(batch, [35])
    seed(batch, [208], owner=1)
    load(batch, owner=1, hp=2)
    start_attack(batch)
    step(batch, [0])
    assert batch.diagnostic_players()[0, 1, 0] == (0 if passives is None else 10)


@pytest.mark.parametrize(
    "profiles",
    [
        (),
        ((208, 0),),
        ((208, 101),),
        ((208, -1),),
        ((208, 10), (208, 10)),
        ((191, 10),),
        ((35, 10),),
        ((181, 10),),
        ((46, 0),),
        ((999, 10),),
    ],
)
def test_invalid_native_profiles_fail_before_start(profiles):
    with pytest.raises(ValueError):
        game(passives=profiles)


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((208, 9),)},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profile_fields": ("x",)},
        {"official_timing_verified": True},
        {"effect_count": 2},
    ],
)
def test_passive_plan_pins_and_readiness_cannot_be_relabelled(change):
    with pytest.raises(ValidationError):
        FullGamePassivePlan.model_validate(PLAN.passives.model_dump() | change)


def test_source_builder_rechecks_unsafe_copies_and_factory_adds_new_profile():
    catalog = read_api_catalog_snapshot(CATALOG)
    item = next(item for item in catalog.items if item.model_id == 208)
    altered = item.model_copy(update={"raw": dict(item.raw) | {"abilityValue": 9}})
    tampered = catalog.model_copy(
        update={"items": tuple(altered if row.model_id == 208 else row for row in catalog.items)}
    )
    with pytest.raises(ValueError):
        build_full_game_passive_plan(tampered, BibleSnapshot.model_validate_json(BIBLE.read_text()))
    configured = create_development_full_game_batch(
        resource_cap=100, catalog_path=CATALOG, bible_path=BIBLE, batch_size=1
    )
    assert configured.metadata.plan.passives.profiles == ((208, 10),)
    assert configured.metadata.observation_schema_version == 32
    assert (
        not configured.metadata.promotion_eligible
        and not configured.metadata.full_game_training_ready
    )
    seed(configured.batch, [35])
    seed(configured.batch, [208], owner=1)
    load(configured.batch, owner=1, hp=2)
    configured.batch.start_environments(ids([0]))
    for choice in (1, 0, configured.metadata.capacity + 2, 0):
        step(configured.batch, [choice])
    assert configured.batch.revival_count == 1


@pytest.mark.parametrize("mask", [0, 1, 2, 3])
@pytest.mark.parametrize("displayed", [191, 208])
def test_different_hidden_passive_ownership_has_identical_public_projections(mask, displayed):
    worlds = []
    for actual in (191, 208):
        batch = game()
        seed(batch, [35])
        batch.seed_hand(0, 1, ids([[101, actual, displayed, 0]]))
        load(batch, owner=1, hp=5, mask=mask)
        start_attack(batch)
        worlds.append(batch)
    for name in (
        "episode_snapshot",
        "actor_hands",
        "player_observations",
        "choice_masks",
        "pending_observations",
        "special_defense_observations",
        "chance_observations",
        "counter_observations",
        "passive_observations",
        "defense_order",
    ):
        np.testing.assert_array_equal(getattr(worlds[0], name)(), getattr(worlds[1], name)())
    for batch in worlds:
        step(batch, [0])
    assert [batch.revival_count for batch in worlds] == [0, 1]


@pytest.mark.parametrize("phase", ["ready", "defense"])
def test_displayed_sun_cannot_be_selected_as_manual_action_or_armor(phase):
    batch = game()
    seed(batch, [208] if phase == "ready" else [35])
    seed(batch, [208], owner=1)
    if phase == "ready":
        batch.start_environments(ids([0]))
    else:
        start_attack(batch)
    assert not batch.choice_masks()[0, 1]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [1])
    same(before, snapshot(batch))


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 8},
        {"kernel_schema_version": 8},
        {"observation_schema_version": 8},
        {"passive_observation_fields": ("actual_owned",)},
        {"revival_snapshot_fields": ("policy_input",)},
        {"passive_observation_boundary": "all-owner-actual-identities"},
        {"revival_snapshot_boundary": "policy-input"},
        {"revival_trigger": "whenever-hp-zero"},
        {"revival_ownership": "displayed-copy"},
        {"revival_order": "after-outcome"},
        {"revival_state": "reset-everything"},
        {"revival_gifts": "immediate"},
        {"promotion_eligible": True},
        {"local_training_eligible": True},
        {"full_game_training_ready": True},
        {"official_fidelity_verified": True},
    ],
)
def test_metadata_cannot_claim_legacy_schema_or_unverified_passive_semantics(change):
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=1,
    )
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(configured.metadata.model_dump() | change)
