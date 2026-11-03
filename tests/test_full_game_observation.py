"""Public-equivalence, numeric choices, padding and native lease boundaries."""

from dataclasses import fields, replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_full_game_generated import hand, ids, load, step

from godfield_bot.full_game import create_development_full_game_batch
from godfield_bot.full_game_observation import (
    CONTEXT_VIEWS,
    GLOBAL_FIELDS,
    HAND_FEATURES,
    PLAYER_FEATURES,
    PUBLIC_GETTERS,
    FullGameEncoderMetadata,
    FullGameObservationEncoder,
)

np = pytest.importorskip("numpy")
pytest.importorskip("godfield_sim")
PATHS = dict(
    catalog_path=Path("data/snapshots/2026-10-01/api-catalog-en.json"),
    bible_path=Path("data/snapshots/2026-09-20/bible.json"),
)


def configured(**options):
    return create_development_full_game_batch(
        **PATHS, batch_size=options.pop("size", 1), capacity=options.pop("capacity", 18), **options
    )


def equal_features(a, b):
    for field in fields(a):
        if field.name != "leases":
            np.testing.assert_array_equal(getattr(a, field.name), getattr(b, field.name))


@pytest.mark.parametrize("players", range(2, 10))
def test_complete_public_shapes_padding_inactive_rows_and_lease_separation(players):
    c = configured(size=2, player_count=players, acquisition_mode="all-held-weighted")
    encoder = FullGameObservationEncoder(c)
    setup = encoder.encode()
    assert not setup.global_features.any() and not setup.choice_mask.any()
    c.batch.start_environments(ids([1]))
    o = encoder.encode()
    assert o.global_features.shape == (2, len(GLOBAL_FIELDS)) == (2, 112)
    assert o.players.shape == (2, 9, len(PLAYER_FEATURES)) == (2, 9, 42)
    assert o.hand_features.shape == (2, 18, len(HAND_FEATURES)) == (2, 18, 27)
    assert o.context_model_ids.shape == (2, 5)
    assert o.choice_mask.shape == (2, 28)
    assert not o.hand_mask[0].any() and o.hand_mask[1].sum() == 9
    assert not o.players[0].any() and not o.players[1, players:].any()
    assert o.player_mask[1].sum() == players
    assert not o.global_features[0].any()
    for field in fields(o):
        assert not getattr(o, field.name).flags.writeable
    np.testing.assert_array_equal(o.leases[:, 0], [0, 1])
    np.testing.assert_array_equal(o.leases[:, 1:], c.batch.episode_snapshot()[:, :4])
    sub = o.take(ids([1]))
    assert sub.leases[:, 0].tolist() == [1] and sub.hand_mask.sum() == 9


@pytest.mark.parametrize("phase", [1, 2, 3])
def test_hidden_actual_cards_instance_ids_and_fog_hidden_opponents_are_not_features(phase):
    observations = []
    truths = []
    for variant in (0, 1):
        c = configured(player_count=3)
        b = c.batch
        b.seed_hand(0, 0, ids([[1 + variant * 1000, 35 if variant else 59, 6, 0]]))
        hand(b, [6 if variant else 230], owner=1)
        load(b, owner=0, hp=40, mp=10, mask=1)
        load(
            b,
            owner=1,
            hp=1 if variant else 99,
            mp=99 if variant else 0,
            cp=13 if variant else 3,
            illness=2 if variant else 0,
            mask=15 if variant else 0,
        )
        b.seed_guardians(ids([0]), ids([1]), ids([9 if variant else 0]))
        b.seed_confusion(ids([0]), ids([1]), ids([10 if variant else 2]))
        b.start_environments(ids([0]))
        if phase >= 2:
            step(b, [1])
        if phase >= 3:
            step(b, [0])
        assert b.episode_snapshot()[0, 3] == phase
        truths.append((b.diagnostic_inventory(), b.diagnostic_players()))
        observations.append(FullGameObservationEncoder(c).encode())
    assert not np.array_equal(truths[0][0], truths[1][0])
    assert not np.array_equal(truths[0][1], truths[1][1])
    equal_features(*observations)
    o = observations[0]
    assert o.card_model_ids[0, 0] == 6
    assert o.players[0, 1, PLAYER_FEATURES.index("visible")] == 0
    assert o.players[0, 1, PLAYER_FEATURES.index("guardian_visible")] == 0
    assert o.players[0, 1, PLAYER_FEATURES.index("control_visible")] == 0


