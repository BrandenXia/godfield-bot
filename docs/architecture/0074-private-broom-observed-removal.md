# ADR 0074: Narrow observed three-item removal from a private game

## Status

Accepted, 2026-09-29. Observation-only native diagnostic; no official game
was started, account created, live control changed, or acquisition training
enabled. The operator chose to use this Broom trace before considering a
second automated account.

## Evidence and boundary

Private API run `34732bcb-cd59-475d-bce8-bfb1596b8b89`, read-only input
fingerprint `f9f9f92bec8dad89c9e566f2e0c0489ec657c636214c915e82c6a6295b7b49b0`,
has adjacent source sequences 36→37 and server updates 5→6 in the same stream.
The source 37 `removeItems` event has an explicit three-item array, self-bound
recipient player 2, and selected instance/model pairs (2, 75), (5, 139),
and (3, 99). Exactly those items disappear from the next self inventory; the
six survivors preserve order. The pinned 2026-09-21 catalog identifies the
three selected models as Star Staff, Ice Shield, and Lightning Kids, and
model 205/Nocturnal Broom as the `removeItems` sundry. The opponent's actual
attack item body is redacted, so attributing the action to Broom relies on
the catalog mapping rather than a witnessed opponent model ID.

The preceding self `useDefenseItems` event in source 37 has **missing**, not
explicitly empty, `items` on the wire. The run also has broader transport and
ownership issues. This is therefore a narrow, conditional inventory-operation
observation, **not** an event-complete replay or a general removal rule. The
full differential still reports source 37 as
`unsupported:ambiguous_self_selection_array`, and `removeItems` is still not
dispatched by that differential. A later self gift in source 38 is separate;
no immediate redraw is inferred from source 37.

## Implementation

The sanitized, account-free fixture
`tests/fixtures/acquisition-private-broom-34732bcb.json` preserves the source
run and two batch fingerprints, ordered before/after rows, explicit event
selection, wire classification, and false eligibility flags. Raw missing
`used`/`fakeModelId` fields become zeros only when interpreted by the pinned
client projection, never as recovered source facts. The fixture is a curated
extract, not a substitute for the complete source evidence.

Native `OrderedInventoryReplay` 0.36.0/schema 3 adds a separately configured
`remove_observed_three` operation. Its caller allowlist contains only the three
witnessed selected models; the operation requires one exact owned unused,
undisguised item of each model and atomically removes all three while
preserving survivor order.
It neither grants generic `removeItems` support nor handles used miracles,
partial hands, other item models, opponent state, replacement gifts, or random
deals. Existing curricula and replay training/promotion flags remain unchanged.
The diagnostic API identity is versioned so older schema-2 binaries fail
closed instead of silently lacking this operation.

## Collection decision

This trace closes the immediate need to wait for **one ordinary three-item
removal projection**. It does not close Goddess's Soap/`removeUsedMiracles` or
general Broom cases. Two-bot collection is deferred: it would need another
persistent account and bounded live automation, and polling could still miss
server updates. The existing human-assisted collector stays available for
other rare effects without treating absence of a random deal as a code bug.
