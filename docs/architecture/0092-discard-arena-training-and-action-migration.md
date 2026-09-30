# ADR 0092: Separate discard rollout, local training, and 30→48 action migration

## Decision

Accepted, 2026-09-30. Complete the user-approved isolated provisional
discard/replacement curriculum from ADR 0091. Native 0.46.0 is unchanged: Python
now adapts its validated caller-driven operations into local episodes and neural
training. No old batch, model, live policy, or official service is modified.
This is locally trainable **subset recovery**, not full-game training readiness.

The broadest existing hand curriculum and this guardian arena remain separate;
implementing discard here does not merge all their other mechanics. Guardian
training is still duel-only, with 102 supported inventory models and an optional
one-Mars-effect opening. Multiplayer returns, remaining cards, event scheduling,
trade/prayer acquisition, Apocalypse/Sacrifice, and official differential
validation remain further work. All full-game/official/live/promotion flags stay
false. No live games were started for this milestone.

## Versioned action and acquisition contracts

The opt-in config requires **all three**:

- `inventory_utilities=true`;
- `inventory_discards=true`;
- `refill=weighted-discard-consumption-v1`.

Mismatched old refill/utility flags fail closed; original defaults remain
30 actions, seven features, no discard, and no redraw. The new metadata/checkpoint
schema is 3, observation `actor-relative-guardian-discard-arena-v3`, rollout
curriculum `synthetic-guardian-discard-weighted-refill-provisional-v3`, and policy
`numeric-slot-recurrent-guardian-discard-arena-v3`. Nine hand features, 43 global
features, nine padded public players, actor-relative targets, and per-seat
recurrent memories are unchanged from the utility adapter.

| Action indices | Meaning | Changed from utility arena? |
| --- | --- | --- |
| 0 | Pass | No |
| 1–18 | Select/use own card | No |
| 19–27 | Actor-relative target | No |
| 28 / 29 | Forgive / confirm defense | No |
| 30–47 | Discard own slot 0–17 | Appended |

Discard legality comes exclusively from the native ready-owner mask. The
outer adapter validates every submitted action before grouped mutations. It
does not expose opponent hands, offer discard during target/defense/bounce, or
add discard origin to pending-attack features. A legal discard completes one
provisional turn without MP/HP/CP changes, cast/use counters, or hidden compaction.
Its separate lifetime counter survives explicit episode resets.

`GuardianDiscardRefillPlan` composes the pinned utility distribution, reusing
its 102 models, total weight 277, source denominator 500, and profile digest
`c325f7ed4134a3feb6ff69948fbd6827d98f070b70951297601670902e56d9e3`.
It explicitly overrides the **consumption-only quantity and RNG**: one gift per
consumed **or discarded** slot, channel **6773** (old streams 6771/6772 remain
unchanged). Gifts wait for a completed ready turn, return to the same empty slot
of a living owner, and are dropped on winner/turn/decision boundaries without
sampling. Reusable casts do not produce gifts. No overflow is introduced.

Initial synthetic deals remain identical to utility deals at matching seed,
environment, and episode. Later gifts intentionally differ across curricula
because their streams and action histories differ; cross-ruleset comparisons
are not controlled estimates of discard's isolated causal effect.

Documented exclusions (weapons and models 208/209) remain pinned. Scheduling,
replacement timing, and eligibility of supported miracles without a performed
flag remain explicitly provisional. The outer adapter is locally trainable;
the nested caller-driven component still declares no standalone training loop.
Its historical `pending_neural_action_*` fields describe the layout implemented
by this outer adapter; they do not mutate the native defense action count.

## Explicit checkpoint transfer

`--migrate-discards-from` accepts only a verified nine-feature, 30-action,
weighted-utility checkpoint. It is mutually exclusive with `--resume` and
`--migrate-utilities-from`; no combined 7→9/30→48 migration is implicit.

All existing tensors are copied exactly. A new shared per-card discard scorer
copies the learned card scorer's first layer; its final weight is zero and bias
is -4. With appended actions masked off, logits 0–29, values, and recurrent
states are bit-identical to the parent. Once discard is legal, probabilities
can differ; this is an initialization contract, not a promise of unchanged play.
The new head receives gradients from both imitation and PPO.

Transfer checks a freshly constructed original arena against the verified
parent before widening. Native profiles/source pins, combat, resources, reward,
opening, and turn/decision bounds must match. Only batch size, seed, the explicit
discard flag, and refill identity can differ. Fresh optimizers and private child
files are created; the parent is never overwritten. Provenance records source
model ID, manifest/weights SHA-256, architecture/arena, action widths, and head
initialization. Ordinary resume still requires exact action/observation/rules.
Read-only evaluation verifies current pinned sources against recorded contracts.
Live model loading does not recognize these local checkpoint files.

The trainer dynamically checks 48-action labels and masks while retaining
learner-only PPO, observed-state defense feedback, absorbing zero bootstrap,
and exact recurrent likelihood replay. There is no new shaping reward,
inference-time fallback, or override of sampled learner actions.

The v3 greedy smoke teacher discards only when no ordinary attack/utility card
is playable, preferring lower visible defense/MP-gain value. It is a terminating
legal baseline, not an expert. Evaluation counts ready discards across both
actors and separately for the learner. Collection/teacher/PPO/evaluation persist
discard counters separately from consumed items and utility effects. Missing
historical discard measurements remain null; old curricula had no discard
actions and their new ready-action subgroup defaults to structural zero.

