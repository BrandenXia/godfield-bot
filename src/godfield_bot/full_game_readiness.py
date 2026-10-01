"""Fail-closed integration audit, distinct from native artifact inclusion."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.guardian_rollout import GuardianRolloutArena, GuardianRolloutConfig
from godfield_bot.guardian_utility import GuardianUtilityTurnMetadata

Integration = Literal["inventory-usable", "opening-only", "component-only", "not-integrated"]


class FullGameArtifactIntegration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_id: int = Field(gt=0, strict=True)
    category: str = Field(min_length=1)
    asset: str = Field(min_length=1)
    integration: Integration


class FullGameWorkflowGap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_id: str = Field(min_length=1)
    status: Literal["partial", "absent"]
    current_behavior: str = Field(min_length=1)
    missing_behavior: str = Field(min_length=1)
    source_files: tuple[str, ...] = Field(min_length=1)


class FullGameReadinessReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    source_kind: Literal["pinned-guardian-full-game-integration-audit-v1"] = (
        "pinned-guardian-full-game-integration-audit-v1"
    )
    scope: Literal["inventory-and-workflow-integration-not-behavioral-fidelity"] = (
        "inventory-and-workflow-integration-not-behavioral-fidelity"
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    curriculum_id: str
    observation_schema_id: str
    action_count: int = Field(gt=0, strict=True)
    artifact_count: int = Field(gt=0, strict=True)
    inventory_model_count: int = Field(ge=0, strict=True)
    opening_only_count: int = Field(ge=0, strict=True)
    component_only_count: int = Field(ge=0, strict=True)
    not_integrated_count: int = Field(ge=0, strict=True)
    artifacts: tuple[FullGameArtifactIntegration, ...]
    workflow_gaps: tuple[FullGameWorkflowGap, ...] = Field(min_length=1)
    rollout_player_counts: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9)
    neural_training_player_counts: tuple[Literal[2], ...] = (2,)
    local_duel_subset_training_ready: Literal[True] = True
    official_fidelity_verified: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    # This schema audits the current subset, not a future engine's acceptance.
    # Catalog inclusion alone cannot bypass its unresolved integration gaps.
    full_game_training_ready: Literal[False] = False

    @model_validator(mode="after")
    def complete_accounting(self) -> FullGameReadinessReport:
        counts = Counter(item.integration for item in self.artifacts)
        if (
            len(self.artifacts) != self.artifact_count
            or len({item.model_id for item in self.artifacts}) != self.artifact_count
            or len({(item.category, item.asset) for item in self.artifacts}) != self.artifact_count
            or sum(
                (
                    self.inventory_model_count,
                    self.opening_only_count,
                    self.component_only_count,
                    self.not_integrated_count,
                )
            )
            != self.artifact_count
            or counts["inventory-usable"] != self.inventory_model_count
            or counts["opening-only"] != self.opening_only_count
            or counts["component-only"] != self.component_only_count
            or counts["not-integrated"] != self.not_integrated_count
            or len({gap.workflow_id for gap in self.workflow_gaps}) != len(self.workflow_gaps)
        ):
            raise ValueError("full-game audit must account for every artifact and unique workflow")
        return self


def _guardian_workflow_gaps() -> tuple[FullGameWorkflowGap, ...]:
    """Reviewed behavior of the existing guardian adapter, not future capabilities."""
    rows: tuple[tuple[str, Literal["partial", "absent"], str, str, tuple[str, ...]], ...] = (
        (
            "acquisition-overflow",
            "partial",
            "Balanced synthetic nine-card deal and subset refill.",
            "Official initial distribution, gift timing, 18-slot overflow and compaction.",
            ("src/godfield_bot/guardian_rollout.py", "src/godfield_bot/guardian_utility_refill.py"),
        ),
        (
            "offensive-combinations",
            "partial",
            "One fixed-value card and one living enemy target.",
            "Multiple offensive cards, boosters, area/random attacks and special weapon effects.",
            ("native/godfield_sim/src/guardian_turn_batch.cpp",),
        ),
        (
            "special-defense",
            "partial",
            "Ordinary armor combinations, Wall and one Turbulence bounce.",
            "Special defenses, reflection, counters, cost cuts and complete redirection chains.",
            ("native/godfield_sim/src/guardian_turn_batch.cpp",),
        ),
        (
            "utility-targeting-costs",
            "partial",
            "Eight self-only HP/MP inventory utilities.",
            "All utilities, official recipient selection, variable costs and reusable-card state.",
            (
                "src/godfield_bot/guardian_utility.py",
                "native/godfield_sim/src/guardian_utility_turn_batch.cpp",
            ),
        ),
        (
            "curse-turn-dynamics",
            "partial",
            "Guardian effects set some curse bits; portable disease/cure kernel is not integrated.",
            "Integrated illness/hell, fog/flash, confusion, dream, redraw, cures and timing.",
            (
                "native/godfield_sim/src/guardian_combat_batch.cpp",
                "native/godfield_sim/src/curse_dynamics_batch.cpp",
                "src/godfield_bot/curse_dynamics.py",
                "src/godfield_bot/guardian_rollout.py",
            ),
        ),
        (
            "guardian-lifecycle-timing",
            "partial",
            "One optional Mars effect at episode opening.",
            "Summoning, regular activation, ownership, expiry and all guardian effects.",
            (
                "native/godfield_sim/src/guardian_lifecycle_batch.cpp",
                "src/godfield_bot/guardian_rollout.py",
            ),
        ),
        (
            "devils",
            "absent",
            "No devil events in arena episodes.",
            "Damage, removal, resource events, target selection and official event scheduling.",
            ("src/godfield_bot/guardian_rollout.py",),
        ),
        (
            "phenomena",
            "absent",
            "No global phenomenon events in arena episodes.",
            "All global events, randomness, inventory redistribution and guardian interactions.",
            ("src/godfield_bot/guardian_rollout.py",),
        ),
        (
            "economy",
            "absent",
            "CP is public state but has no legal economic actions.",
            "Buy/sell, gifts/trades, HP/MP exchange, affordability and merchant responses.",
            ("src/godfield_bot/guardian_rollout.py",),
        ),
        (
            "removal-revival",
            "partial",
            "Opt-in provisional single-card discard/replacement.",
            "Broom, Soap, sacrifice, revive, target/selection legality and inventory lifecycle.",
            ("native/godfield_sim/src/guardian_discard_turn_batch.cpp",),
        ),
        (
            "apocalypse-terminal-flow",
            "partial",
            "Last living seat wins; existing absorbing limits truncate.",
            "Apocalypse timing/escalation, official victory/draw rules and terminal interactions.",
            ("native/godfield_sim/src/guardian_turn_batch.cpp",),
        ),
        (
            "teams-multiplayer-learning",
            "partial",
            "2-9 free-for-all rollout seats; neural learning is duel-only.",
            "Team ownership, targets/rewards, teammates, elimination and multiplayer learning.",
            ("src/godfield_bot/guardian_rollout.py", "src/godfield_bot/guardian_training.py"),
        ),
        (
            "full-action-observation-contract",
            "partial",
            "Versioned 18-slot 48-action subset projection.",
            "All phases, legal choices, observable statuses/history and checkpoint transfer.",
            ("src/godfield_bot/guardian_rollout.py", "src/godfield_bot/guardian_neural.py"),
        ),
        (
            "full-game-validation",
            "absent",
            "Subset tests and diagnostics; official evidence remains gated.",
            "Full interactions, replay, learning/liveness tests and official parity.",
            ("src/godfield_bot/guardian_training.py", "src/godfield_bot/simulation_diagnostics.py"),
        ),
    )
    return tuple(
        FullGameWorkflowGap(
            workflow_id=key,
            status=status,
            current_behavior=current,
            missing_behavior=missing,
            source_files=files,
        )
        for key, status, current, missing, files in rows
    )


def build_full_game_readiness_report(
    *, catalog_path: Path, bible_path: Path
) -> FullGameReadinessReport:
    """Fresh local metadata only; no network, training, account or live-policy writes."""
    catalog = read_api_catalog_snapshot(catalog_path)
    bible = BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8"))
    game = GuardianRolloutArena(
        catalog_path=catalog_path,
        bible_path=bible_path,
        config=GuardianRolloutConfig(
            batch_size=2,
            inventory_utilities=True,
            inventory_discards=True,
            refill="weighted-discard-consumption-v1",
        ),
    )
    native = game.metadata.base_native
    if not isinstance(native, GuardianUtilityTurnMetadata):
        raise ValueError("full-game audit requires the reviewed inventory utility subset")
    inventory = set(
        native.defense_model_ids
        + native.attack_weapon_model_ids
        + native.attack_miracle_model_ids
        + tuple(row[0] for row in native.utility_plan.profiles)
    )
    components = set(native.supported_effect_model_ids)
    expected = {
        (category, item.asset) for category, group in bible.catalog.items() for item in group.items
    }
    selected = [item for item in catalog.items if item.raw.get("category") in bible.catalog]
    actual = {(item.raw.get("category"), item.raw.get("imageName")) for item in selected}
    if len(selected) != len(expected) or actual != expected:
        raise ValueError(
            "full-game audit requires exactly matching API and Bible artifact catalogs"
        )
    selected_ids = {item.model_id for item in selected}
    if (
        inventory & components
        or not inventory <= selected_ids
        or not components <= selected_ids
        or len(inventory) != native.total_inventory_models
    ):
        raise ValueError("full-game audit native inventory/component identities are inconsistent")
    opening = {
        item.model_id
        for item in selected
        if item.raw.get("category") == "guardians" and item.raw.get("guardian") == "mars"
    }
    if (
        len(opening) != 5
        or not opening <= components
        or game.metadata.guardian_policy != "optional-one-mars-effect-at-episode-opening"
    ):
        raise ValueError(
            "full-game audit opening identity differs from the reviewed guardian policy"
        )
    artifacts = tuple(
        FullGameArtifactIntegration(
            model_id=item.model_id,
            category=item.raw["category"],
            asset=item.raw["imageName"],
            integration="inventory-usable"
            if item.model_id in inventory
            else "opening-only"
            if item.model_id in opening
            else "component-only"
            if item.model_id in components
            else "not-integrated",
        )
        for item in selected
    )
    return FullGameReadinessReport(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        curriculum_id=game.metadata.curriculum_id,
        observation_schema_id=game.metadata.observation_schema_id,
        action_count=game.metadata.action_count,
        artifact_count=len(artifacts),
        inventory_model_count=len(inventory),
        opening_only_count=len(opening),
        component_only_count=len(components - opening),
        not_integrated_count=len(selected_ids - inventory - components),
        artifacts=artifacts,
        workflow_gaps=_guardian_workflow_gaps(),
    )
