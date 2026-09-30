"""Group-only ready-phase prior: legal masks and sampled trajectories stay intact."""

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from structlog.testing import capture_logs
from typer.testing import CliRunner

np = pytest.importorskip("numpy")
torch = pytest.importorskip("torch")
pytest.importorskip("godfield_sim")

from godfield_bot.cli import app  # noqa: E402
from godfield_bot.guardian_activity import guardian_ready_activity_loss  # noqa: E402
from godfield_bot.guardian_neural import (  # noqa: E402
    GuardianArenaPolicy,
    GuardianPolicyArchitecture,
)
from godfield_bot.guardian_rollout import GuardianRolloutArena  # noqa: E402
from godfield_bot.guardian_training import (  # noqa: E402
    READY_ACTIVITY_ALGORITHM,
    GuardianArenaManifest,
    GuardianDuelCollector,
    GuardianTrainingConfig,
    _runtime,
    load_guardian_checkpoint,
    replay_guardian_rollout,
    train_guardian_candidate,
    train_guardian_ppo,
)
from godfield_bot.model_registry import load_model  # noqa: E402

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
BIBLE = Path("data/snapshots/2026-09-20/bible.json")


def config(kind="discard", **changes):
    return GuardianTrainingConfig.model_validate(
        {
            "arena": {
                "batch_size": 4,
                "max_turns": 8,
                "max_decisions": 32,
                "inventory_utilities": kind != "old",
                "inventory_discards": kind == "discard",
                "refill": "weighted-discard-consumption-v1"
                if kind == "discard"
                else "weighted-utility-consumption-v1"
                if kind == "utility"
                else "weighted-consumption-v1",
            },
            "hidden_size": 32,
            "embedding_size": 8,
            "rollout_steps": 16,
            "updates": 1,
            "teacher_updates": 0,
            "ppo_epochs": 2,
            "environment_minibatch_size": 2,
            "evaluation_games": 4,
            "cpu_threads": 1,
            **changes,
        }
    )


def arena(cfg):
    return GuardianRolloutArena(catalog_path=CATALOG, bible_path=BIBLE, config=cfg.arena)


def policy(cfg):
    metadata = arena(cfg).metadata
    return GuardianArenaPolicy(
        GuardianPolicyArchitecture(
            vocabulary_size=297,
            hidden_size=cfg.hidden_size,
            embedding_size=cfg.embedding_size,
            hand_feature_count=metadata.hand_feature_count,
            action_count=metadata.action_count,
            observation_schema_id=metadata.observation_schema_id,
        )
    )


@pytest.fixture
def runtime():
    with _runtime(67, 1):
        yield


@pytest.mark.parametrize("actions", [30, 48])
def test_group_probability_analytic_loss_and_only_eligible_gradients(actions):
    logits = torch.zeros(5, actions, requires_grad=True)
    mask = torch.zeros(5, actions, dtype=torch.bool)
    mask[0, [0, 1, actions - 1]] = True  # 1/3 pass; nonpass group 2/3
    mask[1, [0]] = True  # forced pass
    mask[2, [0, 1]] = True  # excluded baseline actor / nonready
    mask[3, [1, 2]] = True  # no pass control, not a ready-pass choice
    mask[4, [0, 1]] = True  # 1/2 pass
    ready = torch.tensor([True, True, False, True, True])
    loss, probability, count = guardian_ready_activity_loss(logits, mask, ready)
    assert count == 2
    assert float(loss.detach()) == pytest.approx((-math.log(2 / 3) - math.log(1 / 2)) / 2)
    assert float(probability) == pytest.approx((1 / 3 + 1 / 2) / 2)
    loss.backward()
    assert logits.grad[0, 0] > 0 and logits.grad[4, 0] > 0
    assert logits.grad[0, 1] < 0 and logits.grad[0, actions - 1] < 0
    assert not logits.grad[~mask].any()
    assert not logits.grad[1:4].any()
    torch.testing.assert_close(logits.grad[0, 1], logits.grad[0, actions - 1])


