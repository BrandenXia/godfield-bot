# ADR 0127: Native Earth Drop and weighted generated-artifact pools

## Scope and remaining objective

2026-10-17. Native0.74.0, kernel/observation/plan/metadata25,
`integrated-full-game-development-v25`; six-column command1, family6 and
trade-choice2 remain unchanged. Continue the separate integrated engine toward
ADR0097's complete acceptance requirements. Existing arenas, checkpoints,
live controls, accounts and credentials are unchanged; no training or live
game starts. Local-training/full-game/official-fidelity/promotion gates remain
false. Git staging is unavailable in this task's read-only Git directory;
changes remain saved in the working tree, not committed.

This adds an executable, labeled provisional Earth Drop path and prepares both
complete category pools, not a complete Earth/Moon action engine. The guardian
ledger is41/42 joined models; Moon286 remains an atomic development error.
That count is not a fidelity percentage or evidence of training readiness.
Complete Apocalypse/Sacrifice and virtual commands, team/reward/elimination
rules, hidden cross-role resolution, cap99 migration, complete action/policy/
checkpoint interfaces, full-episode learning/liveness and official differential
validation remain required. Do not narrow the goal to scripted first turns.

## Frozen evidence and explicit assumptions

Use the existing catalog/client pins, not a new source-freshness claim:

- Catalog `df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
- Client `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.

The complete guardian Bible table/hash remains pinned independently. API285
is Drop/`addItem`/Earth, and286 is Full Moon Blade/ATK10/
`categoryWeapons`/Moon. Exact API objects are validated, not inferred from names.
Bible notes restrict Earth to trade/weapons/armor/sundries and Moon to miracles.
The saved client `attackByGuardian` branch10607–10665 displays artifact model
IDs from its generated payload without the held `useAttackItems` branch's
inventory consumption or ordinary MP debit. Its explicit MP-powered weapon
exception remains relevant to future generated weapon work. The `addItem`
branch11223 onward processes an artifact receipt; `A.la` around3997 exempts an
`addItem` leader from ordinary selected-miracle charges.

These facts do **not** prove the server's generated-list construction,
recipient, cardinality, category probabilities, compound timing, local cap,
disguise probabilities or event hooks. The local Earth interpretation is one
Drop plus one weighted artifact, native uniform living-enemy targeting, generic
guardian-origin response, then a fresh receipt at the final recipient. It is
explicitly provisional, not a claim that every official Earth action has this
shape. It does not execute the sampled artifact's ordinary attack/trade/utility
ability. Moon construction is not approximated by silently using ordinary
held-card controls or omitting defensive miracles from its pool.

The three previously audited redacted `attackByGuardian` acquisition snapshots
(events111198/111311/111414) identify neither special guardian nor generated
model/distribution. They do not validate this provisional interpretation.

## Approved complete sampling contract

The human approved category-filtered **pinned gift weights**, not uniform Earth
sampling. Derive every row from the separately pinned complete held-category
and acquisition plans. Fields are `(group,model_id,category,gift_weight)`:

- Earth9:207 models, weight470, all non-miracle held categories.
- Moon10:30 miracles, weight30. Their pinned weights happen to be equal.
- Combined237 rows in held-model order; SHA
  `f3dba9f996e4c41eb61a4e0c16630713974e5d75c422d25038b12a0ee61bc3f8`.

No card is removed because its ordinary role is passive, defense-only, trading
or expensive. The source plan schema2 pins exact rows/fields/weights and rejects
relabeling. Native admission accepts bounded test subsets, checks categories,
group compatibility, identities, duplicates and cumulative weights, copies
owned sorted pools, and rejects malformed arrays. The factory always supplies
the complete source contract. A raw fixture without Earth profiles still fails
atomically if Earth activates; Moon activation always fails explicitly. All ten
summon outcomes remain sampled.

## Shared receipt and response lifecycle

After the original tick, a living other-seat Earth guardian passes its existing
25% trigger, draws a model from its complete weighted pool and a living enemy
from the guardian target stream. Queue family4 stores guardian model285,
guardian identity and effect12/model payload. The effect is zeroATK/origin4;
ordinary armor and weapon/miracle-only defenses cannot respond. Super Mirror
retargets through the existing chained-response path, with no reroll.
Current response views reveal the generated model; future queued models,
identities and tickets remain diagnostic/private. A dead or replaced queued
guardian suppresses its receipt. Nested Bow/counter/death work finishes before
later guardian siblings. There is one original-owner tick and one guardian
wave, never a guardian-owner turn or recursively triggered wave.

