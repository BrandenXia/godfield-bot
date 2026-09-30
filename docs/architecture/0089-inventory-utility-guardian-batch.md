# ADR 0089: Separately versioned inventory HP/MP guardian turns

## Status and boundary

Accepted, 2026-09-29. Native package 0.45.0 adds `GuardianUtilityTurnBatch`,
kernel/observation/actor-hand schema 1, ruleset
`round-robin-inventory-utility-guardian-turns-provisional-v1`.
`GuardianTurnBatch` retains kernel/observation schema 2 and its existing hand
schema, supported cards, and masks. Neither guardian neural checkpoints nor
the old 94-card refill distribution are widened or migrated.

This is the native component milestone. It is **not yet connected to the
recurrent training adapter**. The metadata marks local training eligibility,
full-game readiness, official fidelity, and promotion false.

## Source contract

The pinned API catalog from 2026-09-21 and Bible/client snapshot from 2026-09-20
agree on the following unconditional effects:

| Model | Card | Resource | Gain | MP cost | Ownership after use |
| ---: | --- | --- | ---: | ---: | --- |
| 191 | Smile Dew | HP | 5 | 0 | consumed |
| 192 | Heart Dew | HP | 10 | 0 | consumed |
| 193 | Romance Water | HP | 15 | 0 | consumed |
| 194 | Galaxy Geyser | HP | 20 | 0 | consumed |
| 195 | Smile Flower | MP | 5 | 0 | consumed |
| 196 | Heart Flower | MP | 10 | 0 | consumed |
| 197 | Romance Fragrance | MP | 15 | 0 | consumed |
| 235 | Spring | HP | 10 | 7 | retained miracle |

Profiles are `(model, resource_code, gain, reusable, mp_cost)`, with HP=0/MP=1.
Their canonical SHA-256 is
`aea15c13fcb187047bbe3548d37de7994e98b562259ecf4db869d74b3c70b29d`.
`GuardianUtilityPlan` is immutable and checks the exact profile and both source
pins. The factory also checks category, ability, amount, cost, and absence of
attack/defense/element fields. Native constructors reject duplicates, collisions
with attack/defense models, invalid amounts, and unsupported resource/cost kinds.

## Provisional execution

One immediate **self-only** utility completes one living player's ready-phase
turn. This narrow target/timing rule is explicitly provisional: printed amounts
and costs do not prove official targeting, curse interactions, or ordering.
The extension retains all existing provisional guardian scheduling and curse
limitations; it does not introduce official end-turn illness or curse behavior.

Using a utility requires the current turn owner, an occupied supported slot,
resource below 100, and sufficient MP **before** use. It cannot revive an
eliminated player, be used during defense/bounce, or act after termination.
HP/MP gains cap at 100. Sundries leave an empty slot; Spring charges exactly
7 MP and retains its instance. There is no defense response, automatic redraw,
compaction, or inferred acquisition timing.

All rows validate before mutation, including unique environment IDs. A bad last
row cannot heal an earlier row, spend MP, consume a card, increment counters, or
advance a turn. The implementation composes the old scheduler/combat state
without copying it or exposing arbitrary resource writes to policy callers.

Existing attack/defense legality remains intact: utilities are neither attacks
nor armor. `utility_action_masks` is `[B,H]`; `ready_action_masks` is `[B,H+1]`,
the union of affordable attack slots, legal utility slots, and pass at `H`.
The caller still dispatches attacks and utilities through their distinct APIs.
Ordinary attack/defense/bounce masks are also available unchanged.

## Observations and counters

The new copied, read-only actor hand is `[B,H,11]`:
instance, model, selected, role, ATK, DEF, element, MP cost, reusable, HP gain,
MP gain. It includes only the acting player's inventory; finished rows are zero.
Numeric hand roles retain the old 0–5 codes and add 6=HP utility, 7=MP utility.
Retained Spring is distinguished by its cost and reusable flag. The full-hand
diagnostic projection is `[B,P,H,8]`; it must not be passed to a policy.
The old native actor hand remains `[B,H,9]` and old full features `[B,P,H,6]`.

Turn snapshots keep the existing eleven fields, adding origin code 3 for a
completed immediate utility. Combat diagnostics have idle phase, the utility
model and self owner/target, and resource effect code 5/6 with nominal gain.
`utility_use_count`, `hp_gained`, and `mp_gained` are lifetime counters; gains
measure actual capped increments. Existing consumed-card, miracle-cast, and
MP-spent counters include the new card uses. Guardian resolved-effect counts
do not. Environment resets clear state but preserve lifetime counters.

## Inspection and verification

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-batch-plan --turns --inventory-utilities \
  --batch-size 512 --player-count 2
```

The flag requires `--turns` and only constructs/inspects local configuration;
it does not play games or train. Tests cover every pinned card at cap and cost
boundaries, repeat casts funded by consumed MP items, attack/Wall/Turbulence
interactions, guardian resource/curse persistence, actor-only snapshots,
elimination, bounded termination/reset, empty calls, and rejected multirow
atomicity. A 512-environment/nine-player batch matches a simple independent
resource oracle. Existing arena/refill/checkpoint regressions remain required.

Validation: 104 new utility checks and all 1,383 non-browser repository tests
pass, alongside Ruff, strict mypy (74 modules), lock consistency, and whitespace
checks. The existing candidate `4d611acb-410e-40dd-8520-0257b5679d79`
reproduces its prior 32-game diagnostic at seed 1,000,070 exactly: 15 wins,
10 losses, seven truncations (four turn/three decision), zero toggle-limit
exits, and one defense deselection. This checks old-model compatibility, not
strength of the new utility curriculum; no new utility model was trained.

## Next training boundary

Add an explicitly versioned rollout observation and policy feature contract
that includes utility values, dispatches utility actions, and records effective
resource/consumption diagnostics. Broaden gifts only under a new separately
pinned 102-model refill profile; do not alter the 94-model distribution. Existing
seven-feature neural weights cannot simply read this wider hand. Any transfer
must be explicit, preserve old artifacts, and remain local-only. Only then can
this subset be marked locally training-eligible. Full-game and live readiness
still require the remaining mechanics and official differential validation.
