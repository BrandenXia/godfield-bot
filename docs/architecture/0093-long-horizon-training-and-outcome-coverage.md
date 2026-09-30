# ADR 0093: Longer local training, outcome coverage, and phase isolation

## Decision and boundary

Accepted, 2026-09-30. Continue ADR 0092 by exercising longer bounded episodes
and measuring winner-outcome availability during local training. Keep native
0.46.0, the 102-card provisional discard curriculum, actions, feature widths,
source pins, reward, and live controls unchanged. This is not new C++ card
coverage or official full-game fidelity.

The 32-turn parent's rules cannot silently resume at 128 turns. A new model is
trained **from scratch** at 128 turns / 512 decisions. Subsequent continuation
changes only training-window/update settings while retaining those recorded
arena bounds. No old checkpoint is overwritten or promoted. Full-game, official,
live-compatibility, and promotion flags remain false. No official-service games,
accounts, or credentials were touched.

A separate user choice was requested about an explicit horizon-changing
checkpoint transfer and subsequently approved. Its implementation and separate
local experiment are recorded in [ADR 0094](0094-explicit-horizon-checkpoint-transfer.md).
Ordinary resume and existing utility/discard migrations still reject changed bounds.

## Outcome coverage is observability, not a new return

`GuardianWindowOutcomeCoverage`, schema 1, scope
`current-window-only-no-future-peeking-v1`, classifies each sampled decision by
the next absorbing outcome **within its collection window**:

- winner-covered: that episode reaches a winner before the window ends;
- truncation-covered: that episode reaches an existing absorbing limit;
- open: its outcome is not available within the window.

Reverse traversal uses copied terminal/truncation flags. Episode boundaries
override later outcomes, so a next game's winner never labels the previous
game. A tail stays open even when its game finishes in a later window. The
helper does not read hidden hands, consume randomness, mutate trajectories,
change legal actions, or relabel historical data.

The three groups account for every sampled decision, alongside their
`trainable_*` subsets. In teacher collection, trainable means imitation-eligible
labels across both actors. In PPO it means learner-policy-eligible decisions,
excluding greedy-opponent overrides. A winner may be a loss for the acting
player; these are not learner wins or policy-gradient sample multipliers.

Signed GAE remains unchanged (gamma 0.99, lambda 0.95 in these recipes), including
zero bootstrap at the existing absorbing boundaries. Winner availability does
not imply strong terminal credit: GAE can heavily attenuate distant rewards and
still use value estimates. Coverage does not imply accurate values, expert
labels, learning efficiency, strength, or a passed promotion gate.

Collector, teacher/PPO logs, and manifests record the measurements. Manifests
cross-check sample totals, trainable counts, and completed/truncated episodes.
New optional fields preserve historical compatibility: missing measurements
remain null, never fabricated zero. No tensor/action/observation schema changes.

## Phase isolation and reporting

Fresh runs now persist `evaluation_teacher` after imitation and before PPO,
using the same diagnostic seed, games, paired seats, and recorded arena. It does
not consume policy RNG or change collector memories, trajectories, optimizers,
or subsequent weights. Historical missing stage evaluations remain unknown;
zero-teacher runs have no teacher-stage evaluation.

`--updates 0` is an explicit imitation-only export, requiring positive
`teacher_updates` and zero PPO defense-feedback weight. It has its own algorithm
ID, `provisional-guardian-duel-recurrent-imitation-only-v1`, no PPO updates, and
equal teacher/final evaluations. Normal defaults and PPO formulas are unchanged.
Selected-defense imitation weighting still applies. Zero updates in both phases
and inapplicable PPO feedback fail before creating a checkpoint.

`guardian-training-report --checkpoint <directory>` checksum/architecture-
verifies the saved local model and summarizes each phase. It runs no games or
source refresh, modifies no files, and preserves the caller's CPU Torch RNG.
Scope `sum-independent-windows-no-backfill-v1` sums classifications without
turning earlier open decisions into known outcomes later. Known and unknown
windows are reported separately; fractions use **only measured trainable
decisions**, and are null for empty/unmeasured phases. The report refers to this
checkpoint's run, not a guessed cumulative lineage. Its recorded source pins
are not proof that the current official client is unchanged.

## Reproducible commands and artifacts

Fresh longer-bound training (no resume or migration flag):

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --inventory-utilities --inventory-discards --refill weighted-discard-consumption-v1 \
  --batch-size 32 --rollout-steps 128 --teacher-updates 64 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --max-turns 128 --max-decisions 512
