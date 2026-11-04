# Roster-wide integrated learning probes

## Audit finding

The acceptance boundary in ADR0097 applies to the separate integrated engine,
not just the older guardian arena reported by `full-game-readiness`. The current
kernel has source-pinned routes for all 237 held models, five devils, 40 regular
guardian effects, Earth/Moon and ten phenomena. Inventory/role registration
alone is not execution evidence. The native tests separately exercise owned
attack/defense/addition profiles, every generated-card route, guardian effects,
devils and phenomena, including interactions and transaction rollback.

The observation/collector/optimizer checks were narrower. Full-pool recurrent
episodes covered selected rosters, while gradient-shape tests covered 2–9
players without optimizing complete episodes for every roster size. This left
a concrete gap between the native multiplayer interface and the training
readiness requirements. Add an offline integration probe rather than using
candidate win rate to infer that coverage.

## Probe contract

`simulation full-game-learning-probe` defaults to 32 cases: 2–9 seats crossed
with solo, two alternating teams, alternating team/solo seats, and up to four
alternating teams. These are representative layouts, not every possible team
assignment. Existing team tests also enumerate all 125 three-seat maps. Each
case uses fresh version 3 weights, the pinned full held-card pool, cap 99,
18 slots, 28 choices, and two complete-episode PPO updates.

The first case starts at seed 1400000. Each case reserves four seeds, one
environment/sampling pair per update. Case offsets depend on the roster's
canonical position, so running a subset preserves its seed schedule. Repeated
collections intentionally reuse their original seeds; they are replay checks,
not extra independent games or extra optimizer updates.

Before each update, run a second collection from fresh native state with the
same frozen policy and seeds. Compare a digest of collection metadata, retained
public observations, accepted terminal trajectories, recurrent states, behavior
probabilities/values, terminal targets, outcomes, rejected commands and final
native state/statistics. Incomplete trajectories remain excluded by the existing
collector: their outcomes and final state are compared, but their discarded
intermediate observations are not reconstructed by this digest. Both copies
also run the existing per-seat behavior replay validator.

The report embeds the standard training report, so ordinary optimizer/credit/
hash-chain validation applies. A case passes only if both updates have real
terminal actor samples, finite validated metrics, positive gradient norm,
changed weights, no native collection error, and matching repeated digests.
Some truncated games can coexist with a passing case if other terminal games
supply valid learning samples. Counts and outcomes retain that distinction;
an all-truncated batch cannot pass. An engine error preserves its unaccepted
commands, skips optimization and stops that case. Other roster cases still run.

The probe reads 33 native diagnostic views after each collection. Their scope
includes every seat and any excluded episode. They never enter inference or
gradients. Counters retain their precise meanings: draws are not executions,
queue state and peak depth are not effect counts, and a nonzero family total
does not prove every model or interaction. Torch RNG state and thread settings
are restored even on failure. Weights are temporary; no checkpoint, source pin,
live model or native gameplay rule is changed.

## Initial matrix result

The full matrix passed all 32 cases and 64 real updates. Its 256 original games
ended with 255 winner outcomes and one draw, with zero native errors or limits.
All 64 repeated collections matched. It produced 122,455 terminal value targets,
122,401 voluntary actor targets and 54 forced value-only decisions. All six
interactive phases supplied terminal samples: opening, attack composition,
target selection, defense, trade and removal.

Selected observed counters:

| Mechanic | Original-game count |
| --- | ---: |
| Broom / Soap resolutions | 31 / 44 |
| CP utility uses | 48 |
| Dream Hat uses | 23 |
| Cost waivers, including defense | 48, including 1 defense |
| Post-death bows consumed | 12 |
| Area attack casts | 27 |
| Earth / Moon casts | 77 / 24 |
| Confusion forced turns | 54 |
| Exchange commits | 633 |
| Sell / Buy casts | 620 / 819 |
| Hidden attack-cost fizzles | 2 |

All five devil model counters, all 40 regular guardian draw counters and all
ten phenomenon draw counters were nonzero. Generated-action execution counts
covered 75 of 237 possible generated models; the separate exhaustive native
route tests cover the remainder. Because every original matrix episode ended,
these counters belong to terminal episodes in this run, but the generic report
does not infer that when truncations or errors are present.

The audit still found zero automatic overflow evictions, protected hidden
removal confirmations and hidden utility/defense cost fizzles. Native tests
exercise those branches, but this matrix does not establish complete-episode
learning coverage for them. Add deterministic targeted learning fixtures next,
preserving the actual terminal reward and excluding forced actor gradients.
Do not wait for random acquisition to happen to cover rare branches.

Follow-up: ADR0150 adds those targeted complete-episode learning checks. This
original matrix's counters remain unchanged; the targeted evidence is separate.

Retain the complete local report at
`runs/full-game-learning-probes/v3-roster-matrix-1400000.json`. The report is
evidence of collection/replay/optimization integration, not evidence of policy
strength. It keeps full-game training readiness, official fidelity and live
promotion false. The remaining acceptance work is an explicit mechanic-family
learning/interaction ledger and targeted fixtures for uncovered branches, followed
by a final audit of ADR0097. The November source refresh in ADR0134 remains
separate from the learner's preserved September/October source pins.

## Verification and operation

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation full-game-learning-probe \
  > runs/full-game-learning-probes/roster-matrix.json
```

Create the output directory first. Progress goes to stderr; the JSON report
goes to stdout. Select a smaller reproduction with `--players 4 --layouts
two-teams --games-per-batch 2`. Exit status is nonzero when a case fails.

Twelve focused tests cover stable disjoint case schedules, real learning,
exact parity with ordinary training, JSON roundtrips, corruption rejection,
limits without invented samples, native-error preservation, and caller-runtime
restoration. The full non-browser suite passes 13,240 tests. Source/test Ruff,
changed-file formatting, strict typing across 142 source modules, offline lock
consistency and whitespace checks pass. The repository-wide Ruff invocation
also exposes 13 pre-existing import/line-format findings in the native package's
Python exports/stubs; those are outside the source/test check and this change.
