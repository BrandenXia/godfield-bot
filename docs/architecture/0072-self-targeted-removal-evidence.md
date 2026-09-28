# ADR 0072: Passive self-targeted removal evidence

## Status

Accepted, 2026-09-28, for evidence collection only. No official game was started.
Normal policy, targeted-miracle collection budget, C++ kernel/native 0.35.0,
native replay schema 2 and allowlists, curricula, checkpoints, live control,
promotion gates, and API dependency remain unchanged.

## Existing evidence

After ADR 0071 verified explicit Flame first use and reuse, all ten locally saved
acquisition runs were inspected using a read-only SQLite connection. They contain
385 batches (165 v1, eight v2, 47 v3, 165 v4) and 202 distinct server snapshots.
No reviewed `removeItems`, `removeUsedMiracles`, `removeSomething`, `discard`,
`redraw`, or `replaceItems` event, or self-bound gift overflow item, was captured.
The maximum raw owned array length is 18, which includes possible placeholders
and is not proof of the game's hand capacity. Missing/redacted bodies and absent
event observations cannot establish that a rule never occurs.

The old probe also deliberately redacted removal bodies even when a known
recipient could be derived. Waiting for more games without fixing that gap
would not produce an explicit removal trace.

## Narrow pinned-client interpretation

Reviewed client SHA256:
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
Catalog SHA256 remains
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.

The pinned dispatcher's `removeItems` and `removeUsedMiracles` handlers choose
the opposite pending combat role when it has a player, otherwise the current
role; they pass the event's `items` array to `ds`/`kr`. That routine removes
owned display entries only when the role's player is self. `removeUsedMiracles`
also calls the recipient's `e8` used-miracle display update. Neither recipient
is resolved from the effect's explicit `playerId` field. `gan` confirms the same
opposite-role-first recipient lookup. These handlers establish payload ownership
for the selected case, not a universal removal algorithm or random selection rule.

Capture v5 admits only the narrower **fully seeded distinct two-player duel**:
ordered `advanceGF` and `setTargetPlayer` context, optionally the already reviewed
v4 reflection swap, identify the target. If that target is self, sanitized item
bodies and wire classifications are saved. If it is the opponent, bodies and
wire shapes remain redacted. An explicit self player ID never overrides a missing
or contradictory phase recipient.

Fallback-to-current-role cases, unknown roles, self-targets, more than two
players, source/server gaps, membership changes, unknown/default-deny effects,
`removeSomething`, and `discard` remain unresolved. Both newly admitted removal
effects **clear**, rather than preserve, carried phase context. They cannot bind
subsequent selections or removals without a new verified phase anchor. No new
browser requests, commands, selected actions, or policy authority are introduced.

## Versioning and transport

New installations use capture schema 5 and source kind
`official-acquisition-evidence-v5`. The strict Python validator independently
replays ownership and post-effect phase clearing. Class-level interpretation
flags cannot be supplied in JSON. V5 keeps self-only wire metadata, malformed
classifications without private raw strings, changed-repeat detection, bounded
queue and payloads, durable-save-before-ACK, and final drain.

Historical v1–v4 schemas retain their original behavior and input fingerprints.
Changing a seeded redacted v4 removal to version 5 without the actual payload
and ownership metadata fails validation. An erased body is not recovered from
inventory differences. The recorder, read-only loader, run-config schema check,
and existing CLI audit commands accept v5 without rewriting old records.

The transport audit advances independently to schema 3/source kind
`official-acquisition-transport-audit-v3`. Four counters distinguish self-bound
removal events, observed removal item rows, unresolved removal recipients, and
ambiguous missing/null/non-array removal bodies. Repeated server updates do not
multiply counters. Historical removal ownership remains unresolved, even with an
explicit event player ID. Malformed fields and ambiguous arrays remain visible.
These counters are evidence coverage, not successful native operations.

## Training boundary and next evidence

The native inventory projection still reports either removal action as
`unsupported_inventory_event`; it does not remove items, fabricate an empty
selection, or repair state from the resulting inventory. All acquisition-rule,
training, promotion, combat, gift-schedule, and overflow eligibility flags remain
false. Existing targeted collection remains opt-in, bounded, and excluded from
learning exports. The usual acquisition commands automatically use v5 in new
games; no new collection policy or gameplay mode is required.

Next, preserve a contiguous official self-removal trace including the exact
selected rows, before/after inventory, wire classifications, ordered effects,
and gift timing. Only then add and compare an independently versioned native
removal primitive. Overflow and stochastic gift scheduling still require their
own verified evidence before replacing the redraw training curriculum.

## Verification

Synthetic Node tests execute the actual passive script. They cover both removal
actions, self versus opponent recipients, contradictory explicit player IDs,
reflected duels, consecutive updates and context clearing, gaps and membership
changes, invalid/self/multiplayer targets, default-deny effects, historical
semantics, missing/null/empty/malformed arrays, repeats, forged metadata, and
client/digest/schema pinning. Recorder tests verify save-before-ACK and no ACK
after storage failure. CLI tests verify read-only evidence/native diagnostics
and continued rejection of unsupported removals. These are not official mechanics
oracles; no official removal or overflow fixture was obtained in this turn.

All 929 non-browser tests pass, including 52 new v5-specific cases and two new
v5 queue parameter cases. Both existing local browser-control fixture tests
also pass outside the sandbox; their initial sandbox attempts failed at Chromium
startup due to macOS IPC permissions, not at a control assertion. Those tests
use temporary browser profiles and do not enter an official game. Ruff lint,
selected-file formatting checks, Mypy across 65 source modules, and the offline
uv lock check pass. Read-only audits of all ten original database runs retain
their existing evidence input fingerprints and capture versions.
