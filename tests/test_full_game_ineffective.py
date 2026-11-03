"""Provisional hidden incompatibility never means free use or missing effects."""

import gc
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import PLAN, game, hand, ids, load, step

from godfield_bot.full_game import FullGameMetadata, create_development_full_game_batch
from godfield_bot.full_game_roles import FullGameRoleManifest, build_full_game_role_manifest

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
ROLES = build_full_game_role_manifest(PLAN)
CATEGORIES = dict(PLAN.inventory.profiles)


def enabled(**options):
    return game(
        role_profiles=ids(ROLES.model_roles),
        resolve_hidden_components=True,
        resolve_hidden_targeting=True,
        **options,
    )


def state(b):
    return tuple(
        getattr(b, name)().copy()
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "cost_snapshot",
            "ineffective_snapshot",
            "ineffective_model_counts",
            "attack_family_snapshot",
            "acquisition_snapshot",
            "hidden_targeting_snapshot",
        )
    )


def cast(b, addition=None):
    step(b, [1])
    if addition is not None:
        step(b, [addition])
    step(b, [0])
    if b.episode_snapshot()[0, 3] == 3:
        step(b, [20])


def response(b, actual, display, *, extra=(), attacker=35, **options):
    hand(b, [attacker])
    hand(b, [(actual, display, 0), *extra], owner=1)
    b.start_environments(ids([0]))
    cast(b)
    assert b.episode_snapshot()[0, [2, 3]].tolist() == [1, 4]
    step(b, [1])
    for i in range(len(extra)):
        step(b, [i + 2])


def test_checked_roles_cover_every_native_context_and_are_owned_readonly():
    b = enabled()
    profiles = b.role_profiles()
    assert profiles.tolist() == [list(r) for r in ROLES.model_roles]
    assert b.resolve_hidden_components
    assert not profiles.flags.writeable
    assert not b.ineffective_snapshot().flags.writeable
    assert not b.ineffective_model_counts().flags.writeable
    del b
    gc.collect()
    assert profiles.shape == (237, 2) and profiles[0, 0] == 3


@pytest.mark.parametrize(
    "option",
    [
        {"role_profiles": None},
        {"armor_profiles": ids([r for r in PLAN.combat.armor_profiles if r[0] != 20])},
        {"attack_profiles": ids([r for r in PLAN.combat.attack_profiles if r[0] != 35])},
        {"boost_profiles": ids([r for r in PLAN.combat.boost_profiles if r[0] != 231])},
        {"passive_profiles": None},
        {"area_profiles": None},
        {"summon_profiles": None},
        {"fate_model_ids": None},
    ],
)
def test_manifest_detects_missing_registration_instead_of_silently_fizzling(option):
    options = dict(role_profiles=ids(ROLES.model_roles), resolve_hidden_components=True)
    options.update(option)
    with pytest.raises(ValueError, match="role manifest"):
        game(**options)


@pytest.mark.parametrize("actual,display", [(78, 108), (6, 20), (54, 49), (91, 24)])
def test_reviewed_wrong_role_or_element_defenses_are_consumed_not_transformed(actual, display):
    b = enabled()
    response(b, actual, display)
    before = b.diagnostic_players()[0, 1, 0]
    step(b, [0])
    assert b.diagnostic_players()[0, 1, 0] == before - 10
    assert b.ineffective_snapshot()[0, [2, 5, 6, 13]].tolist() == [1, 1, 1, 1]
    assert b.ineffective_model_counts()[0, actual - 3] == 1
    assert b.counter_count == 0 and b.attack_count == 1
    assert b.consumed_count == 2


def test_incompatible_counter_has_no_unsolicited_attack_but_compatible_armor_applies():
    b = enabled()
    response(b, 183, 189, extra=(132,), attacker=89)
    step(b, [0])
    assert b.diagnostic_players()[0, 1, 0] == 96  # 8 minus real DEF4
    assert b.counter_count == 0 and b.ineffective_model_counts()[0, 183 - 3] == 1
    assert b.ineffective_snapshot()[0, 13] == 0


@pytest.mark.parametrize(
    "model", [m for m, category in PLAN.inventory.profiles if category in (1, 2, 4)]
)
def test_every_registered_held_family_has_an_explicit_hidden_defense_resolution(model):
    display = {1: 20, 2: 130, 3: 189, 4: 233}[CATEGORIES[model]]
    b = enabled(initial_mp=99)
    response(b, model, display)
    step(b, [0])
    assert b.consumed_count + b.miracle_use_count >= 2
    assert b.ineffective_model_counts().sum() == b.ineffective_snapshot()[0, 5]


@pytest.mark.parametrize(
    "model", [m for m, category in PLAN.inventory.profiles if category in (1, 3, 4)]
)
def test_every_leader_displayable_family_applies_only_its_requested_actual_role(model):
    display = {1: 35, 3: 191, 4: 220}[CATEGORIES[model]]
    b = enabled(initial_mp=99)
    hand(b, [(model, display, 0)])
    load(b, hp=40, mp=99, mask=0)
    b.start_environments(ids([0]))
    cast(b)
    assert b.consumed_count + b.miracle_use_count >= 1
    assert b.ineffective_model_counts().sum() == b.ineffective_snapshot()[0, 3]


def test_actual_special_wins_in_click_order_and_later_numeric_card_is_ineffective():
    b = enabled()
    response(b, 21, 20, extra=(130,))
    step(b, [0])
    assert b.bounce_count == 1
    assert b.ineffective_model_counts()[0, 130 - 3] == 1
    assert b.ineffective_model_counts()[0, 21 - 3] == 0
    assert b.ineffective_snapshot()[0, [2, 5, 12]].tolist() == [1, 1, 1]


