# ADR 0097: Full-game integration audit and readiness plan

## Status and boundary

2026-10-01. The user requested continued work until full-game training readiness.
Audit the **actual integrated training environment**, not just the largest
standalone native catalog or the latest candidate's win rate. This step adds
no simulated mechanics and does not declare the full-game objective achieved.

The overall architecture choice is awaiting user direction: a separate versioned
full-game C++ environment reusing tested components is recommended; continuing
isolated guardian-wrapper extensions is the alternative. Do not silently change
old action/observation contracts, checkpoint compatibility, or live controls.
The user's previous permission to layer labeled provisional rules and keep
promotion gated remains applicable.

## Current source freshness

The public [item catalog](https://godfield.net/i18n/en.json) was fetched through
the pinned pygodfield client on 2026-10-01 and saved separately to
`data/snapshots/2026-10-01/api-catalog-en.json`. Its 296 records have content
SHA-256 `df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`,
identical to the reviewed 2026-09-21 catalog. The 291 Bible artifacts exclude
five non-artifact API records; these counts are not interchangeable.

A read-only fetch of the public [official client](https://godfield.net/main.dart.js)
also reproduced SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`,
the 2026-09-20 Bible's pinned client. Its reported Last-Modified header was
2026-08-11 01:40:09 UTC. The old snapshots, source pins, dependency revision,
accounts, and game sessions were not changed. Matching source bytes establish
source freshness at this check, **not** simulated behavioral fidelity.

## Integration accounting

The legacy wide-hand attack/defense component audit includes 196 artifacts.
That is still valid for **that component**, but it is not the guardian arena
used by the newer recurrent policies. Its coverage cannot be added to the
guardian count or used to declare full-game training readiness.

New `simulation full-game-readiness` audits the guardian discard/utility arena
with a fresh throwaway native state and no rollout decisions, training, network,
account access, or live-policy writes. It validates the complete API/Bible
category/asset mapping and source-pinned native metadata, then assigns every
artifact exactly one integration level:

| Level | Count | Meaning |
| --- | --- | --- |
| Inventory usable | 102 | Existing legal policy card/discard paths can use the model. |
| Opening only | 5 | Mars effects are reachable only through scripted episode initialization. |
| Component only | 34 | Native caller-driven guardian primitive exists, but no arena episode path. |
| Not integrated | 150 | No active inventory/opening/guardian-component route in this arena. |
| Total | 291 | Every pinned Bible artifact appears exactly once. |

Inventory models are 39 weapons, 47 armor, nine miracles (six attacks, two
defenses, Spring), and seven sundries. The 150 wholly unintegrated artifacts
are 68 weapons, 31 armor, 21 miracles, 12 sundries, five devils, ten phenomena,
and three guardians. The latter are Diamond Axe and the Earth/Moon specials.
The 34 component-only guardians are **also not playable regular arena events**;
they must not disappear from the remaining full-game work.

The report lists all model IDs/assets and fourteen reviewed workflow gaps.
Counts are integration accounting, not a percentage of correct official rules,
test completeness, training quality, or strength. A usable artifact can still
have provisional timing, target restrictions, replacement rules, or incomplete
interactions. For example, Spring is self-only, and Turbulence permits only one
bounce. Neither artifact inclusion nor a functioning primitive proves fidelity.

The audit schema describes this existing subset, not a future engine's
acceptance gate: it keeps full-game readiness, official fidelity, live
compatibility, and promotion false. Duel-subset training remains available.
Free-for-all rollouts support 2–9 seats, but current signed-advantage neural
training is explicitly duel-only. Team support is absent here.

## Remaining workflow requirements

The report tracks separate unresolved requirements and source files:

1. Acquisition and overflow: complete initial distribution, replacement timing,
   hand growth, capacity handling and compaction, not just the provisional refill.
2. Offensive combinations: multiple cards, boosters, chance/area/random attacks,
   dual-role and special weapon effects.
3. Special defense: typed origins, special armor/weapons, reflections, counters,
   reductions and full redirect chains.
4. Utilities and costs: complete utility catalog, target decisions, cost changes
   and reusable-card state.
5. Curses: integrated disease progression/periodic effects, fog/flash, confusion,
   dream and redraw, cures, and all timing interactions.
6. Guardians: summon/ownership/lifecycle, regular activation, all effects,
   origin classification and special guardians.
7. Devils: all damage/removal/resource effects, legal targets and event timing.
8. Phenomena: all ten global effects, inventories, resources, curses and guardians.
9. Economy: trades, buy/sell, gifts, CP, resource exchange and responses.
10. Removal/revival: Broom, Soap, sacrifice, revive, legal selections and lifecycle.
11. Apocalypse and terminal flow: timing/escalation, ending rules and interactions.
12. Teams/multiplayer learning: legal ownership/targets, teams, elimination,
    rewards and credit assignment beyond duels.
13. Complete action/observation contract: every phase's choices, observable
    statuses/history, padded hand capacity and explicit checkpoint transfer.
14. Full-game validation: integrated interaction coverage, deterministic replay,
    native/Python parity, bounded liveness, learning probes and official checks.

These are not fourteen equal-sized tasks and do not support a completion ETA.
Existing standalone attack/defense and replay components should be reused where
their contracts match; they must be integrated and tested, not counted as done
just because a class already exists.

## Full-game local-training acceptance boundary

Full-game **local** training readiness must eventually require all of:

- Every artifact has an implemented, reachable route appropriate to its category
  (inventory action or event), with no unsupported/no-op placeholders for effects.
- Complete phases, state, legal actions, costs, inventory changes, random streams,
  guardian/event timing, curses, teams, apocalypse and terminal transitions are
  connected in one versioned environment, not only isolated primitives.
- Policy projections never expose opponents' hidden inventory, and phase/seat
  memories reset correctly; observation/action changes get explicit migration.
- Native/Python interfaces are atomic on invalid batches, deterministic under
  replay/reset, and handle mixed terminal/active rows without looping indefinitely.
- Interaction tests and seeded full-episode smoke/learning probes exercise every
  mechanic family and all supported player/team configurations; wins, losses,
  draws and truncations remain distinct.
- Checkpoints, source/effect ledgers, logs, coverage and evaluations identify the
  complete environment and all remaining provisional assumptions.

As previously approved, clearly labeled provisional mechanics can support local
training once complete and tested. Official fidelity and live promotion still
need independent official differential evidence and their own acceptance gates.
Local full-game readiness must not be made contingent on claiming unobserved
mechanics official-verified, nor used as permission to control live games.

No readiness flag is loosened in this audit, and candidate diagnostic win counts
cannot substitute for any missing mechanics. The retained local reference
`3d09213e-6c5e-4ca4-86f0-f8725d6678fd` and its frozen roster remain unchanged.

## Commands and verification

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-readiness \
  --catalog data/snapshots/2026-10-01/api-catalog-en.json \
  --bible data/snapshots/2026-09-20/bible.json
```

The command is offline and reproducible. Source freshness is established by the
separate dated refresh, not inferred from offline report generation. Existing
`simulation coverage-report` is unchanged and retains its narrower native
artifact-inclusion scope.

Fifteen tests cover exact integration/category counts, Mars-only initialization
(not Mars Ring), subset-versus-full readiness, workflow provenance, aliases,
bucket/count tampering, false gate claims, deterministic JSON roundtrips,
source/catalog drift, a refreshed same-content snapshot, and the offline CLI.
The full non-browser suite passes 1,796 tests. Ruff, changed-file formatting,
strict typing over 81 source modules, offline lock consistency and whitespace
checks pass. No native rebuild or training run is needed for this audit.
