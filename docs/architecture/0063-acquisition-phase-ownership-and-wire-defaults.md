# ADR 0063: Acquisition phase ownership and wire defaults

## Status

Accepted, 2026-09-28, for passive v2 capture and read-only auditing. V2 capture
is synthetically verified; a new operator-run official game is still needed
to verify its end-to-end semantic coverage. No remote match was started during
this change. No native rules, checkpoint, promotion gate, live policy authority,
or API Training guard changed.

## Results from the three v1 games

All three completed with the heuristic controlling the official Training game.
They were losses, not neural evaluations. Each has one stream, a successful
final poll, a start/end event, and zero queue drops, capture rejections, hook
errors, read/ack errors, missing source versions, server gaps, or inconsistent
server repeats. Clean transport did not imply complete mechanics evidence.

| Run ID | Snapshots | Maximum owned IDs | Client-unused maximum | Self gifts | Unresolved consumption events |
| --- | ---: | ---: | ---: | ---: | ---: |
| `a2dc9b5c-451b-4b6f-b866-e5b269f273f3` | 25 | 9 | 9 | 26 | 50 |
| `f456703e-a514-44fc-b474-ba95a676b264` | 14 | 11 | 10 | 18 | 29 |
| `fde22aaa-ebb5-4896-95b3-baed993a9ea6` | 48 | 18 | 18 | 48 | 105 |

The 87 snapshots contain 92 explicitly self-bound gifts: 27 initial and 65
later. All 92 gifted instance/model IDs occur in their corresponding final
snapshot. Among valid adjacent inventory pairs, 11 later gift events introduce
new IDs and 52 use IDs retained from the previous snapshot. Two later gift
events cross an invalid-ID inventory boundary and are excluded from that
comparison. Retained IDs cannot be treated as immutable artifact identities.
There are no captured self overflow-item events. Ownership reaching 18 is an
observation, not a proven maximum or a verified overflow algorithm.

All 184 attack/defense use events lack an explicit player ID. The v1 binding
rule therefore saved no self consumption item payloads. Deleted event bodies
cannot be recovered by replaying the surviving metadata. The first and third
run each contain one invalid-ID snapshot; v1 loses the distinctions needed to
classify a compact empty item safely. These deficiencies block faithful native
consumption/gift/overflow rules, despite otherwise complete transport.

Full read-only input fingerprints remain unchanged:

- First run: `c7cae1d0af67137af42ed2eb6693fd96cf4acacbc67037b18c88967c5335c171`.
- Second run: `6490ff47695e6117f40011b15b047705942a24d74667df0bdba75b3c4421ad1c`.
- Third run: `31687b128f710ec7b2f597579df6169b6fd6eafa299eae99aea4a1bcdc726ac8`.

## Pinned-client interpretation, not rewritten evidence

The decoder is pinned to official client SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The reviewed local source is `runs/experiments/official-client-2026-09-28.js`.
The catalog content fingerprint is
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.

In `A.kY`, integer fields default to zero and a non-boolean `used` field
defaults to false. `A.of` constructs an empty zero-ID/model placeholder with
`used=false`. False fields are commonly omitted on the wire. The three runs
have 947 raw unknown used-flag observations; those remain unknown in raw
records and audit counts. `max_client_unused_distinct_instances` separately
applies the verified client's default, only for this exact client fingerprint.
It must not be confused with an explicit raw false flag or a causal training
label. The five true-flag observations in the second run are snapshots, not
five independently verified performed-miracle transitions.

V2 adds bounded per-item wire classifications for missing/null/zero/positive
integer/other identity fields and missing/null/boolean/other used fields. It
excludes a structurally default-zero empty placeholder from owned-ID counting
only when the raw used flag is not true. Malformed fields remain visible and
are never silently classified as placeholders. V1 cannot retroactively gain
these wire distinctions.

## Conservative ordered ownership

In the reviewed client, `advanceGF.playerId` establishes the attacker role.
`useAttackItems` consumes that role's items, rather than the event's optional
player ID. `setTargetPlayer.playerId` selects a target; `useDefenseItems` uses
the opposing role when available. Self-targets do not replace a prior opposing
role, so inferring a defender directly from a self-target would leak the wrong
inventory. The collector therefore requires a known distinct attacker and
target before binding defense items.

V2 stores a separate ownership proof without fabricating an event player ID:
explicit self gift player, verified turn context, verified target context, or
unresolved. Known player membership is required. Opponent and unresolved item
bodies are still redacted; no opponent inventory or model IDs enter replay
state. Only self gift/attack/defense item bodies are retained.

Carry-over phase context requires consecutive source/server versions,
nonregressing G.F., and identical self/player membership. Unreviewed events,
capture rejection, gaps, boundaries, inconsistent repeated versions, and all
other effects clear context. This includes bounce, reflection, counterattack,
next attack, guardian/dying attacks, and resource effects until their role
semantics have been separately verified. Repeated callbacks replay from the
original pre-update context, not the prior post-update state. Context after a
clearing effect must be reseeded by reviewed events.

Strict Python validation replays every event and checks the owner proof,
self-only binding, and phase output. Offline auditing also checks carried
phase inputs against their actual persisted source anchors; a missing anchor
is an explicit coverage issue and a conflicting anchor is rejected. The
default-deny decoder may still leave some events unresolved. Do not loosen it
merely to increase item counts.

New live captures declare evidence schema 2 in run metadata. V1 readers and
hashes remain supported unchanged. The audit output itself has schema 2 and
reports the actual capture versions separately, including metadata mismatch,
resolved self attack/defense counts, missing ownership, placeholders, malformed
wire fields, overflow coverage, and unverified phase inputs. Transport health
summaries retain their independent v1 format. All evidence and reports remain
ineligible for training, promotion, and adoption of acquisition rules.

## Verification and next boundary

All 615 non-browser tests pass, including 66 acquisition tests; Ruff lint and
format checks pass, and Mypy passes across 60 source modules. Node executes
synthetic callbacks for actor-less self consumption, cross-update context,
opponent redaction, self-target/unseeded defense, default-deny effects, gaps,
repeats, queue overflow, and save-before-ack retries. Four sanitized v1 batches
from the user's runs are compatibility fixtures with original content digests.
Their JSON shapes and hashes must remain unchanged; they are not training data.
The two existing browser-control tests are not part of this offline run.
An offline wheel build includes both the v2 module and the JavaScript asset.

Run one bounded v2 official Training game using the README command. Audit the
new run for transport and actual self consumption coverage. Then review
contiguous, catalog-decoded fixtures for consumed-versus-retained artifacts,
gift ID replacement, performed miracles, and overflow. Only verified mechanics
may enter a separately versioned C++ acquisition curriculum. Preserve the
accepted schema-11 redraw baseline and its gates; do not guess a full official
random acquisition schedule or imply live neural readiness from local wins.
