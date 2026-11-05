# Integrated ledger and separate local acceptance

The user approved a separate versioned local-training acceptance report tied
to the exact source tree, native build and test results. Historical checkpoint
metadata must retain its original values. Official fidelity, live compatibility
and live promotion remain independent gates and are not granted by this report.

## Current engine ledger

`simulation full-game-integration-audit` builds a fresh, unstarted kernel33
instance through the actual full-game factory. It uses cap99, all 237 weighted
held models, 18 slots, a representative four-player team roster, and the public
version3 encoder. It performs no game actions, training or network access.

The ledger joins all 296 source catalog entries without conflating their roles:

| Kind | Count |
| --- | ---: |
| Held Bible artifacts | 234 |
| Held Exchange/Sell/Buy cards | 3 |
| Virtual Discard/Sacrifice controls | 2 |
| Devils | 5 |
| Regular and generated guardian effects | 42 |
| Phenomena | 10 |

The Bible total is 291, excluding the three held trade cards and two controls.
The role manifest covers exactly the 237 held models. Each entry has primary
owned/event routes derived from the actual source-pinned profiles. Generated
guardian routes are separate: using an armor model as a generated Drop receipt
does not prove its owned armor effect. Earth/Moon producer identities have their
own routes, with the complete generated pool and action construction retained
in metadata. Every model requires a primary route.

The 14 workflow requirements from ADR0097 map to current native/Python source
files and required regression files, including both the roster-wide learning
probe and targeted rare-mechanic learning tests. These references declare what
must be tested; they do not assert that tests ran or passed. The ledger also
retains each metadata path whose rule explicitly says provisional. There are
130 such fields in this revision, including nested component descriptions and
duplicates at different integration levels. This is not a count of independent
unknown mechanics or an estimate of official accuracy.

Nested component metadata deliberately retains historical scope/readiness
statements. The composed factory's selected policies and the eventual separate
acceptance report determine the current local-training scope; old primitive or
checkpoint records are not silently rewritten. The new ledger itself keeps
execution evidence, local full-game readiness, official fidelity, live
compatibility and promotion false. All sources are the existing reviewed
September/October pins, with November freshness differences documented in
ADR0134 rather than silently merged into those pins.

The older `simulation full-game-readiness` continues to describe the guardian
subset from ADR0097. Its 102 usable inventory models and unresolved subset
workflows are not the current integrated kernel's counts.

## Acceptance report contract to implement

The separate acceptance step must consume or produce verifiable evidence for
all six local requirements in ADR0097:

1. The complete source/role/event ledger above, rebuilt against the current
   factory and validated against the pinned API and Bible identities.
2. Passing native transition, interaction, transaction and deterministic replay
   tests for the connected workflows, not only profile registration.
3. Public observations, per-seat recurrence, exact versioned transfers,
   terminal-only credit, optimizer/resume and frozen-evaluation checks.
4. The full representative 2–9-player learning matrix, with real outcomes,
   accepted target counts, repeated collection digests and native counters.
5. The targeted learning fixtures for rare branches absent from that matrix.
6. Matching source tree, compiled native binary, runtime, validation inputs and
   evidence digests, so a report cannot silently certify changed code.

The report should retain the exact collected test node IDs and executed test
results. Missing, duplicate, skipped, failing or uncollected required tests must
not count as a passing workflow. A source/build change while checks run must
invalidate acceptance. Repeated games remain replay evidence, not independent
evaluation games; passing these checks does not certify tactical strength.
Only a report meeting the complete local boundary may claim local readiness.
No report in this step grants that claim yet.

## Operation and verification

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-integration-audit
```

Sixteen new checks verify the exact 296/291/237 accounting, primary versus
generated routes, all 14 source/test references, provisional paths, deterministic
JSON, rejection of corrupt classifications and false evidence/readiness claims,
and an offline CLI that leaves the native instance unstarted. Both the new and
legacy audit suites pass together. Source/test Ruff, changed-file formatting,
strict typing over 143 source modules, lock consistency and whitespace checks
pass. Full execution certification is the next implementation step.
