# ADR 0088: Training-only feedback on encountered defense states

## Status and diagnosis

Accepted, 2026-09-29, within the continued local-training milestone. This changes
the isolated guardian trainer, not native combat, live actions, or official
promotion. Existing training behavior remains the default.

Refill candidate `c6ee0b25-6494-47c6-b669-bdb43300061a` repeatedly selected and
deselected the same card. One trace alternated selected DEF16/DEF4 against ATK30,
although all compatible armor had been selected and confirmation was legal.
Another repeatedly toggled a selected reusable defense with only that slot
legal. The greedy teacher would confirm; neural confirmation probabilities were
roughly 0.09–0.20. The native 64-toggle boundary stopped the episodes.

Warm-start imitation follows teacher trajectories, not the learner's mistaken
state/memory histories. The new auxiliary loss labels the states actually
visited during sampled PPO collection, including these recovery states. It
does not change the terminal rewards, bootstrap contract, or legal action mask.

## Learning contract

`GuardianTrainingConfig.defense_feedback_weight` defaults to zero. Positive
values up to four enable a selected-defense-weighted cross-entropy term in
addition to the existing clipped PPO/value/entropy loss. The existing
`teacher_selected_defense_weight` also controls this weighting.

`defense_feedback_scope` is recorded explicitly:

- `all-defense` (default): label learner-controlled phase-1 decisions.
- `finish-decisions`: label only states where the teacher would confirm or
  forgive, leaving intermediate card-selection decisions without feedback.

Labels are generated from the same seven policy projections used by the neural
policy, never hidden inventories. The collector does not override sampled
learner actions with these labels. Baseline-opponent actions remain excluded
from policy, entropy, and feedback losses; existing critic training for both
seats remains unchanged. Labels must have matching shapes, int64 action IDs,
and legal actions before any optimizer update.

Recurrent replay retains original memories, starts, likelihoods, actions, rewards,
and bootstrap values. With feedback disabled, no labels or extra loss are used.
Tests compare enabled/disabled collection under the same seed and confirm exact
equality of sampled trajectories. Feedback labels contribute to enabled rollout
digests. The extra stored tensor is bounded by the existing rollout storage cap.

There is no teacher fallback, toggle shield, altered legality, or auxiliary loss
at inference. Evaluation still chooses raw neural argmax actions.

## Metadata and measurements

Enabled checkpoints use algorithm identity
`provisional-guardian-duel-recurrent-imitation-ppo-defense-feedback-v1`.
Disabled checkpoints retain the original algorithm. Algorithm/configuration
mismatches fail closed. Resume can change training hyperparameters while still
checking the original observation, native, source, refill, and reward contracts;
it writes a new child with fresh optimizers and preserves the parent.

PPO updates report weighted defense-teacher loss, accuracy, and sample count.
Loss is averaged over recurrent minibatch feedback losses weighted by sample
count; accuracy counts pre-optimization predictions. Counts include repeated
passes across PPO epochs, not distinct game decisions, and cannot exceed either
learner decisions or phase-1 decisions times epoch count. Empty eligible sets
record measured zeros. Historical missing measurements remain null. Disabled
feedback cannot claim nonzero measurements.

Evaluations also count `defense_deselections` across both actors. Deselecting can
be a legitimate correction, so this is diagnostic, not a forbidden action or
promotion criterion. Native defense-selection-limit exits remain separately
counted. Historical evaluations without this measurement remain unknown.

## Bounded experiments

All three experiments resumed the same refill parent with batch 32, window 64,
zero additional warm-start updates, 32 PPO updates, selected-defense weight 8,
seed 67, and 32-turn/128-decision bounds. Each trained on 65,536 additional PPO
decisions. The 32-game diagnostic seed 1,000,070 was used for development:

| Feedback | Scope | Wins | Losses | Truncations | Toggle-limit exits |
| --- | --- | ---: | ---: | ---: | ---: |
| Parent, disabled | — | 13 | 8 | 11 | 3 |
| 1 | all-defense | 15 | 10 | 7 | 0 |
| 1 | finish-decisions | 8 | 18 | 6 | 0 |
| 0.25 | all-defense | 11 | 16 | 5 | 0 |

The selected local development candidate is the weight-1/all-defense child
`4d611acb-410e-40dd-8520-0257b5679d79`, weights SHA-256
`3bc2c81c3eeca7c45f386f0bb4d37def6caa96fdc2d4e8c02b0260da81328d7c`.
The narrower and lighter experiments remain private local artifacts, not
promoted candidates. Their IDs are respectively
`5195f62a-6986-4c31-9844-9c134f9a9303` and
`442a36bd-6344-4865-a035-9ef2a357ac15`.

The selected policy was evaluated raw against the same greedy opponent with
paired initial states/learner seats on four additional 64-game sets. Parent
and baseline calibration used identical seeds and bounds:

| Seed | Candidate W/L/truncation | Parent W/L/truncation | Candidate/parent toggle exits | Baseline W/L/truncation |
| --- | --- | --- | --- | --- |
| 4,000,070 | 20/26/18 | 26/21/17 | 0/2 | 22/22/20 |
| 5,000,070 | 17/16/31 | 18/13/33 | 0/0 | 16/16/32 |
| 6,000,070 | 26/16/22 | 17/18/29 | 0/3 | 21/21/22 |
| 7,000,070 | 21/19/24 | 23/16/25 | 0/6 | 20/20/24 |

Seeds 4,000,070/5,000,070 were checked before the two auxiliary ablations.
Seeds 6,000,070/7,000,070 were checked after selecting the original weight-1
candidate without changing its weights. These are development diagnostics,
not an official or statistically powered promotion gate.

Across the diagnostic and four additional sets (288 games), the candidate had
zero toggle-limit exits versus 14 for the parent, and ten deselections versus
551. Across the four additional sets alone, both candidates won 84/256 games;
the feedback candidate had 77 losses/95 truncations versus the parent's
68 losses/104 truncations. Stability improved, but wins are mixed by seed and
reliable superiority is not established. Remaining candidate truncations in
these four sets were 60 turn limits and 35 decision limits, not toggle limits.

Reproduce the selected continuation with the existing local parent:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --resume checkpoints/guardian-arena/c6ee0b25-6494-47c6-b669-bdb43300061a \
  --batch-size 32 --teacher-updates 0 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --defense-feedback-scope all-defense \
  --max-turns 32 --max-decisions 128 --refill weighted-consumption-v1
```

This writes another child, not the same UUID. The recorded checkpoint can be
evaluated read-only with `guardian-evaluate`; no feedback flags are required
for evaluation.

## Readiness and next work

This satisfies a bounded local defense-stability diagnostic, not proof that
loops are impossible. The 94-model provisional arena still lacks most official
mechanics; turn/decision limits and weak tactics remain. Full-game readiness,
official verification, live compatibility, and promotion remain false.
The next C++ curriculum work is inventory-backed HP/MP utility and additional
guardian/effect coverage, with distinct supported-source/ruleset metadata.

The 21 added regressions cover trajectory preservation, visible-only/legal
labels, actual feedback learning, baseline-gradient exclusion, invalid-label
atomicity, empty/scope-specific sample sets, visible loop diagnostics, CLI
controls, checkpoint provenance/tampering, and historical defaults. All 1,279
non-browser tests passed, along with lint, changed-file formatting, strict
typing of 73 modules, and lock/whitespace checks.