def test_nonpass_group_probability_weighted_gradients_and_logit_shift_invariance():
    logits = torch.zeros(2, 48, dtype=torch.float64, requires_grad=True)
    with torch.no_grad():
        logits[:, :3] = torch.tensor([2, 0.3, -0.7])
    mask = torch.zeros_like(logits, dtype=torch.bool)
    mask[:, :3] = True
    ready = torch.ones(2, dtype=torch.bool)
    loss, p, _ = guardian_ready_activity_loss(logits, mask, ready)
    shifted_loss, shifted_p, _ = guardian_ready_activity_loss(logits + 100, mask, ready)
    torch.testing.assert_close(loss, shifted_loss)
    torch.testing.assert_close(p, shifted_p)
    loss.backward()
    assert float(logits.grad[0, 1] / logits.grad[0, 2]) == pytest.approx(math.exp(1))


@pytest.mark.parametrize("sentinel", [float("-inf"), torch.finfo(torch.float32).min])
def test_no_samples_connected_zero_ignores_illegal_sentinels(sentinel):
    logits = torch.full((4, 48), sentinel)
    logits[:, 0] = 1000
    logits.requires_grad_()
    mask = torch.zeros_like(logits, dtype=torch.bool)
    mask[:, 0] = True
    loss, p, count = guardian_ready_activity_loss(logits, mask, torch.ones(4, dtype=torch.bool))
    assert count == 0 and float(loss.detach()) == float(p) == 0
    loss.backward()
    assert torch.isfinite(logits.grad).all() and not logits.grad.any()


def test_illegal_nan_and_equal_minimum_sentinels_never_contribute_group_probability():
    logits = torch.full((2, 48), float("nan"))
    logits[:, :2] = torch.finfo(torch.float32).min
    logits.requires_grad_()
    mask = torch.zeros_like(logits, dtype=torch.bool)
    mask[:, :2] = True
    loss, p, count = guardian_ready_activity_loss(logits, mask, torch.ones(2, dtype=torch.bool))
    assert count == 2 and float(loss.detach()) == pytest.approx(math.log(2))
    assert float(p) == pytest.approx(0.5)
    loss.backward()
    assert torch.isfinite(logits.grad).all()
    assert not logits.grad[:, 2:].any()


@pytest.mark.parametrize("score", [-1000, 0, 1000])
def test_extreme_pass_preference_stays_finite(score):
    logits = torch.zeros(3, 30)
    logits[:, 0] = score
    logits.requires_grad_()
    mask = torch.zeros_like(logits, dtype=torch.bool)
    mask[:, :2] = True
    loss, probability, count = guardian_ready_activity_loss(
        logits, mask, torch.ones(3, dtype=torch.bool)
    )
    assert count == 3 and torch.isfinite(loss) and loss >= 0
    assert 0 <= float(probability) <= 1
    loss.backward()
    assert torch.isfinite(logits.grad).all()


@pytest.mark.parametrize(
    "mutation", ["shape", "dtype", "ready-shape", "ready-dtype", "integer", "width", "nan"]
)
def test_invalid_loss_contract_rejected(mutation):
    logits = torch.zeros(2, 30)
    mask = torch.ones_like(logits, dtype=torch.bool)
    ready = torch.ones(2, dtype=torch.bool)
    if mutation == "shape":
        mask = mask[:1]
    elif mutation == "dtype":
        mask = mask.to(torch.float32)
    elif mutation == "ready-shape":
        ready = ready[:1]
    elif mutation == "ready-dtype":
        ready = ready.to(torch.int64)
    elif mutation == "integer":
        logits = logits.to(torch.int64)
    elif mutation == "width":
        logits = logits[:, :29]
        mask = mask[:, :29]
    else:
        logits[0, 0] = float("nan")
    with pytest.raises(ValueError, match="ready activity"):
        guardian_ready_activity_loss(logits, mask, ready)


@pytest.mark.parametrize(
    "change",
    [
        {"ready_activity_weight": -1},
        {"ready_activity_weight": 5},
        {"ready_activity_weight": float("nan")},
        {"ready_activity_weight": float("inf")},
        {"ready_activity_scope": "all-moves"},
        {"updates": 0, "teacher_updates": 1, "ready_activity_weight": 0.25},
    ],
)
def test_config_bounded_optin_and_not_imitation_only(change):
    with pytest.raises(ValueError):
        config(**change)


