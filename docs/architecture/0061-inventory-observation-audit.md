# ADR 0061: Inventory observations before acquisition rules

## Status

Accepted, 2026-09-28, for offline observation auditing only. No new remote
matches, native rules, model admission, or live controls are changed.

## Evidence boundary

The schema-11 capacity-stress baseline now clears its local league gate, but
still redraws consumed artifacts in place. That is not the official acquisition
lifecycle. Before changing it, separate raw owned-item observations, rendered
hand slots, unused flags, selectability, and causal game events.

The current public [official client](https://godfield.net/main.dart.js) was
refetched on 2026-09-28. SHA-256 remains
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
Its item parser reads `id`, `modelId`, `fakeModelId`, and `used`. The hand
renderer handles used miracles and empty placeholders differently from consumed
items. An event can contain `overflowItem`, and the client renders its removal.
These observations do not establish the server's acquisition rate, selection
algorithm, or maximum ownership capacity.

The existing passive Dream probe reads self-item records from Firestore room
snapshots. A read-only scan of `runs/godfield.sqlite` found 208 recorded samples
across 79 runs. These include repeated versions and initial health samples;
they are not 208 independent transitions. The largest raw sample contains
17 distinct non-null item IDs, 16 known unused items, and one used item. This
is not explained solely by retained used-miracle images. It establishes an
observed ownership-capacity gap, not a maximum or a growth rule.

Run `70db32df-5949-43f8-97a9-3fe7df5d5662` supplies that sample at source and
server version 35. The audited run has 33 samples, zero invalid-instance
samples, 17 repeated-version observations, 14 adjacent observed version pairs,
one gap, and 12 changed adjacent pairs. Four pairs show a known model changing
under a retained ID. IDs also disappear and later reappear; do not assume
global artifact identity or persistence across those gaps. Its evidence digest
is `fe5e2d4271fc5f9626c3f91bea00f5514a0c723cfc06541a68f02ba8ba88e660`.

## Decision

Add `runs inventory-evidence`, reading an existing SQLite run through
`mode=ro`. Missing databases are not created; run rows, events, model manifests,
and source evidence are not modified. Run identity, mode, client fingerprint,
event sequence, and evidence payloads enter the input digest.

Counts use raw distinct item IDs, not rendered images. Unknown or duplicate
IDs invalidate a sample for counting and break transition continuity. Unknown
true identities remain explicit; they are not replaced with Dream disguises.
Unused items are not labeled playable, and all raw items are not labeled
simultaneously selectable.

Only consecutive source and server versions within the same player/probe/game
boundary form observed transitions. Repeated unchanged server versions are
deduplicated for transition purposes. Same-version inventory inconsistencies
break continuity. Missing versions, regressing counters, changed self identity,
and regressing G.F. never form transition pairs. At most 32 changed pairs are
included by default, with explicit truncation.

Reports describe added/removed IDs, retained IDs whose `used` flag changes,
and retained IDs with a changed known model. They do not label these events
as gifts, consumption, discard, trade, or immutable artifact persistence.
Source kind is `official-inventory-observation-audit`, with
`promotion_eligible=false` and `acquisition_rule_eligible=false`. There is no
gate-pass field and no training-dataset ingestion.

```bash
UV_CACHE_DIR=.uv-cache uv run godfield-bot runs inventory-evidence \
  70db32df-5949-43f8-97a9-3fe7df5d5662 --database runs/godfield.sqlite
```

## Training API assumption needs revalidation

The earlier ADR 0026 describes official Training as browser-local. Read-only
client inspection now contradicts that absolute characterization: Training's
start handler calls the common Cloud Functions request path, which includes
mode and room ID; room updates use Firestore listeners. No new request to
start a game or submit a command was made during this investigation.

The pinned [pygodfield revision](https://github.com/xu-shawn/pygodfield/tree/0673312945e3e97ff574cd1617dff7264fed068f)
exposes `join_training()` and `Mode.TRAINING`, but `Bot.run()` explicitly rejects
Training as unsupported and describes it as browser-local. Static client
routing and helper availability do not prove operational API compatibility.
An isolated compatibility probe is a possible follow-up, not justification for
removing that guard or enabling a live neural model. Existing controls stay
unchanged and remote-match probing needs an explicit operator choice.

## Next fidelity work

The current Dream recorder deliberately suppresses most non-Dream updates and
keeps only the latest raw snapshot before a sample. It cannot provide a complete
acquisition trace. A future separate, opt-in passive collector should retain
ordered self-item snapshots and whitelisted causal game events, with explicit
buffer-overflow/missed-update accounting and client/catalog fingerprints.
No account secrets, opponent hidden identities, or inference-derived labels
should enter that evidence.

First verify ordinary consumption, performed-miracle retention/reuse, gift
timing, prayer, empty-hand behavior, and overflow/removal against contiguous
fixtures. Then implement a separately versioned native acquisition curriculum,
keeping this redraw curriculum and its accepted baseline intact. Do not infer
server mechanics from the two-row renderer or silently clamp owned inventories
to 18 slots.

## Verification

All 549 non-browser tests pass, Ruff lint passes, and Mypy passes across
57 source modules. Fifteen new tests cover distinct raw IDs, unknown identities,
retained used flags, known-model changes, repeated/inconsistent versions,
gaps, probe/game boundaries, bounded reports, noncreating read-only database
access, immutable source files, deterministic fingerprints, CLI output,
unknown runs, and malformed evidence rejection. No browser code was changed.
