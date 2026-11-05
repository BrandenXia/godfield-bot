"""Current integrated-engine ledger; declaration is separate from executed evidence."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.api_catalog import read_api_catalog_snapshot
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.full_game import (
    FullGameMetadata,
    FullGamePlan,
    create_development_full_game_batch,
)
from godfield_bot.full_game_observation import (
    CARD_PROPERTIES_OBSERVATION_ID,
    FullGameEncoderMetadata,
    FullGameObservationEncoder,
)

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Kind = Literal["virtual-control", "held-trade", "held-artifact", "devil", "guardian", "phenomenon"]


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class FullGameWorkflowEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_id: str
    implementation: str
    source_files: tuple[str, ...]
    test_files: tuple[str, ...]
    evidence_boundary: Literal["required-tests-not-an-assertion-that-they-ran"] = (
        "required-tests-not-an-assertion-that-they-ran"
    )


def workflow_ledger() -> tuple[FullGameWorkflowEvidence, ...]:
    rows = (
        (
            "acquisition-overflow",
            "Weighted complete held pool, per-use gifts and bounded oldest-card eviction.",
            ("full_game_batch.cpp",),
            ("acquisition", "caps", "mechanic_learning"),
        ),
        (
            "offensive-combinations",
            "Ordered composition, elements, chance, attack effects and multiple recipients.",
            ("full_game_batch.cpp", "full_game_composition.cpp", "full_game_effects.cpp"),
            ("combat", "composition", "chance", "attack_effects", "weapons", "danger", "area"),
        ),
        (
            "special-defense",
            "Ordered armor, origin filters, reflection, bounce and nested counters.",
            ("full_game_batch.cpp", "full_game_effects.cpp"),
            ("special_defense", "defense_effects", "dream_defense", "attack_family"),
        ),
        (
            "utility-targeting-costs",
            "HP/MP/CP utilities, cures, compound effects, waivers and hidden-cost fizzles.",
            ("full_game_batch.cpp", "full_game_ineffective.cpp"),
            (
                "resource_smoke",
                "economy",
                "compound_utilities",
                "costs",
                "hidden_costs",
                "mechanic_learning",
            ),
        ),
        (
            "curse-turn-dynamics",
            "Shared illness ticks, Fog/Flash/Dream, redraws, cures and native confusion turns.",
            (
                "full_game_batch.cpp",
                "full_game_events.cpp",
                "curse_dynamics_batch.cpp",
                "dream_inventory_batch.cpp",
            ),
            ("", "attack_effects", "dream_defense", "phenomena", "hidden_targeting", "ineffective"),
        ),
        (
            "guardian-lifecycle-timing",
            "Ownership, enemy-turn activation, departure, regular effects and Earth/Moon actions.",
            ("full_game_batch.cpp", "full_game_generated.cpp", "full_game_teams.cpp"),
            ("guardians", "earth", "generated", "teams"),
        ),
        (
            "devils",
            "All five effects integrated into bounded receipt waves and death reactions.",
            ("full_game_batch.cpp", "full_game_events.cpp"),
            ("devils", "revival", "attack_family"),
        ),
        (
            "phenomena",
            "All ten effects, generated attacks, shuffle, control and guardian changes.",
            ("full_game_events.cpp", "full_game_generated.cpp"),
            ("phenomena", "generated", "teams"),
        ),
        (
            "economy",
            "Exchange allocation, Sell/Buy custody, payment waterfall and reflected offers.",
            ("full_game_trade.cpp", "full_game_generated.cpp"),
            ("trade", "market", "hidden_trades", "generated", "economy"),
        ),
        (
            "removal-revival",
            "Broom/Soap, discard/sacrifice, protected identities and shared Sun/Bow death hooks.",
            ("full_game_batch.cpp", "full_game_ineffective.cpp"),
            ("removal", "discard", "sacrifice", "hidden_removals", "revival", "mechanic_learning"),
        ),
        (
            "apocalypse-terminal-flow",
            "Threshold, deferred receipts and attack families before true endings or limits.",
            ("full_game_batch.cpp", "full_game_events.cpp", "full_game_teams.cpp"),
            ("", "devils", "sacrifice", "attack_family", "teams", "rewards", "episode_probe"),
        ),
        (
            "teams-multiplayer-learning",
            "Native factions/targets, eliminated teammate rewards and per-seat terminal learning.",
            ("full_game_teams.cpp", "full_game_batch.cpp"),
            ("teams", "rewards", "neural", "rollout", "training", "learning_probe"),
        ),
        (
            "full-action-observation-contract",
            "Public 18-slot/28-choice inputs, announcements, displayed properties and transfers.",
            ("full_game_batch.cpp", "full_game_trade.cpp"),
            ("protocol", "observation", "neural", "card_features", "training"),
        ),
        (
            "full-game-validation",
            "Atomic batches, bounded episodes, seat replay, PPO, restore and frozen evaluation.",
            ("full_game_batch.cpp", "full_game_generated.cpp", "full_game_trade.cpp"),
            (
                "",
                "generated",
                "market",
                "hidden_costs",
                "rollout",
                "training",
                "imitation",
                "diagnostics",
                "learning_probe",
                "mechanic_learning",
            ),
        ),
    )
    python_sources = {
        "teams-multiplayer-learning": (
            "full_game_rewards",
            "full_game_rollout",
            "full_game_training",
        ),
        "full-action-observation-contract": (
            "full_game_protocol",
            "full_game_observation",
            "full_game_neural",
            "full_game_card_features",
        ),
        "full-game-validation": (
            "full_game_replay",
            "full_game_training",
            "full_game_evaluation",
            "full_game_learning_probe",
        ),
    }
    return tuple(
        FullGameWorkflowEvidence(
            workflow_id=key,
            implementation=description,
            source_files=tuple(f"native/godfield_sim/src/{name}" for name in native)
            + tuple(f"src/godfield_bot/{name}.py" for name in python_sources.get(key, ())),
            test_files=tuple(
                f"tests/test_full_game{'_' + name if name else ''}.py" for name in tests
            ),
        )
        for key, description, native, tests in rows
    )


def declared_routes(plan: FullGamePlan) -> dict[int, tuple[str, ...]]:
    """Primary owned/event routes only: a generated fallback is not an owned defense."""
    routes: dict[int, list[str]] = defaultdict(list)
    fields = (
        "combat.attack_profiles",
        "combat.armor_profiles",
        "combat.boost_profiles",
        "combat.special_profiles",
        "combat.chance_profiles",
        "combat.attack_effect_profiles",
        "combat.defense_effect_profiles",
        "effect_profiles",
        "costs.profiles",
        "weapons.profiles",
        "danger.profiles",
        "dream_defense.profiles",
        "attack_family.profiles",
        "area.profiles",
        "removal.profiles",
        "passives.profiles",
        "guardians.summon_profiles",
        "guardians.profiles",
        "devils.profiles",
        "phenomena.profiles",
    )
    for name in fields:
        value: Any = plan
        for part in name.split("."):
            value = getattr(value, part)
        for row in value:
            routes[row[0]].append(name)
    for model in plan.phenomena.fate_model_ids:
        routes[model].append("phenomena.fate_model_ids")
    for model in plan.trade.exchange_model_ids:
        routes[model].append("trade.exchange_model_ids")
    for model, kind, _ in plan.trade.price_profiles:
        if kind in (2, 3):
            routes[model].append("trade.sell" if kind == 2 else "trade.buy")
    routes[plan.discard.virtual_model_id].append("discard.virtual_model_id")
    routes[plan.discard.sacrifice_virtual_model_id].append("discard.sacrifice_virtual_model_id")
    # These two source identities and their category pools are checked by the
    # guardian plan builder, not inferred from generic guardian registration.
    routes[285].append("guardians.earth_generated_actions")
    routes[286].append("guardians.moon_generated_actions")
    return {model: tuple(sorted(names)) for model, names in routes.items()}


def entry_kind(model: int) -> Kind:
    if model <= 2:
        return "virtual-control"
    if model <= 5:
        return "held-trade"
    if model <= 239:
        return "held-artifact"
    if model <= 244:
        return "devil"
    return "guardian" if model <= 286 else "phenomenon"


class FullGameCatalogRoute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_id: int = Field(ge=1, le=296, strict=True)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    asset: str | None
    kind: Kind
    bible_artifact: bool = Field(strict=True)
    owned_role_bits: int = Field(ge=0, le=511, strict=True)
    primary_routes: tuple[str, ...] = Field(min_length=1)
    generated_guardian_route: str | None


class FullGameProvisionalAssumption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metadata_path: str
    rule: str


def provisional_assumptions(
    metadata: FullGameMetadata,
) -> tuple[FullGameProvisionalAssumption, ...]:
    result = []

    def visit(path: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in sorted(value.items()):
                visit(f"{path}.{key}" if path else key, child)
        elif isinstance(value, str) and "provisional" in value:
            result.append(FullGameProvisionalAssumption(metadata_path=path, rule=value))

    visit("", metadata.model_dump(mode="json"))
    return tuple(result)


class FullGameIntegrationAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    scope: Literal["integrated-source-route-and-validation-requirements-ledger"] = (
        "integrated-source-route-and-validation-requirements-ledger"
    )
    native_version: str = Field(min_length=1)
    metadata: FullGameMetadata
    encoder: FullGameEncoderMetadata
    catalog_sha256: Digest
    bible_client_sha256: Digest
    entries: tuple[FullGameCatalogRoute, ...]
    workflows: tuple[FullGameWorkflowEvidence, ...]
    provisional_assumptions: tuple[FullGameProvisionalAssumption, ...]
    catalog_entries: Literal[296] = 296
    bible_artifacts: Literal[291] = 291
    held_models: Literal[237] = 237
    virtual_controls: Literal[2] = 2
    source_routes_complete: Literal[True] = True
    execution_evidence_attached: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def complete_join(self) -> FullGameIntegrationAudit:
        FullGameMetadata.model_validate(self.metadata.model_dump())
        roles = dict(self.metadata.roles.model_roles)
        routes = declared_routes(self.metadata.plan)
        generated = dict(self.metadata.plan.guardians.action_profiles)
        expected_environment = dict(
            batch_size=1,
            player_count=4,
            initial_teams=(1, 2, 1, 2),
            capacity=18,
            acquisition_mode="all-held-weighted",
            resource_cap=99,
            seed=67,
            max_turns=256,
            max_decisions=2048,
            apocalypse_after_turns=64,
            hidden_cost_policy="fizzle-provisional",
        )
        if (
            self.metadata.model_dump(include=set(expected_environment)) != expected_environment
            or tuple(row.model_id for row in self.entries) != tuple(range(1, 297))
            or set(routes) != set(range(1, 297))
            or self.catalog_sha256 != self.metadata.plan.inventory.catalog_sha256
            or self.bible_client_sha256 != self.metadata.plan.inventory.bible_client_sha256
            or self.encoder.observation_id != CARD_PROPERTIES_OBSERVATION_ID
            or self.encoder.environment_metadata_sha256
            != canonical_sha256(self.metadata.model_dump(mode="json"))
            or self.workflows != workflow_ledger()
            or self.provisional_assumptions != provisional_assumptions(self.metadata)
            or any(
                row.kind != entry_kind(row.model_id)
                or row.bible_artifact != (row.model_id >= 6)
                or row.owned_role_bits != roles.get(row.model_id, 0)
                or row.primary_routes != routes[row.model_id]
                or row.generated_guardian_route
                != (
                    self.metadata.plan.guardians.action_routes[generated[row.model_id]]
                    if row.model_id in generated
                    else None
                )
                for row in self.entries
            )
        ):
            raise ValueError("integrated full-game source/route/workflow accounting differs")
        return self


def build_full_game_integration_audit(
    *, catalog_path: Path, bible_path: Path
) -> FullGameIntegrationAudit:
    """Build an unstarted current native instance; never turn route inclusion into certification."""
    catalog = read_api_catalog_snapshot(catalog_path)
    bible = BibleSnapshot.model_validate_json(bible_path.read_text(encoding="utf-8"))
    configured = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=1,
        player_count=4,
        teams=(1, 2, 1, 2),
        capacity=18,
        acquisition_mode="all-held-weighted",
        seed=67,
        max_turns=256,
        max_decisions=2048,
        apocalypse_after_turns=64,
    )
    metadata = configured.metadata
    roles = dict(metadata.roles.model_roles)
    routes = declared_routes(metadata.plan)
    generated = dict(metadata.plan.guardians.action_profiles)
    expected = {
        (category, row.asset) for category, group in bible.catalog.items() for row in group.items
    }
    actual = {
        (item.raw.get("category"), item.raw.get("imageName"))
        for item in catalog.items
        if item.model_id >= 6
    }
    if (
        len(expected) != 291
        or len(actual) != 291
        or actual != expected
        or len(catalog.items) != 296
    ):
        raise ValueError("integrated audit requires the exact API/Bible artifact join")
    entries = tuple(
        FullGameCatalogRoute(
            model_id=item.model_id,
            name=str(item.raw["name"]),
            category=str(item.raw.get("category", "controls")),
            asset=item.raw.get("imageName"),
            kind=entry_kind(item.model_id),
            bible_artifact=item.model_id >= 6,
            owned_role_bits=roles.get(item.model_id, 0),
            primary_routes=routes.get(item.model_id, ()),
            generated_guardian_route=metadata.plan.guardians.action_routes[generated[item.model_id]]
            if item.model_id in generated
            else None,
        )
        for item in catalog.items
    )
    return FullGameIntegrationAudit(
        native_version=version("godfield-sim"),
        metadata=metadata,
        encoder=FullGameObservationEncoder(configured, CARD_PROPERTIES_OBSERVATION_ID).metadata,
        catalog_sha256=catalog.content_sha256,
        bible_client_sha256=bible.client.sha256,
        entries=entries,
        workflows=workflow_ledger(),
        provisional_assumptions=provisional_assumptions(metadata),
    )
