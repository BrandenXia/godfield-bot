import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from godfield_bot.config import AppSettings
from godfield_bot.domain.game import GameState, PlayerState
from godfield_bot.domain.run import RunMode, RunRecord, RunStatus
from godfield_bot.runner import (
    RunnerPolicyName,
    TrainingCampaignConfig,
    TrainingRunConfig,
    build_action_transition,
    run_training_campaign,
)


def game_state(*, field_number: int, opponent_hp: int) -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=field_number,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=40, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=opponent_hp, mp=10, money=20, is_self=False),
        ),
        hand=(),
        scene_layers=(),
    )


def test_executable_policy_requires_positive_action_budget() -> None:
    with pytest.raises(ValidationError, match="positive in-match action budget"):
        TrainingRunConfig(
            expected_client_sha256="a" * 64,
            policy=RunnerPolicyName.HEURISTIC_V0,
            max_in_match_actions=0,
            verified_weapon_attacks={"bronze-club": ("ATK1", 1.0)},
            plain_armor_defenses={"iron-shield": 4},
        )


def test_executable_policy_requires_bible_artifact_knowledge() -> None:
    with pytest.raises(ValidationError, match="Bible-audited artifact values"):
        TrainingRunConfig(
            expected_client_sha256="a" * 64,
            policy=RunnerPolicyName.HEURISTIC_V0,
            max_in_match_actions=1,
        )


def test_safe_observer_defaults_to_zero_action_budget() -> None:
    config = TrainingRunConfig(expected_client_sha256="a" * 64)

    assert config.policy is RunnerPolicyName.SAFE_OBSERVER
    assert config.max_in_match_actions == 0
    assert config.no_progress_seconds == 60


def test_no_progress_limit_is_bounded() -> None:
    with pytest.raises(ValidationError):
        TrainingRunConfig(
            expected_client_sha256="a" * 64,
            no_progress_seconds=9,
        )


def test_action_transition_records_state_and_hp_changes() -> None:
    before = game_state(field_number=1, opponent_hp=40)
    after = game_state(field_number=2, opponent_hp=31)

    transition = build_action_transition("confirm:attack", before, after)

    assert transition.state_changed is True
    assert transition.before_state_digest != transition.after_state_digest
    assert transition.field_delta == 1
    assert transition.player_hp_deltas == {"CPU": -9}
    assert transition.before_state == before
    assert transition.after_state == after


def test_action_transition_marks_unaccepted_unchanged_frame() -> None:
    before = game_state(field_number=1, opponent_hp=40)
    after = before.model_copy(update={"observed_at": datetime(2030, 1, 1, tzinfo=UTC)})

    transition = build_action_transition("target:1:CPU", before, after)

    assert transition.state_changed is False
    assert transition.before_state_digest == transition.after_state_digest
    assert transition.before_state == before
    assert transition.after_state == after


def training_run(
    run_id: str,
    *,
    status: RunStatus,
    reason: str,
    result: str | None = None,
) -> RunRecord:
    outcome: dict[str, object] = {"reason": reason}
    if result is not None:
        outcome["result"] = result
    return RunRecord(
        run_id=run_id,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        status=status,
        mode=RunMode.TRAINING,
        identity="ロキ-67",
        client_sha256="a" * 64,
        policy_id="heuristic-v0",
        outcome=outcome,
    )


def campaign_config(*, max_games: int) -> TrainingCampaignConfig:
    return TrainingCampaignConfig(
        game=TrainingRunConfig(
            expected_client_sha256="a" * 64,
            policy=RunnerPolicyName.HEURISTIC_V0,
            max_in_match_actions=100,
            verified_weapon_attacks={"bronze-club": ("ATK1", 1.0)},
            plain_armor_defenses={"iron-shield": 4},
        ),
        max_games=max_games,
        restart_delay_seconds=0,
    )


def test_training_campaign_keeps_one_run_per_completed_game(monkeypatch) -> None:
    runs = iter(
        [
            training_run(
                "run-win",
                status=RunStatus.COMPLETED,
                reason="classified_terminal",
                result="win",
            ),
            training_run(
                "run-loss",
                status=RunStatus.COMPLETED,
                reason="classified_terminal",
                result="loss",
            ),
        ]
    )

    async def fake_run(*args, **kwargs):
        return next(runs)

    monkeypatch.setattr("godfield_bot.runner.run_training_observer", fake_run)

    summary = asyncio.run(run_training_campaign(AppSettings(), campaign_config(max_games=2)))

    assert summary.stop_reason == "game_limit"
    assert summary.games_started == 2
    assert summary.games_completed == 2
    assert (summary.wins, summary.losses, summary.draws) == (1, 1, 0)
    assert summary.run_ids == ("run-win", "run-loss")


def test_unlimited_training_campaign_stops_on_first_anomaly(monkeypatch) -> None:
    runs = iter(
        [
            training_run(
                "run-draw",
                status=RunStatus.COMPLETED,
                reason="classified_terminal",
                result="draw",
            ),
            training_run(
                "run-stalled",
                status=RunStatus.ABORTED,
                reason="no_progress_limit",
            ),
        ]
    )

    async def fake_run(*args, **kwargs):
        return next(runs)

    monkeypatch.setattr("godfield_bot.runner.run_training_observer", fake_run)

    summary = asyncio.run(run_training_campaign(AppSettings(), campaign_config(max_games=0)))

    assert summary.stop_reason == "aborted:no_progress_limit"
    assert summary.games_started == 2
    assert summary.games_completed == 1
    assert summary.draws == 1
    assert summary.last_run_status is RunStatus.ABORTED