## Commands and trained artifact

The referenced parent must exist locally:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --migrate-discards-from checkpoints/guardian-arena/d496547f-3fb4-4ca4-80ba-20e51bf89b84 \
  --inventory-utilities --inventory-discards --refill weighted-discard-consumption-v1 \
  --batch-size 32 --teacher-updates 16 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --max-turns 32 --max-decisions 128
```

This run created local child `0664c622-6cbe-47f8-a29c-a55dad54313a`, weights SHA-256
`76d09d40e49b8c5beff62e0b0160193b7fc613e5bf95786ad9ca01f4a547687a`.
Parent weights remain
`6c1dabede46ceac8827e7b874e5b678243ed555e71e6ffb022afd050e0f591ac`;
parent manifest SHA-256 is
`e68399682ffd869a493fec9b5af9e13457cace968d1e6f77f745ba329189ae17`.
Checkpoints are ignored local artifacts, not committed or promoted.

With the unchanged default window 64, two PPO epochs, minibatch 16, hidden 128,
embedding 32, and seed 67, collection produced 32,768 teacher plus 65,536 PPO
decisions = **98,304 decisions**, across both actors, exercising **895 discards**.
Teacher labels and baseline-opponent decisions are not learner-policy gradient
samples. Utility gains/costs and all update counts are recorded in its manifest.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-evaluate \
  --checkpoint checkpoints/guardian-arena/0664c622-6cbe-47f8-a29c-a55dad54313a \
  --games 64 --seed 4000070
```

For continuation use `--resume` with that child, retaining the two inventory
flags, new refill, and **32/128** bounds. Changing bounds is not an authorized
implicit resume. A larger-bound fresh run is available without a parent; any
future bound-changing weight transfer needs its own explicit contract.

## Diagnostic results and limits

All rows are paired by learner seat with matching initial states within the new
curriculum. Before = verified parent explicitly transferred in memory without
updates; after = saved child; reference = greedy versus greedy. First seed is the
training manifest's diagnostic, not an independent promotion holdout. Separate
seeds are also development diagnostics and no statistical strength gate passed.

| Seed | Games per policy | Bounds | Policy | W / L / truncation | Discards (both actors) |
| --- | --- | --- | --- | --- | --- |
| 1,000,070 | 32 | 32/128 | Before | 2 / 7 / 23 | 61 |
| 1,000,070 | 32 | 32/128 | After | 4 / 7 / 21 | 25 |
| 1,000,070 | 32 | 32/128 | Reference | 3 / 3 / 26 | 22 |
| 4,000,070 | 64 | 32/128 | Before | 8 / 10 / 46 | 108 |
| 4,000,070 | 64 | 32/128 | After | 7 / 14 / 43 | 54 |
| 4,000,070 | 64 | 32/128 | Reference | 7 / 7 / 50 | 54 |
| 5,000,070 | 64 | 32/128 | Before | 9 / 13 / 42 | 77 |
| 5,000,070 | 64 | 32/128 | After | 6 / 13 / 45 | 29 |
| 5,000,070 | 64 | 32/128 | Reference | 7 / 7 / 50 | 30 |
| 1,000,070 | 32 | 128/512 | Before | 7 / 23 / 2 | 141 |
| 1,000,070 | 32 | 128/512 | After | 11 / 19 / 2 | 73 |
| 1,000,070 | 32 | 128/512 | Reference | 13 / 13 / 6 | 96 |

Every truncation is turn-limit; all policies recorded zero defense-toggle or
decision-limit exits, zero defense deselections, and zero forced/voluntary passes
on these sets. The child played 192 total bounded diagnostic games, including
the longer-horizon row. At the longer bound it used 561 utilities (456 consumed
items, 105 Spring casts), spent 735 MP on utility miracles, and gained 3,505 HP
and 1,905 MP effectively; learner-only discards were 36 of the total 73.

The longer-horizon experiment changes both normalized horizon inputs and is
**not a prefix-equivalent continuation**, a saved configuration mutation, or
an ordinary-resume exception. The high short-horizon truncation rate persists.
Across the two extra short seed sets, after is 13/27/88 versus before 17/23/88:
**no reliable playing-strength improvement is established**.

Zero pass-only witnesses are partly structural: adding legal discard gives
stale hands another action. Actual discard/utility interactions and completed
games are stronger evidence of recovery than the witness count alone. The
child also chose no voluntary passes, but recovery does not establish optimal
discard decisions or full official fidelity. Longer complete-episode training
and broader source-reviewed rules are the next milestones; promotion remains
blocked independently of these diagnostics.

## Verification

Regressions cover separate config/metadata/RNG identities, actor-only projections
with up to nine players, unchanged old indices, pending-phase masks, native and
adapter terminal boundaries, rejected-last-row atomicity, same-slot/padded-slot
replacement, retained versus discarded miracle costs, recovery-only teacher,
reproducible collection, bit-identical masked migration/recurrent states,
architecture mismatch rejection, recurrent replay, discard-head gradients,
learner-only PPO sampling, strict resume/source/bound/provenance checks,
measurement tampering, private child/source preservation, and closed live gates.

All 36 added tests and the full 1,589-test non-browser suite pass, plus both
existing local Chromium tests (1,591 total). Ruff, changed-file formatting,
strict mypy across 77 source modules, offline lock consistency, and whitespace
checks pass. Reloading the saved child through the source-verified evaluation
CLI reproduces 4/7/21 exactly; both recorded parent/child weight hashes match.