```

This produced `b53ba01b-0f2c-4137-92d3-0e543e6c50f0`, weights SHA-256
`55d274b507d110098deafa94fb512e4b50057df9d93d888eb459825257107830`.
The recipe retains seed 67, hidden 128, embedding 32, two PPO epochs,
minibatch 16, 50% baseline-opponent environments, mixed opening, and 32 paired
diagnostic games. It collected 262,144 imitation plus 131,072 PPO decisions =
**393,216**, counting both actors, not all as learner-gradient samples.

Its file predates the new teacher-stage field. The matching imitation-only
recipe was rerun to obtain a real endpoint, rather than infer its missing
evaluation or recover unsaved intermediate tensors:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --inventory-utilities --inventory-discards --refill weighted-discard-consumption-v1 \
  --batch-size 32 --rollout-steps 128 --teacher-updates 64 --updates 0 \
  --teacher-selected-defense-weight 8 --max-turns 128 --max-decisions 512
```

This produced `c5e874a9-2175-4abe-8738-5866fe2a49fd`, weights SHA-256
`eb495dccc345621649489df34e68c6a883778b8fb8802d636ee3e4980f60cb5d`.
It records the same teacher metrics/coverage and collects 262,144 decisions.
It is a controlled rerun, not 262,144 novel distinct training examples.

The bounded larger-window continuation preserved the first model and all arena
rules, with fresh optimizers under the existing ordinary-resume contract:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --resume checkpoints/guardian-arena/b53ba01b-0f2c-4137-92d3-0e543e6c50f0 \
  --inventory-utilities --inventory-discards --refill weighted-discard-consumption-v1 \
  --batch-size 32 --rollout-steps 256 --teacher-updates 0 --updates 16 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --max-turns 128 --max-decisions 512
```

This produced `b9698d9a-b624-494d-957d-29f3d03f2a30`, weights SHA-256
`72342a10bc8e288efa2d02bf68999b2fb77689d71a9df9cf2baeaac3ac9dbc0c`,
direct parent SHA equal to the first model. It collected 131,072 additional
decisions. The recurrent minibatch reaches the existing 4,096-decision cap
(256 × 16), without increasing allowed memory bounds. The original short-parent
hash `76d09d40e49b8c5beff62e0b0160193b7fc613e5bf95786ad9ca01f4a547687a`
and all saved parent hashes remain unchanged.

Reports/evaluation:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-training-report \
  --checkpoint checkpoints/guardian-arena/b53ba01b-0f2c-4137-92d3-0e543e6c50f0

UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-evaluate \
  --checkpoint checkpoints/guardian-arena/b53ba01b-0f2c-4137-92d3-0e543e6c50f0 \
  --games 64 --seed 4000070
```

These are ignored local artifacts, not Git-tracked weights or live candidates.
The 128-step PPO parent is the current reference for **further local work**;
the newer 256-step child is not recommended as a better policy.

## Measured training exposure

| Phase / artifact | Collected decisions | Eligible decisions | Winner-covered eligible | Truncation-covered eligible | Open eligible | Completed / truncated episodes |
| --- | --- | --- | --- | --- | --- | --- |
| Imitation (both matching recipes) | 262,144 | 262,144 labels | 78,369 (29.90%) | 10,377 | 173,398 | 1,415 / 157 |
| 128-step PPO | 131,072 | 98,033 | 42,854 (43.71%) | 1,617 | 53,562 | 1,136 / 36 |
| 256-step continuation | 131,072 | 98,016 | 67,679 (69.05%) | 2,428 | 27,909 | 1,298 / 25 |

Completed games during stochastic mixed-opponent collection are not fixed
greedy-opponent evaluation wins. The two PPO rows differ in updates, policy,
trajectory, fresh optimizer state, and window length; their difference alone
does not isolate window length's effect on learning or strength.

## Frozen-trajectory window check

To isolate **availability** from trajectory changes, each frozen policy collected
one 256-step / 32-environment trajectory at seed 6,000,067 under its unchanged
128/512 arena. Ending flags were captured without altering actions, and the
same 8,192 decisions were then partitioned into 32/64/128/256-step windows.
No optimization, weight/config saves, return recomputation, or future-window
backfill occurred. All windows use the same eligible mask within a policy.