@pytest.mark.parametrize("kind", ["old", "utility", "discard"])
def test_activity_collects_no_extra_labels_and_changes_no_trajectory(kind):
    original_cfg = config(kind)
    changed_cfg = config(kind, ready_activity_weight=0.25)
    with _runtime(67, 1):
        original = GuardianDuelCollector(arena(original_cfg), policy(original_cfg)).collect(
            original_cfg
        )
    with _runtime(67, 1):
        changed = GuardianDuelCollector(arena(changed_cfg), policy(changed_cfg)).collect(
            changed_cfg
        )
    assert original.defense_teacher_actions is changed.defense_teacher_actions is None
    assert original.digest == changed.digest
    assert original.outcome_coverage == changed.outcome_coverage
    for field in (
        "actors",
        "actions",
        "starts",
        "initial_states",
        "policy_trainable",
        "old_log_probabilities",
        "old_values",
        "rewards",
        "done",
        "advantages",
        "returns",
    ):
        torch.testing.assert_close(
            getattr(original, field), getattr(changed, field), rtol=0, atol=0
        )
    for a, b in zip(original.observations, changed.observations, strict=True):
        torch.testing.assert_close(a, b, rtol=0, atol=0)


def test_activity_loss_learns_from_onpolicy_states_without_forcing_card_labels(runtime):
    cfg = config(
        ready_activity_weight=1,
        value_weight=0,
        entropy_weight=0,
        environment_minibatch_size=4,
    )
    model = policy(cfg)
    original = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    rollout = replace(original, advantages=torch.zeros_like(original.advantages))
    ready = rollout.policy_trainable & (rollout.observations[0][..., 0] > 0)
    mask = rollout.observations[6]
    initial, _ = replay_guardian_rollout(model, rollout, torch.arange(4))
    initial_loss, initial_p, count = guardian_ready_activity_loss(initial, mask, ready)
    assert count > 0
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
    for _ in range(5):
        metric = train_guardian_ppo(model, optimizer, rollout, cfg)
        assert metric.ready_activity_samples == count * cfg.ppo_epochs
        assert metric.ready_activity_loss > 0 and 0 <= metric.ready_pass_probability <= 1
        assert metric.defense_teacher_samples == 0
    final, _ = replay_guardian_rollout(model, rollout, torch.arange(4))
    final_loss, final_p, _ = guardian_ready_activity_loss(final, mask, ready)
    assert final_loss.detach() < initial_loss.detach()
    assert final_p < initial_p
    for field in ("actions", "rewards", "old_log_probabilities", "returns", "observations"):
        assert getattr(rollout, field) is getattr(original, field)


@pytest.mark.parametrize("excluded", ["nonready", "forced-pass", "no-pass", "baseline"])
def test_excluded_states_cannot_change_optimizer_update(runtime, excluded):
    cfg = config(ready_activity_weight=1, value_weight=0, entropy_weight=0)
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg)
    globals_ = rollout.observations[0].clone()
    mask = rollout.observations[6].clone()
    trainable = rollout.policy_trainable.clone()
    if excluded == "nonready":
        globals_[..., 0] = 0
    elif excluded == "forced-pass":
        globals_[..., 0] = 1
        mask.zero_()
        mask[..., 0] = True
        rollout = replace(rollout, actions=torch.zeros_like(rollout.actions))
    elif excluded == "no-pass":
        globals_[..., 0] = 1
        mask[..., 0] = False
        mask[..., 1] = True
        rollout = replace(rollout, actions=torch.ones_like(rollout.actions))
    else:
        trainable[globals_[..., 0] > 0] = False
        assert trainable.any()
    rollout = replace(
        rollout,
        observations=(globals_, *rollout.observations[1:6], mask),
        advantages=torch.zeros_like(rollout.advantages),
        policy_trainable=trainable,
    )
    disabled_cfg = cfg.model_copy(update={"ready_activity_weight": 0})
    first, second = deepcopy(model), deepcopy(model)
    with _runtime(778, 1):
        a = train_guardian_ppo(first, torch.optim.Adam(first.parameters()), rollout, cfg)
    with _runtime(778, 1):
        b = train_guardian_ppo(second, torch.optim.Adam(second.parameters()), rollout, disabled_cfg)
    assert a == b and a.ready_activity_samples == 0
    for name, value in first.state_dict().items():
        torch.testing.assert_close(value, second.state_dict()[name], rtol=0, atol=0)


