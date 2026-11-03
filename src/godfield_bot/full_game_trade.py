"""Pinned trade identities and provisional joined Exchange/Sell/Buy contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot

TRADE_PRICE_SHA256: Final = "2a748a50cc390df76da833a02d09a34bf857b5eb9d6b17a4c76b72e3a93e6679"
EXCHANGE_CHOICES: Final = (
    "confirm-exchange",
    "mp-plus10-from-hp",
    "mp-plus1-from-hp",
    "mp-minus1-to-hp",
    "mp-minus10-to-hp",
    "cp-plus10-from-hp",
    "cp-plus1-from-hp",
    "cp-minus1-to-hp",
    "cp-minus10-to-hp",
    "cancel-without-use-or-tick",
)
TRADE_FIELDS: Final = (
    "active",
    "mode",
    "preview_hp",
    "preview_mp",
    "preview_cp",
    "amount_edits",
    "reserved_displayed_slot",
)
TRADE_STATS: Final = (
    "exchange_reservations",
    "amount_edits",
    "cancellations",
    "exchange_commits",
    "net_hp_to_mp",
    "net_mp_to_hp",
    "net_hp_to_cp",
    "net_cp_to_hp",
    "forced_exchange_commits",
    "forced_allocation_draws",
)
MARKET_FIELDS: Final = (
    "active",
    "kind",
    "stage",
    "current_source",
    "target",
    "selected_sale_choice",
    "revealed_item_model",
    "revealed_price",
    "sale_selection_edits",
)
MARKET_STATS: Final = (
    "sell_reservations",
    "buy_reservations",
    "sale_selection_edits",
    "sell_casts",
    "buy_casts",
    "native_target_draws",
    "reflections",
    "blocks",
    "sales_resolved",
    "buy_offers",
    "empty_buy_offers",
    "purchases",
    "refusals",
    "transfers",
    "refunds",
    "cp_debit",
    "mp_debit",
    "hp_debit",
    "unpaid",
    "seller_cp_credit",
    "credit_cap_loss",
    "native_offer_draws",
    "received_disguises",
    "forced_purchase_draws",
    "overflow_evictions",
)
MARKET_ESCROW_FIELDS: Final = (
    "original_owner",
    "instance_id",
    "actual_model",
    "disguise_model",
    "performed",
    "present",
)


class FullGameTradePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = 2
    choice_schema_version: Literal[2] = 2
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    price_profiles: tuple[tuple[StrictInt, StrictInt, StrictInt], ...]
    price_profile_fields: tuple[str, ...] = ("model_id", "trade_kind", "raw_price")
    price_sha256: Literal["2a748a50cc390df76da833a02d09a34bf857b5eb9d6b17a4c76b72e3a93e6679"] = (
        TRADE_PRICE_SHA256
    )
    exchange_model_ids: tuple[StrictInt, ...] = (3,)
    implemented_trade_count: Literal[3] = 3
    pending_trade_model_ids: tuple[StrictInt, ...] = ()
    exchange_phase: Literal[6] = 6
    exchange_mode: Literal[1] = 1
    exchange_choices: tuple[str, ...] = EXCHANGE_CHOICES
    maximum_amount_edits: Literal[64] = 64
    amount_arithmetic: Literal["pinned-client-clipped-one-for-one-hp-mp-and-hp-cp"] = (
        "pinned-client-clipped-one-for-one-hp-mp-and-hp-cp"
    )
    cap: Literal["metadata-selected-client99-default-explicit-legacy100-no-silent-migration"] = (
        "metadata-selected-client99-default-explicit-legacy100-no-silent-migration"
    )
    transaction: Literal["preview-only-until-confirm-owned-card-use-once-one-owner-tick"] = (
        "preview-only-until-confirm-owned-card-use-once-one-owner-tick"
    )
    zero_hp: Literal["shared-sun-bow-before-one-tick-exchange-cause8-provisional"] = (
        "shared-sun-bow-before-one-tick-exchange-cause8-provisional"
    )
    damage: Literal["resource-conversion-not-attack-payment-or-guardian-damage"] = (
        "resource-conversion-not-attack-payment-or-guardian-damage"
    )
    confusion: Literal["bounded-uniform-final-conserved-wallet-native-not-policy-provisional"] = (
        "bounded-uniform-final-conserved-wallet-native-not-policy-provisional"
    )
    hidden_resolution: Literal["displayed-only-reservation-cross-role-confirm-atomic-error"] = (
        "displayed-only-reservation-cross-role-confirm-atomic-error"
    )
    market_family: Literal["family7-zero-atk-origin6-shared-supermirror-reactions"] = (
        "family7-zero-atk-origin6-shared-supermirror-reactions"
    )
    sell_selection: Literal["phase6-mode2-own-unused-slot-zero-confirm-capacity-plus1-cancel"] = (
        "phase6-mode2-own-unused-slot-zero-confirm-capacity-plus1-cancel"
    )
    purchase_decision: Literal["phase6-mode3-current-source-zero-refuse-one-buy"] = (
        "phase6-mode3-current-source-zero-refuse-one-buy"
    )
    purchase_offer: Literal[
        "native-uniform-current-target-unused-card-after-defense-provisional"
    ] = "native-uniform-current-target-unused-card-after-defense-provisional"
    custody: Literal["remove-owned-card-into-private-escrow-until-settle-or-return-provisional"] = (
        "remove-owned-card-into-private-escrow-until-settle-or-return-provisional"
    )
    transfer: Literal[
        "fresh-id-receiver-dream-refake-local-overflow-no-replacement-gift-provisional"
    ] = "fresh-id-receiver-dream-refake-local-overflow-no-replacement-gift-provisional"
    market_payment: Literal[
        "receive-then-shared-cp-mp-hp-debit-credit-price-configured-cap-before-sun-bow-provisional"
    ] = "receive-then-shared-cp-mp-hp-debit-credit-price-configured-cap-before-sun-bow-provisional"
    refunds: Literal[
        "same-original-id-disguise-unused-card-tail-return-no-payment-or-gift-provisional"
    ] = "same-original-id-disguise-unused-card-tail-return-no-payment-or-gift-provisional"
    forced_market: Literal[
        "native-sale-target-and-original-buyer-purchase-reflector-voluntary-provisional"
    ] = "native-sale-target-and-original-buyer-purchase-reflector-voluntary-provisional"
    sell_buy_item_transfers_implemented: Literal[True] = True
    official_market_timing_and_distribution_verified: Literal[False] = False
    complete_training_pipeline_implemented: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGameTradePlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or self.price_profile_fields != ("model_id", "trade_kind", "raw_price")
            or len(self.price_profiles) != 237
            or hashlib.sha256(
                json.dumps(self.price_profiles, separators=(",", ":")).encode()
            ).hexdigest()
            != self.price_sha256
            or self.exchange_model_ids != (3,)
            or self.pending_trade_model_ids != ()
            or self.exchange_choices != EXCHANGE_CHOICES
        ):
            raise ValueError("full-game trade source or numeric-choice contract differs")
        return self


def build_full_game_trade_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameTradePlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    raw = {item.model_id: item.raw for item in catalog.items}
    for model, name in ((3, "Exchange"), (4, "Sell"), (5, "Buy")):
        if raw.get(model) != {
            "imageName": name.lower(),
            "category": "trade",
            "ability": name.lower(),
            "price": 5,
            "giftRate": 20,
            "name": name,
        }:
            raise ValueError("full-game trade API identities differ")
    # These three cards have no Bible catalog entries. Do not manufacture them.
    # The catalog pins numbers, not server selection, timing or ownership rules.
    profiles = tuple(
        (
            item.model_id,
            item.model_id - 2 if item.model_id in (3, 4, 5) else 0,
            item.raw.get("price", 0),
        )
        for item in catalog.items
        if 3 <= item.model_id <= 239
    )
    return FullGameTradePlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        price_profiles=profiles,
    )
