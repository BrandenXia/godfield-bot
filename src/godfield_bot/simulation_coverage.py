"""Read-only artifact-inclusion audit for the latest native curriculum.

An included artifact is not proof that every official interaction is modeled.
This report must never be used as a promotion or live-control gate.
"""

from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.simulation import AttackDefenseRuleset, create_attack_defense_simulation


class SimulationCoverageReport(BaseModel):
    schema_version: Literal[1] = 1
    scope: Literal["artifact-inclusion-only-not-behavioral-fidelity"] = (
        "artifact-inclusion-only-not-behavioral-fidelity"
    )
    ruleset_id: str
    client_sha256: str
    rule_catalog_sha256: str
    bible_artifact_count: int = Field(ge=0)
    included_artifact_count: int = Field(ge=0)
    missing_artifact_count: int = Field(ge=0)
    missing_by_category: dict[str, tuple[str, ...]]
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False


def build_simulation_coverage_report(
    snapshot_path: Path,
    *,
    ruleset: AttackDefenseRuleset = "wide-hand-gift-weighted-dream-resource-hand",
) -> SimulationCoverageReport:
    """Compare the actual configured native catalog to the pinned Bible catalog."""

    snapshot = BibleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    simulation = create_attack_defense_simulation(
        snapshot_path,
        batch_size=1,
        ruleset=ruleset,
    )
    configured = simulation.catalog_token_ids
    if len(configured) != simulation.metadata.rule_catalog_size:
        raise ValueError("native catalog token count does not match metadata")
    if len(configured) != len(set(configured)):
        raise ValueError("native catalog contains duplicate artifact tokens")

    token_ids = {token: token_id for token_id, token in enumerate(vocabulary.tokens)}
    artifacts = {
        f"{category_name}/{artifact.asset}"
        for category_name, category in snapshot.catalog.items()
        for artifact in category.items
    }
    artifact_ids = {token_ids[token] for token in artifacts}
    unexpected = set(configured) - artifact_ids
    if unexpected:
        raise ValueError("native catalog contains tokens outside the Bible artifact catalog")
    missing: dict[str, list[str]] = defaultdict(list)
    for token in sorted(artifacts):
        if token_ids[token] not in configured:
            category, asset = token.split("/", 1)
            missing[category].append(asset)
    return SimulationCoverageReport(
        ruleset_id=simulation.metadata.ruleset_id,
        client_sha256=simulation.metadata.client_sha256,
        rule_catalog_sha256=simulation.metadata.rule_catalog_sha256,
        bible_artifact_count=len(artifacts),
        included_artifact_count=len(configured),
        missing_artifact_count=sum(len(assets) for assets in missing.values()),
        missing_by_category={category: tuple(missing[category]) for category in sorted(missing)},
    )
