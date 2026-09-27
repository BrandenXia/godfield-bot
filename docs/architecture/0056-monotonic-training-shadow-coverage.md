# ADR 0056: Monotonic Training-shadow coverage gate

## Status

Accepted, 2026-09-27.

## Context

The first official-Training readiness gate required both a 98% Wilson lower
bound on exact-view coverage and no more than five exact-view encoding gaps.
The absolute limit was intended to keep adapter gaps rare, but it made the gate
non-monotonic: once a sixth safe abstention was observed, no amount of later
covered evidence could make the same immutable candidate ready.

Prospective candidate `088ef7a5-c8bf-46e2-8469-4d2390719839` exposed this
failure after 21 evidence-bearing runs. It covered 370 of 376 exact-view
opportunities and safely abstained six times when an artifact beyond the
schema-v10 nine-slot hand was selectable. No unsupported action was proposed or
executed. The 98.40% point estimate remained below the required 98% Wilson
lower confidence bound because the cohort was still small.

The same audit also exposed two classification bugs. A pre-game setup timeout
with no shadow evidence was counted as a failed evidence run, and an aborted
departure marker was treated as a typed terminal outcome requiring an adjacent
reward. Neither event contained candidate behavior to audit.

## Decision

Version the admission behavior as `official-training-shadow-readiness-v2`.
Retain exact-view gaps in the denominator and preserve the 98% Wilson lower
confidence-bound requirement, but remove the default absolute gap-count cap.
This makes readiness monotonic: additional covered evidence can increase
confidence, while additional gaps continue to reduce measured coverage.

The schema-v10 adapter remains fail-closed. Hidden statistics, selectable
overflow slots, and every other encoding error produce no candidate proposal;
the heuristic retains control. The report continues to expose the gap count and
reasons. An explicit non-default absolute cap remains available in the typed
configuration for focused tests or future stricter gates.

Exclude a configured run from the evidence cohort when it ended before writing
any official-Training shadow evidence. Count an interruption after evidence as
an operational abort. Accept the runner's two versioned unclassified terminal
candidate markers only on aborted runs and only without a reward; typed terminal
outcomes retain the exact adjacent reward and normalized-state checks.

Readiness report schema 1 remains structurally compatible and now accepts both
v1 and v2 gate identifiers. This preserves already issued v1 canary admission
reports. New evaluations emit v2 and bind the changed configuration into their
input digest.

## Consequences

The collected cohort still does not pass automatically. It must reach at least
500 exact-view opportunities, a 98% Wilson coverage lower bound, 20 completed
games, and a 0.80 Wilson completion lower bound. The redesign removes only the
impossible absolute-count condition; it does not authorize an overflow action,
widen canary scope, promote the model, or establish official-game strength.

Expanding the native model beyond nine hand slots remains a separate simulator
fidelity milestone. Until then, every selectable overflow state stays under
heuristic control.
