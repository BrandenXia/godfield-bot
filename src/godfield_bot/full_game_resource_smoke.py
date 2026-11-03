"""Near-ceiling resource paths at client99 or explicit legacy100, not training."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import (
    FULL_GAME_RULESET_ID,
    ResourceCap,
    create_development_full_game_batch,
)

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

Count = Annotated[int, Field(ge=0, strict=True)]
SCENARIOS = ("hp-utility", "mp-utility", "treasure", "heaven-herb", "exchange", "heaven-tick")


class FullGameResourceSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["integrated-full-game-development-v33"] = FULL_GAME_RULESET_ID
    source_kind: Literal["near-cap-utilities-exchange-heaven-probe-v1"] = (
        "near-cap-utilities-exchange-heaven-probe-v1"
    )
    resource_cap: ResourceCap
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    scenarios: tuple[str, ...] = SCENARIOS
    scenario_counts: tuple[Count, ...]
    final_resource_totals: tuple[tuple[Count, Count, Count], ...]
    sun_revivals_by_scenario: tuple[Count, ...]
    commands: Count
    original_owner_ticks: Count
    consumed_cards: Count
    utilities: Count
    miracle_uses: Count
    mp_spent: Count
    cp_credited: Count
    exchange_commits: Count
    exchange_hp_to_mp: Count
    revived_hp: Count
    resource_bound_violations: Literal[0] = 0
    pending_families: Literal[0] = 0
    other_owner_ticks: Literal[0] = 0
    limit_truncations: Literal[0] = 0
    real_terminal_endings: Literal[0] = 0
    automatic_gifts: Literal[0] = 0
    full_games_completed: Literal[0] = 0
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameResourceSmokeReport:
        n, r, cap = self.scenario_counts, self.sun_revivals_by_scenario, self.resource_cap
        if (
            self.scenarios != SCENARIOS
            or n != tuple((self.batch_size + 5 - i) // 6 for i in range(6))
            or len(r) != 6
            or any(r[i] > n[i] or (i not in (3, 5) and r[i]) for i in range(6))
        ):
            raise ValueError("resource smoke scenario or revival layout differs")
        delta = cap - 98
        expected = (
            (cap * n[0], 98 * n[0], 98 * n[0]),
            (98 * n[1], cap * n[1], 98 * n[1]),
            (98 * n[2], 93 * n[2], cap * n[2]),
            (cap * n[3] - (cap - 10) * r[3], cap * n[3], 98 * n[3]),
            ((98 - delta) * n[4], cap * n[4], 98 * n[4]),
            (cap * n[5] - (cap - 10) * r[5], 98 * n[5], 98 * n[5]),
        )
        if (
            self.final_resource_totals != expected
            or self.commands != 2 * self.batch_size + n[4] - n[5]
            or self.original_owner_ticks != self.batch_size
            or self.consumed_cards != n[0] + n[1] + n[3] + n[4] + sum(r)
            or self.utilities != sum(n[:4])
            or self.miracle_uses != n[2]
            or self.mp_spent != 5 * n[2]
            or self.cp_credited != delta * n[2]
            or self.exchange_commits != n[4]
            or self.exchange_hp_to_mp != delta * n[4]
            or self.revived_hp != 10 * sum(r)
        ):
            raise ValueError("resource smoke cap, payment, use or tick accounting differs")
        return self


def run_full_game_resource_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 4096,
    player_count: int = 3,
    seed: int = 67,
    resource_cap: ResourceCap = 99,
) -> FullGameResourceSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("resource smoke batch size must be 1 through 4096")
    c = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=18,
        seed=seed,
        max_turns=2,
        max_decisions=16,
        initial_hp=resource_cap,
        initial_mp=98,
        initial_cp=98,
        resource_cap=resource_cap,
    )
    b = c.batch
    envs = np.arange(batch_size, dtype=np.int64)
    scenario = envs % 6
    models = [
        next(r[0] for r in c.metadata.plan.effect_profiles if r[1] == kind and r[3] == cost)
        for kind, cost in ((1, 0), (2, 0), (5, 5), (6, 0))
    ]
    players = np.tile([98, 98, 98, 0], (batch_size, 1)).astype(np.int64)
    players[scenario == 5, 3] = 4
    b.seed_players(envs, np.zeros(batch_size, dtype=np.int64), players, envs * 0)
    for env, case in enumerate(scenario):
        cards = [models[case]] if case < 4 else ([3] if case == 4 else [])
        if case in (3, 5):
            cards.append(208)
        b.seed_hand(
            env,
            0,
            np.asarray([[i + 1, model, 0, 0] for i, model in enumerate(cards)], dtype=np.int64),
        )
    b.start_environments(envs)
    replay = hashlib.sha256()

    def fingerprint() -> None:
        resources = b.diagnostic_players()[:, :, :3]
        if (resources < 0).any() or (resources > resource_cap).any():
            raise RuntimeError("resource smoke observed an out-of-cap resource")
        for name in (
            "episode_snapshot",
            "diagnostic_players",
            "diagnostic_inventory",
            "choice_masks",
            "trade_observations",
            "trade_snapshot",
            "cp_utility_snapshot",
            "compound_utility_snapshot",
            "revival_snapshot",
            "attack_family_snapshot",
        ):
            replay.update(getattr(b, name)().astype("<i8", copy=False).tobytes())

    def move(selected: npt.NDArray[np.int64], choices: int | npt.NDArray[np.int64]) -> None:
        if not len(selected):
            return
        choices = np.broadcast_to(choices, selected.shape)
        if not b.choice_masks()[selected, choices].all():
            raise RuntimeError("resource smoke scripted public choice unavailable")
        b.step(np.column_stack((selected, b.episode_snapshot()[selected, :4], choices)))
        fingerprint()

    fingerprint()
    move(envs, (scenario != 5).astype(np.int64))
    selected = envs[scenario != 5]
    move(selected, (scenario[selected] == 4).astype(np.int64))
    move(envs[scenario == 4], 0)
    episodes, players, family = (
        b.episode_snapshot(),
        b.diagnostic_players(),
        b.attack_family_snapshot(),
    )
    trade = b.trade_snapshot().sum(axis=0)
    n = tuple(int((scenario == case).sum()) for case in range(6))
    r = tuple(int(b.revival_snapshot()[scenario == case, 0].sum()) for case in range(6))
    delta = resource_cap - 98
    if (
        not (episodes[:, 3] == 1).all()
        or not (episodes[:, 4] == 1).all()
        or not (episodes[:, 2] == 1).all()
        or players[:, 1:, 5].any()
        or family.any()
        or b.automatic_gift_count
        or b.attack_count
        or tuple(int(x) for x in trade) != (n[4], n[4], 0, n[4], delta * n[4], 0, 0, 0, 0, 0)
    ):
        raise RuntimeError("resource smoke left extra turns, families, gifts or trades")
    # Per-row oracle prevents compensating errors from passing aggregate checks.
    for env, case in enumerate(scenario):
        expected = [98, 98, 98]
        if case in (0, 3, 5):
            expected[0] = 10 if b.revival_snapshot()[env, 0] else resource_cap
        if case in (1, 3, 4):
            expected[1] = resource_cap
        if case == 2:
            expected[1:] = [93, resource_cap]
        if case == 4:
            expected[0] -= delta
        if players[env, 0, :3].tolist() != expected:
            raise RuntimeError("resource smoke per-row resource accounting differs")

    def totals(case: int) -> tuple[int, int, int]:
        values = players[scenario == case, 0, :3].sum(axis=0)
        return int(values[0]), int(values[1]), int(values[2])

    return FullGameResourceSmokeReport(
        resource_cap=resource_cap,
        metadata_sha256=hashlib.sha256(
            json.dumps(
                c.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        diagnostic_replay_sha256=replay.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        scenario_counts=n,
        final_resource_totals=tuple(totals(case) for case in range(6)),
        sun_revivals_by_scenario=r,
        commands=b.action_count,
        original_owner_ticks=int(players[:, 0, 5].sum()),
        consumed_cards=b.consumed_count,
        utilities=b.utility_count,
        miracle_uses=b.miracle_use_count,
        mp_spent=b.mp_spent,
        cp_credited=b.utility_cp_gain,
        exchange_commits=int(trade[3]),
        exchange_hp_to_mp=int(trade[4]),
        revived_hp=b.revived_hp,
    )
