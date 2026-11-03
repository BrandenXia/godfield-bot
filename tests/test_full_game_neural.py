"""Legal recurrent inference, separate seat credit and failed-step rollback."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, step  # noqa: E402
from test_full_game_observation import configured  # noqa: E402

from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyArchitecture,
    FullGamePolicyController,
    full_game_policy_inputs,
)
from godfield_bot.full_game_observation import FullGameObservationEncoder  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def isolated_cpu_runtime():
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(2)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(67)
            yield
    finally:
        torch.set_num_threads(previous)


def biased(policy, choice):
    with torch.no_grad():
        policy.action_head.weight.zero_()
        policy.action_head.bias.zero_()
        policy.action_head.bias[choice] = 1000


@pytest.mark.parametrize("players", range(2, 10))
def test_28_native_logits_values_and_gradients_support_every_roster_size(players):
    c = configured(size=2, player_count=players, acquisition_mode="all-held-weighted")
    c.batch.start_environments(ids([0, 1]))
    o = FullGameObservationEncoder(c).encode()
    policy = FullGameActorCritic()
    logits, values, memory = policy(full_game_policy_inputs(o))
    assert logits.shape == (2, 28) and values.shape == (2,) and memory.shape == (2, 128)
    probabilities = torch.softmax(logits, dim=1)
    assert torch.equal(
        probabilities[~torch.from_numpy(o.choice_mask.copy())],
        torch.zeros_like(probabilities[~torch.from_numpy(o.choice_mask.copy())]),
    )
    target = torch.from_numpy(np.argmax(o.choice_mask, axis=1))
    loss = torch.nn.functional.cross_entropy(logits, target) + values.square().mean()
    loss.backward()
    for parameter in policy.parameters():
        assert parameter.grad is not None and torch.isfinite(parameter.grad).all()
    assert not policy.architecture.full_game_training_ready


def test_command_epoch_decision_ids_are_not_learned_policy_inputs():
    c = configured()
    hand(c.batch, [35])
    c.batch.start_environments(ids([0]))
    o = FullGameObservationEncoder(c).encode()
    alternative = replace(o, leases=o.leases + 123)
    policy = FullGameActorCritic()
    for a, b in zip(
        policy(full_game_policy_inputs(o)),
        policy(full_game_policy_inputs(alternative)),
        strict=True,
    ):
        assert torch.equal(a, b)


def test_only_accepted_actors_update_memory_and_response_memory_is_not_attacker_memory():
    c = configured(size=2, player_count=4, teams=(1, 1, 2, 2))
    hand(c.batch, [35])
    c.batch.start_environments(ids([0, 1]))
    policy = FullGameActorCritic()
    controller = FullGamePolicyController(c, policy)
    for choice in (1, 0, 21):  # Seat2 enemy: capacity+1+2.
        biased(policy, choice)
        result = controller.step(ids([0]), deterministic=True)
        assert result.actions.tolist() == [choice]
    previous = controller.memory_snapshot()
    assert previous[0, 0].abs().sum() > 0
    assert not previous[0, 1:].any() and not previous[1].any()
    biased(policy, 0)
    defense = controller.step(ids([0]), deterministic=True)
    assert defense.observation.leases[0, 3] == 2
    assert not defense.previous_memory.any()
    current = controller.memory_snapshot()
    assert torch.equal(current[0, 0], previous[0, 0])
    assert current[0, 2].abs().sum() > 0 and not current[0, 1].any()
    defense.previous_memory.fill_(999)
    assert not torch.equal(controller.memory_snapshot()[0, 2], defense.previous_memory[0])


def test_rejected_hidden_cost_batch_preserves_all_seat_memories_sampling_rng_and_native_state():
    c = configured(size=2, initial_mp=6, hidden_cost_policy="strict-error")
    for env, actual in enumerate((231, 235)):
        hand(c.batch, [(actual, 228, 0)], env=env)
    c.batch.start_environments(ids([0, 1]))
    policy = FullGameActorCritic()
    controller = FullGamePolicyController(c, policy, seed=901)
    biased(policy, 1)
    controller.step(ids([0, 1]))
    before = (
        controller.memory_snapshot(),
        controller.sampling_state(),
        c.batch.episode_snapshot().copy(),
    )
    biased(policy, 0)
    with pytest.raises(ValueError, match="unaffordable"):
        controller.step(ids([0, 1]))
    assert torch.equal(controller.memory_snapshot(), before[0])
    assert torch.equal(controller.sampling_state(), before[1])
    np.testing.assert_array_equal(c.batch.episode_snapshot(), before[2])
    result = controller.step(ids([0]))
    assert result.transition.commands[:, 0].tolist() == [0]
    assert torch.equal(controller.memory_snapshot()[1], before[0][1])


def test_explicit_reset_clears_every_seat_only_in_selected_epochs():
    c = configured(size=2, max_decisions=2)
    c.batch.start_environments(ids([0, 1]))
    policy = FullGameActorCritic()
    biased(policy, 0)
    controller = FullGamePolicyController(c, policy)
    controller.step(ids([0, 1]))
    result = controller.step(ids([0, 1]))
    assert result.transition.rewards.truncated.all() and not result.transition.rewards.valid.any()
    before = controller.memory_snapshot()
    assert before[:, :2].abs().sum() > 0
    controller.reset_environments(ids([0]))
    assert not controller.memory_snapshot()[0].any()
    assert torch.equal(controller.memory_snapshot()[1], before[1])
    c.batch.start_environments(ids([0]))
    fresh = controller.step(ids([0]))
    assert fresh.observation.leases[0, 1] == 2 and not fresh.previous_memory.any()


@pytest.mark.parametrize("bypass", ["step", "reset"])
def test_raw_cursor_changes_cannot_silently_advance_policy_memory(bypass):
    c = configured()
    c.batch.start_environments(ids([0]))
    controller = FullGamePolicyController(c, FullGameActorCritic())
    before = controller.memory_snapshot(), controller.sampling_state()
    if bypass == "step":
        step(c.batch, [0])
    else:
        c.batch.reset_environments(ids([0]))
        c.batch.start_environments(ids([0]))
    with pytest.raises(RuntimeError, match="untracked"):
        controller.step(ids([0]))
    assert torch.equal(controller.memory_snapshot(), before[0])
    assert torch.equal(controller.sampling_state(), before[1])


def test_native_forced_turns_have_zero_policy_weight_but_real_seat_memory():
    c = configured(player_count=3)
    c.batch.seed_confusion(ids([0]), ids([0]), ids([1]))
    c.batch.start_environments(ids([0]))
    controller = FullGamePolicyController(c, FullGameActorCritic())
    result = controller.step(ids([0]))
    assert result.actions.tolist() == [0]
    assert result.transition.policy_gradient_masks.tolist() == [[False]]
    assert controller.memory_snapshot()[0, 0].abs().sum() > 0
    assert not controller.memory_snapshot()[0, 1:].any()


@pytest.mark.parametrize(
    "players,teams",
    [
        (2, (0, 0)),
        (3, (0, 0, 0)),
        (4, (1, 1, 2, 2)),
        (9, (1, 2, 3, 4, 1, 2, 3, 4, 0)),
    ],
)
def test_complete_pool_neural_episodes_keep_legality_memory_and_outcome_credit(players, teams):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(67)
        c = configured(
            size=4,
            player_count=players,
            teams=teams,
            acquisition_mode="all-held-weighted",
            max_turns=256,
            max_decisions=2048,
            apocalypse_after_turns=64,
        )
        c.batch.start_environments(ids(range(4)))
        controller = FullGamePolicyController(c, FullGameActorCritic(), seed=901)
        counts = np.zeros((4, 9), dtype=np.int64)
        for _ in range(2048):
            active = np.flatnonzero(c.batch.choice_masks().any(axis=1)).astype(np.int64)
            if not len(active):
                break
            result = controller.step(active)
            counts += result.transition.rewards.valid
            assert result.observation.choice_mask[np.arange(len(active)), result.actions].all()
            np.testing.assert_array_equal(
                result.transition.commands[:, :5], result.observation.leases
            )
        state = c.batch.episode_snapshot()
        assert (state[:, 3] >= 12).all()
        real_endings = state[:, 3] == 12
        assert real_endings.any()  # Truncations never stand in for learning wins.
        assert (counts[real_endings, :players] == 1).all()
        assert not counts[~real_endings].any() and not counts[:, players:].any()
        assert not controller.poll_rewards().valid.any()


@pytest.mark.parametrize(
    "change",
    [
        {"choices": 30},
        {"hand_slots": 9},
        {"vocabulary_size": 4096},
        {"schema_version": True},
        {"old_checkpoint_compatible": True},
        {"full_game_training_ready": True},
        {"promotion_eligible": True},
    ],
)
def test_separate_architecture_cannot_admit_old_models_or_claim_live_readiness(change):
    with pytest.raises(ValidationError):
        FullGamePolicyArchitecture.model_validate(
            FullGamePolicyArchitecture().model_dump() | change
        )
