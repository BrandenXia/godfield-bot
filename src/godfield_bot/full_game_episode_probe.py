"""Unscripted whole-episode integration diagnostics, never learner/reward data."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from godfield_bot.full_game import (
    FULL_GAME_RULESET_ID,
    HIDDEN_COST_FIELDS,
    HIDDEN_REMOVAL_FIELDS,
    HIDDEN_TARGETING_FIELDS,
    HIDDEN_TRADE_FIELDS,
    INEFFECTIVE_FIELDS,
    HiddenCostPolicy,
    create_development_full_game_batch,
)
from godfield_bot.full_game_rewards import (
    FullGameRewardAdapter,
    FullGameRewardBatch,
    FullGameRewardMetadata,
)
from godfield_bot.full_game_teams import TeamId

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    from godfield_sim import FullGameBatch

Count = Annotated[int, Field(ge=0, strict=True)]
CommandToken = Annotated[int, Field(ge=0, le=2**53 - 1, strict=True)]
CommandRow = tuple[
    CommandToken, CommandToken, CommandToken, CommandToken, CommandToken, CommandToken
]
Status = Literal["winner", "draw", "turn-limit", "decision-limit", "engine-error"]
FINGERPRINT_VIEWS = (
    "episode_snapshot",
    "diagnostic_players",
    "diagnostic_inventory",
    "choice_masks",
    "attack_family_snapshot",
    "trade_snapshot",
    "market_snapshot",
    "market_escrow_snapshot",
    "hidden_targeting_snapshot",
    "hidden_trade_snapshot",
    "ineffective_snapshot",
    "ineffective_model_counts",
    "hidden_removal_snapshot",
    "team_ids",
    "winning_seats",
    "acquisition_snapshot",
)


class FullGameEpisodeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    environment: int = Field(ge=0, le=4095, strict=True)
    episode: int = Field(ge=1, strict=True)
    decision: int = Field(ge=1, strict=True)
    actor: int = Field(ge=-1, le=8, strict=True)
    native_phase: int = Field(ge=0, le=13, strict=True)
    native_outcome: int = Field(ge=0, le=4, strict=True)
    winner: int = Field(ge=-1, le=8, strict=True)
    winning_players: tuple[Annotated[int, Field(ge=0, le=8, strict=True)], ...] = ()
    completed_turns: Count
    accepted_commands: Count
    status: Status
    error_command: CommandRow | None = None
    error_reason: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def terminal_or_error(self) -> FullGameEpisodeResult:
        if (
            tuple(sorted(set(self.winning_players))) != self.winning_players
            or (bool(self.winning_players) != (self.status == "winner"))
            or (self.status == "winner" and self.winner not in self.winning_players)
        ):
            raise ValueError("episode winning players must match the terminal faction")
        if self.status == "engine-error":
            if (
                self.native_phase not in (1, 2, 3, 4, 6, 7)
                or self.native_outcome != 0
                or self.winner != -1
                or self.error_command is None
                or self.error_reason is None
                or self.error_command[:5]
                != (self.environment, self.episode, self.decision, self.actor, self.native_phase)
            ):
                raise ValueError("engine error must preserve its unaccepted native decision")
        else:
            phase, outcome = {
                "winner": (12, 1),
                "draw": (12, 2),
                "turn-limit": (13, 3),
                "decision-limit": (13, 4),
            }[self.status]
            if (
                self.native_phase != phase
                or self.native_outcome != outcome
                or (self.winner >= 0) != (self.status == "winner")
                or self.error_command is not None
                or self.error_reason is not None
            ):
                raise ValueError("episode status must match native ending, never a synthetic win")
        if self.decision != self.accepted_commands + 1:
            raise ValueError("episode decision and accepted-command accounting differs")
        return self


class FullGameEpisodeProbeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[6] = 6
    ruleset_id: Literal["integrated-full-game-development-v33"] = FULL_GAME_RULESET_ID
    source_kind: Literal["complete-pool-unscripted-episode-diagnostic-v1"] = (
        "complete-pool-unscripted-episode-diagnostic-v1"
    )
    policy: Literal["bounded-public-random-v1"] = "bounded-public-random-v1"
    resource_cap: Literal[99] = 99
    acquisition_mode: Literal["all-held-weighted"] = "all-held-weighted"
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint_views: tuple[str, ...] = FINGERPRINT_VIEWS
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    teams: tuple[TeamId, ...]
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    policy_seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    max_turns: int = Field(ge=1, le=10000, strict=True)
    max_decisions: int = Field(ge=1, le=40000, strict=True)
    apocalypse_after_turns: int = Field(ge=0, le=10000, strict=True)
    outcomes: tuple[FullGameEpisodeResult, ...]
    games_completed: Count
    winner_games: Count
    draws: Count
    turn_limit_games: Count
    decision_limit_games: Count
    engine_errors: Count
    rejected_batches: Count
    accepted_commands: Count
    forced_commands: Count
    accepted_commands_by_phase: tuple[Count, ...]
    automatic_gifts: Count
    hidden_targeting_fields: tuple[str, ...] = HIDDEN_TARGETING_FIELDS
    hidden_targeting_totals: tuple[Count, ...]
    hidden_trade_fields: tuple[str, ...] = HIDDEN_TRADE_FIELDS
    hidden_trade_totals: tuple[Count, ...]
    ineffective_fields: tuple[str, ...] = INEFFECTIVE_FIELDS
    ineffective_totals: tuple[Count, ...]
    ineffective_model_counts: tuple[Count, ...]
    hidden_removal_fields: tuple[str, ...] = HIDDEN_REMOVAL_FIELDS
    hidden_removal_totals: tuple[Count, ...]
    hidden_cost_policy: HiddenCostPolicy = "fizzle-provisional"
    hidden_cost_fields: tuple[str, ...] = HIDDEN_COST_FIELDS
    hidden_cost_totals: tuple[Count, ...]
    terminal_rewards_tracked: bool = Field(default=False, strict=True)
    reward_schema_version: StrictInt | None = Field(default=None, ge=1, le=1)
    reward_metadata_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    terminal_reward_totals: tuple[StrictInt, ...] | None = None
    terminal_reward_valid_counts: tuple[Count, ...] | None = None
    error_recovery: Literal["stop-failed-environment-never-substitute-an-action"] = (
        "stop-failed-environment-never-substitute-an-action"
    )
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameEpisodeProbeReport:
        counts = {
            status: sum(r.status == status for r in self.outcomes)
            for status in ("winner", "draw", "turn-limit", "decision-limit", "engine-error")
        }
        h, t = self.hidden_targeting_totals, self.hidden_trade_totals
        if (
            len(self.teams) != self.player_count
            or any(
                row.winner >= self.player_count
                or row.winning_players
                != (
                    tuple(
                        seat
                        for seat in range(self.player_count)
                        if self.teams[row.winner] != 0
                        and self.teams[seat] == self.teams[row.winner]
                    )
                    if self.teams[row.winner] != 0
                    else (row.winner,)
                )
                for row in self.outcomes
                if row.status == "winner"
            )
            or tuple(r.environment for r in self.outcomes) != tuple(range(self.batch_size))
            or any(
                r.winner >= self.player_count
                or r.actor >= self.player_count
                or r.accepted_commands > self.max_decisions
                or r.completed_turns > self.max_turns
                or (r.status == "turn-limit" and r.completed_turns != self.max_turns)
                or (r.status == "decision-limit" and r.accepted_commands != self.max_decisions)
                for r in self.outcomes
            )
            or self.winner_games != counts["winner"]
            or self.draws != counts["draw"]
            or self.turn_limit_games != counts["turn-limit"]
            or self.decision_limit_games != counts["decision-limit"]
            or self.engine_errors != counts["engine-error"]
            or self.games_completed != self.winner_games + self.draws
            or self.rejected_batches > self.engine_errors
            or bool(self.engine_errors) != bool(self.rejected_batches)
            or self.accepted_commands != sum(r.accepted_commands for r in self.outcomes)
            or len(self.accepted_commands_by_phase) != 14
            or sum(self.accepted_commands_by_phase) != self.accepted_commands
            or any(self.accepted_commands_by_phase[i] for i in (0, 5, 8, 9, 10, 11, 12, 13))
            or self.forced_commands > self.accepted_commands
            or self.fingerprint_views != FINGERPRINT_VIEWS
            or self.hidden_targeting_fields != HIDDEN_TARGETING_FIELDS
            or len(h) != 4
            or self.hidden_trade_fields != HIDDEN_TRADE_FIELDS
            or len(t) != 9
            or self.ineffective_fields != INEFFECTIVE_FIELDS
            or len(self.ineffective_totals) != 14
            or len(self.ineffective_model_counts) != 237
            or self.hidden_removal_fields != HIDDEN_REMOVAL_FIELDS
            or len(self.hidden_removal_totals) != 7
            or self.hidden_cost_fields != HIDDEN_COST_FIELDS
            or len(self.hidden_cost_totals) != 9
        ):
            raise ValueError("episode probe ending, command or diagnostic layout differs")
        cost = self.hidden_cost_totals
        if (
            cost[3] != cost[4] + cost[5]
            or cost[6] != cost[7] + cost[8]
            or sum(cost[:3]) > cost[3]
            or sum(cost[:3]) > cost[8]
            or bool(sum(cost[:3])) != bool(cost[3])
            or bool(sum(cost[:3])) != bool(cost[6])
            or bool(sum(cost[:3])) != bool(cost[8])
            or (self.hidden_cost_policy == "strict-error" and any(cost))
        ):
            raise ValueError("episode probe hidden-cost conservation differs")
        if (
            h[0] != h[1] + h[2]
            or h[3] > h[2]
            or t[0] != sum(t[1:4])
            or t[4] != t[1]
            or t[5] + t[7] != t[2]
            or t[6] > t[2] + t[3] - t[7]
            or t[8] > t[0]
        ):
            raise ValueError("episode probe hidden-resolution conservation differs")
        i = self.ineffective_totals
        if (
            sum(self.ineffective_model_counts) != i[3] + i[4] + i[5]
            or i[6] + i[7] != sum(self.ineffective_model_counts)
            or i[0] + i[1] != i[9] + i[10]
            or i[3] != i[9]
            or i[13] > i[2]
        ):
            raise ValueError("episode probe ineffective-component conservation differs")
        removal = self.hidden_removal_totals
        if (
            removal[2] != removal[5] + removal[6]
            or removal[2] < removal[0] + removal[1]
            or removal[4] > removal[0] + removal[1]
        ):
            raise ValueError("episode probe hidden-removal conservation differs")
        if self.terminal_rewards_tracked:
            expected_totals = tuple(
                sum(
                    1 if seat in row.winning_players else -1
                    for row in self.outcomes
                    if row.status == "winner"
                )
                if seat < self.player_count
                else 0
                for seat in range(9)
            )
            reward_metadata = FullGameRewardMetadata(
                ruleset_id=self.ruleset_id, environment_metadata_sha256=self.metadata_sha256
            )
            expected_hash = hashlib.sha256(
                json.dumps(
                    reward_metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            if (
                type(self.reward_schema_version) is not int
                or self.reward_schema_version != 1
                or self.reward_metadata_sha256 != expected_hash
                or self.terminal_reward_totals != expected_totals
                or self.terminal_reward_valid_counts
                != tuple(
                    self.games_completed if seat < self.player_count else 0 for seat in range(9)
                )
            ):
                raise ValueError(
                    "episode probe terminal rewards disagree with true faction endings"
                )
        elif any(
            value is not None
            for value in (
                self.reward_schema_version,
                self.reward_metadata_sha256,
                self.terminal_reward_totals,
                self.terminal_reward_valid_counts,
            )
        ):
            raise ValueError("untracked terminal rewards must remain unknown, not invented zeros")
        return self


class BoundedPublicRandomPolicy:
    """Inputs are public decision rows/masks only, never true hands or diagnostics."""

    def __init__(self, batch_size: int, seed: int) -> None:
        import numpy as np

        self._rng = [
            np.random.default_rng(np.random.SeedSequence([seed, env])) for env in range(batch_size)
        ]
        self._context: dict[int, tuple[int, int, int, int]] = {}
        self._edits: dict[int, int] = {}

    def choose(
        self, environment: int, public_row: npt.NDArray[np.int64], legal_mask: npt.NDArray[np.bool_]
    ) -> int:
        import numpy as np

        key = (int(public_row[0]), int(public_row[2]), int(public_row[3]), int(public_row[4]))
        edits = self._edits.get(environment, 0) + 1 if self._context.get(environment) == key else 0
        self._context[environment] = key
        self._edits[environment] = edits
        phase = int(public_row[3])
        legal = np.flatnonzero(legal_mask)
        if not len(legal):
            raise RuntimeError("active full-game decision has no legal public choice")
        if phase == 1 and len(legal) > 1:
            legal = legal[legal != 0]
        if phase in (2, 4, 6, 7) and legal_mask[0] and edits >= 2:
            return 0
        return int(self._rng[environment].choice(legal))


def _state_digest(batch: FullGameBatch) -> bytes:
    digest = hashlib.sha256()
    for name in FINGERPRINT_VIEWS:
        digest.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())
    return digest.digest()


def run_full_game_episode_probe(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 64,
    player_count: int = 3,
    seed: int = 67,
    policy_seed: int = 901,
    max_turns: int = 256,
    max_decisions: int = 2048,
    apocalypse_after_turns: int = 64,
    teams: Sequence[int] | None = None,
    terminal_rewards: bool = False,
    hidden_cost_policy: HiddenCostPolicy = "fizzle-provisional",
) -> FullGameEpisodeProbeReport:
    import numpy as np

    for value, low, high in (
        (batch_size, 1, 4096),
        (player_count, 2, 9),
        (seed, 0, 2**64 - 1),
        (policy_seed, 0, 2**64 - 1),
        (max_turns, 1, 10000),
        (max_decisions, 1, 40000),
        (apocalypse_after_turns, 0, 10000),
    ):
        if type(value) is not int or not low <= value <= high:
            raise ValueError("episode probe configuration is outside its bounded contract")
    try:
        layout = tuple(teams) if teams is not None else (0,) * player_count
    except TypeError:
        raise ValueError("episode probe teams must be one ID per seat") from None
    if len(layout) != player_count or any(
        type(team) is not int or not 0 <= team <= 4 for team in layout
    ):
        raise ValueError("episode probe teams must be one ID in 0..4 per seat")
    if type(terminal_rewards) is not bool:
        raise ValueError("episode probe terminal reward tracking must be boolean")
    if hidden_cost_policy not in ("strict-error", "fizzle-provisional"):
        raise ValueError("episode probe hidden cost policy differs")
    c = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        teams=layout,
        hidden_cost_policy=hidden_cost_policy,
        seed=seed,
        capacity=18,
        acquisition_mode="all-held-weighted",
        max_turns=max_turns,
        max_decisions=max_decisions,
        apocalypse_after_turns=apocalypse_after_turns,
    )
    b = c.batch
    b.start_environments(np.arange(batch_size, dtype=np.int64))
    reward_adapter = FullGameRewardAdapter(c) if terminal_rewards else None
    reward_totals = np.zeros(9, dtype=np.int64)
    reward_counts = np.zeros(9, dtype=np.int64)

    def capture_rewards(batch: FullGameRewardBatch) -> None:
        reward_totals[:] += batch.values.sum(axis=0)
        reward_counts[:] += batch.valid.sum(axis=0)

    def execute(commands: npt.NDArray[np.int64]) -> None:
        if reward_adapter is None:
            b.step(commands)
        else:
            capture_rewards(reward_adapter.step(commands).rewards)

    policy = BoundedPublicRandomPolicy(batch_size, policy_seed)
    failures: dict[int, tuple[tuple[int, int, int, int, int, int], str]] = {}
    phase_counts = [0] * 14
    forced, rejected = 0, 0
    replay = hashlib.sha256(_state_digest(b))
    for _ in range(max_decisions):
        state, masks = b.episode_snapshot(), b.choice_masks()
        envs = [
            env
            for env in range(batch_size)
            if env not in failures and state[env, 3] not in (12, 13)
        ]
        if not envs:
            break
        rows = np.asarray(
            [[env, *state[env, :4], policy.choose(env, state[env], masks[env])] for env in envs],
            dtype=np.int64,
        )
        gradient_masks = b.policy_gradient_masks()
        before = _state_digest(b)
        accepted: list[int] = []
        try:
            execute(rows)
            accepted = envs
        except (ValueError, RuntimeError):
            if _state_digest(b) != before:
                raise RuntimeError(
                    "failed episode batch mutated authoritative diagnostic state"
                ) from None
            rejected += 1
            failed = False
            # Reuse the exact decisions, without resampling, retry policies or
            # skipping a bad turn. Independent healthy environments may proceed.
            for row in rows:
                env = int(row[0])
                row_before = _state_digest(b)
                try:
                    execute(row.reshape(1, 6))
                    accepted.append(env)
                except (ValueError, RuntimeError) as error:
                    if _state_digest(b) != row_before:
                        raise RuntimeError(
                            "failed episode row mutated authoritative diagnostic state"
                        ) from error
                    command = (
                        int(row[0]),
                        int(row[1]),
                        int(row[2]),
                        int(row[3]),
                        int(row[4]),
                        int(row[5]),
                    )
                    messages = str(error).splitlines()
                    reason = messages[0] if messages else type(error).__name__
                    failures[env] = (command, reason[:300])
                    failed = True
            if not failed:
                raise RuntimeError(
                    "episode batch failure did not reproduce in any environment"
                ) from None
        for env in accepted:
            phase_counts[int(state[env, 3])] += 1
            forced += int(not gradient_masks[env, 0])
        replay.update(rows.astype("<i8", copy=False).tobytes())
        replay.update(_state_digest(b))
    if reward_adapter is not None:
        capture_rewards(reward_adapter.poll())
    state = b.episode_snapshot()
    outcomes = []
    statuses: dict[int, Status] = {1: "winner", 2: "draw", 3: "turn-limit", 4: "decision-limit"}
    winning = b.winning_seats()
    for env, row in enumerate(state):
        if env not in failures and int(row[5]) not in statuses:
            raise RuntimeError("episode probe exhausted its bound without a native ending or error")
        error_command, error_reason = failures.get(env, (None, None))
        outcomes.append(
            FullGameEpisodeResult(
                environment=env,
                episode=int(row[0]),
                decision=int(row[1]),
                actor=int(row[2]),
                native_phase=int(row[3]),
                native_outcome=int(row[5]),
                winner=int(row[6]),
                winning_players=tuple(int(seat) for seat in np.flatnonzero(winning[env])),
                completed_turns=int(row[4]),
                accepted_commands=int(row[7]),
                status="engine-error" if env in failures else statuses[int(row[5])],
                error_command=error_command,
                error_reason=error_reason,
            )
        )
    counts = {status: sum(r.status == status for r in outcomes) for status in statuses.values()}
    return FullGameEpisodeProbeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                c.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        teams=layout,
        seed=seed,
        policy_seed=policy_seed,
        max_turns=max_turns,
        max_decisions=max_decisions,
        apocalypse_after_turns=apocalypse_after_turns,
        outcomes=tuple(outcomes),
        games_completed=counts["winner"] + counts["draw"],
        winner_games=counts["winner"],
        draws=counts["draw"],
        turn_limit_games=counts["turn-limit"],
        decision_limit_games=counts["decision-limit"],
        engine_errors=len(failures),
        rejected_batches=rejected,
        accepted_commands=b.action_count,
        forced_commands=forced,
        accepted_commands_by_phase=tuple(phase_counts),
        automatic_gifts=b.automatic_gift_count,
        hidden_cost_policy=hidden_cost_policy,
        hidden_cost_totals=tuple(int(v) for v in b.hidden_cost_snapshot().sum(axis=0)),
        terminal_rewards_tracked=terminal_rewards,
        reward_schema_version=1 if terminal_rewards else None,
        reward_metadata_sha256=hashlib.sha256(
            json.dumps(
                reward_adapter.metadata.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if reward_adapter is not None
        else None,
        terminal_reward_totals=tuple(int(value) for value in reward_totals)
        if terminal_rewards
        else None,
        terminal_reward_valid_counts=tuple(int(value) for value in reward_counts)
        if terminal_rewards
        else None,
        hidden_targeting_totals=tuple(int(x) for x in b.hidden_targeting_snapshot().sum(axis=0)),
        hidden_trade_totals=tuple(int(x) for x in b.hidden_trade_snapshot().sum(axis=0)),
        ineffective_totals=tuple(int(x) for x in b.ineffective_snapshot().sum(axis=0)),
        ineffective_model_counts=tuple(int(x) for x in b.ineffective_model_counts().sum(axis=0)),
        hidden_removal_totals=tuple(int(x) for x in b.hidden_removal_snapshot().sum(axis=0)),
    )