| Window | 128-step-trained PPO: winner-covered / 6,117 eligible | Imitation-only: winner-covered / 6,103 eligible |
| --- | --- | --- |
| 32 | 973 (15.91%) | 860 (14.09%) |
| 64 | 1,740 (28.45%) | 1,674 (27.43%) |
| 128 | 3,106 (50.78%) | 2,772 (45.42%) |
| 256 | 4,245 (69.40%) | 4,069 (66.67%) |

The underlying PPO trajectory completed 72 games and imitation-only 68, neither
with a truncation. Larger windows expose more observed winner outcomes on these
fixed trajectories. This does not establish that larger-window PPO is better.

## Playing-strength diagnostics

All policies use the same provisional 128/512 curriculum and greedy-discard
opponent, with paired initial states across learner seats. Seeds are development
diagnostics, not untouched statistical promotion holdouts. First seed is the
training diagnostic; later seeds were used to investigate/tune this milestone.

| Policy | Seed 1,000,070 (32 games) | Seed 4,000,070 (64 games) | Seed 5,000,070 (64 games) |
| --- | --- | --- | --- |
| Imitation-only endpoint | 8 / 19 / 5 | 15 / 41 / 8 | 19 / 42 / 3 |
| 128-step PPO | 7 / 23 / 2 | 19 / 43 / 2 | 25 / 38 / 1 |
| 256-step continuation | 7 / 22 / 3 | 19 / 39 / 6 | 23 / 39 / 2 |
| Greedy reference | 13 / 13 / 6 | 28 / 28 / 8 | 27 / 27 / 10 |

Cells are W / L / truncations, counting every attempted game. Truncations are
all turn-limit; these trained policies had zero defense-toggle/decision-limit
exits, zero deselections, and zero forced passes on these sets. Imitation chose
24/62/2 voluntary passes, 128-step PPO 3/17/0, and the continuation zero throughout.

Across the two extra seed sets, PPO is **44/81/3** versus imitation **34/83/11**;
125 of 128 PPO games reach a winner, but only 44 are learner wins. **Completion
can improve by losing earlier**, so it is not itself a strength gate. The
256-step continuation is **42/78/8**, not an established improvement over its
parent, despite better measured coverage. No local or official strength gate
passed, and neither candidate is promoted. More data collection/training alone
has not erased the weakness of this partial-rules/teacher setup.

## Read-only horizon-transfer preflight

A copy of the short parent was evaluated under explicit counterfactual 128/512
bounds, both raw and with only `global_encoder.0.weight` columns 7 and 42 scaled
by four (target/source horizon ratio). Scaling compensates those normalized
inputs algebraically before the old absorbing boundary. It is not a guarantee
about later extrapolation, values, or stronger play; no transfer implementation,
optimizer, migration record, changed saved configuration, or checkpoint was
created. Raw source weights/files were untouched.

| Preflight policy | 32 diagnostic games | Extra 64 games at 4,000,070 | Extra 64 games at 5,000,070 |
| --- | --- | --- | --- |
| Raw short model, counterfactual bounds | 11 / 19 / 2 | 17 / 34 / 13 | 21 / 36 / 7 |
| Rescaled copy, no updates | 11 / 19 / 2 | 17 / 37 / 10 | 22 / 37 / 5 |

All truncations are turn-limit. One raw short-model diagnostic deselected a
defense card once; the rescaled copy did not. This is a preflight, not a
prefix-equivalence regression suite or evidence that the proposed transfer
should replace fresh longer-bound training. An explicit implementation and
its invariants required a separate user design choice, subsequently approved
and implemented in ADR 0094. The preflight itself did not create a checkpoint.

## Verification and next work

New tests cover window boundaries, disjoint flags, randomized forward-oracle
equivalence, eligible/all accounting, no future backfill, RNG/tensor preservation,
historical unknowns, manifest cross-checks, imitation-only configuration/export,
teacher-stage identities, unchanged optimizer/replay results, phase-evaluation
RNG/weight equivalence, report denominators/unknown phases, CLI behavior, and
checksum/source preservation. Existing contracts and live regressions remain
required.

The approved explicit horizon transfer is the follow-up in ADR 0094, then a
better local tactical curriculum and broader source-reviewed
rules integration. The native game subset remains incomplete; this milestone
does not merge the broad hand curriculum with guardians, implement remaining
cards/event scheduling/trade/Apocalypse, or verify full official fidelity.
