# ADR 0101: Separate full-game engine and decision-scoped command protocol

## Approved architecture

2026-10-01. The user explicitly chose a separate versioned C++ full-game
environment reusing tested components. Preserve the existing guardian arena,
legacy curricula, models, logs and live controls. Provisional mechanics may
support local training once complete; official verification/promotion remains
an independent gate. This records the integrated design before implementation.

The initial code here is a strict **command admission contract**, not a native
engine implementation. No gameplay, costs, counters, masks, RNG, decisions or
episodes are executed/advanced by it. Source catalogs stay pinned as in ADR 0100.

## One authoritative episode state

The new native batch will own each episode's resources/statuses, ordered true
and displayed inventories, team/seat map, guardians, pending effects, phase,
acting player, turn count, RNG streams and terminal/truncation reason. Reuse
verified/provisional calculations from existing components, not their separate
automatic turn schedulers. No Python-controlled hidden resource overrides or
two independent schedulers may govern the same episode.

Stage complete per-episode transactions before committing a batched decision.
Validate every selected item, resource cost, target and phase across the entire
batch first; failures cannot partly pay MP, use a miracle, apply a cure or move
another environment. Status restoration and inventory display restoration must
commit together. Diagnostic sync/replay paths stay separate from learner moves.

Start with a vertical slice joining inventory, HP/MP/CP, documented cures and
bounded round-robin progression. Then integrate combat combinations/defense,
guardian and event timing, economy/removal/revival, overflow, apocalypse and
multiplayer/team transitions. Each family must be reachable in this same engine;
registration alone or another isolated primitive is not completion. Unsupported
effects are explicit development failures, never silently successful no-ops.

## Decisions and liveness

Every episode has a monotonically increasing reset epoch. Every accepted policy
decision advances a native decision counter, including selections that do not
finish a turn. Native legality supplies an ephemeral public choice table rather
than interpreting an old 21/30/48-action model. This keeps commands independent
of the eventual neural action-head design; that design and any learned-weight
migration will be decided explicitly after the complete phase contract works.

Schema-1 `FullGameCommand` contains only environment, episode, decision, actor,
phase and public choice ID. No true model IDs, opponent inventory, RNG tickets
or resources are action payloads. The engine resolves a valid current choice
through its authoritative state. A stable card/miracle ID is not sufficient to
authorize an old or duplicate move after the phase or reset changes.

`FullGameDecisionContext` is a trusted adapter projection with legal choice IDs.
The new Python `validate_full_game_commands` validates the whole batch against
those contexts, rejects duplicate environments, and preserves command order.
Native commit **must recheck** the same tokens; Python validation neither
advances counters nor establishes exactly-once execution by itself. Repeating
admission against an unchanged context is deliberately harmless, not execution.

Keep this object validation at diagnostic/CLI/adapter boundaries, not in the
high-throughput training inner loop. The native binding will admit packed
contiguous integer command arrays and validate tokens/legality in C++; Python
must not copy every hand or build Pydantic models for every simulated move.
The eventual packed phase enum/layout gets its own native schema and parity
tests against this human-readable contract before rollout integration.

Planned phase families are ready, attack/target selection, defense/redirect,
trade responses, removal/revival/overflow, event choices, automatic, terminal
and truncated. Their names in the protocol do not imply implemented mechanics.
Interactive contexts require a nonempty legal choice set; automatic/ended
contexts have none. Automatic transitions use an internal bounded effect stack
and cannot wait forever for policy input. Selection limits, redirect/event depth,
turn and decision budgets produce explicit **truncations**, not fabricated draws
or wins. Bounds and provisional policies belong in the versioned manifest.

## Observation, training, and readiness

Assemble policy observations actor-relatively with explicit visibility flags,
own displayed hand only, public phase/history, seat/team map and legal choices.
Exclude actual/fake diagnostics, internal tickets, lifetime counters and numeric
instance handles. Do not concatenate scheduler hit/recipient calculations into
policy features. Keep diagnostic all-seat snapshots on a separate named path.

Initial behavior tests exercise two through nine seats and teams, but current
duel signed-advantage training is not reused for arbitrary multiplayer rewards.
The neural adapter must identify the new state/action schema, reset recurrent
memories per episode/seat, and report wins/losses/draws/truncations separately.
The retained checkpoint and frozen league remain unchanged.

The eventual full-game gate in ADR 0097 still requires every artifact and held
trade route, all phase/event interactions, deterministic replay, source/effect
ledgers, atomicity/visibility/liveness tests, and full-episode learning probes.
Before that, the new engine is developmental and cannot enter existing training
or live-promotion registries. No completeness flag is changed by this plan.

## First contract verification

Tests cover context matching, wrong actor/phase, stale reset and decision tokens,
unchanged reusable-card choices after advancement, late-row rejection, duplicate
environments, strict safe-integer bounds, noninteractive phases, bounded unique
choice tables, unchecked-model-copy tampering and deterministic serialization.
These are protocol tests, not native execution, legal-effect or liveness proof.

All 33 protocol tests pass, including strict schema-version integer checks.
The full non-browser suite passes 2,135 tests; the two existing local browser
fixtures also passed earlier in this work. Ruff/formatting, strict typing across
85 source modules, offline lock consistency and whitespace checks pass. The
native package stays 0.49.0 because this contract adds no compiled engine yet.

Follow-up: ADR 0102 introduces native 0.50.0's first integrated state/transaction
slice and adds explicit noninteractive setup phase 0. It does not complete the
remaining engine design or change the current arena's training eligibility.
