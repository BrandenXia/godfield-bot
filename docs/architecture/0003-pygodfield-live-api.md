# ADR 0003: Pinned pygodfield live-game adapter

- Status: **Accepted**
- Date: 2026-09-07
- Amends: ADR 0001

## Context

The initial architecture kept all game control in the visible browser because
God Field has no documented public API. The operator has since selected
[`xu-shawn/pygodfield`](https://github.com/xu-shawn/pygodfield) as the live API
adapter. It implements the protocol observed in the shipped web client:
Firebase anonymous authentication, Cloud Function commands, and Firestore room
state.

This is an unofficial, reverse-engineered client rather than a stable service
contract. Its Training mode has no server-side game and cannot be driven by its
bot runner. A real API match therefore requires an operator-owned private room
with at least two participants. Public Duel remains outside the approved
scope.

## Decision

Depend on package `godfield==0.1.0` at exact Git revision
`679527115909cf9b516e6365b28c3221a33f3855`, resolved and locked by uv. Do not
track a moving branch. An upgrade requires review of its protocol behavior,
offline test suite, state schema, command construction, and credential
handling.

Use pygodfield as the transport and wire-model layer for private live games.
Keep these project-owned boundaries around it:

- The existing `ロキ-67` browser identity is the only account the adapter may
  use. Enabling API access is an explicit migration from its Firebase browser
  session, not an anonymous sign-up.
- The browser profile and API token file share one exclusive identity lock.
  The token file is outside the repository, owner-readable only, and its user
  ID must match the one-way fingerprint already recorded for the browser
  identity. A missing, corrupt, or mismatched file fails closed before the
  upstream client can create a replacement identity.
- The normalized policy observation includes the bot's own hand plus public
  player statistics and hand counts. Opponents' item instance IDs, model IDs,
  names, and stats are discarded even if the room document exposes them.
  Declared attack cards remain observable because they have been played.
  A transient own-hand placeholder without a model ID is retained as an
  unknown, non-actionable item instead of terminating the session or inventing
  an identity for it.
- A project-owned legal-action layer converts only reviewed actions into
  pygodfield commands. The initial surface is deliberately incomplete:
  passing, declining a purchase, and conservative single-card actions. Unknown
  phases and future effects must not be guessed.
- The adapter never enters public Duel and never calls pygodfield's chat
  method. Private-room passwords are secrets and must not appear in logs or
  ordinary command-line arguments.

Retain Playwright for account bootstrap and continuity checks, browser-local
Training games, visible-client contract verification, and comparison against
the API adapter when protocol drift is suspected. This replaces ADR 0001's
blanket ban on undocumented endpoint use; all other safety and observability
requirements remain in force.

The current item catalog is captured through pygodfield's catalog loader into
a checksummed, versioned snapshot. The 2026-09-07 English API catalog has 296
models: the same 291 artifact records shown across the seven existing Bible
categories plus five `trade` models.

The first runtime is `api-observer-v0`. It can use a private matchmaking key or
an internal room ID, records lobby progress and normalized active-game states
in the append-only run store, emits sparse terminal outcome evidence, and
always has an in-match action budget of zero. It remains a spectator by
default; entering the next match requires a separate explicit flag. Room IDs
are stored only as a one-way fingerprint. An optional room key is read without
echo or from a regular owner-only file and is never copied into events,
configuration, or logs.
The existing browser replay exporters intentionally reject these API-specific
state and action schemas; a reviewed feature/action conversion must land before
private-game evidence can enter model training.

The first executable policy is `api-heuristic-v0`, gated behind the separate
`api play-private --confirm-play` command, explicit next-match entry, a hard
action budget, optional wall-clock limit, and no-progress limit. A wall-clock
value of zero disables only that limit. It ranks only the
project-owned conservative action set: the strongest eligible single weapon on
an attack turn, the strongest eligible single defense, decline an unmodeled
purchase, remove curses with the reviewed `removeAllCurses` action, or pass
when the turn is not curse-constrained. It submits at most once per observed
state and never retries an ambiguous turn-consuming request. Every decision, dispatch result, and
observed transition is recorded. This policy is a data-collection baseline,
not a learned or promotion-eligible policy.

## Learning boundary

pygodfield is a live environment adapter, not the high-throughput learning
environment. The C++ simulator from ADR 0002 remains the primary rollout
source. Completed private games will be normalized into the same append-only
trajectory and sparse terminal-outcome pipeline used by browser observations.
No model may receive opponent hidden-card identities as features, and no
candidate may be promoted solely from the narrow simulator curriculum.

## Consequences

Live control becomes less brittle and more observable than coordinate-level
browser automation, but it now depends on an unstable external protocol and
project. Exact pinning, protocol fixtures, rate limits, idempotency safeguards,
and fail-closed schema checks are required.

The upstream README labels the project MIT, but the selected revision does not
contain a standalone license file or package license metadata. Dependency use
can continue for local development, but redistribution or source vendoring
requires resolving that licensing ambiguity first.
