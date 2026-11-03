"""Read-only decision and mechanic diagnostics for integrated full-game evaluation."""

from __future__ import annotations

from typing import Annotated, Final, Literal

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot import full_game as game
from godfield_bot.full_game_greedy import GREEDY_POLICY_ID, FullGameGreedyPolicy
from godfield_bot.full_game_guardians import GUARDIAN_GENERATED_STATS
from godfield_bot.full_game_neural import (
    FullGameActorCritic,
    FullGamePolicyStep,
    full_game_policy_inputs,
)
from godfield_bot.full_game_observation import GLOBAL_FIELDS, HAND_FEATURES, HAND_SLOTS
from godfield_bot.full_game_trade import MARKET_STATS, TRADE_STATS

Count = Annotated[int, Field(ge=0, strict=True)]
Phase = Literal[1, 2, 3, 4, 6, 7]
PHASES: Final[tuple[Phase, ...]] = (1, 2, 3, 4, 6, 7)
HELD_MODELS: Final = tuple(range(3, 240))
# These are final per-episode diagnostic views. Summing a queue size or peak
# depth is explicitly a sum of final rows, not a count of effects executed.
NATIVE_VIEWS: Final = {
    "acquisition_snapshot": game.ACQUISITION_FIELDS,
    "chance_snapshot": game.CHANCE_SNAPSHOT_FIELDS,
    "attack_effect_snapshot": game.ATTACK_EFFECT_SNAPSHOT_FIELDS,
    "counter_snapshot": game.COUNTER_SNAPSHOT_FIELDS,
    "revival_snapshot": game.REVIVAL_FIELDS,
    "removal_snapshot": game.REMOVAL_FIELDS,
    "cp_utility_snapshot": game.CP_UTILITY_FIELDS,
    "compound_utility_snapshot": game.COMPOUND_UTILITY_FIELDS,
    "cost_snapshot": game.COST_FIELDS,
    "complex_weapon_snapshot": game.COMPLEX_WEAPON_SNAPSHOT_FIELDS,
    "danger_snapshot": game.DANGER_SNAPSHOT_FIELDS,
    "dream_defense_snapshot": game.DREAM_DEFENSE_FIELDS,
    "attack_family_snapshot": game.ATTACK_FAMILY_FIELDS,
    "area_snapshot": game.AREA_SNAPSHOT_FIELDS,
    "discard_snapshot": game.DISCARD_SNAPSHOT_FIELDS,
    "sacrifice_snapshot": game.SACRIFICE_SNAPSHOT_FIELDS,
    "guardian_statistics": game.GUARDIAN_STATISTIC_FIELDS,
    "guardian_generated_snapshot": GUARDIAN_GENERATED_STATS,
    "devil_snapshot": game.DEVIL_FIELDS,
    "confusion_snapshot": game.CONFUSION_FIELDS,
    "phenomenon_snapshot": game.PHENOMENON_SNAPSHOT_FIELDS,
    "trade_snapshot": TRADE_STATS,
    "market_snapshot": MARKET_STATS,
    "hidden_targeting_snapshot": game.HIDDEN_TARGETING_FIELDS,
    "hidden_trade_snapshot": game.HIDDEN_TRADE_FIELDS,
    "ineffective_snapshot": game.INEFFECTIVE_FIELDS,
    "hidden_removal_snapshot": game.HIDDEN_REMOVAL_FIELDS,
    "hidden_cost_snapshot": game.HIDDEN_COST_FIELDS,
    "devil_model_counts": tuple(str(i) for i in range(240, 245)),
    "guardian_model_counts": tuple(str(i) for i in range(245, 285)),
    "phenomenon_model_counts": tuple(str(i) for i in range(287, 297)),
    "guardian_generated_model_counts": tuple(str(i) for i in HELD_MODELS),
    "guardian_generated_execution_counts": tuple(str(i) for i in HELD_MODELS),
}


class FullGamePhaseDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    phase: Phase
    candidate_decisions: Count
    voluntary_decisions: Count
    sampled_teacher_agreements: Count
    argmax_teacher_agreements: Count
    teacher_probability_sum: float = Field(ge=0, allow_inf_nan=False)
    displayed_slot_choices: Count
    deselections: Count
    candidate_choice_counts: tuple[Count, ...]
    teacher_choice_counts: tuple[Count, ...]

    @model_validator(mode="after")
    def accounting(self) -> FullGamePhaseDiagnostics:
        if (
            self.voluntary_decisions > self.candidate_decisions
            or self.sampled_teacher_agreements > self.voluntary_decisions
            or self.argmax_teacher_agreements > self.voluntary_decisions
            or self.teacher_probability_sum > self.voluntary_decisions + 1e-6
            or self.displayed_slot_choices > self.candidate_decisions
            or self.deselections > self.displayed_slot_choices
            or len(self.candidate_choice_counts) != 28
            or len(self.teacher_choice_counts) != 28
            or sum(self.candidate_choice_counts) != self.voluntary_decisions
            or sum(self.teacher_choice_counts) != self.voluntary_decisions
        ):
            raise ValueError("full-game phase diagnostic accounting differs")
        return self


class FullGameNativeDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    view: str
    fields: tuple[str, ...]
    totals: tuple[Count, ...]

    @model_validator(mode="after")
    def pinned_layout(self) -> FullGameNativeDiagnostic:
        if self.fields != NATIVE_VIEWS.get(self.view) or len(self.totals) != len(self.fields):
            raise ValueError("full-game native diagnostic layout differs")
        return self


class FullGameEvaluationDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    ruleset_id: Literal["integrated-full-game-development-v33"] = game.FULL_GAME_RULESET_ID
    teacher: Literal["full-game-public-greedy-v1"] = GREEDY_POLICY_ID
    decision_scope: Literal["candidate-decisions-in-evaluated-games-including-truncations"] = (
        "candidate-decisions-in-evaluated-games-including-truncations"
    )
    native_scope: Literal["all-seats-sum-final-per-episode-rows-diagnostic-only"] = (
        "all-seats-sum-final-per-episode-rows-diagnostic-only"
    )
    model_scope: Literal["displayed-slot-choices-including-toggles-not-effect-execution"] = (
        "displayed-slot-choices-including-toggles-not-effect-execution"
    )
    accepted_decisions: Count
    candidate_decisions: Count
    candidate_forced_decisions: Count
    all_seat_phase_counts: tuple[Count, ...]
    phases: tuple[FullGamePhaseDiagnostics, ...]
    displayed_model_ids: tuple[int, ...] = HELD_MODELS
    displayed_model_choice_counts: tuple[Count, ...]
    native: tuple[FullGameNativeDiagnostic, ...]
    training_dataset_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def accounting(self) -> FullGameEvaluationDiagnostics:
        if (
            tuple(row.phase for row in self.phases) != PHASES
            or len(self.all_seat_phase_counts) != 14
            or sum(self.all_seat_phase_counts) != self.accepted_decisions
            or any(self.all_seat_phase_counts[i] for i in range(14) if i not in PHASES)
            or sum(row.candidate_decisions for row in self.phases) != self.candidate_decisions
            or sum(row.candidate_decisions - row.voluntary_decisions for row in self.phases)
            != self.candidate_forced_decisions
            or any(
                row.candidate_decisions > self.all_seat_phase_counts[row.phase]
                for row in self.phases
            )
            or self.displayed_model_ids != HELD_MODELS
            or len(self.displayed_model_choice_counts) != len(HELD_MODELS)
            or sum(self.displayed_model_choice_counts)
            != sum(row.displayed_slot_choices for row in self.phases)
            or tuple(row.view for row in self.native) != tuple(NATIVE_VIEWS)
        ):
            raise ValueError("full-game evaluation diagnostic accounting differs")
        return self


