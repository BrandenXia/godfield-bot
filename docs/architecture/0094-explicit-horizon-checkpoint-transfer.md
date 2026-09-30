# ADR 0094: Explicit longer-horizon checkpoint transfer

## Decision and boundary

Accepted by the user, 2026-09-30. Add a separate, opt-in transfer to reuse a
local guardian arena policy at longer bounded episodes. Do not relax ordinary
resume, utility migration, or discard migration. Native 0.46.0, source pins,
card coverage, action widths, live policies, accounts, and credentials are
unchanged. All full-game, official-fidelity, live-compatibility, and promotion
flags remain false.

`simulation guardian-train --migrate-horizon-from CHECKPOINT` creates a new
private child, with fresh optimizers and per-seat recurrent memories. It is
mutually exclusive with `--resume`, `--migrate-utilities-from`, and
`--migrate-discards-from`. It may extend either or both episode bounds, never
shrink either, and must extend at least one. Bounds remain strict integers in
the existing range 1–100,000. There is no unlimited local episode mode.

This operation is supported for the original 7-feature/30-action arena,
9-feature/30-action utility arena, and 9-feature/48-action discard arena. It
does not change or combine those schemas.

## Why a direct resume would change the policy

The 43-global-feature observation contains two limit-normalized inputs:

| Column | Input | Initial weight-column multiplier |
| --- | --- | --- |
| 7 | turn count / max turns | target max turns / source max turns |
| 42 | adapter decisions / max decisions | target max decisions / source max decisions |

Keeping the old weights but increasing limits reduces these inputs for the
same position. The transfer instead clones the source and rescales only these
columns of `global_encoder.0.weight`. At equal counts, the first layer's input
contributions are preserved up to floating-point rounding. The bias and every
other parameter are copied exactly. Column 8 (defense-toggle fraction) is
deliberately untouched; its separate native limit is not migrated.

Before optimization, logits, value estimates, and recurrent memory match for
the same trajectory before the old absorbing limits, within numerical
tolerance. Legal masks, initial deals, source-reviewed rules, and refill RNG
are identical for identical seed, batch, and actions in that prefix. Terminal
rewards, reset/refill behavior at the old limit, and behavior after it are
**not** equivalent: those differences are the purpose of extending episodes.
New optimizer updates are expected to change the copied weights.

## Contract and provenance

The loader verifies source weight checksum, schema, architecture, and finite
parameters. A fresh arena is built at the original bounds, then checked with
the existing strict resume compatibility check before transfer. This prevents
simultaneous changes to rules, sources, rewards, initial resources, refill
distribution/stream, guardian opening, defense limits, observations, or model
architecture. Batch size and seed may change under the existing training
contract; prefix-trajectory equivalence requires keeping them equal.

The optional `horizon_migration` record is schema 1, ID
`guardian-horizon-input-rescale-v1`. It includes source model ID,
manifest/weight SHA-256, complete source architecture/arena, target bounds,
column indices and exact target/source ratios, and the equivalence scope.
It explicitly records that optimizers are not resumed. Validation cross-checks
ratios and target bounds and rejects unrelated metadata changes or combined
migration records. It does not treat untrusted provenance text as proof of
official fidelity or learned performance.

The parent files are never rewritten. New directories are mode 0700 and
weights/manifests 0600. Both non-finite source weights and finite weights that
overflow during scaling are rejected. Historical absent migration records
remain null. Resuming a transferred child at the same bounds records only its
immediate parent checksum, not a fabricated duplicate transfer. The parent's
original bounds continue to be enforced when that parent is loaded normally.

## Local experiment recipe

Transfer the existing 32-turn / 128-decision discard parent into 128 turns /
512 decisions. Both input columns therefore receive a multiplier of 4.

Source:

