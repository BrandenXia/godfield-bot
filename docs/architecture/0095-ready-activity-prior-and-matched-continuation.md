# ADR 0095: Ready-state activity prior and matched continuation

## Decision and boundary

Experimental training-only implementation, 2026-09-30. Investigate ready-phase
voluntary passing after the explicit horizon-transfer experiment (ADR 0094).
Add an opt-in probability-group prior, and compare against ordinary continuation
from exactly the same parent and training seed. Do not make the prior a default
or an inference-time action ban.

Native 0.46.0, the provisional 102-card discard curriculum, 128-turn /
512-decision episode bounds, card/observation schemas, rewards, and live
controls remain unchanged. No accounts, credentials, official-service games,
live policies, or promotion baselines are modified. Full-game readiness,
official fidelity, live compatibility, and promotion remain false.

## Diagnostic, not a causal or strategic claim

The previous child `14230655-0841-4859-83a0-49f05b9e7e66` scored 40 wins /
74 losses / 14 truncations over diagnostic seeds 4,000,070 and 5,000,070,
64 games each, with 253 learner voluntary passes. The existing auxiliary loss
supervises learner defense, not ready states. That absence alone does not prove
passing is the cause of losses or that passing can never be strategically useful.

A read-only copied-model counterfactual lowered only the pass-control bias by
20; no checkpoint or optimizer was saved and the source remained unchanged.
It scored 22 / 34 / 8 and 23 / 37 / 4, respectively: 45 / 71 / 12 in total,
with zero voluntary passes. This is a modest development signal, not a
statistically established gain, an expert policy, or permission to forbid pass
in live games. The trained experiment below does not retain that bias override.

## Loss contract

`--ready-activity-weight` is a separate finite scalar in [0, 4], default 0.
Its fixed scope is `learner-ready-pass-plus-alternative-v1`. Eligible sampled
states must satisfy all of:

- the PPO actor is learner-controlled, not a greedy-opponent override;
- the stored public phase projection says ready;
- pass (action 0) is legal;
- at least one nonpass action is legal in the same observed mask.

The helper computes `-log(P(any legal nonpass action))`, averaged over eligible
states, and adds the weighted result to the existing PPO objective. It does
not label a particular card, discard, or target as correct. It is a behavioral
prior, not evidence that every nonpass alternative is tactically good. Shared
network updates can still change card rankings and other outputs.

Forced-pass states, nonready phases, and baseline-controlled actors are
excluded. Sampling, actions, old likelihoods, rewards, signed GAE, legal masks,
refill RNG, and rollout digest are unchanged before optimization. No extra
teacher labels or hidden inventory are collected, and no prior is applied at
inference. The original PPO code path is retained when the weight is zero.

Masked logits are replaced with negative infinity inside the group calculation
so illegal scores cannot contribute, even if valid logits equal the old minimum
sentinel. A no-sample minibatch returns a connected zero without sentinel-sum
overflow. Negative roundoff in a mathematically nonnegative loss is clamped to
zero. Legal non-finite logits and incompatible boolean masks/shapes are rejected.

Enabled checkpoints use algorithm ID
`provisional-guardian-duel-recurrent-ppo-ready-activity-v1`, with defense
feedback independently recorded if enabled. Imitation-only export rejects a
positive PPO-only activity weight. Normal resume remains source/rule/bound
strict and saves a new child with fresh optimizers; no architecture migration
is needed for this loss.

Update logs/manifests separately record `ready_activity_loss`,
`ready_pass_probability`, and `ready_activity_samples`. Loss/probability are
eligible-sample-weighted averages across optimizer minibatches/epochs, before
each step, not evaluation win rate. Sample counts include repeated PPO epochs.
Manifest validation checks presence, finite/range bounds, algorithm identity,
sample budget, and zero values for an enabled but empty group. Disabled new
updates record zero; historical absent fields stay null rather than being
invented measurements.

## Matched training experiment

Both runs resume ADR 0094's child, weights SHA-256
`c6940cbb4403d7283863b87fdefcb5cdbc09b2845783a1985c397863ce1eaa23`.
They retain the same arena, hidden 128 / embedding 32, baseline fraction 0.5,
rollout window 128, teacher updates 0, PPO updates 32, epochs 2, minibatch 16,
defense feedback 1 with selected-defense weight 8, learning rate 0.0003,
gamma 0.99 / lambda 0.95, and CPU threads 2. Training seed is 1,067 in both.
Only `ready_activity_weight` differs: 0 versus 0.25. Subsequent trajectories
can diverge after the first optimizer step; they are not identical replay data.

Each run collects 131,072 decisions across both actors. Both start at the same
evaluation score 13 / 16 / 3 on seed 1,001,070, 32 games.

| Artifact | Model ID | Weights SHA-256 |
| --- | --- | --- |
| Ordinary control | `3d09213e-6c5e-4ca4-86f0-f8725d6678fd` | `96bfedadc99c05527d7df85288c70de522e4a16c6ec3ec6ea5eb194a0cc4213a` |
| Activity weight 0.25 | `3d364e60-1b1f-46e1-86f9-82c09778f4ad` | `95ba7a047f7f21f8a8c7f7f6981cdc2645dd582fea29d488e8cbb21b2ee2f00c` |

The final illegal-logit masking version was separately rerun under the identical
recipe as `86c19791-ec61-462a-abe3-617938956aa8`, reproducing the activity
weight digest exactly. This is repeated controlled data, not an independent
training seed or additional unique evidence. All parent weights remain intact.

