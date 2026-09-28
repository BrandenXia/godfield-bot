# ADR 0069: Deferred ordinary gifts and MP-utility inventory replay

## Status

Accepted, 2026-09-28, for explicit native inventory diagnostics on the verified-only
path. Native 0.35.0/replay schema 2, redraw curricula, candidates, live policies,
and promotion gates are unchanged. One bounded official Training-computer game
was played with the existing heuristic and passive v3 capture; no human room
or public Duel was entered. No experiment-specific policy was enabled.

## Recorded evidence

Run `cb9da594-c497-416f-86d6-444dc33e27c5` completed with a classified heuristic
loss. Setup/gameplay failures, source/server gaps, drops, hook/read/ack errors,
and malformed fields are zero; the final drain succeeded. Its 24 batches contain
13 ordered snapshots and 12 adjacent pairs. All 117 raw omitted owned used flags
remain unknown. There are no performed-miracle activations or overflow events.

The checksummed fixture `tests/fixtures/acquisition-v3-cb9da594.json` preserves
all 25 collector records, batch digests, original event sequences, omitted
defense arrays, and unresolved/opponent redactions. The complete input hash is
`18bfdec78b4b9fa7820a78793fe614ad725c4cec29270a093573a9e73b43d79b`.
Client/catalog hashes remain the reviewed identities from ADR 0067.

The transport report deliberately retains two missing self defense arrays and
one unresolved reflected-defense owner. These are not collection crashes;
the probe conservatively cleared its phase context at reflection. An erased
item body cannot be recovered from the next inventory or an intended click.

## Consumption and gift are not one update

The significant new case is the Direct Smash Axe attack:

| Source update | Explicit evidence | Owned inventory |
| --- | --- | --- |
| 7 | Prior observed baseline | Nine owned items, including ID 4/model 44 |
| 8 | Self attack selects ID 4/model 44; opponent defense; reflect; no gift | Eight owned items and one raw zero-ID/model empty placeholder |
| 9 | Redacted unresolved defense; damage; self gift ID 4/model 199 | Nine owned items; replacement ID 4 appended |

The C++ primitive consumes the explicit attack selection without redrawing.
It matches every normalized item in update 8 at size eight with zero gifts.
Only the later explicit gift appends ID 4/model 199. The raw placeholder remains
in evidence, but is not an owned artifact. A retained native snapshot stays
independent after the gift grows the replay.

This explains the audit's single inventory-growth pair without inventing a
miracle cast or miracle lifecycle. It disproves an immediate same-update gift
assumption for this observed ordinary attack. It does not establish a universal
gift scheduler, all redirect chains, or what happens on death before resolution.
The isolated later gift comparison is not a full replay of the redacted defense.

## Additional witnessed ordinary models

The same trace provides single-item consumption pairs for Hatchet/model 16
(three different instance uses), Gravity Mace/40, Goodbye Sword/81,
Iron Shield/130, Energy Helm/166, and Smile Flower/195. Smile Flower's selected
`useAttackItems` event is followed by `boostMP` and an explicit replacement gift;
the native inventory operation matches. Resource/combat correctness is not
asserted by this inventory comparison.

Together with the two earlier fixtures, the differential caller's exact
ordinary allowlist is now 17 models. A regression test derives that list only
from the explicit self selections in those official fixtures; a gifted model
or catalog category alone still cannot admit consumption. Multi-item selections
remain unsupported. No C++ API change is needed because the existing primitive
takes an explicit allowlist.

The projection ID advances to
`observed-inventory-projection-verified-ordinary-wire-aware-v4`; report schema 2
and native replay identity remain unchanged. The reviewed pinned-client reflect
handler swaps pending combat roles and targets, not owned inventory. It can be
inventory-neutral for the diagnostic without preserving the collector's owner
context or recovering a later redacted selection. Unexpected inventory changes
on a reflection-only update still produce a mismatch.

The full new run matches the initial deal and nine adjacent transitions,
including the size-eight deferred-gift update. It counts nine consumed items,
17 gifts, zero mismatches, and three unsupported updates: two omitted selections
and the unresolved reflected defense. Complete projection replay and complete
self-event metadata are false. All training, promotion, acquisition-rule,
combat, schedule, and overflow flags remain false.

## Verification and remaining boundary

Eleven new tests cover original fixture integrity, six additional model families,
deferred consumption/gift separation, zero-placeholder normalization, explicit
ID reuse, conservative full-run results, resource/reflect neutrality versus owner
proof, unexpected changes, and deterministic read-only CLI behavior. The existing
v2 and v3 fixtures retain their original results and input fingerprints.

All 816 non-browser tests pass. Ruff lint and changed-file format checks pass;
Mypy passes across 62 source modules, and the offline uv lock check succeeds.
The two existing browser-control tests were not run; this bounded official
match exercised the existing Training browser harness.

Next fix reflected-defense capture ownership using the pinned client's role
swap, in a new capture version rather than rewriting historical v3 evidence.
Separately, the operator has been asked whether to enable an opt-in bounded
miracle-focused collection policy; the normal heuristic remains unchanged while
that decision is pending. Gift scheduling, miracle reuse, and overflow still
need official evidence before replacing redraw training mechanics.
