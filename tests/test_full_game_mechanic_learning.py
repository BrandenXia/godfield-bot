"""Rare native branches must survive public collection, terminal credit and PPO."""

import pytest

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load  # noqa: E402
from test_full_game_observation import configured  # noqa: E402

from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyArchitecture,
)
from godfield_bot.full_game_observation import (  # noqa: E402
    CARD_PROPERTIES_OBSERVATION_ID,
    GLOBAL_FIELDS,
    HAND_FEATURES,
)
from godfield_bot.full_game_replay import verify_full_game_behavior  # noqa: E402
from godfield_bot.full_game_rollout import (  # noqa: E402
    collect_full_game_episodes,
    full_game_policy_sha256,
)
from godfield_bot.full_game_training import FullGamePpoConfig, train_full_game_ppo  # noqa: E402


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


def public_fixture_policy(models, *, removal=False, ordered_defense=False):
    """Canonical real network; no command scripts, hidden IDs or rewritten logits.

    Displayed model embeddings favor the specified slots. Public selected ranks
    suppress toggling already-selected defense/removal cards. Public phase2
    favors confirmation, and an optional phase1 signal favors virtual removal.
    This initializes a diagnostic behavior policy; it is not a trained candidate.
    """
    policy = FullGameActorCritic(
        FullGamePolicyArchitecture(
            schema_version=3,
            observation_id=CARD_PROPERTIES_OBSERVATION_ID,
        )
    )
    with torch.no_grad():
        for parameter in policy.parameters():
            parameter.zero_()
        e, h = policy.architecture.embedding_size, policy.architecture.hidden_size
        for model in models:
            policy.embedding.weight[model, 0] = 1
        policy.card_encoder[0].weight[0, 0] = 1
        for name in ("defense_selection_rank", "discard_selection_rank"):
            policy.card_encoder[0].weight[1, e + HAND_FEATURES.index(name)] = 18
        for slot in range(18):
            policy.observation_encoder[0].weight[slot, slot * e] = 1
            policy.observation_encoder[0].weight[18 + slot, slot * e + 1] = 1
            policy.action_head.weight[1 + slot, slot] = (
                70 - 10 * slot if ordered_defense else 24 if removal else 50 - 0.5 * slot
            )
            policy.action_head.weight[1 + slot, 18 + slot] = -2000
        for index, phase in enumerate((1, 2)):
            policy.context_encoder[0].weight[index, GLOBAL_FIELDS.index(f"phase_{phase}")] = 1
            policy.observation_encoder[0].weight[36 + index, 27 * e + index] = 1
        for index in range(38):
            policy.memory.weight_ih[2 * h + index, index] = 1
        policy.memory.bias_ih[h : 2 * h].fill_(-1000)
        policy.action_head.weight[0, 37] = 2000
        if removal:
            policy.action_head.weight[19, 36] = 2000
        policy.action_head.bias[0] = 10
        # During target phase the native mask leaves only eligible recipients.
        # Do not bias19 globally: it means cancellation during removal.
    return policy


def learn_terminal(configured, policy, *, sampling_seed=67):
    collection = collect_full_game_episodes(configured, policy, sampling_seed=sampling_seed)
    assert collection.collection_error is None and not collection.rejected_commands.size
    assert all(e.outcome.status in ("winner", "draw") for e in collection.episodes)
    assert collection.eligible_decisions == collection.accepted_decisions > 0
    assert collection.eligible_policy_decisions > 0
    verify_full_game_behavior(collection, policy)
    for episode in collection.episodes:
        sample = episode.samples
        assert sample is not None
        np.testing.assert_array_equal(
            sample.terminal_targets,
            np.asarray(episode.outcome.terminal_values)[sample.commands[:, 3]],
        )
    before = full_game_policy_sha256(policy)
    actor_before = {name: value.clone() for name, value in policy.action_head.state_dict().items()}
    metrics = train_full_game_ppo(
        policy,
        torch.optim.Adam(policy.parameters(), lr=3e-4),
        collection,
        FullGamePpoConfig(epochs=1),
    )
    assert metrics.gradient_norm > 0 and np.isfinite(list(metrics.model_dump().values())).all()
    assert full_game_policy_sha256(policy) != before
    assert any(
        not torch.equal(value, actor_before[name])
        for name, value in policy.action_head.state_dict().items()
    ), "The actor must learn too; changing only value predictions is insufficient."
    assert policy.card_property_encoder.weight.any()
    return collection


