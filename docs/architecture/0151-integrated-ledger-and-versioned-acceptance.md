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

## Implemented acceptance report contract

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
The ledger alone never grants that claim. The separate execution command below
can produce a version1 positive receipt after every requirement passes.

## Exact execution receipt

`simulation full-game-acceptance` runs the complete non-browser suite and the
standard 32-case roster probe in a new UUID evidence directory. It copies the
pinned catalog and Bible, rebuilds the ledger, records every collected test
identity, and checks exact JUnit identities and counters. Skips, deselections,
failures, missing tests, duplicate tests and unexpected tests reject acceptance.
The browser-control test file is deliberately excluded: this is the local
engine/training boundary, not certification of website automation. Environment
pytest options cannot narrow the selected suite.

The probe must use the full standard configuration: 2–9 players, four roster
layouts, four games per batch and two optimizer updates. Every one of the 256
original games must finish with a winner or draw. All 64 frozen collections
must reproduce exactly. Replays do not add independent games to that total.
The existing typed reports validate actor targets, finite optimization, changed
weights and diagnostic accounting; targeted rare-mechanic learning fixtures run
as part of the regression suite.

Source identity includes Python/native code, build configuration, the lockfile,
test files and fixtures, and reference snapshots. Accounts, recorded games,
checkpoints and caches are excluded. Native0.84.1 adds an embedded build-source
SHA-256 without changing kernel33 or any gameplay/action contract. CMake hashes
the sorted relative native input paths and each file's digest; Python computes
the same manifest independently and rejects a stale extension. CMake tracks
both source edits and changes to the input list. The receipt records this
identity, the installed extension's digest, Python/package versions and the
existing Torch/platform runtime description.

The runner checks code/build/runtime/input stability after execution and fully
validates the evidence before atomically publishing `acceptance.json`. Failure
or interruption retains diagnostic evidence and `failure.json`, never a positive
receipt. Parsing receipt JSON alone grants nothing: the verify command checks
current source/build/runtime, evidence checksums, rebuilt factory ledger, exact
test results and the full typed probe again. A changed build or source tree
requires fresh acceptance; historical receipts remain useful as historical
evidence. This is a local reproducibility receipt, not a cryptographic attestation
against an adversary who can rewrite code and all evidence.

Only the separate verified receipt sets `full_game_training_ready=true` for the
pinned provisional kernel33/public-observation3 scope. Historical checkpoints
and component reports keep their original flags. Official fidelity, live
checkpoint compatibility, live promotion and competitive strength remain false.
Provisional rules are permitted by the approved local boundary and remain
explicitly listed; passing acceptance does not turn them into official rules.

## Operation and verification

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-integration-audit

# Install/rebuild the current native package and the local training/test stack.
UV_CACHE_DIR=.uv-cache uv sync --frozen --extra simulation --extra training --group dev

# Fresh suite + learning matrix; writes a separate UUID evidence directory.
UV_CACHE_DIR=.uv-cache uv run --frozen --no-sync \
  godfield-bot simulation full-game-acceptance

# Supply the emitted directory, not the acceptance.json filename.
UV_CACHE_DIR=.uv-cache uv run --frozen --no-sync \
  godfield-bot simulation full-game-acceptance-verify runs/full-game-acceptance/UUID
```

Sixteen new checks verify the exact 296/291/237 accounting, primary versus
generated routes, all 14 source/test references, provisional paths, deterministic
JSON, rejection of corrupt classifications and false evidence/readiness claims,
and an offline CLI that leaves the native instance unstarted. Both the new and
legacy audit suites pass together. Source/test Ruff, changed-file formatting,
strict typing over 143 source modules, lock consistency and whitespace checks
pass. The acceptance runner adds 44 focused checks for exact test execution,
source/build identity, collection completeness, evidence paths, interruption,
matrix limits/configuration and separate local/live flags. The combined ledger
and acceptance checks pass 60 tests.

## Accepted local revision

The fresh execution retained at
`runs/full-game-acceptance/98418665-4755-42d6-b777-9628f4e6cb18/acceptance.json`
passed the full boundary:

- All 13,321 collected non-browser tests executed and passed, with no skips.
- All 32 player/layout cases passed; 64 optimizer updates consumed 122,455
  terminal targets, including 122,401 actor targets and 54 forced value-only rows.
- All 256 original games ended: 255 faction winners and one draw, with no engine
  failures, turn limits or decision limits. This is not a candidate win rate.
- All 64 frozen collections reproduced exactly; those repetitions are not
  additional independent evaluation games.
- The receipt passed an independent verification in a fresh process.

The accepted source-tree SHA-256 is
`f9c31280a661db3950f3934d45f6363639b06c5ad841cc37c96962b72ac595cd`;
native build-input SHA-256 is
`677f7eeb9bc96cd8544f088c37ffc448fe06b5b648d9c6b7e677a3840eabf7c9`.
The receipt also retains the exact native binary and runtime identities.
Local full-game training readiness is now true **for this verified provisional
revision**. Official fidelity, live compatibility, promotion and competitive
strength remain false. Source/test Ruff, changed-file formatting, strict typing
over 144 source modules, lock consistency and whitespace checks also pass.
