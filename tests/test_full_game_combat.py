"""Combat phases joined to native resources, inventory, turns and atomic batches."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    build_full_game_plan,
    create_development_full_game_batch,
    execute_full_game_commands,
    full_game_decision_contexts,
)
from godfield_bot.full_game_combat_plan import FULL_GAME_COMBAT_SHA256, FullGameCombatPlan
from godfield_bot.full_game_combat_smoke import (
    FullGameCombatSmokeReport,
    run_full_game_combat_smoke,
)
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


def game(
    *,
    size=1,
    players=3,
    capacity=8,
    max_turns=1000,
    max_decisions=4000,
    attacks=None,
    armor=None,
    seed=67,
):
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        capacity,
        seed,
        max_turns,
        max_decisions,
        40,
        20,
        0,
        ids(PLAN.combat.attack_profiles if attacks is None else attacks),
        ids(PLAN.combat.armor_profiles if armor is None else armor),
    )


def load(batch, *, env=0, owner=0, hp=40, mp=20, illness=0, mask=0):
    batch.seed_players(ids([env]), ids([owner]), ids([[hp, mp, 0, illness]]), ids([mask]))


def seed(batch, cards, *, env=0, owner=0):
    batch.seed_hand(env, owner, ids(cards).reshape(-1, 4))


def step(batch, choices, envs=None):
    envs = list(range(len(choices))) if envs is None else envs
    episode = batch.episode_snapshot()
    command = ids(
        [[env, *episode[env, :4], choice] for env, choice in zip(envs, choices, strict=True)]
    ).reshape(-1, 6)
    batch.step(command)
    return command


def state(batch):
    return (
        batch.episode_snapshot(),
        batch.diagnostic_players(),
        batch.diagnostic_inventory(),
        batch.actor_hands(),
        batch.player_observations(),
        batch.choice_masks(),
        batch.pending_observations(),
        batch.selected_defenses(),
        (
            batch.action_count,
            batch.pass_count,
            batch.utility_count,
            batch.attack_count,
            batch.resolved_attack_count,
            batch.defense_toggle_count,
            batch.hp_damage,
            batch.mp_spent,
            batch.consumed_count,
            batch.miracle_use_count,
            batch.restored_count,
        ),
    )


def same(batch, previous):
    current = state(batch)
    for a, b in zip(current[:-1], previous[:-1], strict=True):
        np.testing.assert_array_equal(a, b)
    assert current[-1] == previous[-1]


def begin(batch, model=35, *, armor=(), target=1, capacity=8):
    seed(batch, [(1, model, 0, 0)], owner=0)
    seed(batch, [(10 + i, card, 0, 0) for i, card in enumerate(armor)], owner=target)
    batch.start_environments(ids([0]))
    step(batch, [1])
    if batch.episode_snapshot()[0, 3] == 2:
        step(batch, [0])  # Source-pinned factory has explicit attack confirmation.
    step(batch, [capacity + 1 + target])


@pytest.mark.parametrize("profile", PLAN.combat.attack_profiles)
def test_all_source_pinned_attacks_join_costs_inventory_and_turns(profile):
    model, attack, element, origin, cost = profile
    batch = game()
    seed(batch, [(1, model, 0, 0), (2, 191, 0, 0)])
    load(batch, illness=1)
    load(batch, owner=1, illness=2)
    batch.start_environments(ids([0]))
    old = step(batch, [1])
    assert batch.episode_snapshot()[0, 2:5].tolist() == [0, 3, 0]
    assert batch.diagnostic_players()[0, 0, :2].tolist() == [40, 20]
    assert batch.consumed_count == batch.miracle_use_count == batch.attack_count == 0
    assert batch.pending_observations()[0, :6].tolist() == [1, 0, -1, attack, element, origin]
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [10, 11]
    before = state(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.step(old)
    same(batch, before)
    step(batch, [10])
    assert batch.episode_snapshot()[0, 2:5].tolist() == [1, 4, 0]
    assert batch.pending_observations()[0, :6].tolist() == [1, 0, 1, attack, element, origin]
    assert batch.diagnostic_players()[0, 0, :2].tolist() == [40, 20 - cost]
    assert batch.actor_hands()[0, 0].tolist() == [0, 0, 0]  # Defender's own hand.
    assert batch.attack_count == 1 and batch.mp_spent == cost
    if origin:
        assert batch.diagnostic_inventory()[0, 0, :2].tolist() == [[2, 191, 0, 0], [1, model, 0, 1]]
        assert batch.miracle_use_count == 1 and batch.consumed_count == 0
    else:
        assert batch.diagnostic_inventory()[0, 0, 0].tolist() == [2, 191, 0, 0]
        assert batch.consumed_count == 1 and batch.miracle_use_count == 0
    step(batch, [0])
    actual_damage = 40 if element == 6 else attack
    assert batch.diagnostic_players()[0, 1].tolist() == [40 - actual_damage, 20, 0, 2, 0, 0]
    assert batch.diagnostic_players()[0, 0, 0] == 39
    assert batch.diagnostic_players()[0, 0, 5] == 1
    assert batch.episode_snapshot()[0, 2:5].tolist() == [2 if element == 6 else 1, 1, 1]
    assert batch.episode_snapshot()[0, 7] == 3
    assert batch.action_count == 3 and batch.pass_count == batch.utility_count == 0
    assert batch.resolved_attack_count == 1 and batch.hp_damage == actual_damage
    assert not np.any(batch.pending_observations())


@pytest.mark.parametrize("profile", PLAN.combat.armor_profiles)
def test_all_ordinary_armor_consumes_only_confirmed_owned_cards(profile):
    model, defense, _, _, _ = profile
    batch = game()
    begin(batch, armor=(model, 194))
    old = batch.actor_hands()
    step(batch, [1])
    assert batch.pending_observations()[0, 6:9].tolist() == [defense, 1, 1]
    assert batch.selected_defenses()[0, :2].tolist() == [True, False]
    assert batch.consumed_count == 1 and batch.diagnostic_players()[0, 1, 0] == 40
    assert batch.actor_hands()[0].tolist() == old[0].tolist()
    step(batch, [0])
    assert batch.diagnostic_inventory()[0, 1, 0].tolist() == [11, 194, 0, 0]
    assert batch.consumed_count == 2 and batch.defense_toggle_count == 1
    assert batch.hp_damage == max(0, 10 - defense)
    assert batch.diagnostic_players()[0, 1, 0] == 40 - max(0, 10 - defense)
    assert not np.any(batch.selected_defenses())


@pytest.mark.parametrize("attack_element", range(7))
@pytest.mark.parametrize("defense_element", range(7))
def test_element_compatibility_masks_are_rechecked_on_native_dispatch(
    attack_element, defense_element
):
    # Synthetic profiles isolate pure element arithmetic, not new official cards.
    batch = game(attacks=[(6, 10, attack_element, 0, 0)], armor=[(113, 4, defense_element, 0, 0)])
    begin(batch, model=6, armor=(113,))
    compatible = attack_element in (0, 6) or (
        attack_element in (1, 2, 3, 4)
        and defense_element in ({1: 2, 2: 1, 3: 4, 4: 3}[attack_element], 5)
    )
    assert batch.choice_masks()[0, 1] == compatible
    if compatible:
        step(batch, [1])
    else:
        before = state(batch)
        with pytest.raises(ValueError, match="unavailable"):
            step(batch, [1])
        same(batch, before)
    step(batch, [0])
    assert batch.hp_damage == (40 if attack_element == 6 else 6 if compatible else 10)


def test_multicard_toggle_flash_undo_and_bounded_confirm_only_liveness():
    batch = game()
    load(batch, owner=1, mask=4)
    begin(batch, armor=(118, 123))
    step(batch, [1])
    assert batch.choice_masks()[0, :3].tolist() == [True, True, False]
    before = state(batch)
    with pytest.raises(ValueError):
        step(batch, [2])
    same(batch, before)
    step(batch, [1])  # Undo remains available under Flash.
    assert batch.choice_masks()[0, :3].tolist() == [True, True, True]
    step(batch, [2])
    for _ in range(61):
        step(batch, [2])
    assert batch.defense_toggle_count == 64
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]
    before = state(batch)
    with pytest.raises(ValueError):
        step(batch, [2])
    same(batch, before)
    step(batch, [0])
    assert batch.resolved_attack_count == 1 and batch.episode_snapshot()[0, 4] == 1


def test_additive_armor_never_aliases_attacker_hand_and_undo_does_not_consume():
    batch = game()
    begin(batch, armor=(118, 123, 130))
    step(batch, [1])
    step(batch, [2])
    step(batch, [3])
    step(batch, [2])
    assert batch.pending_observations()[0, 6:8].tolist() == [6, 2]
    step(batch, [0])
    assert batch.diagnostic_inventory()[0, 1, 0].tolist() == [11, 123, 0, 0]
    assert batch.consumed_count == 3 and batch.hp_damage == 4
    assert not np.any(batch.diagnostic_inventory()[0, 0])


@pytest.mark.parametrize("players", [2, 3, 9])
def test_target_legality_elimination_and_next_turn_origin(players):
    batch = game(players=players)
    if players > 2:
        load(batch, owner=1, hp=0)
    target = 1 if players == 2 else players - 1
    load(batch, owner=target, hp=2, illness=4)
    seed(batch, [(1, 35, 0, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    mask = batch.choice_masks()[0]
    assert not mask[9]  # self
    if players > 2:
        assert not mask[10]  # dead
    assert not np.any(mask[:9]) and not np.any(mask[9 + players :])
    for choice in (0, 1, 9, 9 + players, -(2**63), 2**63 - 1):
        before = state(batch)
        with pytest.raises(ValueError):
            step(batch, [choice])
        same(batch, before)
    step(batch, [9 + target])
    step(batch, [0])
    assert batch.diagnostic_players()[0, target, 0] == 0  # No Heaven resurrection.
    if players == 2 or players == 3:
        assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, 1, 0]
    else:
        # Advance from the attacker, not from the defender at seat eight.
        assert batch.episode_snapshot()[0, 2:5].tolist() == [2, 1, 1]


@pytest.mark.parametrize(
    "owner_hp,owner_illness,target_hp,outcome,winner",
    [(40, 0, 5, 1, 0), (1, 3, 40, 1, 1), (1, 3, 5, 2, -1)],
)
def test_joint_attacker_disease_and_defender_damage_endings_precede_limits(
    owner_hp, owner_illness, target_hp, outcome, winner
):
    batch = game(players=2, max_turns=1, max_decisions=3)
    load(batch, hp=owner_hp, illness=owner_illness)
    load(batch, owner=1, hp=target_hp)
    begin(batch)
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3:7].tolist() == [12, 1, outcome, winner]
    assert not np.any(batch.choice_masks())
    assert batch.diagnostic_players()[0, 0, 5] == 1
    assert batch.diagnostic_players()[0, 1, 5] == 0


@pytest.mark.parametrize("limit", [1, 2, 3, 4])
def test_decision_limits_truncate_intermediate_phases_without_fabricated_outcomes(limit):
    batch = game(max_decisions=limit)
    seed(batch, [(1, 211, 0, 0)])
    seed(batch, [(2, 113, 0, 0)], owner=1)
    batch.start_environments(ids([0]))
    for command in (1, 10, 0, 0):
        if batch.episode_snapshot()[0, 3] == 13:
            break
        step(batch, [command])
    assert batch.episode_snapshot()[0, 5:7].tolist() == [4, -1]
    assert batch.action_count == limit and not np.any(batch.choice_masks())
    assert not np.any(batch.pending_observations()) and not np.any(batch.selected_defenses())


def test_hidden_attack_value_and_cost_do_not_leak_until_cast_or_error():
    batch = game(size=2)
    for env in range(2):
        load(batch, env=env, mp=2, mask=2)
        seed(batch, [(1, 218 if env else 211, 211, 0)], env=env)
    batch.start_environments(ids([0, 1]))
    step(batch, [1, 1])
    for view in (
        batch.actor_hands(),
        batch.pending_observations(),
        batch.choice_masks(),
        batch.player_observations(),
    ):
        np.testing.assert_array_equal(view[0], view[1])
    before = state(batch)
    with pytest.raises(ValueError, match="unaffordable"):
        step(batch, [10, 10])
    same(batch, before)
    step(batch, [10], [0])
    assert batch.mp_spent == 2 and batch.miracle_use_count == 1


def test_supported_dream_attack_resolves_actual_value_and_retains_displayed_handle():
    batch = game()
    load(batch, mask=2)
    seed(batch, [(1, 218, 211, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert batch.pending_observations()[0, 3] == 4
    step(batch, [10])
    assert batch.pending_observations()[0, 3] == 25
    assert batch.diagnostic_inventory()[0, 0, 0].tolist() == [1, 218, 211, 1]
    step(batch, [0])
    assert batch.hp_damage == 25 and batch.mp_spent == 12


@pytest.mark.parametrize("true_model", [9, 239])
def test_unsupported_disguised_attack_fails_atomically_at_cast(true_model):
    # Use weapon 6 disguise for weapon 9, miracle 211 for miracle 239 (Release).
    display = 6 if true_model == 9 else 211
    batch = game()
    seed(batch, [(1, true_model, display, 0)])
    batch.start_environments(ids([0]))
    step(batch, [1])
    before = state(batch)
    with pytest.raises(ValueError, match="not implemented"):
        step(batch, [10])
    same(batch, before)


@pytest.mark.parametrize(
    "true_model,display,attack,error",
    [
        (189, 113, 35, "not implemented"),
        (119, 115, 59, "incompatible"),
    ],
)
def test_disguised_armor_errors_do_not_leak_through_displayed_masks_or_half_consume(
    true_model, display, attack, error
):
    batch = game(size=2)
    for env in range(2):
        seed(batch, [(1, attack, 0, 0)], env=env)
        seed(batch, [(2, true_model if env else display, display, 0)], env=env, owner=1)
    batch.start_environments(ids([0, 1]))
    step(batch, [1, 1])
    step(batch, [10, 10])
    np.testing.assert_array_equal(batch.choice_masks()[0], batch.choice_masks()[1])
    step(batch, [1, 1])
    before = state(batch)
    with pytest.raises(ValueError, match=error):
        step(batch, [0, 0])
    same(batch, before)
    step(batch, [1], [1])  # Can undo a disguised unsupported defense and forgive.
    step(batch, [0, 0])
    assert batch.resolved_attack_count == 2


def combat_rank(env, bound, seed=67, epoch=1):
    mask = 2**64 - 1
    first, second, third = 0x9E3779B97F4A7C15, 0xBF58476D1CE4E5B9, 0x94D049BB133111EB
    state = seed ^ (((env + 1) * first) & mask) ^ ((epoch * second) & mask) ^ 0xD2B74407B1CE6E93
    for _ in range(16):
        state = (state + first) & mask
        word = ((state ^ (state >> 30)) * second) & mask
        word = ((word ^ (word >> 27)) * third) & mask
        word ^= word >> 31
        if word >= (2**64 % bound):
            return word % bound
    raise AssertionError("reference sampling bound exhausted")


def test_fog_samples_living_enemy_natively_and_failed_late_rows_preserve_rng():
    first, second = game(size=64, players=9), game(size=64, players=9)
    for batch in (first, second):
        for env in range(64):
            load(batch, env=env, mask=1, illness=1)
            load(batch, env=env, owner=2, hp=0)
            seed(batch, [(1, 35, 0, 0)], env=env)
        batch.start_environments(ids(range(64)))
        step(batch, [1] * 64)
    before = state(first)
    with pytest.raises(ValueError):
        step(first, [10] * 63 + [11])  # dead target in last environment
    same(first, before)
    for batch in (first, second):
        step(batch, [10] * 64)
    same(first, state(second))
    eligible = [1, 3, 4, 5, 6, 7, 8]
    targets = first.episode_snapshot()[:, 2]
    assert targets.tolist() == [eligible[combat_rank(env, 7)] for env in range(64)]
    assert set(targets) == set(eligible)
    for batch in (first, second):
        step(batch, [0] * 64)
    same(first, state(second))


def test_mixed_phase_batch_rejection_preserves_all_owners_selection_ticks_and_rng():
    batch = game(size=3)
    for env in range(3):
        load(batch, env=env, hp=30, illness=1)
        seed(batch, [(1, 194, 0, 0), (2, 35, 0, 0)], env=env)
        seed(batch, [(3, 113, 0, 0)], env=env, owner=1)
    batch.start_environments(ids([0, 1, 2]))
    step(batch, [2, 2], [1, 2])
    step(batch, [10], [2])
    step(batch, [1], [2])
    before = state(batch)
    with pytest.raises(ValueError):
        step(batch, [1, 10, 99])
    same(batch, before)
    step(batch, [1, 10, 0])
    assert batch.utility_count == 1 and batch.attack_count == 2 and batch.resolved_attack_count == 1
    assert batch.diagnostic_players()[0, 0, 0] == 49
    assert batch.diagnostic_players()[2, 1, 0] == 31


def test_reset_pending_selection_views_copy_and_command_protocol_parity():
    configured = create_development_full_game_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=1, capacity=8
    )
    batch = configured.batch
    begin(batch, armor=(113,))
    for choice in (1, 0):
        context = full_game_decision_contexts(configured)[0]
        execute_full_game_commands(
            configured,
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
        if choice:
            pending, selected = batch.pending_observations(), batch.selected_defenses()
    assert pending[0, 7] == 1 and selected[0, 0]
    assert not pending.flags.writeable and not selected.flags.writeable
    batch.reset_environments(ids([0]))
    assert batch.episode_snapshot()[0, :4].tolist() == [2, 1, 0, 0]
    assert not np.any(batch.pending_observations()) and not np.any(batch.selected_defenses())
    assert pending[0, 7] == 1 and selected[0, 0]
    assert batch.attack_count == batch.resolved_attack_count == 1


@pytest.mark.parametrize(
    "change",
    [
        {"attack_profiles": ((6, 100, 0, 0, 0),)},
        {"armor_profiles": ((113, 100, 0, 0, 0),)},
        {"attack_fields": ("actual_hidden_id",)},
        {"armor_fields": ("value",)},
        {"combat_effect_count": 237},
        {"timing_and_hidden_resolution_verified": True},
    ],
)
def test_combat_plan_cannot_forge_profile_coverage_or_fidelity(change):
    assert PLAN.combat.profile_sha256 == FULL_GAME_COMBAT_SHA256
    assert PLAN.integrated_artifact_effect_count == 154
    with pytest.raises(ValidationError):
        FullGameCombatPlan.model_validate({**PLAN.combat.model_dump(), **change})


@pytest.mark.parametrize(
    "attacks,armor",
    [
        ([], [(113, 1, 0, 0, 0)]),
        ([(6, 1, 0, 0, 0)], []),
        ([(6, 1, 0, 0)], [(113, 1, 0, 0, 0)]),
        ([(6, 1, 0, 0, 0)] * 2, [(113, 1, 0, 0, 0)]),
        ([(6, 1, 0, 1, 2)], [(113, 1, 0, 0, 0)]),
        ([(211, 1, 0, 1, 0)], [(113, 1, 0, 0, 0)]),
        ([(6, 0, 0, 0, 0)], [(113, 1, 0, 0, 0)]),
        ([(6, 1, 7, 0, 0)], [(113, 1, 0, 0, 0)]),
        ([(6, 1, 0, 0, 0)], [(113, 1, 0, 1, 0)]),
        ([(6, 1, 0, 0, 0)], [(113, 1, 0, 0, 1)]),
        ([(6, 1, 0, 0, 0)], [(6, 1, 0, 0, 0)]),
    ],
)
def test_native_combat_profiles_reject_malformed_bounds_and_wrong_categories(attacks, armor):
    with pytest.raises((ValueError, TypeError)):
        game(attacks=attacks, armor=armor)


def test_native_combat_profile_pair_is_required_and_can_be_explicitly_absent():
    args = (1, 2, ids(PLAN.inventory.profiles), ids(PLAN.effect_profiles))
    with pytest.raises(ValueError, match="together"):
        native.FullGameBatch(*args, attack_profiles=ids(PLAN.combat.attack_profiles))
    batch = native.FullGameBatch(*args)
    seed(batch, [(1, 35, 0, 0)])
    batch.start_environments(ids([0]))
    assert np.flatnonzero(batch.choice_masks()[0]).tolist() == [0]


@pytest.mark.parametrize("players", [2, 3, 9])
@pytest.mark.parametrize("turn_limit", [1, 64])
def test_full_combat_smoke_finishes_or_explicitly_truncates_reproducibly(players, turn_limit):
    options = dict(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=16,
        player_count=players,
        max_turns=turn_limit,
    )
    first = run_full_game_combat_smoke(**options)
    assert first == run_full_game_combat_smoke(**options)
    assert (
        first.winners
        + first.all_dead_draws
        + first.turn_limit_truncations
        + first.decision_limit_truncations
        == 16
    )
    assert first.attacks_cast > 0 if turn_limit > 1 else first.utilities > 0
    assert first.defense_toggles > 0 if turn_limit > 1 else first.attacks_resolved == 0
    assert first.unfinished == 0 and first.actions <= 16 * turn_limit * 8
    assert first.winners > 0 if turn_limit > 1 else first.turn_limit_truncations == 16
    assert not first.local_training_eligible and not first.full_game_training_ready
    assert not first.teacher_or_reward_dataset_eligible and not first.official_fidelity_verified
    assert not first.promotion_eligible
    assert FullGameCombatSmokeReport.model_validate_json(first.model_dump_json()) == first


@pytest.mark.parametrize(
    "change",
    [
        {"winners": 500},
        {"actions": 0},
        {"completed_turns": 99999},
        {"attacks_cast": 0},
        {"defense_toggles": -1},
        {"max_decisions": True},
        {"local_training_eligible": True},
        {"teacher_or_reward_dataset_eligible": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
    ],
)
def test_combat_probe_cannot_relabel_diagnostics_or_forge_outcome_accounting(change):
    report = run_full_game_combat_smoke(catalog_path=CATALOG, bible_path=BIBLE, batch_size=2)
    with pytest.raises(ValidationError):
        FullGameCombatSmokeReport.model_validate({**report.model_dump(), **change})


def test_combat_probe_uses_public_views_not_true_inventory_diagnostics(monkeypatch):
    from dataclasses import replace

    import godfield_bot.full_game_combat_smoke as smoke

    options = dict(catalog_path=CATALOG, bible_path=BIBLE, batch_size=4)
    reference = run_full_game_combat_smoke(**options)
    factory = smoke.create_development_full_game_batch

    class DiagnosticsRedacted:
        def __init__(self, batch):
            self.batch = batch

        def __getattr__(self, name):
            return getattr(self.batch, name)

        def diagnostic_players(self):
            return np.zeros_like(self.batch.diagnostic_players())

        def diagnostic_inventory(self):
            return np.zeros_like(self.batch.diagnostic_inventory())

    def redacted_factory(**kwargs):
        configured = factory(**kwargs)
        return replace(configured, batch=DiagnosticsRedacted(configured.batch))

    monkeypatch.setattr(smoke, "create_development_full_game_batch", redacted_factory)
    redacted = run_full_game_combat_smoke(**options)
    assert reference.diagnostic_replay_sha256 != redacted.diagnostic_replay_sha256
    assert reference.model_dump(exclude={"diagnostic_replay_sha256"}) == redacted.model_dump(
        exclude={"diagnostic_replay_sha256"}
    )


def test_combat_probe_cli_has_explicit_offline_scope(monkeypatch):
    import json

    from typer.testing import CliRunner

    from godfield_bot.cli import app

    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(app, ["simulation", "full-game-combat-smoke", "--batch-size", "4"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ruleset_id"] == "integrated-full-game-development-v5"
    assert report["winners"] > 0 and report["attacks_resolved"] > 0
    assert not report["local_training_eligible"] and not report["promotion_eligible"]


@pytest.mark.parametrize("phase", [3, 4])
@pytest.mark.parametrize(
    "column,value",
    [(0, -1), (0, 1), (1, 0), (1, 2), (2, 1), (3, 8), (4, 1), (5, 2**63 - 1), (5, -(2**63))],
)
def test_combat_phase_envelopes_fail_native_admission_without_any_state_change(
    phase, column, value
):
    batch = game()
    seed(batch, [(1, 35, 0, 0)])
    seed(batch, [(2, 113, 0, 0)], owner=1)
    batch.start_environments(ids([0]))
    step(batch, [1])
    if phase == 4:
        step(batch, [10])
    context = batch.episode_snapshot()[0]
    command = ids([[0, *context[:4], 10 if phase == 3 else 1]])
    command[0, column] = value
    before = state(batch)
    with pytest.raises(ValueError):
        batch.step(command)
    same(batch, before)


def test_gifts_do_not_change_fog_or_disease_randomness_and_reset_rekeys_combat():
    first, second = game(size=32, players=9, capacity=64), game(size=32, players=9, capacity=64)
    for epoch in (1, 2):
        for batch in (first, second):
            for env in range(32):
                load(batch, env=env, illness=4, mask=1)
                load(batch, env=env, owner=8, mask=2)
                seed(batch, [(1, 35, 0, 0)], env=env)
        for env in range(32):
            first.deal_cards(ids([env] * 32), ids([8] * 32), ids(range(10, 42)), ids([6] * 32))
        for batch in (first, second):
            batch.start_environments(ids(range(32)))
            step(batch, [1] * 32)
            step(batch, [66] * 32)
        assert first.episode_snapshot()[:, 2].tolist() == [
            1 + combat_rank(env, 8, epoch=epoch) for env in range(32)
        ]
        np.testing.assert_array_equal(first.episode_snapshot(), second.episode_snapshot())
        for batch in (first, second):
            step(batch, [0] * 32)
        np.testing.assert_array_equal(first.diagnostic_players(), second.diagnostic_players())
        for batch in (first, second):
            batch.reset_environments(ids(range(32)))
