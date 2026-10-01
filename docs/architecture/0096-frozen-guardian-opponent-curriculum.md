# ADR 0096: Opt-in frozen guardian opponent curriculum

## Decision and boundary

User-approved, implemented 2026-10-01. Add a fixed local opponent roster to the
guardian C++ duel curriculum: exactly one versioned greedy baseline plus the
reference neural checkpoint and optional compatible frozen peers. Select one
opponent per episode, keep its recurrent memory private, and exclude its moves
from learner policy gradients. Keep the existing greedy/self-play mix as the
default. This is an opponent curriculum, not additional native game mechanics.

Native 0.46.0, the provisional 102-card discard pool, padded observations,
48 actions, 128-turn / 512-decision experimental arena, source pins, legal
masks, rewards, signed GAE, and live controls are unchanged. No official-service
games, accounts, credentials, live candidates, or promotion baselines are
modified. Full-game readiness, official fidelity, live compatibility, and
promotion remain false.

The older `models create-simulation-league` targets a different simulator and
checkpoint architecture. Its roster is not silently reused for guardian arena
models. The new interface lives under `simulation guardian-*`.

## Source-pinned roster

`guardian-create-league` writes a separate schema-1
`local-frozen-guardian-league-v1` JSON snapshot. It records:

- the exact reference model ID and weights SHA-256;
- every neural member's absolute checkpoint directory, manifest-file SHA-256,
  weights SHA-256, and distinct model ID;
- the complete reference architecture and arena metadata, including source
  hashes, refill distribution, episode limits, resources, and reward settings;
- integer selection weights, scope, dedicated RNG stream, argmax action mode,
  and false readiness/promotion flags.

The canonical sorted snapshot JSON has its own SHA-256. Creation and loading
verify checkpoint tensor integrity and all compatibility checks. Only batch
size and seed may differ from the reference arena. Bounds, architecture,
observation schema, native wrapper, cards, source catalog/client, refill, and
reward contracts remain strict. Duplicate IDs or identical policy-weight
hashes are rejected, including aliases of a reproduced experiment. There must
be exactly one correctly versioned greedy member and 1–8 neural members,
including the exact reference. Weights are integers 1–1,000; CLI neural members
default to 1, with a separate bounded `--greedy-weight` option.

Checkpoint files are read, not copied over or rewritten. New roster files use
mode 0600, and newly created roster directories use 0700. Opponent loading
restores the caller's CPU Torch RNG, so merely loading extra models does not
advance learner sampling randomness. These are ignored local artifacts, not
Git-tracked weights or live-model registry entries.

## Collection and learning contract

`guardian-train --league FILE` requires ordinary `--resume` from that roster's
exact reference, `--teacher-updates 0`, and no architecture or horizon migration.
Those transfers must happen in a separate stage. League mode rejects a
nondefault `baseline_opponent_fraction`; its default 0.5 is explicitly unused
there. The roster weights control episode selection instead.

Selection uses NumPy `SeedSequence([seed, environment, episode_id, 6774])`.
It neither uses Torch sampling nor any existing gift RNG channel. Assignment
changes only when the environment actually starts a new episode, not at PPO
window boundaries. Equal weights mean uniform **episode assignments**, not
equal decision counts: longer games contribute more decisions. Batch prefixes
have the same assignments for equal environment/episode identities.

The learner seat alternates with `(environment + episode_id) % 2`. Every league
episode contains exactly one sampled learner versus one greedy or argmax-frozen
opponent; there are no learner-versus-learner episodes in this mode. Each frozen
policy is a separate eval-mode, gradient-disabled model. Its private memory is
indexed by environment and seat, reset at real episode starts, and updated only
when it acts. Policy inputs are the actor's existing projection, including its
own visible hand, not an opponent's inventory or roster identity. Opponent IDs
are telemetry, not extra policy features. Learner/opponent model aliasing and
stale/inactive controller rows are rejected.

PPO likelihood, clipping, entropy, and auxiliary defense/activity losses use
only learner-controlled rows. Frozen-opponent moves never become imitation
labels. Training-only defense feedback, when enabled, still comes from the
existing legal observed-state greedy teacher on **learner defense states**.
The value objective and signed GAE retain the existing both-actor critic path;
this is policy-gradient isolation, not removal of opponent transitions from
value learning. No inference-time pass ban or teacher override is added.

New checkpoints use algorithm
`provisional-guardian-duel-frozen-league-ppo-v1`, embed the roster and digest,
and save a new child with fresh optimizers. League selection is opt-in on every
run. Continuing a child in league mode requires creating a new roster whose
reference is that child; the old roster cannot silently change parent identity.
Omitting `--league` deliberately returns to the existing default opponent mix.

## Observable training and read-only evaluation

