"""Integrated multi-card Discard: source eligibility, private roles and atomicity."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    DISCARD_FIELDS,
    DISCARD_SNAPSHOT_FIELDS,
    FullGameMetadata,
    build_full_game_plan,
    create_development_full_game_batch,
    execute_full_game_commands,
    full_game_decision_contexts,
)
from godfield_bot.full_game_discard import FullGameDiscardPlan, build_full_game_discard_plan
from godfield_bot.full_game_protocol import FullGameCommand

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")
PLAN = build_full_game_plan(
    read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
)


def ids(values):
    return np.asarray(values, dtype=np.int64)


def configured(
    *, size=1, players=3, capacity=18, seed=67, turns=100, decisions=1000, acquisition="manual"
):
    return create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=size,
        player_count=players,
        capacity=capacity,
        seed=seed,
        max_turns=turns,
        max_decisions=decisions,
        initial_hp=100,
        initial_mp=20,
        acquisition_mode=acquisition,
    )


def hand(batch, values, *, env=0, owner=0):
    batch.seed_hand(
        env,
        owner,
        ids(
            [
                [owner * 1000 + i + 1, *((v, 0, 0) if isinstance(v, int) else v)]
                for i, v in enumerate(values)
            ]
        ).reshape(-1, 4),
    )


def load(batch, *, env=0, owner=0, hp=100, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, 20, 7, illness]]), ids([mask]))


def step(batch, choices, envs=None):
    rows = batch.episode_snapshot()
    envs = range(len(choices)) if envs is None else envs
    batch.step(
        ids(
            [[env, *rows[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
        ).reshape(-1, 6)
    )


def snapshot(batch):
    return (
        tuple(
            getattr(batch, n)()
            for n in (
                "episode_snapshot",
                "diagnostic_players",
                "diagnostic_inventory",
                "actor_hands",
                "player_observations",
                "choice_masks",
                "discard_observations",
                "discard_order",
                "discard_snapshot",
                "attack_family_snapshot",
                "revival_snapshot",
                "acquisition_snapshot",
            )
        ),
        tuple(
            getattr(batch, n)
            for n in (
                "action_count",
                "discard_count",
                "discarded_card_count",
                "consumed_count",
                "miracle_use_count",
                "mp_spent",
                "hp_damage",
                "removal_count",
                "automatic_gift_count",
                "suppressed_gift_count",
                "revival_count",
                "ascension_count",
            )
        ),
    )


def same(left, right):
    assert left[1] == right[1]
    for a, b in zip(left[0], right[0], strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("model", PLAN.discard.discard_model_ids)
@pytest.mark.parametrize("players", [2, 3, 9])
def test_every_eligible_held_model_removes_without_executing_its_card_effect(model, players):
    batch = configured(players=players).batch
    hand(batch, [model])
    batch.start_environments(ids([0]))
    assert batch.choice_masks()[0, 19]
    before = batch.diagnostic_players().copy()
    step(batch, [19])
    assert batch.episode_snapshot()[0, 3] == 7
    assert not batch.choice_masks()[0, 0] and batch.choice_masks()[0, 19]
    assert batch.discard_observations().tolist() == [[1, 0, 0, 64, 1]]
    step(batch, [1])
    assert batch.discard_order()[0, 0] == 1
    assert batch.discarded_card_count == 0
    step(batch, [0])
    assert not batch.diagnostic_inventory().any()
    assert batch.discard_count == batch.discarded_card_count == 1
    assert batch.consumed_count == batch.miracle_use_count == batch.removal_count == 0
    assert batch.mp_spent == batch.hp_damage == batch.automatic_gift_count == 0
    after = batch.diagnostic_players()
    np.testing.assert_array_equal(before[:, :, :5], after[:, :, :5])
    assert after[0, :, 5].tolist() == [1] + [0] * (players - 1)
    assert batch.discard_snapshot().tolist() == [[1, 1, 0, 1, 1, 0]]
    assert not batch.discard_observations().any() and not batch.discard_order().any()


@pytest.mark.parametrize("model", [m for m, c in PLAN.inventory.profiles if c == 1] + [208, 209])
def test_protected_weapon_sun_and_mortar_have_no_discard_control(model):
    batch = configured().batch
    hand(batch, [model])
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 19]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [19])
    same(before, snapshot(batch))


@pytest.mark.parametrize("mask", range(16))
def test_multi_card_selection_undo_cancel_used_miracles_and_stable_survivors(mask):
    batch = configured().batch
    hand(batch, [35, (237, 217, 1), 3, 191, 208, 209, 127, (232, 217, 0)])
    load(batch, mask=mask)
    batch.start_environments(ids([0]))
    original = batch.diagnostic_inventory().copy()
    step(batch, [19])
    assert not batch.choice_masks()[0, [1, 5, 6]].any()
    for choice in (8, 2, 4, 4, 7):
        step(batch, [choice])
    assert batch.discard_order()[0, :4].tolist() == [8, 2, 7, 0]
    assert batch.discard_observations().tolist() == [[1, 3, 5, 64, 1]]
    step(batch, [19])
    assert batch.episode_snapshot()[0, 3] == 1 and batch.discard_count == 0
    np.testing.assert_array_equal(original, batch.diagnostic_inventory())
    assert not batch.diagnostic_players()[:, :, 5].any()
    step(batch, [19])
    for choice in (8, 2, 7, 3):
        step(batch, [choice])
    step(batch, [0])
    result = batch.diagnostic_inventory()[0, 0]
    np.testing.assert_array_equal(result[:4], original[0, 0, [0, 3, 4, 5]])
    assert not result[4:].any() and batch.discarded_card_count == 4
    assert batch.discard_snapshot().tolist() == [[2, 9, 1, 1, 4, 1]]
    assert batch.consumed_count == batch.miracle_use_count == batch.mp_spent == 0


@pytest.mark.parametrize("selected_at_limit", [False, True])
def test_toggle_limit_allows_nonempty_confirm_or_cancel_and_never_empty_mask(selected_at_limit):
    batch = configured().batch
    hand(batch, [127, 191])
    batch.start_environments(ids([0]))
    step(batch, [19])
    for _ in range(63):
        step(batch, [1])
    step(batch, [2 if selected_at_limit else 1])
    assert batch.discard_observations()[0, 2] == 64
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == (
        [0, 19] if selected_at_limit else [19]
    )
    step(batch, [0 if selected_at_limit else 19])
    assert batch.discard_count == int(selected_at_limit)


def test_all_18_slots_can_be_removed_in_one_turn_without_per_card_ticking():
    batch = configured().batch
    hand(batch, [127, 191, 3, (237, 0, 1), 232, 204] * 3)
    batch.start_environments(ids([0]))
    step(batch, [19])
    for slot in range(18, 0, -1):
        step(batch, [slot])
    assert batch.discard_order()[0].tolist() == list(range(18, 0, -1))
    step(batch, [0])
    assert batch.discard_count == 1 and batch.discarded_card_count == 18
    assert batch.discard_snapshot()[0, 5] == 3
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]


@pytest.mark.parametrize("actual,display", [(208, 191), (209, 191), (191, 208), (191, 209)])
def test_public_masks_do_not_leak_protected_actual_sundry_identity(actual, display):
    hidden, reference = configured().batch, configured().batch
    hand(hidden, [(actual, display, 0), 127])
    hand(reference, [display, 127])
    for batch in (hidden, reference):
        batch.start_environments(ids([0]))
        step(batch, [19])
    for name in ("actor_hands", "player_observations", "choice_masks", "discard_observations"):
        np.testing.assert_array_equal(getattr(hidden, name)(), getattr(reference, name)())
    if display == 191:
        step(hidden, [1])
        step(hidden, [0])
        assert hidden.diagnostic_inventory()[0, 0, 0, 1] == actual
        assert hidden.discarded_card_count == 0
        assert hidden.hidden_removal_snapshot()[0, [0, 2, 4]].tolist() == [1, 1, 1]


def test_late_hidden_protection_rolls_back_earlier_removals_and_periodic_revival():
    from test_full_game_generated import game as complete_raw_game

    batch, reference = [complete_raw_game(size=2, seed=67) for _ in range(2)]
    for item in (batch, reference):
        for env in range(2):
            hand(item, [127, (208, 191, 0) if env else 208], env=env)
            load(item, env=env, hp=1, illness=1)
        item.start_environments(ids([0, 1]))
        step(item, [19, 19])
        step(item, [1, 2])
    before = snapshot(batch)
    with pytest.raises(ValueError, match="actual discard model"):
        step(batch, [0, 0])
    same(before, snapshot(batch))
    for item in (batch, reference):
        step(item, [0], [0])
    same(snapshot(batch), snapshot(reference))
    assert batch.discard_count == 1 and batch.revival_count == 1


def test_periodic_death_keeps_bow_family_before_ending_without_second_tick():
    batch = configured(players=2).batch
    hand(batch, [127, 112])
    load(batch, hp=1, illness=1)
    load(batch, owner=1, mask=8)
    batch.start_environments(ids([0]))
    for choice in (19, 1, 0):
        step(batch, [choice])
    assert batch.episode_snapshot()[0, 2:4].tolist() == [1, 4]
    assert batch.discard_count == 1 and batch.discarded_card_count == 1
    assert batch.ascension_count == 1 and batch.diagnostic_players()[0, 0, 5] == 1
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 12
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0]
    assert batch.ascension_hp_damage == 30


def test_discard_does_not_refill_victims_in_automatic_acquisition_mode():
    configured_game = configured(acquisition="all-held-weighted")
    batch = configured_game.batch
    # Automatic opening is tested elsewhere; exercise a chosen eligible card after it.
    batch.start_environments(ids([0]))
    masks = batch.choice_masks()[0]
    assert masks[19]
    step(batch, [19])
    eligible = int(np.flatnonzero(batch.choice_masks()[0, 1:19])[0]) + 1
    baseline = batch.automatic_gift_count
    step(batch, [eligible])
    step(batch, [0])
    assert batch.automatic_gift_count == baseline and batch.discarded_card_count == 1
    assert not batch.acquisition_snapshot()[:, :, 0].any()


def test_epoch_token_and_mixed_finished_rows_remain_atomic():
    batch = configured(size=2, turns=1).batch
    for env in (0, 1):
        hand(batch, [127], env=env)
    batch.start_environments(ids([0, 1]))
    step(batch, [19, 19])
    step(batch, [1], [0])
    step(batch, [0], [0])
    assert batch.episode_snapshot()[0, 3] == 13
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [1, 0], [1, 0])
    same(before, snapshot(batch))
    batch.reset_environments(ids([0]))
    assert not batch.discard_snapshot()[0].any() and batch.discard_count == 1
    assert batch.discard_snapshot()[1, 0] == 1
    assert not batch.discard_order()[0].any()


def test_python_command_adapter_understands_phase7_without_inventing_private_choice_ids():
    game = configured()
    hand(game.batch, [127])
    game.batch.start_environments(ids([0]))
    for choice in (19, 1, 0):
        context = full_game_decision_contexts(game)[0]
        execute_full_game_commands(
            game,
            [
                FullGameCommand(
                    environment=0,
                    episode=context.episode,
                    decision=context.decision,
                    actor=context.actor,
                    phase=context.phase,
                    choice_id=choice,
                )
            ],
        )
    assert game.batch.discard_count == 1


def test_source_and_metadata_do_not_relabel_removal_as_effect_or_training_coverage():
    game = configured()
    assert PLAN.integrated_artifact_effect_count == 237
    assert PLAN.discard.discardable_models == 128
    assert PLAN.discard.discard_model_ids == tuple(
        m for m, c in PLAN.inventory.profiles if c != 1 and m not in (208, 209)
    )
    assert game.metadata.discard_observation_fields == DISCARD_FIELDS
    assert game.metadata.discard_snapshot_fields == DISCARD_SNAPSHOT_FIELDS
    assert not game.metadata.full_game_training_ready and not game.metadata.promotion_eligible
    assert native.FULL_GAME_MAX_DISCARD_ACTIONS == 64
    assert (
        build_full_game_discard_plan(
            read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
        )
        == PLAN.discard
    )
    assert FullGameMetadata.model_validate_json(game.metadata.model_dump_json()) == game.metadata


@pytest.mark.parametrize(
    "change",
    [
        {"discard_model_ids": (127,)},
        {"catalog_sha256": "0" * 64},
        {"forbidden_exception_model_ids": (208, 201)},
        {"documented_restrictions": ()},
        {"official_fidelity_verified": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
        {"apocalypse_policy": "sacrifice-implemented"},
    ],
)
def test_forged_discard_source_and_readiness_scope_relabeling_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameDiscardPlan.model_validate(PLAN.discard.model_dump() | change)


@pytest.mark.parametrize(
    "values", [[], [127, 127], [35], [208], [209], [1], [245], [999], [127] * 238]
)
def test_raw_discard_profiles_reject_forbidden_unknown_duplicate_or_excessive_models(values):
    with pytest.raises(ValueError, match=r"discard model|inventory model is not registered"):
        native.FullGameBatch(
            1,
            2,
            ids(PLAN.inventory.profiles),
            ids(PLAN.effect_profiles),
            discard_model_ids=ids(values),
        )


def test_optional_discard_omission_keeps_raw_unsupported_fixtures_unchanged():
    batch = native.FullGameBatch(
        1, 2, ids(PLAN.inventory.profiles), ids(PLAN.effect_profiles), capacity=18
    )
    hand(batch, [127])
    batch.start_environments(ids([0]))
    assert not batch.choice_masks()[0, 19] and not batch.discard_snapshot().any()


@pytest.mark.parametrize(
    "values",
    [
        np.asarray([[127]], dtype=np.int64),
        np.asarray([127], dtype=np.float64),
        np.asarray([127], dtype=np.int32),
        np.asarray([127, 0, 191, 0], dtype=np.int64)[::2],
    ],
)
def test_raw_discard_profiles_refuse_shape_dtype_or_implicit_copy(values):
    with pytest.raises(TypeError):
        native.FullGameBatch(
            1, 2, ids(PLAN.inventory.profiles), ids(PLAN.effect_profiles), discard_model_ids=values
        )


@pytest.mark.parametrize(
    "change",
    [
        {"discard_observation_fields": ("actual-role",)},
        {"discard_snapshot_fields": ("hidden-victim",)},
        {"max_discard_actions": 65},
        {"discard_control_choice": "unversioned-new-control"},
    ],
)
def test_metadata_layout_and_control_drift_fail_closed(change):
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(configured().metadata.model_dump() | change)


def test_source_builder_rejects_changed_reference_discard_restrictions():
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    altered = bible.model_copy(
        update={
            "reference_sections": bible.reference_sections
            | {"trade": ("All cards may be discarded.",)}
        }
    )
    with pytest.raises(ValueError, match="source restrictions"):
        build_full_game_discard_plan(read_api_catalog_snapshot(CATALOG), altered)


def test_owned_discard_views_remain_readonly_snapshots_across_mutation_and_reset():
    batch = configured().batch
    hand(batch, [127, 191])
    batch.start_environments(ids([0]))
    step(batch, [19])
    step(batch, [2])
    views = (batch.discard_snapshot(), batch.discard_observations(), batch.discard_order())
    for view in views:
        assert not view.flags.writeable
        with pytest.raises(ValueError):
            view[0, 0] = 99
    step(batch, [0])
    batch.reset_environments(ids([0]))
    assert views[0][0, 0] == 1 and views[1][0, 1] == 1 and views[2][0, 0] == 2
    assert not batch.discard_snapshot().any() and batch.discard_count == 1
