"""Joined post-gift devils: source checks, native tickets, ownership and atomicity."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import build_full_game_plan, create_development_full_game_batch
from godfield_bot.full_game_devils import FullGameDevilPlan, build_full_game_devil_plan

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


def game(*, size=1, players=3, seed=67, profiles=PLAN.devils.profiles, threshold=1, **options):
    kwargs = dict(
        capacity=18,
        seed=seed,
        initial_hp=50,
        initial_mp=20,
        initial_cp=5,
        gift_profiles=ids([[191, 1]]),
        prayer_gifts=True,
        refill_on_use=True,
        max_turns=100,
        max_decisions=1000,
        attack_profiles=ids(PLAN.combat.attack_profiles),
        armor_profiles=ids(PLAN.combat.armor_profiles),
        special_profiles=ids(PLAN.combat.special_profiles),
        boost_profiles=ids(PLAN.combat.boost_profiles),
        cost_reducer_profiles=ids(PLAN.costs.profiles),
        attack_effect_profiles=ids(PLAN.combat.attack_effect_profiles),
        defense_effect_profiles=ids(PLAN.combat.defense_effect_profiles),
        dream_defense_profiles=ids(PLAN.dream_defense.profiles),
        passive_profiles=ids(PLAN.passives.profiles),
        ascension_profiles=ids(PLAN.attack_family.profiles),
        discard_model_ids=ids(PLAN.discard.discard_model_ids),
        guardian_profiles=ids(PLAN.guardians.profiles),
    )
    kwargs.update(options)
    return native.FullGameBatch(
        size,
        players,
        ids(PLAN.inventory.profiles),
        ids(PLAN.effect_profiles),
        devil_profiles=None if profiles is None else ids(profiles).reshape(-1, 4),
        apocalypse_after_turns=threshold,
        **kwargs,
    )


def force(model, **options):
    profile = next(row for row in PLAN.devils.profiles if row[0] == model)
    return game(profiles=((model, 100, *profile[2:]),), **options)


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
        ids([[e, *rows[e, :4], choice] for e, choice in zip(envs, choices, strict=True)]).reshape(
            -1, 6
        )
    )
    stats = batch.attack_family_snapshot()
    np.testing.assert_array_equal(
        stats[:, 0], stats[:, 2] + stats[:, 3] + stats[:, 13] + (stats[:, 14] > 0)
    )


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
            "devil_snapshot",
            "devil_model_counts",
            "apocalypse_observations",
            "attack_family_snapshot",
            "revival_snapshot",
            "guardian_snapshot",
        )
    )


def same(left, right):
    for a, b in zip(left, right, strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("model", [240, 241, 242, 243, 244])
@pytest.mark.parametrize("players", [2, 3, 9])
def test_five_joined_effects_one_receipt_one_tick(model, players):
    batch = force(model, players=players)
    hand(batch, [127, (237, 0, 0), (238, 235, 1)])
    batch.start_environments(ids([0]))
    step(batch, [0])
    stats = batch.devil_snapshot()[0]
    assert stats[0:3].tolist() == [1, 1, 1]
    assert stats[14:18].tolist() == [1, 1, 0, 1]
    assert batch.devil_model_counts()[0, model - 240] == 1
    assert batch.episode_snapshot()[0, 3:5].tolist() == [1, 1]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1] + [0] * (players - 1)
    if model < 243:
        damage = (model - 239) * 10
        assert stats[3:5].tolist() == [1, damage]
        assert batch.diagnostic_players()[0, 0, 0] == 50 - damage
        assert batch.hp_damage == batch.utility_hp_damage == 0
        assert batch.devil_hp_damage == damage
    elif model == 243:
        assert stats[5:8].tolist() == [1, 3, 2]
        assert stats[12] == 2
        inventory = batch.diagnostic_inventory()[0, 0]
        survivors = [row.tolist() for row in inventory if row[0]]
        assert any(row[1] == 237 and row[3] == 0 for row in survivors)
        assert len(survivors) == 2
        assert [row[0] for row in survivors] == sorted(row[0] for row in survivors)
        assert batch.devil_removed_count == batch.removal_count == 2
    else:
        resource = next(tickets(67, 0, 0x636920D871574E69)) % 3
        assert stats[8] == stats[13] == 1
        assert stats[9:12].tolist() == [10 if i == resource else 0 for i in range(3)]
    assert batch.apocalypse_observations()[0].tolist() == [1, 1, 1]


def test_source_percentages_independent_oracle_and_no_event_inventory_cards():
    batch = game(size=4096)
    batch.start_environments(ids(range(4096)))
    step(batch, [0] * 4096)
    oracle = np.zeros((4096, 5), dtype=np.int64)
    for env in range(4096):
        ticket = next(tickets(67, env, 0x24A19947B3916CF7)) % 100
        for model, upper in ((240, 7), (241, 12), (242, 15), (243, 20), (244, 25)):
            if ticket < upper:
                oracle[env, model - 240] = 1
                break
    np.testing.assert_array_equal(batch.devil_model_counts(), oracle)
    assert (oracle.sum(axis=0) > 0).all()
    assert np.all(batch.devil_snapshot()[:, 1] == 1)
    assert batch.devil_count == oracle.sum()
    inventory = batch.diagnostic_inventory()
    assert np.all((inventory[..., 1] < 240) | (inventory[..., 1] == 0))


@pytest.mark.parametrize("threshold", [0, 2, 100])
def test_threshold_disabled_or_delayed_without_initial_deal_devils(threshold):
    batch = game(size=8, threshold=threshold, initial_cards=9, oldest_overflow=True)
    batch.start_environments(ids(range(8)))
    assert not batch.devil_snapshot().any()
    step(batch, [0] * 8)
    assert not batch.devil_model_counts().any()
    assert not batch.apocalypse_observations()[:, 1].any()


def test_sun_then_bow_reactions_keep_original_tick_until_family_drains():
    batch = force(240)
    load(batch, hp=5)
    for owner in [1, 2]:
        load(batch, owner=owner, hp=100, mask=8)
    hand(batch, [196, 208, 112])
    batch.start_environments(ids([0]))
    step(batch, [1])
    assert not batch.devil_snapshot().any()
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 4
    assert batch.devil_snapshot()[0, 1:5].tolist() == [2, 2, 2, 15]
    assert batch.revival_snapshot()[0].tolist() == [1, 10, 0, 0, 0, 0, 0, 0, 1, 0]
    assert batch.attack_family_snapshot()[0, 14:16].tolist() == [3, 1]
    assert batch.diagnostic_players()[0, :, 5].tolist() == [1, 0, 0]
    step(batch, [0])
    step(batch, [0])
    assert batch.diagnostic_players()[0, :, 0].tolist() == [0, 70, 70]
    assert batch.episode_snapshot()[0, 3:5].tolist() == [1, 1]
    assert not batch.attack_family_snapshot()[0, 13:].any()


@pytest.mark.parametrize("seed", range(12))
def test_trickster_uses_actual_roles_not_disguises_and_stable_survivors(seed):
    batch = force(243, seed=seed)
    hand(batch, [196, (237, 235, 0), (238, 237, 1), (127, 142, 0), 208, 209])
    batch.start_environments(ids([0]))
    step(batch, [1])
    step(batch, [0])
    before = [(3, 238, 237, 1), (4, 127, 142, 0), (5, 208, 0, 0), (6, 209, 0, 0), (7, 191, 0, 0)]
    candidates = list(range(5))
    rng = tickets(seed, 0, 0x0801F2E2858EFC16)
    for i in range(2):
        j = i + next(rng) % (5 - i)
        candidates[i], candidates[j] = candidates[j], candidates[i]
    removed = {before[i][0] for i in candidates[:2]}
    expected = [(2, 237, 235, 0)] + [row for row in before if row[0] not in removed]
    actual = [tuple(row) for row in batch.diagnostic_inventory()[0, 0] if row[0]]
    assert actual == expected


@pytest.mark.parametrize("hp,mp,cp", [(100, 100, 100), (95, 96, 97), (1, 0, 0)])
@pytest.mark.parametrize("seed", range(12))
def test_charity_uniform_choice_and_local_caps(hp, mp, cp, seed):
    batch = force(244, seed=seed)
    load(batch, hp=hp, mp=mp, cp=cp)
    batch.start_environments(ids([0]))
    step(batch, [0])
    resource = next(tickets(seed, 0, 0x636920D871574E69)) % 3
    expected = [hp, mp, cp]
    expected[resource] = min(100, expected[resource] + 10)
    assert batch.diagnostic_players()[0, 0, :3].tolist() == expected


@pytest.mark.parametrize("turns,decisions", [(1, 100), (100, 1)])
def test_limits_suppress_receipts_before_new_devils(turns, decisions):
    batch = force(240, max_turns=turns, max_decisions=decisions)
    batch.start_environments(ids([0]))
    step(batch, [0])
    assert batch.episode_snapshot()[0, 3] == 13
    assert batch.suppressed_gift_count == 1
    assert not batch.devil_model_counts().any()
    assert not batch.apocalypse_observations().any()


def test_last_row_rejection_rolls_back_rng_gifts_resources_and_lifetimes():
    batch, reference = game(size=2), game(size=2)
    for b in [batch, reference]:
        b.start_environments(ids([0, 1]))
    before = snapshot(batch)
    rows = batch.episode_snapshot()
    with pytest.raises(ValueError):
        batch.step(ids([[0, *rows[0, :4], 0], [1, rows[1, 0], 999, *rows[1, 2:4], 0]]))
    same(before, snapshot(batch))
    assert batch.devil_count == batch.devil_hp_damage == batch.devil_removed_count == 0
    step(batch, [0, 0])
    step(reference, [0, 0])
    same(snapshot(batch), snapshot(reference))


def test_reset_clears_episode_events_and_preserves_owned_snapshots_and_lifetimes():
    batch = force(240)
    batch.start_environments(ids([0]))
    step(batch, [0])
    old = snapshot(batch)
    copies = tuple(a.copy() for a in old)
    for a in old:
        assert not a.flags.writeable
    assert batch.devil_count == 1
    batch.reset_environments(ids([0]))
    assert not batch.devil_snapshot().any()
    assert not batch.devil_model_counts().any()
    assert not batch.apocalypse_observations().any()
    assert batch.devil_count == 1 and batch.devil_hp_damage == 10
    same(old, copies)
    reference = force(240)
    reference.reset_environments(ids([0]))
    for b in [batch, reference]:
        b.start_environments(ids([0]))
        step(b, [0])
    same(snapshot(batch), snapshot(reference))


def test_raw_fixture_without_sacrifice_opt_in_does_not_reuse_discard_after_apocalypse():
    batch = force(244)
    hand(batch, [127])
    batch.start_environments(ids([0]))
    assert batch.choice_masks()[0, 19]
    step(batch, [0])
    assert not batch.choice_masks()[0, 19]
    before = snapshot(batch)
    with pytest.raises(ValueError):
        step(batch, [19])
    same(before, snapshot(batch))


@pytest.mark.parametrize(
    "profiles",
    [
        (),
        ((240, 0, 1, 10),),
        ((240, 101, 1, 10),),
        ((239, 7, 1, 10),),
        ((245, 7, 3, 10),),
        ((240, 7, 2, 10),),
        ((243, 5, 2, 3),),
        ((244, 5, 3, 0),),
        ((240, 7, 1, 10), (240, 7, 1, 10)),
        ((240, 80, 1, 10), (241, 80, 1, 20)),
    ],
)
def test_raw_profile_fail_closed(profiles):
    with pytest.raises(ValueError):
        game(profiles=profiles)


@pytest.mark.parametrize(
    "options", [{"profiles": None}, {"gift_profiles": None}, {"threshold": 1_000_000_001}]
)
def test_threshold_dependencies_and_bounds(options):
    with pytest.raises(ValueError):
        game(**options)


@pytest.mark.parametrize(
    "field", ["appearanceRate", "abilityValue", "category", "imageName", "name", "ability"]
)
def test_api_drift_rejected(field):
    payload = read_api_catalog_snapshot(CATALOG).model_dump()
    row = next(r for r in payload["items"] if r["model_id"] == 240)
    row["raw"][field] = 11 if field in ("appearanceRate", "abilityValue") else "wrong"
    with pytest.raises((ValueError, TypeError)):
        build_full_game_devil_plan(
            read_api_catalog_snapshot(CATALOG).model_validate(payload),
            BibleSnapshot.model_validate_json(BIBLE.read_text()),
        )


@pytest.mark.parametrize("field", ["detail", "asset", "image_path", "element_image_paths"])
def test_bible_drift_rejected(field):
    payload = BibleSnapshot.model_validate_json(BIBLE.read_text()).model_dump()
    payload["catalog"]["devils"]["items"][0][field] = (
        ["wrong"] if field in ("detail", "element_image_paths") else "wrong"
    )
    with pytest.raises(ValueError):
        build_full_game_devil_plan(
            read_api_catalog_snapshot(CATALOG), BibleSnapshot.model_validate(payload)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("promotion_eligible", True),
        ("full_game_training_ready", True),
        ("official_fidelity_verified", True),
        ("profiles", ((240, 7, True, 10),)),
        ("profile_fields", ("wrong",)),
    ],
)
def test_source_plan_cannot_relabel_coverage(field, value):
    payload = PLAN.devils.model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        FullGameDevilPlan.model_validate(payload)


def test_adapter_opt_in_and_gates():
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=CATALOG,
        bible_path=BIBLE,
        batch_size=2,
        capacity=18,
        apocalypse_after_turns=20,
    )
    assert configured.metadata.kernel_schema_version == 31
    assert configured.metadata.attack_family_schema_version == 8
    assert configured.metadata.apocalypse_after_turns == 20
    assert not configured.metadata.full_game_training_ready
    assert not configured.metadata.local_training_eligible
    assert not configured.metadata.promotion_eligible


@pytest.mark.parametrize("capacity,players", [(18, 3), (512, 9)])
def test_automatic_sun_receipt_cycle_has_atomic_finite_bound(capacity, players):
    batch = force(240, gift_profiles=ids([[208, 1]]), capacity=capacity, players=players)
    load(batch, hp=5)
    batch.start_environments(ids([0]))
    before = snapshot(batch)
    for _ in range(2):
        with pytest.raises(ValueError, match="receipt bound exceeded"):
            step(batch, [0])
        same(before, snapshot(batch))
        assert batch.action_count == batch.devil_count == batch.revival_count == 0


@pytest.mark.parametrize("seed", range(20))
def test_devil_damage_joins_guardian_departure_stream_without_activation_or_attack(seed):
    batch = force(240, seed=seed)
    batch.seed_guardians(ids([0]), ids([0]), ids([1]))
    batch.start_environments(ids([0]))
    step(batch, [0])
    departed = next(tickets(seed, 0, 0xBA7C9045F12C7F99)) % 100 < 10
    assert batch.guardian_snapshot()[0, 0, 0] == (0 if departed else 1)
    assert batch.guardian_statistics()[0, 10:12].tolist() == [1, int(departed)]
    assert batch.guardian_activation_count == batch.hp_damage == 0
