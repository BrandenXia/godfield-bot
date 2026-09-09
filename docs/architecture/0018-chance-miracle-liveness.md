# ADR 0018: Bible-verified chance-miracle liveness

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0011, ADR 0015, and ADR 0016

## Context

Private run `f72c145b-dd35-4f02-b8d0-b266352db916` completed three games and
33 accepted actions before stopping at `unsupported_self_turn`. The final state
was a cursed turn with 35 HP and 10 MP. No cleanser, deterministic base attack,
HP/MP utility, targeted curse, or valid Sell pair was available. The hand did
contain `<Thunder>`, documented by the accepted Bible as `25%ATK10` for 4 MP
and represented by the pinned API catalog as model 227 with a 25 percent hit
rate. Pygodfield classifies this as an untargeted turn-leading card.

The prior tactical surface intentionally excluded chance attacks. Treating the
resulting safe stop as an operational error is useful evidence, but repeatedly
ending continuous sessions on a fully described, directly serializable action
is no longer useful.

## Decision

Add a separate Bible parser for plain probabilistic miracles. It accepts only
five-field miracle records with exactly one combat element, `%ATK` syntax, an
explicit MP cost, and the normal gift-rate suffix. The current accepted Bible
contains six such cards. Miracles with additional effects, including
`<Flash>`, remain excluded.

Expose an untargeted `chance-miracle-attack` action only when the live catalog's
asset, hit rate, attack, MP cost, element, category, ability, additive flag, and
turn-leading predicate exactly match that Bible record. The command contains
only the card instance ID and no target. The tactical heuristic considers these
actions after deterministic attacks, targeted curses, and useful HP/MP
recovery, but before speculative trade fallback or an unsupported stop. A
chance attack is never classified as guaranteed lethal.

This action family remains outside resource-neural shadow macros and live
resource opportunity counts. It broadens only the behavior adapter's reviewed
liveness surface; it does not pretend the current C++ curriculum or candidate
learned probabilistic outcomes.

Version the changed behavior as `api-combo-utility-heuristic-v3` and the live
evidence contract as `live-resource-shadow-readiness-v3`, report schema 3.
Earlier behavior evidence cannot satisfy the new gate.

## Consequences

The captured failure state now emits
`chance-miracle-attack:2:227:untargeted`, serialized as `{"itemIds":[2]}`.
Unknown random effects, discretionary choices, phenomena, guardians, general
trades, and purchase acceptance still fail closed.
