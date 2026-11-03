"""Terminal faction credit only: no shaping, automatic resets or learner claims."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from godfield_bot.full_game import FULL_GAME_RULESET_ID, DevelopmentFullGameBatch, FullGameMetadata
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    IntArray = npt.NDArray[np.int64]
    BoolArray = npt.NDArray[np.bool_]


class FullGameRewardMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    reward_schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    ruleset_id: Literal[
        "integrated-full-game-development-v32", "integrated-full-game-development-v33"
    ] = FULL_GAME_RULESET_ID
    environment_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    values: Literal["win-plus1-loss-minus1-draw0-each-present-seat"] = (
        "win-plus1-loss-minus1-draw0-each-present-seat"
    )
    team_credit: Literal["include-eliminated-winning-teammates-no-size-normalization"] = (
        "include-eliminated-winning-teammates-no-size-normalization"
    )
    shaping: Literal["none"] = "none"
    timing: Literal["native-true-endings-only-once-per-adapter-epoch"] = (
        "native-true-endings-only-once-per-adapter-epoch"
    )
    truncations_and_errors: Literal["invalid-terminal-target-never-synthetic-loss"] = (
        "invalid-terminal-target-never-synthetic-loss"
    )
    forced_turns: Literal["zero-policy-weight-not-zero-outcome-reward"] = (
        "zero-policy-weight-not-zero-outcome-reward"
    )
    reset: Literal["explicit-no-active-reset-no-uncollected-ending-reset-reseed-teams"] = (
        "explicit-no-active-reset-no-uncollected-ending-reset-reseed-teams"
    )
    complete_policy_encoder_implemented: Literal[False] = False
    complete_rollout_and_learner_implemented: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False


def _readonly(array: IntArray | BoolArray) -> None:
    array.setflags(write=False)


@dataclass(frozen=True)
class FullGameRewardBatch:
    """Credit events, not current-state values: invalid zero is not a draw."""

    epochs: IntArray
    decisions: IntArray
    values: IntArray  # [B,9], absolute seats
    valid: BoolArray  # true once for each present seat at a real ending
    terminated: BoolArray  # [B], current native true ending, even after collection
    truncated: BoolArray  # [B], never a valid terminal target


@dataclass(frozen=True)
class FullGameRewardTransition:
    commands: IntArray  # accepted public six-column commands only
    actors: IntArray  # [B], pre-step actor, -1 for unstepped environments
    policy_gradient_masks: BoolArray  # [B,1], false for unstepped or forced decisions
    rewards: FullGameRewardBatch


class FullGameRewardAdapter:
    """Own the action/reset cursor when collecting credit; do not step behind it.

    Trusted setup/start calls on ``configured.batch`` are allowed while collecting:
    they do not advance decisions. Raw steps/resets are rejected as cursor drift.
    Native errors propagate; neither native nor credit state is changed by a
    rejected batch. This component has no optimizer, model, discount or replay log.
    """

    def __init__(self, configured: DevelopmentFullGameBatch) -> None:
        import godfield_sim as native
        import numpy as np

        schema = getattr(native, "FULL_GAME_REWARD_SCHEMA_VERSION", None)
        if (
            type(schema) is not int
            or schema != 1
            or any(
                not hasattr(configured.batch, method)
                for method in ("terminal_rewards", "terminal_reward_masks", "winning_seats")
            )
        ):
            raise ProvisionalRuleUnavailableError("native full-game reward interface differs")
        self.configured = configured
        FullGameMetadata.model_validate(configured.metadata.model_dump())
        self.metadata = FullGameRewardMetadata(
            ruleset_id=configured.metadata.ruleset_id,
            environment_metadata_sha256=hashlib.sha256(
                json.dumps(
                    configured.metadata.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        )
        self._size = configured.metadata.batch_size
        self._players = configured.metadata.player_count
        self._cursor = configured.batch.episode_snapshot().copy()
        self._credited = np.zeros(self._size, dtype=np.int64)
        self._read()

    def _read(self) -> tuple[IntArray, IntArray, BoolArray]:
        import numpy as np

        b = self.configured.batch
        state, values, masks, winners, teams = (
            b.episode_snapshot(),
            b.terminal_rewards(),
            b.terminal_reward_masks(),
            b.winning_seats(),
            b.team_ids(),
        )
        if (
            state.dtype != np.int64
            or state.shape != (self._size, 9)
            or values.dtype != np.int64
            or values.shape != (self._size, 9)
            or masks.dtype != np.bool_
            or masks.shape != (self._size, 9)
            or winners.dtype != np.bool_
            or winners.shape != (self._size, 9)
            or teams.dtype != np.int64
            or teams.shape != (self._size, 9)
        ):
            raise RuntimeError("native full-game terminal reward layout differs")
        ended = (state[:, 3] == 12) & np.isin(state[:, 5], (1, 2))
        won = (state[:, 3] == 12) & (state[:, 5] == 1)
        present = np.arange(9) < self._players
        if (
            np.any(teams[:, : self._players] < 0)
            or np.any(teams[:, : self._players] > 4)
            or np.any(teams[:, self._players :] != -1)
            or np.any(won & ((state[:, 6] < 0) | (state[:, 6] >= self._players)))
            or np.any((~won) & (state[:, 6] != -1))
            or np.any((state[:, 3] == 12) & ~np.isin(state[:, 5], (1, 2)))
            or np.any((state[:, 3] == 13) & ~np.isin(state[:, 5], (3, 4)))
            or np.any(~np.isin(state[:, 3], (12, 13)) & (state[:, 5] != 0))
        ):
            raise RuntimeError("native full-game terminal faction or ending differs")
        representative = np.clip(state[:, 6], 0, self._players - 1)
        winning_team = teams[np.arange(self._size), representative]
        expected_winners = (
            won[:, None]
            & present[None, :]
            & (
                (np.arange(9)[None, :] == representative[:, None])
                | ((winning_team[:, None] > 0) & (teams == winning_team[:, None]))
            )
        )
        expected_masks = ended[:, None] & present[None, :]
        expected_values = np.where(
            won[:, None] & present[None, :], np.where(expected_winners, 1, -1), 0
        )
        if (
            not np.array_equal(winners, expected_winners)
            or not np.array_equal(masks, expected_masks)
            or not np.array_equal(values, expected_values)
        ):
            raise RuntimeError("native full-game terminal reward mapping differs")
        return state, values, masks

    def _check_cursor(self, state: IntArray) -> None:
        import numpy as np

        if not np.array_equal(state[:, [0, 1, 7]], self._cursor[:, [0, 1, 7]]):
            raise RuntimeError("untracked full-game step/reset; use the reward adapter")

    def _collect(
        self, state: IntArray, native_values: IntArray, masks: BoolArray
    ) -> FullGameRewardBatch:
        import numpy as np

        fresh = masks.any(axis=1) & (self._credited != state[:, 0])
        valid = masks & fresh[:, None]
        values = np.where(valid, native_values, 0).astype(np.int64)
        epochs, decisions = state[:, 0].copy(), state[:, 1].copy()
        terminated = state[:, 3] == 12
        truncated = state[:, 3] == 13
        for array in (epochs, decisions, values, valid, terminated, truncated):
            _readonly(array)
        result = FullGameRewardBatch(epochs, decisions, values, valid, terminated, truncated)
        cursor = state.copy()
        credited = self._credited.copy()
        credited[fresh] = state[fresh, 0]
        self._cursor, self._credited = cursor, credited
        return result

    def poll(self) -> FullGameRewardBatch:
        """Collect setup/start endings too; repeated reads cannot pay twice."""
        state, values, masks = self._read()
        self._check_cursor(state)
        return self._collect(state, values, masks)

    def step(self, commands: IntArray) -> FullGameRewardTransition:
        import numpy as np

        if (
            not isinstance(commands, np.ndarray)
            or commands.dtype != np.int64
            or commands.ndim != 2
            or commands.shape[1] != 6
            or not commands.flags.c_contiguous
            or len(commands) > self._size
        ):
            raise ValueError("reward adapter requires bounded contiguous int64 six-column commands")
        state, _, _ = self._read()
        self._check_cursor(state)
        commands = commands.copy()
        envs = commands[:, 0]
        if np.any(envs < 0) or np.any(envs >= self._size):
            raise ValueError("reward adapter command environment is out of range")
        actors = np.full(self._size, -1, dtype=np.int64)
        actors[envs] = state[envs, 2]
        policy_masks = np.zeros((self._size, 1), dtype=np.bool_)
        policy_masks[envs] = self.configured.batch.policy_gradient_masks()[envs]
        expected = state.copy()
        expected[envs, 1] += 1
        expected[envs, 7] += 1
        expected[envs, 8] = commands[:, 5]
        # Native validates every row before committing any; no credit mutation
        # has happened yet. Never catch/substitute an unaffordable hidden action.
        self.configured.batch.step(commands)
        after, values, masks = self._read()
        if not np.array_equal(after[:, [0, 1, 7]], expected[:, [0, 1, 7]]) or not np.array_equal(
            after[envs, 8], commands[:, 5]
        ):
            raise RuntimeError("native accepted-command counters differ from reward cursor")
        for array in (commands, actors, policy_masks):
            _readonly(array)
        rewards = self._collect(after, values, masks)
        return FullGameRewardTransition(commands, actors, policy_masks, rewards)

    def reset_environments(self, environments: IntArray) -> None:
        """Explicit reset only after collection, truncation or unstarted setup."""
        import numpy as np

        if (
            not isinstance(environments, np.ndarray)
            or environments.dtype != np.int64
            or environments.ndim != 1
            or not environments.flags.c_contiguous
            or np.any(environments < 0)
            or np.any(environments >= self._size)
        ):
            raise ValueError("reward adapter reset environments are invalid")
        state, _, _ = self._read()
        self._check_cursor(state)
        if np.any(~np.isin(state[environments, 3], (0, 12, 13))):
            raise ValueError("reward adapter cannot silently reset an active episode")
        ending = state[environments, 3] == 12
        if np.any(ending & (self._credited[environments] != state[environments, 0])):
            raise ValueError("collect the terminal reward before resetting its episode")
        self.configured.batch.reset_environments(environments)
        after, _, _ = self._read()
        self._cursor = after.copy()