class FullGameDiagnosticCollector:
    """Observe accepted steps without modifying policy, memory, commands or RNG."""

    def __init__(self, metadata: game.FullGameMetadata, candidate_seats: tuple[int, ...]) -> None:
        self.metadata = metadata
        if (
            not candidate_seats
            or len(set(candidate_seats)) != len(candidate_seats)
            or any(seat not in range(metadata.player_count) for seat in candidate_seats)
        ):
            raise ValueError("full-game diagnostic candidate seats differ")
        self.candidate_seats = candidate_seats
        self.teacher = FullGameGreedyPolicy(metadata)
        self.accepted = np.zeros(metadata.batch_size, dtype=np.int64)
        self.phase_counts = np.zeros(14, dtype=np.int64)
        self.counts = np.zeros((14, 6), dtype=np.int64)
        self.probability = np.zeros(14, dtype=np.float64)
        self.choices = np.zeros((14, 28), dtype=np.int64)
        self.teacher_choices = np.zeros((14, 28), dtype=np.int64)
        self.model_counts = np.zeros(237, dtype=np.int64)

    def observe(self, step: FullGamePolicyStep, policy: FullGameActorCritic) -> None:
        o = step.observation
        envs = o.leases[:, 0]
        if (
            np.any(envs < 0)
            or np.any(envs >= len(self.accepted))
            or len(np.unique(envs)) != len(envs)
            or not np.all(o.leases[:, 1] == 1)
            or not np.array_equal(o.leases[:, 2], self.accepted[envs] + 1)
            or not np.array_equal(
                step.transition.commands, np.column_stack((o.leases, step.actions))
            )
        ):
            raise ValueError("full-game diagnostics require ordered accepted episode steps")
        rows = np.flatnonzero(np.isin(o.leases[:, 3], self.candidate_seats)).astype(np.int64)
        if len(rows):
            selected = o.take(rows)
            actual = step.actions[rows]
            teacher = self.teacher.actions(selected)
            with torch.no_grad():
                logits, _, _ = policy(full_game_policy_inputs(selected), step.previous_memory[rows])
                argmax = logits.argmax(1).numpy()
                probability = logits.softmax(1)[torch.arange(len(rows)), teacher].double().numpy()
            for i, lease in enumerate(selected.leases):
                phase, action, expected = int(lease[4]), int(actual[i]), int(teacher[i])
                self.counts[phase, 0] += 1
                if selected.policy_gradient_mask[i]:
                    self.counts[phase, 1] += 1
                    self.counts[phase, 2] += int(action == expected)
                    self.counts[phase, 3] += int(argmax[i] == expected)
                    self.probability[phase] += float(probability[i])
                    self.choices[phase, action] += 1
                    self.teacher_choices[phase, expected] += 1
                mode = selected.global_features[i, GLOBAL_FIELDS.index("trade_observations.mode")]
                sell_parcel = phase == 6 and round(float(np.expm1(float(mode) * np.log(100)))) == 2
                if (phase in (1, 2, 4, 7) or sell_parcel) and 1 <= action <= HAND_SLOTS:
                    model = int(selected.card_model_ids[i, action - 1])
                    if model not in HELD_MODELS:
                        raise ValueError("full-game diagnostic slot has no displayed held model")
                    self.counts[phase, 4] += 1
                    self.model_counts[model - 3] += 1
                    rank = {
                        2: "attack_selection_rank",
                        4: "defense_selection_rank",
                        7: "discard_selection_rank",
                    }.get(phase)
                    if (
                        rank is not None
                        and selected.hand_features[i, action - 1, HAND_FEATURES.index(rank)] > 0
                    ):
                        self.counts[phase, 5] += 1
        self.accepted[envs] += 1
        self.phase_counts += np.bincount(o.leases[:, 4], minlength=14)

    def finish(self, configured: game.DevelopmentFullGameBatch) -> FullGameEvaluationDiagnostics:
        if configured.metadata != self.metadata:
            raise ValueError("full-game diagnostic environment contract differs")
        b = configured.batch
        state = b.episode_snapshot()
        if not np.isin(state[:, 3], (12, 13)).all() or not np.array_equal(
            state[:, 7], self.accepted
        ):
            raise ValueError("full-game diagnostics require all endings and accepted commands")
        native = []
        # Private diagnostics enter only this final report, after every command.
        for getter, columns in NATIVE_VIEWS.items():
            values = getattr(b, getter)()
            shape = (
                (self.metadata.batch_size, self.metadata.player_count, len(columns))
                if getter == "acquisition_snapshot"
                else (self.metadata.batch_size, len(columns))
            )
            if values.shape != shape or values.dtype != np.int64 or np.any(values < 0):
                raise ValueError(f"full-game native diagnostic shape or values differ: {getter}")
            native.append(
                FullGameNativeDiagnostic(
                    view=getter,
                    fields=columns,
                    totals=tuple(int(v) for v in values.reshape(-1, len(columns)).sum(axis=0)),
                )
            )
        phases = tuple(
            FullGamePhaseDiagnostics(
                phase=phase,
                candidate_decisions=int(self.counts[phase, 0]),
                voluntary_decisions=int(self.counts[phase, 1]),
                sampled_teacher_agreements=int(self.counts[phase, 2]),
                argmax_teacher_agreements=int(self.counts[phase, 3]),
                teacher_probability_sum=float(self.probability[phase]),
                displayed_slot_choices=int(self.counts[phase, 4]),
                deselections=int(self.counts[phase, 5]),
                candidate_choice_counts=tuple(int(v) for v in self.choices[phase]),
                teacher_choice_counts=tuple(int(v) for v in self.teacher_choices[phase]),
            )
            for phase in PHASES
        )
        return FullGameEvaluationDiagnostics(
            accepted_decisions=int(self.accepted.sum()),
            candidate_decisions=sum(row.candidate_decisions for row in phases),
            candidate_forced_decisions=sum(
                row.candidate_decisions - row.voluntary_decisions for row in phases
            ),
            all_seat_phase_counts=tuple(int(v) for v in self.phase_counts),
            phases=phases,
            displayed_model_choice_counts=tuple(int(v) for v in self.model_counts),
            native=tuple(native),
        )
