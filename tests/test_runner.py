from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from godfield_bot.domain.game import GameState, PlayerState
from godfield_bot.runner import RunnerPolicyName, TrainingRunConfig, build_action_transition


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
            plain_weapon_attacks={"bronze-club": 1},
            plain_armor_defenses={"iron-shield": 4},
        )


def test_executable_policy_requires_bible_artifact_knowledge() -> None:
    with pytest.raises(ValidationError, match="Bible-verified plain artifacts"):
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


def test_action_transition_marks_unaccepted_unchanged_frame() -> None:
    before = game_state(field_number=1, opponent_hp=40)
    after = before.model_copy(update={"observed_at": datetime(2030, 1, 1, tzinfo=UTC)})

    transition = build_action_transition("target:1:CPU", before, after)

    assert transition.state_changed is False
    assert transition.before_state_digest == transition.after_state_digest
