# ADR 0090: Local utility arena training and explicit checkpoint migration

## Decision and scope

Accepted, 2026-09-29. The user selected the recommended explicit transfer from
the existing local seven-feature candidate rather than discarding its learned
weights. This connects native 0.45.0's isolated HP/MP inventory component to
the recurrent imitation/PPO trainer. It does not change native combat, the old
arena, the 94-card refill profile, live action schemas, or online controls.

The new checkpoint is locally training-eligible for this **incomplete,
provisional subset**. Full-game training readiness, official verification,
live checkpoint compatibility, and promotion remain false. The native component
still requires caller-supplied cards/actions and retains its component-level
local-training-ineligible marker; the connected outer curriculum supplies the
missing rollout/training contract.

## Separate observation and curriculum identities

Opt-in `GuardianRolloutConfig.inventory_utilities=True` selects the utility
native component. Rollouts and checkpoint manifests use schema 2, observation
`actor-relative-guardian-utility-arena-v2`, and nine numeric own-hand features:
`role/7, ATK/100, DEF/100, element/6, MP_cost/100, reusable, selected,
HP_gain/100, MP_gain/100`. The selected-card flag stays at index 6 for attack
targeting, defense confirmation, and training-only defense feedback.

The new checkpoint source is `local-guardian-utility-duel-neural-checkpoint-v2`
and policy identity is `numeric-slot-recurrent-guardian-utility-arena-v2`.
Global features (43), player features (nine padded players × eight), 18 hand
slots, the 30-action layout, model vocabulary, and independent player recurrent
memories remain unchanged. The trainer remains duel-only; the smoke rollout
supports two through nine players. Hidden inventories are never policy inputs.

Attack slots still require a separate target decision. Legal utility slots
dispatch immediately to native self-use, consume the sundry or retain Spring,
charge its exact seven MP, apply capped gains, and finish one ready turn. No
utility can be used during defense/bounce, by a dead owner, at a full resource,
or with insufficient pre-cast MP. All outer actions validate before any native
group or refill RNG is changed.

The synthetic initial nine-card deal guarantees one weapon, one attack miracle,
one armor, one defense miracle, one HP sundry, one MP sundry, and Spring, with
two further uniform supported draws, then shuffles. It is a coverage curriculum,
not the official initial distribution. Old initial deals/RNG order are intact.
The guardian opening remains the earlier optional single simple Mars effect.
Utility targeting/timing and guardian scheduling are explicitly provisional;
no curse/illness effect order is inferred from printed card amounts.

## Explicit 7→9 transfer

`guardian-train --migrate-utilities-from <old_checkpoint>` requires the utility
flag and cannot be combined with `--resume`. It verifies the source manifest,
weight checksum, finite parameters, pinned sources, original combat cards,
episode bounds, rewards, opening, and architecture before training or saving.
Batch size and seed may differ. No-redraw transfers remain no-redraw; the old
94-card weighted curriculum can explicitly transfer to the new 102-card pool.
Other observation, source, combat, reward, or bounds changes are rejected.

Migration `guardian-card-encoder-7-to-9-role-rescale-v1` copies every tensor
exactly except the first card-encoder weight. That matrix gains two zero-filled
HP/MP columns. Its role-input column is multiplied by **7/5**, compensating
for old `role/5` becoming `role/7`. Thus ordinary old-card projections preserve
logits, values, and recurrent outputs within floating-point tolerance before
training. Tests replay 48 steps with separate seat memories at `rtol=1e-5`,
`atol=2e-6`. This is not an equivalence claim for new utility cards or the new
deal/refill distribution.

The child records the original model ID, manifest and weights SHA-256, full
source arena and architecture, role compensation, and zero-column rule.
Original files are never overwritten. Optimizers are fresh. Ordinary resume
still requires exact curriculum/feature/source contracts, cannot silently
widen an old checkpoint or change refill/bounds, and writes a new child. A
wide-to-wide continuation records its direct parent checksum, not a second
7→9 migration. Historical architecture fields default to the original width
and identity when reading old checkpoints.

## Separate provisional refill

`--refill weighted-utility-consumption-v1` requires `--inventory-utilities`.
Without refill, the utility curriculum has no redraw. The old weighted flag
cannot be combined with utilities, and the new flag cannot select the old arena.

`GuardianUtilityRefillPlan` has ruleset
`utility-consumption-deferred-weighted-gifts-provisional-v1`: exactly 102 models,
total relative weight 277, source denominator 500, profile SHA-256
`c325f7ed4134a3feb6ff69948fbd6827d98f070b70951297601670902e56d9e3`.
Both pinned API/Bible gift weights must agree. This conditions on the supported
subset, not the complete official gift pool. The old 94-model/227-weight
profile and its digest remain unchanged.

Consumed weapons, confirmed armor, and utility sundries each queue one gift
into their same empty slot. Reusable miracles do not queue gifts. Gifts wait
until the turn finishes ready, including defense/bounce resolution, and apply
only to living owners. Finished/truncated rows discard pending gifts without
sampling. There is no compaction or overflow. Utility refill uses independent
seed/environment/episode RNG channel 6772; old refill retains 6771. Placement,
quantity, and timing remain provisional despite source-pinned relative weights.

## Learning and observable measurements

The existing zero-sum HP/MP potential shaping, terminal winner rewards, gamma,
absorbing truncations/zero bootstrap, recurrent PPO likelihood replay, and
defense feedback semantics are unchanged. New numeric columns receive genuine
gradients. No utility-specific bonus is added to the reward.

