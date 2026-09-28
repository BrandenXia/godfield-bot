# ADR 0065: Retained-miracle observation replay

## Status

Accepted, 2026-09-28, for explicit C++ replay of observed inventory states and
read-only coverage counters. This is not a full event replay or an acquisition
training curriculum. No remote game was started. No checkpoint, live policy,
promotion gate, existing combat curriculum, or observation/action layout changed.

## Existing evidence supplies a narrow case

Only one v2 capture exists locally, the ordinary-consumption game from ADR 0064.
The older v1 run `f456703e-a514-44fc-b474-ba95a676b264` nevertheless contains
three consecutive, valid owned-item snapshots at source/server sequences 9,
10, and 11. Each includes the same instance 8/model 215, `<Flame>`. The pinned
catalog classifies it as a miracle. G.F. is nonregressing and player membership
counts and self identity are unchanged.

| Pair | Retained item observation | Explicit self gift | Owned size |
| --- | --- | --- | --- |
| 9 → 10 | ID 8/model 215: raw used unknown → true; retained at the tail before the new gift | ID 10/model 3, Exchange | 9 → 10 |
| 10 → 11 | ID 8/model 215: raw used true → true; reordered after ID 10, before the new gift | ID 11/model 202 | 10 → 11 |

Run action-result records also contain two dispatched confirmations for Flame.
They corroborate the intended selections, not server consumption, exact item
binding, MP effects, or successful casts. V1 deleted the item bodies from the
intervening attack/defense use events. No native operation selected from these
inventory observations is promoted to a recovered event label.

The reviewed client `A.kY` interprets non-boolean used values as false; raw
unknowns remain unknown in saved evidence. Client inventory `ee` distinguishes
miracles from ordinary removal, adds the used marker, and retains them. Its
animation/render ordering is not a substitute for the server inventory order.
The replay's tail placement matches the two observed raw inventory pairs;
it is not asserted for every miracle, mixed selection, or special effect.

Full original run input SHA-256 remains
`6490ff47695e6117f40011b15b047705942a24d74667df0bdba75b3c4421ad1c`.
Client/catalog fingerprints are unchanged from ADR 0063. The new sanitized
fixture preserves three original v1 batches and their digests, explicitly
declares `event_complete=false`, and retains all three eligibility flags as
false. It is a sparse observation fixture, not an entire transport audit.

## Explicit native operation, not automatic dispatch

Native package 0.35.0 exports replay schema 2 and ruleset ID
`explicit-ordinary-and-retained-miracle-ordered-gift-replay-v2`. The existing
ordinary constructor/consume/gift/snapshot API remains available.

Before any successful operation, a caller may configure a retained-miracle
model allowlist once. IDs must be distinct positive safe integers, bounded at
512, and disjoint from the ordinary-consumption allowlist. Configuration is
validated before commitment and cannot change after a successful operation,
including an empty ordinary selection. The observed fixture configures only
model 215; catalog membership and self ownership are verified outside C++.

`perform_retained_miracle(expected_item)` accepts exactly one
`[instance_id, model_id, fake_model_id, used]` row. It requires an exact owned,
allowlisted, undisguised artifact. An unperformed or already-used miracle is
retained under the same instance/model, marked used, and moved to the tail.
Population is unchanged. A separate operation counter advances; ordinary
consumption and gift counters do not. MP costs and combat are not simulated
by this operation. Validation failure leaves inventory and counters unchanged.

Ordinary consumption still rejects miracles, and retention rejects ordinary
artifacts. A configuration collision cannot silently change a card's lifecycle.
Array dtype/shape requirements, snapshot independence, and explicit resource
capacity remain unchanged. No collector, exporter, trainer, or live adapter
automatically invokes this component. Overflow removal and random acquisition
remain unsupported.

## Read-only observation counters

The existing audit gains three additive fields, without rewriting raw evidence
or changing its input fingerprints:

- `raw_used_true_observation_count`: true flags seen in saved self snapshots,
  not independent uses or successful casts.
- `owned_inventory_growth_pair_count`: valid contiguous inventory pairs whose
  distinct owned count increases, not an inferred gift schedule.
- `client_interpreted_used_activation_count`: unchanged instance/model/fake
  identity moves from client-interpreted false to raw true in a valid pair.
  Interpretation requires the reviewed client hash. A replacement self gift
  of the same ID is excluded, even if it repeats the model.

Comparisons exclude source/server gaps, invalid identities, inconsistent
repeats, document/game/self boundaries, and changed player counts. Raw flags
and client defaults remain separate. The full v1 run has five true-flag
observations, two growth pairs, and one activation; those numbers do not
establish two processed casts or complete mechanics fidelity. The new sparse
fixture observes two true flags, two growth pairs, and one activation.
All report eligibility flags remain false.

## Verification and next boundary

All 678 non-browser tests pass. The native replay tests now total 54, including
first-use/reuse state matching, stable population, snapshot independence,
configuration opt-in/immutability, disjoint allowlists, stale/unknown/mismatched
items, invalid IDs/used flags, full-capacity retention, and dtype/shape checks.
Audit tests verify unsafe-pair exclusions, replacement identity/gift exclusions,
and no client interpretation for an unreviewed hash. Original v1 and v2 fixtures
still validate unchanged JSON shapes and content digests. Ruff lint, formatting,
and Mypy (60 source modules) pass; the native package rebuilt with locked offline
uv, and the lock remains valid without changing external dependency pins.
The two browser-control tests were not run.

Next obtain full v2 self consumption/retention evidence, especially combinations
and disguise cases, plus explicit overflow/removal and gift scheduling/empty-hand
behavior. Existing collection controls remain sufficient and unchanged. Only
then integrate a separately versioned acquisition training curriculum; preserve
the accepted redraw baseline and its evaluation results.
