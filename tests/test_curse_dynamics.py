"""Portable status mechanics, trusted-caller boundaries, and legacy compatibility."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.curse_dynamics import (
    CURSE_DYNAMICS_RULESET_ID,
    CURSE_PROFILE_SHA256,
    CurseDynamicsMetadata,
    CurseDynamicsPlan,
    build_curse_dynamics_plan,
    create_provisional_curse_dynamics_batch,
)
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError
from godfield_bot.simulation import create_attack_defense_simulation
from godfield_bot.simulation_policy import build_curriculum_heuristic, curriculum_heuristic_actions

np = pytest.importorskip("numpy")
native = pytest.importorskip("godfield_sim")
CATALOG = Path("data/snapshots/2026-10-01/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def ids(values):
    return np.asarray(values, dtype=np.int64)


def game(*, size=2, players=3, hp=40):
    return native.CurseDynamicsBatch(size, players, hp)


def load(batch, *, env=0, player=0, hp=40, illness=0, mask=0):
    batch.load_players(ids([env]), ids([player]), ids([hp]), ids([illness]), ids([mask]))


def tick(batch, *, env=0, player=0, ticket=99, expected=None):
    if expected is None:
        expected = int(batch.snapshot()[env, player, 3])
    batch.finish_turns(ids([env]), ids([player]), ids([expected]), ids([ticket]))


def states(batch):
    return (
        batch.snapshot(),
        batch.transition_snapshot(),
        (
            batch.illness_count,
            batch.curse_count,
            batch.cure_count,
            batch.tick_count,
            batch.death_count,
        ),
    )


def assert_unchanged(batch, before):
    after = states(batch)
    np.testing.assert_array_equal(after[0], before[0])
    np.testing.assert_array_equal(after[1], before[1])
    assert after[2] == before[2]


@pytest.mark.parametrize("players", [2, 3, 9])
def test_all_illness_stages_hp_boundaries_and_100_progression_tickets(players):
    cases = [
        (hp, stage, ticket)
        for hp in (1, 2, 5, 6, 96, 100)
        for stage in range(5)
        for ticket in range(100)
    ]
    batch = game(size=len(cases), players=players)
    envs = ids(range(len(cases)))
    owners = ids([players - 1] * len(cases))
    batch.load_players(
        envs,
        owners,
        ids([hp for hp, _, _ in cases]),
        ids([stage for _, stage, _ in cases]),
        ids([15] * len(cases)),
    )
    batch.finish_turns(envs, owners, ids([0] * len(cases)), ids([ticket for _, _, ticket in cases]))
    snapshot = batch.snapshot()
    transitions = batch.transition_snapshot()
    for env, (hp, stage, ticket) in enumerate(cases):
        new_hp = min(100, hp + 5) if stage == 4 else max(0, hp - (0, 1, 2, 5)[stage])
        new_stage = stage
        if new_hp and stage and ticket < 5:
            if stage == 4:
                new_hp = 0
            else:
                new_stage += 1
        np.testing.assert_array_equal(snapshot[env, players - 1], ids([new_hp, new_stage, 15, 1]))
        np.testing.assert_array_equal(
            transitions[env, players - 1], ids([5, hp, stage, 15, new_hp - hp, int(new_hp == 0)])
        )
    np.testing.assert_array_equal(snapshot[:, 0], np.tile(ids([40, 0, 0, 0]), (len(cases), 1)))
    assert batch.tick_count == len(cases)
    assert batch.death_count == np.count_nonzero(snapshot[:, players - 1, 0] == 0)


@pytest.mark.parametrize("current", range(5))
@pytest.mark.parametrize("incoming", range(1, 5))
def test_repeated_illness_advances_exactly_one_stage_not_incoming_stage(current, incoming):
    batch = game()
    load(batch, illness=current, mask=15)
    batch.apply_illnesses(ids([0]), ids([0]), ids([incoming]))
    expected = incoming if current == 0 else min(4, current + 1)
    np.testing.assert_array_equal(
        batch.snapshot()[0, 0], ids([0 if current == 4 else 40, expected, 15, 0])
    )
    assert batch.illness_count == 1
    assert batch.death_count == int(current == 4)


@pytest.mark.parametrize("scope", [1, 2])
def test_documented_cures_for_every_illness_and_mask_combination(scope):
    cases = [(stage, mask) for stage in range(5) for mask in range(16)]
    batch = game(size=len(cases))
    envs = ids(range(len(cases)))
    players = ids([1] * len(cases))
    batch.load_players(
        envs,
        players,
        ids([40] * len(cases)),
        ids([stage for stage, _ in cases]),
        ids([mask for _, mask in cases]),
    )
    for env, (stage, mask) in enumerate(cases):
        cured_stage = 0 if scope == 2 or stage <= 2 else stage
        cured_mask = 0 if scope == 2 else mask & ~5
        if (cured_stage, cured_mask) == (stage, mask):
            before = states(batch)
            with pytest.raises(ValueError, match="does not affect"):
                batch.cure_players(ids([env]), ids([1]), ids([scope]))
            assert_unchanged(batch, before)
        else:
            batch.cure_players(ids([env]), ids([1]), ids([scope]))
        np.testing.assert_array_equal(
            batch.snapshot()[env, 1], ids([40, cured_stage, cured_mask, 0])
        )


def test_mild_cure_does_not_clear_dream_dark_cloud_hell_or_heaven():
    batch = game()
    load(batch, illness=3, mask=15)
    batch.cure_players(ids([0]), ids([0]), ids([1]))
    np.testing.assert_array_equal(batch.snapshot()[0, 0], ids([40, 3, 10, 0]))
    tick(batch)
    assert batch.snapshot()[0, 0, 0] == 35
    batch.cure_players(ids([0]), ids([0]), ids([2]))
    tick(batch, ticket=0)
    np.testing.assert_array_equal(batch.snapshot()[0, 0], ids([35, 0, 0, 2]))


def test_cure_before_owner_tick_prevents_damage_and_does_not_affect_other_players():
    batch = game()
    load(batch, illness=1, hp=1, mask=5)
    load(batch, player=1, illness=3, mask=10)
    batch.cure_players(ids([0]), ids([0]), ids([1]))
    tick(batch, ticket=0)
    np.testing.assert_array_equal(batch.snapshot()[0, 0], ids([1, 0, 0, 1]))
    np.testing.assert_array_equal(batch.snapshot()[0, 1], ids([40, 3, 10, 0]))
    assert batch.death_count == 0


def test_non_disease_curses_accumulate_idempotently_and_do_not_change_illness():
    batch = game()
    load(batch, illness=2)
    for bit in (1, 2, 4, 8, 1, 2, 4, 8):
        batch.apply_curses(ids([0]), ids([0]), ids([bit]))
    np.testing.assert_array_equal(batch.snapshot()[0, 0], ids([40, 2, 15, 0]))
    assert batch.curse_count == 8
    assert tuple(
        getattr(native, name)
        for name in ("CURSE_FOG_BIT", "CURSE_DREAM_BIT", "CURSE_FLASH_BIT", "CURSE_DARK_CLOUD_BIT")
    ) == (1, 2, 4, 8)


def test_stale_tick_and_duplicate_player_rejection_is_atomic():
    batch = game()
    load(batch, illness=1)
    tick(batch, ticket=99)
    before = states(batch)
    with pytest.raises(ValueError, match="stale"):
        batch.finish_turns(ids([1, 0]), ids([0, 0]), ids([0, 0]), ids([0, 0]))
    assert_unchanged(batch, before)
    with pytest.raises(ValueError, match="duplicate"):
        batch.finish_turns(ids([1, 1]), ids([1, 1]), ids([0, 0]), ids([99, 99]))
    assert_unchanged(batch, before)
    load(batch, hp=40, illness=3)
    assert batch.snapshot()[0, 0, 3] == 1  # Synchronizing HP preserves the tick token.
    with pytest.raises(ValueError, match="stale"):
        tick(batch, expected=0)


@pytest.mark.parametrize("operation", ["illness", "curse", "cure", "tick"])
def test_dead_players_cannot_act_or_be_healed_by_status_operations(operation):
    batch = game()
    load(batch, player=1, hp=0, illness=4, mask=15)
    before = states(batch)
    calls = {
        "illness": lambda: batch.apply_illnesses(ids([1, 0]), ids([0, 1]), ids([1, 1])),
        "curse": lambda: batch.apply_curses(ids([1, 0]), ids([0, 1]), ids([1, 1])),
        "cure": lambda: batch.cure_players(ids([1, 0]), ids([0, 1]), ids([2, 2])),
        "tick": lambda: batch.finish_turns(ids([1, 0]), ids([0, 1]), ids([0, 0]), ids([99, 99])),
    }
    with pytest.raises(ValueError, match="dead"):
        calls[operation]()
    assert_unchanged(batch, before)
    assert batch.death_count == 0  # External combat HP loading is not a curse death.


@pytest.mark.parametrize(
    "operation,bad",
    [
        ("hp", -1),
        ("hp", 101),
        ("stage", -1),
        ("stage", 5),
        ("mask", -1),
        ("mask", 16),
        ("incoming", 0),
        ("incoming", 5),
        ("bit", 0),
        ("bit", 3),
        ("bit", 16),
        ("scope", 0),
        ("scope", 3),
        ("ticket", -1),
        ("ticket", 100),
    ],
)
def test_invalid_later_row_rejects_whole_batch_and_preserves_counters(operation, bad):
    batch = game()
    load(batch, env=1, illness=1, mask=5)
    envs, players = ids([1, 0]), ids([0, 0])
    before = states(batch)
    with pytest.raises(ValueError):
        if operation in ("hp", "stage", "mask"):
            batch.load_players(
                envs,
                players,
                ids([1, bad if operation == "hp" else 1]),
                ids([1, bad if operation == "stage" else 1]),
                ids([1, bad if operation == "mask" else 1]),
            )
        elif operation == "incoming":
            batch.apply_illnesses(envs, players, ids([1, bad]))
        elif operation == "bit":
            batch.apply_curses(envs, players, ids([1, bad]))
        elif operation == "scope":
            batch.cure_players(envs, players, ids([2, bad]))
        else:
            batch.finish_turns(envs, players, ids([0, 0]), ids([99, bad]))
    assert_unchanged(batch, before)


@pytest.mark.parametrize("bad_env,bad_player", [(-1, 0), (2, 0), (0, -1), (0, 3)])
def test_invalid_seat_or_environment_does_not_mutate_first_row(bad_env, bad_player):
    batch = game()
    before = states(batch)
    with pytest.raises(ValueError, match="out of range"):
        batch.apply_illnesses(ids([1, bad_env]), ids([0, bad_player]), ids([1, 1]))
    assert_unchanged(batch, before)


def test_empty_batches_lengths_and_numpy_input_boundary():
    batch = game()
    before = states(batch)
    batch.load_players(*[ids([]) for _ in range(5)])
    batch.apply_illnesses(*[ids([]) for _ in range(3)])
    batch.apply_curses(*[ids([]) for _ in range(3)])
    batch.cure_players(*[ids([]) for _ in range(3)])
    batch.finish_turns(*[ids([]) for _ in range(4)])
    batch.reset_environments(ids([]))
    assert_unchanged(batch, before)
    with pytest.raises(ValueError, match="lengths"):
        batch.apply_illnesses(ids([0, 1]), ids([0, 0]), ids([1]))
    with pytest.raises(TypeError):
        batch.apply_illnesses(np.asarray([0], dtype=np.int32), ids([0]), ids([1]))
    with pytest.raises(TypeError):
        batch.apply_illnesses(ids([0]), ids([0]), ids([1, 2, 1, 2])[::2])
    assert_unchanged(batch, before)


@pytest.mark.parametrize(
    "size,players,hp",
    [
        (0, 2, 40),
        (1, 1, 40),
        (1, 10, 40),
        (1_000_001, 2, 40),
        (250_001, 9, 40),
        (1, 2, 0),
        (1, 2, 101),
    ],
)
def test_dimensions_and_resource_capacity_are_bounded(size, players, hp):
    with pytest.raises(ValueError):
        game(size=size, players=players, hp=hp)


def test_readonly_owned_snapshots_and_selective_reset_are_stable():
    batch = game()
    load(batch, illness=3, mask=15)
    load(batch, env=1, player=2, illness=1)
    old = batch.snapshot()
    old_transition = batch.transition_snapshot()
    assert not old.flags.writeable and not old_transition.flags.writeable
    tick(batch)
    assert old[0, 0, 0] == 40
    before = states(batch)
    for envs in ([0, 0], [0, 2], [0, -1]):
        with pytest.raises(ValueError):
            batch.reset_environments(ids(envs))
        assert_unchanged(batch, before)
    batch.reset_environments(ids([0]))
    np.testing.assert_array_equal(batch.snapshot()[0], np.tile(ids([40, 0, 0, 0]), (3, 1)))
    np.testing.assert_array_equal(batch.snapshot()[1], before[0][1])
    assert not np.any(batch.transition_snapshot()[0])
    assert states(batch)[2] == before[2]  # Lifetime counters are never reset.
    tick(batch, expected=0)


@pytest.mark.parametrize("players", [2, 3, 9])
def test_seeded_composition_matches_independent_python_reference(players):
    rng = np.random.default_rng(77067 + players)
    batch = game(size=8, players=players)
    expected = np.zeros((8, players, 4), dtype=np.int64)
    expected[:, :, 0] = 40
    for step in range(200):
        envs = ids(range(8))
        owners = rng.integers(0, players, 8, dtype=np.int64)
        current = expected[envs, owners].copy()
        operation = step % 5
        if operation == 0:
            current[:, 0] = rng.integers(1, 101, 8)
            current[:, 1] = rng.integers(0, 5, 8)
            current[:, 2] = rng.integers(0, 16, 8)
            batch.load_players(
                envs, owners, current[:, 0].copy(), current[:, 1].copy(), current[:, 2].copy()
            )
            expected[envs, owners] = current
        else:
            living = current[:, 0] > 0
            envs, owners, current = envs[living], owners[living], current[living]
            if operation == 1:
                incoming = rng.integers(1, 5, len(envs), dtype=np.int64)
                batch.apply_illnesses(envs, owners, incoming)
                for row, stage in enumerate(current[:, 1]):
                    if stage == 0:
                        current[row, 1] = incoming[row]
                    elif stage == 4:
                        current[row, 0] = 0
                    else:
                        current[row, 1] += 1
            elif operation == 2:
                bits = ids(rng.choice([1, 2, 4, 8], len(envs)))
                batch.apply_curses(envs, owners, bits)
                current[:, 2] |= bits
            elif operation == 3:
                scopes = rng.integers(1, 3, len(envs), dtype=np.int64)
                after = current.copy()
                for row, scope in enumerate(scopes):
                    if scope == 2 or after[row, 1] <= 2:
                        after[row, 1] = 0
                    after[row, 2] = 0 if scope == 2 else after[row, 2] & ~5
                effective = np.any(after != current, axis=1)
                batch.cure_players(envs[effective], owners[effective], scopes[effective])
                current = after
            else:
                tickets = rng.integers(0, 100, len(envs), dtype=np.int64)
                batch.finish_turns(envs, owners, current[:, 3].copy(), tickets)
                for row, stage in enumerate(current[:, 1]):
                    if stage == 4:
                        current[row, 0] = min(100, current[row, 0] + 5)
                    else:
                        current[row, 0] = max(0, current[row, 0] - (0, 1, 2, 5)[stage])
                    if current[row, 0] > 0 and stage and tickets[row] < 5:
                        if stage == 4:
                            current[row, 0] = 0
                        else:
                            current[row, 1] += 1
                    current[row, 3] += 1
            expected[envs, owners] = current
        np.testing.assert_array_equal(batch.snapshot(), expected)


def test_source_pinned_factory_records_costs_scopes_and_false_readiness():
    configured = create_provisional_curse_dynamics_batch(
        catalog_path=CATALOG, bible_path=BIBLE, batch_size=4, player_count=9, initial_hp=100
    )
    metadata = configured.metadata
    assert metadata.plan.profile_sha256 == CURSE_PROFILE_SHA256
    assert metadata.plan.ruleset_id == CURSE_DYNAMICS_RULESET_ID
    assert metadata.plan.cure_profiles == (
        (199, 1, 0, 0),
        (200, 2, 0, 0),
        (237, 1, 1, 2),
        (238, 2, 1, 5),
    )
    assert configured.batch.snapshot().shape == (4, 9, 4)
    assert not metadata.full_game_training_ready
    assert not metadata.local_training_eligible
    assert not metadata.official_fidelity_verified
    assert not metadata.promotion_eligible
    assert not metadata.non_disease_effects_implemented
    assert not metadata.policy_projection_implemented
    assert not metadata.item_legality_and_costs_implemented
    assert CurseDynamicsMetadata.model_validate_json(metadata.model_dump_json()) == metadata


@pytest.mark.parametrize(
    "field,value",
    [
        ("illness_profiles", ((0, 0, 0),)),
        ("curse_bits", (("fog", 2),)),
        ("cure_profiles", ((199, 2, 0, 0),)),
        ("catalog_sha256", "0" * 64),
        ("bible_client_sha256", "0" * 64),
        ("illness_fields", ("stage",)),
        ("cure_fields", ("model_id",)),
        ("documented_mild_illness_stages", (1,)),
        ("documented_mild_mask", 15),
        ("progression_percent", 10),
        ("official_fidelity_verified", True),
        ("promotion_eligible", True),
    ],
)
def test_serialized_rule_drift_and_fidelity_claims_are_rejected(field, value):
    plan = build_curse_dynamics_plan(
        read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
    )
    raw = plan.model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        CurseDynamicsPlan.model_validate(raw)


def test_curse_help_and_api_cure_drift_are_rejected_before_native_construction():
    catalog = read_api_catalog_snapshot(CATALOG)
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    raw = bible.model_dump()
    raw["reference_sections"]["curses"] = tuple(raw["reference_sections"]["curses"][:-1])
    with pytest.raises(ValueError, match="help differs"):
        build_curse_dynamics_plan(catalog, BibleSnapshot.model_validate(raw))
    api = catalog.model_dump()
    for item in api["items"]:
        if item["model_id"] == 237:
            item["raw"]["cost"] = 3
    # model_copy deliberately keeps a claimed source hash: inspect values as well.
    tampered = catalog.model_copy(
        update={
            "items": tuple(type(catalog.items[0]).model_validate(item) for item in api["items"])
        }
    )
    with pytest.raises(ValueError, match="API cure"):
        build_curse_dynamics_plan(tampered, bible)


def test_mismatched_native_contract_cannot_be_used(monkeypatch):
    monkeypatch.setattr(native, "CURSE_DREAM_BIT", 1)
    with pytest.raises(ProvisionalRuleUnavailableError, match="contract differs"):
        create_provisional_curse_dynamics_batch(
            catalog_path=CATALOG, bible_path=BIBLE, batch_size=1
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("batch_size", 1_000_001),
        ("batch_size", True),
        ("player_count", 1),
        ("initial_hp", 101),
        ("state_fields", ("hp",)),
        ("transition_fields", ("operation",)),
        ("local_training_eligible", True),
        ("full_game_training_ready", True),
        ("official_fidelity_verified", True),
        ("promotion_eligible", True),
    ],
)
def test_metadata_cannot_change_the_contract_or_enable_training(field, value):
    plan = build_curse_dynamics_plan(
        read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate_json(BIBLE.read_text())
    )
    metadata = CurseDynamicsMetadata(plan=plan, batch_size=1, player_count=2, initial_hp=40)
    raw = metadata.model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        CurseDynamicsMetadata.model_validate(raw)


def test_native_unavailable_is_an_explicit_optional_dependency_error(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "godfield_sim", None)
    with pytest.raises(ProvisionalRuleUnavailableError, match="simulation extra"):
        create_provisional_curse_dynamics_batch(
            catalog_path=CATALOG, bible_path=BIBLE, batch_size=1
        )


def test_shared_illness_math_preserves_legacy_full_seeded_trajectory():
    """Captured on package 0.46.0 before the shared helper refactor."""
    ruleset = "wide-hand-gift-weighted-dream-resource-hand"
    simulation = create_attack_defense_simulation(
        BIBLE, batch_size=32, seed=41067, initial_hp=100, ruleset=ruleset
    )
    bible = BibleSnapshot.model_validate_json(BIBLE.read_text())
    heuristic = build_curriculum_heuristic(
        bible, ArtifactVocabulary.from_snapshot(bible), ruleset=ruleset
    )
    batch = simulation.batch
    digest = hashlib.sha256()
    seen = set()
    completed = 0
    for _ in range(1024):
        for name in (
            "global_features",
            "player_features",
            "hand_token_ids",
            "action_mask",
            "illness_stages",
            "terminated",
            "terminal_returns",
            "turn_numbers",
        ):
            digest.update(np.asarray(getattr(batch, name)).tobytes())
        seen.update(int(stage) for stage in np.asarray(batch.illness_stages).reshape(-1))
        actions = curriculum_heuristic_actions(simulation, np.arange(32, dtype=np.int64), heuristic)
        digest.update(actions.tobytes())
        batch.step(actions)
        completed += batch.reset_done()
    assert seen == {0, 1, 2, 3, 4}
    assert completed == 241
    assert digest.hexdigest() == "1437712753d61312efff7716bb91ae34ba30c05e18ca8980f636f1c25a40bcc6"