The visible-only `greedy-utility-smoke-baseline-v2` teacher scores capped
healing more highly at low HP and favors MP funding for the actor's visible
miracle costs. It uses the same legal masks. It is a smoke-test teacher, not
an expert policy. Sampled PPO actions are not overridden. Evaluation remains
raw neural argmax without a toggle shield or heuristic fallback.

Rollout, teacher, PPO-update, and evaluation reports record utility uses,
consumed sundries, Spring casts, utility MP spent, and actual capped HP/MP
gains. Measurements count **both actors**, including baseline decisions,
not learner-only usage, nominal amounts, or added policy inputs. Each collected
window reports lifetime-counter deltas across resets. Old curricula record
null (not unmeasured zeros); new curricula require complete measured counts,
including zero where appropriate. Identity/profile/measurement mismatches fail
closed. Checkpoints stay in the separate private `checkpoints/guardian-arena`
tree and cannot load through the live registry.

## Bounded experiment

The source is `4d611acb-410e-40dd-8520-0257b5679d79`, weights SHA-256
`3bc2c81c3eeca7c45f386f0bb4d37def6caa96fdc2d4e8c02b0260da81328d7c`.
Its old 32-game diagnostic at seed 1,000,070 still reproduces 15 wins, 10 losses,
seven truncations (four turn/three decision), zero toggle exits, and one
deselection. Those numbers are not comparable to the changed utility deal/pool.

Utility child `d496547f-3fb4-4ca4-80ba-20e51bf89b84`, weights SHA-256
`6c1dabede46ceac8827e7b874e5b678243ed555e71e6ffb022afd050e0f591ac`,
used batch 32, window 64, 16 teacher updates, 32 PPO updates, two PPO epochs,
minibatch 16, selected-defense weight 8, all-defense feedback weight 1, seed 67,
hidden size 128/embedding 32, and 32-turn/128-decision limits. It collected
32,768 teacher plus 65,536 PPO decisions: 98,304 total across both actors,
not distinct games or learner-only decisions.

All comparisons below use the **same new utility curriculum**, greedy utility
opponent, and paired initial states/learner seats. Transfer means the old model
migrated in memory, before further training. Seeds 4,000,070 and 5,000,070 were
evaluated after training with unchanged child weights.

| Seed / games | Trained W/L/truncation | Transfer W/L/truncation | Greedy reference W/L/truncation | Trained/transfer toggle exits |
| --- | --- | --- | --- | --- |
| 1,000,070 / 32 | 8/6/18 | 9/4/19 | 6/6/20 | 0/0 |
| 4,000,070 / 64 | 11/13/40 | 12/19/33 | 9/9/46 | 0/0 |
| 5,000,070 / 64 | 12/11/41 | 13/14/37 | 10/10/44 | 0/1 |

The child made 325 utility uses in the 32-game diagnostic: 255 consumed items,
70 Spring casts, 490 MP spent, 2,036 effective HP gained, and 1,200 effective MP
gained across both actors. Additional 128-game evaluation totaled 1,243 utility
uses and one deselection, with all 81 truncations caused by the turn limit.
The transferred source had 68 deselections and one toggle exit across those
128 games. These bounded diagnostics exercise utility learning and suggest
better toggle stability, but **do not establish improved playing strength**.
Healing-heavy games frequently outlive the configured 32-turn horizon, even
for the greedy-versus-greedy reference. No promotion gate is passed.

Reproduce the transfer/training experiment (writes another UUID):

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --migrate-utilities-from checkpoints/guardian-arena/4d611acb-410e-40dd-8520-0257b5679d79 \
  --inventory-utilities --refill weighted-utility-consumption-v1 \
  --batch-size 32 --rollout-steps 64 --teacher-updates 16 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --defense-feedback-scope all-defense --max-turns 32 --max-decisions 128
```

Continue the new child without repeating the transfer:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --resume checkpoints/guardian-arena/d496547f-3fb4-4ca4-80ba-20e51bf89b84 \
  --inventory-utilities --refill weighted-utility-consumption-v1 \
  --batch-size 32 --teacher-updates 0 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --max-turns 32 --max-decisions 128
```

Evaluate a recorded child without training or online play:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-evaluate \
  --checkpoint checkpoints/guardian-arena/d496547f-3fb4-4ca4-80ba-20e51bf89b84 \
  --games 64 --seed 4000070
```

The next local investigation is long healed episodes and attack/defense tactics,
not declaring this subset a full-game simulator or silently changing saved
episode/reward contracts. Remaining official mechanics and differential
validation still gate full-game readiness and live promotion.

## Verification

Regression coverage includes all-tensor preservation, role-rescaled recurrent
output equivalence, exact PPO likelihood/value replay, utility-column gradients,
private child artifacts, same-width continuation, old behavior, explicit opt-in,
source/bounds/profile/identity tampering, utility dispatch and reward caps,
consumption/refill timing and terminal RNG, failed-row atomicity, actor-only
observations, multiplayer smoke rollouts, deterministic resets, and CLI controls.

All 54 new regressions and the complete 1,437-test non-browser suite pass.
The two local browser regressions also pass when Chromium is allowed to launch
outside the macOS sandbox (its Mach-port permission check blocks sandboxed
launch). Ruff, changed-file formatting, strict mypy across 75 source modules,
lock consistency, whitespace checks, and checksummed child evaluation pass.

Follow-up: [ADR 0091](0091-pass-only-diagnostics-and-discard-component.md)
separates policy-independent pass-only witnesses from other truncations and
adds the approved isolated native discard recovery component. Its new action
adapter/migration is not yet connected to this 30-action utility trainer.