| Diagnostic seed / games | Control W/L/truncated | Activity 0.25 W/L/truncated |
| --- | --- | --- |
| 1,001,070 / 32 (saved stage) | 16 / 14 / 2 | 14 / 17 / 1 |
| 4,000,070 / 64 | 28 / 33 / 3 | 23 / 36 / 5 |
| 5,000,070 / 64 | 35 / 27 / 2 | 31 / 31 / 2 |
| 6,000,070 / 64 | 31 / 27 / 6 | 32 / 27 / 5 |
| Extra sets total / 192 | **94 / 87 / 11** | **86 / 94 / 12** |

All four sets for both children have zero voluntary and forced passes, zero
defense deselections, and zero defense/decision-limit exits. Truncations are
all native turn limits. Paired learner seats are evaluated against the same
greedy discard smoke baseline. These are development diagnostics, not a formal
promotion gate or official-bot benchmark.

The extra winner-covered PPO fractions are 37,266 / 98,010 = 38.02% for control
and 33,958 / 98,002 = 34.65% for activity. Coverage is current-window outcome
availability, not learner wins, advantage quality, or a strength multiplier.
Both children have no teacher-stage evaluation, because no teacher windows were
collected; training-only defense feedback is not a teacher collection phase.

The control performs better on this aggregate comparison. **Do not recommend
the ready-activity prior over ordinary continuation** from these results. Keep
it disabled; its opt-in implementation permits future controlled experiments
without changing existing policies. The improved control is still only an
experimental local training parent, not an accepted/live baseline.

To reproduce the matched control, with 0.25 substituted only for a deliberate
activity-prior experiment:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --resume checkpoints/guardian-arena/14230655-0841-4859-83a0-49f05b9e7e66 \
  --inventory-utilities --inventory-discards \
  --refill weighted-discard-consumption-v1 \
  --batch-size 32 --max-turns 128 --max-decisions 512 \
  --rollout-steps 128 --teacher-updates 0 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --ready-activity-weight 0 --ppo-epochs 2 --environment-minibatch-size 16 \
  --evaluation-games 32 --cpu-threads 2 --seed 1067
```

## Further ordinary continuation: retain the parent

A bounded follow-up resumed the control with training seed 2,067, teacher
updates 0, PPO updates 64, and activity weight 0. All other parameters and
arena bounds remained unchanged. It collects 262,144 additional decisions
across both actors and saves `b9ce530e-3c6a-4841-9b16-bdf682bdd9b7`, weights
SHA-256 `c9b8fc46f8b82bb8caf75335785cd2a7e7719542d537d32eae5126cf125bad65`.
Its immediate parent hash is the control's `96bfedad…4213a`, not the activity
candidate or its repeated reproduction.

The saved 32-game stage evaluation, seed 1,002,070, rises from 17 / 11 / 4
to 20 / 10 / 2. An apparent gain there is not sufficient to recommend it:

| Diagnostic seed / games | Control parent W/L/truncated | 64-update child W/L/truncated |
| --- | --- | --- |
| 4,000,070 / 64 | 28 / 33 / 3 | 30 / 30 / 4 |
| 5,000,070 / 64 | 35 / 27 / 2 | 35 / 27 / 2 |
| 6,000,070 / 64 | 31 / 27 / 6 | 28 / 33 / 3 |
| 7,000,070 / 64 | 28 / 35 / 1 | 26 / 33 / 5 |
| Total / 256 | **122 / 122 / 12** | **119 / 123 / 14** |

The fourth seed was specified for both policies before running this comparison.
All sets have zero learner voluntary/forced passes, zero defense deselections,
and zero defense/decision-limit exits. All truncations remain native turn
limits. These comparisons are not independent formal promotion holdouts or
evidence that either policy is stronger than humans/the official computer.

This segment's eligible decisions number 195,957: 81,334 winner-covered
(41.51%), 3,197 truncation-covered, and 111,426 open. All-actor counts are
105,397 / 4,526 / 152,221; there are 2,190 completed episodes and 75
truncations. It records 3,505 discarded cards and 112,537 replacement gifts.
The higher outcome coverage and saved-stage win count do not translate into
better aggregate diagnostic results. **Retain the control parent** as the
experimental local training reference; neither continuation is an accepted
or live-promoted baseline.

Evaluate that reference in the local C++ arena, without changing it:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-evaluate \
  --checkpoint checkpoints/guardian-arena/3d09213e-6c5e-4ca4-86f0-f8725d6678fd \
  --games 64 --seed 8000070 --cpu-threads 2
```

That example reserves a new diagnostic seed for a user-initiated run; it was
not used in the reported comparisons above. It is not an official-service
game or a live-neural command.

## Verification and remaining work

Tests cover analytic group probabilities and gradients, action widths 30/48,
probability-weighted nonpass gradients, common-logit shift invariance, illegal
NaNs/minimum sentinels, connected empty-group zeros, extreme pass preference,
invalid masks/dtypes/shapes, bounded configuration, all three arena-schema
trajectory equivalence, reduced activity loss on a frozen on-policy window,
exclusion of baseline/forced-pass/nonready states, disabled-path neutrality,
independent defense/activity metrics, historical unknowns, manifest tampering,
checkpoint isolation, and CLI opt-in behavior.

Verification: 1,729 non-browser tests plus two local browser-control tests
passed, including 41 new activity tests. Ruff, changed-file formatting, mypy
over 79 source modules, offline lock consistency, and whitespace checks pass.
The source parent hashes and reproduced treatment weights were rechecked.
No native rebuild or dependency update was needed.

The native game subset remains incomplete. Further local strength work and
broader integrated source-reviewed rules are still needed before full-game
training readiness, official fidelity checks, or live promotion can be claimed.
These results favor improving tactical/opponent diversity over adding more
undirected updates or enabling the activity prior. Stronger local play still
does not replace the missing full-game mechanics and official differential
evidence required by the overall project.
