# ADR0139: public full-game encoding and transactional seat memory

## Scope and versions

Implements the first part of user-approved ADR0138 against native0.83.0/kernel33,
without changing gameplay, native schemas, existing arenas or live controls.
Observation schema`full-game-public-18-slot-v1` and policy architecture1 are
separate contracts. Full-game training, official fidelity and promotion remain
false. A network forward/backward pass is not a complete training loop.

`FullGameObservationEncoder` requires18 physical slots and at most4096 batched
environments. It supports2–9 players, source-configured99 or100 resource caps
and native teams. It hashes the complete configured environment metadata,
including costs, source pins, bounds, acquisition and team layout. It exposes:

- 112 global features: public phase/actor one-hots, roster and horizon fractions,
  and every column of17 reviewed public action/reaction/event/trade views.
- Nine actor-cyclic player rows of42 features: public absolute seat/team/relation,
  resource/status visibility, guardian visibility and confusion visibility.
- 18 displayed card model tokens with27 features per slot: performed flag,
  ordered attack/defense/removal ranks, displayed passive role/value and position.
- Five separately embedded currently revealed model tokens for guardian,
  generated/virtual action, phenomenon and market parcel, vocabulary0–296.
- The exact28-choice native legal mask and forced-turn policy-gradient mask.

Inactive rows and padded seats/cards have zero features and false masks.
Hidden values retain explicit visibility flags; unknown does not become a known
zero. Numeric context values use signed `log1p(abs(x))/log(100)` without clipping;
resources and horizon fractions use their pinned configured bounds. Metadata
records every field, ordering, allowed getter and transformation.

## Privacy and numeric action semantics

Only29 reviewed getters are allowed. True inventory, private resources/status,
future queue entries, private escrow, RNG and diagnostic counters are not input.
Epoch/decision/instance identities are not learned features. Native five-column
command leases are held separately for accepted six-column commands and memory
dispatch. Hidden actual cards and Fog-hidden opponents can change independently
without changing encoded features when the public situation is the same.

Exchange's amounts, Sell's parcel selection, Buy's purchase menu, discard and
Sacrifice retain native numeric semantics. The policy uses a phase-conditioned
28-logit head, rather than assuming every low choice ID selects a card or every
high choice ID selects an enemy. Sell settles after defense; Buy can open its
purchase menu afterward. Explicit active/model fields distinguish revealed
parcels from pre-defense hidden offers.

## Policy and memory

`FullGameActorCritic` uses displayed model embeddings, separate card/player/
context encoders, a GRU,28 masked logits and a value head. Fixed padded rows are
flattened so per-slot/per-seat identity is preserved. Absent MLP rows are masked
after their bias. No old checkpoint loader or implicit migration is added.

`FullGamePolicyController` performs CPU float32 inference and delegates accepted
steps/terminal credit to ADR0136's reward adapter. Memory is indexed by
environment/epoch/absolute seat and updates only after the native command batch
is accepted. Another seat never inherits it. Failed batches leave native state,
all seat memories and the sampling generator unchanged; no sample receipt is
returned. Explicit reset clears all nine seat states for each reset environment,
including eliminated teammates, and preserves other environments. Raw step/reset
cursor drift is rejected. Forced turns retain their real outcome and memory but
have zero policy-gradient weight.

This captures current public state and ordered selections; it does not add an
official public event-history stream. Rollout credit, recurrent optimization,
checkpoint persistence and held-out useful-learning validation are subsequent
work, not inferred from successful inference or metadata presence.

## Verification checkpoint

505 focused observation/neural/reward tests pass. Cases cover all2–9-player
rosters, padding, privacy counterfactuals, separate command identities, zero-MP
ordered waivers, trade/purchase/discard/Sacrifice phases, corrupt native layouts,
ordinary gradients, rejected-batch rollback, independent seat memory, reset,
forced-turn weights and full-pool episode credit. Static checks pass133 modules.

A separate untrained-network diagnostic runs32 complete local games: eight each
in2-player solo,3-player solo,4-player2v2 and9-player mixed-team layouts. It
accepts12,391 commands across all six active decision phases, with zero engine
errors, illegal moves or truncations. Every present player receives one terminal
credit; repeated reads pay nothing. These are liveness/interface checks, not
candidate win-rate or useful learning. No training job, checkpoint or live game
was changed. Local records:
`/private/tmp/godfield-full-neural-interface-probe.jsonl`.
The full nonbrowser regression passes13,152 tests in218.93s; the older native
scripted replay/metadata pins and arena training/checkpoints remain unchanged.
