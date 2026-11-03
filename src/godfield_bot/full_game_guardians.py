"""Pinned standard guardian effects and ten-outcome summon ownership contract."""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.acquisition_probe import (
    ACQUISITION_REVIEWED_CATALOG_SHA256,
    ACQUISITION_REVIEWED_CLIENT_SHA256,
)
from godfield_bot.api_catalog import ApiCatalogSnapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.dream_inventory import build_dream_inventory_plan
from godfield_bot.elements import COMBAT_ELEMENT_IDS
from godfield_bot.full_game_acquisition import build_full_game_acquisition_plan

FULL_GAME_GUARDIAN_SHA256: Final = (
    "d5275fde52d4fb421dd387e65a8866d4535216263a534e91d4af595dc468c471"
)
FULL_GAME_SUMMON_SHA256: Final = "3761e8f41af915bacf6f6db4e8874bea0ec6c95c0d1960e762bbd1cb6f0ff606"
GUARDIAN_GROUPS: Final = (
    "mars",
    "mercury",
    "jupiter",
    "saturn",
    "uranus",
    "pluto",
    "neptune",
    "venus",
    "earth",
    "moon",
)
GUARDIAN_NOTES: Final = (
    "Earth God uses trade, weapons, armor, and sundries.",
    "Moon God uses miracles.",
    "Guardians act after enemy's turn by 25% chance.",
    "Guardians leave by 10% chance when damaged.",
)
GUARDIAN_GENERATED_SHA256: Final = (
    "f3dba9f996e4c41eb61a4e0c16630713974e5d75c422d25038b12a0ee61bc3f8"
)
GUARDIAN_GENERATED_FIELDS: Final = ("group", "model_id", "category", "gift_weight")
GUARDIAN_ACTION_SHA256: Final = "de73db352861dc25b0f091b0e34b0715fb3e2cad04fba19deb4ea82a486d020f"
GUARDIAN_ACTION_FIELDS: Final = ("model_id", "route")
# Independent fixed ID ledger: the source builder below re-derives each route
# from the pinned client's leader predicate and catalog abilities.
GUARDIAN_ACTION_PROFILES: Final = tuple(
    (
        model,
        model
        if model <= 5
        else 6
        if 113 <= model <= 190 or model in (203, 204, 208, 209)
        else 7
        if 231 <= model <= 234
        else 2
        if 191 <= model <= 202 or model == 207 or 235 <= model <= 239
        else 1,
    )
    for model in range(3, 240)
)
GENERATED_ACTION_FIELDS: Final = (
    "active",
    "producer_model",
    "generated_model",
    "virtual_leader",
    "current_source",
    "target",
)
GUARDIAN_GENERATED_STATS: Final = (
    "earth_casts",
    "model_draws",
    "receipts",
    "disguises",
    "overflow_evictions",
    "blocked",
    "suppressed",
    "moon_casts",
    "direct_attacks",
    "utilities",
    "exchanges",
    "sells",
    "buys",
    "drop_fallbacks",
    "moon_fallbacks",
    "attack_entries",
    "attack_resolutions",
    "attack_suppressions",
    "attack_hp_loss",
    "attack_misses",
    "special_mp_debit",
    "generated_parcels",
    "retired_parcels",
)
GUARDIAN_PROFILE_FIELDS: Final = (
    "model_id",
    "group",
    "weight",
    "attack",
    "element",
    "hit_rate",
    "kind",
    "value",
    "curse_mask",
    "origin",
)


class FullGameGuardianPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[3] = 3
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bible_client_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: Literal["d5275fde52d4fb421dd387e65a8866d4535216263a534e91d4af595dc468c471"] = (
        FULL_GAME_GUARDIAN_SHA256
    )
    summon_profile_sha256: Literal[
        "3761e8f41af915bacf6f6db4e8874bea0ec6c95c0d1960e762bbd1cb6f0ff606"
    ] = FULL_GAME_SUMMON_SHA256
    bible_profiles_sha256: Literal[
        "0febd23f793202ac6e5ec96e5cb7721dc902341d51075ee9effe7c0088142ae5"
    ] = "0febd23f793202ac6e5ec96e5cb7721dc902341d51075ee9effe7c0088142ae5"
    profiles: tuple[tuple[int, int, int, int, int, int, int, int, int, int], ...]
    generated_profiles: tuple[tuple[int, int, int, int], ...]
    action_profiles: tuple[tuple[int, int], ...]
    action_fields: tuple[str, ...] = GUARDIAN_ACTION_FIELDS
    action_sha256: Literal["de73db352861dc25b0f091b0e34b0715fb3e2cad04fba19deb4ea82a486d020f"] = (
        GUARDIAN_ACTION_SHA256
    )
    construction: Literal["client-leader-direct-else-drop-or-full-moon-blade-provisional"] = (
        "client-leader-direct-else-drop-or-full-moon-blade-provisional"
    )
    action_routes: tuple[str, ...] = (
        "unused-zero",
        "direct-attack",
        "direct-utility",
        "exchange",
        "sell",
        "buy",
        "drop-receipt",
        "full-moon-blade-addition",
    )
    earth_direct_models: Literal[125] = 125
    earth_fallback_models: Literal[82] = 82
    moon_direct_models: Literal[26] = 26
    moon_fallback_models: Literal[4] = 4
    moon_fallback: Literal[
        "blade10-ordered-boosts-defensive-additions-no-offensive-ability-provisional"
    ] = "blade10-ordered-boosts-defensive-additions-no-offensive-ability-provisional"
    generated_exchange: Literal[
        "native-uniform-configured-cap-wallet-allocation-no-held-use-provisional"
    ] = "native-uniform-configured-cap-wallet-allocation-no-held-use-provisional"
    generated_sell: Literal[
        "second-earth-weighted-generated-parcel-custody-minus2-retire-not-refund-provisional"
    ] = "second-earth-weighted-generated-parcel-custody-minus2-retire-not-refund-provisional"
    generated_buy: Literal[
        "native-original-buyer-coin-voluntary-reflected-current-buyer-provisional"
    ] = "native-original-buyer-coin-voluntary-reflected-current-buyer-provisional"
    generated_fields: tuple[str, ...] = GUARDIAN_GENERATED_FIELDS
    generated_sha256: Literal[
        "f3dba9f996e4c41eb61a4e0c16630713974e5d75c422d25038b12a0ee61bc3f8"
    ] = GUARDIAN_GENERATED_SHA256
    generated_sampling: Literal[
        "pinned-category-filtered-gift-weights-provisional-not-server-probabilities"
    ] = "pinned-category-filtered-gift-weights-provisional-not-server-probabilities"
    earth_pool_models: Literal[207] = 207
    earth_pool_weight: Literal[470] = 470
    moon_pool_models: Literal[30] = 30
    moon_pool_weight: Literal[30] = 30
    earth_drop: Literal[
        "nonleader-artifact-native-enemy-super-mirror-response-fresh-receipt-provisional"
    ] = "nonleader-artifact-native-enemy-super-mirror-response-fresh-receipt-provisional"
    earth_receipt: Literal[
        "receiver-dream-and-explicit-cap-no-use-cost-replacement-or-devil-trigger-provisional"
    ] = "receiver-dream-and-explicit-cap-no-use-cost-replacement-or-devil-trigger-provisional"
    joined_guardian_models: Literal[42] = 42
    summon_profiles: tuple[tuple[int, int], ...] = ((201, 0), (239, 15))
    profile_fields: tuple[str, ...] = GUARDIAN_PROFILE_FIELDS
    group_names: tuple[str, ...] = GUARDIAN_GROUPS
    notes: tuple[str, ...] = GUARDIAN_NOTES
    effect_count: Literal[40] = 40
    ownership: Literal["one-guardian-per-seat-replace-uniform-all10-groups-provisional"] = (
        "one-guardian-per-seat-replace-uniform-all10-groups-provisional"
    )
    trigger: Literal[
        "once-post-original-tick-other-living-seats-ascending25-no-recursion-provisional"
    ] = "once-post-original-tick-other-living-seats-ascending25-no-recursion-provisional"
    departure: Literal["each-positive-hp-debit-after-sun10-final-death-clears-provisional"] = (
        "each-positive-hp-debit-after-sun10-final-death-clears-provisional"
    )
    targeting: Literal["native-uniform-living-enemy-independent-fog-provisional"] = (
        "native-uniform-living-enemy-independent-fog-provisional"
    )
    currencies: Literal[
        "configured-cap-shared-fine-payment-waterfall-requested-credit-provisional"
    ] = "configured-cap-shared-fine-payment-waterfall-requested-credit-provisional"
    scheduler: Literal[
        "shared-family4-depth-first-before-gifts-endings-and-next-owner-provisional"
    ] = "shared-family4-depth-first-before-gifts-endings-and-next-owner-provisional"
    unsupported_special_model_ids: tuple[int, ...] = ()
    special_activation: Literal["all-models-provisional-direct-and-virtual-actions-joined"] = (
        "all-models-provisional-direct-and-virtual-actions-joined"
    )
    complete_guardian_effects_implemented: Literal[False] = False
    official_compound_timing_verified: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_contract(self) -> FullGameGuardianPlan:
        if (
            self.catalog_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
            or self.bible_client_sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
            or len(self.profiles) != 40
            or self.profile_fields != GUARDIAN_PROFILE_FIELDS
            or self.group_names != GUARDIAN_GROUPS
            or self.notes != GUARDIAN_NOTES
            or self.unsupported_special_model_ids != ()
            or self.action_fields != GUARDIAN_ACTION_FIELDS
            or self.action_profiles != GUARDIAN_ACTION_PROFILES
            or self.action_routes
            != (
                "unused-zero",
                "direct-attack",
                "direct-utility",
                "exchange",
                "sell",
                "buy",
                "drop-receipt",
                "full-moon-blade-addition",
            )
            or hashlib.sha256(
                json.dumps(self.action_profiles, separators=(",", ":")).encode()
            ).hexdigest()
            != self.action_sha256
            or self.generated_fields != GUARDIAN_GENERATED_FIELDS
            or len(self.generated_profiles) != 237
            or hashlib.sha256(
                json.dumps(self.generated_profiles, separators=(",", ":")).encode()
            ).hexdigest()
            != self.generated_sha256
            or hashlib.sha256(json.dumps(self.profiles, separators=(",", ":")).encode()).hexdigest()
            != self.profile_sha256
            or hashlib.sha256(
                json.dumps(self.summon_profiles, separators=(",", ":")).encode()
            ).hexdigest()
            != self.summon_profile_sha256
        ):
            raise ValueError("full-game guardian source or scheduler contract differs")
        return self


