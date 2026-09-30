"""Bounded, hidden-hand-safe episodes for the separate provisional C++ arena.

This is not the live feature schema or an official full-game environment.
The native arena remains authoritative for legality, resources and combat.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_batch import GuardianTurnMetadata, create_provisional_guardian_turn_batch
from godfield_bot.guardian_refill import GuardianRefillPlan, build_guardian_refill_plan
from godfield_bot.guardian_utility import (
    GuardianUtilityTurnMetadata,
    create_provisional_guardian_utility_turn_batch,
)
from godfield_bot.guardian_utility_refill import (
    GuardianUtilityRefillPlan,
    build_guardian_utility_refill_plan,
)
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

HAND_SLOTS = 18
MAX_PLAYERS = 9
ACTION_COUNT = 30
TARGET_START = 19
FORGIVE = 28
CONFIRM = 29
GLOBAL_FEATURE_COUNT = 43
PLAYER_FEATURE_COUNT = 8
HAND_FEATURE_COUNT = 7
UTILITY_HAND_FEATURE_COUNT = 9
UTILITY_OBSERVATION_ID = "actor-relative-guardian-utility-arena-v2"
TARGET_PHASE = 5
IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]


def _readonly[ScalarT: np.generic](array: npt.NDArray[ScalarT]) -> npt.NDArray[ScalarT]:
    array.flags.writeable = False
    return array


class GuardianRolloutConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    batch_size: int = Field(default=64, ge=1, le=4096, strict=True)
    player_count: int = Field(default=2, ge=2, le=9, strict=True)
    seed: int = Field(default=67, ge=0, le=2**32 - 1, strict=True)
    max_turns: int = Field(default=64, ge=1, le=100_000, strict=True)
    max_decisions: int = Field(default=1024, ge=1, le=100_000, strict=True)
    initial_hp: int = Field(default=40, ge=1, le=100, strict=True)
    initial_mp: int = Field(default=10, ge=0, le=100, strict=True)
    opening: Literal["cards-only", "mars-opening", "mixed"] = "mixed"
    inventory_utilities: bool = Field(default=False, strict=True)
    refill: Literal["none", "weighted-consumption-v1", "weighted-utility-consumption-v1"] = "none"
    gamma: float = Field(default=0.99, gt=0, le=1, allow_inf_nan=False)
    shaping_weight: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def separate_utility_refill(self) -> GuardianRolloutConfig:
        if (self.inventory_utilities and self.refill == "weighted-consumption-v1") or (
            not self.inventory_utilities and self.refill == "weighted-utility-consumption-v1"
        ):
            raise ValueError("utility and old refill curricula must be selected separately")
        return self


class GuardianRolloutMetadata(BaseModel):
    schema_version: Literal[1, 2] = 1
    source_kind: Literal[
        "provisional-guardian-arena-rollout-v1",
        "provisional-guardian-refill-arena-rollout-v1",
        "provisional-guardian-utility-arena-rollout-v2",
        "provisional-guardian-utility-refill-arena-rollout-v2",
    ] = "provisional-guardian-arena-rollout-v1"
    curriculum_id: Literal[
        "synthetic-guardian-no-redraw-v1",
        "synthetic-guardian-weighted-refill-provisional-v1",
        "synthetic-guardian-utility-no-redraw-v2",
        "synthetic-guardian-utility-weighted-refill-provisional-v2",
    ] = "synthetic-guardian-no-redraw-v1"
    observation_schema_id: Literal[
        "actor-relative-guardian-arena-v1", "actor-relative-guardian-utility-arena-v2"
    ] = "actor-relative-guardian-arena-v1"
    actor_hand_schema_version: Literal[1] = 1
    native: GuardianTurnMetadata | GuardianUtilityTurnMetadata
    config: GuardianRolloutConfig
    hand_slots: Literal[18] = 18
    max_players: Literal[9] = 9
    action_count: Literal[30] = 30
    global_feature_count: Literal[43] = 43
    player_feature_count: Literal[8] = 8
    hand_feature_count: Literal[7, 9] = 7
    initial_cards_per_player: Literal[9] = 9
    acquisition_policy: Literal[
        "synthetic-balanced-initial-deal-no-redraw",
        "synthetic-balanced-deal-deferred-weighted-refill",
        "synthetic-balanced-utility-initial-deal-no-redraw",
        "synthetic-balanced-utility-deal-deferred-weighted-refill",
    ] = "synthetic-balanced-initial-deal-no-redraw"
    refill_plan: GuardianRefillPlan | GuardianUtilityRefillPlan | None = None
    guardian_policy: Literal["optional-one-mars-effect-at-episode-opening"] = (
        "optional-one-mars-effect-at-episode-opening"
    )
    reward_policy: Literal["zero-sum-hp-mp-potential-and-terminal-winner-v1"] = (
        "zero-sum-hp-mp-potential-and-terminal-winner-v1"
    )
    truncation_policy: Literal["bounded-episode-absorbing-zero-bootstrap"] = (
        "bounded-episode-absorbing-zero-bootstrap"
    )
    global_fields: tuple[str, ...] = (
        "phase[6]",
        "turn_owner_is_self",
        "turn_fraction",
        "defense_toggle_fraction",
        "selected_defense",
        "selected_mp_cost",
        "attack_origin[3]",
        "bounced",
        "pending_attack",
        "pending_element[7]",
        "pending_effect[-1..10]",
        "pending_utility",
        "pending_curse_bits[4]",
        "pending_owner_is_self",
        "pending_target_is_self",
        "decision_fraction",
    )
    player_fields: tuple[str, ...] = (
        "hp",
        "mp",
        "cp",
        "alive",
        "fog",
        "dream",
        "flash",
        "darkcloud",
    )
    hand_fields: tuple[str, ...] = (
        "role/5",
        "attack/100",
        "defense/100",
        "element/6",
        "mp_cost/100",
        "reusable",
        "selected",
    )
    action_layout: tuple[str, ...] = (
        "0:pass",
        "1..18:hand-slot",
        "19..27:actor-relative-target",
        "28:forgive",
        "29:confirm",
    )
    local_rollout_ready: Literal[True] = True
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False

    @model_validator(mode="after")
    def separate_acquisition_contract(self) -> GuardianRolloutMetadata:
        if self.config.inventory_utilities:
            if (
                self.schema_version != 2
                or not isinstance(self.native, GuardianUtilityTurnMetadata)
                or self.observation_schema_id != UTILITY_OBSERVATION_ID
                or self.hand_feature_count != UTILITY_HAND_FEATURE_COUNT
                or self.hand_fields
                != (
                    "role/7",
                    "attack/100",
                    "defense/100",
                    "element/6",
                    "mp_cost/100",
                    "reusable",
                    "selected",
                    "hp_gain/100",
                    "mp_gain/100",
                )
            ):
                raise ValueError(
                    "utility arena requires the separate native and nine-feature observation"
                )
            weighted = self.config.refill != "none"
            if weighted:
                if (
                    self.source_kind != "provisional-guardian-utility-refill-arena-rollout-v2"
                    or self.curriculum_id
                    != "synthetic-guardian-utility-weighted-refill-provisional-v2"
                    or self.acquisition_policy
                    != "synthetic-balanced-utility-deal-deferred-weighted-refill"
                    or not isinstance(self.refill_plan, GuardianUtilityRefillPlan)
                ):
                    raise ValueError(
                        "utility refill requires an explicit 102-card curriculum and plan"
                    )
                supported = (
                    self.native.defense_model_ids
                    + self.native.attack_weapon_model_ids
                    + self.native.attack_miracle_model_ids
                    + tuple(row[0] for row in self.native.utility_plan.profiles)
                )
                if tuple(sorted(supported)) != tuple(
                    model for model, _ in self.refill_plan.model_weights
                ):
                    raise ValueError("utility refill and native supported models differ")
            elif (
                self.source_kind != "provisional-guardian-utility-arena-rollout-v2"
                or self.curriculum_id != "synthetic-guardian-utility-no-redraw-v2"
                or self.acquisition_policy != "synthetic-balanced-utility-initial-deal-no-redraw"
                or self.refill_plan is not None
            ):
                raise ValueError("utility no-redraw curriculum cannot declare replacement gifts")
            return self
        if (
            self.schema_version != 1
            or not isinstance(self.native, GuardianTurnMetadata)
            or self.observation_schema_id != "actor-relative-guardian-arena-v1"
            or self.hand_feature_count != HAND_FEATURE_COUNT
        ):
            raise ValueError("old arena requires its original native and seven-feature observation")
        weighted = self.config.refill != "none"
        if weighted:
            if (
                self.source_kind != "provisional-guardian-refill-arena-rollout-v1"
                or self.curriculum_id != "synthetic-guardian-weighted-refill-provisional-v1"
                or self.acquisition_policy != "synthetic-balanced-deal-deferred-weighted-refill"
                or not isinstance(self.refill_plan, GuardianRefillPlan)
            ):
                raise ValueError(
                    "weighted refill requires an explicit separate curriculum and plan"
                )
            supported = (
                self.native.defense_model_ids
                + self.native.attack_weapon_model_ids
                + self.native.attack_miracle_model_ids
            )
            if (
                tuple(sorted(supported))
                != tuple(model for model, _ in self.refill_plan.model_weights)
                or self.native.catalog_sha256 != self.refill_plan.catalog_sha256
                or self.native.bible_client_sha256 != self.refill_plan.bible_client_sha256
            ):
                raise ValueError("refill profile and native supported sources differ")
        elif (
            self.source_kind != "provisional-guardian-arena-rollout-v1"
            or self.curriculum_id != "synthetic-guardian-no-redraw-v1"
            or self.acquisition_policy != "synthetic-balanced-initial-deal-no-redraw"
            or self.refill_plan is not None
        ):
            raise ValueError("no-redraw curriculum cannot declare replacement gifts")
        return self


@dataclass(frozen=True)
class GuardianObservation:
    global_features: FloatArray
    players: FloatArray
    player_mask: BoolArray
    hand_model_ids: IntArray
    hand_features: FloatArray
    hand_mask: BoolArray
    action_mask: BoolArray
    actors: IntArray
    phases: IntArray
    episode_ids: IntArray
    decisions: IntArray
    active: BoolArray


@dataclass(frozen=True)
class GuardianTransition:
    observation: GuardianObservation
    actors: IntArray
    rewards: FloatArray  # absolute seat order; observation players are actor-relative
    terminated: BoolArray
    truncated: BoolArray
    newly_finished: BoolArray
    winners: IntArray

    @property
    def acting_rewards(self) -> FloatArray:
        result = np.zeros(len(self.actors), dtype=np.float32)
        rows = np.flatnonzero(self.actors >= 0)
        result[rows] = self.rewards[rows, self.actors[rows]]
        return _readonly(result)


class GuardianUtilityStatistics(BaseModel):
    """Lifetime/window diagnostics for both seats, never additional policy inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    uses: int = Field(ge=0, strict=True)
    consumed_items: int = Field(ge=0, strict=True)
    miracle_casts: int = Field(ge=0, strict=True)
    mp_spent: int = Field(ge=0, strict=True)
    hp_gained: int = Field(ge=0, strict=True)
    mp_gained: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def accounted(self) -> GuardianUtilityStatistics:
        if (
            self.consumed_items + self.miracle_casts != self.uses
            or self.mp_spent != 7 * self.miracle_casts
            or self.hp_gained > 100 * self.uses
            or self.mp_gained > 100 * self.consumed_items
        ):
            raise ValueError("utility statistics do not account for the pinned card uses")
        return self

    def since(self, previous: GuardianUtilityStatistics) -> GuardianUtilityStatistics:
        return GuardianUtilityStatistics(
            **{
                field: getattr(self, field) - getattr(previous, field)
                for field in type(self).model_fields
            }
        )


