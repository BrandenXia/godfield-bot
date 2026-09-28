# ADR 0068: Verified-only acquisition and broader ordinary inventory replay

## Status

Accepted, 2026-09-28. The operator chose verified official acquisition mechanics
instead of a synthetic experimental acquisition curriculum. Do not invent a
gift schedule, an owned-hand cap, or an overflow victim algorithm to unblock
training. Preserve the accepted schema-11 redraw baseline and its live-control
exclusion until separately versioned acquisition mechanics have official evidence.

One bounded official Training-computer match was run after checking that no
collector or browser occupied the account profile. The existing CLI, identity
lock, heuristic, pinned client/catalog, and passive v3 probe were used. It had
a five-minute per-game limit, 1,000-click budget, 90-second no-progress limit,
one completed-game budget, and no setup/gameplay retries. No human room or
public Duel was entered, and no neural candidate controlled the game.

## First real v3 capture

Run `60fe19b4-1ed3-42cf-9ce6-b63c52baa858` completed with a classified heuristic
loss and 20 in-match actions. There were no setup/gameplay failures, hangs,
disconnects, source/server gaps, repeats, drops, rejections, hook/read/ack
errors, unresolved item owners, malformed wire fields, or unreviewed events.
The final collector drain succeeded. This is mechanics collection, not a
candidate strength evaluation.

There are 23 batches, 12 ordered snapshots, 11 adjacent inventory pairs,
29 self-event wire sidecars, seven selected self attack items, two selected
self defense items, and 18 explicit self gifts. All 108 raw omitted owned used
flags remain omitted/unknown; the pinned-client default is a separate projection.
There are no performed-miracle activations, hand growth, or overflow items.
The maximum observed owned population is nine, not an inferred official cap.

The complete sanitized collector evidence and summary are saved in
`tests/fixtures/acquisition-v3-60fe19b4.json`. All original event sequences,
batch digests, wire omissions, and redacted opponent bodies are preserved.
The input fingerprint is
`502ab0aca105ea5ea085bdfe229736ad8e9fa8692e9af7e7523eeef6de0421d1`.
The reviewed client and catalog identities are unchanged from ADR 0067.

## Evidence-bounded native expansion

The existing C++ `OrderedInventoryReplay` already accepts an explicit ordinary
model allowlist, so no kernel, package version, or native replay schema change
is needed. The Python differential projection advances to
`observed-inventory-projection-verified-ordinary-wire-aware-v3`. Its ordinary
allowlist now contains only models with explicit captured self consumption:

| Model | Artifact | New captured use |
| --- | --- | --- |
| 26 | Glaive Classic | Attack |
| 29 | Final Tusk | Attack |
| 32 | Power Halberd | Attack |
| 41 | Hexagon Doom | Attack |
| 44 | Direct Smash Axe | Attack |
| 55 | Angel Axe | Attack |
| 123 | Iron Gauntlet | Defense |
| 135 | Iron Armor | Defense |
| 192 | Heart Dew | HP utility through `useAttackItems` |

Models 23 and 142 remain admitted from the original v2 fixture. For each new
model, a test seeds C++ from the exact preceding inventory, consumes the
explicit self-bound single-item selection, appends its explicit gift, and
compares every resulting item row and its order. This includes recycled IDs
and utility consumption. These isolated operation checks do not simulate
the artifact's combat ability or prove a universal one-gift-per-use schedule.

Category membership alone does not admit a consumable. Flare Axe/model 110 is
gifted in this run but never selected; it stays opaque. The differential
dispatcher now also explicitly rejects multi-item selections, including
combinations of individually witnessed ordinary models. The general native
atomic-selection primitive remains available for diagnostic callers, but its
existence is not official combination evidence. The single Flame/model 215
retention comparison remains the older observation hypothesis, not newly
verified miracle physics or training data.

The pinned client's `boostHP`/`boostMP` handlers and `eW`/`dH` helpers update
only numeric resource displays, not owned inventory. They are admitted as
inventory-neutral for this diagnostic. Combat/resource correctness is still
not asserted. An unexpected inventory change on such an update remains a
mismatch; no resulting inventory is patched into the predicted state.

`addCurse` is deliberately not admitted as universally neutral: its handler
has a conditional Dream-refresh path. The capture does not preserve enough
curse payload to exclude that path for arbitrary future updates. The isolated
Hexagon Doom consumption pair matches, but the full update is unsupported.
`buy`, `setBought`, and other unreviewed effects also stay unsupported.

## Preserved real ambiguities

The official server omitted `items` on two self defense events, including
the terminal defense. V3 records `items_kind="missing"`, not a fabricated
explicit empty array. The transport diagnostic reports
`ambiguous_self_selections`; the differential replay does not relax this guard
just to make a complete-run result pass. One of those updates also contains
buy/setBought and changes inventory ordering; it is not a no-op transition.

The full run has one matched initial inventory, eight matched adjacent
transitions, eight counted consumed items, 17 counted gifts, zero mismatches,
and three unsupported updates: the curse update and the two omitted-selection
updates. Counters exclude partially processed unsupported rows. Independent
later pairs can use their recorded baselines, but earlier unsupported rows
remain visible and `complete_projection_replay` remains false. Self-event
metadata availability is true; it is not a mechanics pass. All combat, gift
scheduling, overflow, training, promotion, and acquisition-rule flags stay false.

## Verification and next boundary

The 23 new regression tests cover the full real-v3 fixture/hash, all nine new
native operation pairs, conservative full-run results, read-only deterministic
CLI behavior, opaque gifted models, resource-event inventory mismatches,
unreviewed effects, and rejection of unobserved multi-item combinations.
The original v2 run still matches all four inventories, and all four previous
run fingerprints are unchanged. Historical evidence is not rewritten.

All 805 non-browser tests pass. Ruff lint and changed-Python-file format checks
pass; Mypy passes across 62 source modules. Offline locked uv validation and a
wheel build succeed. The two existing browser-control tests were not run; the
bounded Training CLI exercised the real browser harness with the official bot.
No native dependency, checkpoint, live policy, or promotion gate was changed.

Continue with explicit performed-miracle first-use/reuse, combination/disguise,
and overflow/removal captures. Gift scheduling and empty-hand behavior remain
unverified. The wider redraw training environment is preserved; this change
does not make its learned candidate eligible to control official games.
