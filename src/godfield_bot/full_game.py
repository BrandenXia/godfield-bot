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
from godfield_bot.full_game_acquisition import (
    FullGameAcquisitionPlan,
    build_full_game_acquisition_plan,
)
from godfield_bot.full_game_combat_plan import FullGameCombatPlan, build_full_game_combat_plan
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

FULL_GAME_RULESET_ID: Final = "integrated-full-game-development-v7"
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
PENDING_FIELDS: Final = (
    "active",
    "turn_owner",
    "target",
    "attack",
    "element",
    "origin",
    "displayed_selected_defense",
    "selected_count",
    "selection_actions",
    "reserved_attack_choice",
)
ACQUISITION_FIELDS: Final = ("gifts_due", "automatic_receipts", "automatic_evictions")
SPECIAL_DEFENSE_FIELDS: Final = (
    "active",
    "damage_source",
    "redirect_count",
    "displayed_response_kind",
    "displayed_mp_cost",
)
ATTACK_SELECTION_FIELDS: Final = (
    "selected_count",
    "displayed_attack",
    "displayed_element",
    "displayed_mp_cost",
    "selection_actions",
)
CHANCE_FIELDS: Final = ("active", "displayed_hit_rate", "already_hit", "automatic_target")
CHANCE_SNAPSHOT_FIELDS: Final = ("casts", "hits", "misses")
ATTACK_EFFECT_FIELDS: Final = ("active", "kind", "value", "damage_source")
ATTACK_EFFECT_SNAPSHOT_FIELDS: Final = (
    "absorptions",
    "absorbed_hp",
    "inflicted_curses",
    "inflicted_illnesses",
    "illness_effect_damage",
    "dark_cloud_hits",
)
AcquisitionMode = Literal["manual", "all-held-weighted"]


class FullGamePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[7] = 7
    inventory: DreamInventoryPlan
    curses: CurseDynamicsPlan
    utilities: GuardianUtilityPlan
    combat: FullGameCombatPlan
    gifts: FullGameAcquisitionPlan
    effect_sha256: Literal["834c9fe8bce6185e2bb3729c64813e85ef84daf07c77fd7a8030b32362ccaae1"] = (
        FULL_GAME_EFFECT_SHA256
    )
    effect_profiles: tuple[tuple[int, int, int, int], ...]
    effect_fields: tuple[str, ...] = EFFECT_FIELDS
    implemented_effect_count: Literal[12] = 12
    implemented_phases: tuple[int, ...] = (0, 1, 2, 3, 4, 12, 13)
    integrated_artifact_effect_count: Literal[195] = 195
    effect_codes: tuple[str, ...] = ("unused-zero", "hp", "mp", "mild-cure", "full-cure")
    scheduling: Literal[
        "utility-or-ordered-attack-target-chained-defenses-then-owner-tick-provisional"
    ] = "utility-or-ordered-attack-target-chained-defenses-then-owner-tick-provisional"
    acquisition: Literal["opt-in-full-held-native-deal-and-per-use-gifts-provisional"] = (
        "opt-in-full-held-native-deal-and-per-use-gifts-provisional"
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
            or self.implemented_phases != (0, 1, 2, 3, 4, 12, 13)
            or self.effect_codes != ("unused-zero", "hp", "mp", "mild-cure", "full-cure")
            or len(
                {
                    self.inventory.catalog_sha256,
                    self.curses.catalog_sha256,
                    self.utilities.catalog_sha256,
                    self.gifts.catalog_sha256,
                    self.combat.catalog_sha256,
                }
            )
            != 1
            or len(
                {
                    self.inventory.bible_client_sha256,
                    self.curses.bible_client_sha256,
                    self.utilities.bible_client_sha256,
                    self.gifts.bible_client_sha256,
                    self.combat.bible_client_sha256,
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
        inventory=inventory,
        curses=curses,
        utilities=utilities,
        combat=build_full_game_combat_plan(catalog, bible),
        gifts=build_full_game_acquisition_plan(catalog, bible),
        effect_profiles=effects,
    )


class FullGameMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[7] = 7
    ruleset_id: Literal["integrated-full-game-development-v7"] = FULL_GAME_RULESET_ID
    kernel_schema_version: Literal[7] = 7
    command_schema_version: Literal[1] = 1
    observation_schema_version: Literal[7] = 7
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
    acquisition_mode: AcquisitionMode = "manual"
    initial_deal_cards: int = Field(default=0, ge=0, le=9, strict=True)
    refill_on_use: bool = Field(default=False, strict=True)
    prayer_gifts: bool = Field(default=False, strict=True)
    hand_limit: int = Field(ge=1, le=512, strict=True)
    overflow_policy: Literal["reject", "oldest-held-provisional"] = "reject"
    hand_limit_boundary: Literal["explicit-local-cap-not-proven-official-ownership-maximum"] = (
        "explicit-local-cap-not-proven-official-ownership-maximum"
    )
    acquisition_snapshot_fields: tuple[str, ...] = ACQUISITION_FIELDS
    acquisition_snapshot_boundary: Literal["all-owner-scheduler-counters-diagnostic-not-policy"] = (
        "all-owner-scheduler-counters-diagnostic-not-policy"
    )
    command_fields: tuple[str, ...] = COMMAND_FIELDS
    episode_fields: tuple[str, ...] = EPISODE_FIELDS
    player_observation_fields: tuple[str, ...] = PLAYER_FIELDS
    diagnostic_fields: tuple[str, ...] = DIAGNOSTIC_FIELDS
    pending_observation_fields: tuple[str, ...] = PENDING_FIELDS
    special_defense_observation_fields: tuple[str, ...] = SPECIAL_DEFENSE_FIELDS
    chance_observation_fields: tuple[str, ...] = CHANCE_FIELDS
    chance_snapshot_fields: tuple[str, ...] = CHANCE_SNAPSHOT_FIELDS
    attack_effect_observation_fields: tuple[str, ...] = ATTACK_EFFECT_FIELDS
    attack_effect_snapshot_fields: tuple[str, ...] = ATTACK_EFFECT_SNAPSHOT_FIELDS
    attack_effect_snapshot_boundary: Literal["episode-effect-counters-diagnostic-not-policy"] = (
        "episode-effect-counters-diagnostic-not-policy"
    )
    damage_effect_timing: Literal[
        "positive-actual-hp-loss-before-original-owner-tick-provisional"
    ] = "positive-actual-hp-loss-before-original-owner-tick-provisional"
    absorption: Literal[
        "current-living-source-heals-post-defense-hp-loss-cap100-no-resurrection-provisional"
    ] = "current-living-source-heals-post-defense-hp-loss-cap100-no-resurrection-provisional"
    direct_curses: Literal[
        "enemy-only-zero-atk-special-defense-only-no-effect-if-blocked-provisional"
    ] = "enemy-only-zero-atk-special-defense-only-no-effect-if-blocked-provisional"
    curse_infliction: Literal[
        "living-final-target-existing-illness-worsens-new-dream-gifts-only-provisional"
    ] = "living-final-target-existing-illness-worsens-new-dream-gifts-only-provisional"
    chance_policy: Literal[
        "standalone-no-additions-native-roll-on-confirm-no-defense-on-miss-provisional"
    ] = "standalone-no-additions-native-roll-on-confirm-no-defense-on-miss-provisional"
    chance_target: Literal[
        "native-uniform-living-enemies-before-roll-dark-cloud-skips-ticket-provisional"
    ] = "native-uniform-living-enemies-before-roll-dark-cloud-skips-ticket-provisional"
    hidden_target_mode: Literal[
        "mismatched-displayed-actual-target-mode-atomic-development-error"
    ] = "mismatched-displayed-actual-target-mode-atomic-development-error"
    special_selection: Literal["exclusive-special-or-compatible-numeric-armor-source-pinned"] = (
        "exclusive-special-or-compatible-numeric-armor-source-pinned"
    )
    reflection: Literal[
        "to-current-source-reflector-becomes-source-original-turn-owner-preserved-provisional"
    ] = "to-current-source-reflector-becomes-source-original-turn-owner-preserved-provisional"
    bounce: Literal[
        "uniform-living-including-self-source-preserved-native-separate-stream-provisional"
    ] = "uniform-living-including-self-source-preserved-native-separate-stream-provisional"
    redirect_limit: Literal[
        "fresh-response-until-resolution-or-explicit-episode-decision-truncation"
    ] = "fresh-response-until-resolution-or-explicit-episode-decision-truncation"
    attack_selection_fields: tuple[str, ...] = ATTACK_SELECTION_FIELDS
    max_attack_actions: Literal[64] = 64
    max_exact_attack: Literal[9007199254740991] = 9007199254740991
    attack_composition: Literal["ordered-public-selection-fixed-weapon-additions-source-pinned"] = (
        "ordered-public-selection-fixed-weapon-additions-source-pinned"
    )
    attack_limit: Literal["confirm-only-after-64-selections-toggles-provisional"] = (
        "confirm-only-after-64-selections-toggles-provisional"
    )
    attack_undo: Literal["remove-addition-recompute-order-leader-undo-cancels-all-provisional"] = (
        "remove-addition-recompute-order-leader-undo-cancels-all-provisional"
    )
    max_defense_actions: Literal[64] = 64
    defense_limit: Literal["confirm-only-after-64-toggles-not-silent-auto-defense"] = (
        "confirm-only-after-64-toggles-not-silent-auto-defense"
    )
    target_policy: Literal["living-enemies-seat-choice-fog-samples-endogenous-provisional"] = (
        "living-enemies-seat-choice-fog-samples-endogenous-provisional"
    )
    phase_names: tuple[str, ...] = FULL_GAME_PHASES
    outcome_names: tuple[str, ...] = OUTCOMES
    randomness: Literal[
        "native-splitmix-model-disguise-illness-fog-bounce-chance-roll-target-max16-provisional"
    ] = "native-splitmix-model-disguise-illness-fog-bounce-chance-roll-target-max16-provisional"
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
        "phase-zero-or-own-slot-plus-one-or-capacity-plus-one-plus-target-seat"
    ] = "phase-zero-or-own-slot-plus-one-or-capacity-plus-one-plus-target-seat"
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
            or self.pending_observation_fields != PENDING_FIELDS
            or self.special_defense_observation_fields != SPECIAL_DEFENSE_FIELDS
            or self.chance_observation_fields != CHANCE_FIELDS
            or self.chance_snapshot_fields != CHANCE_SNAPSHOT_FIELDS
            or self.attack_effect_observation_fields != ATTACK_EFFECT_FIELDS
            or self.attack_effect_snapshot_fields != ATTACK_EFFECT_SNAPSHOT_FIELDS
            or self.attack_selection_fields != ATTACK_SELECTION_FIELDS
            or self.acquisition_snapshot_fields != ACQUISITION_FIELDS
            or self.phase_names != FULL_GAME_PHASES
            or self.outcome_names != OUTCOMES
        ):
            raise ValueError("full-game storage or projection contract differs")
        expected = (
            (0, False, False, self.capacity, "reject")
            if self.acquisition_mode == "manual"
            else (9, True, True, 18, "oldest-held-provisional")
        )
        if (
            self.initial_deal_cards,
            self.refill_on_use,
            self.prayer_gifts,
            self.hand_limit,
            self.overflow_policy,
        ) != expected or self.hand_limit > self.capacity:
            raise ValueError("full-game acquisition mode and native options differ")
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
    acquisition_mode: AcquisitionMode = "manual",
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
        acquisition_mode=acquisition_mode,
        initial_deal_cards=9 if acquisition_mode == "all-held-weighted" else 0,
        refill_on_use=acquisition_mode == "all-held-weighted",
        prayer_gifts=acquisition_mode == "all-held-weighted",
        hand_limit=18 if acquisition_mode == "all-held-weighted" else capacity,
        overflow_policy="oldest-held-provisional"
        if acquisition_mode == "all-held-weighted"
        else "reject",
    )
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "full-game development engine requires simulation extra"
        ) from None
    if (
        getattr(native, "FULL_GAME_KERNEL_SCHEMA_VERSION", None) != 7
        or getattr(native, "FULL_GAME_COMMAND_SCHEMA_VERSION", None) != 1
        or getattr(native, "FULL_GAME_OBSERVATION_SCHEMA_VERSION", None) != 7
        or getattr(native, "FULL_GAME_MAX_DEFENSE_ACTIONS", None) != 64
        or getattr(native, "FULL_GAME_MAX_ATTACK_ACTIONS", None) != 64
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
            np.asarray(plan.combat.attack_profiles, dtype=np.int64),
            np.asarray(plan.combat.armor_profiles, dtype=np.int64),
            np.asarray(plan.gifts.model_weights, dtype=np.int64),
            metadata.initial_deal_cards,
            metadata.refill_on_use,
            metadata.prayer_gifts,
            metadata.hand_limit,
            metadata.overflow_policy == "oldest-held-provisional",
            np.asarray(plan.combat.boost_profiles, dtype=np.int64),
            np.asarray(plan.combat.special_profiles, dtype=np.int64),
            np.asarray(plan.combat.chance_profiles, dtype=np.int64),
            np.asarray(plan.combat.attack_effect_profiles, dtype=np.int64),
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
    ruleset_id: Literal["integrated-full-game-development-v7"] = FULL_GAME_RULESET_ID
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
