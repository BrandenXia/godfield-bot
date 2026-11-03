# ADR0137: approved insufficient-MP fizzle resolution

## Decision and scope

User-approved2026-11-03; implemented in native0.83.0/schema33. A displayed-legal held
selection whose actual hidden net miracle cost exceeds available MP uses up
its selected nonmiracles, marks its selected miracles performed and pays only
the available MP. None of that selection's effects apply. There is no HP debt,
partial component benefit, successful waiver credit or free hidden effect.

An attack or utility fizzle finishes the original turn through the existing
scheduler. A failed defense supplies no DEF, filter, block, redirect, counter
or selected self-effect; the incoming attack and its queued family continue
normally. Existing replacement receipts and miracle-use custody apply, with no
invented tick for a defending player. Costs use actual adjacent reducers before
checking affordability. Affordable selections retain their existing behavior.

## Compatibility and observability

Use a separate gameplay release, native0.83.0/kernel, observation, plan and
metadata33, ruleset`integrated-full-game-development-v33`. Preserve six-column
commands, family8, trade-choice2 and reward1. Append raw
`resolve_hidden_costs=false`; enabling it requires the complete checked hidden
component resolver. The source factory defaults to the approved provisional
fizzle and offers an explicit strict-error mode for diagnostics. Metadata pins
the choice. Existing arenas, trained checkpoints and live controls are unchanged.

Expose owned readonly per-episode diagnostic counters for affected attack,
utility and defense selections, selected/consumed/performed cards, requested
net cost, paid MP and unpaid deficit. These are private diagnostics, never
policy inputs. Reset clears them; a rejected batch cannot commit them.

The rule is user-approved provisional behavior, not observed official server
behavior. It does not claim full-game training readiness, official fidelity or
live promotion. Complete policy encoding and rollout/learning still need work.

## Verification

28 new direct/metadata/episode tests pass; the combined cost/ineffective/reward/
episode suite passes998 tests. Direct cases cover zero/partial MP payments,
hidden chance/fixed targeting, utility suppression, mixed cards/true waivers,
failed defense filters/counters/self-effects/redraw, Darkness terminal credit,
staged rollback on another invalid row, readonly ownership and reset. The
original two-player seed0/32-environment failure now completes32 games; explicit
strict mode still reproduces31 completions and one atomic unaffordable error.

The new sweep covers players2–9, solo/pairs/mixed-solo/four-team rosters,
seeds0/1/67 and32 environments per configuration, with reward tracking enabled:

- 3072 games complete:3050 faction winner endings and22 all-dead draws.
- Zero engine errors, turn limits or decision limits;1,066,610 accepted commands.
- 26 fizzles:24 attack and2 utility selections,42 selected cards (16 consumed
  nonmiracles/26 performed miracles),189 requested MP,94 paid MP,95 unpaid MP.
- The reported zero defense fizzles in random episodes are not defense coverage;
  direct tests exercise failed-defense paths and incoming resolution separately.

The sweep's96 report records and summary are retained locally at
`/private/tmp/godfield-v33-full-episode-sweep.jsonl` until temporary cleanup.
All24 reviewed default replay fingerprints, including legacy100, are unchanged;
only explicit metadata pins advance. No reward/checkpoint migration or live
control change is inferred. Episode report6 pins the cost policy and validates
cost/card conservation. Static checks and lock consistency pass.
The final nonbrowser regression passes13,076 tests in246.55s. One test that
intentionally builds an incomplete raw engine needed its positional truncation
boundary updated for the appended flag; it now asserts the omitted action-table
identity so a future extension cannot silently remove its failure coverage.
Archived reward-schema1 records retain their explicit v32 or v33 gameplay ID;
new adapters pin the configured v33 ID without relabeling old records.