def test_encoder_never_reads_private_getters_and_does_not_move_rng_or_gameplay():
    c = configured(acquisition_mode="all-held-weighted")
    c.batch.start_environments(ids([0]))
    before = c.batch.episode_snapshot().copy(), c.batch.diagnostic_inventory().copy()
    reads = []

    class PublicOnly:
        def __getattr__(self, name):
            assert name in PUBLIC_GETTERS, name
            reads.append(name)
            return getattr(c.batch, name)

    e = FullGameObservationEncoder(replace(c, batch=PublicOnly()))
    equal_features(e.encode(), e.encode())
    assert set(reads) == set(PUBLIC_GETTERS)
    np.testing.assert_array_equal(c.batch.episode_snapshot(), before[0])
    np.testing.assert_array_equal(c.batch.diagnostic_inventory(), before[1])


def test_ordered_waiver_selections_are_visible_and_instance_and_epoch_ids_are_not():
    observations = []
    c = configured(initial_mp=0)
    for epoch in (1, 2):
        hand(c.batch, [215, 46])
        c.batch.start_environments(ids([0]))
        step(c.batch, [1])
        step(c.batch, [2])
        o = FullGameObservationEncoder(c).encode()
        observations.append(o)
        assert o.hand_features[
            0, :2, HAND_FEATURES.index("attack_selection_rank")
        ].tolist() == pytest.approx([1 / 18, 2 / 18])
        assert (
            o.global_features[
                0, GLOBAL_FIELDS.index("attack_selection_observations.displayed_mp_cost")
            ]
            == 0
        )
        assert o.leases[0, 1] == epoch
        c.batch.reset_environments(ids([0]))
    equal_features(*observations)


@pytest.mark.parametrize("model", [3, 4, 5])
def test_trade_and_purchase_menus_preserve_their_native_numeric_meanings(model):
    c = configured(initial_cp=20)
    b = c.batch
    hand(b, [model, 35])
    hand(b, [6], owner=1)
    b.start_environments(ids([0]))
    step(b, [1])
    if model == 4:
        step(b, [2])
        step(b, [0])
    if model in (4, 5):
        pre = FullGameObservationEncoder(c).encode()
        assert pre.context_model_ids[0, 4] == 0
        step(b, [20])
        offered = FullGameObservationEncoder(c).encode()
        assert offered.context_model_ids[0, 4] == (35 if model == 4 else 0)
        step(b, [0])
    o = FullGameObservationEncoder(c).encode()
    if model == 4:
        assert o.leases[0, 4] == 1 and not o.context_model_ids.any()
        return  # Sell settles after defense; only Buy has a purchase menu.
    assert o.leases[0, 4] == 6
    np.testing.assert_array_equal(o.choice_mask, b.choice_masks())
    if model == 3:
        assert o.choice_mask[0, 0] and o.choice_mask[0, 9]
    else:
        assert o.choice_mask[0, :2].all() and o.choice_mask[0].sum() == 2
        assert o.context_model_ids[0, 4] == b.market_observations()[0, 6] != 0


@pytest.mark.parametrize("apocalypse", [False, True])
def test_discard_and_sacrifice_have_distinct_public_virtual_controls(apocalypse):
    c = configured(apocalypse_after_turns=1 if apocalypse else 0)
    b = c.batch
    hand(b, [191], owner=0)
    hand(b, [191], owner=1)
    b.start_environments(ids([0]))
    if apocalypse:
        step(b, [0])
    step(b, [19])
    step(b, [1])
    o = FullGameObservationEncoder(c).encode()
    assert o.leases[0, 4] == 7
    assert o.hand_features[0, 0, HAND_FEATURES.index("discard_selection_rank")] == pytest.approx(
        1 / 18
    )
    index = GLOBAL_FIELDS.index("discard_observations.virtual_model_id")
    assert o.global_features[0, index] == pytest.approx(
        np.log1p(2 if apocalypse else 1) / np.log(100)
    )


@pytest.mark.parametrize(
    "name",
    [name for name, _ in CONTEXT_VIEWS] + ["actor_hands", "player_observations", "choice_masks"],
)
def test_corrupt_native_layouts_fail_closed_without_coercing(name):
    c = configured()
    c.batch.start_environments(ids([0]))

    class WrongLayout:
        def __getattr__(self, key):
            original = getattr(c.batch, key)
            return (lambda: original().astype(np.float64)) if key == name else original

    with pytest.raises(RuntimeError, match="layout differs"):
        FullGameObservationEncoder(replace(c, batch=WrongLayout())).encode()


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"hand_slots": 9},
        {"choices": 30},
        {"global_fields": ()},
        {"public_getters": ("diagnostic_inventory",)},
        {"context_model_columns": ()},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
    ],
)
def test_encoder_metadata_cannot_silently_widen_or_authorize_training(change):
    m = FullGameObservationEncoder(configured()).metadata
    with pytest.raises(ValidationError):
        FullGameEncoderMetadata.model_validate(m.model_dump() | change)


@pytest.mark.parametrize("capacity", [9, 17, 19, 512])
def test_other_raw_capacities_need_an_explicit_new_encoder(capacity):
    with pytest.raises(ValueError, match="requires18 slots"):
        FullGameObservationEncoder(configured(capacity=capacity))
