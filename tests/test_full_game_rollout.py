"""Complete team returns, no truncated targets and honest native rejection data."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from test_full_game_generated import hand, ids, load  # noqa: E402
from test_full_game_neural import biased  # noqa: E402
from test_full_game_observation import configured  # noqa: E402

from godfield_bot.full_game_neural import (  # noqa: E402
    FullGameActorCritic,
    FullGamePolicyController,
    full_game_policy_inputs,
)
from godfield_bot.full_game_replay import (  # noqa: E402
    full_game_seat_sequences,
    verify_full_game_behavior,
)
from godfield_bot.full_game_rollout import (  # noqa: E402
    FullGameCollectionMetadata,
    collect_full_game_episodes,
    full_game_policy_sha256,
    validate_full_game_collection,
)


@pytest.fixture(scope="module", autouse=True)
def isolated_runtime():
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(2)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(67)
            yield
    finally:
        torch.set_num_threads(previous)


def terminal_team_setup():
    c = configured(player_count=3, teams=(1, 1, 2), max_turns=8, max_decisions=16)
    load(c.batch, owner=0, hp=0, mask=0)
    load(c.batch, owner=2, hp=1, illness=1, mask=0)
    c.batch.seed_confusion(ids([0]), ids([2]), ids([1]))
    return c


def test_real_interleaved_actions_get_their_own_faction_outcome_including_dead_teammates():
    c = terminal_team_setup()
    r = collect_full_game_episodes(c, FullGameActorCritic())
    episode = r.episodes[0]
    assert episode.outcome.status == "winner" and episode.outcome.winning_players == (0, 1)
    assert episode.outcome.terminal_values == (1, 1, -1, 0, 0, 0, 0, 0, 0)
    s = episode.samples
    assert s is not None and s.commands[:, 3].tolist() == [1, 2]
    assert s.terminal_targets.tolist() == [1, -1]
    assert s.observation.policy_gradient_mask.tolist() == [True, False]
    assert not s.previous_memory.any()
    assert r.accepted_decisions == r.eligible_decisions == 2
    assert r.eligible_policy_decisions == 1 and r.collection_error is None
    assert not r.rejected_commands.size
    validate_full_game_collection(r)
    for a in (
        s.commands,
        s.previous_memory,
        s.behavior_log_probabilities,
        s.behavior_values,
        s.terminal_targets,
    ):
        assert not a.flags.writeable


def test_post_death_bow_draw_supplies_valid_zero_targets_for_actual_accepted_commands():
    c = configured(max_turns=8, max_decisions=16)
    hand(c.batch, [112])
    load(c.batch, owner=0, hp=1, illness=1, mask=0)
    load(c.batch, owner=1, hp=1, mask=8)
    p = FullGameActorCritic()
    biased(p, 0)
    r = collect_full_game_episodes(c, p)
    e = r.episodes[0]
    assert e.outcome.status == "draw" and e.outcome.terminal_valid[:2] == (True, True)
    assert e.samples is not None and len(e.samples.commands) >= 1
    assert not e.samples.terminal_targets.any()
    assert r.eligible_decisions == e.outcome.accepted_commands


@pytest.mark.parametrize("draw", [False, True])
def test_zero_command_endings_do_not_fabricate_policy_or_value_samples(draw):
    c = configured(player_count=3, teams=(1, 1, 1) if not draw else (0, 0, 0))
    if draw:
        for seat in range(3):
            load(c.batch, owner=seat, hp=0, mask=0)
    r = collect_full_game_episodes(c, FullGameActorCritic())
    s = r.episodes[0].samples
    assert s is not None and s.commands.shape == (0, 6)
    assert s.observation.global_features.shape == (0, 112)
    assert r.eligible_decisions == r.accepted_decisions == 0
    assert r.episodes[0].outcome.status == ("draw" if draw else "winner")


@pytest.mark.parametrize("bound", ["turn", "decision"])
def test_entire_truncated_episodes_are_excluded_instead_of_fake_zero_draw_targets(bound):
    c = configured(
        max_turns=1 if bound == "turn" else 32, max_decisions=1 if bound == "decision" else 16
    )
    p = FullGameActorCritic()
    biased(p, 0)
    r = collect_full_game_episodes(c, p)
    assert r.episodes[0].outcome.status == f"{bound}-limit"
    assert r.episodes[0].samples is None
    assert not any(r.episodes[0].outcome.terminal_valid)
    assert r.accepted_decisions == 1 and r.eligible_decisions == 0


def failing_setup(*, completed_first=False):
    c = configured(size=2, initial_mp=6, hidden_cost_policy="strict-error", max_decisions=32)
    for env, actual in enumerate((236, 235)):
        if env == 0 and completed_first:
            # This row really plays and ends on its first action, before the
            # other row's next command hits the actual-cost error.
            load(c.batch, env=0, hp=1, illness=1, mask=0)
        else:
            hand(c.batch, [(actual, 236, 0)], env=env)
    p = FullGameActorCritic()
    with torch.no_grad():
        # A fixed, canonical network routes public ready->slot1 and
        # public selection->confirm. A constant slot1 bias would just cancel
        # the leader repeatedly, never reaching the actual cost failure.
        for parameter in p.parameters():
            parameter.zero_()
        h = p.architecture.hidden_size
        offset = 27 * p.architecture.embedding_size
        for index, phase in enumerate((1, 2)):
            p.context_encoder[0].weight[index, phase] = 1
            p.observation_encoder[0].weight[index, offset + index] = 1
            p.memory.weight_ih[2 * h + index, index] = 1
        p.memory.bias_ih[h : 2 * h].fill_(-1000)
        p.action_head.weight[1, 0] = 1000
        p.action_head.weight[0, 1] = 1000
    return c, p


@pytest.mark.parametrize("completed_first", [False, True])
def test_rejected_batch_keeps_exact_unaccepted_commands_and_excludes_every_incomplete_episode(
    completed_first,
):
    c, p = failing_setup(completed_first=completed_first)
    r = collect_full_game_episodes(c, p)
    assert r.collection_error == "full-game hidden actual miracle cost is unaffordable"
    assert r.rejected_commands[:, 0].tolist() == ([1] if completed_first else [0, 1])
    assert r.rejected_commands[:, 2].tolist() == ([2] if completed_first else [2, 2])
    assert r.rejected_commands[:, 5].tolist() == ([0] if completed_first else [0, 0])
    assert r.eligible_decisions == int(completed_first)
    for e in r.episodes:
        if e.outcome.environment == 0 and completed_first:
            assert e.outcome.status == "winner" and e.samples is not None
            assert e.outcome.accepted_commands == 1
            assert e.samples.terminal_targets.tolist() == [-1]
        else:
            assert e.outcome.status == "collection-aborted" and e.samples is None
            assert e.outcome.accepted_commands == 1
    validate_full_game_collection(r)


def test_source_policy_mutation_does_not_change_private_frozen_behavior(monkeypatch):
    c = terminal_team_setup()
    p = FullGameActorCritic()
    before = full_game_policy_sha256(p)
    original = FullGamePolicyController.step

    def mutate_source(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        with torch.no_grad():
            p.action_head.bias.add_(1)
        return result

    monkeypatch.setattr(FullGamePolicyController, "step", mutate_source)
    r = collect_full_game_episodes(c, p)
    assert r.metadata.behavior_policy_sha256 == before != full_game_policy_sha256(p)
    assert p.training and all(t.requires_grad for t in p.parameters())


def test_encoder_or_policy_error_is_not_hidden_as_a_native_episode_failure(monkeypatch):
    c = configured(max_decisions=16)

    def broken(*args, **kwargs):
        raise ValueError("broken policy")

    monkeypatch.setattr(FullGamePolicyController, "step", broken)
    with pytest.raises(ValueError, match="broken policy"):
        collect_full_game_episodes(c, FullGameActorCritic())


@pytest.mark.parametrize("limit", [0, True, 32769, 1])
def test_insufficient_storage_budget_rejects_before_start_instead_of_partial_targets(limit):
    c = configured(max_decisions=16)
    before = c.batch.episode_snapshot().copy()
    with pytest.raises(ValueError, match="storage"):
        collect_full_game_episodes(c, FullGameActorCritic(), max_stored_decisions=limit)
    np.testing.assert_array_equal(before, c.batch.episode_snapshot())


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"local_training_eligible": True},
        {"return_rule": "discounted"},
        {"incomplete_episodes": "bootstrap"},
        {"behavior_policy_sha256": "invalid"},
    ],
)
def test_collection_metadata_cannot_change_credit_or_claim_readiness(change):
    r = collect_full_game_episodes(terminal_team_setup(), FullGameActorCritic())
    with pytest.raises(ValidationError):
        FullGameCollectionMetadata.model_validate(r.metadata.model_dump() | change)


@pytest.mark.parametrize(
    "field", ["terminal_targets", "commands", "behavior_values", "previous_memory"]
)
def test_learning_admission_rejects_corrupt_targets_leases_values_or_seat_starts(field):
    r = collect_full_game_episodes(terminal_team_setup(), FullGameActorCritic())
    e = r.episodes[0]
    s = e.samples
    assert s is not None
    a = getattr(s, field).copy()
    if field == "terminal_targets":
        a[0] = 0
    elif field == "commands":
        a[0, 2] = 2
    elif field == "behavior_values":
        a[0] = np.nan
    else:
        a[0, 0] = 1
    corrupt = replace(r, episodes=(replace(e, samples=replace(s, **{field: a})),))
    with pytest.raises(ValueError):
        validate_full_game_collection(corrupt)


@pytest.mark.parametrize(
    "players,teams", [(2, (0, 0)), (4, (1, 1, 2, 2)), (9, (1, 2, 3, 4, 1, 2, 3, 4, 0))]
)
def test_complete_pool_frozen_collection_has_per_actor_returns_and_accepted_public_data(
    players, teams
):
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
        p = FullGameActorCritic()
        before = full_game_policy_sha256(p)
        r = collect_full_game_episodes(c, p, sampling_seed=901)
        assert r.collection_error is None and r.eligible_decisions > 0
        assert before == full_game_policy_sha256(p) == r.metadata.behavior_policy_sha256
        for e in r.episodes:
            if e.samples is None:
                continue
            s = e.samples
            targets = np.asarray(e.outcome.terminal_values)[s.commands[:, 3]]
            np.testing.assert_array_equal(s.terminal_targets, targets)
            assert s.commands.shape[0] == e.outcome.accepted_commands
            assert s.observation.leases[:, 0].tolist() == [e.outcome.environment] * len(s.commands)
        validate_full_game_collection(r)
        replay = verify_full_game_behavior(r, p, chunk_size=128)
        assert replay.decisions == r.eligible_decisions and replay.seat_sequences > 0


def test_behavior_replay_rejects_wrong_weights_or_forged_probabilities():
    p = FullGameActorCritic()
    r = collect_full_game_episodes(terminal_team_setup(), p)
    assert verify_full_game_behavior(r, p, chunk_size=1).decisions == 2
    e = r.episodes[0]
    s = e.samples
    assert s is not None
    logs = s.behavior_log_probabilities.copy()
    logs[0] -= 0.25
    corrupt = replace(
        r, episodes=(replace(e, samples=replace(s, behavior_log_probabilities=logs)),)
    )
    with pytest.raises(ValueError, match="probability or value differs"):
        verify_full_game_behavior(corrupt, p)
    with torch.no_grad():
        p.action_head.bias[0] += 1
    with pytest.raises(ValueError, match="weights differ"):
        verify_full_game_behavior(r, p)


def test_individually_consistent_outputs_cannot_hide_a_broken_seat_memory_handoff():
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(67)
        p = FullGameActorCritic()
        c = configured(
            acquisition_mode="all-held-weighted",
            max_turns=256,
            max_decisions=2048,
            apocalypse_after_turns=64,
        )
        r = collect_full_game_episodes(c, p, sampling_seed=901)
    e = r.episodes[0]
    s = e.samples
    assert s is not None
    sequence = next(x for x in full_game_seat_sequences(r) if len(x.rows) >= 2)
    row = int(sequence.rows[1])
    memory = s.previous_memory.copy()
    logs, values = s.behavior_log_probabilities.copy(), s.behavior_values.copy()
    memory[row, 0] += 0.25
    with torch.no_grad():
        logits, value, _ = p(
            full_game_policy_inputs(s.observation.take(ids([row]))),
            torch.from_numpy(memory[row : row + 1].copy()),
        )
    logs[row] = torch.log_softmax(logits, dim=1)[0, s.commands[row, 5]].item()
    values[row] = value[0].item()
    corrupt = replace(
        r,
        episodes=(
            replace(
                e,
                samples=replace(
                    s,
                    previous_memory=memory,
                    behavior_log_probabilities=logs,
                    behavior_values=values,
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="memory handoff differs"):
        verify_full_game_behavior(corrupt, p)
