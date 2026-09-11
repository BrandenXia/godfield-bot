from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState, HandArtifact
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.elements import CombatElement
from godfield_bot.weapon_rules import WeaponAttackRule, weapon_attack_value

if TYPE_CHECKING:
    from torch import Tensor

    from godfield_bot.features import ArtifactVocabulary, StateFeatureEncoder
    from godfield_bot.model_registry import ModelManifest
    from godfield_bot.neural import RecurrentPolicyValueNet

OFFICIAL_TRAINING_NEURAL_POLICY_ID = "official-training-neural-v1"
_COMBO_RULESET_ID = "plain-elemental-combo-attack-defense-redraw-duel-v1"
_RESOURCE_RULESET_ID = (
    "plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1"
)


class Policy(Protocol):
    policy_id: str

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision: ...


class SafeObserverPolicy:
    """A deterministic baseline that refuses unverified external actions."""

    policy_id = "safe-observer-v0"

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        del state
        wait_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.WAIT
        ]
        if len(wait_actions) != 1:
            raise ValueError("safe observer policy requires exactly one WAIT action")
        wait = wait_actions[0]
        return PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=self.policy_id,
            state_digest=legal_actions.state_digest,
            chosen_action_id=wait.action_id,
            scores={wait.action_id: 1.0},
            rationale=legal_actions.blocked_reason or "observation-only safety gate",
            executable=False,
        )