Update logs/manifests record roster-ordered `league_statistics`: episode starts,
learner decisions, opponent decisions, completed games, and truncated games.
Counters are per-window deltas. A window may finish episodes started in an
earlier window, so completions need not be bounded by **that window's** starts.
`baseline_decisions` means greedy-overridden decisions; neural overrides are
separately recorded as `frozen_opponent_decisions`. The manifest cross-checks
all decision/outcome totals, member order, algorithm, parent, and roster hash.
Historical absent roster/frozen measurements remain null, not invented zeros.

`guardian-training-report` now also sums roster counters across this saved run,
alongside unchanged outcome coverage. It checksum-verifies the candidate,
preserves Torch RNG, and runs no games; it does not reverify external peer files
or backfill historical outcomes. Training/evaluation startup rechecks peers.

`guardian-evaluate --opponent-checkpoint DIR` adds paired read-only neural
duels with separate learner/opponent memories, even for a self-match. The
source/architecture/bounds checks remain strict, and the report records the
opponent model ID and weight hash. Without this option, evaluation is unchanged.

`guardian-evaluate-league --checkpoint DIR --league FILE` evaluates against
every pinned member using the same specified seed, number of games, and paired
learner seats. Each matchup accounts for wins, losses, all truncations, ready
actions, and defense deselections. A league-trained candidate must use its
recorded training roster; a nonleague reference/control can use the same roster
for comparison. The report is explicitly a local diagnostic: no aggregate
`passed` gate or automatic promotion is introduced. Default before/after saved
stage evaluations still use the greedy baseline, not a hidden changed opponent.

## Bounded matched experiment

Roster `63b800ae-44d3-4832-9278-4d1b5f05ce66`, SHA-256
`14c51d138ac1989e9bb07a389c8811897d6f26a17420debf121c701ba97d4051`,
has four equal-weight members:

| Member | Identity | Weights SHA-256 |
| --- | --- | --- |
| Greedy | `greedy-discard-smoke-baseline-v3` | None |
| Retained reference P | `3d09213e-6c5e-4ca4-86f0-f8725d6678fd` | `96bfedadc99c05527d7df85288c70de522e4a16c6ec3ec6ea5eb194a0cc4213a` |
| Fresh longer-bound A | `b53ba01b-0f2c-4137-92d3-0e543e6c50f0` | `55d274b507d110098deafa94fb512e4b50057df9d93d888eb459825257107830` |
| Horizon-transfer H | `14230655-0841-4859-83a0-49f05b9e7e66` | `c6940cbb4403d7283863b87fdefcb5cdbc09b2845783a1985c397863ce1eaa23` |

Both children resume exactly P, use training seed 3,067, batch 32, mixed opening,
initial HP 40 / MP 10, hidden 128 / embedding 32, window 128, 48 PPO updates,
two epochs, minibatch 16, teacher updates 0, defense feedback 1 with selected
weight 8, activity weight 0, learning rate 0.0003, gamma 0.99 / lambda 0.95,
and two CPU threads. Arena/refill/source/reward contracts are identical.

The greedy-only control uses legacy `baseline_opponent_fraction=1`, not the
default 0.5. That gives it the same **one learner per episode** structure as the
league child, rather than a higher proportion of eligible self-play rows.
Actual sample counts and trajectories can still differ; no identical-data or
statistically established treatment-effect claim is made.

| Child | Model ID | Weights SHA-256 |
| --- | --- | --- |
| Greedy-only control | `cc5273bf-66e0-487c-833c-4bb66a2b3fdc` | `670001092ae0243eec9a5678151750419905cd9aa76f9fe54e7e70b014cb955b` |
| Frozen league | `bd86df6e-c317-4693-981e-36391085c4d7` | `c5eb36aef0282d455d25ffbd72165e071d46c72b6a621ce87b6695818263a424` |

Each collects 196,608 decisions across both actors. Eligible learner counts are
97,313 control versus 97,568 league. Control records 99,295 greedy decisions;
league records 31,663 greedy plus 67,377 frozen-neural decisions. Saved stage
evaluations on seed 1,003,070, 32 games, start at 16 / 14 / 2 for both and end at
18 / 14 / 0 control versus 15 / 17 / 0 league (W/L/truncated).

The league completes 1,691 collection episodes and truncates 51, versus control
1,290 and 82. Winner-covered learner decisions rise from 33,302 / 97,313 =
34.22% to 40,032 / 97,568 = 41.03%; this measures in-window outcome availability,
not learner wins or improved strength. Roster starts are 456 / 449 / 456 / 413
in greedy / P / A / H order. Their completed/truncated counts are respectively
423/17, 435/6, 445/6, and 388/22; 32 sampled episodes remain open at collection end.

Two specified diagnostic seed sets, 8,000,070 and 9,000,070, use 64 paired games
per member for all three policies. Combined results, **128 games per row**:

