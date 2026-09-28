# ADR 0064: Verified ordinary inventory replay

## Status

Accepted, 2026-09-28, for an explicit, separately versioned C++ replay component.
The first v2 official run verifies ordinary consumption coverage. No remote
game was started during implementation. No training checkpoint, curriculum,
observation/action schema, promotion gate, or live policy authority changed.

## Operator-run verification

Run `bc54a888-de09-4654-9b7a-80533d525c2a` completed with the existing
`heuristic-v0` policy, five in-match actions, and a classified loss. It is not
a neural strength evaluation. The evidence contains eight saved batches, four
snapshots, three adjacent inventory pairs, and a successful final drain.
Declared and captured evidence versions are both 2.

There are no source/server gaps, repeats, drops, capture rejections, invalid
item IDs, hook/read/ack failures, malformed wire items, unverified phase inputs,
unreviewed events, or unresolved attack/defense owners. All 36 raw missing used
flags remain unknown in the evidence; the pinned-client interpretation is
separate. Three opponent item events are redacted as intended.

One self attack event contains one item; two self defense events contain one
item in total, because the terminal defense uses no items. Ownership comes from
persisted, verified phase context, not a fabricated event player ID. There are
11 self gifts (nine initial and two later), no overflow-item events, no observed
performed-miracle lifecycle, and no empty-hand/growing-hand transitions.

Verified input SHA-256:
`50aaf546587fd4582989e2710188a306684160e6e7a0ad2a606c0c3676a3f017`.
Client and catalog hashes are unchanged from ADR 0063. The cached official
client's SHA-256 was also rechecked against this run. A sanitized fixture
preserves all nine collector evidence records, their source event sequences,
and every original batch digest; the database is read only and unchanged.

## Narrow verified transitions

| Update | Self operation | Ordered inventory consequence |
| --- | --- | --- |
| 1 | Nine initial gifts | IDs 1 through 9, in observed gift order |
| 2 | Use ID 4/model 142, Steel Gauntlet; gift ID 4/model 3, Exchange | Remove ordinary armor; preserve survivors; append reused ID 4 |
| 3 | Use ID 2/model 23, Hard Hammer; gift ID 2/model 126, Flame Boots | Remove ordinary weapon; preserve survivors; append reused ID 2 |
| 4 | Empty self defense, damage, death, game end | Inventory unchanged |

The pinned catalog identifies both consumed models as ordinary armor/weapon.
The gift of Exchange is an opaque inventory item, not evidence for simulating
its trade ability. These transitions verify ordered removal and append in this
trace, not a universal acquisition rate, gift count, timing, random selection
algorithm, or overflow limit. Recycled IDs are not immutable artifact identities.

## Native component and boundary

Native package 0.34.0 exports `OrderedInventoryReplay`, with replay schema 1 and
ruleset ID `explicit-ordinary-consumption-ordered-gift-replay-v1`. This is not a
new `create_attack_defense_simulation` ruleset and is not wired into collectors,
exporters, training, or live inference. Existing redraw curricula and their
schema-11 accepted baseline retain their mechanics and observation layouts.

The interface uses contiguous `int64` arrays with item columns
`[instance_id, model_id, fake_model_id, used]`. Inputs must already be bound to
verified self ownership and interpreted using the pinned client/catalog.
Missing raw fields are not converted inside the C++ component. Positive safe
instance/model IDs, nonnegative safe fake-model IDs, boolean used flags, and
unique owned instance IDs are required.

The constructor receives an explicit ordinary-consumable model allowlist and
an optional capacity. The official fixture allowlist is exactly models 23 and
142; nonconsumed artifacts are retained as opaque inventory records.
`consume(expected_items)` rejects used, disguised, or non-allowlisted artifacts,
unknown or model-mismatched IDs, and duplicate selections. Full validation
precedes any removal or counter update. Survivor ordering is stable.
`gift(item)` appends only when its ID is absent and capacity is available;
it cannot overwrite a live artifact or guess which overflow item disappears.
A consumed ID can be reused by a later gift with a different model.

The configurable capacity, bounded at 512, is an implementation resource limit,
not an asserted official maximum. Independent read-only snapshots remain valid
after consumption, growth, or object destruction. Diagnostic size, capacity,
and successful consumed/gift-item counters are exposed. No game actions or
random draws occur in this component.

## Verification and next milestone

The native replay reproduces every ordered item row in all four recorded
snapshots, with two ordinary items consumed and 11 gifts appended. Original v2
batch JSON shapes and content hashes remain unchanged. Snapshot tests include
the empty defense and the terminal no-inventory-change update.

All 648 non-browser tests pass, including 33 new replay tests. They cover
atomic failures, stable compaction, ID reuse, duplicate/unknown/mismatched IDs,
unsupported used/disguised artifacts, invalid gifts, explicit capacity, array
shape/type checks, empty selections, independent snapshot lifetimes, and
separate replay identity. Ruff lint passes and Mypy passes across 60 source
modules. Native wheel build and locked offline `uv sync` succeed; offline
`uv lock --check` verifies the updated local package version without changing
any external dependency pins. The two browser-control tests were not run.

Next, obtain contiguous performed-miracle retention and overflow/removal
fixtures, and review gift scheduling/empty-hand behavior before integrating
this lifecycle into a separately versioned acquisition training curriculum.
Additional collection can use the existing opt-in v2 command; no model promotion
or altered safety limits are needed. Continue preserving the accepted redraw
baseline rather than changing its mechanics under an existing ruleset ID.
