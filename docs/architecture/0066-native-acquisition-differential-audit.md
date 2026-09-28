# ADR 0066: Native acquisition differential audit

## Status

Accepted, 2026-09-28, for automated, read-only comparison of a narrow captured
inventory projection with the native replay from ADRs 0064 and 0065. No remote
game was started, and no native curriculum, checkpoint, dependency pin, live
policy, or promotion gate changed. Native package 0.35.0 and replay schema 2
remain unchanged.

## Why this precedes overflow and scheduling

There is still only one local v2 capture, `bc54a888-de09-4654-9b7a-80533d525c2a`.
It contains ordinary consumption but no performed miracle or overflow. The
three v1 runs retain their missing consumption bodies. The reviewed client's
18-slot UI management is not proof of an official inventory cap or an overflow
victim algorithm.

The current official [English JSON](https://godfield.net/i18n/en.json) was read
again on this date. Its full byte SHA-256 remains
`bb1b433ba6d336765589aec940cca0bac8b7c0bdcee33969c207a17365509188` and all 296
item records equal the pinned API catalog. The reference text confirms reusable
miracles and distinguishes discard from sacrifice gift behavior; it does not
provide a complete overflow or ordinary gift schedule. This absence is not
proof that no such rules exist elsewhere.

Instead of inferring mechanics from inventory differences, make future explicit
captures automatically comparable with the existing native building block.

## Read-only, bounded interpretation

`runs acquisition-replay RUN_ID` reads run metadata and evidence in one SQLite
read transaction (`mode=ro`). Transport auditing and native comparison consume
the same loaded records; a concurrent collector cannot give the two diagnostics
different read snapshots. The existing transport report format and the original
input fingerprint calculation are preserved. No evidence, database, label,
model, or game action is written.

The report has its own schema 1 and projection ID
`observed-inventory-projection-23-142-215-v1`, and checks native replay schema 2
and its exact ruleset ID. Missing or incompatible native dependencies fail
clearly; there is no Python simulation fallback. Client interpretation remains
pinned through strict v2 validation, and the exact reviewed catalog content
fingerprint is required.

Ordinary consumption is deliberately limited to verified models 23 and 142.
Single-item model 215 retention is admitted as a comparison hypothesis using
the two observed Flame transitions from ADR 0065, not as independently verified
full v2 event evidence. Mixed miracle selections, other consumption models,
disguised selections, overflow, missing gift payloads, unknown catalog models,
and inventory-affecting events outside the reviewed subset are unsupported.
Opaque catalog-backed items may be owned or explicitly gifted without gaining
additional mechanics support. Known opponent gift/use events are skipped, never
simulated; unresolved ownership blocks comparison.

Only the reviewed phase/control, safe/miss, damage/dark damage, death, and
end-game handlers are treated as inventory-neutral in this projection.
`startGame` is admitted only at index zero of the first source snapshot, where
explicit gifts are replayed from empty inventory. A later start does not erase
an existing inventory or hide a boundary. Being a collector-reviewed event is
not sufficient to treat it as inventory-neutral.

Owned-item normalization uses validated v2 wire classifications, excludes only
structural empty placeholders, and rejects malformed fields and duplicate IDs.
Saved raw used flags remain untouched. Missing/non-boolean used defaults are
part of the separately declared pinned-client projection. V2 has no event-item
wire sidecars, so it cannot establish complete original wire interpretation;
`event_item_wire_metadata_complete` remains false even for matching projections.

## Differential checks and failure visibility

Each adjacent pair uses a fresh C++ object initialized from its recorded
previous inventory. Explicit ordered operations produce a candidate resulting
inventory, which is compared row-for-row, including order, instance/model/fake
identity, and used flags. No consumption is inferred from missing items, no
gift is fabricated, and no mismatch is repaired from the resulting snapshot.
Later comparisons may use a new observed baseline, but prior failures remain
in the results and prevent complete projection replay.

The report distinguishes `matched`, `mismatch`, `unsupported`, `skipped`, and
consistent `repeat` outcomes, with source/update identifiers, static reason
codes, event positions, inventory sizes, and first differing row positions.
Only matched comparisons contribute successful operation counters. Raw item
bodies, opponent inventory, credentials, and malformed input are not printed.

Source/server gaps, self/player membership changes, regressing G.F./versions,
terminal-to-next transitions, invalid previous inventory, and inconsistent
repeats cannot bridge a comparison. Duplicate deliveries and consistent server
versions do not replay gifts twice. Conflicting deliveries and phase anchors
are rejected before native comparison. Run-level completion also requires a
clean transport report, including the final collector poll and declared
capture version.

`complete_projection_replay` means only that this limited projection matched
all saved, nonrepeated rows with acceptable collection health. It is not named
`passed`, is not a mechanics or promotion gate, and proves neither combat nor
random acquisition. Combat, gift scheduling, overflow, training, promotion,
and acquisition-rule verification/eligibility flags remain false. CLI exit
zero means a report was produced; mismatch and unsupported counts must still
be inspected. Exit one means the inputs or optional native package could not
be validated safely.

## Verification and remaining boundary

The CLI matches all four ordered inventories in the original v2 run, including
the initial nine gifts, two ordinary uses, two reused-ID gifts, and the empty
terminal defense. There are three matched adjacent transitions, two consumed
items, 11 gifts, and zero retained-miracle uses, mismatches, or unsupported rows.
The complete original input SHA-256 remains
`50aaf546587fd4582989e2710188a306684160e6e7a0ad2a606c0c3676a3f017`.
All 87 v1 snapshots are explicitly unsupported for event replay, rather than
being upgraded from inventory observations; all three original hashes also
remain unchanged. No retained-miracle cast is recovered from the v1 fixture.

The new tests exercise the real sanitized v2 fixture and separately marked
synthetic first-use/reuse comparisons, missing operations, stale identities,
ordered mismatches, independent recovery, unresolved owners, unsupported
effects/models/combinations, overflow, source/server/document gaps, repeats,
transport failures, malformed wire classifications, empty placeholders,
provenance/native identity failures, read-only deterministic CLI behavior,
unchanged fingerprints, and private-input-safe errors. Synthetic tests are not
official mechanics evidence.

All 729 non-browser tests pass, including 51 new differential-audit tests.
Ruff lint and changed-file formatting checks pass; Mypy passes across 61 source
modules. The locked offline uv environment and lock check remain valid. An
offline wheel build includes the new module and existing probe asset, without
cache, run-database, or credential paths. The two existing browser-control tests
were not run.

Next collect complete v2 miracle, combination, disguise, and explicit overflow
transitions and establish the gift/empty-hand schedule. The diagnostic now
provides automatic differential feedback for those captures. A separately
versioned acquisition curriculum still requires verified mechanics; preserve
the accepted schema-11 redraw baseline in the meantime.
