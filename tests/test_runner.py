import pytest
from pydantic import ValidationError

from godfield_bot.runner import RunnerPolicyName, TrainingRunConfig


def test_executable_policy_requires_positive_action_budget() -> None:
    with pytest.raises(ValidationError, match="positive in-match action budget"):
        TrainingRunConfig(
            expected_client_sha256="a" * 64,
            policy=RunnerPolicyName.HEURISTIC_V0,
            max_in_match_actions=0,
        )


def test_safe_observer_defaults_to_zero_action_budget() -> None:
    config = TrainingRunConfig(expected_client_sha256="a" * 64)

    assert config.policy is RunnerPolicyName.SAFE_OBSERVER
    assert config.max_in_match_actions == 0
