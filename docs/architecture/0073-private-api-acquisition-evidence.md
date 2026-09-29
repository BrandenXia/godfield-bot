# ADR 0073: Human-assisted private API acquisition capture

## Status

Accepted, 2026-09-28, after the operator approved the private-room capture
adapter. Collection and diagnostics only; no official game was started during
implementation. C++/native 0.35.0, ordered replay schema 2, curricula, learned
weights, live neural authority, and promotion gates remain unchanged.

## Why change the collection route

The operator's three later v5 official-computer recordings completed without
operational failures, but none contained a removal event. Their 65 distinct
server snapshots also contain none of the six fixed-attack miracles supported
by the browser collection policy. Zero focused selections therefore indicate
missing deals, not a failed selection counter. The recordings include other
miracles, but those do not silently gain browser control authority.

Runs and unchanged evidence input fingerprints:

- `62af4169-69be-4fbf-a552-8c045faed389`:
  `cfd5d9602145332a9b4e8da3af0576cb011441af2c3df3f4708a709e17e49cf9`.
- `57fe5532-b8ad-422a-9c2d-8f899f1de061`:
  `9c10c79a87865d7d6b020217f31471dae927a269f59f203e009ceaa0f10f6096`.
- `c197e02f-58d1-47b4-a9f7-fb88d05a340f`:
  `3c0dda9c1a81d8ced9fc3c6292c7af6bc2782cb261ee974ec2d3bce498c7a703`.

A human can deliberately target the bot with an available removal artifact
after observing its retained miracle. This still depends on a random deal;
the adapter supplies neither artifacts nor removal mechanics labels.

## Opt-in scope

`api play-private --acquisition-evidence-probe` uses the existing tactical API
policy and ordinary legal-action checks. Require solo/team 0, explicit entry,
a positive finite time limit, and no model/shadow policy. Public Duel, chat,
and normal private play remain unchanged. Use only two players for the
reviewed removal ownership case; more players do not acquire payload authority.

Explicitly pass the reviewed catalog rather than changing normal API defaults:
`data/snapshots/2026-09-21/api-catalog-en.json`, SHA256
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
The pygodfield revision remains
`0673312945e3e97ff574cd1617dff7264fed068f`.

Collection mode treats a completed game already displayed on joining as lobby
state until an active self match is observed. It uses the existing entry
mechanism and does not export that stale result as a new collected match.
The first observed terminal result or existing safety limit ends the session.
Run metadata is explicitly collection-only, with false training/promotion
eligibility. Both replay exporters reject these runs before selecting samples.

## Raw projection, identity, and privacy

pygodfield preserves the room document in `RoomState.raw`. Project this data
before normalization/deduplication or policy decisions. Do not use modeled
`.used` or `.events` defaults: omitted wire fields must stay omitted/unknown.
Every successful in-match read is recorded, including repeated server versions.

Bind self only when exactly one player matches the verified API user ID and
configured identity, and the identity name is unique. Account IDs, names,
room keys, arbitrary raw fields/strings, and opponent item bodies are not saved
in acquisition evidence. The usual normalized gameplay logs remain separate.
Bound arrays, event counts, player counts, safe integer IDs, and payload size.
Reject malformed frames rather than manufacture defaults; log only fixed,
sanitized error classifications. Malformed/rejected reads, missing membership,
lobby absence, transport read failures, and new matches clear carried context.

The Python projection independently passes the strict capture v5 validator.
Ordered turn/target context, reviewed two-player reflection, self-only wire
classifications, changed-repeat invalidation, and removal phase clearing match
the existing browser script. There is no additional removal ownership rule.
An explicit self actor cannot override an unresolved recipient.

## Polling is not push delivery

No additional state request, browser hook, subscription, or gameplay command is
introduced by the evidence recorder. It observes existing `client.state()`
reads. Each persisted delivery uses separate source kind
`private-api-acquisition-evidence-v5`, capture schema 5, and `api-polling` delivery
metadata. Sequence numbers count local reads, not intervening server updates.
Skipped update counters remain server gaps; no intermediate event is invented.

Keep the API run's existing environment fingerprint in `RunSpec.client_sha256`.
Each evidence batch separately records that fingerprint, pygodfield revision,
catalog pin, and reviewed decoder client pin
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The latter is decoder provenance, **not** proof that this browser client was
running in the private room. The private batch digest is domain-separated from
browser capture digests and binds all these pins plus counters and snapshots.
The read-only loader cross-checks provenance against collection run metadata.

Save before locally acknowledging a delivery or committing its carried phase.
Storage failures propagate and prevent dispatch. On exit, persist one
idempotent summary without a final network request. API summaries report
`final_poll_succeeded: null` and `final_flush_succeeded: true`, never a fictional
browser drain. Cleanup still attempts to leave the room if flush fails.

Transport audit advances to schema 4/source
`official-acquisition-transport-audit-v4`. Report delivery kinds and API stream
counts separately. Missing hooks/listeners are an issue for browser streams,
not for honestly labeled API streams. Browser evidence/summaries cannot be
relabeled as private API collection; historical v1–v5 input fingerprints and
interpretations remain unchanged.

## Rule verification boundary

The existing read-only `runs acquisition-evidence` and `runs acquisition-replay`
commands accept private collection runs. Repeated polls do not multiply event
counts, gaps cannot become causal transitions, and data-quality issues remain
visible. Both removal actions still produce native
`unsupported_inventory_event`. No inventory difference is repaired into a
removal operation; all training/promotion/acquisition-rule flags remain false.

The next useful input is a contiguous human-assisted trace with an explicit
self-targeted removal payload, selected item identities, before/after retained
inventory, ordered effects, and later gift timing. Review that real trace before
implementing a native removal primitive. Stochastic gift scheduling and overflow
need their own evidence. Synthetic parity tests are not official rule fixtures.

## Verification

Tests exercise actual browser-v5/Python projection parity, both removal actions,
reflection, self/opponent privacy, ambiguous identity, malformed and absent
fields, safe integer boundaries, repeated-payload changes, skipped updates,
membership changes, multiplayer rejection, read-error boundaries, terminal
boundaries, bounded rejections, strict provenance, and save-before-ACK.

Fake API sessions verify unchanged commands/read counts for active games,
capture before normalized-state deduplication and dispatch, stale-terminal
entry, interruption/failure/recovery finalization, cleanup after storage faults,
CLI forwarding, early rejection of incompatible flags/catalogs, exclusion from
both training exports, read-only diagnostics, and continued native removal
rejection. No account credentials or official room are used by these tests.

All 1,007 non-browser tests pass, including 78 new private-API cases. Both
existing local browser-control fixture tests pass outside the sandbox using
temporary profiles. Ruff lint and selected-file formatting, Mypy across 66
source modules, CLI help verification, and the offline uv lock check pass.
The synthetic Node harness now freezes its capture clock so short numeric
privacy markers cannot accidentally match timestamp digits; production clocks
and historical fixtures are unchanged. Read-only production audits confirm
the three fingerprints above, their 36/14/15 saved snapshots, and zero removal
events remain unchanged.
