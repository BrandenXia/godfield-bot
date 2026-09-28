# ADR 0071: Event-backed official Flame first use and reuse

## Status

Accepted, 2026-09-28, for verified native inventory regression cases. Three
operator-run official Training games were inspected read-only. No new remote
game was started. Native 0.35.0, the projection allowlists and identity, C++
training curricula, checkpoints, live control, API dependency, and promotion
gates are unchanged. This confirms an existing replay primitive rather than
introducing an unverified acquisition schedule.

## Campaign audit

All three games completed as classified losses with zero setup/gameplay
failures. They use `official-training-acquisition-miracle-v1`, focus `flame`,
and collection-only metadata. These intentionally targeted games are not a
candidate strength evaluation and cannot enter teacher/terminal-reward exports.

| Run prefix | Snapshots / adjacent pairs | Flame priority decisions | Explicit matched Flame uses |
| --- | --- | --- | --- |
| 23c7b935 | 16 / 15 | 0; Flame never owned | 0 |
| 32d8eeeb | 15 / 14 | 2 | 2 |
| 3bf94967 | 21 / 20 | 0; Flame never owned | 0 |

All three have zero source/server gaps, queue drops, rejections, hook/read/ACK
failures, and successful final drains. Their raw omitted flags and selections
remain unknown; incomplete ownership and unsupported effects are not repaired.
The first run recorded six transient recovered DOM parse errors; the other two
recorded none. No freezes or disconnected games are reported.

Input fingerprints from read-only transport/replay audits:

- `23c7b935-5fb7-40bf-863c-05e73ed1c3d5`:
  `6f00419cd5fbf0a6365f07c1d79924f30e0b6ee1334670aec6ba4c79308cc13b`
- `32d8eeeb-e23c-4196-a18e-be68ee1fc1e2`:
  `c640ac037072e63ea616ae450a2d31c27123747394ba750e592c7fe9fc0f837a`
- `3bf94967-e139-4179-96ac-6e7df61bdc7d`:
  `a6d78d684f845807b8095665c9305ee76dcb3cd651142b046021776ddd6978a7`

## What the second run proves

`tests/fixtures/acquisition-v4-32d8eeeb.json` preserves all 31 acquisition
records: 30 batches and the final collector summary, original event sequences,
individual digests, self-only wire metadata, and all redactions. It uses the
existing reviewed client and catalog hashes. Self is player ID 2, not 1.

| Source/server sequence | Explicit selection or gift | Observed owned Flame |
| --- | --- | --- |
| 8 | Self defense consumes ordinary model 161; gift ID 4/model 215 | ID 4/model 215, raw used omitted, inventory size 8 |
| 9 | Self attack selects ID 4/model 215 with raw used omitted; gift ID 5/model 161 | Same ID/model retained, used true, before appended gift, size 9 |
| 10 | Self defense selection array omitted | Same retained Flame, size 9; this update remains unsupported |
| 11 | Self attack explicitly selects ID 4/model 215 with used true; gift ID 10/model 76 | Retained Flame moves after ID 5 and before new gift, size 10 |

The two attack arrays are explicitly present, malformed-free, and bound by
ordered turn context to self. The fresh received Flame and first selection
keep their raw missing used flag; the existing pinned-client interpretation
provides the separate native false-bit projection. The second selection
actually includes boolean true. No use is inferred solely from inventory
growth, a true flag, or a dispatched browser click.

For each cast, an independent native replay seeded from the immediately prior
observed inventory executes `perform_retained_miracle`. Population does not
change, ordinary consumption remains zero, and gift count remains zero. Only
the subsequent explicit `gift` increases inventory by one. Every ordered item
matches the official result. The reuse pair proves tail reordering rather than
replacement of the miracle ID/model. Stale first-use input after marking used
is rejected atomically. Native snapshots remain independent after mutation.

There are seven raw true-flag observations but only two explicit use events,
and only one false-to-true activation observation. These counters must not be
treated as interchangeable. Existing normalized browser confirmation records
also show self MP 10→5 and 5→0, consistent with the reviewed Flame cost; this
inventory fixture and primitive do not claim resource/combat replay fidelity.

## Conservative full-run result

The existing checker matches the initial inventory and four adjacent transitions,
including both miracle uses. Counts are two retained-miracle uses, two ordinary
consumptions, 13 gifts, and zero mismatches. Ten updates remain unsupported:
four omitted selection arrays, one unresolved-owner update, and five unsupported
model/combination updates. Two unresolved item-owner events remain visible in
transport. In particular, source 8's ordinary model 161 is not silently added
to the production allowlist, and source 10's omitted defense is not fabricated
as an explicit empty array. Later comparisons use their own observed baselines;
they do not hide these unsupported updates.

The full run still has `complete_projection_replay=false` and incomplete
self-event metadata. All training, promotion, acquisition-rule, combat, gift
schedule, and overflow flags remain false. Flame remains in the terminal
inventory after the classified loss; no removal or overflow was witnessed.
The first and third games contain no self Flame; their native replay counters
do not invent any miracle use despite other gifts and inventory changes.

## Next boundary

This closes the missing *event-backed single-Flame first-use/reuse* regression
case from ADR 0070. It does not close universal miracle consumption, multi-item
or disguised casting, random gift distribution/timing, removal/overflow, or
full acquisition training. Broader acquisition mechanics must stay separately
versioned and supported by their own official fixtures; existing redraw
curricula and checkpoint authority are preserved.

## Verification

Eight new tests cover complete fixture and batch checksums, raw missing versus
boolean flags, explicit receipt with self player ID 2, both native cast/gift
pairs, reuse reordering, atomic stale-input rejection, conservative full-run
coverage, and deterministic read-only CLI/database behavior.

All 875 non-browser tests pass. Ruff lint and the new test's format check pass;
Mypy passes across 64 source modules, and the offline uv lock check succeeds.
The two existing browser-control tests were not run. Historical input hashes,
model checkpoints, and native/public action layouts remain unchanged.
