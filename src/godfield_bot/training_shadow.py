from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from godfield_bot.domain.action import ActionKind, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenObservation
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.domain.run import EventKind, RunMode
from godfield_bot.features import (
    DREAM_FEATURE_SCHEMA_VERSION,
    DREAM_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
    FeatureEncodingError,
    StateFeatureEncoder,
    action_index,
)
from godfield_bot.game_state import parse_game_state
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.model_registry import ModelStatus, load_model, vocabulary_digest
from godfield_bot.run_store import RunStore

if TYPE_CHECKING:
    from torch import Tensor

    from godfield_bot.model_registry import ModelManifest
    from godfield_bot.neural import RecurrentPolicyValueNet

OFFICIAL_TRAINING_SHADOW_POLICY_ID = "official-training-neural-shadow-v1"
DREAM_RULESET_ID = (
    "plain-elemental-combo-stochastic-chance-absorption-weapon-dynamic-mp-"
    "same-damage-weapon-attack-twice-weapon-random-target-weapon-illness-weapon-"
    "illness-cure-heaven-herb-fever-mask-miracle-block-armor-weapon-miracle-"
    "bounce-armor-weapon-miracle-miracle-reflection-armor-weapon-fog-flash-"
    "weapon-miracle-dark-cloud-weapon-miracle-dream-weapon-miracle-displayed-"
    "identity-additive-reflection-dual-role-resource-miracle-attack-defense-"
    "redraw-duel-v1"
)


class TrainingShadowError(ValueError):
    """Raised when a model cannot be bound to read-only Training shadow inference."""


class TrainingShadowEvidence(BaseModel):
    schema_version: Literal[1] = 1
    evidence_type: Literal["official_training_shadow"] = "official_training_shadow"
    observed_at: datetime
    policy_id: Literal["official-training-neural-shadow-v1"] = (
        "official-training-neural-shadow-v1"
    )
    model_id: str
    model_weights_sha256: str
    feature_schema_version: Literal[10] = 10
    state_digest: str
    field_number: int = Field(ge=0)
    behavior_action_id: str
    behavior_executable: bool
    covered: bool
    proposed_action_id: str | None = None
    agreement: bool | None = None
    abstain_reason: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    recurrent_reset: bool = False


class TrainingShadowSummary(BaseModel):
    schema_version: Literal[1] = 1
    model_id: str
    model_weights_sha256: str
    samples: int = Field(ge=0)
    eligible_decisions: int = Field(ge=0)
    covered_decisions: int = Field(ge=0)
    abstained_decisions: int = Field(ge=0)
    agreements: int = Field(ge=0)
    disagreements: int = Field(ge=0)
    recurrent_resets: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    agreement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    abstain_reasons: dict[str, int]
    behavior_action_families: dict[str, int]
    proposal_action_families: dict[str, int]
    disagreement_pairs: dict[str, int]


def _validate_model(
    manifest: ModelManifest,
    vocabulary: ArtifactVocabulary,
    snapshot: BibleSnapshot,
) -> None:
    if manifest.status not in {ModelStatus.CANDIDATE, ModelStatus.CHAMPION}:
        raise TrainingShadowError("Training shadow requires a candidate or champion model")
    if manifest.feature_schema_version != DREAM_FEATURE_SCHEMA_VERSION:
        raise TrainingShadowError("Training shadow requires a feature-schema-v10 model")
    if (
        manifest.architecture.action_count != 21
        or manifest.architecture.global_feature_count != DREAM_GLOBAL_FEATURE_COUNT
        or manifest.architecture.vocabulary_size != len(vocabulary.tokens)
    ):
        raise TrainingShadowError("model architecture differs from the schema-v10 bridge")
    if manifest.client_sha256 != snapshot.client.sha256:
        raise TrainingShadowError("model client fingerprint differs from the Bible snapshot")
    if manifest.vocabulary_sha256 != vocabulary_digest(vocabulary):
        raise TrainingShadowError("model vocabulary differs from the Bible snapshot")
    simulation = manifest.training_context.get("simulation")
    if not isinstance(simulation, dict) or (
        simulation.get("ruleset_id") != DREAM_RULESET_ID
        or simulation.get("observation_schema_version") != DREAM_FEATURE_SCHEMA_VERSION
        or simulation.get("action_semantics") != "sequential-combo-selection"
    ):
        raise TrainingShadowError(
            "model was not trained on the matching schema-v10 sequential ruleset"
        )