def build_full_game_guardian_plan(
    catalog: ApiCatalogSnapshot, bible: BibleSnapshot
) -> FullGameGuardianPlan:
    catalog = ApiCatalogSnapshot.model_validate(catalog.model_dump())
    bible = BibleSnapshot.model_validate(bible.model_dump())
    if (
        catalog.content_sha256 != ACQUISITION_REVIEWED_CATALOG_SHA256
        or bible.client.sha256 != ACQUISITION_REVIEWED_CLIENT_SHA256
    ):
        raise ValueError("full-game guardians require the pinned complete sources")
    element_ids = {str(name): value for name, value in COMBAT_ELEMENT_IDS.items()}
    guardians = bible.catalog.get("guardians")
    if guardians is None or guardians.notes != GUARDIAN_NOTES or len(guardians.items) != 42:
        raise ValueError("guardian Bible notes or complete source scope differ")
    bible_rows = tuple(
        (r.asset, r.image_path, r.detail, r.element_image_paths) for r in guardians.items
    )
    if hashlib.sha256(json.dumps(bible_rows, separators=(",", ":")).encode()).hexdigest() != (
        "0febd23f793202ac6e5ec96e5cb7721dc902341d51075ee9effe7c0088142ae5"
    ):
        raise ValueError("guardian complete Bible effect contracts differ")
    records = {r.asset: r for r in guardians.items}
    kinds = {
        None: 0,
        "categoryWeapons": 0,
        "absorbHP": 1,
        "addCurseOnDamage": 2,
        "addCurse": 3,
        "removeAllCurses": 4,
        "boostHP": 5,
        "boostMP": 6,
        "boostCP": 7,
        "boostCPOfEverybody": 8,
        "boostCPToEnemy": 9,
        "takeCP": 10,
    }
    masks = {"fog": 1, "dream": 2, "flash": 4, "darkcloud": 8}
    profiles = []
    for item in catalog.items:
        if not 245 <= item.model_id <= 284:
            continue
        raw = item.raw
        reference = records.get(str(raw.get("imageName")))
        group = raw.get("guardian")
        weight = raw.get("guardianAttackRate")
        ability = raw.get("ability")
        if (
            raw.get("category") != "guardians"
            or group not in GUARDIAN_GROUPS[:8]
            or type(weight) is not int
            or weight not in (6, 5, 4, 3, 2)
            or ability not in kinds
            or str(raw.get("element", "non-element")) not in element_ids
            or reference is None
            or reference.image_path != f"/images/items/guardians/{raw.get('imageName')}.webp"
            or f"Action: {weight * 5}%" not in reference.detail
        ):
            raise ValueError("guardian API and Bible effect contracts differ")
        profiles.append(
            (
                item.model_id,
                GUARDIAN_GROUPS.index(str(group)),
                weight,
                int(raw.get("atk", 0)),
                element_ids[str(raw.get("element", "non-element"))],
                int(raw.get("hitRate", 100)),
                kinds[ability],
                int(raw.get("abilityValue", 0)),
                masks.get(str(raw.get("curse")), 0),
                0 if item.model_id == 264 else 4,
            )
        )
    raw_by_id = {i.model_id: i.raw for i in catalog.items}
    for model, expected in (
        (
            285,
            {
                "imageName": "drop",
                "category": "guardians",
                "ability": "addItem",
                "guardian": "earth",
                "name": "Drop",
            },
        ),
        (
            286,
            {
                "imageName": "full-moon-blade",
                "category": "guardians",
                "atk": 10,
                "ability": "categoryWeapons",
                "guardian": "moon",
                "name": "Full Moon Blade",
            },
        ),
    ):
        if raw_by_id.get(model) != expected:
            raise ValueError("special guardian API contract differs")
    for model, category, asset, cost, price, rate in (
        (201, "sundries", "guardian-pot", None, 10, 3),
        (239, "miracles", "release", 15, None, 1),
    ):
        raw = raw_by_id[model]
        reference = next((r for r in bible.catalog[category].items if r.asset == asset), None)
        if (
            raw.get("ability") != "setGuardian"
            or raw.get("category") != category
            or raw.get("imageName") != asset
            or raw.get("cost") != cost
            or raw.get("price") != price
            or raw.get("giftRate") != rate
            or reference is None
            or reference.image_path != f"/images/items/{category}/{asset}.webp"
            or reference.detail
            != (
                ("Guardian Pot", "Summon", "a guardian", "$10", "Gift Rate: 3/500")
                if model == 201
                else ("<Release>", "Summon", "a guardian", "Cost", "15MP", "Gift Rate: 1/500")
            )
        ):
            raise ValueError("guardian summon API and Bible contracts differ")
    categories = {row[0]: row[1] for row in build_dream_inventory_plan(catalog, bible).profiles}
    gifts = build_full_game_acquisition_plan(catalog, bible)
    return FullGameGuardianPlan(
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        profiles=tuple(profiles),
        action_profiles=_generated_action_profiles(catalog),
        generated_profiles=tuple(
            (10 if categories[model] == 4 else 9, model, categories[model], weight)
            for model, weight in gifts.model_weights
        ),
    )


