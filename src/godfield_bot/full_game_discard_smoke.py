"""Bounded multi-discard/cancel/Sun/Bow probe, not full-game learning evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    DISCARD_SNAPSHOT_FIELDS,
    FULL_GAME_RULESET_ID,
    create_development_full_game_batch,
)
from godfield_bot.full_game_discard import FULL_GAME_DISCARD_SHA256

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameDiscardSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[7] = 7
    source_kind: Literal["integrated-development-multi-discard-smoke-v1"] = (
        "integrated-development-multi-discard-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    scenario: Literal["ordinary-used-multi-periodic-sun-bow-cancel-scripted-not-full-games"] = (
        "ordinary-used-multi-periodic-sun-bow-cancel-scripted-not-full-games"
    )
    discard_profile_sha256: Literal[
        "2df3973944e31c672893fa041ba24e4cc31ed64a146efcf790dfe1e519332b80"
    ] = FULL_GAME_DISCARD_SHA256
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenario_counts: tuple[Count, ...]
    discard_fields: tuple[str, ...] = DISCARD_SNAPSHOT_FIELDS
    discard_totals: tuple[Count, ...]
    actions: Count
    discard_turns: Count
    discarded_cards: Count
    completed_turns: Count
    original_owner_ticks: Count
    other_owner_ticks: Literal[0] = 0
    consumed_cards: Count
    revivals: Count
    bows_consumed: Count
    bow_recipients: Count
    bow_hp_damage: Count
    family_enqueued: Count
    family_resolved: Count
    ready_after_one_turn: Count
    real_terminal_endings: Count
    automatic_gifts: Literal[0] = 0
    mp_spent: Literal[0] = 0
    miracle_uses: Literal[0] = 0
    original_attacks: Literal[0] = 0
    removal_attack_cards: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    apocalypse_and_sacrifice_exercised: Literal[False] = False
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def scripted_accounting(self) -> FullGameDiscardSmokeReport:
        n = tuple((self.batch_size + 5 - i) // 6 for i in range(6))
        recipients = n[4] * (self.player_count - 1)
        endings = n[4] if self.player_count == 2 else 0
        if (
            self.scenario_counts != n
            or self.discard_fields != DISCARD_SNAPSHOT_FIELDS
            or self.discard_totals
            != (
                self.batch_size + n[5],
                self.batch_size + 3 * (n[2] + n[5]),
                n[5],
                self.batch_size,
                self.batch_size + 3 * n[2],
                n[1] + n[2],
            )
            or self.actions != 3 * self.batch_size + 3 * n[2] + 5 * n[5] + recipients
            or self.discard_turns != self.batch_size
            or self.discarded_cards != self.batch_size + 3 * n[2]
            or self.completed_turns != self.batch_size
            or self.original_owner_ticks != self.batch_size
            or self.consumed_cards != n[3] + n[4]
            or self.revivals != n[3]
            or self.bows_consumed != n[4]
            or self.bow_recipients != recipients
            or self.bow_hp_damage != 30 * recipients
            or self.family_enqueued != recipients
            or self.family_resolved != recipients
            or self.ready_after_one_turn != self.batch_size - endings
            or self.real_terminal_endings != endings
        ):
            raise ValueError("discard smoke scripted accounting differs")
        return self


def run_full_game_discard_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 512,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameDiscardSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("discard smoke batch size must be 1 through 4096")
    configured = create_development_full_game_batch(
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=64,
        initial_hp=100,
        initial_mp=20,
    )
    batch = configured.batch
    environments = np.arange(batch_size, dtype=np.int64)
    scenarios = environments % 6
    for env, scenario in enumerate(scenarios):
        models = ([127], [237], [127, 191, 3, 232], [127, 208], [127, 112], [127, 191])[scenario]
        batch.seed_hand(
            env,
            0,
            np.asarray(
                [[i + 1, m, 0, int(m in (237, 232))] for i, m in enumerate(models)], dtype=np.int64
            ),
        )
        if scenario in (3, 4):
            batch.seed_players(
                np.asarray([env], dtype=np.int64),
                np.asarray([0], dtype=np.int64),
                np.asarray([[1, 20, 0, 1]], dtype=np.int64),
                np.asarray([0], dtype=np.int64),
            )
        for owner in range(1, player_count):
            batch.seed_players(
                np.asarray([env], dtype=np.int64),
                np.asarray([owner], dtype=np.int64),
                np.asarray([[100, 20, 0, 0]], dtype=np.int64),
                np.asarray([8], dtype=np.int64),
            )
    batch.start_environments(environments)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "actor_hands",
            "player_observations",
            "choice_masks",
            "discard_observations",
            "discard_order",
            "discard_snapshot",
            "attack_family_snapshot",
            "revival_snapshot",
            "acquisition_snapshot",
        ):
            replay.update(getattr(batch, name)().astype("<i8", copy=False).tobytes())

    def issue(envs: npt.NDArray[np.int64], choice: int) -> None:
        if not len(envs):
            return
        if not batch.choice_masks()[envs, choice].all():
            raise RuntimeError("discard smoke expected public choice is unavailable")
        batch.step(
            np.column_stack(
                (
                    envs,
                    batch.episode_snapshot()[envs, :4],
                    np.full(len(envs), choice, dtype=np.int64),
                )
            )
        )
        fingerprint()

    fingerprint()
    issue(environments, 19)
    cancelled = environments[scenarios == 5]
    for choice in (2, 2, 1, 19, 19):
        issue(cancelled, choice)
    issue(environments, 1)
    for choice in (2, 3, 4):
        issue(environments[scenarios == 2], choice)
    issue(environments, 0)
    for _ in range(player_count):
        responses = np.flatnonzero(batch.episode_snapshot()[:, 3] == 4)
        if not len(responses):
            break
        issue(responses, 0)
    else:
        raise RuntimeError("discard smoke exceeded bounded post-tick response loop")
    episodes, players, family = (
        batch.episode_snapshot(),
        batch.diagnostic_players(),
        batch.attack_family_snapshot(),
    )
    if (
        not np.isin(episodes[:, 3], (1, 12)).all()
        or family[:, 13:].any()
        or players[:, 1:, 5].any()
        or batch.automatic_gift_count
        or batch.mp_spent
        or batch.miracle_use_count
        or batch.attack_count
        or batch.removal_count
    ):
        raise RuntimeError("discard smoke produced an unexpected phase, receipt, cost, use or tick")
    return FullGameDiscardSmokeReport(
        metadata_sha256=hashlib.sha256(
            json.dumps(
                configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=tuple(int(np.count_nonzero(scenarios == i)) for i in range(6)),
        discard_totals=tuple(int(v) for v in batch.discard_snapshot().sum(axis=0)),
        actions=batch.action_count,
        discard_turns=batch.discard_count,
        discarded_cards=batch.discarded_card_count,
        completed_turns=int(episodes[:, 4].sum()),
        original_owner_ticks=int(players[:, 0, 5].sum()),
        consumed_cards=batch.consumed_count,
        revivals=batch.revival_count,
        bows_consumed=batch.ascension_count,
        bow_recipients=int(family[:, 8].sum()),
        bow_hp_damage=batch.ascension_hp_damage,
        family_enqueued=int(family[:, 0].sum()),
        family_resolved=int(family[:, 2].sum()),
        ready_after_one_turn=int(np.count_nonzero(episodes[:, 3] == 1)),
        real_terminal_endings=int(np.count_nonzero(episodes[:, 3] == 12)),
    )