class OfficialTrainingShadowPolicy:
    """Produce counterfactual schema-v10 proposals without controlling the browser."""

    policy_id = OFFICIAL_TRAINING_SHADOW_POLICY_ID

    def __init__(self, model_directory: Path, snapshot: BibleSnapshot) -> None:
        vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
        manifest, model = load_model(model_directory)
        _validate_model(manifest, vocabulary, snapshot)
        model.eval()
        self.manifest = manifest
        self.model: RecurrentPolicyValueNet = model
        self.encoder = StateFeatureEncoder(
            vocabulary,
            snapshot,
            feature_schema_version=DREAM_FEATURE_SCHEMA_VERSION,
        )
        self.recurrent_state: Tensor | None = None

    def reset(self) -> None:
        self.recurrent_state = None

    def _abstain(
        self,
        state: GameState,
        behavior: PolicyDecision,
        reason: str,
        *,
        reset: bool,
    ) -> TrainingShadowEvidence:
        if reset:
            self.reset()
        return TrainingShadowEvidence(
            observed_at=state.observed_at,
            model_id=self.manifest.model_id,
            model_weights_sha256=self.manifest.weights_sha256,
            state_digest=behavior.state_digest,
            field_number=state.field_number,
            behavior_action_id=behavior.chosen_action_id,
            behavior_executable=behavior.executable,
            covered=False,
            abstain_reason=reason,
            recurrent_reset=reset,
        )

    def evaluate(
        self,
        state: GameState,
        legal_actions: LegalActionSet,
        behavior: PolicyDecision,
    ) -> TrainingShadowEvidence:
        import torch

        from godfield_bot.neural import features_to_tensors

        if behavior.state_digest != legal_actions.state_digest:
            return self._abstain(
                state,
                behavior,
                "behavior decision does not belong to the legal action set",
                reset=True,
            )
        executable_actions = tuple(
            action for action in legal_actions.actions if action.kind is not ActionKind.WAIT
        )
        if not behavior.executable:
            return self._abstain(
                state,
                behavior,
                "behavior decision is not executable",
                reset=False,
            )
        if not executable_actions:
            return self._abstain(
                state,
                behavior,
                "no reviewed executable action is available",
                reset=True,
            )
        if len(state.players) != 2:
            return self._abstain(
                state,
                behavior,
                "schema-v10 shadow is restricted to two-player Training games",
                reset=True,
            )
        try:
            features = self.encoder.encode(state, legal_actions)
            indexed_actions = {action_index(action): action for action in executable_actions}
        except FeatureEncodingError as error:
            return self._abstain(state, behavior, str(error), reset=True)
        if len(indexed_actions) != len(executable_actions):
            return self._abstain(
                state,
                behavior,
                "reviewed browser actions collide in the neural action head",
                reset=True,
            )

        action_mask = list(features.action_mask)
        action_mask[0] = False
        features = features.model_copy(update={"action_mask": tuple(action_mask)})
        with torch.no_grad():
            logits, _, recurrent_state = self.model(
                *features_to_tensors([features]),
                recurrent_state=self.recurrent_state,
            )
            probabilities = torch.softmax(logits, dim=-1)
        proposed_index = int(probabilities[0].argmax().item())
        proposed = indexed_actions.get(proposed_index)
        if proposed is None:
            return self._abstain(
                state,
                behavior,
                "shadow model proposed an action outside the reviewed browser set",
                reset=True,
            )

        agreement = proposed.action_id == behavior.chosen_action_id
        if agreement:
            self.recurrent_state = recurrent_state.detach()
        else:
            self.reset()
        return TrainingShadowEvidence(
            observed_at=state.observed_at,
            model_id=self.manifest.model_id,
            model_weights_sha256=self.manifest.weights_sha256,
            state_digest=behavior.state_digest,
            field_number=state.field_number,
            behavior_action_id=behavior.chosen_action_id,
            behavior_executable=True,
            covered=True,
            proposed_action_id=proposed.action_id,
            agreement=agreement,
            scores={
                action.action_id: (
                    0.0
                    if action.kind is ActionKind.WAIT
                    else float(probabilities[0, action_index(action)].item())
                )
                for action in legal_actions.actions
            },
            recurrent_reset=not agreement,
        )


