# ADR 0023: Private-room membership recovery

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0003, ADR 0017, ADR 0020, and ADR 0021

## Context

Continuous private run `378242a8-22d4-4b6d-a533-52526881a186` received an
ambiguous transport response while submitting a Wall defense. The action was
not replayed and the room was polled for reconciliation. The next changed game
snapshot marked ロキ-67 as `isBot=true`, although every earlier snapshot had
marked the seat as connected. The match later ended in a classified win, after
which `make-entry` received HTTP 403.

The evidence indicates that the account lost room membership while the server
kept its player seat under bot control; the post-game entry failure was a
consequence rather than the original fault. The runtime retained a local room
ID and kept reading the document, but it never verified `users[]` membership
after the initial join.

The accepted official client bundle checks the current Firebase UID against
each room snapshot. If it is absent and not denied, the client submits
`join-room` and returns before rendering or acting on that stale snapshot.

## Decision

After every successful room read, verify that the persistent ロキ-67 UID is in
the room's `users[]` list before processing lobby or game state. Treat the
initial join as pending confirmation so Firestore propagation cannot cause a
duplicate request. Once membership has previously been confirmed, a missing UID
causes exactly one `join-room` request using the already selected internal room,
mode, identity name, and operator-supplied private-room key.

Record a sanitized `membership_rejoin_requested` observation containing only
whether a game exists and whether it is over. Do not record the internal room
ID or key. Do not normalize the stale game snapshot, invoke either policy, or
submit a game command until a later room read confirms membership. A successful
rejoin request resets the no-progress clock; failure to observe confirmation is
still bounded by the existing no-progress limit.

Also treat only an explicit `make-entry` HTTP 403 after at least one completed
game as a temporary post-game transition rejection. Record each rejection and
retry after exponential delays of 1, 2, 4, 8, then at most 10 seconds. Initial
entry failures and other actions or statuses remain fatal. Repeated post-game
failure remains bounded by the no-progress timer.

## Consequences

A transient membership loss no longer leaves the match under server bot control
for the rest of the session, and the runner cannot act concurrently from a stale
bot-controlled snapshot. The post-game 403 from the captured run no longer ends
an otherwise unlimited campaign. This changes connection lifecycle handling,
not the tactical legal-action set or selection order, so the v5 behavior and
live evidence identities remain unchanged.
