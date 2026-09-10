# ADR 0021: Ambiguous command reconciliation

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0003, ADR 0017, and ADR 0020

## Context

Private run `55bbcd08-063b-46c7-a477-6966aee6ac21` recovered from an earlier
transient room-state read and accepted two actions. Its third action submitted
Direct Smash Axe from a valid self turn, waited 18.37 seconds, and then raised
`TransportError`. The runner correctly did not replay the command, but it
immediately ended the session.

Pygodfield deliberately disables HTTP retries for `submit-command`: a lost
response does not reveal whether the server consumed the turn or card. A later
room snapshot can reconcile that uncertainty without another write. Ending
before obtaining such a snapshot discards a safe recovery opportunity.

## Decision

Classify a `TransportError` raised by command submission as an ambiguous
response. Record one action result with `server_acknowledged=null` and a
sanitized error event, count the dispatched command against the in-match action
budget, and do not submit it again.

Continue read-only room polling. If the normalized state digest changes, record
the transition and resume ordinary policy execution from the new state. An
unchanged read neither repeats the command nor reruns the policy. If no changed
state appears within 30 seconds by default, fail with the explicit reason
`ambiguous submit could not be reconciled before timeout`. The reconciliation
window is configurable from one through 300 seconds with
`--command-reconcile-seconds`.

State-read retry limits and the wall-clock limit remain active during
reconciliation. The generic no-progress timer yields to the dedicated,
explicit reconciliation timer. Other API errors still fail closed, while
explicit HTTP 400 command rejections continue to use ADR 0020's unchanged-state
retry path.

## Consequences

A dropped submit response no longer tears down a healthy session when the room
subsequently advances. The runner never guesses that an ambiguous command
failed and never risks a duplicate turn. Persistent uncertainty is bounded and
fully visible in the local event stream. Tactical action selection remains
unchanged, so the behavior identifier stays `api-combo-utility-heuristic-v4`.