def summarize_training_shadow(
    samples: tuple[TrainingShadowEvidence, ...],
) -> TrainingShadowSummary:
    if not samples:
        raise ValueError("at least one Training shadow sample is required")
    identities = {(sample.model_id, sample.model_weights_sha256) for sample in samples}
    if len(identities) != 1:
        raise ValueError("Training shadow samples must name one immutable model")
    model_id, weights_sha256 = identities.pop()
    eligible = tuple(sample for sample in samples if sample.behavior_executable)
    covered = tuple(sample for sample in eligible if sample.covered)
    agreements = sum(sample.agreement is True for sample in covered)
    disagreements = sum(sample.agreement is False for sample in covered)
    reasons = Counter(
        sample.abstain_reason or "unspecified"
        for sample in eligible
        if not sample.covered
    )
    behavior_families = Counter(
        _action_family(sample.behavior_action_id) for sample in covered
    )
    proposal_families = Counter(
        _action_family(sample.proposed_action_id)
        for sample in covered
        if sample.proposed_action_id is not None
    )
    disagreement_pairs = Counter(
        f"{sample.behavior_action_id} -> {sample.proposed_action_id}"
        for sample in covered
        if sample.agreement is False
    )
    return TrainingShadowSummary(
        model_id=model_id,
        model_weights_sha256=weights_sha256,
        samples=len(samples),
        eligible_decisions=len(eligible),
        covered_decisions=len(covered),
        abstained_decisions=len(eligible) - len(covered),
        agreements=agreements,
        disagreements=disagreements,
        recurrent_resets=sum(sample.recurrent_reset for sample in samples),
        coverage=(len(covered) / len(eligible) if eligible else 0.0),
        agreement_rate=(agreements / len(covered) if covered else None),
        abstain_reasons=dict(sorted(reasons.items())),
        behavior_action_families=dict(sorted(behavior_families.items())),
        proposal_action_families=dict(sorted(proposal_families.items())),
        disagreement_pairs=dict(
            sorted(
                disagreement_pairs.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
    )


def _action_family(action_id: str) -> str:
    if action_id.startswith("artifact:"):
        parts = action_id.split(":", 2)
        category = parts[2].split("/", 1)[0] if len(parts) == 3 else "unknown"
        return f"artifact:{category}"
    if action_id.startswith("confirm:"):
        parts = action_id.split(":", 2)
        return ":".join(parts[:2])
    return action_id.split(":", 1)[0]


def evaluate_recorded_training_runs(
    store: RunStore,
    model_directory: Path,
    snapshot: BibleSnapshot,
    run_ids: tuple[str, ...],
) -> tuple[TrainingShadowEvidence, ...]:
    """Replay recorded behavior states without writing to the trajectory store."""

    if not run_ids:
        raise ValueError("at least one Training run ID is required")
    policy = OfficialTrainingShadowPolicy(model_directory, snapshot)
    evidence: list[TrainingShadowEvidence] = []
    for run_id in run_ids:
        run = store.get_run(run_id)
        if run is None:
            raise ValueError(f"unknown run: {run_id}")
        if run.mode is not RunMode.TRAINING:
            raise ValueError(f"run {run_id} is not an official Training run")
        if run.client_sha256 != policy.manifest.client_sha256:
            raise ValueError(f"run {run_id} uses a different client fingerprint")
        policy.reset()
        previous_state: GameState | None = None
        events = store.events(run_id)
        for index, event in enumerate(events):
            if event.kind is not EventKind.GAME_STATE:
                continue
            if (
                index < 1
                or index + 2 >= len(events)
                or events[index - 1].kind is not EventKind.OBSERVATION
                or events[index + 1].kind is not EventKind.LEGAL_ACTIONS
                or events[index + 2].kind is not EventKind.DECISION
            ):
                raise ValueError(f"run {run_id} has a malformed policy event group")
            observation = ScreenObservation.model_validate(events[index - 1].payload)
            state = parse_game_state(
                observation,
                identity=run.identity,
                previous_state=previous_state,
            )
            previous_state = state
            digest = game_state_digest(state)
            legal_actions = LegalActionSet.model_validate(
                events[index + 1].payload
            ).model_copy(update={"state_digest": digest})
            behavior = PolicyDecision.model_validate(
                events[index + 2].payload
            ).model_copy(update={"state_digest": digest})
            evidence.append(policy.evaluate(state, legal_actions, behavior))
    return tuple(evidence)