class GuardianRolloutArena:
    """Explicit-reset episodes; no automatic reset hides terminal observations.

    Select an attack card then an actor-relative target. Card/MP consumption
    happens only when the target is committed. Completed rows require -1 in
    step() while other rows continue. reset_done() starts fresh independent RNG
    streams, keyed by seed, environment index and episode number.
    """

    def __init__(self, *, catalog_path: Path, bible_path: Path, config: GuardianRolloutConfig):
        import godfield_sim as native

        if getattr(native, "GUARDIAN_ACTOR_HAND_SCHEMA_VERSION", None) != 1:
            raise ProvisionalRuleUnavailableError("guardian actor hand projection identity differs")
        created = (
            create_provisional_guardian_utility_turn_batch
            if config.inventory_utilities
            else create_provisional_guardian_turn_batch
        )(
            catalog_path=catalog_path,
            bible_path=bible_path,
            batch_size=config.batch_size,
            player_count=config.player_count,
            slots_per_environment=1,
            hand_slots=HAND_SLOTS,
            max_turns=config.max_turns,
            initial_hp=config.initial_hp,
            initial_mp=config.initial_mp,
        )
        self.config = config
        if config.inventory_utilities:
            meta = created.metadata
            assert isinstance(meta, GuardianUtilityTurnMetadata)
            utility_refill = None
            if config.refill != "none":
                utility_refill = build_guardian_utility_refill_plan(
                    read_api_catalog_snapshot(catalog_path),
                    BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
                    meta.defense_model_ids
                    + meta.attack_weapon_model_ids
                    + meta.attack_miracle_model_ids
                    + tuple(row[0] for row in meta.utility_plan.profiles),
                )
            self.metadata = GuardianRolloutMetadata(
                schema_version=2,
                native=meta,
                config=config,
                observation_schema_id="actor-relative-guardian-utility-arena-v2",
                hand_feature_count=9,
                hand_fields=(
                    "role/7",
                    "attack/100",
                    "defense/100",
                    "element/6",
                    "mp_cost/100",
                    "reusable",
                    "selected",
                    "hp_gain/100",
                    "mp_gain/100",
                ),
                source_kind="provisional-guardian-utility-refill-arena-rollout-v2"
                if utility_refill is not None
                else "provisional-guardian-utility-arena-rollout-v2",
                curriculum_id="synthetic-guardian-utility-weighted-refill-provisional-v2"
                if utility_refill is not None
                else "synthetic-guardian-utility-no-redraw-v2",
                acquisition_policy="synthetic-balanced-utility-deal-deferred-weighted-refill"
                if utility_refill is not None
                else "synthetic-balanced-utility-initial-deal-no-redraw",
                refill_plan=utility_refill,
            )
        elif config.refill == "none":
            self.metadata = GuardianRolloutMetadata(native=created.metadata, config=config)
        else:
            meta = created.metadata
            assert isinstance(meta, GuardianTurnMetadata)
            plan = build_guardian_refill_plan(
                read_api_catalog_snapshot(catalog_path),
                BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
                meta.defense_model_ids
                + meta.attack_weapon_model_ids
                + meta.attack_miracle_model_ids,
            )
            self.metadata = GuardianRolloutMetadata(
                native=meta,
                config=config,
                source_kind="provisional-guardian-refill-arena-rollout-v1",
                curriculum_id="synthetic-guardian-weighted-refill-provisional-v1",
                acquisition_policy="synthetic-balanced-deal-deferred-weighted-refill",
                refill_plan=plan,
            )
        self._native = created.batch
        self._utility_native = (
            self._native
            if config.inventory_utilities
            and isinstance(self._native, native.GuardianUtilityTurnBatch)
            else None
        )
        self._utility_consumed = self._utility_casts = self._utility_mp_spent = 0
        self._episode_ids = np.full(config.batch_size, -1, dtype=np.int64)
        self._decisions = np.zeros(config.batch_size, dtype=np.int64)
        self._selected_slots = np.full(config.batch_size, -1, dtype=np.int64)
        self._budget_truncated = np.zeros(config.batch_size, dtype=np.bool_)
        self._pending_refills: list[set[tuple[int, int]]] = [
            set() for _ in range(config.batch_size)
        ]
        self._refill_rngs: dict[int, np.random.Generator] = {}
        self._next_instances = np.full(
            config.batch_size, config.player_count * 9 + 1, dtype=np.int64
        )
        self._replacement_gifts = 0
        self._refill_models = np.asarray(
            [model for model, _ in self.metadata.refill_plan.model_weights]
            if self.metadata.refill_plan is not None
            else [],
            dtype=np.int64,
        )
        self._refill_cumulative = np.cumsum(
            [weight for _, weight in self.metadata.refill_plan.model_weights]
            if self.metadata.refill_plan is not None
            else [],
            dtype=np.int64,
        )
        self._reset(np.arange(config.batch_size, dtype=np.int64))

    @property
    def replacement_gifts(self) -> int:
        """Lifetime diagnostic counter, not a policy feature or shaping reward."""
        return self._replacement_gifts

    @property
    def utility_statistics(self) -> GuardianUtilityStatistics | None:
        if self._utility_native is None:
            return None
        return GuardianUtilityStatistics(
            uses=self._utility_native.utility_use_count,
            consumed_items=self._utility_consumed,
            miracle_casts=self._utility_casts,
            mp_spent=self._utility_mp_spent,
            hp_gained=self._utility_native.hp_gained,
            mp_gained=self._utility_native.mp_gained,
        )

    def _reset(self, rows: IntArray) -> None:
        if len(rows) == 0:
            return
        config, meta = self.config, self.metadata.native
        all_models = (
            meta.defense_model_ids + meta.attack_weapon_model_ids + meta.attack_miracle_model_ids
        )
        utilities = (
            meta.utility_plan.profiles if isinstance(meta, GuardianUtilityTurnMetadata) else ()
        )
        all_models += tuple(row[0] for row in utilities)
        hands = np.empty((len(rows), config.player_count, 9), dtype=np.int64)
        mars_rows, selections, hits, targets = [], [], [], []
        for offset, env in enumerate(rows):
            episode = int(self._episode_ids[env]) + 1
            rng = np.random.default_rng(np.random.SeedSequence([config.seed, int(env), episode]))
            for player in range(config.player_count):
                cards = [
                    int(rng.choice(meta.attack_weapon_model_ids)),
                    int(rng.choice(meta.attack_miracle_model_ids)),
                    int(rng.choice(meta.armor_model_ids)),
                    int(rng.choice(meta.defense_miracle_model_ids)),
                ]
                if utilities:
                    # Explicit balanced utility opening, not an official gift distribution.
                    cards += [
                        int(rng.choice([r[0] for r in utilities if r[1] == 0 and r[3] == 0])),
                        int(rng.choice([r[0] for r in utilities if r[1] == 1])),
                        235,
                    ]
                    cards += [int(model) for model in rng.choice(all_models, size=2)]
                else:
                    cards += [int(model) for model in rng.choice(all_models, size=5)]
                rng.shuffle(cards)
                hands[offset, player] = cards
            if config.opening == "mars-opening" or (
                config.opening == "mixed" and (int(env) + episode) % 2 == 0
            ):
                mars_rows.append(int(env))
                selections.append(int(rng.integers(20)))
                hits.append(int(rng.integers(100)))
                targets.append(int(rng.integers(1, config.player_count)))
        self._native.reset_environments(rows)
        count = len(rows) * config.player_count * 9
        self._native.deal_cards(
            np.repeat(rows, config.player_count * 9),
            np.tile(np.repeat(np.arange(config.player_count, dtype=np.int64), 9), len(rows)),
            np.tile(np.arange(9, dtype=np.int64), len(rows) * config.player_count),
            np.tile(np.arange(1, config.player_count * 9 + 1, dtype=np.int64), len(rows)),
            hands.reshape(count),
        )
        if mars_rows:
            envs = np.asarray(mars_rows, dtype=np.int64)
            zeros, ones = np.zeros(len(envs), dtype=np.int64), np.ones(len(envs), dtype=np.int64)
            self._native.summon(envs, zeros, ones, zeros, zeros)
            self._native.begin_effects(
                envs,
                zeros,
                ones,
                np.asarray(targets, dtype=np.int64),
                np.asarray(selections, dtype=np.int64),
                np.asarray(hits, dtype=np.int64),
            )
        self._episode_ids[rows] += 1
        self._decisions[rows] = 0
        self._selected_slots[rows] = -1
        self._budget_truncated[rows] = False
        for env in rows:
            self._pending_refills[env].clear()
            self._next_instances[env] = config.player_count * 9 + 1
            if config.refill != "none":
                self._refill_rngs[int(env)] = np.random.default_rng(
                    np.random.SeedSequence(
                        [
                            config.seed,
                            int(env),
                            int(self._episode_ids[env]),
                            6772 if config.inventory_utilities else 6771,
                        ]
                    )
                )

    def _apply_refills(self, turn: IntArray, finished: BoolArray) -> None:
        """Defer gifts across defense/bounce; never deal into pending or finished rows."""
        if self.metadata.refill_plan is None:
            return
        resources = self._native.resource_snapshot()
        deals: list[tuple[int, int, int, int, int]] = []
        for env, pending in enumerate(self._pending_refills):
            if finished[env]:
                pending.clear()
            elif turn[env, 0] == 0 and self._selected_slots[env] < 0:
                for owner, slot in sorted(pending):
                    if resources[env, owner, 0] <= 0:
                        continue
                    ticket = self._refill_rngs[env].integers(int(self._refill_cumulative[-1]))
                    model = self._refill_models[
                        np.searchsorted(self._refill_cumulative, ticket, side="right")
                    ]
                    deals.append((env, owner, slot, int(self._next_instances[env]), int(model)))
                    self._next_instances[env] += 1
                pending.clear()
        if deals:
            columns = np.asarray(deals, dtype=np.int64).T
            self._native.deal_cards(*(np.ascontiguousarray(column) for column in columns))
            self._replacement_gifts += len(deals)

    def reset_done(self) -> GuardianObservation:
        turn = self._native.turn_snapshot()
        self._reset(np.flatnonzero((turn[:, 0] == 2) | (turn[:, 0] == 3) | self._budget_truncated))
        return self.observe()

    def finish_reasons(self) -> tuple[str, ...]:
        """Public episode diagnostics, separate from policy features and rewards."""
        turn = self._native.turn_snapshot()
        reasons = []
        for env in range(self.config.batch_size):
            if turn[env, 0] == 2:
                reason = "winner"
            elif turn[env, 0] == 3 and turn[env, 7] >= self.metadata.native.max_defense_actions:
                reason = "defense_selection_limit"
            elif turn[env, 0] == 3:
                reason = "turn_limit"
            elif self._budget_truncated[env]:
                reason = "decision_limit"
            else:
                reason = "active"
            reasons.append(reason)
        return tuple(reasons)

    def observe(self) -> GuardianObservation:
        size, players = self.config.batch_size, self.config.player_count
        turn = self._native.turn_snapshot()
        combat = self._native.combat_snapshot()
        resources = self._native.resource_snapshot()
        hand = self._native.actor_hand_snapshot()
        active = (turn[:, 0] != 2) & (turn[:, 0] != 3) & ~self._budget_truncated
        actors = np.where(active, turn[:, 2], -1)
        phases = turn[:, 0].copy()
        targeting = active & (self._selected_slots >= 0)
        phases[targeting] = TARGET_PHASE
        relative_seats = (np.maximum(actors, 0)[:, None] + np.arange(players)) % players
        public = resources[np.arange(size)[:, None], relative_seats]
        player_features = np.zeros((size, MAX_PLAYERS, PLAYER_FEATURE_COUNT), dtype=np.float32)
        player_features[:, :players, :3] = public[:, :, :3] / 100
        player_features[:, :players, 3] = public[:, :, 0] > 0
        player_features[:, :players, 4:] = (public[:, :, 3, None] & (1 << np.arange(4))) != 0
        player_mask = np.zeros((size, MAX_PLAYERS), dtype=np.bool_)
        player_mask[:, :players] = active[:, None]
        hand_models = hand[:, :, 1].copy()
        hand_mask = (hand[:, :, 0] != 0) & active[:, None]
        hand_features = np.concatenate(
            (hand[:, :, 3:9], hand[:, :, 2, None], hand[:, :, 9:]), axis=2
        ).astype(np.float32)
        scales = (
            [7, 100, 100, 6, 100, 1, 1, 100, 100]
            if self.config.inventory_utilities
            else [5, 100, 100, 6, 100, 1, 1]
        )
        hand_features /= np.asarray(scales, dtype=np.float32)
        target_rows = np.flatnonzero(targeting)
        hand_features[target_rows, self._selected_slots[target_rows], 6] = 1
        mask = np.zeros((size, ACTION_COUNT), dtype=np.bool_)
        ready = active & (phases == 0)
        attack_mask = (
            self._utility_native.ready_action_masks()
            if self._utility_native is not None
            else self._native.attack_action_masks()
        )
        mask[ready, 0] = attack_mask[ready, HAND_SLOTS]
        mask[ready, 1:TARGET_START] = attack_mask[ready, :HAND_SLOTS]
        defense = active & (phases == 1)
        defense_mask = self._native.defense_action_masks()
        mask[defense, 1:TARGET_START] = defense_mask[defense, :HAND_SLOTS]
        mask[defense, FORGIVE:] = defense_mask[defense, HAND_SLOTS:]
        for phase, native_targets in (
            (TARGET_PHASE, self._native.attack_target_masks()),
            (4, self._native.bounce_target_masks()),
        ):
            rows = np.flatnonzero(active & (phases == phase))
            mask[rows, TARGET_START : TARGET_START + players] = native_targets[
                rows[:, None], relative_seats[rows]
            ]
        globals_ = np.zeros((size, GLOBAL_FEATURE_COUNT), dtype=np.float32)
        globals_[np.arange(size), phases] = 1
        globals_[:, 6] = turn[:, 1] == actors
        globals_[:, 7] = turn[:, 3] / self.config.max_turns
        globals_[:, 8] = turn[:, 7] / 64
        globals_[:, 9:11] = turn[:, [6, 8]] / 100
        pending = active & ((phases == 1) | (phases == 4))
        rows = np.flatnonzero(pending)
        globals_[rows, 11 + turn[rows, 9]] = 1
        globals_[:, 14] = turn[:, 10]
        globals_[rows, 15] = combat[rows, 4] / 100
        globals_[rows, 16 + combat[rows, 5]] = 1
        globals_[rows, 23 + combat[rows, 7] + 1] = 1
        globals_[rows, 35] = combat[rows, 8] / 100
        globals_[rows, 36:40] = (combat[rows, 9, None] & (1 << np.arange(4))) != 0
        globals_[rows, 40] = combat[rows, 2] == actors[rows]
        globals_[rows, 41] = combat[rows, 3] == actors[rows]
        # Remaining-decision fraction exposes the adapter's additional absorbing boundary.
        globals_[:, 42] = self._decisions / self.config.max_decisions
        globals_[~active] = 0
        player_features[~active] = 0
        hand_features[~active] = 0
        hand_models[~active] = 0
        return GuardianObservation(
            *map(
                _readonly,
                (
                    globals_,
                    player_features,
                    player_mask,
                    hand_models,
                    hand_features,
                    hand_mask,
                    mask,
                    actors,
                    phases,
                    self._episode_ids.copy(),
                    self._decisions.copy(),
                    active,
                ),
            )
        )

    def _potential(self) -> npt.NDArray[np.float64]:
        resources = self._native.resource_snapshot()
        utility = (resources[:, :, 0] + 0.05 * resources[:, :, 1]) / 100
        return utility - (utility.sum(axis=1, keepdims=True) - utility) / (
            self.config.player_count - 1
        )

    def step(self, actions: IntArray) -> GuardianTransition:
        if (
            not isinstance(actions, np.ndarray)
            or actions.dtype != np.int64
            or not actions.flags.c_contiguous
            or actions.shape != (self.config.batch_size,)
        ):
            raise ValueError("actions must be a contiguous int64 vector with batch_size entries")
        before = self.observe()
        rows = np.flatnonzero(before.active)
        if np.any(actions[~before.active] != -1):
            raise ValueError("finished environments require action -1 and explicit reset_done")
        chosen = actions[rows]
        if np.any((chosen < 0) | (chosen >= ACTION_COUNT)) or not np.all(
            before.action_mask[rows, chosen]
        ):
            raise ValueError("illegal arena action; batch was not changed")
        potential = self._potential()
        ready_pass = rows[(before.phases[rows] == 0) & (chosen == 0)]
        select = rows[(before.phases[rows] == 0) & (chosen != 0)]
        utility = np.empty(0, dtype=np.int64)
        if self._utility_native is not None:
            utility_masks = self._utility_native.utility_action_masks()
            is_utility = utility_masks[select, actions[select] - 1]
            utility, select = select[is_utility], select[~is_utility]
        attack = rows[before.phases[rows] == TARGET_PHASE]
        defend = rows[before.phases[rows] == 1]
        bounce = rows[before.phases[rows] == 4]
        # All rows are validated above before any grouped native operation mutates state.
        if len(ready_pass):
            self._native.pass_turns(ready_pass, before.actors[ready_pass])
        if len(utility):
            assert self._utility_native is not None
            self._utility_native.use_utility_cards(
                utility, before.actors[utility], actions[utility] - 1
            )
            for env in utility:
                slot = int(actions[env]) - 1
                reusable = bool(before.hand_features[env, slot, 5])
                if reusable:
                    self._utility_casts += 1
                    self._utility_mp_spent += round(float(before.hand_features[env, slot, 4]) * 100)
                else:
                    self._utility_consumed += 1
                    if self.metadata.refill_plan is not None:
                        self._pending_refills[env].add((int(before.actors[env]), slot))
        if len(attack):
            targets = (
                before.actors[attack] + actions[attack] - TARGET_START
            ) % self.config.player_count
            self._native.begin_card_attacks(
                attack, before.actors[attack], self._selected_slots[attack], targets
            )
            if self.metadata.refill_plan is not None:
                for env in attack:
                    slot = int(self._selected_slots[env])
                    if (
                        before.hand_model_ids[env, slot]
                        in self.metadata.native.attack_weapon_model_ids
                    ):
                        self._pending_refills[env].add((int(before.actors[env]), slot))
            self._selected_slots[attack] = -1
        if len(defend):
            native_actions = np.where(
                actions[defend] < TARGET_START, actions[defend] - 1, actions[defend] - 10
            )
            self._native.step_defenses(defend, before.actors[defend], native_actions)
            if self.metadata.refill_plan is not None:
                for env in defend[actions[defend] == CONFIRM]:
                    selected = before.hand_features[env, :, 6] > 0
                    armor = np.isin(
                        before.hand_model_ids[env], self.metadata.native.armor_model_ids
                    )
                    for armor_slot in np.flatnonzero(selected & armor):
                        self._pending_refills[env].add((int(before.actors[env]), int(armor_slot)))
        if len(bounce):
            targets = (
                before.actors[bounce] + actions[bounce] - TARGET_START
            ) % self.config.player_count
            self._native.resolve_bounces(bounce, before.actors[bounce], targets)
        self._selected_slots[select] = actions[select] - 1
        self._decisions[rows] += 1
        turn = self._native.turn_snapshot()
        terminated = turn[:, 0] == 2
        self._budget_truncated |= (
            before.active & ~terminated & (self._decisions >= self.config.max_decisions)
        )
        truncated = (turn[:, 0] == 3) | self._budget_truncated
        finished = terminated | truncated
        self._apply_refills(turn, finished)
        newly_finished = before.active & finished
        next_potential = self._potential()
        next_potential[finished] = 0  # bounded episodes explicitly use zero bootstrap
        rewards = self.config.shaping_weight * (self.config.gamma * next_potential - potential)
        rewards[~before.active] = 0
        winners = np.where(terminated, turn[:, 4], -1)
        won_rows = np.flatnonzero(before.active & terminated)
        rewards[won_rows] -= 1 / (self.config.player_count - 1)
        rewards[won_rows, winners[won_rows]] += 1 + 1 / (self.config.player_count - 1)
        return GuardianTransition(
            self.observe(),
            before.actors,
            _readonly(rewards.astype(np.float32)),
            _readonly(terminated),
            _readonly(truncated),
            _readonly(newly_finished),
            _readonly(winners),
        )