| Opponent | Reference P W/L/T | Control W/L/T | League W/L/T |
| --- | --- | --- | --- |
| Greedy | 61 / 61 / 6 | 58 / 64 / 6 | 55 / 68 / 5 |
| Reference P | 64 / 64 / 0 | 66 / 59 / 3 | 62 / 65 / 1 |
| Fresh A | 79 / 48 / 1 | 74 / 53 / 1 | 74 / 53 / 1 |
| Horizon H | 73 / 50 / 5 | 75 / 47 / 6 | 64 / 56 / 8 |
| Total / 512 | **277 / 223 / 12** | **273 / 223 / 16** | **255 / 242 / 15** |

All 1,536 diagnostic games have zero learner forced/voluntary passes, zero
defense deselections, and zero defense-selection/decision-limit exits. All
truncations are native turn limits. Reference self-matches split wins/losses
equally as expected with paired identical starts and independent memory.

The league implementation is exercised, but this recipe shows **no strength
gain**. Do not recommend either new child over P or enable league training by
default. Retain P as the experimental local reference, not an accepted or live
baseline. A roster of these nonexpert policies does not establish expert play.
These development diagnostics, including opponents seen in training, are not
formal independent promotion holdouts or an official-computer/human benchmark.

## Commands

Create a new roster without training or changing checkpoints:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-create-league \
  --reference-checkpoint checkpoints/guardian-arena/3d09213e-6c5e-4ca4-86f0-f8725d6678fd \
  --opponent-checkpoint checkpoints/guardian-arena/b53ba01b-0f2c-4137-92d3-0e543e6c50f0 \
  --opponent-checkpoint checkpoints/guardian-arena/14230655-0841-4859-83a0-49f05b9e7e66
```

Each creation prints a **new** `league_path` and digest; use that returned path
for new experiments. To reproduce the bounded league recipe with the retained
local roster (diagnostic experiment, not a recommended stronger policy):

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --resume checkpoints/guardian-arena/3d09213e-6c5e-4ca4-86f0-f8725d6678fd \
  --league checkpoints/guardian-leagues/63b800ae-44d3-4832-9278-4d1b5f05ce66.json \
  --inventory-utilities --inventory-discards --refill weighted-discard-consumption-v1 \
  --batch-size 32 --max-turns 128 --max-decisions 512 --rollout-steps 128 \
  --teacher-updates 0 --updates 48 --teacher-selected-defense-weight 8 \
  --defense-feedback-weight 1 --ready-activity-weight 0 \
  --ppo-epochs 2 --environment-minibatch-size 16 --evaluation-games 32 \
  --cpu-threads 2 --seed 3067
```

For the matched greedy-only control, remove `--league` and add
`--baseline-opponent-fraction 1`, leaving all other flags unchanged.

Read-only per-opponent evaluation and saved exposure inspection:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-evaluate-league \
  --checkpoint checkpoints/guardian-arena/bd86df6e-c317-4693-981e-36391085c4d7 \
  --league checkpoints/guardian-leagues/63b800ae-44d3-4832-9278-4d1b5f05ce66.json \
  --games 64 --seed 8000070 --cpu-threads 2

UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-training-report \
  --checkpoint checkpoints/guardian-arena/bd86df6e-c317-4693-981e-36391085c4d7
```

These do not join rooms or control the official game. Files contain local
absolute checkpoint paths; moving a roster or its members requires an explicitly
recreated snapshot, not rewriting an existing candidate's pinned roster.

## Verification and next work

Tests cover all three guardian observation schemas, manifest/weight tampering,
strict bounds/reward/source compatibility, duplicate policies, private files,
RNG-neutral loading, episode-fixed and batch-prefix selection, own-hand inputs,
per-seat memory/reset isolation, learner aliases, exact recurrent replay,
gradient exclusion, defense-label scope, counter accounting, historical nulls,
paired neural self-matches, report identity/gates, child-roster recreation,
exposure aggregation, and CLI creation/training/evaluation. An all-greedy
scheduled roster reproduces the legacy one-learner trajectory exactly, including
likelihoods, rewards, signed advantages, and returns; the digest intentionally
adds roster identity. Frozen tensors remain bit-identical after learner PPO.

Verification: 1,781 non-browser tests and two local browser-control tests pass,
including 52 dedicated frozen-league tests. Ruff, changed-file formatting,
mypy over 80 source modules, offline lock consistency, and whitespace checks
pass. The roster's three neural source weight hashes were rechecked after
training/evaluation. No native rebuild or dependency update was needed.

The next strength work should diagnose tactical errors and policy/critic
credit rather than treating extra completion or roster diversity as proof of
improvement. Broader source-reviewed integrated C++ mechanics, multiplayer
learning, and official differential validation remain necessary for full-game
training readiness. No automatic live promotion is authorized by this milestone.
