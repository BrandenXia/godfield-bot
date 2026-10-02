"""Source-pinned adapter for the separate, incomplete native full-game engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.curse_dynamics import CurseDynamicsPlan, build_curse_dynamics_plan
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.dream_inventory import DreamInventoryPlan, build_dream_inventory_plan
from godfield_bot.full_game_protocol import (
    FullGameCommand,
    FullGameDecisionContext,
    FullGamePhase,
    validate_full_game_commands,
)
from godfield_bot.guardian_utility import GuardianUtilityPlan, build_guardian_utility_plan
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    from godfield_sim import FullGameBatch

FULL_GAME_RULESET_ID: Final = "integrated-full-game-development-v1"
FULL_GAME_EFFECT_SHA256: Final = "834c9fe8bce6185e2bb3729c64813e85ef84daf07c77fd7a8030b32362ccaae1"
FULL_GAME_PHASES: Final[tuple[FullGamePhase, ...]] = get_args(FullGamePhase)
COMMAND_FIELDS: Final = ("environment", "episode", "decision", "actor", "phase", "choice_id")
EPISODE_FIELDS: Final = (
    "episode",
    "decision",
    "actor",
    "phase",
    "completed_turns",
    "outcome",
    "winner",
    "accepted_commands",
    "last_choice_id",
)
PLAYER_FIELDS: Final = (
    "seat",
    "present",
    "visible",
    "hp",
    "mp",
    "cp",
    "illness_stage",
    "curse_mask",
)
DIAGNOSTIC_FIELDS: Final = ("hp", "mp", "cp", "illness_stage", "curse_mask", "owner_turn_ticks")
OUTCOMES: Final = ("none", "winner", "all-dead-draw", "turn-limit", "decision-limit")
EFFECT_FIELDS: Final = ("model_id", "effect", "value", "mp_cost")


class FullGamePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    inventory: DreamInventoryPlan
    curses: CurseDynamicsPlan
    utilities: GuardianUtilityPlan
    effect_sha256: Literal["834c9fe8bce6185e2bb3729c64813e85ef84daf07c77fd7a8030b32362ccaae1"] = (
        FULL_GAME_EFFECT_SHA256
    )
    effect_profiles: tuple[tuple[int, int, int, int], ...]
    effect_fields: tuple[str, ...] = EFFECT_FIELDS
    implemented_effect_count: Literal[12] = 12
    implemented_phases: tuple[int, ...] = (0, 1, 12, 13)
    effect_codes: tuple[str, ...] = ("unused-zero", "hp", "mp", "mild-cure", "full-cure")
    scheduling: Literal["immediate-self-utility-then-owner-disease-tick-provisional"] = (
        "immediate-self-utility-then-owner-disease-tick-provisional"
    )
    acquisition: Literal["explicit-setup-gifts-no-automatic-refill-or-official-deal"] = (
        "explicit-setup-gifts-no-automatic-refill-or-official-deal"
    )
    hidden_resolution: Literal[
        "unsupported-effect-or-unaffordable-cost-atomic-development-error"
    ] = "unsupported-effect-or-unaffordable-cost-atomic-development-error"
    free_for_all_ending: Literal["one-living-wins-all-dead-draw-before-limits-provisional"] = (
        "one-living-wins-all-dead-draw-before-limits-provisional"
    )
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_effects(self) -> FullGamePlan:
        expected = tuple(
            sorted(
                [
                    (model, resource + 1, gain, cost)
                    for model, resource, gain, _, cost in self.utilities.profiles
                ]
                + [
                    (model, scope + 2, 0, cost)
                    for model, scope, _, cost in self.curses.cure_profiles
                ]
            )
        )
        digest = hashlib.sha256(
            json.dumps(self.effect_profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.effect_profiles != expected
            or digest != self.effect_sha256
            or self.effect_fields != EFFECT_FIELDS
            or self.implemented_phases != (0, 1, 12, 13)
            or self.effect_codes != ("unused-zero", "hp", "mp", "mild-cure", "full-cure")
            or len(
                {
                    self.inventory.catalog_sha256,
                    self.curses.catalog_sha256,
                    self.utilities.catalog_sha256,
                }
            )
            != 1
            or len(
                {
                    self.inventory.bible_client_sha256,
                    self.curses.bible_client_sha256,
                    self.utilities.bible_client_sha256,
                }
            )
            != 1
        ):
            raise ValueError("full-game initial integrated effect contract differs")
        return self


def build_full_game_plan(catalog: ApiCatalogSnapshot, bible: BibleSnapshot) -> FullGamePlan:
    inventory = build_dream_inventory_plan(catalog, bible)
    curses = build_curse_dynamics_plan(catalog, bible)
    utilities = build_guardian_utility_plan(catalog, bible)
    effects = tuple(
        sorted(
            [
                (model, resource + 1, gain, cost)
                for model, resource, gain, _, cost in utilities.profiles
            ]
            + [(model, scope + 2, 0, cost) for model, scope, _, cost in curses.cure_profiles]
        )
    )
    return FullGamePlan(
        inventory=inventory, curses=curses, utilities=utilities, effect_profiles=effects
    )


class FullGameMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["integrated-full-game-development-v1"] = FULL_GAME_RULESET_ID
    command_schema_version: Literal[1] = 1
    observation_schema_version: Literal[1] = 1
    plan: FullGamePlan
    batch_size: int = Field(ge=1, le=1_000_000, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    capacity: int = Field(ge=1, le=512, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    max_turns: int = Field(ge=1, le=1_000_000_000, strict=True)
    max_decisions: int = Field(ge=1, le=1_000_000_000, strict=True)
    initial_hp: int = Field(ge=1, le=100, strict=True)
    initial_mp: int = Field(ge=0, le=100, strict=True)
    initial_cp: int = Field(ge=0, le=100, strict=True)
    command_fields: tuple[str, ...] = COMMAND_FIELDS
    episode_fields: tuple[str, ...] = EPISODE_FIELDS
    player_observation_fields: tuple[str, ...] = PLAYER_FIELDS
    diagnostic_fields: tuple[str, ...] = DIAGNOSTIC_FIELDS
    phase_names: tuple[str, ...] = FULL_GAME_PHASES
    outcome_names: tuple[str, ...] = OUTCOMES
    randomness: Literal[
        "separate-native-splitmix-gift-and-illness-rejection-max-16-provisional"
    ] = "separate-native-splitmix-gift-and-illness-rejection-max-16-provisional"
    limits: Literal["terminal-before-turn-before-decision-limit-truncation-not-draw"] = (
        "terminal-before-turn-before-decision-limit-truncation-not-draw"
    )
    diagnostic_boundary: Literal[
        "all-true-inventories-resources-ticks-controls-not-policy-features"
    ] = "all-true-inventories-resources-ticks-controls-not-policy-features"
    observation_boundary: Literal["actor-cyclic-nine-seats-fog-hides-other-resources-status"] = (
        "actor-cyclic-nine-seats-fog-hides-other-resources-status"
    )
    choice_boundary: Literal[
        "pass-or-own-slot-plus-one-displayed-effect-and-self-affordability"
    ] = "pass-or-own-slot-plus-one-displayed-effect-and-self-affordability"
    setup_boundary: Literal["closed-on-start-until-reset-epoch-increases"] = (
        "closed-on-start-until-reset-epoch-increases"
    )
    joined_transactions_implemented: Literal[True] = True
    native_command_tokens_rechecked: Literal[True] = True
    complete_action_observation_contract: Literal[False] = False
    complete_mechanics_and_acquisition: Literal[False] = False
    team_rules_and_rewards_implemented: Literal[False] = False
    action_observation_checkpoint_compatible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def bounded_pinned_layout(self) -> FullGameMetadata:
        if (
            self.batch_size * self.player_count * self.capacity > 2_000_000
            or self.command_fields != COMMAND_FIELDS
            or self.episode_fields != EPISODE_FIELDS
            or self.player_observation_fields != PLAYER_FIELDS
            or self.diagnostic_fields != DIAGNOSTIC_FIELDS
            or self.phase_names != FULL_GAME_PHASES
            or self.outcome_names != OUTCOMES
        ):
            raise ValueError("full-game storage or projection contract differs")
        return self


@dataclass(frozen=True)
class DevelopmentFullGameBatch:
    batch: FullGameBatch
    metadata: FullGameMetadata


def create_development_full_game_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    capacity: int = 512,
    seed: int = 67,
    max_turns: int = 1000,
    max_decisions: int = 4000,
    initial_hp: int = 40,
    initial_mp: int = 10,
    initial_cp: int = 0,
) -> DevelopmentFullGameBatch:
    plan = build_full_game_plan(
        read_api_catalog_snapshot(catalog_path),
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    metadata = FullGameMetadata(
        plan=plan,
        batch_size=batch_size,
        player_count=player_count,
        capacity=capacity,
        seed=seed,
        max_turns=max_turns,
        max_decisions=max_decisions,
        initial_hp=initial_hp,
        initial_mp=initial_mp,
        initial_cp=initial_cp,
    )
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "full-game development engine requires simulation extra"
        ) from None
    if (
        getattr(native, "FULL_GAME_KERNEL_SCHEMA_VERSION", None) != 1
        or getattr(native, "FULL_GAME_COMMAND_SCHEMA_VERSION", None) != 1
        or getattr(native, "FULL_GAME_OBSERVATION_SCHEMA_VERSION", None) != 1
        or getattr(native, "FULL_GAME_RULESET_ID", None) != FULL_GAME_RULESET_ID
        or not hasattr(native, "FullGameBatch")
    ):
        raise ProvisionalRuleUnavailableError("native full-game development contract differs")
    return DevelopmentFullGameBatch(
        native.FullGameBatch(
            batch_size,
            player_count,
            np.asarray(plan.inventory.profiles, dtype=np.int64),
            np.asarray(plan.effect_profiles, dtype=np.int64),
            capacity,
            seed,
            max_turns,
            max_decisions,
            initial_hp,
            initial_mp,
            initial_cp,
        ),
        metadata,
    )


def full_game_decision_contexts(
    configured: DevelopmentFullGameBatch,
) -> dict[int, FullGameDecisionContext]:
    """Diagnostic/CLI adapter only; training should use native arrays directly."""
    import numpy as np

    episodes = configured.batch.episode_snapshot()
    masks = configured.batch.choice_masks()
    return {
        env: FullGameDecisionContext(
            environment=env,
            episode=int(row[0]),
            decision=int(row[1]),
            actor=int(row[2]),
            phase=FULL_GAME_PHASES[int(row[3])],
            legal_choice_ids=tuple(int(choice) for choice in np.flatnonzero(masks[env])),
        )
        for env, row in enumerate(episodes)
    }


def pack_full_game_commands(commands: Sequence[FullGameCommand]) -> npt.NDArray[np.int64]:
    """Public commands only; no true card IDs or caller-supplied random tickets."""
    import numpy as np

    validated = [FullGameCommand.model_validate(command.model_dump()) for command in commands]
    return np.asarray(
        [
            (
                command.environment,
                command.episode,
                command.decision,
                command.actor,
                FULL_GAME_PHASES.index(command.phase),
                command.choice_id,
            )
            for command in validated
        ],
        dtype=np.int64,
    ).reshape(-1, 6)


def execute_full_game_commands(
    configured: DevelopmentFullGameBatch,
    commands: Sequence[FullGameCommand],
) -> None:
    """Validate the adapter context; native step independently validates before commit."""
    accepted = validate_full_game_commands(commands, full_game_decision_contexts(configured))
    configured.batch.step(pack_full_game_commands(accepted))


class FullGameSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["integrated-development-utility-cure-smoke-v1"] = (
        "integrated-development-utility-cure-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v1"] = FULL_GAME_RULESET_ID
    scenario: Literal["fixed-own-utility-cure-hands-disease-not-combat-strength"] = (
        "fixed-own-utility-cure-hands-disease-not-combat-strength"
    )
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    max_turns: int = Field(ge=1, le=4096, strict=True)
    winners: int = Field(ge=0, strict=True)
    all_dead_draws: int = Field(ge=0, strict=True)
    turn_limit_truncations: int = Field(ge=0, strict=True)
    decision_limit_truncations: int = Field(ge=0, strict=True)
    unfinished: Literal[0] = 0
    actions: int = Field(ge=0, strict=True)
    passes: int = Field(ge=0, strict=True)
    utilities: int = Field(ge=0, strict=True)
    mp_spent: int = Field(ge=0, strict=True)
    consumed_cards: int = Field(ge=0, strict=True)
    retained_miracle_uses: int = Field(ge=0, strict=True)
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def complete_bounded_accounting(self) -> FullGameSmokeReport:
        if (
            self.winners
            + self.all_dead_draws
            + self.turn_limit_truncations
            + self.decision_limit_truncations
            != self.batch_size
            or self.actions != self.passes + self.utilities
            or self.utilities != self.consumed_cards + self.retained_miracle_uses
            or self.actions > self.batch_size * self.max_turns
        ):
            raise ValueError("full-game smoke outcomes or action accounting differ")
        return self


def run_full_game_development_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 32,
    player_count: int = 3,
    seed: int = 67,
    max_turns: int = 64,
) -> FullGameSmokeReport:
    """Offline joined-state liveness probe, NOT gameplay training or evaluation."""
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("development smoke batch size must be 1 through 4096")
    if type(max_turns) is not int or not 1 <= max_turns <= 4096:
        raise ValueError("development smoke turn bound must be 1 through 4096")
    configured = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        max_turns=max_turns,
        max_decisions=max_turns + 1,
        capacity=8,
        initial_hp=30,
        initial_mp=20,
    )
    batch = configured.batch
    envs = np.repeat(np.arange(batch_size, dtype=np.int64), player_count)
    owners = np.tile(np.arange(player_count, dtype=np.int64), batch_size)
    resources = np.zeros((batch_size * player_count, 4), dtype=np.int64)
    resources[:, :3] = (30, 20, 5)
    resources[:, 3] = owners % 5
    batch.seed_players(envs, owners, resources, np.full(len(envs), 15, dtype=np.int64))
    for env in range(batch_size):
        for owner in range(player_count):
            start = owner * 4 + 1
            batch.seed_hand(
                env,
                owner,
                np.asarray(
                    [
                        (start + index, model, 0, 0)
                        for index, model in enumerate((194, 195, 237, 238))
                    ],
                    dtype=np.int64,
                ),
            )
    batch.start_environments(np.arange(batch_size, dtype=np.int64))
    digest = hashlib.sha256()

    def fingerprint() -> None:
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
        ):
            digest.update(view.astype("<i8", copy=False).tobytes())

    fingerprint()
    for _ in range(max_turns):
        episodes = batch.episode_snapshot()
        active = np.flatnonzero(episodes[:, 3] == 1)
        if not len(active):
            break
        masks = batch.choice_masks()[active, 1:]
        choices = np.where(np.any(masks, axis=1), np.argmax(masks, axis=1) + 1, 0)
        commands = np.column_stack((active, episodes[active, :4], choices)).astype(np.int64)
        batch.step(commands)
        fingerprint()
    episodes = batch.episode_snapshot()
    if np.any((episodes[:, 3] != 12) & (episodes[:, 3] != 13)):
        raise RuntimeError("full-game development smoke left unfinished environments")
    metadata_sha = hashlib.sha256(
        json.dumps(
            configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return FullGameSmokeReport(
        metadata_sha256=metadata_sha,
        diagnostic_replay_sha256=digest.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        max_turns=max_turns,
        winners=int(np.count_nonzero(episodes[:, 5] == 1)),
        all_dead_draws=int(np.count_nonzero(episodes[:, 5] == 2)),
        turn_limit_truncations=int(np.count_nonzero(episodes[:, 5] == 3)),
        decision_limit_truncations=int(np.count_nonzero(episodes[:, 5] == 4)),
        actions=batch.action_count,
        passes=batch.pass_count,
        utilities=batch.utility_count,
        mp_spent=batch.mp_spent,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
    )