def greedy_guardian_actions(observation: GuardianObservation) -> IntArray:
    """Legal, terminating smoke-test baseline, not a claim of expert play."""
    actions = np.full(len(observation.actors), -1, dtype=np.int64)
    for env in np.flatnonzero(observation.active):
        mask, hand = observation.action_mask[env], observation.hand_features[env]
        phase = observation.phases[env]
        slots = np.flatnonzero(mask[1:TARGET_START])
        if phase == 0:
            if len(slots):
                score = hand[slots, 1] - 0.1 * hand[slots, 4]
                if hand.shape[1] == UTILITY_HAND_FEATURE_COUNT:
                    hp, mp = observation.players[env, 0, :2]
                    healing = hand[slots, 7] > 0
                    mana = hand[slots, 8] > 0
                    score[healing] = (
                        np.minimum(hand[slots[healing], 7], 1 - hp) * (1.5 if hp <= 0.35 else 0.6)
                        - 0.1 * hand[slots[healing], 4]
                    )
                    missing = max(0.0, float(hand[:, 4].max()) - float(mp))
                    gains = np.minimum(hand[slots[mana], 8], 1 - mp)
                    score[mana] = 1.2 * np.minimum(gains, missing) + 0.05 * gains
                actions[env] = slots[int(np.argmax(score))] + 1
            else:
                actions[env] = 0
        elif phase in (4, TARGET_PHASE):
            targets = np.flatnonzero(mask[TARGET_START:FORGIVE])
            hp = observation.players[env, targets, 0]
            actions[env] = TARGET_START + targets[int(np.argmin(hp))]
        elif phase == 1:
            selected = hand[:, 6] > 0
            special = (hand[:, 5] > 0) & (hand[:, 2] == 0)
            selected_special = np.any(selected & special)
            enough = observation.global_features[env, 9] >= observation.global_features[env, 15]
            unselected = slots[~selected[slots]]
            if (selected_special or enough) and mask[CONFIRM]:
                actions[env] = CONFIRM
            elif len(unselected):
                score = hand[unselected, 2] + special[unselected]
                actions[env] = unselected[int(np.argmax(score))] + 1
            else:
                actions[env] = CONFIRM if np.any(selected) and mask[CONFIRM] else FORGIVE
        else:
            raise ValueError("unsupported active arena phase")
    return actions