New private `receive_artifact` provides a fresh monotonic identity, unused flag,
recipient-Dream category-safe disguise, explicit cap rejection or approved
oldest-held eviction. Gifts, accepted trades and Drop share this storage
operation while retaining separate accounting. Drop never removes/performs
anything from the guardian owner's real hand, spends ordinary MP/price, counts
as a transfer, or creates a per-use replacement gift. No devil trigger is added
to Drop (or market receipt); that event-hook interpretation remains provisional.
The received artifact is real held inventory for later ordinary use/passive
effects. No fake held card is temporarily injected to simulate generated use.

The utility effect helper is also separated from card admission/consumption/
payment in preparation for Moon. Dream cure reads staged status and restores
the actual staged hand. `finish_turn` consistently uses the already-recorded
original owner even when a generated effect is executed by another seat.

Two independent staged illness-seed XOR streams are generated model
`0x2ba9c55d741831f6` and receipt disguise `0xce5c3e169b87931e`.
All prior streams retain their salts and ticket order on successful unchanged
paths. Invalid late rows, cap failures, stale commands and unsupported Moon
effects roll back the entire batch, including model/disguise draws and IDs.

## Diagnostics and bounded checks

- `guardian_generated_snapshot[B,7]`: Earth casts, model draws, receipts,
  disguises, overflow evictions, blocked and suppressed tasks.
- `guardian_generated_model_counts[B,237]`: actual generated models3..239;
  unimplemented Moon never claims model draws.
- Existing guardian model histogram stays `[B,40]` for standard245..284.
- Existing guardian effect view reveals285/current source/current target;
  `attack_effect_observations` reveals kind12 and current generated model.

New arrays are owned/read-only, diagnostic rather than policy inputs, cleared
on reset, and preserved in old returned snapshots. The metadata validates all
layouts and keeps complete-action/checkpoint readiness false.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-earth-smoke \
  --batch-size 4096 --players 9 --seed 67
```

This unforced-trigger/unforced-weight scripted first-turn probe records1045
receipts,519 Dream disguises,5141 commands and4096 original ticks, with194/207
Earth models observed. It explicitly reports zero full games and disallows
teacher/reward/training/promotion use. Separate parameterized unit tests force
each of207 source models through2/3/9 seats, both Dream states, while independent
ticket oracles check native weighted activation/model/target draws. Tests also
cover reflection, cap rejection/oldest eviction, whole-batch rollback/corrected
retry, nested death suppression, policy privacy, reset and gate tampering.

Eighteen prior default behavioral replay hashes remain unchanged. Only metadata
pins change there. The uniform512/three-seat/seed67 phenomenon probe now commits
512 rather than507 first turns: its five Earth failures resolve, with1143 rather
than1133 commands and unchanged4839 attack HP loss. Other seeds still reach
Moon errors: seed0 retains failed rows71/73/194/400, reports508 completed first
turns and never retries failed rows indefinitely. Passing the default seed is
not complete Solar or full-game outcome coverage.

Verification: **9484 non-browser tests passed in168.17s**, including1319 Earth
runtime/report tests. Ruff passes across `src`/`tests`; mypy passes all124
source modules; all89 selected full-game/CLI Python files are formatted.
Changed native files pass clang-format, the frozen lock passes its offline
check, and `git diff --check` is clean. Installed native0.74.0 reports
kernel/observation25, command1, trade2 and family6. The default Earth probe's
metadata/replay pins are respectively
`1606e515742fac1b793da51f395bc0a0a93f966aabd64b0b182834ef61a64ad4` and
`ab3501d0fa1b392b701a9b77c2fc8bfa27608502adbaac5d0288affefd24b84c`.
The4096/nine-seat pins are
`1c37d23119dc3815cc4de0d03c1b96cf263be8a69a3c2526575a8edf5a32e1e6` and
`e296d70fadcb948f5d0ef9ac5646995845dbad1e2c39545bd26a36bf17bbaaba`.
These are local diagnostic reproducibility pins, not official-game validation.
