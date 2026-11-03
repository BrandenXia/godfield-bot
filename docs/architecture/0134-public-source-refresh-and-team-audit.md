# ADR 0134: November public-source refresh and team audit

## Scope and findings

2026-11-03: read only the public client and English catalog/translations. Both
were last modified2026-11-03 05:01:41 UTC. No account, room, credentials,
checkpoint or live policy was accessed. Archive exact source bytes with dated
provenance and a complete296-model API catalog under `data/snapshots/2026-11-03`.
The translation archive adds one newline, recorded separately from its body hash.

- Client SHA256: `5ece06c224b6a7a5d877eb45d22ea18b82a03aaf1b7161cbbdf6a1e23ceab2cd`.
- English body SHA256: `23fbf5e637b8f3f628d78e5de14f3ce2b65442066c6f94820d8f0d517c6fbd00`.
- Catalog content SHA256: `cf011ec0874c8ee7e9403d2559d4d60380d0347e99a38a5db06a63a619f3170d`.

Against the October catalog, exactly three model names/image names changed:
19 Chain Sickle/chain-sickle → Kusarigama/kusarigama;26 Glaive Classic/
glaive-classic → Naginata Classic/naginata-classic;117 Slate/slate → Stone
Tablet/stone-tablet. No other raw item key/value differs. This verifies the
catalog's nonlabel fields, not whole-client or server semantic equivalence.
Text changes split cost and price labels and add Spanish translation credits;
the mechanics reference/ability/element/curse/guardian descriptions are unchanged.
The compiled client renames many generated symbols; its changed hash must not
be dismissed as cosmetic without auditing the relevant code paths.

Preserve existing simulator/Bible/checkpoint pins rather than silently repin
all families. The new team contract can cite independently reviewed current
client excerpts. Broader source migration/live compatibility remains separate.

## Reviewed team evidence

Current client `ce(a)` returns `s===B.p&&this!==a||s!==a.r`, with `s=this.r`.
`B.p` is solo0 and the four shared teams have IDs1–4. Thus distinct solo seats
are enemies; equal nonzero teams are allies; self is never an enemy.
The current `dQ(a)` enumerates living players and filters through that predicate.
Guardian help states activation follows an enemy's turn, not any other turn.

The ending UI's `lU()` takes the first living member; a solo result returns that
member, while a shared-team result enumerates every member of the same team,
including dead members. The actual server sends endGame/isOver. Inferring a
local last-living-faction ending and queue timing remains explicitly provisional.
These source facts do not establish reward scaling or full-game training readiness.

The user approved central native team ownership/enemy selection/team victory,
keeping old arenas/checkpoints/live controls unchanged (ADR0135).