class HeuristicV0Policy:
    """Executable baseline constrained to Bible-audited combat and resource actions."""

    policy_id = "heuristic-v0"
    heal_threshold = 25

    def __init__(
        self,
        verified_weapon_attacks: Mapping[str, WeaponAttackRule],
        plain_armor_defenses: Mapping[str, int],
        verified_miracle_attacks: Mapping[str, tuple[int, int, str]] | None = None,
        plain_hp_utilities: Mapping[str, int] | None = None,
        plain_mp_utilities: Mapping[str, int] | None = None,
    ) -> None:
        if not verified_weapon_attacks or not plain_armor_defenses:
            raise ValueError("heuristic-v0 requires Bible-audited artifact values")
        self.verified_weapon_attacks = dict(verified_weapon_attacks)
        self.verified_miracle_attacks = dict(verified_miracle_attacks or {})
        self.plain_hp_utilities = dict(plain_hp_utilities or {})
        self.plain_mp_utilities = dict(plain_mp_utilities or {})
        self.plain_armor_defenses = dict(plain_armor_defenses)

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        wait_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.WAIT
        ]
        if len(wait_actions) != 1:
            raise ValueError("heuristic policy requires exactly one WAIT action")
        artifact_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.SELECT_ARTIFACT
        ]
        target_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.SELECT_TARGET
        ]
        forgive_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.FORGIVE
        ]
        pass_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.PASS
        ]
        confirm_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.CONFIRM
        ]
        chance_actions = [
            action for action in legal_actions.actions if action.kind is ActionKind.CONFIRM_CHANCE
        ]
        utility_confirm_actions = [
            action
            for action in legal_actions.actions
            if action.kind is ActionKind.CONFIRM_UTILITY
        ]
        if len(target_actions) > 1:
            raise ValueError("heuristic policy requires at most one verified target")
        if len(forgive_actions) > 1:
            raise ValueError("heuristic policy requires at most one Forgive action")
        if len(confirm_actions) > 1:
            raise ValueError("heuristic policy requires at most one verified confirmation")
        if len(chance_actions) > 1:
            raise ValueError("heuristic policy requires at most one chance confirmation")
        if len(utility_confirm_actions) > 1:
            raise ValueError("heuristic policy requires at most one utility confirmation")
        if len(pass_actions) > 1:
            raise ValueError("heuristic policy requires at most one verified pass")
        artifacts_by_slot = {artifact.slot: artifact for artifact in state.hand}

        def artifact_for(action: LegalAction) -> HandArtifact | None:
            return (
                artifacts_by_slot.get(action.artifact_slot)
                if action.artifact_slot is not None
                else None
            )

        attack_actions = [
            action
            for action in artifact_actions
            if (artifact := artifact_for(action)) is not None
            and (
                (artifact.category == "weapons" and artifact.slug in self.verified_weapon_attacks)
                or (
                    artifact.category == "miracles"
                    and artifact.slug in self.verified_miracle_attacks
                    and self.verified_miracle_attacks[artifact.slug][1]
                    <= state.players[state.self_player_index].mp
                )
            )
        ]
        hp_utility_actions = [
            action
            for action in artifact_actions
            if (artifact := artifact_for(action)) is not None
            and artifact.category == "sundries"
            and artifact.slug in self.plain_hp_utilities
        ]
        mp_utility_actions = [
            action
            for action in artifact_actions
            if (artifact := artifact_for(action)) is not None
            and artifact.category == "sundries"
            and artifact.slug in self.plain_mp_utilities
        ]
        armor_actions = [
            action
            for action in artifact_actions
            if (artifact := artifact_for(action)) is not None
            and artifact.category == "armor"
            and artifact.slug in self.plain_armor_defenses
        ]

        def artifact_value(action: LegalAction) -> tuple[float, int]:
            artifact = artifact_for(action)
            if artifact is None or action.artifact_slot is None:
                raise ValueError("ranked artifact action is missing its slot")
            if artifact.category == "weapons":
                value = weapon_attack_value(
                    self.verified_weapon_attacks[artifact.slug],
                    mp=state.players[state.self_player_index].mp,
                )
            elif artifact.category == "miracles":
                value = self.verified_miracle_attacks[artifact.slug][0]
            elif artifact.category == "armor":
                value = self.plain_armor_defenses[artifact.slug]
            elif artifact.slug in self.plain_hp_utilities:
                value = self.plain_hp_utilities[artifact.slug]
            else:
                value = self.plain_mp_utilities[artifact.slug]
            return value, -action.artifact_slot

        best_attack = max(attack_actions, key=artifact_value) if attack_actions else None
        best_hp_utility = (
            max(hp_utility_actions, key=artifact_value) if hp_utility_actions else None
        )
        best_mp_utility = (
            max(mp_utility_actions, key=artifact_value) if mp_utility_actions else None
        )
        best_armor = max(armor_actions, key=artifact_value) if armor_actions else None
        me = state.players[state.self_player_index]
        living_opponent_hp = [
            player.hp for player in state.players if not player.is_self and player.hp
        ]
        attack_is_lethal = (
            best_attack is not None
            and bool(living_opponent_hp)
            and artifact_value(best_attack)[0] >= min(living_opponent_hp)
        )
        selected_artifact: LegalAction | None
        if best_armor is not None:
            selected_artifact = best_armor
        elif attack_is_lethal:
            selected_artifact = best_attack
        elif me.hp <= self.heal_threshold and best_hp_utility is not None:
            selected_artifact = best_hp_utility
        else:
            selected_artifact = best_attack or best_hp_utility or best_mp_utility

        chosen = (
            confirm_actions[0]
            if confirm_actions
            else chance_actions[0]
            if chance_actions
            else utility_confirm_actions[0]
            if utility_confirm_actions
            else target_actions[0]
            if target_actions
            else selected_artifact
            if selected_artifact is not None
            else pass_actions[0]
            if pass_actions
            else forgive_actions[0]
            if forgive_actions
            else wait_actions[0]
        )
        executable = chosen.kind is not ActionKind.WAIT
        chosen_artifact = artifact_for(chosen)
        return PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=self.policy_id,
            state_digest=legal_actions.state_digest,
            chosen_action_id=chosen.action_id,
            scores={
                action.action_id: float(action.action_id == chosen.action_id)
                for action in legal_actions.actions
            },
            rationale=(
                "select the sole verified opponent target"
                if chosen.kind is ActionKind.SELECT_TARGET
                else "resolve the selected Bible-audited untargeted attack"
                if chosen.kind is ActionKind.CONFIRM_CHANCE
                else "confirm the selected deterministic Bible-audited utility"
                if chosen.kind is ActionKind.CONFIRM_UTILITY
                else "confirm the selected verified attack on the named sole opponent"
                if chosen.kind is ActionKind.CONFIRM
                else "restore HP with the strongest deterministic Bible-audited utility"
                if chosen_artifact is not None and chosen_artifact.slug in self.plain_hp_utilities
                else "restore MP with the strongest deterministic Bible-audited utility"
                if chosen_artifact is not None and chosen_artifact.slug in self.plain_mp_utilities
                else "select the strongest affordable phase-appropriate Bible-audited artifact"
                if chosen.kind is ActionKind.SELECT_ARTIFACT
                else "forgive an incoming attack with no verified usable defense"
                if chosen.kind is ActionKind.FORGIVE
                else "pass an attack turn because no reviewed attack is usable"
                if chosen.kind is ActionKind.PASS
                else legal_actions.blocked_reason or "no executable action verified"
            ),
            executable=executable,
        )


