# ADR 0077: Count native catalog inclusion separately from game fidelity

## Status

Accepted, 2026-09-29. This is a read-only audit, not a new ruleset or a
training-ready declaration.

## Decision

Expose the exact token IDs configured in the native attack/defense curriculum
without adding them to versioned observation or checkpoint metadata. A
`simulation coverage-report` command compares these IDs with the pinned Bible
artifact vocabulary. It fails closed on duplicate IDs, metadata count drift,
or non-artifact tokens, and lists every omitted artifact by category. The
report's scope is explicitly *artifact inclusion only*: inclusion is not
evidence of correct semantics, probabilities, interactions, or official parity.

The 2026-09-20 Bible lists 291 artifacts. The current wide-hand,
gift-weighted Dream curriculum configures 196 unique artifacts; the other 95
are 42 guardians, 17 armor, 10 phenomena, 9 sundries, 7 miracles, 5 devils,
and 5 weapons. The provisional Soap projection is not part of the batch
kernel and remains among the nine omitted sundries. The verified Nocturnal
Broom inventory-replay primitive is also not part of that kernel. The report
therefore sets full-game training readiness, official fidelity, and promotion
eligibility to false regardless of the included count.

## Consequences

The gap is now reproducible and can drive a versioned provisional curriculum
rather than silent additions to existing checkpoints. Each new mechanic must
define its state, action/phase semantics, randomness, inventory and resource
effects, and observation tests. Separate curriculum identities and promotion
checks are required when provisional behavior is added. Reaching 291/291
artifacts would be necessary for complete catalog coverage, but still would
not prove a full game: guardians, devils, phenomena, economic actions,
multiplayer interactions, and official parity require independent tests.
