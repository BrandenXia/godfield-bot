# ADR 0062: Passive acquisition evidence transport

## Status

Accepted, 2026-09-28, for opt-in collection and offline transport auditing.
The v1 transport has since been validated on three operator-run games. Its
explicit-player-only binding omitted consumption payloads; new captures use
the v2 interpretation in [ADR 0063](0063-acquisition-phase-ownership-and-wire-defaults.md).
The following records the original v1 contract and verification.
Synthetic tests verify the hook and delivery contract. End-to-end capture on
the official service still needs an operator-run collection campaign. No remote
match was started while implementing this change. No native acquisition rule,
model promotion, Training API guard, or policy authority changes.

## Why this comes before native rules

[ADR 0061](0061-inventory-observation-audit.md) establishes an ownership-capacity
gap but not the acquisition lifecycle. The Dream probe keeps a latest snapshot
and deliberately suppresses most non-Dream samples. It cannot reconstruct all
ordinary consumption, gift, prayer, performed-miracle, or overflow updates.
The accepted schema-11 local baseline remains a fixed-occupancy redraw
curriculum, not a full-fidelity official simulator.

## Collection contract

`play-training --acquisition-evidence-probe` installs a separate passive
Firestore listener wrapper before the official client loads. Default behavior
is unchanged; there are no acquisition probe evaluations when the flag is off.
The reviewed event schema is pinned to client SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The existing live-client fingerprint check also remains mandatory. A pinned
API catalog's content hash is recorded as provenance, not used to substitute
guessed item identities.

Each page document gets a new stream UUID. Source sequences advance for
matching self snapshots, including rejected captures. The queue defaults to
256 snapshots, configurable from 8 to 4096. Overflow drops the oldest snapshot
and increments a cumulative counter. Item and event arrays are bounded at
512 entries and each sanitized snapshot at 262,144 JSON characters. Invalid
or oversized snapshots are rejected explicitly, never silently truncated.

Captured fields include G.F., server update count, self player ID, player count,
attack-turn ID, optional game-over flag, and the self's ordered item array.
Items retain only numeric instance/model/fake-model IDs and an optional `used`
boolean. Missing identities, used flags, and game-over flags remain unknown.
Null or duplicate instance IDs are retained as observations but disqualify
inventory transition counting.

Only 52 reviewed event action names and bounded numeric metadata are retained.
Event item bodies are retained only for an explicitly self-bound `gift`,
`useAttackItems`, or `useDefenseItems` event. Other event item bodies are
redacted; unreviewed actions are counted without storing their bodies. Opponent
inventory records, names, account tokens, room IDs, and arbitrary document
fields never enter the acquisition evidence payload. These are observed
event records, not verified causal acquisition labels.

The wrapper preserves callback receivers, additional arguments, return values,
observer methods, unsubscribe handles, and application callback exceptions.
If combined with the Dream probe, one ordered initialization script installs
both and chains the Firebase accessor. Separate init-script execution order
is not assumed. The probe itself sends no requests or game commands.

## Delivery and failures

Python reads a non-destructive queue snapshot, validates it strictly, and
commits a fingerprinted evidence batch to SQLite before acknowledging its
source prefix. New updates arriving between read and acknowledgement remain
queued. A stream UUID mismatch cannot clear a newly loaded document's queue.
Retries deduplicate already saved source sequences within the recorder.

Reads and acknowledgements each have a five-second timeout. Validation,
browser, timeout, and acknowledgement failures generate sanitized health
events without changing the policy or resetting its no-progress clock.
Storage failures propagate and are never followed by acknowledgement.

The recorder polls outside policy/terminal event groups. Its final drain and
summary run before browser-context closure on terminal, abort, exception, and
operator-interrupt paths. A closed or stalled page instead produces an explicit
failed-final-poll summary. Counters and source gaps remain visible even when
capture is incomplete. Final stream status is the last pre-ack read; its
pending count is not an unsaved-snapshot count.

## Read-only audit

`runs acquisition-evidence RUN_ID` opens an existing database with `mode=ro`.
It checks batch content digests and binds client/catalog provenance to run
metadata. Mixed provenance, conflicting source rows, regressing stream
counters, and inconsistent final summaries are rejected. Raw validation input
is not echoed to the CLI on schema errors.

The report distinguishes saved source snapshots, source holes, queue drops,
capture rejections, hook/listener health, read/ack failures, server-version
repeats/inconsistencies/gaps, game boundaries, unknown flags, and invalid item
IDs. Repeated server versions do not multiply event counts. No transition pair
crosses a document/game boundary, invalid IDs, inconsistent repeat, or missing
source/server update. Ownership counts are distinct IDs, not rendered slots
or selectable actions. Catalog decoding and mechanics inference are separate
future work.

All batch, error, summary, and audit records explicitly disable training,
promotion, and acquisition-rule eligibility. There is no gate-pass field and
no connection to dataset exporters or training. An empty `collection_issues`
list would only describe transport health, not simulator fidelity.

## Operator validation

Start a bounded three-completed-game collection with the existing heuristic:

```bash
cd /Users/brandenxia/code/godfield-bot
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot play-training --headless --max-games 3 \
  --max-seconds 0 --max-actions 1000 --no-progress-seconds 120 \
  --acquisition-evidence-probe \
  --acquisition-evidence-catalog data/snapshots/2026-09-21/api-catalog-en.json \
  --acquisition-queue-capacity 256
```

Existing setup/gameplay retry limits remain in effect; the campaign may start
more than three runs when retrying failures. Inspect each returned run ID:

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot runs acquisition-evidence RUN_ID --database runs/godfield.sqlite
```

No `--neural-model`, `--canary-model`, or `--shadow-model` is required. Schema-11
models remain excluded from live bridges. Do not run a second account campaign
against the same browser profile concurrently. For an intentionally continuous
collection use `--max-games 0`; anomaly/retry and action limits still apply.

After validating capture, review contiguous fixtures for consumption,
performed-miracle retention, gift timing, prayer, empty-hand behavior, and
overflow/removal. Only then specify a separately versioned C++ acquisition
curriculum. Do not silently change the accepted redraw baseline, guess the
server's random selection algorithm, or interpret 18 display slots as a proven
ownership maximum.

## Verification

Synthetic JavaScript tests execute the packaged script in Node, without an
official browser or endpoint. Python tests cover strict schema validation,
save-before-ack delivery, storage failure, retries, stream reloads, bounded
evaluation timeouts, offline auditing, CLI argument propagation, and runner
shutdown ordering. The built wheel includes the JavaScript asset. Final test
results: all 589 non-browser tests pass, including 40 new acquisition tests;
Ruff lint passes and Mypy passes across 59 source modules. The two existing
browser-control tests were not run. No official browser, endpoint request, or
live policy trial was used to validate this collector.
