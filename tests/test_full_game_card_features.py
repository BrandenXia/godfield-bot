"""Displayed-only properties, exact transfer, seed lineage and complete PPO replay."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load, step  # noqa: E402
from test_full_game_observation import PATHS, configured, equal_features  # noqa: E402

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.full_game_card_features import (  # noqa: E402
    CARD_PROPERTY_FIELDS,
    public_card_property_table,
)
from godfield_bot.full_game_evaluation import evaluate_full_game_candidate  # noqa: E402
from godfield_bot.full_game_imitation import FullGameImitationConfig  # noqa: E402
from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyArchitecture,
    full_game_policy_inputs,
    transfer_full_game_card_properties,
)
from godfield_bot.full_game_observation import (  # noqa: E402
    ATTACK_HISTORY_OBSERVATION_ID,
    CARD_PROPERTIES_OBSERVATION_ID,
    HAND_FEATURES,
    PROPERTY_HAND_FIELDS,
    FullGameEncoderMetadata,
    FullGameObservationEncoder,
)
from godfield_bot.full_game_rollout import full_game_policy_sha256  # noqa: E402
from godfield_bot.full_game_training import (  # noqa: E402
    FullGamePpoConfig,
    FullGameTrainingConfig,
    FullGameTrainingReport,
    load_full_game_candidate,
    resume_full_game_training,
    run_full_game_training,
    save_full_game_training,
)


@pytest.fixture(scope="module", autouse=True)
def cpu_runtime():
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(2)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(67)
            yield
    finally:
        torch.set_num_threads(previous)


def test_public_properties_cover_all_held_roles_prices_costs_and_variable_attacks():
    m = configured().metadata
    table = public_card_property_table(m)
    index = {name: i for i, name in enumerate(CARD_PROPERTY_FIELDS)}

    def value(model, name):
        return float(table[model, index[name]])

    def raw(model, name):
        return round(np.expm1(value(model, name) * np.log(100)))

    assert table.shape == (297, len(CARD_PROPERTY_FIELDS)) and not table.flags.writeable
    assert not table[:3].any() and not table[240:].any()
    for model, roles in m.roles.model_roles:
        assert sum(int(value(model, f"role_bit_{bit}")) << bit for bit in range(9)) == roles
    for model, _, price in m.plan.trade.price_profiles:
        assert raw(model, "price_log") == price
    for model, _, _, _, cost in m.plan.combat.attack_profiles:
        assert raw(model, "attack_mp_cost_log") == cost
    for model, _, _, _, cost in m.plan.combat.special_profiles:
        assert raw(model, "defense_mp_cost_log") == cost
    assert raw(58, "mp_attack_coefficient_log") == 2 and raw(58, "fixed_attack_log") == 0
    assert raw(14, "fixed_attack_log") == 3 and value(14, "attack_strikes_fraction") == 1
    assert value(112, "hit_rate_fraction") == 0.25
    assert value(207, "fate") == 1
    assert value(235, "utility_kind_1") == value(235, "reusable_miracle") == 1


@pytest.mark.parametrize("players", range(2, 10))
def test_version3_keeps_original_hand_prefix_and_masks_padding_and_inactive_rows(players):
    c = configured(size=2, player_count=players, acquisition_mode="all-held-weighted")
    e = FullGameObservationEncoder(c, CARD_PROPERTIES_OBSERVATION_ID)
    assert e.metadata.schema_version == 3 and e.metadata.hand_fields == PROPERTY_HAND_FIELDS
    assert not e.encode().hand_features.any()
    c.batch.start_environments(ids([0]))
    new = e.encode()
    old = FullGameObservationEncoder(c, ATTACK_HISTORY_OBSERVATION_ID).encode()
    assert new.hand_features.shape == (2, 18, len(PROPERTY_HAND_FIELDS))
    np.testing.assert_array_equal(new.hand_features[:, :, : len(HAND_FEATURES)], old.hand_features)
    np.testing.assert_array_equal(new.global_features, old.global_features)
    assert not new.hand_features[~new.hand_mask].any()
    assert not new.hand_features.flags.writeable
    bad = e.metadata.model_dump() | {"hand_fields": HAND_FEATURES}
    with pytest.raises(ValueError):
        FullGameEncoderMetadata.model_validate(bad)


def test_dream_actual_cards_and_fog_hidden_opponents_cannot_change_properties():
    observations = []
    for variant in (0, 1):
        c = configured(player_count=3)
        hand(c.batch, [(59 if variant else 6, 35, 0), 15])
        hand(c.batch, [90 if variant else 31], owner=1)
        load(c.batch, owner=0, hp=40, mask=3)
        load(c.batch, owner=1, hp=50 if variant else 2, mp=1 if variant else 20, mask=0)
        c.batch.start_environments(ids([0]))
        observations.append(FullGameObservationEncoder(c, CARD_PROPERTIES_OBSERVATION_ID).encode())
    equal_features(*observations)
    table = public_card_property_table(c.metadata)
    np.testing.assert_array_equal(
        observations[0].hand_features[0, 0, len(HAND_FEATURES) :], table[35]
    )


def test_zero_property_projection_preserves_parent_logits_values_memory_and_rng():
    original = FullGameActorCritic(
        FullGamePolicyArchitecture(schema_version=2, observation_id=ATTACK_HISTORY_OBSERVATION_ID)
    )
    with torch.no_grad():
        original.history_encoder.weight.fill_(0.002)
    rng = torch.random.get_rng_state().clone()
    migrated = transfer_full_game_card_properties(original)
    assert torch.equal(rng, torch.random.get_rng_state())
    assert not migrated.card_property_encoder.weight.any()
    c = configured(player_count=4, teams=(1, 1, 2, 2))
    hand(c.batch, [35])
    c.batch.start_environments(ids([0]))
    for action in (1, 0, 21):
        step(c.batch, [action])
    before = FullGameObservationEncoder(c, ATTACK_HISTORY_OBSERVATION_ID).encode()
    after = FullGameObservationEncoder(c, CARD_PROPERTIES_OBSERVATION_ID).encode()
    memory = torch.linspace(-0.5, 0.5, original.architecture.hidden_size)[None, :]
    with torch.no_grad():
        a = original(full_game_policy_inputs(before), memory)
        b = migrated(full_game_policy_inputs(after), memory)
    assert all(torch.equal(x, y) for x, y in zip(a, b, strict=True))
    with pytest.raises(ValueError, match="version 2"):
        transfer_full_game_card_properties(FullGameActorCritic())


@pytest.fixture(scope="module")
def parent_candidate(tmp_path_factory):
    config = FullGameTrainingConfig(
        batch_size=2,
        player_count=2,
        updates=1,
        seed=1290000,
        ppo=FullGamePpoConfig(epochs=1, sequence_length=8),
        architecture=FullGamePolicyArchitecture(
            schema_version=2, observation_id=ATTACK_HISTORY_OBSERVATION_ID
        ),
    )
    run = run_full_game_training(
        **PATHS, config=config, imitation=FullGameImitationConfig(batches=1, epochs=1, seed=1291000)
    )
    directory = save_full_game_training(tmp_path_factory.mktemp("property-parent"), run)
    return run, directory


def test_transfer_imitation_ppo_and_resume_preserve_complete_source_seed_lineage(
    parent_candidate, tmp_path, monkeypatch
):
    parent, directory = parent_candidate
    parent_bytes = (directory / "weights.pt").read_bytes()
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    result = CliRunner().invoke(
        app,
        [
            "simulation",
            "full-game-train",
            "--public-card-features",
            "--initialize-from",
            str(directory),
            "--players",
            "2",
            "--batch-size",
            "2",
            "--updates",
            "1",
            "--seed",
            "1300000",
            "--imitation-batches",
            "1",
            "--imitation-epochs",
            "1",
            "--imitation-seed",
            "1310000",
            "--checkpoint-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    child = Path(json.loads(result.stdout)["checkpoint"])
    manifest, policy = load_full_game_candidate(child)
    report = manifest.training
    assert report.card_initialization.source_training_seeds == tuple(
        sorted(parent.report.used_seeds())
    )
    assert (
        report.card_initialization.initialized_policy_sha256
        == report.imitation.before_policy_sha256
    )
    assert report.imitation.after_policy_sha256 == report.initial_collection.behavior_policy_sha256
    assert policy.card_property_encoder.weight.any()
    resumed = resume_full_game_training(child, **PATHS, additional_updates=1)
    whole = run_full_game_training(
        **PATHS,
        config=resumed.report.config,
        initialize_from=directory,
        imitation=report.imitation.config,
    )
    assert resumed.report == whole.report
    assert full_game_policy_sha256(resumed.policy) == full_game_policy_sha256(whole.policy)
    assert (directory / "weights.pt").read_bytes() == parent_bytes
    for seed in parent.report.used_seeds() | report.used_seeds():
        with pytest.raises(ValueError, match="held-out"):
            evaluate_full_game_candidate(
                child, **PATHS, seed=seed, games_per_faction=1, greedy_baseline=True
            )
    evaluation = evaluate_full_game_candidate(
        child,
        **PATHS,
        seed=1320000,
        games_per_faction=1,
        baseline_directory=directory,
        diagnostics=True,
    )
    assert evaluation.baseline_policy_sha256 == parent.report.final_policy_sha256
    assert not evaluation.promotion_eligible
    bad = report.model_dump()
    bad["card_initialization"]["initialized_policy_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        FullGameTrainingReport.model_validate(bad)
    with pytest.raises(ValueError, match="new training seeds"):
        run_full_game_training(
            **PATHS,
            config=report.config,
            initialize_from=directory,
            imitation=FullGameImitationConfig(batches=1, epochs=1, seed=1291000),
        )


def test_zero_projection_cannot_hide_tampered_property_inputs_from_replay():
    from godfield_bot.full_game_replay import verify_full_game_behavior
    from godfield_bot.full_game_rollout import collect_full_game_episodes

    c = configured(size=2, player_count=2, acquisition_mode="all-held-weighted", seed=1350000)
    policy = FullGameActorCritic(
        FullGamePolicyArchitecture(schema_version=3, observation_id=CARD_PROPERTIES_OBSERVATION_ID)
    )
    collection = collect_full_game_episodes(c, policy)
    verify_full_game_behavior(collection, policy)
    episode = next(
        e for e in collection.episodes if e.samples is not None and len(e.samples.commands)
    )
    features = episode.samples.observation.hand_features.copy()
    features[0, 0, len(HAND_FEATURES)] += 1
    changed = replace(
        episode,
        samples=replace(
            episode.samples,
            observation=replace(episode.samples.observation, hand_features=features),
        ),
    )
    tampered = replace(
        collection, episodes=tuple(changed if e is episode else e for e in collection.episodes)
    )
    with pytest.raises(ValueError, match="public card properties"):
        verify_full_game_behavior(tampered, policy)
