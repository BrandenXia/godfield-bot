# ADR 0022: Visible-weapon Prayer validation and Absorption liveness

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0011, ADR 0015, ADR 0019, and ADR 0020

## Context

Private run `7f9fdd8a-955a-4ff7-ade9-8e0f2eb55131` made progress for almost
twelve minutes, including 23 server updates, before an empty attack-turn
command received HTTP 400 on the initial submission and both bounded retries.
The normalized state was unchanged, proving this was not a transient rejection.

The displayed hand contained Unknown Feather, an additive `+ATK7` weapon that
cannot begin an attack. The old conservative action surface found no base
weapon and offered Prayer as its fallback. The official client bundle's current
command validation instead rejects Prayer whenever the displayed hand contains
any weapon-class artifact. The rule is based on the displayed identity, which
preserves Dream's information boundary.

The same captured hand contained `<Absorption>` with exactly 10 available MP.
The accepted Bible records a light `ATK10`, automatic `Absorb HP` effect, and
10 MP cost. The accepted API catalog matches model 216's asset, attack, element,
cost, `absorbHP` ability, targeted shape, and turn-leading predicate.

## Decision

Suppress an empty command on an uncursed attack turn whenever any non-used
displayed card has category `weapons`. Continue allowing an empty defense
command, and continue allowing Prayer when the displayed hand has no weapon.
If a visible weapon exists but there is no reviewed turn-leading action, fail
closed as `unsupported_self_turn` instead of submitting an invalid command.

Parse automatic-effect attack miracles separately from the plain fixed and
chance miracle families. Require an exact Bible shape, one combat element,
fixed attack, explicit MP cost, ordinary gift-rate suffix, and a hard-coded
mapping from the Bible effect to the API ability. The initial mapping contains
only `Absorb HP` to `absorbHP`. At runtime, require an exact match on asset,
attack, element, cost, ability, affordability, reliable identity, targeted
shape, and turn-leading predicate.

Serialize Absorption as the one-card targeted command. Keep it outside the
schema-v5 neural resource macro set and resource evidence counts because the
native curriculum does not yet model healing from dealt damage.

Version the changed behavior as `api-combo-utility-heuristic-v5` and the live
evidence contract as `live-resource-shadow-readiness-v5`, report schema 5.
Earlier behavior evidence cannot satisfy the new gate.

## Consequences

The captured failure state now emits
`effect-miracle-attack:9:216:2`, serialized as
`{"itemIds":[9],"targetPlayerId":2}`. It cannot emit Prayer. Unknown automatic
effects, additive-only hands with no reviewed leader, Exchange, general
Discard/Sacrifice, and other unmodeled choices continue to fail closed.
