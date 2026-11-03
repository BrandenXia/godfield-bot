"""Joined Broom/Soap scheduling, actual eligibility and staged native sampling."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import FullGameMetadata, build_full_game_plan
from godfield_bot.full_game_removal import FullGameRemovalPlan, build_full_game_removal_plan
from godfield_bot.full_game_roles import build_full_game_role_manifest

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
    profiles=PLAN.removal.profiles,
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
        passive_profiles=ids(PLAN.passives.profiles),
        removal_profiles=ids(profiles).reshape(-1, 3) if profiles is not None else None,
        gift_profiles=ids([[191, 1]]) if refill else None,
        refill_on_use=refill,
    )


def seed(batch, rows, *, owner=0, env=0):
    batch.seed_hand(env, owner, ids(rows).reshape(-1, 4))


def models(batch, cards, *, owner=0, env=0):
    seed(
        batch,
        [(100 * owner + i + 1, card, 0, 0) for i, card in enumerate(cards)],
        owner=owner,
        env=env,
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


def begin(batch, *, size=1):
    batch.start_environments(ids(range(size)))
    for choice in (1, 0, 20):
        step(batch, [choice] * size)


def hand(batch, *, owner=1, env=0):
    values = batch.diagnostic_inventory()[env, owner]
    return values[values[:, 0] != 0]


def snapshot(batch):
    arrays = [
        getattr(batch, name)()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "defense_order",
            "attack_effect_observations",
            "counter_observations",
            "counter_snapshot",
            "passive_observations",
            "revival_snapshot",
            "removal_snapshot",
            "acquisition_snapshot",
            "chance_snapshot",
            "attack_effect_snapshot",
            "selected_defenses",
            "attack_order",
        )
    ]
    totals = [
        getattr(batch, name)
        for name in (
            "action_count",
            "consumed_count",
            "miracle_use_count",
            "mp_spent",
            "removal_count",
            "removal_effect_count",
            "automatic_gift_count",
            "suppressed_gift_count",
            "overflow_count",
            "revival_count",
            "revived_hp",
            "hp_damage",
            "attack_count",
            "resolved_attack_count",
        )
    ]
    return arrays, totals


def same(left, right):
    assert left[1] == right[1]
    for before, after in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(before, after)


def sample_indices(eligible, maximum, *, env=0, seed=67, epoch=1, state=None):
    # Independent bounded SplitMix + partial Fisher-Yates reference.
    mask = (1 << 64) - 1
    if state is None:
        state = (
            seed
            ^ (((env + 1) * 0x9E3779B97F4A7C15) & mask)
            ^ ((epoch * 0xBF58476D1CE4E5B9) & mask)
            ^ 0x243F6A8885A308D3
        )
    pool, selected, draws = list(eligible), [], 0
    for pick in range(min(maximum, len(pool))):
        bound = len(pool) - pick
        offset = 0
        if bound > 1:
            for _ in range(16):
                state = (state + 0x9E3779B97F4A7C15) & mask
                word = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & mask
                word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & mask
                word ^= word >> 31
                if word >= (1 << 64) % bound:
                    offset = word % bound
                    break
            else:
                raise AssertionError("independent rejection bound exhausted")
            draws += 1
        pool[pick], pool[pick + offset] = pool[pick + offset], pool[pick]
        selected.append(pool[pick])
    return set(selected), state, draws


@pytest.mark.parametrize("model,kind,limit", PLAN.removal.profiles)
def test_enemy_targeted_standalone_sundry_origin_and_only_super_mirror(model, kind, limit):
    batch = game()
    models(batch, [model, 9])
    models(batch, [190, 174, 151, 165, 234, 37, 189, 184], owner=1)
    load(batch, mp=0, cp=0)
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.episode_snapshot()[0, 3] == 2
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0, 1]
    assert batch.pending_observations()[0, 3:6].tolist() == [0, 0, 3]
    assert batch.attack_effect_observations()[0].tolist() == [1, 7 + kind, limit, 0]
    assert batch.consumed_count == batch.mp_spent == 0
    step(batch, [0])
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [20, 21]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [19])  # Viewer-self evidence is not self-cast permission.
    same(before, snapshot(batch))
    step(batch, [20])
    assert batch.pending_observations()[0, 3:6].tolist() == [0, 0, 3]
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0, 1]
    assert batch.mp_spent == 0 and batch.consumed_count == 1


@pytest.mark.parametrize("model,eligible,expected", [(205, [191, 194, 208], 3), (206, [], 0)])
def test_whole_small_pool_and_empty_pool_resolve_without_hanging(model, eligible, expected):
    batch = game(refill=True)
    models(batch, [model])
    models(batch, eligible, owner=1)
    begin(batch)
    step(batch, [0])
    assert batch.removal_count == expected and batch.removal_effect_count == 1
    assert batch.automatic_gift_count == 1  # Source use, never per victim.
    assert batch.consumed_count == 1 and not hand(batch).size
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    assert batch.hp_damage == batch.inflicted_illness_count == batch.revival_count == 0


@pytest.mark.parametrize("count", [0, 1, 2, 3, 5, 18])
@pytest.mark.parametrize("model,kind,limit", PLAN.removal.profiles)
def test_partial_pools_native_sample_without_duplicates_and_stable_survivors(
    count, model, kind, limit
):
    batch = game(size=64)
    rows = [(101 + i, 211 if kind == 2 else 191, 0, 1 if kind == 2 else 0) for i in range(count)]
    for env in range(64):
        models(batch, [model], env=env)
        seed(batch, rows, owner=1, env=env)
    begin(batch, size=64)
    step(batch, [0] * 64)
    removed = min(count, limit)
    for env in range(64):
        selected, _, draws = sample_indices(range(count), limit, env=env)
        assert hand(batch, env=env).tolist() == [
            list(row) for i, row in enumerate(rows) if i not in selected
        ]
        stats = [
            int(kind == 1),
            int(kind == 2),
            removed if kind == 1 else 0,
            removed if kind == 2 else 0,
            int(count == 0),
            int(count < limit),
            count,
            draws,
        ]
        assert batch.removal_snapshot()[env].tolist() == stats
    assert batch.removal_count == 64 * removed and batch.removal_effect_count == 64


@pytest.mark.parametrize("model,kind,limit", PLAN.removal.profiles)
def test_category_used_flag_and_fake_identity_restrictions_use_actual_pool(model, kind, limit):
    # Used miracles are protected from Broom, even under a fake model. Soap
    # cannot remove unused miracles, ordinary artifacts or held trade cards.
    # Broom provisionally includes held trade cards; no exemption is proven.
    rows = [
        (101, 211, 212, 1),
        (102, 213, 214, 1),
        (103, 215, 216, 1),
        (104, 211, 212, 0),
        (105, 191, 208, 0),
        (106, 35, 64, 0),
        (107, 3, 0, 0),
    ]
    batch = game(size=128)
    for env in range(128):
        models(batch, [model], env=env)
        seed(batch, rows, env=env, owner=1)
        load(batch, env=env, owner=1, mask=2)
    begin(batch, size=128)
    step(batch, [0] * 128)
    pool = [3, 4, 5, 6] if kind == 1 else [0, 1, 2]
    for env in range(128):
        selected, _, _ = sample_indices(pool, limit, env=env)
        assert hand(batch, env=env).tolist() == [
            list(row) for i, row in enumerate(rows) if i not in selected
        ]
    assert batch.removal_count == 128 * limit and batch.miracle_use_count == 0


@pytest.mark.parametrize("actual,displayed,kind,limit", [(205, 206, 1, 3), (206, 205, 2, 2)])
def test_hidden_sundry_resolves_its_actual_kind_only_on_cast(actual, displayed, kind, limit):
    batch = game()
    seed(batch, [(1, actual, displayed, 0)])
    seed(
        batch,
        [(101, 211, 0, 1), (102, 212, 0, 1), (103, 191, 0, 0), (104, 194, 0, 0), (105, 208, 0, 0)],
        owner=1,
    )
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.attack_effect_observations()[0, 1] == (8 if displayed == 205 else 9)
    step(batch, [0])
    step(batch, [20])
    assert batch.attack_effect_observations()[0, 1:3].tolist() == [7 + kind, limit]
    step(batch, [0])
    assert hand(batch)[:, 1].tolist() == ([211, 212] if kind == 1 else [191, 194, 208])


def test_soap_uses_performed_flags_created_by_actual_prior_miracle_uses():
    batch = game()
    models(batch, [35, 206])
    models(batch, [213, 235, 196, 197, 198], owner=1)
    load(batch, owner=1, hp=50, illness=1)
    batch.start_environments(ids([0]))
    step(batch, [0])
    # Perform a reusable HP utility, then hand off to the third living owner.
    step(batch, [2])
    assert hand(batch)[-1, [1, 3]].tolist() == [235, 1]
    step(batch, [0])
    for choice in (2, 0, 20, 0):
        step(batch, [choice])
    assert batch.removal_count == 1 and batch.removal_snapshot()[0, 5] == 1
    assert hand(batch)[:, 1].tolist() == [213, 196, 197, 198]
    assert batch.miracle_use_count == 1


@pytest.mark.parametrize("model", [205, 206])
def test_reflection_uses_current_source_and_final_staged_hand(model):
    batch = game(refill=True)
    seed(
        batch,
        [
            (1, model, 0, 0),
            (2, 191, 0, 0),
            (3, 194, 0, 0),
            (4, 208, 0, 0),
            (5, 211, 0, 1),
            (6, 212, 0, 1),
        ],
    )
    models(batch, [190, 191], owner=1)
    begin(batch)
    for choice in (1, 0):
        step(batch, [choice])
    assert batch.removal_count == batch.automatic_gift_count == 0
    assert batch.attack_effect_observations()[0, 3] == 1
    assert batch.episode_snapshot()[0, 2] == 0
    assert hand(batch, owner=0)[:, 1].tolist() == [191, 194, 208, 211, 212]
    step(batch, [0])
    assert batch.automatic_gift_count == 2 and batch.consumed_count == 2
    assert batch.removal_count == (3 if model == 205 else 2)
    assert batch.removal_effect_count == batch.reflection_count == 1
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


def test_reflected_broom_can_remove_amulet_before_original_owner_lethal_tick():
    batch = game(players=2, refill=True, max_turns=1)
    models(batch, [205, 208, 191, 194])
    models(batch, [190], owner=1)
    load(batch, hp=1, illness=1)
    begin(batch)
    for choice in (1, 0, 0):
        step(batch, [choice])
    assert batch.removal_count == 3 and batch.revival_count == 0
    assert batch.diagnostic_players()[0, 0, 0] == 0
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 1]
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 2


@pytest.mark.parametrize("model", [205, 206])
def test_chained_super_mirrors_defer_removal_and_all_receipts(model):
    batch = game(refill=True)
    seed(batch, [(1, model, 0, 0), (2, 190, 0, 0), (3, 211, 0, 1), (4, 212, 0, 1)])
    seed(
        batch,
        [
            (101, 190, 0, 0),
            (102, 191, 0, 0),
            (103, 194, 0, 0),
            (104, 208, 0, 0),
            (105, 211, 0, 1),
            (106, 212, 0, 1),
        ],
        owner=1,
    )
    begin(batch)
    for choice in (1, 0, 1, 0):
        step(batch, [choice])
    assert batch.reflection_count == 2 and batch.removal_count == batch.automatic_gift_count == 0
    assert batch.episode_snapshot()[0, 2] == 1
    step(batch, [0])
    assert batch.removal_effect_count == 1 and batch.automatic_gift_count == 3
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("limit", [3, 4])
def test_explicit_decision_limit_does_not_fabricate_resolution_or_victim_gifts(limit):
    batch = game(refill=True, max_decisions=limit)
    models(batch, [205])
    models(batch, [191, 194, 208], owner=1)
    begin(batch)
    if limit == 4:
        step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 13
    assert batch.removal_count == (3 if limit == 4 else 0)
    assert batch.removal_effect_count == (1 if limit == 4 else 0)
    assert batch.automatic_gift_count == 0 and batch.suppressed_gift_count == 1


@pytest.mark.parametrize("model,limit", [(205, 3), (206, 2)])
def test_native_stream_is_reproducible_independent_and_epoch_reset_clears_counts(model, limit):
    batch = game(size=128)
    total = 0
    for epoch in (1, 2):
        rows = [(101 + i, 211 if model == 206 else 191, 0, int(model == 206)) for i in range(8)]
        for env in range(128):
            models(batch, [model], env=env)
            seed(batch, rows, owner=1, env=env)
            load(batch, env=env, owner=0, illness=4, mask=2)
        begin(batch, size=128)
        step(batch, [0] * 128)
        for env in range(128):
            selected, _, _ = sample_indices(range(8), limit, env=env, epoch=epoch)
            assert hand(batch, env=env).tolist() == [
                list(row) for i, row in enumerate(rows) if i not in selected
            ]
        total += 128 * limit
        assert batch.removal_count == total
        if epoch == 1:
            batch.reset_environments(ids(range(128)))
            assert not batch.removal_snapshot().any()
            assert batch.removal_effect_count == 128


def test_empty_soap_does_not_advance_sampling_stream_before_later_broom():
    batch = game()
    models(batch, [206, 205])
    models(batch, [191] * 6, owner=1)
    begin(batch)
    step(batch, [0])
    assert batch.removal_snapshot()[0, 7] == 0
    for choice in (0, 0, 1, 0, 20, 0):
        step(batch, [choice])
    selected, _, _ = sample_indices(range(6), 3)
    assert hand(batch).tolist() == [[101 + i, 191, 0, 0] for i in range(6) if i not in selected]


def test_late_hidden_failure_rolls_back_all_removals_rng_receipts_and_corrected_retry():
    def prepare():
        batch = game(size=2, refill=True)
        for env in range(2):
            models(batch, [205], env=env)
            models(batch, [191] * 8, env=env, owner=1)
        seed(batch, [(101, 178, 190, 0), *[(102 + i, 191, 0, 0) for i in range(7)]], owner=1, env=1)
        begin(batch, size=2)
        step(batch, [1], [1])
        return batch

    batch, reference = prepare(), prepare()
    before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [0, 0])
    same(before, snapshot(batch))
    for candidate in (batch, reference):
        step(candidate, [1], [1])
        step(candidate, [0, 0])
    same(snapshot(batch), snapshot(reference))
    assert batch.removal_count == 6 and batch.automatic_gift_count == 2
    assert not batch.removal_snapshot().flags.writeable


@pytest.mark.parametrize("model", [205, 206])
def test_hidden_unsupported_leader_cast_error_is_atomic(model):
    batch = game()
    seed(batch, [(1, 207, model, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [0])
    begin_before = snapshot(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [20])
    same(begin_before, snapshot(batch))


def test_raw_removal_only_scheduler_joins_without_optional_composition_or_curses():
    batch = native.FullGameBatch(
        1,
        2,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity=18,
        removal_profiles=ids(PLAN.removal.profiles),
    )
    models(batch, [205])
    models(batch, [191, 194], owner=1)
    batch.start_environments(ids([0]))
    for choice in (1, 20, 0):
        step(batch, [choice])
    assert batch.removal_count == 2 and batch.removal_effect_count == 1
    assert batch.episode_snapshot()[0, 3:5].tolist() == [1, 1]


@pytest.mark.parametrize("model", [205, 206])
def test_omitted_raw_removal_profiles_keep_old_unavailable_leaders(model):
    batch = game(profiles=None)
    models(batch, [model])
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 1]


@pytest.mark.parametrize(
    "profiles",
    [
        (),
        ((205, 0, 3),),
        ((205, 3, 3),),
        ((205, 1, 2),),
        ((206, 2, 3),),
        ((205, 1, 0),),
        ((205, 1, 513),),
        ((205, 1, 3), (205, 1, 3)),
        ((208, 1, 3),),
        ((191, 1, 3),),
        ((35, 1, 3),),
        ((999, 1, 3),),
    ],
)
def test_invalid_native_profile_dimensions_categories_counts_and_collisions(profiles):
    with pytest.raises(ValueError):
        game(profiles=profiles)


@pytest.mark.parametrize(
    "change",
    [
        {"profiles": ((205, 1, 2), (206, 2, 2))},
        {"catalog_sha256": "0" * 64},
        {"bible_client_sha256": "0" * 64},
        {"profile_fields": ("x",)},
        {"origin": "miracle"},
        {"targeting": "self-cast"},
        {"broom_pool": "all-owned"},
        {"soap_pool": "unused-miracles"},
        {"victim_selection": "learner-victim-ids"},
        {"short_pool": "stall"},
        {"victim_receipts": "one-per-victim"},
        {"official_sampling_and_timing_verified": True},
        {"official_soap_event_observed": True},
    ],
)
def test_plan_relabeling_cannot_change_pins_or_claim_official_sampling(change):
    with pytest.raises(ValidationError):
        FullGameRemovalPlan.model_validate(PLAN.removal.model_dump() | change)


def test_source_builder_revalidates_unsafe_catalog_copy():
    catalog = read_api_catalog_snapshot(CATALOG)
    row = next(row for row in catalog.items if row.model_id == 205)
    altered = row.model_copy(update={"raw": dict(row.raw) | {"cost": 10}})
    tampered = catalog.model_copy(
        update={"items": tuple(altered if item.model_id == 205 else item for item in catalog.items)}
    )
    with pytest.raises(ValueError):
        build_full_game_removal_plan(tampered, BibleSnapshot.model_validate_json(BIBLE.read_text()))


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 9},
        {"kernel_schema_version": 9},
        {"observation_schema_version": 9},
        {"removal_snapshot_fields": ("victim-id",)},
        {"removal_effect_codes": ("broom=miracle",)},
        {"removal_sampling": "player-selected"},
        {"removal_short_pool": "require-full-pool"},
        {"removal_receipts": "victim-gifts"},
        {"removal_order": "after-refill"},
        {"removal_snapshot_boundary": "policy-input"},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
    ],
)
def test_metadata_pins_new_observations_and_keeps_readiness_false(change):
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
        FullGameMetadata.model_validate(metadata.model_dump() | change)


def test_trade_membership_is_provisional_and_soap_does_not_remove_trade():
    for model in (205, 206):
        batch = game()
        models(batch, [model])
        models(batch, [3, 4, 5], owner=1)
        begin(batch)
        step(batch, [0])
        assert batch.removal_count == (3 if model == 205 else 0)
    assert "trade-included-provisional" in PLAN.removal.broom_pool
    assert not PLAN.removal.official_broom_trade_eligibility_verified


@pytest.mark.parametrize("prior_used_count", [0, 1])
def test_empty_and_forced_singleton_do_not_advance_rng_before_later_removal(prior_used_count):
    batch = game()
    models(batch, [206, 205])
    seed(
        batch,
        [(101 + i, 191, 0, 0) for i in range(6)] + ([(107, 211, 0, 1)] if prior_used_count else []),
        owner=1,
    )
    begin(batch)
    step(batch, [0])
    assert batch.removal_snapshot()[0, 7] == 0
    assert batch.removal_count == prior_used_count
    for choice in (0, 0, 1, 0, 20, 0):
        step(batch, [choice])
    selected, _, _ = sample_indices(range(6), 3)
    assert hand(batch).tolist() == [[101 + i, 191, 0, 0] for i in range(6) if i not in selected]


def test_consecutive_nonempty_removals_use_committed_native_stream_not_reset_ticket():
    batch = game()
    models(batch, [205, 205])
    rows = [[101 + i, 191, 0, 0] for i in range(8)]
    seed(batch, rows, owner=1)
    begin(batch)
    step(batch, [0])
    selected, state, _ = sample_indices(range(8), 3)
    survivors = [row for i, row in enumerate(rows) if i not in selected]
    assert hand(batch).tolist() == survivors
    for choice in (0, 0, 1, 0, 20, 0):
        step(batch, [choice])
    selected, _, _ = sample_indices(range(5), 3, state=state)
    assert hand(batch).tolist() == [row for i, row in enumerate(survivors) if i not in selected]
    assert batch.removal_snapshot()[0, [0, 2, 6, 7]].tolist() == [2, 6, 13, 6]


@pytest.mark.parametrize("model", [205, 206])
def test_root_policy_does_not_observe_private_victim_pool_before_resolution(model):
    batch = game(size=2)
    for env in (0, 1):
        models(batch, [model], env=env)
    models(batch, [191, 194], env=0, owner=1)
    seed(batch, [(101, 211, 0, 1), (102, 212, 0, 1), (103, 213, 0, 1)], env=1, owner=1)
    batch.start_environments(ids([0, 1]))
    for phase_choice in (None, 1, 0):
        if phase_choice is not None:
            step(batch, [phase_choice, phase_choice])
        for name in (
            "actor_hands",
            "player_observations",
            "choice_masks",
            "pending_observations",
            "attack_effect_observations",
            "passive_observations",
            "removal_snapshot",
        ):
            views = getattr(batch, name)()
            np.testing.assert_array_equal(views[0], views[1])


@pytest.mark.parametrize("column,value", [(0, -1), (1, 0), (2, 0), (3, 0), (4, 1), (5, 18)])
def test_late_malformed_command_rolls_back_prepared_removal_and_all_diagnostics(column, value):
    batch = game(size=2, refill=True)
    for env in (0, 1):
        models(batch, [205], env=env)
        models(batch, [191] * 8, env=env, owner=1)
    begin(batch, size=2)
    before = snapshot(batch)
    episodes = batch.episode_snapshot()
    commands = ids([[env, *episodes[env, :4], 0] for env in (0, 1)])
    commands[1, column] = value
    with pytest.raises(ValueError):
        batch.step(commands)
    same(before, snapshot(batch))


def test_duplicate_environment_rolls_back_first_prepared_removal():
    batch = game(size=2)
    models(batch, [205])
    models(batch, [191] * 6, owner=1)
    begin(batch)
    before = snapshot(batch)
    command = ids([[0, *batch.episode_snapshot()[0, :4], 0]])
    with pytest.raises(ValueError, match="duplicate"):
        batch.step(np.repeat(command, 2, axis=0))
    same(before, snapshot(batch))


def test_ready_leader_cancel_does_not_consume_or_sample_and_restores_choices():
    batch = game(refill=True)
    models(batch, [205, 206, 9])
    batch.start_environments(ids([0]))
    before = hand(batch, owner=0).copy()
    for choice in (1, 1):
        step(batch, [choice])
    assert batch.episode_snapshot()[0, 3] == 1
    assert batch.removal_effect_count == batch.removal_count == batch.consumed_count == 0
    assert batch.automatic_gift_count == 0 and not batch.removal_snapshot().any()
    np.testing.assert_array_equal(hand(batch, owner=0), before)
