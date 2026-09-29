# ADR 0075: Private API ordinary single and paired inventory selections

## Status

Accepted, 2026-09-29. Read-only inventory-projection expansion only. No
official games or accounts were started, credentials accessed, live policy
authority changed, or simulator training labels created.

## Evidence selection

Eight existing private API collection runs contain 36 adjacent, explicit,
self-bound **single-item** attack or defense selections over 28 models absent
from the previous 17-model replay allowlist. Each update is source- and
server-consecutive, has an explicit array on the wire, and matches native
ordered inventory after applying only witnessed self selections and gifts.
The curated, sanitized fixture
`tests/fixtures/acquisition-private-ordinary-single-use-v1.json` preserves
the exact ordered before/after inventories, explicit operations, phase and
wire classifications, source run and batch fingerprints, and false eligibility
flags. The 28 models span weapons, armor, and HP utility. The caller's
single-item allowlist is now 45 models, not a catalog-wide category rule.

Nine further adjacent private updates from six of those runs contain exact
**two-item** ordinary selections that reproduce the resulting inventories
when the native atomic `consume()` primitive receives both explicit rows.
`tests/fixtures/acquisition-private-ordinary-paired-use-v1.json` pins the
ordered pairs and all before/after rows. The replay dispatcher admits only
those nine ordered model pairs. Twelve models seen solely inside pairs remain
unsupported as single-card uses. Reversed pairs, other combinations,
disguised selections, and inferred consumption remain unsupported.

The fixtures are curated extracts, not replacements for the complete local
evidence. Their source hashes were checked against the read-only run database
when extracted. Raw missing flags are projected through the existing pinned
client interpretation; the fixture does not pretend to recover missing wire
values. Polling can miss server updates, so no comparison spans a gap.

## Identity and gate boundary

The projection identity advances to
`observed-inventory-projection-verified-ordinary-wire-aware-v5`; the read-only
report advances to schema/source kind 3 to expose the exact witnessed pairs
and matched pair-event count. Native package 0.36.0/schema 3 is unchanged:
the existing primitive already validates atomic multi-item consumption. The
caller supplies the union of 45 single-admitted and 12 pair-only models to
native, but the Python dispatcher enforces separate witnessed selections.

In the eight private runs, the expanded checker matches 36 new single-card
and nine pair transitions. All eight still fail complete projection replay.
The residual first-failure counts are nine unsupported selections, 26 other
inventory events, 18 missing/ambiguous self arrays, 18 unresolved item owners,
and 18 unsafe boundaries; repeated polls are counted separately. Broom's
specific three-item primitive remains isolated because its real update has an
omitted defense array. Combat, resource effects, gift scheduling, overflow,
trade, guardians, acquisition, multiplayer, and full official-game fidelity
are not verified by these inventory matches. Training, promotion, and
acquisition-rule eligibility remain false.