class GuardianRolloutReport(BaseModel):
    schema_version: Literal[1] = 1
    metadata: GuardianRolloutMetadata
    steps: int
    transitions: int
    games_completed: int
    games_truncated: int
    wins_by_seat: tuple[int, ...]
    decisions_by_phase: tuple[int, ...]
    actions_by_index: tuple[int, ...]
    transition_sha256: str
    replacement_gifts: int = Field(default=0, ge=0, strict=True)
    utility_statistics: GuardianUtilityStatistics | None = None
    collection_policy: Literal["greedy-smoke-baseline-v1", "greedy-utility-smoke-baseline-v2"] = (
        "greedy-smoke-baseline-v1"
    )
    learning_performed: Literal[False] = False


def collect_guardian_rollout(arena: GuardianRolloutArena, *, steps: int) -> GuardianRolloutReport:
    """Stream bounded transitions and a reproducibility digest; no weights are trained."""
    if (
        type(steps) is not int
        or not 1 <= steps <= 100_000
        or steps * arena.config.batch_size > 1_000_000
    ):
        raise ValueError("rollout requires 1..100000 steps and at most 1000000 transitions")
    digest = hashlib.sha256(arena.metadata.model_dump_json().encode())
    phases = np.zeros(6, dtype=np.int64)
    action_counts = np.zeros(ACTION_COUNT, dtype=np.int64)
    wins = np.zeros(arena.config.player_count, dtype=np.int64)
    completed = truncated = 0
    initial_gifts = arena.replacement_gifts
    initial_utilities = arena.utility_statistics
    for _ in range(steps):
        observation = arena.reset_done()
        actions = greedy_guardian_actions(observation)
        phases += np.bincount(observation.phases, minlength=6)
        action_counts += np.bincount(actions, minlength=ACTION_COUNT)
        transition = arena.step(actions)
        completed += int(np.count_nonzero(transition.newly_finished & transition.terminated))
        truncated += int(np.count_nonzero(transition.newly_finished & transition.truncated))
        for winner in transition.winners[transition.newly_finished & transition.terminated]:
            wins[winner] += 1
        for array in (
            observation.global_features,
            observation.players,
            observation.hand_model_ids,
            observation.hand_features,
            observation.action_mask,
            observation.actors,
            observation.episode_ids,
            actions,
            transition.rewards,
            transition.terminated,
            transition.truncated,
            transition.winners,
        ):
            digest.update(array.tobytes(order="C"))
    return GuardianRolloutReport(
        metadata=arena.metadata,
        steps=steps,
        transitions=steps * arena.config.batch_size,
        games_completed=completed,
        games_truncated=truncated,
        wins_by_seat=tuple(int(value) for value in wins),
        decisions_by_phase=tuple(int(value) for value in phases),
        actions_by_index=tuple(int(value) for value in action_counts),
        transition_sha256=digest.hexdigest(),
        replacement_gifts=arena.replacement_gifts - initial_gifts,
        utility_statistics=arena.utility_statistics.since(initial_utilities)
        if initial_utilities is not None and arena.utility_statistics is not None
        else None,
        collection_policy="greedy-utility-smoke-baseline-v2"
        if arena.config.inventory_utilities
        else "greedy-smoke-baseline-v1",
    )