class OfficialTrainingNeuralPolicy:
    """Sample a candidate only across reviewed official-Training actions."""

    policy_id = OFFICIAL_TRAINING_NEURAL_POLICY_ID

    def __init__(
        self,
        model_directory: Path,
        snapshot: BibleSnapshot,
        verified_weapon_attacks: Mapping[str, WeaponAttackRule],
        plain_armor_defenses: Mapping[str, int],
        verified_miracle_attacks: Mapping[str, tuple[int, int, CombatElement]] | None = None,
        plain_hp_utilities: Mapping[str, int] | None = None,
        plain_mp_utilities: Mapping[str, int] | None = None,
        sampling_seed: int = 67,
    ) -> None:
        import torch

        from godfield_bot.features import (
            FEATURE_SCHEMA_VERSION,
            GLOBAL_FEATURE_COUNT,
            RESOURCE_FEATURE_SCHEMA_VERSION,
            ArtifactVocabulary,
            StateFeatureEncoder,
        )
        from godfield_bot.model_registry import ModelStatus, load_model, vocabulary_digest

        self.fallback = HeuristicV0Policy(
            verified_weapon_attacks,
            plain_armor_defenses,
            verified_miracle_attacks,
            plain_hp_utilities,
            plain_mp_utilities,
        )
        self.verified_weapon_attacks = self.fallback.verified_weapon_attacks
        self.verified_miracle_attacks = self.fallback.verified_miracle_attacks
        self.plain_hp_utilities = self.fallback.plain_hp_utilities
        self.plain_mp_utilities = self.fallback.plain_mp_utilities
        self.plain_armor_defenses = self.fallback.plain_armor_defenses

        vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
        manifest, model = load_model(model_directory)
        if manifest.status not in {ModelStatus.CANDIDATE, ModelStatus.CHAMPION}:
            raise ValueError("official Training neural control requires a candidate or champion")
        expected_ruleset = {
            FEATURE_SCHEMA_VERSION: _COMBO_RULESET_ID,
            RESOURCE_FEATURE_SCHEMA_VERSION: _RESOURCE_RULESET_ID,
        }.get(manifest.feature_schema_version)
        if expected_ruleset is None:
            raise ValueError("official Training neural control requires feature schema v4 or v5")
        if (
            manifest.architecture.action_count != 21
            or manifest.architecture.global_feature_count != GLOBAL_FEATURE_COUNT
            or manifest.architecture.vocabulary_size != len(vocabulary.tokens)
        ):
            raise ValueError("model architecture differs from the official Training bridge")
        if manifest.client_sha256 != snapshot.client.sha256:
            raise ValueError("model client fingerprint differs from the Bible snapshot")
        if manifest.vocabulary_sha256 != vocabulary_digest(vocabulary):
            raise ValueError("model vocabulary differs from the Bible snapshot")
        simulation = manifest.training_context.get("simulation")
        if not isinstance(simulation, dict) or (
            simulation.get("ruleset_id") != expected_ruleset
            or simulation.get("action_semantics") != "sequential-combo-selection"
        ):
            raise ValueError(
                "model was not trained on matching sequential action semantics"
            )

        self.manifest: ModelManifest = manifest
        self.model: RecurrentPolicyValueNet = model
        self.vocabulary: ArtifactVocabulary = vocabulary
        self.encoder: StateFeatureEncoder = StateFeatureEncoder(
            vocabulary,
            snapshot,
            feature_schema_version=manifest.feature_schema_version,
        )
        self.recurrent_state: Tensor | None = None
        self.generator = torch.Generator(device="cpu").manual_seed(sampling_seed)
        self.model.eval()

    def _fallback_decision(
        self,
        state: GameState,
        legal_actions: LegalActionSet,
        reason: str,
        *,
        reset_memory: bool,
    ) -> PolicyDecision:
        if reset_memory:
            self.recurrent_state = None
        fallback = self.fallback.decide(state, legal_actions)
        return fallback.model_copy(
            update={
                "policy_id": self.policy_id,
                "rationale": f"neural fallback: {reason}; {fallback.rationale}",
            }
        )

    def decide(self, state: GameState, legal_actions: LegalActionSet) -> PolicyDecision:
        import torch

        from godfield_bot.features import FeatureEncodingError, action_index
        from godfield_bot.neural import features_to_tensors

        executable_actions = [
            action for action in legal_actions.actions if action.kind is not ActionKind.WAIT
        ]
        if not executable_actions:
            return self._fallback_decision(
                state,
                legal_actions,
                "no reviewed executable action is available",
                reset_memory=False,
            )
        indexed_actions: dict[int, LegalAction] = {}
        for action in executable_actions:
            index = action_index(action)
            if index in indexed_actions:
                raise ValueError("reviewed browser actions collide in the neural action head")
            indexed_actions[index] = action
        try:
            features = self.encoder.encode(state, legal_actions)
        except FeatureEncodingError as error:
            return self._fallback_decision(
                state,
                legal_actions,
                str(error),
                reset_memory=True,
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
        chosen_index = int(
            torch.multinomial(
                probabilities[0],
                num_samples=1,
                generator=self.generator,
            ).item()
        )
        chosen = indexed_actions.get(chosen_index)
        if chosen is None:
            raise ValueError("neural policy chose an action outside the reviewed browser set")
        self.recurrent_state = recurrent_state.detach()
        return PolicyDecision(
            decided_at=datetime.now(UTC),
            policy_id=self.policy_id,
            state_digest=legal_actions.state_digest,
            chosen_action_id=chosen.action_id,
            scores={
                action.action_id: (
                    0.0
                    if action.kind is ActionKind.WAIT
                    else float(probabilities[0, action_index(action)].item())
                )
                for action in legal_actions.actions
            },
            rationale=(
                f"sampled immutable candidate {self.manifest.model_id} choice "
                "within the reviewed official-Training action set"
            ),
            executable=True,
        )