def _generated_action_profiles(catalog: ApiCatalogSnapshot) -> tuple[tuple[int, int], ...]:
    """Pinned client gkN leader predicate; guardian use of it is provisional."""
    rows = []
    defensive = {
        "bounceWeapon",
        "reflectWeapon",
        "blockWeapon",
        "reflectAnything",
        "bounceMiracle",
        "reflectMiracle",
        "blockMiracle",
    }
    for item in catalog.items:
        if not 3 <= item.model_id <= 239:
            continue
        raw = item.raw
        category, ability = raw.get("category"), raw.get("ability")
        attack = raw.get("atk", 0)
        can_lead = (
            category in ("weapons", "trade")
            or (
                category == "sundries"
                and not raw.get("isPlusAtk", False)
                and ability not in ("cutCost", "revive", "attractDanger")
            )
            or (
                category == "miracles"
                and not (raw.get("isPlusAtk", False) and not attack)
                and ability not in defensive
            )
        )
        if not can_lead:
            route = 7 if category == "miracles" else 6
        elif category == "trade":
            route = item.model_id
        elif (
            category == "weapons"
            or attack
            or ability
            in (
                "addCurse",
                "removeItems",
                "removeUsedMiracles",
            )
        ):
            route = 1
        else:
            route = 2
        rows.append((item.model_id, route))
    return tuple(rows)
