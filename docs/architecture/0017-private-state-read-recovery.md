# ADR 0017: Bounded private room-state read recovery

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0003

## Context

The synchronous pygodfield room-state reader converts temporary Firestore
request failures into `TransportError`. A private run previously treated every
such error as fatal. Live evidence from run
`f42174f3-57d1-4d21-9126-f6c6e192d7ba` showed four acknowledged game actions
followed by a status-less transport failure during a room read. No policy or
command rejection preceded the failure.

Reads are idempotent, but submitted game actions are not. Retrying both through
one generic recovery mechanism could submit a turn twice after an ambiguous
response.

## Decision

Retry only `TransportError` raised by `client.state()`. A missing HTTP status is
treated as a retryable network failure, as are 408, 425, 429, 500, 502, 503,
and 504. Other HTTP responses fail closed without retry, including
authentication and authorization failures.

The default read budget is five retries with exponential delays starting at
one second and capped at 30 seconds. A successful room read resets the
consecutive-failure count. Each failed read is recorded as a sanitized error
event containing the operation, status when available, attempt, budget, delay,
and whether another read was scheduled. Exhaustion produces an explicit failed
run outcome. The wall-clock, no-progress, and action-count limits remain
independent.

Never retry `submit`, lobby entry, team changes, or other writes at this layer.
Their server outcome can be ambiguous, so existing fail-closed behavior and
transition evidence remain unchanged.