def test_later_actual_special_cannot_replace_an_already_effective_numeric_defense():
    b = enabled()
    response(b, 130, 130, extra=((21, 20, 0),))
    step(b, [0])
    assert b.bounce_count == 0 and b.diagnostic_players()[0, 1, 0] == 94
    assert b.ineffective_model_counts()[0, 21 - 3] == 1


def test_later_actual_filter_cannot_retroactively_enable_an_incompatible_defense():
    b = enabled()
    response(b, 130, 130, extra=((189, 130, 0),))
    step(b, [0])
    assert b.filtered_attack_count == 0
    assert b.diagnostic_players()[0, 1, 0] == 94
    assert b.ineffective_model_counts()[0, 189 - 3] == 1


def test_reset_clears_private_ineffectiveness_but_preserves_role_catalog():
    b = enabled()
    response(b, 78, 108)
    step(b, [0])
    old = b.ineffective_snapshot()
    assert old.any()
    b.reset_environments(ids([0]))
    assert not b.ineffective_snapshot().any() and not b.ineffective_model_counts().any()
    assert old.any() and b.role_profiles().tolist() == [list(r) for r in ROLES.model_roles]


def test_addition_only_miracle_as_leader_pays_once_fizzles_and_ticks_once():
    b = enabled()
    hand(b, [(231, 228, 0)])
    b.start_environments(ids([0]))
    cast(b)
    assert b.mp_spent == 6 and b.miracle_use_count == 1
    assert b.attack_count == b.attack_component_count == 0
    assert b.episode_snapshot()[0, [2, 3, 4]].tolist() == [1, 1, 1]
    assert b.ineffective_snapshot()[0, [0, 3, 7, 8, 9]].tolist() == [1, 1, 1, 6, 1]
    assert b.diagnostic_inventory()[0, 0, 0].tolist() == [1, 231, 228, 1]
    assert not b.hidden_targeting_snapshot().any()


def test_incompatible_addition_does_not_invent_a_boost_or_hide_valid_leader():
    b = enabled()
    hand(b, [34, (19, 12, 0)])
    b.start_environments(ids([0]))
    cast(b, 2)
    assert b.pending_observations()[0, 3] == 9
    assert b.attack_component_count == 1 and b.consumed_count == 2
    assert b.ineffective_snapshot()[0, [0, 4, 6, 10]].tolist() == [1, 1, 1, 1]
    step(b, [0])
    assert b.diagnostic_players()[0, 1, 0] == 91


@pytest.mark.parametrize("actual,display", [(220, 235), (235, 220)])
def test_hidden_utility_attack_cross_role_does_not_execute_unrequested_ability(actual, display):
    b = enabled()
    hand(b, [(actual, display, 0)])
    load(b, hp=40, mp=20, mask=0)
    b.start_environments(ids([0]))
    cast(b)
    assert b.utility_count == b.attack_count == 0
    assert b.diagnostic_players()[0, 0, 0] == 40
    assert b.mp_spent == (15 if actual == 220 else 7)
    assert b.ineffective_model_counts()[0, actual - 3] == 1


@pytest.mark.parametrize("reducer", [46, 143, 163, 173, 204])
def test_actual_adjacent_reducer_waives_an_ineffective_miracle_once(reducer):
    b = enabled()
    hand(b, [(235, 220, 0), reducer])
    load(b, mp=0, mask=0)
    b.start_environments(ids([0]))
    cast(b, 2)
    assert b.mp_spent == 0 and b.waived_mp == 7 and b.cost_waiver_count == 1
    assert b.ineffective_snapshot()[0, [3, 7, 8, 9]].tolist() == [1, 1, 0, 1]
    assert b.consumed_count == b.miracle_use_count == 1


def test_hidden_actual_unaffordable_cost_is_atomic_for_entire_batch():
    b = enabled(size=2)
    for env, actual in enumerate((231, 235)):
        hand(b, [(actual, 228, 0)], env=env)
        load(b, env=env, mp=6, mask=0)
    b.start_environments(ids([0, 1]))
    step(b, [1, 1])
    before = state(b)
    with pytest.raises(ValueError, match="unaffordable"):
        step(b, [0, 0])
    for a, c in zip(before, state(b), strict=True):
        np.testing.assert_array_equal(a, c)
    assert b.mp_spent == b.miracle_use_count == 0
    step(b, [0], envs=[0])
    assert b.mp_spent == 6 and b.ineffective_snapshot()[0, 9] == 1


def test_strict_raw_behavior_is_still_default():
    b = game()
    hand(b, [(231, 228, 0)])
    b.start_environments(ids([0]))
    step(b, [1])
    with pytest.raises(ValueError, match="cannot lead"):
        step(b, [0])
    assert not b.resolve_hidden_components and not b.ineffective_snapshot().any()


def test_source_factory_pins_rule_and_manifest_but_never_claims_training_readiness():
    engine = create_development_full_game_batch(
        catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
        bible_path=Path("data/snapshots/2026-09-20/bible.json"),
        batch_size=1,
        player_count=3,
        capacity=18,
    )
    assert engine.batch.resolve_hidden_components
    assert engine.metadata.roles == ROLES
    assert engine.metadata.schema_version == 31
    assert not engine.metadata.local_training_eligible and not engine.metadata.promotion_eligible
    data = engine.metadata.model_dump()
    data["resolve_hidden_components"] = False
    with pytest.raises(ValidationError):
        FullGameMetadata.model_validate(data)
    data = ROLES.model_dump()
    data["model_roles"] = ((3, 1), *ROLES.model_roles[1:])
    with pytest.raises(ValidationError):
        FullGameRoleManifest.model_validate(data)
