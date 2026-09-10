# ADR 0020: Confirmed command-rejection recovery

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0003 and ADR 0017

## Context

Private v4 run `6a616ec6-9b98-40ea-a05c-63213c09b258` completed two games and
28 accepted actions before the server rejected an empty turn command with HTTP
400. The normalized state was an ordinary self attack turn and the same command
shape had been accepted in earlier live matches. Run
`e529c3c6-6ceb-4eeb-88f8-934306fb654c` ended on the same response shape.

The pinned pygodfield bot driver distinguishes a Cloud Function's explicit 400
rejection from a network or transport failure. The former confirms that the
command was not accepted and can be retried after another state read. The
latter has an ambiguous server outcome and must never be repeated blindly.
Our observable runner used pygodfield's direct client and was missing that
distinction.

## Decision

Treat only an API error for `submit-command` with integer HTTP status 400 as a
confirmed rejection. Record its action result with `server_acknowledged=false`
and a sanitized error event. Before retrying, obtain a new successful room
read and require its normalized state digest to match the state from which the
command was selected. Reuse the recorded action without rerunning the policy or
advancing neural shadow state.

Allow two retries after the initial rejection by default, configurable from
zero through five with `--command-retries`. Every retry gets its own action
result, error event, and observed transition. A changed state cancels the
retry. Budget exhaustion remains a failed run rather than an unbounded loop.

Do not retry transport failures, missing responses, authentication failures,
other HTTP statuses, or any other write. Their server outcome is not proven.
The read-recovery rules from ADR 0017 remain unchanged.

## Consequences

Transient 400 responses no longer terminate an otherwise healthy multi-match
session on the first occurrence. The trajectory store makes rejected attempts
and recovery visible while keeping server response bodies out of persisted
events. Since the selected tactical action and its ordering are unchanged, the
behavior policy remains `api-combo-utility-heuristic-v4`.
