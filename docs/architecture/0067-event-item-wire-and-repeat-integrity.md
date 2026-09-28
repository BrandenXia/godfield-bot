# ADR 0067: Event item wire metadata and repeated-update integrity

## Status

Accepted, 2026-09-28, for passive v3 capture and read-only wire-aware replay
diagnostics. No remote match was started. No C++ operation, combat curriculum,
neural checkpoint, dependency pin, policy authority, progress clock, transport
timeout, or promotion gate changed. Native 0.35.0/replay schema 2 are unchanged.

## A specific fidelity gap in v2

V2 classified raw fields in the owned inventory, but only saved sanitized
event item payloads. A missing/null selection and an explicitly empty array
both became `items=[]`. Invalid fake-model integers and omitted fake fields
both became `fake_model_id=null`; missing and malformed used values both
became `used=null`. These projections cannot establish identical raw inputs.
Treating their differences as captured facts would lose mechanics evidence.

V2's online repeated-version stamp also included owned inventory, action names,
and actor IDs, but not self event payloads. Offline auditing could detect a
changed sanitized event later; the callback could nevertheless reuse owner
context while its source version was inconsistent. Classification-only event
changes were not visible even to offline projection comparison.

## Additive, self-only capture version 3

`AcquisitionSnapshotV3` inherits v2's strict phase, owner, raw ordering, and
owned-wire validation. It adds `event_item_wire`, exactly one sidecar per
reviewed event, aligned by original event index. Each sidecar classifies:

- Single gift/overflow item containers: missing, null, object, other, or redacted.
- Selection containers: missing, null, array, other, or redacted.
- Optional event model ID: the existing bounded integer kinds, or redacted.
- Each retained self item: the existing instance/model/fake integer and used
  classifications, including omitted, null, zero, positive, and malformed cases.

Only verified self-bound gift/use events receive raw-field classifications.
Opponent and unresolved events have all four container/model kinds redacted
and no item sidecars. Unknown events retain only their omitted-event indices.
No opponent models, private malformed strings/values, credentials, or arbitrary
fields enter the saved sidecars or their consistency stamp.

Strict validators require exact coverage, ordering, container/body agreement,
matching sanitized values and wire kinds, and zero-based selection item indices.
They forbid classified data on an unbound event. V3 batches require the reviewed
client hash and the complete content digest; queue and saved-subset bounds
remain unchanged. No v1/v2 fields, JSON shapes, or original digests are rewritten.

Malformed top-level self event containers are recorded as `other` with no raw
body, so the audit can expose the ambiguity without echoing it. Arrays exceeding
512 items or containing non-item entries are rejected as a bounded snapshot
failure; original callbacks still receive the document and rejection/source-gap
counters remain visible. The queue and 262,144-byte per-snapshot budget are
unchanged.

New opt-in installations use v3 and declare capture version 3 in run metadata
through the same typed constant. Read/ack prefers v3 and retains v2/v1 fallback.
The recorder validates and durably saves a v3 batch before acknowledgement,
with unchanged bounded I/O and final-drain behavior. Combined Dream installation
remains ordered and passive. Already-running processes are not hot-upgraded;
restart with the same collection command and avoid a second campaign on the
same profile.

## Conservative repeat comparison

For a candidate repeat, first reuse the original pre-update phase only to
construct the self-bound/redacted projection. Then compare its sanitized self
payloads and sidecars with the prior projection. Any difference changes the
classification to `inconsistent_repeat`, clears the carried input, and replays
ownership from an empty phase. Actor-less events without fresh phase seeds
become unresolved/redacted. Explicit self gifts or roles freshly established
inside the update can still bind without borrowing inconsistent context.

This catches classification-only changes whose sanitized items are identical,
such as empty-to-missing selections and omitted-to-negative fake fields. Stable
repeats keep their original input and are deduplicated offline. Changing an
opponent item/model does not enter this comparison. This observer behavior
does not dispatch actions or affect the policy's progress clock.

## Auditing and native projection boundaries

The transport report remains schema 2 with additive counters for self-event
sidecar coverage, legacy self-bound events without sidecars, malformed self
event fields, and missing/null/non-array self selections. Malformed or ambiguous
v3 input adds collection issues. Captured evidence version is reported separately
and metadata mismatch detection now understands declarations 1, 2, and 3.

The native differential report advances to schema 2/source kind
`official-acquisition-native-projection-audit-v2` and projection ID
`observed-inventory-projection-23-142-215-wire-aware-v2`. The underlying native
mechanics and model allowlists do not change. Before passing v3 self operations
to C++, malformed event classifications are unsupported, and use events require
an explicit selection array. An omitted array is not inferred as an empty
defense, even though the pinned client's visual parser supplies a default.

`event_item_wire_metadata_complete` is true only when every saved snapshot has
strict v3 sidecars, all item-event owners resolve, no reviewed phase anchors
are missing, and no unreviewed event may hide an omitted self operation.
This is self-only metadata availability, including explicit
classifications of malformed fields, not correct combat or complete official
physics. It may be true while the projection is unsupported. Legacy v2 remains
replayable under its declared sanitized projection, with this flag false;
legacy v1 remains unsupported for full consumption event replay. Combat, gift
schedule, overflow, training, promotion, and acquisition-rule flags remain false.

## Verification and next boundary

Node executes the actual capture script with synthetic callbacks for omissions,
nulls, explicit empty defenses, malformed containers/fake/used fields, gift and
overflow sidecars, opponent/unresolved redaction, array/resource bounds,
classification-only inconsistent repeats, stable repeats, and opponent-payload
changes. Recorder/runner tests cover declared v3 metadata, passive combined
installation, durable-save-before-ack retries, final drainage before close, and
setup/interrupt/telemetry-error paths. Strict batch tests reject sidecar conflicts,
leaks, unreviewed clients, and changed content digests.

Synthetic v3 ordinary consumption, ID reuse, Flame first-use/reuse, and explicit
empty defense traverse capture, storage, read-only CLI, and C++ comparison.
They are not new official mechanics fixtures. No v3 remote run is available
locally yet. The existing v2 run still matches all four ordered inventories,
and all four original run input fingerprints remain unchanged. No missing
v1/v2 fields are recovered or relabeled.

All 782 non-browser tests pass, including 51 new v3 tests and v3 queue coverage
in the existing collector tests. Ruff lint passes, acquisition-module/test
format checks pass, and Mypy passes across 62 source modules. Locked offline
uv validation and a wheel build succeed; the wheel contains the latest v3
validators and replay guards without cache, database, or credential paths.
The two existing browser-control tests were not run.

Collect v3 performed-miracle, combination/disguise, and explicit overflow
transitions next, then use the same `runs acquisition-replay` command for
differential feedback. Gift scheduling and the overflow victim/capacity rule
still need official evidence before a separately versioned acquisition training
curriculum can replace synthetic redraw behavior.
