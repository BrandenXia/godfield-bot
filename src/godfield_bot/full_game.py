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
from godfield_bot.full_game_area import FullGameAreaPlan, build_full_game_area_plan
from godfield_bot.full_game_attack_family import (
    FullGameAttackFamilyPlan,
    build_full_game_attack_family_plan,
)
from godfield_bot.full_game_combat_plan import FullGameCombatPlan, build_full_game_combat_plan
from godfield_bot.full_game_compound_utilities import (
    FullGameCompoundUtilityPlan,
    build_full_game_compound_utility_plan,
)
from godfield_bot.full_game_costs import FullGameCostPlan, build_full_game_cost_plan
from godfield_bot.full_game_danger import FullGameDangerPlan, build_full_game_danger_plan
from godfield_bot.full_game_devils import FullGameDevilPlan, build_full_game_devil_plan
from godfield_bot.full_game_discard import FullGameDiscardPlan, build_full_game_discard_plan
from godfield_bot.full_game_dream_defense import (
    FullGameDreamDefensePlan,
    build_full_game_dream_defense_plan,
)
from godfield_bot.full_game_economy import FullGameEconomyPlan, build_full_game_economy_plan
from godfield_bot.full_game_guardians import (
    GENERATED_ACTION_FIELDS,
    GUARDIAN_GENERATED_STATS,
    FullGameGuardianPlan,
    build_full_game_guardian_plan,
)
from godfield_bot.full_game_passives import FullGamePassivePlan, build_full_game_passive_plan
from godfield_bot.full_game_phenomena import FullGamePhenomenonPlan, build_full_game_phenomenon_plan
from godfield_bot.full_game_protocol import (
    FullGameCommand,
    FullGameDecisionContext,
    FullGamePhase,
    validate_full_game_commands,
)
from godfield_bot.full_game_removal import FullGameRemovalPlan, build_full_game_removal_plan
from godfield_bot.full_game_roles import FullGameRoleManifest, build_full_game_role_manifest
from godfield_bot.full_game_teams import TEAM_FIELDS, FullGameTeamPlan, TeamId
from godfield_bot.full_game_trade import (
    MARKET_ESCROW_FIELDS,
    MARKET_FIELDS,
    MARKET_STATS,
    TRADE_FIELDS,
    TRADE_STATS,
    FullGameTradePlan,
    build_full_game_trade_plan,
)
from godfield_bot.full_game_weapons import FullGameWeaponPlan, build_full_game_weapon_plan
from godfield_bot.guardian_utility import GuardianUtilityPlan, build_guardian_utility_plan
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    from godfield_sim import FullGameBatch

FULL_GAME_RULESET_ID: Final = "integrated-full-game-development-v32"
INEFFECTIVE_FIELDS: Final = (
    "affected_attack_uses",
    "affected_utility_uses",
    "affected_defense_responses",
    "ineffective_leaders",
    "ineffective_additions",
    "ineffective_defense_cards",
    "consumed_ineffective_nonmiracles",
    "performed_ineffective_miracles",
    "paid_mp_for_ineffective_cards",
    "full_offense_fizzles",
    "partial_offense_uses",
    "incompatible_elements",
    "ordering_or_reducer_mismatches",
    "fully_ineffective_defenses",
)
HIDDEN_REMOVAL_FIELDS: Final = (
    "affected_discard_confirmations",
    "affected_sacrifice_confirmations",
    "retained_protected_selections",
    "effective_removals_in_affected_confirmations",
    "empty_removal_confirmations",
    "retained_sun_amulets",
    "retained_dangerous_mortars",
)
HIDDEN_TARGETING_FIELDS: Final = (
    "mismatched_casts",
    "actual_chance_over_displayed_fixed",
    "actual_fixed_over_displayed_chance",
    "provisional_fallback_enemy_draws",
)
HIDDEN_TRADE_FIELDS: Final = (
    "mismatched_casts",
    "actual_exchanges",
    "actual_sales",
    "actual_buys",
    "allocation_draws",
    "sale_parcel_draws",
    "enemy_target_draws",
    "empty_sales",
    "casts_discarding_inapplicable_public_choices",
)
FULL_GAME_EFFECT_SHA256: Final = "c89243685670bf98b4fb7d9175be66de1eb94f0e8ac4681c3bb1636614edae6d"
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
ResourceCap = Literal[99, 100]
COUNTER_FIELDS: Final = ("active", "kind", "source", "target", "damage_basis", "hit_rate")
COUNTER_SNAPSHOT_FIELDS: Final = (
    "enqueued",
    "casts",
    "resolved",
    "misses",
    "dead_suppressed",
    "attack_hp_damage",
    "mp_gain",
    "cp_credit",
    "cp_spill_hp_damage",
    "filters",
    "self_illnesses",
    "queued",
)
PASSIVE_FIELDS: Final = ("displayed_kind", "displayed_value")
REVIVAL_FIELDS: Final = (
    "revivals",
    "hp_granted",
    "attack",
    "infliction",
    "payment",
    "periodic",
    "worsening",
    "utility",
    "devil",
    "exchange",
)
REMOVAL_FIELDS: Final = (
    "broom_resolutions",
    "soap_resolutions",
    "broom_removed",
    "soap_removed",
    "empty_resolutions",
    "partial_resolutions",
    "eligible_cards_seen",
    "native_draws",
)
CP_UTILITY_FIELDS: Final = ("uses", "credited_cp", "mp_spent", "capped_uses")
COMPOUND_UTILITY_FIELDS: Final = (
    "herb_uses",
    "herb_mp_gain",
    "herb_capped_uses",
    "herb_illness_applications",
    "herb_illness_hp_damage",
    "tear_uses",
    "tear_heal_outcomes",
    "tear_hp_gain",
    "tear_damage_outcomes",
    "tear_hp_damage",
)
COST_FIELDS: Final = (
    "waivers",
    "waived_mp",
    "utility_waivers",
    "attack_waivers",
    "defense_waivers",
)
UTILITY_SELECTION_FIELDS: Final = (
    "active",
    "displayed_kind",
    "displayed_value",
    "displayed_mp_cost",
)
COMPLEX_WEAPON_FIELDS: Final = (
    "active",
    "displayed_or_revealed_kind",
    "value_or_mp_coefficient",
    "strikes_remaining",
)
COMPLEX_WEAPON_SNAPSHOT_FIELDS: Final = (
    "dynamic_casts",
    "dynamic_mp_spent",
    "same_damage_casts",
    "recoil_resolutions",
    "recoil_hp_damage",
    "double_casts",
    "double_strikes_resolved",
    "double_strikes_suppressed",
)
DANGER_FIELDS: Final = ("active", "displayed_or_revealed_base_attack", "base_element")
DANGER_SNAPSHOT_FIELDS: Final = (
    "casts",
    "random_target_draws",
    "self_targets",
    "attractions",
    "attractor_owner_draws",
    "attracted_self_targets",
    "automatic_resolutions",
    "automatic_hp_damage",
)


