# ADR 0019: Bible-verified CP-miracle liveness

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0013, ADR 0015, and ADR 0018

## Context

Private v3 run `c6bc3db9-4a53-4a22-b896-166c69fe9c9b` completed two games and
26 accepted actions before stopping at `unsupported_self_turn`. Dream made
eight displayed hand identities unreliable, so they were correctly excluded.
The only reliable card was `<Treasure>`: the accepted Bible documents `$+10`
for 5 MP, the pinned API catalog identifies model 236 as an untargeted
turn-leading `boostCP` miracle with value 10 and cost 5, and the player had 10
MP. The tactical bridge modeled HP and MP utility but not CP utility.

## Decision

Parse unconditional CP miracles separately from the accepted Bible. Admit a
live action only when the Bible record has no element, exactly `$+N`, `Cost`,
an exact MP cost, and the normal gift-rate suffix, and when the live catalog's
asset, miracle category, `boostCP` ability, value, cost, untargeted shape, and
turn-leading predicate all match. The current accepted Bible admits exactly
`treasure: (10 CP, 5 MP)`.

Serialize the action as a one-card, untargeted API command. The behavior policy
uses CP gain only after cleansers, deterministic attacks, targeted curses,
useful HP/MP recovery, and chance attacks are unavailable, but before a Sell
fallback or safe stop.

Keep CP utility outside the schema-v5 resource-neural macro set and its four
resource-opportunity families. Although CP is observable, the current C++
curriculum has no CP action or purchase economy, so treating this as a learned
resource decision would be false evidence.

Version the changed behavior as `api-combo-utility-heuristic-v4` and the live
evidence contract as `live-resource-shadow-readiness-v4`, report schema 4.

## Consequences

The captured failure state now emits `cp-utility:boostCP:2:236`, serialized as
`{"itemIds":[2]}`. Dream-disguised identities remain excluded. Further CP
economy, purchases, CP transfers, guardians, and arbitrary miracle choices
remain outside the reviewed surface.
