"""Uniform Fate first-turn probe; incomplete guardian branches remain reported."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    FULL_GAME_RULESET_ID,
    PHENOMENON_SNAPSHOT_FIELDS,
    create_development_full_game_batch,
)
from godfield_bot.full_game_phenomena import PHENOMENON_SHA256

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGamePhenomenonSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[4] = 4
    source_kind: Literal["uniform-fate-firstturn-with-generated-events-v2"] = (
        "uniform-fate-firstturn-with-generated-events-v2"
    )
    ruleset_id: Literal["integrated-full-game-development-v31"] = FULL_GAME_RULESET_ID
    queue_schema_version: Literal[8] = 8
    scenario: Literal[
        "controlled-fate-hands-unforced-all10-models-forgiven-responses-not-full-games"
    ] = "controlled-fate-hands-unforced-all10-models-forgiven-responses-not-full-games"
    development_failure_policy: Literal[
        "atomic-batch-then-per-row-known-earth-moon-error-report-never-retry-failed-row"
    ] = "atomic-batch-then-per-row-known-earth-moon-error-report-never-retry-failed-row"
    profile_sha256: Literal["600b2314b68a4809797395afcaa2c711b0e8aa705bcd2bdf5f248ffd49645c55"] = (
        PHENOMENON_SHA256
    )
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    statistic_fields: tuple[str, ...] = PHENOMENON_SNAPSHOT_FIELDS
    statistic_totals: tuple[Count, ...]
    model_ids: tuple[int, ...] = tuple(range(287, 297))
    model_counts: tuple[Count, ...]
    observed_committed_models: int = Field(ge=0, le=10, strict=True)
    first_turns_completed: Count
    generated_fate_uses: Count
    development_failures: Count
    failed_environment_ids: tuple[Count, ...]
    commands: Count
    original_owner_ticks: Count
    incoming_hp_damage: Count
    active_families_in_completed_rows: Literal[0] = 0
    other_owner_ticks: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    full_games_completed: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGamePhenomenonSmokeReport:
        s, n = self.statistic_totals, self.model_counts
        if (
            len(s) != 23
            or len(n) != 10
            or self.statistic_fields != PHENOMENON_SNAPSHOT_FIELDS
            or self.model_ids != tuple(range(287, 297))
        ):
            raise ValueError("phenomenon smoke layout differs")
        if (
            self.first_turns_completed + self.development_failures != self.batch_size
            or self.development_failures != len(self.failed_environment_ids)
            or tuple(sorted(set(self.failed_environment_ids))) != self.failed_environment_ids
            or any(e >= self.batch_size for e in self.failed_environment_ids)
            or self.original_owner_ticks != self.first_turns_completed
            or self.observed_committed_models != sum(v > 0 for v in n)
            or s[0] != self.first_turns_completed + self.generated_fate_uses
            or s[1] != sum(n)
            or s[1] != s[0]
            or s[2] != sum(n[i] for i in (4, 5, 6, 7))
            or s[3] != n[4] + n[5]
            or s[4] + s[6] != s[3]
            or s[5] > n[5]
            or s[8] > n[0] * self.player_count
            or s[9] > n[1] * self.player_count
            or s[10] > n[2] * 3 * self.player_count
            or s[10] % 3 != 0
            or s[11] > n[3] * self.player_count
            or s[12] > n[3] * 99 * self.player_count
            or s[13] > n[6] * 50
            or s[14] > n[7] * 100 * self.player_count
            or s[15] > n[7] * 100
            or s[16] != s[14] - s[15]
            or s[17] != n[8]
            or s[18] > n[8] * 18 * self.player_count
            or s[19] != 0
            or s[20] != n[8]
            or s[21] > n[9] * self.player_count
            or s[22] != sum(n[i] for i in (0, 1, 2, 3, 6, 7, 8, 9))
            or s[7] > 50 * (s[4] - s[5])
            or self.incoming_hp_damage < s[7]
            or self.commands < self.batch_size + self.first_turns_completed
        ):
            raise ValueError("phenomenon smoke first-turn accounting differs")
        # Without generated Fate, the original controlled world remains an exact
        # independent oracle. Nested events can revisit changed wallets, hands,
        # health and living rosters; never pretend their effects use initial state.
        if not self.generated_fate_uses and (
            s[4] != s[3]
            or s[8] != n[0] * self.player_count
            or s[9] != n[1] * self.player_count
            or s[10] != n[2] * 3 * self.player_count
            or s[11] != n[3] * self.player_count
            or s[12] != n[3] * 49 * self.player_count
            or s[13] != n[6] * 50
            or s[14] != n[7] * 99 * self.player_count
            or s[15] != n[7] * 100
            or s[18] != n[8] * 3 * self.player_count
            or s[21] != n[9] * self.player_count
            or s[7] != 50 * (n[4] + n[5] - s[5])
        ):
            raise ValueError("phenomenon controlled initial-world accounting differs")
        return self


def run_full_game_phenomenon_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGamePhenomenonSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("phenomenon smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=128,
        initial_hp=50,
        initial_mp=20,
        initial_cp=99,
    )
    batch = configured.batch
    envs = np.arange(batch_size, dtype=np.int64)
    owners = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    batch.seed_players(
        np.repeat(envs, player_count),
        owners,
        np.tile([50, 20, 99, 0], (len(owners), 1)).astype(np.int64),
        np.full(len(owners), 8, dtype=np.int64),
    )
    for env in range(batch_size):
        for owner in range(player_count):
            rows = (
                [
                    [owner * 100 + 1, 207, 0, 0],
                    [owner * 100 + 2, 127, 142, 0],
                    [owner * 100 + 3, 238, 235, 1],
                    [owner * 100 + 4, 208, 0, 0],
                ]
                if owner == 0
                else [
                    [owner * 100 + 1, 127, 0, 0],
                    [owner * 100 + 2, 237, 0, 0],
                    [owner * 100 + 3, 208, 0, 0],
                ]
            )
            batch.seed_hand(env, owner, np.asarray(rows, dtype=np.int64))
    batch.start_environments(envs)
    failed = np.zeros(batch_size, dtype=np.bool_)
    replay = hashlib.sha256()
    view_names = (
        "episode_snapshot",
        "diagnostic_players",
        "diagnostic_inventory",
        "actor_hands",
        "player_observations",
        "choice_masks",
        "phenomenon_snapshot",
        "phenomenon_model_counts",
        "phenomenon_observations",
        "control_observations",
        "confusion_snapshot",
        "policy_gradient_masks",
        "attack_family_snapshot",
        "guardian_snapshot",
        "guardian_statistics",
        "guardian_generated_model_counts",
        "guardian_generated_execution_counts",
    )

    def fingerprint() -> None:
        for name in view_names:
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())
        replay.update(failed.astype("<i8", copy=False).tobytes())

    fingerprint()
    for _ in range(128):
        episodes = batch.episode_snapshot()
        active = np.flatnonzero(
            ~failed & (episodes[:, 3] < 12) & ((episodes[:, 4] == 0) | (episodes[:, 3] == 4))
        )
        if not len(active):
            break
        choices = np.where(episodes[active, 3] == 1, 1, 0).astype(np.int64)
        masks = batch.choice_masks()
        if not masks[active, choices].all():
            raise RuntimeError("phenomenon smoke public scripted choice unavailable")
        commands = np.column_stack((active, episodes[active, :4], choices))
        try:
            batch.step(commands)
        except ValueError as error:
            if str(error) != (
                "full-game Earth/Moon guardian producer requires generated action profiles"
            ):
                raise
            # Native batch validation is atomic. No guessed hidden-model filtering:
            # retry each unchanged public command once, retaining known failures.
            if not np.array_equal(episodes, batch.episode_snapshot()):
                raise RuntimeError("phenomenon development error leaked a partial batch") from None
            # Getter arrays are owned snapshots. Capture the unchanged batch
            # once: unrelated successful rows cannot mutate a failed row's
            # preimage. Avoid copying every B-row view for every successful retry.
            before = tuple(getattr(batch, name)() for name in view_names)
            for command in commands:
                env = int(command[0])
                try:
                    batch.step(command.reshape(1, 6))
                except ValueError as row_error:
                    if str(row_error) != (
                        "full-game Earth/Moon guardian producer requires generated action profiles"
                    ):
                        raise
                    for name, previous in zip(view_names, before, strict=True):
                        if not np.array_equal(previous[env], getattr(batch, name)()[env]):
                            raise RuntimeError(
                                "phenomenon error leaked world state or RNG diagnostics"
                            ) from None
                    failed[env] = True
        fingerprint()
    else:
        raise RuntimeError("phenomenon smoke first-turn decision bound exceeded")
    episodes = batch.episode_snapshot()
    players = batch.diagnostic_players()
    families = batch.attack_family_snapshot()
    if (
        np.any(episodes[~failed, 4] != 1)
        or np.any(episodes[:, 3] == 13)
        or families[~failed, 13:].any()
        or players[:, 1:, 5].any()
        or batch.automatic_gift_count
    ):
        raise RuntimeError("phenomenon smoke first-turn scheduler differs")
    counts = batch.phenomenon_model_counts().sum(axis=0)
    return FullGamePhenomenonSmokeReport(
        metadata_sha256=hashlib.sha256(configured.metadata.model_dump_json().encode()).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        statistic_totals=tuple(int(v) for v in batch.phenomenon_snapshot().sum(axis=0)),
        model_counts=tuple(int(v) for v in counts),
        observed_committed_models=int(np.count_nonzero(counts)),
        first_turns_completed=int(np.count_nonzero(~failed)),
        generated_fate_uses=int(batch.guardian_generated_execution_counts()[:, 207 - 3].sum()),
        development_failures=int(np.count_nonzero(failed)),
        failed_environment_ids=tuple(int(v) for v in np.flatnonzero(failed)),
        commands=batch.action_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        incoming_hp_damage=batch.hp_damage,
    )
