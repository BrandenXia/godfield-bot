"""Source-pinned ordered inventory component, not a full-game rollout contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot, read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

if TYPE_CHECKING:
    from godfield_sim import DreamInventoryBatch

DREAM_INVENTORY_RULESET_ID: Final = "caller-driven-ordered-dream-inventory-provisional-v1"
INVENTORY_PROFILE_SHA256: Final = "98c3b89fb319be8b16990e10a0180f0d353ba78c75081da6fc076503eb87f78d"
INVENTORY_CATEGORIES: Final = (
    ("weapons", 1),
    ("armor", 2),
    ("sundries", 3),
    ("miracles", 4),
    ("trade", 5),
)
INVENTORY_STATE_FIELDS: Final = ("instance_id", "actual_model_id", "fake_model_id", "used")
ACTOR_HAND_FIELDS: Final = ("instance_id", "displayed_model_id", "used")
_MIRACLE_NOTES = (
    "Miracles costs MP but can be used repeatedly.",
    "Performed miracles are not subject to Sell, Buy, and Nocturnal Broom.",
)


class DreamInventoryPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["caller-driven-ordered-dream-inventory-provisional-v1"] = (
        DREAM_INVENTORY_RULESET_ID
    )
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["98c3b89fb319be8b16990e10a0180f0d353ba78c75081da6fc076503eb87f78d"] = (
        INVENTORY_PROFILE_SHA256
    )
    profiles: tuple[tuple[int, int], ...]
    profile_fields: tuple[str, ...] = ("model_id", "category")
    categories: tuple[tuple[str, int], ...] = INVENTORY_CATEGORIES
    handable_model_count: Literal[237] = 237
    artifact_handable_model_count: Literal[234] = 234
    held_trade_model_count: Literal[3] = 3
    excluded_event_models: Literal[57] = 57
    excluded_virtual_controls: Literal[2] = 2
    disguise_percent: Literal[50] = 50
    dream_bit: Literal[2] = 2
    fake_sampling: Literal["ascending-same-category-pool-caller-rank-ticket-provisional"] = (
        "ascending-same-category-pool-caller-rank-ticket-provisional"
    )
    disguise_eligibility: Literal["all-handable-models-provisional-generalization"] = (
        "all-handable-models-provisional-generalization"
    )
    receipt_rule: Literal["only-new-receipts-not-retroactive-caller-status-and-tickets"] = (
        "only-new-receipts-not-retroactive-caller-status-and-tickets"
    )
    reusable_rule: Literal[
        "all-miracles-mark-used-preserve-id-fake-and-move-to-tail-provisional"
    ] = "all-miracles-mark-used-preserve-id-fake-and-move-to-tail-provisional"
    ordinary_rule: Literal["all-nonmiracles-consumed-on-caller-confirmed-use-provisional"] = (
        "all-nonmiracles-consumed-on-caller-confirmed-use-provisional"
    )
    source_evidence: Literal["pinned-help-catalog-and-bounded-dream-flame-traces"] = (
        "pinned-help-catalog-and-bounded-dream-flame-traces"
    )
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_profiles(self) -> DreamInventoryPlan:
        digest = hashlib.sha256(
            json.dumps(self.profiles, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or digest != self.profile_sha256
            or self.profile_fields != ("model_id", "category")
            or self.categories != INVENTORY_CATEGORIES
        ):
            raise ValueError("dream inventory requires the pinned category profiles")
        return self


def build_dream_inventory_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> DreamInventoryPlan:
    # Recheck integrity even if a caller obtained models via unchecked model_copy.
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    categories = dict(INVENTORY_CATEGORIES)
    if (
        bible.catalog.get("miracles") is None
        or bible.catalog["miracles"].notes != _MIRACLE_NOTES
        or not any(
            bible.reference_sections.get("curses", ())[offset : offset + 3]
            == ("Dream", "Given artifacts look", "false by 50% chance")
            for offset in range(len(bible.reference_sections.get("curses", ())))
        )
    ):
        raise ValueError("pinned Dream or reusable-miracle help differs")
    for name in ("weapons", "armor", "sundries", "miracles"):
        if name not in bible.catalog or {item.asset for item in bible.catalog[name].items} != {
            item.raw.get("imageName") for item in catalog.items if item.raw.get("category") == name
        }:
            raise ValueError("dream inventory Bible/API category assets differ")
    profiles = tuple(
        (item.model_id, categories[item.raw["category"]])
        for item in catalog.items
        if item.raw.get("category") in categories and item.model_id not in (1, 2)
    )
    return DreamInventoryPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        profiles=profiles,
    )


class DreamInventoryMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    plan: DreamInventoryPlan
    batch_size: int = Field(ge=1, le=1_000_000, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    capacity: int = Field(ge=1, le=512, strict=True)
    capacity_meaning: Literal["storage-bound-not-official-hand-limit-or-neural-layout"] = (
        "storage-bound-not-official-hand-limit-or-neural-layout"
    )
    state_fields: tuple[str, ...] = INVENTORY_STATE_FIELDS
    actor_hand_fields: tuple[str, ...] = ACTOR_HAND_FIELDS
    snapshot_boundary: Literal["trusted-diagnostic-all-players-actual-and-fake-identities"] = (
        "trusted-diagnostic-all-players-actual-and-fake-identities"
    )
    actor_boundary: Literal["own-displayed-hand-only-no-true-id-fake-flag-or-opponent-items"] = (
        "own-displayed-hand-only-no-true-id-fake-flag-or-opponent-items"
    )
    padding: Literal["packed-occupied-prefix-all-zero-tail-instance-zero-empty"] = (
        "packed-occupied-prefix-all-zero-tail-instance-zero-empty"
    )
    multiple_selections: Literal["stable-survivors-then-retained-miracles-in-input-order"] = (
        "stable-survivors-then-retained-miracles-in-input-order"
    )
    explicit_removal: Literal["caller-selected-exact-rows-no-effect-or-cardinality-inference"] = (
        "caller-selected-exact-rows-no-effect-or-cardinality-inference"
    )
    restore_displays: Literal["caller-invokes-after-dream-ends-no-curse-state-mutation"] = (
        "caller-invokes-after-dream-ends-no-curse-state-mutation"
    )
    identity_scope: Literal["unique-instance-within-environment-caller-reset-epoch-required"] = (
        "unique-instance-within-environment-caller-reset-epoch-required"
    )
    execution_context: Literal[
        "caller-phase-and-reset-epochs-not-exactly-once-action-execution"
    ] = "caller-phase-and-reset-epochs-not-exactly-once-action-execution"
    mask_and_ticket_consumer: Literal["trusted-scheduler-not-policy-feature"] = (
        "trusted-scheduler-not-policy-feature"
    )
    instance_id_role: Literal["selection-handle-not-numeric-policy-feature"] = (
        "selection-handle-not-numeric-policy-feature"
    )
    native_operations_atomic: Literal[True] = True
    item_registration_is_battle_effect_coverage: Literal[False] = False
    gift_timing_distribution_and_overflow_implemented: Literal[False] = False
    item_legality_costs_and_battle_effects_implemented: Literal[False] = False
    transfer_economy_and_removal_rules_implemented: Literal[False] = False
    complete_policy_projection_implemented: Literal[False] = False
    action_observation_checkpoint_compatible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def bounded_and_pinned_fields(self) -> DreamInventoryMetadata:
        if (
            self.batch_size * self.player_count * self.capacity > 2_000_000
            or self.state_fields != INVENTORY_STATE_FIELDS
            or self.actor_hand_fields != ACTOR_HAND_FIELDS
        ):
            raise ValueError("dream inventory storage or field contract differs")
        return self


@dataclass(frozen=True)
class ProvisionalDreamInventoryBatch:
    batch: DreamInventoryBatch
    metadata: DreamInventoryMetadata


def create_provisional_dream_inventory_batch(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int,
    player_count: int = 2,
    capacity: int = 512,
) -> ProvisionalDreamInventoryBatch:
    plan = build_dream_inventory_plan(
        read_api_catalog_snapshot(catalog_path),
        BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8")),
    )
    metadata = DreamInventoryMetadata(
        plan=plan, batch_size=batch_size, player_count=player_count, capacity=capacity
    )
    try:
        import godfield_sim as native
        import numpy as np
    except (ImportError, OSError):
        raise ProvisionalRuleUnavailableError(
            "dream inventory requires the native simulation extra"
        ) from None
    if (
        getattr(native, "DREAM_INVENTORY_SCHEMA_VERSION", None) != 1
        or getattr(native, "DREAM_INVENTORY_RULESET_ID", None) != DREAM_INVENTORY_RULESET_ID
        or not hasattr(native, "DreamInventoryBatch")
    ):
        raise ProvisionalRuleUnavailableError("native dream inventory contract differs")
    return ProvisionalDreamInventoryBatch(
        native.DreamInventoryBatch(
            batch_size, player_count, np.asarray(plan.profiles, dtype=np.int64), capacity
        ),
        metadata,
    )
