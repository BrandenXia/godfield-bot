# ADR 0100: Portable ordered inventory, Dream displays, and miracle retention

## Status and boundary

2026-10-01. Native 0.49.0 adds `DreamInventoryBatch`, schema 1, ruleset
`caller-driven-ordered-dream-inventory-provisional-v1`. This shared inventory
component is reusable under either architecture in ADR 0097, **not** a new
turn engine, neural curriculum, or completed full-game milestone. Labeled
provisional mechanics are approved. During verification the user chose the
separate versioned full-game environment from ADR 0097; the current arena and
its state/action contracts remain unchanged.

Existing `OrderedInventoryReplay`, witnessed allowlists, curricula,
observations/actions, checkpoints, API revision, accounts and live play are
unchanged. Broad storage does not widen official replay admission or prove
combat/economic effects. Training, full-game readiness, official fidelity,
checkpoint compatibility and promotion remain false.

## Sources and the corrected inventory distinction

Use the dated 2026-10-01 API catalog checked in ADR 0097, content SHA-256
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`,
and the 2026-09-20 Bible, pinned-client SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The adapter revalidates checksums even for unchecked model copies and checks
help, complete category/asset mappings and the exact inventory profile.
No remote account or game is accessed.

There are **237 registered held models**, not 234:

| Component category code | Category | Models |
| --- | --- | ---: |
| 1 | Weapons | 107 |
| 2 | Armor | 78 |
| 3 | Sundries | 19 |
| 4 | Miracles | 30 |
| 5 | Held trade cards | 3 |

These codes are not asserted to be the official client's enum values.
Exchange, Sell and Buy (API 3–5) have gift weights; the Flame capture contains
owned Exchange and Sell. They are not among the Bible's 291 artifacts. Only
Discard and Sacrifice (1–2) are excluded virtual controls. The other 57 models
are events/guardians, not held cards. The inventory profile SHA-256 is
`98c3b89fb319be8b16990e10a0180f0d353ba78c75081da6fc076503eb87f78d`.
The full-game report still accounts for 291 **artifacts**, with its economy gap
covering held trades; its 102 usable-model count does not increase here.

Help documents 50% false appearances for newly given cards during Dream and
repeated use of miracles. ADR 0051 provides bounded Dream evidence for separate
true/displayed identities, non-retroactive receipt and same-ID fakes. ADR 0071
verifies one Flame's first use/reuse, including tail reordering. These do not
establish all sampling pools, special interactions or complete event timing.

Explicit provisional hypotheses extend Dream to all 237 held models, use
ascending same-category pools with caller rank tickets, consume confirmed
nonmiracles including trades, and mark every miracle used while retaining its
ID/display and moving it to the tail. Multiple selections leave stable
survivors followed by retained miracles in input order. These are future local
simulation rules, not newly verified official acquisition semantics. The old
Dream curriculum's narrower eligibility and RNG stream are untouched.

## Native caller interface

Construct `(batch_size, player_count, profiles, capacity=512)` with contiguous
`int64` rows `[model_id, category]`. The source factory supplies all 237 profiles;
native tests can use small synthetic registries. Two through nine players,
capacity 1–512 and two million total slots bound storage, **not** official
inventory size or a new neural layout. Every hand is a packed occupied prefix
followed by all-zero padding.

- `seed_hand(environment, owner, items)` loads trusted fixture/sync rows
  `[instance_id, actual_model_id, fake_model_id, used]`. Fake zero means absent;
  positive fakes must share the registered category. Only miracles can be used.
  Positive safe-integer instance IDs are unique across all owners in an
  environment, but independent across environments.
- `add_cards(environments, owners, instance_ids, model_ids, curse_masks,
  disguise_tickets, fake_tickets)` appends fresh unused cards in input order.
  Dream bit 2 and a ticket below 50 in [0,99] assign the category-pool rank.
  Same-ID fakes remain internally stored. Existing cards are not retroactively
  disguised. Masks/tickets are validated even when unused; the caller decides
  RNG consumption, status and gift cadence.
- `use_cards(environments, owners, expected_items)` consumes exact owned
  nonmiracle rows, retaining/reordering used miracles. It resolves the actual
  identity, not the display. Mixed selections are a storage operation, not a
  declaration of legal combat combinations or paid costs.
- `remove_cards(...)` removes explicit exact owned rows stably. It infers no
  Broom/Soap cardinality, discard restriction, target or replacement. Used
  miracles can be removed by trusted effect callers, not by an automatically
  enabled economic/discard policy action.
- `restore_displays(environments, owners)` clears fakes without changing actual
  identity, use flags, order or external curse state. Invoke only when Dream
  ends. Documented mild cures in ADR 0098 retain Dream; full cures clear it. A
  local composition test respects that distinction without changing legacy cures.
- `reset_environments(environments)` clears all selected environment inventories
  while retaining lifetime diagnostic counters.

All input validation and allocation precedes mutation. Duplicate instances and
stale item contents are rejected. Repeated owners are allowed for ordered
gifts/selections, but not restoration. Overflow rejects the entire batch,
never silently dropping or replacing cards. The caller must supply phase/reset
epochs and exactly-once action dispatch: exact content cannot distinguish
repeated use of an unchanged already-used miracle or a stale token after
reseeding an identical item. Separate status/inventory objects do not implement
a joint gameplay transaction.

This component implements no MP/CP cost, card/phase/target/team legality, battle
effects, gift distribution/timing, overflow choice, transfer, economy, event
scheduler, turns, winner or automatic progress. It has no training `step` API.
These and bounded phase progression must be integrated before a full-game gate.

## Visibility, source metadata, and diagnostics

`snapshot()` returns copied read-only `[batch, players, capacity, 4]` **trusted
diagnostic** state including all actual/fake identities; never feed it to a
policy. `actor_hands(environments, actors)` returns copied `[rows, capacity, 3]`
rows: own instance ID, displayed model ID and used flag. No true identity behind
a fake, fake-assignment flag, opponent items, RNG tickets or counters appear.
Same-ID fakes are indistinguishable from truthful cards. Instance IDs are
selection handles, not numerical learning features. Actor authorization and
complete policy observation assembly belong to the composing engine.

Outputs survive mutation, reset and native-object destruction. Query allocation
bounds are checked first; scalar operation batches are limited to one million
rows. Gift, ordinary-consumption, miracle-use, explicit-removal and restored-fake
counters are diagnostic, not policy features or evidence of complete gameplay.

`create_provisional_dream_inventory_batch` supplies immutable strict metadata,
source fingerprints and native identity checks. Altered fields/pins, inflated
storage or battle-effect coverage, and true readiness claims are rejected. The
full-game audit references the component without widening integration buckets.

## Verification

Tests cover all 237 held models; every category, 16 masks and 100 tickets;
same-ID fakes; displayed-only own hands; ordinary removal versus miracle
first/repeated use; mixed order and compaction; cross-owner identity uniqueness;
atomic late-row, capacity, stale-content and reset failures; empty, typed,
bounded, copied queries; source drift/false metadata gates; and 512 seeded
operations against an independent ordered model.

Both event-backed official Flame first-use/reuse inventory pairs from ADR 0071
match. The older state-observation-only Flame fixture also matches, including
its held trades and explicit fake sundry. A caller rank reproduces the fake,
**not** the official random stream or Dream-state timing. These bounded cases
do not verify every miracle/display rule or promote a complete run. The legacy
disease/Dream seeded replay golden remains mandatory.

The 131 new inventory tests and the new audit regression pass. The complete
suite passes 2,102 non-browser tests plus the two local browser fixtures. Ruff,
changed-file formatting, native component formatting, strict typing across 84
source modules, offline lock consistency and whitespace checks pass. The
package was rebuilt and installed offline through uv; only the local simulator
version changed in the lockfile. No training or remote gameplay was started.