def test_disabled_default_does_not_call_activity_loss(runtime, monkeypatch):
    import godfield_bot.guardian_training as module

    cfg = config()
    model = policy(cfg)
    rollout = GuardianDuelCollector(arena(cfg), model).collect(cfg)

    def fail(*_):
        pytest.fail("disabled activity must not change the original optimizer path")

    monkeypatch.setattr(module, "guardian_ready_activity_loss", fail)
    metric = train_guardian_ppo(model, torch.optim.Adam(model.parameters()), rollout, cfg)
    assert cfg.ready_activity_weight == 0
    assert metric.ready_activity_samples == metric.ready_activity_loss == 0
    assert metric.ready_pass_probability == 0


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory):
    root = tmp_path_factory.mktemp("guardian-activity")
    return train_guardian_candidate(
        catalog_path=CATALOG,
        bible_path=BIBLE,
        checkpoint_root=root,
        config=config(ready_activity_weight=0.25, defense_feedback_weight=1),
    )


def test_checkpoint_records_activity_and_defense_separately_no_live_change(checkpoint):
    directory, manifest = checkpoint
    metric = manifest.update_metrics[0].ppo
    assert manifest.algorithm == READY_ACTIVITY_ALGORITHM
    assert manifest.training.ready_activity_weight == 0.25
    assert metric.ready_activity_samples > 0 and metric.defense_teacher_samples > 0
    assert not manifest.live_checkpoint_compatible and not manifest.promotion_eligible
    assert not manifest.full_game_training_ready and not manifest.official_fidelity_verified
    assert load_guardian_checkpoint(directory)[0] == manifest
    assert hashlib.sha256((directory / "arena-weights.pt").read_bytes()).hexdigest() == (
        manifest.weights_sha256
    )
    with pytest.raises(FileNotFoundError):
        load_model(directory)


@pytest.mark.parametrize(
    "mutation", ["missing", "budget", "algorithm", "disabled", "empty", "scope", "gate"]
)
def test_activity_manifest_tampering_rejected(checkpoint, mutation):
    data = checkpoint[1].model_dump()
    metric = data["update_metrics"][0]["ppo"]
    if mutation == "missing":
        metric.pop("ready_activity_loss")
    elif mutation == "budget":
        metric["ready_activity_samples"] = 10000000
    elif mutation == "algorithm":
        data["algorithm"] = "provisional-guardian-duel-recurrent-imitation-ppo-v1"
    elif mutation == "disabled":
        data["training"]["ready_activity_weight"] = 0
        data["algorithm"] = "provisional-guardian-duel-recurrent-imitation-ppo-defense-feedback-v1"
    elif mutation == "empty":
        metric["ready_activity_samples"] = 0
        metric["ready_activity_loss"] = 1
    elif mutation == "scope":
        data["training"]["ready_activity_scope"] = "all-ready"
    else:
        data["promotion_eligible"] = True
    with pytest.raises(ValueError):
        GuardianArenaManifest.model_validate(data)


def test_historical_activity_data_remains_unknown(checkpoint):
    data = checkpoint[1].model_dump()
    data["training"].pop("ready_activity_weight")
    data["training"].pop("ready_activity_scope")
    data["algorithm"] = "provisional-guardian-duel-recurrent-imitation-ppo-defense-feedback-v1"
    for metric in data["update_metrics"]:
        for key in ("ready_activity_loss", "ready_pass_probability", "ready_activity_samples"):
            metric["ppo"].pop(key)
    loaded = GuardianArenaManifest.model_validate(data)
    assert loaded.training.ready_activity_weight == 0
    assert loaded.update_metrics[0].ppo.ready_activity_loss is None
    assert loaded.update_metrics[0].ppo.ready_pass_probability is None
    assert loaded.update_metrics[0].ppo.ready_activity_samples is None


def test_cli_ready_activity_optin(tmp_path, monkeypatch):
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_: None)
    with capture_logs():
        result = CliRunner().invoke(
            app,
            [
                "simulation",
                "guardian-train",
                "--checkpoint-root",
                str(tmp_path / "cli"),
                "--ready-activity-weight",
                "0.25",
                "--batch-size",
                "4",
                "--max-turns",
                "8",
                "--max-decisions",
                "32",
                "--rollout-steps",
                "16",
                "--teacher-updates",
                "0",
                "--updates",
                "1",
                "--ppo-epochs",
                "1",
                "--evaluation-games",
                "4",
                "--hidden-size",
                "32",
                "--embedding-size",
                "8",
                "--cpu-threads",
                "1",
            ],
        )
    assert result.exit_code == 0, result.output
    manifest = GuardianArenaManifest.model_validate(json.loads(result.output)["manifest"])
    assert manifest.algorithm == READY_ACTIVITY_ALGORITHM
    assert manifest.training.ready_activity_weight == 0.25
    assert manifest.update_metrics[0].ppo.ready_activity_samples > 0