- model `0664c622-6cbe-47f8-a29c-a55dad54313a`;
- weights SHA-256 `76d09d40e49b8c5beff62e0b0160193b7fc613e5bf95786ad9ca01f4a547687a`;
- schema 3, hand width 9, actions 48, hidden 128, embedding 32;
- mixed opening, HP 40 / MP 10, weighted discard-consumption refill;
- source rules and gamma 0.99 / shaping scale 0.1 unchanged.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --migrate-horizon-from checkpoints/guardian-arena/0664c622-6cbe-47f8-a29c-a55dad54313a \
  --inventory-utilities --inventory-discards \
  --refill weighted-discard-consumption-v1 \
  --batch-size 32 --max-turns 128 --max-decisions 512 \
  --rollout-steps 128 --teacher-updates 0 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --ppo-epochs 2 --environment-minibatch-size 16 \
  --evaluation-games 32 --cpu-threads 2 --seed 67
```

This is 131,072 newly collected decisions across both actors, not that many
policy-gradient examples; greedy overrides are excluded from PPO eligibility.
It is bounded local training, not an official-service collector. A command
rerun creates a new UUID child; it does not overwrite the artifact below.

Child `14230655-0841-4859-83a0-49f05b9e7e66`, weights SHA-256
`c6940cbb4403d7283863b87fdefcb5cdbc09b2845783a1985c397863ce1eaa23`,
completed all 32 updates and round-trips through the verified loader. The
parent's original weight digest remains unchanged. There is no teacher-stage
evaluation or newly collected teacher window, since `teacher_updates` is zero.
Training-only defense feedback remains enabled.

The current training segment has 98,067 PPO-eligible decisions: 35,971
winner-covered (36.68%), 2,884 truncation-covered, and 59,212 open. Across both
actors, winner-covered / truncation-covered / open counts are
47,519 / 3,987 / 79,566. It records 850 completed episodes and 61 truncations.
The source's historical missing coverage is not backfilled into these numbers.

| Diagnostic seed / games | Initial transferred policy W/L/truncated | Trained child W/L/truncated | Child learner voluntary passes |
| --- | --- | --- | --- |
| 1,000,070 / 32 | 11 / 19 / 2 | 11 / 19 / 2 | 57 |
| 4,000,070 / 64 | 17 / 37 / 10 | 19 / 38 / 7 | 153 |
| 5,000,070 / 64 | 22 / 37 / 5 | 21 / 36 / 7 | 100 |

The first initial evaluation is persisted in the child's manifest. The other
initial scores are the rescaled read-only preflight in ADR 0093, with identical
source/configuration. The two extra child sets total **40 wins / 74 losses /
14 turn-limit truncations** versus **39 / 74 / 15** in the preflight. This is
not a credible strength gain. All child sets have zero defense-toggle or
decision-limit exits, zero defense deselections, and zero forced passes. The
increased voluntary passing is undesirable; this child is **not recommended
as a replacement** for the source or the ADR 0093 diagnostic reference. No
live or local promotion baseline was changed.

Inspect its measured exposure without running any games:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-training-report \
  --checkpoint checkpoints/guardian-arena/14230655-0841-4859-83a0-49f05b9e7e66
```

## Verification and remaining work

Tests cover all three architectures, exact unchanged tensor copies, recurrent
prediction equivalence for power-of-two and non-power-of-two ratios, actual
arena prefix mechanics/RNG, extended absorbing boundaries, one-bound transfer,
strict bounds, no-shrink/no-op rejection, source non-finiteness and scaling
overflow, private immutable-parent exports, normal strict resume, conflicting
sources, unrelated contract changes, historical null records, standalone
transfer equivalence, manifest tampering, and the CLI path.

Verification at this milestone: 1,688 non-browser tests passed (including 99
new coverage/transfer tests); the two local browser-control tests passed during
this turn. Ruff, changed-file formatting, mypy over 78 source modules, offline
lock consistency, and whitespace checks pass. No native rebuild or dependency
update is needed for this Python-only training change.

The transfer supplies continuity, not a strength gate. Development evaluations
reuse diagnostic seeds, not promotion holdouts. Longer coverage alone did not
improve the ADR 0093 policy. Remaining work is a better tactical curriculum and
broader integrated source-reviewed C++ rules. This still does not implement
full official acquisition/events, trade, Apocalypse, every card, or official
multiplayer scheduling, nor authorize a local arena policy to control live play.