DREAM_DEFENSE_FIELDS: Final = (
    "hat_uses",
    "dream_applications",
    "redraws",
    "redrawn_cards",
    "disguised_cards",
    "changed_displays",
    "dead_suppressed",
    "empty_redraws",
)

ATTACK_FAMILY_FIELDS: Final = (
    "enqueued",
    "started",
    "resolved",
    "suppressed",
    "missed",
    "peak_depth",
    "final_death_edges",
    "bows_consumed",
    "death_recipients",
    "death_hits",
    "death_misses",
    "death_suppressed",
    "death_hp_damage",
    "queued_pending",
    "active_kind",
    "owner_already_ticked",
)

AREA_FIELDS: Final = ("active", "displayed_or_revealed_components", "all_enemies")
AREA_SNAPSHOT_FIELDS: Final = (
    "casts",
    "miracle_components",
    "recipient_slots",
    "scheduled_shots",
    "resolved_shots",
    "suppressed_shots",
    "incoming_hp_damage",
    "fog_bypasses",
)
DISCARD_FIELDS: Final = (
    "active",
    "selected_count",
    "selection_actions",
    "max_selection_actions",
    "virtual_model_id",
)
DISCARD_SNAPSHOT_FIELDS: Final = (
    "reservations",
    "toggles",
    "cancels",
    "turns",
    "removed_cards",
    "removed_performed_miracles",
)
SACRIFICE_SNAPSHOT_FIELDS: Final = (
    *DISCARD_SNAPSHOT_FIELDS,
    "requested_replacements",
    "received_replacements",
    "suppressed_replacements",
)
GUARDIAN_STATE_FIELDS: Final = ("group_plus_one", "instance_id")
GUARDIAN_OBSERVATION_FIELDS: Final = ("seat", "present", "visible", "group_plus_one")
GUARDIAN_EFFECT_FIELDS: Final = ("active", "revealed_model", "current_source", "target")
GUARDIAN_STATISTIC_FIELDS: Final = (
    "summons",
    "replacements",
    "activation_checks",
    "activations",
    "effect_draws",
    "target_draws",
    "enqueued",
    "resolved",
    "missed",
    "suppressed",
    "damage_checks",
    "damage_departures",
    "death_departures",
    "attack_hp_damage",
    "hp_gain",
    "mp_gain",
    "cp_gain",
    "cp_spill_hp",
    "cures",
)
APOCALYPSE_FIELDS: Final = ("enabled", "active", "configured_turn_threshold")
DEVIL_FIELDS: Final = (
    "apocalypse_entries",
    "gift_checks",
    "appearances",
    "damage_events",
    "hp_loss",
    "tricksters",
    "eligible_cards",
    "removed_cards",
    "charities",
    "hp_gain",
    "mp_gain",
    "cp_gain",
    "removal_draws",
    "charity_draws",
    "queued_receipts",
    "resolved_receipts",
    "suppressed_receipts",
    "receipt_waves",
)
CONTROL_FIELDS: Final = ("seat", "present", "visible", "confusion_turns")
CONFUSION_FIELDS: Final = (
    *(f"seat{i}_remaining" for i in range(9)),
    "forced_turns",
    "action_draws",
    "card_plays",
    "discard_or_sacrifice_turns",
    "prayers",
    "idle_passes",
    "target_draws",
    "turns_consumed",
)
PHENOMENON_OBSERVATION_FIELDS: Final = ("active", "revealed_model", "current_source", "target")
PHENOMENON_SNAPSHOT_FIELDS: Final = (
    "fate_uses",
    "model_draws",
    "target_draws",
    "queued_attacks",
    "resolved_attacks",
    "missed_attacks",
    "suppressed_attacks",
    "attack_hp_loss",
    "fever_recipients",
    "fog_recipients",
    "confusion_turns_added",
    "tornado_recipients",
    "tornado_hp_decrease",
    "hp_gain",
    "cp_collected",
    "cp_granted",
    "cp_cap_loss",
    "shuffles",
    "shuffled_cards",
    "refaked_cards",
    "performed_flags_cleared",
    "guardian_recipients",
    "automatic_resolutions",
)


class FullGamePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    teams: FullGameTeamPlan = FullGameTeamPlan()
    schema_version: Literal[32] = 32
    inventory: DreamInventoryPlan
    curses: CurseDynamicsPlan
    utilities: GuardianUtilityPlan
    combat: FullGameCombatPlan
    gifts: FullGameAcquisitionPlan
    passives: FullGamePassivePlan
    removal: FullGameRemovalPlan
    economy: FullGameEconomyPlan
    costs: FullGameCostPlan
    weapons: FullGameWeaponPlan
    compound_utilities: FullGameCompoundUtilityPlan
    danger: FullGameDangerPlan
    dream_defense: FullGameDreamDefensePlan
    attack_family: FullGameAttackFamilyPlan
    area: FullGameAreaPlan
    discard: FullGameDiscardPlan
    guardians: FullGameGuardianPlan
    devils: FullGameDevilPlan
    phenomena: FullGamePhenomenonPlan
    trade: FullGameTradePlan
    effect_sha256: Literal["c89243685670bf98b4fb7d9175be66de1eb94f0e8ac4681c3bb1636614edae6d"] = (
        FULL_GAME_EFFECT_SHA256
    )
    effect_profiles: tuple[tuple[int, int, int, int], ...]
    effect_fields: tuple[str, ...] = EFFECT_FIELDS
    implemented_effect_count: Literal[15] = 15
    implemented_phases: tuple[int, ...] = (0, 1, 2, 3, 4, 6, 7, 12, 13)
    integrated_artifact_effect_count: Literal[237] = 237
    effect_codes: tuple[str, ...] = (
        "unused-zero",
        "hp",
        "mp",
        "mild-cure",
        "full-cure",
        "cp",
        "mp-and-heaven",
        "hp-or-self-damage",
    )
    scheduling: Literal[
        "ordered-card-selection-response-family-owner-tick-postturn-events-provisional"
    ] = "ordered-card-selection-response-family-owner-tick-postturn-events-provisional"
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
                + list(self.economy.profiles)
                + list(self.compound_utilities.profiles)
            )
        )
        digest = hashlib.sha256(
            json.dumps(self.effect_profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.effect_profiles != expected
            or digest != self.effect_sha256
            or self.effect_fields != EFFECT_FIELDS
            or self.implemented_phases != (0, 1, 2, 3, 4, 6, 7, 12, 13)
            or self.effect_codes
            != (
                "unused-zero",
                "hp",
                "mp",
                "mild-cure",
                "full-cure",
                "cp",
                "mp-and-heaven",
                "hp-or-self-damage",
            )
            or len(
                {
                    self.inventory.catalog_sha256,
                    self.curses.catalog_sha256,
                    self.utilities.catalog_sha256,
                    self.gifts.catalog_sha256,
                    self.combat.catalog_sha256,
                    self.passives.catalog_sha256,
                    self.removal.catalog_sha256,
                    self.economy.catalog_sha256,
                    self.costs.catalog_sha256,
                    self.weapons.catalog_sha256,
                    self.compound_utilities.catalog_sha256,
                    self.danger.catalog_sha256,
                    self.dream_defense.catalog_sha256,
                    self.attack_family.catalog_sha256,
                    self.area.catalog_sha256,
                    self.discard.catalog_sha256,
                    self.guardians.catalog_sha256,
                    self.devils.catalog_sha256,
                    self.phenomena.catalog_sha256,
                    self.trade.catalog_sha256,
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
                    self.passives.bible_client_sha256,
                    self.removal.bible_client_sha256,
                    self.economy.bible_client_sha256,
                    self.costs.bible_client_sha256,
                    self.weapons.bible_client_sha256,
                    self.compound_utilities.bible_client_sha256,
                    self.danger.bible_client_sha256,
                    self.dream_defense.bible_client_sha256,
                    self.attack_family.bible_client_sha256,
                    self.area.bible_client_sha256,
                    self.discard.bible_client_sha256,
                    self.guardians.bible_client_sha256,
                    self.devils.bible_client_sha256,
                    self.phenomena.bible_client_sha256,
                    self.trade.bible_client_sha256,
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
    economy = build_full_game_economy_plan(catalog, bible)
    compound = build_full_game_compound_utility_plan(catalog, bible)
    effects = tuple(
        sorted(
            [
                (model, resource + 1, gain, cost)
                for model, resource, gain, _, cost in utilities.profiles
            ]
            + [(model, scope + 2, 0, cost) for model, scope, _, cost in curses.cure_profiles]
            + list(economy.profiles)
            + list(compound.profiles)
        )
    )
    return FullGamePlan(
        inventory=inventory,
        curses=curses,
        utilities=utilities,
        combat=build_full_game_combat_plan(catalog, bible),
        gifts=build_full_game_acquisition_plan(catalog, bible),
        passives=build_full_game_passive_plan(catalog, bible),
        removal=build_full_game_removal_plan(catalog, bible),
        economy=economy,
        costs=build_full_game_cost_plan(catalog, bible),
        weapons=build_full_game_weapon_plan(catalog, bible),
        compound_utilities=compound,
        danger=build_full_game_danger_plan(catalog, bible),
        dream_defense=build_full_game_dream_defense_plan(catalog, bible),
        attack_family=build_full_game_attack_family_plan(catalog, bible),
        area=build_full_game_area_plan(catalog, bible),
        discard=build_full_game_discard_plan(catalog, bible),
        guardians=build_full_game_guardian_plan(catalog, bible),
        devils=build_full_game_devil_plan(catalog, bible),
        phenomena=build_full_game_phenomenon_plan(catalog, bible),
        trade=build_full_game_trade_plan(catalog, bible),
        effect_profiles=effects,
    )


class FullGameMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[32] = 32
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
    kernel_schema_version: Literal[32] = 32
    command_schema_version: Literal[1] = 1
    observation_schema_version: Literal[32] = 32
    plan: FullGamePlan
    roles: FullGameRoleManifest
    teams_enabled: Literal[True] = True
    initial_teams: tuple[TeamId, ...] = ()
    team_observation_fields: tuple[str, ...] = TEAM_FIELDS
    native_team_rules_implemented: Literal[True] = True
    native_team_victory_implemented: Literal[True] = True
    complete_team_rewards_implemented: Literal[False] = False
    resolve_hidden_removals: Literal[True] = True
    hidden_removals: Literal[
        "retain-protected-actuals-remove-eligible-only-empty-confirmation-ticks-provisional"
    ] = "retain-protected-actuals-remove-eligible-only-empty-confirmation-ticks-provisional"
    hidden_removal_snapshot_fields: tuple[str, ...] = HIDDEN_REMOVAL_FIELDS
    hidden_removal_snapshot_boundary: Literal["trusted-diagnostic-never-policy-input"] = (
        "trusted-diagnostic-never-policy-input"
    )
    resolve_hidden_components: Literal[True] = True
    hidden_components: Literal[
        "actual-affordable-cost-ordered-compatible-effects-ineffective-consumption-provisional"
    ] = "actual-affordable-cost-ordered-compatible-effects-ineffective-consumption-provisional"
    ineffective_snapshot_fields: tuple[str, ...] = INEFFECTIVE_FIELDS
    ineffective_model_ids: tuple[int, ...] = tuple(range(3, 240))
    ineffective_snapshot_boundary: Literal["trusted-diagnostic-never-policy-input"] = (
        "trusted-diagnostic-never-policy-input"
    )
    batch_size: int = Field(ge=1, le=1_000_000, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    capacity: int = Field(ge=1, le=512, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    max_turns: int = Field(ge=1, le=1_000_000_000, strict=True)
    max_decisions: int = Field(ge=1, le=1_000_000_000, strict=True)
    initial_hp: int = Field(ge=1, le=100, strict=True)
    initial_mp: int = Field(ge=0, le=100, strict=True)
    initial_cp: int = Field(ge=0, le=100, strict=True)
    resource_cap: ResourceCap = 99
    resolve_hidden_targeting: Literal[True] = True
    hidden_targeting: Literal[
        "displayed-ui-actual-chance-rng-fixed-untargeted-private-enemy-fallback-provisional"
    ] = "displayed-ui-actual-chance-rng-fixed-untargeted-private-enemy-fallback-provisional"
    hidden_targeting_snapshot_fields: tuple[str, ...] = HIDDEN_TARGETING_FIELDS
    hidden_targeting_snapshot_boundary: Literal["trusted-diagnostic-never-policy-input"] = (
        "trusted-diagnostic-never-policy-input"
    )
    complete_hidden_cross_role_resolution: Literal[False] = False
    resolve_hidden_trades: Literal[True] = True
    hidden_trades: Literal[
        "displayed-ui-actual-trade-private-missing-parameters-consumed-empty-sale-provisional"
    ] = "displayed-ui-actual-trade-private-missing-parameters-consumed-empty-sale-provisional"
    hidden_trade_snapshot_fields: tuple[str, ...] = HIDDEN_TRADE_FIELDS
    hidden_trade_snapshot_boundary: Literal["trusted-diagnostic-never-policy-input"] = (
        "trusted-diagnostic-never-policy-input"
    )
    trade_reservation_statistics: Literal[
        "displayed-reservations-actual-commits-private-cross-counters"
    ] = "displayed-reservations-actual-commits-private-cross-counters"
    resource_cap_policy: Literal["client99-default-explicit-legacy100-no-silent-setup-clipping"] = (
        "client99-default-explicit-legacy100-no-silent-setup-clipping"
    )
    acquisition_mode: AcquisitionMode = "manual"
    initial_deal_cards: int = Field(default=0, ge=0, le=9, strict=True)
    refill_on_use: bool = Field(default=False, strict=True)
    prayer_gifts: bool = Field(default=False, strict=True)
    apocalypse_after_turns: int = Field(default=0, ge=0, le=1_000_000_000, strict=True)
    apocalypse_observation_fields: tuple[str, ...] = APOCALYPSE_FIELDS
    devil_snapshot_fields: tuple[str, ...] = DEVIL_FIELDS
    devil_model_count_ids: tuple[int, ...] = tuple(range(240, 245))
    control_observation_fields: tuple[str, ...] = CONTROL_FIELDS
    confusion_snapshot_fields: tuple[str, ...] = CONFUSION_FIELDS
    phenomenon_observation_fields: tuple[str, ...] = PHENOMENON_OBSERVATION_FIELDS
    phenomenon_snapshot_fields: tuple[str, ...] = PHENOMENON_SNAPSHOT_FIELDS
    phenomenon_model_count_ids: tuple[int, ...] = tuple(range(287, 297))
    trade_choice_schema_version: Literal[2] = 2
    trade_observation_fields: tuple[str, ...] = TRADE_FIELDS
    trade_snapshot_fields: tuple[str, ...] = TRADE_STATS
    market_observation_fields: tuple[str, ...] = MARKET_FIELDS
    market_snapshot_fields: tuple[str, ...] = MARKET_STATS
    market_escrow_fields: tuple[str, ...] = MARKET_ESCROW_FIELDS
    forced_turn_policy_mask: Literal[
        "prestep-native-batch-by-one-false-for-ready-confusion-no-training-pipeline-claim"
    ] = "prestep-native-batch-by-one-false-for-ready-confusion-no-training-pipeline-claim"
    control_boundary: Literal[
        "actor-cyclic-fog-hidden-others-no-native-action-rng-or-future-effects"
    ] = "actor-cyclic-fog-hidden-others-no-native-action-rng-or-future-effects"
    devil_boundary: Literal[
        "global-apocalypse-public-episode-events-and-hidden-tickets-diagnostic-only"
    ] = "global-apocalypse-public-episode-events-and-hidden-tickets-diagnostic-only"
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
    counter_observation_fields: tuple[str, ...] = COUNTER_FIELDS
    counter_snapshot_fields: tuple[str, ...] = COUNTER_SNAPSHOT_FIELDS
    passive_observation_fields: tuple[str, ...] = PASSIVE_FIELDS
    revival_snapshot_fields: tuple[str, ...] = REVIVAL_FIELDS
    removal_snapshot_fields: tuple[str, ...] = REMOVAL_FIELDS
    cp_utility_snapshot_fields: tuple[str, ...] = CP_UTILITY_FIELDS
    compound_utility_snapshot_fields: tuple[str, ...] = COMPOUND_UTILITY_FIELDS
    compound_utility_snapshot_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    utility_damage_accounting: Literal["separate-from-incoming-attack-damage-and-owner-ticks"] = (
        "separate-from-incoming-attack-damage-and-owner-ticks"
    )
    cost_snapshot_fields: tuple[str, ...] = COST_FIELDS
    utility_selection_observation_fields: tuple[str, ...] = UTILITY_SELECTION_FIELDS
    complex_weapon_observation_fields: tuple[str, ...] = COMPLEX_WEAPON_FIELDS
    complex_weapon_snapshot_fields: tuple[str, ...] = COMPLEX_WEAPON_SNAPSHOT_FIELDS
    danger_observation_fields: tuple[str, ...] = DANGER_FIELDS
    danger_snapshot_fields: tuple[str, ...] = DANGER_SNAPSHOT_FIELDS
    dream_defense_snapshot_fields: tuple[str, ...] = DREAM_DEFENSE_FIELDS
    attack_family_schema_version: Literal[8] = 8
    guardian_state_fields: tuple[str, ...] = GUARDIAN_STATE_FIELDS
    guardian_observation_fields: tuple[str, ...] = GUARDIAN_OBSERVATION_FIELDS
    guardian_effect_observation_fields: tuple[str, ...] = GUARDIAN_EFFECT_FIELDS
    guardian_statistic_fields: tuple[str, ...] = GUARDIAN_STATISTIC_FIELDS
    guardian_model_count_ids: tuple[int, ...] = tuple(range(245, 285))
    guardian_generated_snapshot_fields: tuple[str, ...] = GUARDIAN_GENERATED_STATS
    guardian_generated_model_count_ids: tuple[int, ...] = tuple(range(3, 240))
    guardian_generated_histograms: Literal[
        "private-draws-including-suppressed-vs-dispatched-effects-separate-237-columns"
    ] = "private-draws-including-suppressed-vs-dispatched-effects-separate-237-columns"
    guardian_generated_effect_code: Literal[12] = 12
    generated_action_observation_fields: tuple[str, ...] = GENERATED_ACTION_FIELDS
    guardian_boundary: Literal[
        "actor-cyclic-fog-hidden-others-no-queued-models-rng-or-identities"
    ] = "actor-cyclic-fog-hidden-others-no-queued-models-rng-or-identities"
    guardian_statistics_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    summon_effect_code: Literal[8] = 8
    area_observation_fields: tuple[str, ...] = AREA_FIELDS
    area_snapshot_fields: tuple[str, ...] = AREA_SNAPSHOT_FIELDS
    area_observation_boundary: Literal[
        "displayed-before-cast-revealed-family-no-future-recipients-or-queue-leak"
    ] = "displayed-before-cast-revealed-family-no-future-recipients-or-queue-leak"
    area_snapshot_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    discard_observation_fields: tuple[str, ...] = DISCARD_FIELDS
    discard_snapshot_fields: tuple[str, ...] = DISCARD_SNAPSHOT_FIELDS
    sacrifice_snapshot_fields: tuple[str, ...] = SACRIFICE_SNAPSHOT_FIELDS
    sacrifice_model_count_ids: tuple[int, ...] = tuple(range(3, 240))
    sacrifice_snapshot_boundary: Literal["private-tagged-receipts-diagnostic-not-policy"] = (
        "private-tagged-receipts-diagnostic-not-policy"
    )
    sacrifice_enabled: Literal[True] = True
    max_discard_actions: Literal[64] = 64
    discard_control_choice: Literal[
        "capacity-plus-one-ready-phase7-discard-or-sacrifice-cancel"
    ] = "capacity-plus-one-ready-phase7-discard-or-sacrifice-cancel"
    discard_observation_boundary: Literal["phase7-own-displayed-selection-no-actual-role-leak"] = (
        "phase7-own-displayed-selection-no-actual-role-leak"
    )
    discard_limit: Literal["after64-only-confirm-nonempty-or-cancel-no-empty-mask"] = (
        "after64-only-confirm-nonempty-or-cancel-no-empty-mask"
    )
    attack_family_snapshot_fields: tuple[str, ...] = ATTACK_FAMILY_FIELDS
    attack_family_snapshot_boundary: Literal[
        "private-queue-and-episode-counts-diagnostic-not-policy"
    ] = "private-queue-and-episode-counts-diagnostic-not-policy"
    dream_defense_snapshot_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    danger_observation_boundary: Literal[
        "displayed-before-cast-revealed-family-no-holder-or-rng-leak"
    ] = "displayed-before-cast-revealed-family-no-holder-or-rng-leak"
    danger_snapshot_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    passive_effect_codes: tuple[str, ...] = ("sun-revival=1", "mortar-attraction=2", "dying-bow=3")
    complex_weapon_effect_codes: tuple[str, ...] = ("same-damage-recoil=10",)
    complex_weapon_boundary: Literal[
        "displayed-before-cast-revealed-family-after-no-hidden-wallet"
    ] = "displayed-before-cast-revealed-family-after-no-hidden-wallet"
    complex_weapon_snapshot_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    dynamic_preview_cost: Literal["net-miracle-cost-affordability-cast-consumes-all-own-mp"] = (
        "net-miracle-cost-affordability-cast-consumes-all-own-mp"
    )
    repeated_attack_schedule: Literal[
        "fresh-original-payload-target-after-counters-no-intermediate-gift-or-tick-provisional"
    ] = "fresh-original-payload-target-after-counters-no-intermediate-gift-or-tick-provisional"
    utility_selection_boundary: Literal["phase2-current-actor-displayed-effect-only"] = (
        "phase2-current-actor-displayed-effect-only"
    )
    utility_command_timing: Literal["reserve-then-confirm-no-resource-effect-before-confirm"] = (
        "reserve-then-confirm-no-resource-effect-before-confirm"
    )
    cost_reservation: Literal[
        "displayed-unaffordable-miracle-may-select-confirm-needs-net-cost"
    ] = "displayed-unaffordable-miracle-may-select-confirm-needs-net-cost"
    cost_waiver_boundary: Literal["episode-counts-and-saved-mp-diagnostic-not-policy"] = (
        "episode-counts-and-saved-mp-diagnostic-not-policy"
    )
    cost_limit_escape: Literal[
        "unaffordable-at-toggle-limit-cancel-or-undo-before-global-limit"
    ] = "unaffordable-at-toggle-limit-cancel-or-undo-before-global-limit"
    cp_utility_snapshot_boundary: Literal["episode-counts-diagnostic-not-policy"] = (
        "episode-counts-diagnostic-not-policy"
    )
    removal_snapshot_boundary: Literal[
        "episode-counts-no-victim-identities-diagnostic-not-policy"
    ] = "episode-counts-no-victim-identities-diagnostic-not-policy"
    removal_effect_codes: tuple[str, ...] = ("broom=8", "soap=9", "sundry-origin=3")
    removal_sampling: Literal[
        "staged-native-uniform-partial-fisher-yates-actual-eligible-pool-provisional"
    ] = "staged-native-uniform-partial-fisher-yates-actual-eligible-pool-provisional"
    removal_short_pool: Literal["min-limit-and-eligible-count-provisional"] = (
        "min-limit-and-eligible-count-provisional"
    )
    removal_receipts: Literal["no-victim-replacements-source-and-defense-use-only-provisional"] = (
        "no-victim-replacements-source-and-defense-use-only-provisional"
    )
    removal_order: Literal["after-final-defense-before-owner-tick-and-gifts-provisional"] = (
        "after-final-defense-before-owner-tick-and-gifts-provisional"
    )
    revival_snapshot_boundary: Literal["episode-cause-counters-diagnostic-not-policy"] = (
        "episode-cause-counters-diagnostic-not-policy"
    )
    passive_observation_boundary: Literal[
        "current-actor-displayed-model-only-interactive-phases"
    ] = "current-actor-displayed-model-only-interactive-phases"
    revival_trigger: Literal[
        "positive-to-zero-hp-transition-never-dead-setup-deal-idle-provisional"
    ] = "positive-to-zero-hp-transition-never-dead-setup-deal-idle-provisional"
    revival_ownership: Literal[
        "first-held-actual-owned-copy-consumed-stable-survivor-order-provisional"
    ] = "first-held-actual-owned-copy-consumed-stable-survivor-order-provisional"
    revival_order: Literal[
        "after-each-hp-zero-before-next-effect-counter-liveness-and-outcome-provisional"
    ] = "after-each-hp-zero-before-next-effect-counter-liveness-and-outcome-provisional"
    revival_state: Literal["retain-illness-curses-mp-cp-and-other-inventory-provisional"] = (
        "retain-illness-curses-mp-cp-and-other-inventory-provisional"
    )
    revival_gifts: Literal[
        "one-per-consumed-amulet-deferred-or-suppressed-like-other-uses-provisional"
    ] = "one-per-consumed-amulet-deferred-or-suppressed-like-other-uses-provisional"
    counter_snapshot_boundary: Literal[
        "episode-counters-and-private-queue-size-diagnostic-not-policy"
    ] = "episode-counters-and-private-queue-size-diagnostic-not-policy"
    generated_effect_codes: tuple[str, ...] = ("counter-mp=6", "counter-cp=7", "armor-origin=2")
    counter_trigger: Literal["actual-positive-hp-loss-living-reactors-only-provisional"] = (
        "actual-positive-hp-loss-living-reactors-only-provisional"
    )
    counter_scheduler: Literal[
        "click-order-depth-first-fixed-current-source-no-intermediate-tick-or-refill-provisional"
    ] = "click-order-depth-first-fixed-current-source-no-intermediate-tick-or-refill-provisional"
    counter_queue_bound: Literal[
        "player-count-times-capacity-consumed-rings-no-intermediate-gifts"
    ] = "player-count-times-capacity-consumed-rings-no-intermediate-gifts"
    counter_hit_rule: Literal[
        "separate-native-stream-target-dark-cloud-skips-ticket-no-redirect-reroll"
    ] = "separate-native-stream-target-dark-cloud-skips-ticket-no-redirect-reroll"
    venus_payment: Literal["shared-cp-then-mp-then-hp-waterfall-source-pinned-arithmetic"] = (
        "shared-cp-then-mp-then-hp-waterfall-source-pinned-arithmetic"
    )
    venus_credit: Literal[
        "requested-damage-credit-configured-cap-self-transfer-noop-timing-provisional"
    ] = "requested-damage-credit-configured-cap-self-transfer-noop-timing-provisional"
    neptune_credit: Literal[
        "self-target-double-actual-damage-mp-configured-cap-timing-provisional"
    ] = "self-target-double-actual-damage-mp-configured-cap-timing-provisional"
    defense_order: Literal[
        "public-click-order-undo-rebuilds-and-prunes-incompatible-suffix-source-pinned"
    ] = "public-click-order-undo-rebuilds-and-prunes-incompatible-suffix-source-pinned"
    element_filter: Literal[
        "filter-prefix-clears-element-before-defense-and-darkness-source-pinned"
    ] = "filter-prefix-clears-element-before-defense-and-darkness-source-pinned"
    self_illness: Literal[
        "living-defender-after-incoming-effects-before-counter-family-provisional"
    ] = "living-defender-after-incoming-effects-before-counter-family-provisional"
    attack_effect_snapshot_boundary: Literal["episode-effect-counters-diagnostic-not-policy"] = (
        "episode-effect-counters-diagnostic-not-policy"
    )
    damage_effect_timing: Literal[
        "positive-actual-hp-loss-before-original-owner-tick-provisional"
    ] = "positive-actual-hp-loss-before-original-owner-tick-provisional"
    absorption: Literal[
        "current-living-source-heals-post-defense-hp-loss-configured-cap-no-resurrection-provisional"
    ] = Field(
        default="current-living-source-heals-post-defense-hp-loss-configured-cap-no-resurrection-provisional"
    )
    direct_curses: Literal[
        "enemy-only-zero-atk-special-defense-only-no-effect-if-blocked-provisional"
    ] = "enemy-only-zero-atk-special-defense-only-no-effect-if-blocked-provisional"
    curse_infliction: Literal[
        "living-final-target-existing-illness-worsens-new-dream-gifts-only-provisional"
    ] = "living-final-target-existing-illness-worsens-new-dream-gifts-only-provisional"
    chance_policy: Literal[
        "no-stat-additions-adjacent-miracle-waiver-native-confirm-roll-no-defense-on-miss-provisional"
    ] = (
        "no-stat-additions-adjacent-miracle-waiver-native-confirm-roll-"
        "no-defense-on-miss-provisional"
    )
    chance_target: Literal[
        "native-uniform-living-enemies-before-roll-dark-cloud-skips-ticket-provisional"
    ] = "native-uniform-living-enemies-before-roll-dark-cloud-skips-ticket-provisional"
    hidden_target_mode: Literal[
        "mismatched-displayed-actual-target-mode-atomic-development-error"
    ] = "mismatched-displayed-actual-target-mode-atomic-development-error"
    special_selection: Literal[
        "filter-prefix-exclusive-special-with-optional-miracle-waiver-or-armor-source-pinned"
    ] = "filter-prefix-exclusive-special-with-optional-miracle-waiver-or-armor-source-pinned"
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
    attack_limit: Literal["after-64-confirm-if-affordable-otherwise-leader-cancel-provisional"] = (
        "after-64-confirm-if-affordable-otherwise-leader-cancel-provisional"
    )
    attack_undo: Literal["remove-addition-recompute-order-leader-undo-cancels-all-provisional"] = (
        "remove-addition-recompute-order-leader-undo-cancels-all-provisional"
    )
    max_defense_actions: Literal[64] = 64
    defense_limit: Literal["after-64-confirm-if-affordable-otherwise-selected-undo-provisional"] = (
        "after-64-confirm-if-affordable-otherwise-selected-undo-provisional"
    )
    target_policy: Literal["living-enemies-seat-choice-fog-samples-endogenous-provisional"] = (
        "living-enemies-seat-choice-fog-samples-endogenous-provisional"
    )
    phase_names: tuple[str, ...] = FULL_GAME_PHASES
    outcome_names: tuple[str, ...] = OUTCOMES
    randomness: Literal[
        "native-splitmix-model-disguise-illness-fog-bounce-chance-roll-target-counter-"
        "removal-utility-danger-attractor-redraw-model-disguise-ascension-"
        "guardian-summon-trigger-model-target-hit-departure-generated-model-receipt-allocation-devil-appearance-removal-charity-phenomenon-model-target-hit-shuffle-disguise-confusion-action-target-exchange-allocation-market-target-offer-disguise-purchase-sale-max16-provisional"
    ] = (
        "native-splitmix-model-disguise-illness-fog-bounce-"
        "chance-roll-target-counter-removal-utility-danger-attractor-redraw-model-disguise-ascension-"
        "guardian-summon-trigger-model-target-hit-departure-generated-model-receipt-allocation-devil-appearance-removal-charity-phenomenon-model-target-hit-shuffle-disguise-confusion-action-target-exchange-allocation-market-target-offer-disguise-purchase-sale-max16-provisional"
    )
    limits: Literal["terminal-before-turn-before-decision-limit-truncation-not-draw"] = (
        "terminal-before-turn-before-decision-limit-truncation-not-draw"
    )
    diagnostic_boundary: Literal[
        "all-true-inventories-resources-ticks-controls-not-policy-features"
    ] = "all-true-inventories-resources-ticks-controls-not-policy-features"
    observation_boundary: Literal["actor-cyclic-nine-seats-fog-hides-other-resources-status"] = (
        "actor-cyclic-nine-seats-fog-hides-other-resources-status"
    )
    choice_boundary: Literal["phase-specific-trade-menu-or-zero-slot-discard-target-seat"] = (
        "phase-specific-trade-menu-or-zero-slot-discard-target-seat"
    )
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
            or max(self.initial_hp, self.initial_mp, self.initial_cp) > self.resource_cap
            or self.hidden_targeting_snapshot_fields != HIDDEN_TARGETING_FIELDS
            or self.hidden_trade_snapshot_fields != HIDDEN_TRADE_FIELDS
            or self.roles != build_full_game_role_manifest(self.plan)
            or self.ineffective_snapshot_fields != INEFFECTIVE_FIELDS
            or self.ineffective_model_ids != tuple(range(3, 240))
            or self.hidden_removal_snapshot_fields != HIDDEN_REMOVAL_FIELDS
            or self.team_observation_fields != TEAM_FIELDS
            or (self.initial_teams and len(self.initial_teams) != self.player_count)
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
            or self.counter_observation_fields != COUNTER_FIELDS
            or self.counter_snapshot_fields != COUNTER_SNAPSHOT_FIELDS
            or self.passive_observation_fields != PASSIVE_FIELDS
            or self.revival_snapshot_fields != REVIVAL_FIELDS
            or self.compound_utility_snapshot_fields != COMPOUND_UTILITY_FIELDS
            or self.removal_snapshot_fields != REMOVAL_FIELDS
            or self.cp_utility_snapshot_fields != CP_UTILITY_FIELDS
            or self.cost_snapshot_fields != COST_FIELDS
            or self.utility_selection_observation_fields != UTILITY_SELECTION_FIELDS
            or self.complex_weapon_observation_fields != COMPLEX_WEAPON_FIELDS
            or self.complex_weapon_snapshot_fields != COMPLEX_WEAPON_SNAPSHOT_FIELDS
            or self.danger_observation_fields != DANGER_FIELDS
            or self.danger_snapshot_fields != DANGER_SNAPSHOT_FIELDS
            or self.dream_defense_snapshot_fields != DREAM_DEFENSE_FIELDS
            or self.attack_family_snapshot_fields != ATTACK_FAMILY_FIELDS
            or self.area_observation_fields != AREA_FIELDS
            or self.area_snapshot_fields != AREA_SNAPSHOT_FIELDS
            or self.discard_observation_fields != DISCARD_FIELDS
            or self.discard_snapshot_fields != DISCARD_SNAPSHOT_FIELDS
            or self.sacrifice_snapshot_fields != SACRIFICE_SNAPSHOT_FIELDS
            or self.sacrifice_model_count_ids != tuple(range(3, 240))
            or self.guardian_state_fields != GUARDIAN_STATE_FIELDS
            or self.guardian_observation_fields != GUARDIAN_OBSERVATION_FIELDS
            or self.guardian_effect_observation_fields != GUARDIAN_EFFECT_FIELDS
            or self.guardian_statistic_fields != GUARDIAN_STATISTIC_FIELDS
            or self.guardian_model_count_ids != tuple(range(245, 285))
            or self.guardian_generated_snapshot_fields != GUARDIAN_GENERATED_STATS
            or self.guardian_generated_model_count_ids != tuple(range(3, 240))
            or self.generated_action_observation_fields != GENERATED_ACTION_FIELDS
            or self.apocalypse_observation_fields != APOCALYPSE_FIELDS
            or self.devil_snapshot_fields != DEVIL_FIELDS
            or self.devil_model_count_ids != tuple(range(240, 245))
            or self.control_observation_fields != CONTROL_FIELDS
            or self.confusion_snapshot_fields != CONFUSION_FIELDS
            or self.phenomenon_observation_fields != PHENOMENON_OBSERVATION_FIELDS
            or self.phenomenon_snapshot_fields != PHENOMENON_SNAPSHOT_FIELDS
            or self.phenomenon_model_count_ids != tuple(range(287, 297))
            or self.trade_observation_fields != TRADE_FIELDS
            or self.trade_snapshot_fields != TRADE_STATS
            or self.market_observation_fields != MARKET_FIELDS
            or self.market_snapshot_fields != MARKET_STATS
            or self.market_escrow_fields != MARKET_ESCROW_FIELDS
            or self.passive_effect_codes != ("sun-revival=1", "mortar-attraction=2", "dying-bow=3")
            or self.complex_weapon_effect_codes != ("same-damage-recoil=10",)
            or self.removal_effect_codes != ("broom=8", "soap=9", "sundry-origin=3")
            or self.generated_effect_codes != ("counter-mp=6", "counter-cp=7", "armor-origin=2")
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
    apocalypse_after_turns: int = 0,
    resource_cap: ResourceCap = 99,
    teams: Sequence[int] | None = None,
) -> DevelopmentFullGameBatch:
    if teams is not None and len(teams) != player_count:
        raise ValueError("full-game initial teams must match the player count")
    plan = build_full_game_plan(
        read_api_catalog_snapshot(catalog_path),
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    metadata = FullGameMetadata(
        plan=plan,
        roles=build_full_game_role_manifest(plan),
        initial_teams=tuple(teams) if teams is not None else (0,) * player_count,
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
        apocalypse_after_turns=apocalypse_after_turns,
        resource_cap=resource_cap,
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
        getattr(native, "FULL_GAME_KERNEL_SCHEMA_VERSION", None) != 32
        or getattr(native, "FULL_GAME_COMMAND_SCHEMA_VERSION", None) != 1
        or getattr(native, "FULL_GAME_ATTACK_FAMILY_SCHEMA_VERSION", None) != 8
        or getattr(native, "FULL_GAME_OBSERVATION_SCHEMA_VERSION", None) != 32
        or getattr(native, "FULL_GAME_MAX_DEFENSE_ACTIONS", None) != 64
        or getattr(native, "FULL_GAME_MAX_ATTACK_ACTIONS", None) != 64
        or getattr(native, "FULL_GAME_MAX_DISCARD_ACTIONS", None) != 64
        or getattr(native, "FULL_GAME_MAX_TRADE_ACTIONS", None) != 64
        or getattr(native, "FULL_GAME_TRADE_CHOICE_SCHEMA_VERSION", None) != 2
        or getattr(native, "FULL_GAME_RULESET_ID", None) != FULL_GAME_RULESET_ID
        or not hasattr(native, "FullGameBatch")
    ):
        raise ProvisionalRuleUnavailableError("native full-game development contract differs")
    configured = DevelopmentFullGameBatch(
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
            np.asarray(plan.combat.defense_effect_profiles, dtype=np.int64),
            np.asarray(plan.passives.profiles, dtype=np.int64),
            np.asarray(plan.removal.profiles, dtype=np.int64),
            np.asarray(plan.costs.profiles, dtype=np.int64),
            np.asarray(plan.weapons.profiles, dtype=np.int64),
            np.asarray(plan.danger.profiles, dtype=np.int64),
            np.asarray(plan.dream_defense.profiles, dtype=np.int64),
            np.asarray(plan.attack_family.profiles, dtype=np.int64),
            np.asarray(plan.area.profiles, dtype=np.int64),
            np.asarray(plan.discard.discard_model_ids, dtype=np.int64),
            np.asarray(plan.guardians.profiles, dtype=np.int64),
            np.asarray(plan.guardians.summon_profiles, dtype=np.int64),
            np.asarray(plan.devils.profiles, dtype=np.int64),
            metadata.apocalypse_after_turns,
            np.asarray(plan.phenomena.profiles, dtype=np.int64),
            np.asarray(plan.phenomena.fate_model_ids, dtype=np.int64),
            np.asarray(plan.trade.exchange_model_ids, dtype=np.int64),
            np.asarray(plan.trade.price_profiles, dtype=np.int64),
            np.asarray(plan.guardians.generated_profiles, dtype=np.int64),
            np.asarray(plan.guardians.action_profiles, dtype=np.int64),
            metadata.sacrifice_enabled,
            metadata.resource_cap,
            metadata.resolve_hidden_targeting,
            metadata.resolve_hidden_trades,
            metadata.resolve_hidden_components,
            np.asarray(metadata.roles.model_roles, dtype=np.int64),
            metadata.resolve_hidden_removals,
            metadata.teams_enabled,
        ),
        metadata,
    )
    if any(metadata.initial_teams):
        configured.batch.seed_teams(
            np.repeat(np.arange(batch_size, dtype=np.int64), player_count),
            np.tile(np.arange(player_count, dtype=np.int64), batch_size),
            np.tile(np.asarray(metadata.initial_teams, dtype=np.int64), batch_size),
        )
    return configured


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


def full_game_policy_gradient_weights(
    configured: DevelopmentFullGameBatch,
    commands: Sequence[FullGameCommand],
) -> npt.NDArray[np.float32]:
    """Capture before step: forced turns get zero policy weight, not zero reward.

    This is a training-interface component, not a complete trainer or an
    authorization to train/promote the still-incomplete full-game environment.
    Voluntary defense choices during confusion retain their policy weight.
    """
    import numpy as np

    accepted = validate_full_game_commands(commands, full_game_decision_contexts(configured))
    masks = configured.batch.policy_gradient_masks()
    result = np.asarray([masks[c.environment, 0] for c in accepted], dtype=np.float32)
    result.flags.writeable = False
    return result


class FullGameSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    resource_cap: Literal[100] = 100
    schema_version: Literal[15] = 15
    source_kind: Literal["integrated-development-utility-cure-smoke-v1"] = (
        "integrated-development-utility-cure-smoke-v1"
    )
    ruleset_id: Literal["integrated-full-game-development-v32"] = FULL_GAME_RULESET_ID
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
    selection_commands: int = Field(ge=0, strict=True)
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
            or self.actions != self.passes + self.utilities + self.selection_commands
            or self.selection_commands != self.utilities
            or self.utilities != self.consumed_cards + self.retained_miracle_uses
            or self.actions > 2 * self.batch_size * self.max_turns
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
        resource_cap=100,
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        max_turns=max_turns,
        max_decisions=2 * max_turns + 1,
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
    for _ in range(2 * max_turns):
        episodes = batch.episode_snapshot()
        active = np.flatnonzero(np.isin(episodes[:, 3], (1, 2)))
        if not len(active):
            break
        # This historical probe scripts utility slots only. Virtual controls
        # belong to their own phase-aware probes, never a generic slot fallback.
        masks = batch.choice_masks()[active, 1 : configured.metadata.capacity + 1]
        choices = np.where(np.any(masks, axis=1), np.argmax(masks, axis=1) + 1, 0)
        choices = np.where(episodes[active, 3] == 2, 0, choices)
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
        selection_commands=batch.utility_count,
        mp_spent=batch.mp_spent,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
    )
