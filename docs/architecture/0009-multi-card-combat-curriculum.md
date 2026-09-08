# ADR 0009: Sequential multi-card combat curriculum

- Status: **Accepted**
- Date: 2026-09-08

## Context

The elemental curriculum resolves one weapon or armor card per phase. The live
rules also permit a base `ATK` weapon followed by additive `+ATK` weapons, and
permit multiple compatible armor cards to contribute defense. Representing a
combination as one action would require a combinatorial action head and would
hide the intermediate choices needed for debugging and learning.

The extension must be bounded, must never strand a policy in an unfinished
selection, and must not silently reinterpret the existing schema-v3 elemental
checkpoint.

## Decision

Add `plain-elemental-combo-attack-defense-redraw-duel-v1` as an independent
native ruleset. Its accepted-snapshot catalog contains 39 effect-free base
weapons, 17 effect-free additive weapons, and 47 effect-free armor cards.
Initial hands contain four base weapons, two boosters, and three armor cards in
deterministically shuffled slots. Consumed slots redraw uniformly from the
combined catalog, with the existing base-weapon liveness repair.

Keep the 21-action policy head. Actions 1 through 9 select visible hand slots,
action 19 is Forgive, and action 20 is Confirm. During attack selection the
first card must be a base weapon; subsequent selections may only be boosters.
Confirm is legal after the base selection. During defense, every selected armor
must independently be compatible with the pending attack element. Forgive is
legal before selecting armor; after any selection, Confirm is always legal.
Selections cannot be toggled or cancelled, so at most nine selections precede
resolution.

Selected cards remain owned until Confirm, but their visible token, kind, and
hand mask are cleared. Diagnostics expose the selected-slot mask, count,
aggregate value, and aggregate attack element. Defense values sum. Attack
elements follow the accepted rule and API behavior: identical elements remain,
Light can substitute for Fire, Water, Wood, or Stone, and every other mixture
becomes Non-element.

Observation schema v4 retains 13 global inputs. In attack selection, global
input 5 holds the selected aggregate attack and inputs 6 through 12 hold its
element. In defense, those positions continue to hold the pending incoming
attack and element. The live browser encoder uses the same outgoing-selection
semantics when the game exposes an aggregate `ATK` display.

`models migrate-combo-features` creates a schema-v4 model from schema v3 using
an exact parameter copy. Although tensor shapes are unchanged, the manifest
records the semantic migration so schema-v3 models cannot be used against the
new ruleset accidentally. Training and evaluation require exact agreement
between model feature schema and simulator observation schema.

## Consequences

Selection trajectories are longer than atomic combat trajectories, but their
branching factor remains bounded and their intermediate state is observable.
The versioned greedy heuristic always selects a base attack, consumes available
boosters, and confirms; on defense it accumulates the largest compatible armor
until sufficient, then confirms, or uses Forgive when no armor is available.

This remains non-promotable. Resource costs, special booster effects, attack
doubling, counters, status effects, miracles, guardians, trading, and full
multiplayer resolution remain outside this curriculum.
