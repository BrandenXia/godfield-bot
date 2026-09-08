# ADR 0008: Elemental single-card combat curriculum

- Status: **Accepted**
- Date: 2026-09-08

## Context

The mixed-hand curriculum teaches card-role recognition, but excludes every
elemental weapon and armor card. Elemental defense changes legal actions,
Light attacks cannot be blocked, and a Darkness attack is lethal when any
damage penetrates defense. The policy therefore needs the pending attack's
element in addition to the attack value and visible artifact identities.

This expansion must preserve old simulator trajectories and make checkpoint
compatibility explicit rather than silently changing an input tensor.

## Decision

Add `plain-elemental-mixed-hand-attack-defense-redraw-duel-v1` as a separate
native ruleset. Its catalog contains only single-card weapons and armor whose
accepted Bible entry is exactly a name, fixed `ATK` or `DEF`, price, and gift
rate, with either no element or exactly one recognized combat element. The
2026-09-07 accepted snapshot yields 39 weapons and 47 armor cards.

The compatibility table is:

| Attack | Legal armor elements |
| --- | --- |
| Non-element | Any |
| Fire | Water or Light |
| Water | Fire or Light |
| Wood | Stone or Light |
| Stone | Wood or Light |
| Light | None |
| Darkness | Any |

Defense subtracts `DEF` from `ATK`. A Darkness attack sets the defender to zero
HP only when the resulting damage is positive; a full block survives. Existing
mixed-hand redraw and attack-liveness behavior remains in force.

Observation schema v3 keeps the six schema-v2 global values in place and
appends a seven-way pending-element one-hot in the order Non-element, Fire,
Water, Wood, Stone, Light, Darkness. It is zero outside the defense phase. The
native batch also exposes read-only hand and pending element IDs for diagnostics.

Feature-schema-v2 checkpoints remain loadable for historical fixed-role and
mixed-hand evaluation. `models migrate-element-features` creates a new
feature-schema-v3 baseline by copying every parameter and expanding only the
first global encoder matrix. Its first six columns are preserved and the seven
new columns are initialized to zero, so neutral-state logits, values, and
recurrent states are initially identical. The migrated manifest records the
source model, algorithm, target schema, and initialization.

## Consequences

Elemental training and evaluation reject six-global models, while the older
rulesets reject 13-global models. Their simulator metadata records the global
feature count, catalog digest, ruleset ID, observation schema, and sampling
distribution. The elemental heuristic gets its own policy ID and recognizes
the expanded catalog.

This remains a deliberately narrow, non-promotable curriculum. Multi-card
attack/defense totals, resource costs, status effects, counterattacks, miracles,
guardians, trades, and multiplayer rules require later versioned expansions.