@pytest.mark.parametrize("players", [2, 4, 9])
def test_hidden_utility_cost_fizzle_keeps_complete_episode_targets_and_real_ppo(players):
    c = configured(
        player_count=players,
        teams=(1, *(2 for _ in range(players - 1))),
        max_turns=64,
        max_decisions=256,
    )
    hand(c.batch, [(235, 237, 0)])
    load(c.batch, hp=40, mp=2, mask=4)
    for seat in range(1, players):
        load(c.batch, owner=seat, hp=1, illness=1, mask=0)
        c.batch.seed_confusion(ids([0]), ids([seat]), ids([1]))
    r = learn_terminal(c, public_fixture_policy([237]))
    assert c.batch.hidden_cost_snapshot()[0].tolist() == [0, 1, 0, 1, 0, 1, 7, 2, 5]
    assert r.eligible_decisions - r.eligible_policy_decisions == players - 1
    assert r.episodes[0].outcome.winning_players == (0,)
    assert c.batch.utility_count == 0 and c.batch.diagnostic_players()[0, 0, 0] == 40


@pytest.mark.parametrize("players", [2, 4, 9])
def test_hidden_defense_cost_fizzle_does_not_erase_the_losing_responders_training_rows(players):
    c = configured(
        player_count=players,
        teams=(1, 2, *(1 for _ in range(players - 2))),
        initial_mp=0,
        max_turns=64,
        max_decisions=256,
    )
    hand(c.batch, [92])  # Darkness10 ends the only enemy after failed defense.
    # Displayed filter, Wall and adjacent Spiritual Hood look free. The true
    # third card is ordinary armor, so the actual Wall still costs six MP.
    hand(c.batch, [189, 233, (130, 163, 0)], owner=1)
    r = learn_terminal(c, public_fixture_policy([92, 189, 233, 163], ordered_defense=True))
    assert c.batch.hidden_cost_snapshot()[0].tolist() == [0, 0, 1, 3, 2, 1, 6, 0, 6]
    sample = r.episodes[0].samples
    defense = sample.commands[:, 4] == 4
    assert defense.sum() == 4 and (sample.commands[defense, 3] == 1).all()
    assert (sample.terminal_targets[defense] == -1).all()
    assert sample.observation.policy_gradient_mask[defense].all()
    assert c.batch.hp_damage > 0 and c.batch.diagnostic_players()[0, 1, 0] == 0


@pytest.mark.parametrize("players", [2, 4, 9])
@pytest.mark.parametrize("actual", [208, 209])
@pytest.mark.parametrize("sacrifice", [False, True])
def test_protected_hidden_removal_is_a_real_accepted_learning_decision(players, actual, sacrifice):
    c = configured(
        player_count=players,
        teams=(1, 2, *(1 for _ in range(players - 2))),
        max_turns=128,
        max_decisions=512,
        apocalypse_after_turns=1 if sacrifice else 0,
    )
    hand(c.batch, [(actual, 191, 0)], owner=1)
    load(c.batch, owner=1, hp=1, illness=3, mask=2)
    r = learn_terminal(c, public_fixture_policy([191], removal=True))
    snapshot = c.batch.hidden_removal_snapshot()[0]
    assert snapshot[int(sacrifice)] >= 1
    assert snapshot[2] >= 1 and snapshot[5 if actual == 208 else 6] >= 1
    assert c.batch.sacrifice_snapshot()[0, 6] == 0
    sample = r.episodes[0].samples
    confirmations = (sample.commands[:, 4] == 7) & (sample.commands[:, 5] == 0)
    assert confirmations.any()
    assert (sample.terminal_targets[confirmations] == -1).all()
    assert sample.observation.policy_gradient_mask[confirmations].all()


@pytest.mark.parametrize("players", [2, 4, 9])
def test_real_full_pool_miracle_reuse_reaches_overflow_then_terminal_training(players):
    c = configured(
        player_count=players,
        teams=(*(1 for _ in range(players - 1)), 2),
        acquisition_mode="all-held-weighted",
        seed=4,  # Full weighted opening gives the last living seat Fireball.
        initial_hp=99,
        initial_mp=99,
        max_turns=512,
        max_decisions=2048,
    )
    for seat in range(1, players - 1):
        load(c.batch, owner=seat, hp=0, mask=0)
    r = learn_terminal(c, public_fixture_policy([210]))
    assert c.batch.acquisition_snapshot()[0, :, 2].sum() > 0
    assert c.batch.miracle_use_count > 9
    assert r.episodes[0].outcome.status == "winner"
    assert r.episodes[0].samples.observation.hand_mask.sum(axis=1).max() == 18
