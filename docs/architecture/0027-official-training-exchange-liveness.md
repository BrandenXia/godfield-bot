# ADR 0027: Last-resort Exchange liveness in official Training

- Status: **Accepted**
- Date: 2026-09-11
- Amends: ADR 0012, ADR 0022, and ADR 0026

## Context

Candidate-controlled Training run `a68e48a3-a0c6-41c0-b105-1f2ca575f2a7`
made 20 accepted actions before stopping at its bounded no-progress limit on
field 15. The final repeated observation was the bot's empty `Pray` phase under
Dream. Its displayed hand contained a masked weapon and two armors, none with a
clickable hit target. The current client still exposed unique clickable
`trade/exchange` and `trade/buy` controls.

Prayer cannot be submitted while a displayed weapon exists. Waiting could not
change this client-local state, so the previous fail-closed action surface
created a deterministic deadlock.

The exact-pinned pygodfield catalog model independently classifies Exchange and
Buy as turn-leading trade actions. It classifies Buy as targeted and models its
subsequent purchase decision, while Exchange is untargeted. This is supporting
protocol evidence only; official Training remains browser-local.

## Decision

Admit one explicit browser `exchange` action only when all of these conditions
hold in the same observation:

- the verified actor is the bot and the action display is empty `Pray`;
- a displayed weapon suppresses Prayer;
- no reviewed weapon, miracle, or HP/MP utility candidate is clickable;
- the empty left action panel remains clickable; and
- exactly one visible `trade/exchange.webp` has a hand-area pointer target.

The executor re-derives the actor, `Pray` display, empty action panel, exact
Exchange asset, unique location, and pointer target immediately before the
selection click. The following observation must expose the selected Exchange
asset, no action display, no target, and the left action-panel hit target before
a separate confirmation click is admitted. This exact intermediate shape was
already captured at sequence 518 of run
`acdc3664-8a69-4b5d-89db-ad12782b76b0`. Both executors repeat their DOM checks
immediately before clicking. A mismatch raises `BrowserContractError` rather
than clicking by stale coordinates.

Exchange is deliberately outside the existing 21-action neural head. A neural
controller resets recurrent memory and delegates this liveness decision to the
audited heuristic. Outcome replay therefore preserves the same fallback
boundary and does not train the model as if it selected Exchange.

Do not admit Buy. Its target and purchase-response phases need separate state,
action, executor, and replay contracts before it can be controlled safely.
Private API behavior is unchanged.

## Consequences

The captured Dream state now exposes `wait` and `exchange`; the heuristic
selects Exchange and can progress instead of timing out. Ordinary turns still
prefer reviewed playable artifacts, and Exchange is not offered merely as a
tactical alternative. Oversized hands also fall back before action-head
indexing, so both failures found in the same validation cycle are bounded and
observable rather than process crashes.
