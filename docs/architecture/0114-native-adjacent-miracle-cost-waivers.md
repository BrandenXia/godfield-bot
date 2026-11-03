# ADR 0114: Native adjacent miracle-cost waivers

## Status and boundary

2026-10-02, native 0.61.0, `integrated-full-game-development-v12`.
Kernel, observation, plan and metadata versions advance to 12; command 1,
combat 6 and passive/removal/economy 1 remain. Cost-plan 1 adds five held
models, raising execution coverage from 216 to **221/237**, with 16 remaining.
This is inventory coverage, not a full-game readiness percentage.

The separate engine is still not full-game training-ready. Guardian/event
scheduling, trading, teams/rewards, complete neural interfaces and unsupported
hidden action-family transitions remain incomplete. Official compound timing,
fidelity and live promotion stay false. Existing arenas, checkpoints, accounts,
API revision and live controllers are unchanged; no live game was started.

## Source-derived selection and arithmetic

Pins remain catalog
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and saved Bible/client
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The cost builder revalidates both snapshots, exact API rows, Bible details,
image paths, prices, weights and the `cutCost` ability. No catalog price is
treated as a use charge.

| Model | Card | Category | Standalone ATK | Standalone DEF |
| --- | --- | --- | --- | --- |
| 46 | Spiritual Staff | Weapon | 12 | 0 |
| 143 | Spiritual Socks | Armor | 0 | 6 |
| 163 | Spiritual Hood | Armor | 0 | 9 |
| 173 | Spiritual Sash | Armor | 0 | 12 |
| 204 | Spiritual Doll | Sundry | 0 | 0 |

Tuple hash:
`d880c010d37efd2d2d3d81d1e4830286a236dfdf40c417526b527f867544d2a0`.
Native optional `cost_reducer_profiles[N,4]` uses the four numeric columns
above. It validates shape, bounds, registered category, numeric role, duplicates
and collisions before constructing state. Staff joins attack roles, armor
joins numeric defense roles, and Doll cannot lead an attack.

The saved client's `A.la` (lines 3997–4002) skips a miracle's MP cost **only
when the immediately following selected card has `cutCost`**. It is not a
global discount, reusable free turn or cost reduction on a nonadjacent card.
`A.jM.ev` (9478–9503) admits this attachment in attack and defense order after
a miracle, before ordinary compatibility/exclusivity restrictions. The Flash
one-card defense check precedes the exception and remains binding.

`A.tw`/`A.l9` (3970–3991) skip the reducer's attached ATK and attack element.
Do not extrapolate that into a universal attached-DEF rule: `A.tx` and the
ordinary DEF sum do not skip `cutCost`. The currently implemented miracle
defenses are exclusive Wall and Turbulence; `A.fj.iM` shows special response
before the ordinary numeric DEF summary (12294–12323). Those special responses
remain unchanged when a reducer follows. Standalone Spiritual armor retains
its actual DEF. A future numeric defense miracle must revisit composition.

`A.jQ` (9587–9602) checks the final `A.la` cost on confirmation, rather than
requiring affordability before selecting the miracle. This establishes the
client-visible selection/confirmation distinction. Actual server compound
timing, receipt scheduling, self-utility scheduling and all hidden-family
resolution remain explicitly provisional or incomplete.

## Joined selection and confirmation

With cost profiles enabled, all displayed HP/MP/cure/CP utilities reserve a
slot in the existing phase 2. `utility_selection` distinguishes that path
from attacks. Ordered preview contains zero attack/element, displayed utility
cost and any adjacent waiver. A cost reducer can be attached to an attack
miracle, chance miracle, utility miracle or currently supported defense
miracle; chance weapons cannot gain attack-stat additions from this rule.

Reservation changes only the command lease and selection state. It never
spends MP, grants HP/MP/CP, cures, uses a miracle, consumes an attachment,
draws a receipt or ticks a player. Displayed utility usefulness remains a
ready-phase restriction; affordability moves to confirmation. Full wallets
still do not offer their displayed resource utility. An unaffordable miracle
may therefore be reserved even if the player must subsequently cancel it.

Confirmation resolves actual identities in staged inventory, recomputes net
cost and validates actual attachment adjacency and action compatibility. It
then pays net MP once, records each waiver, applies the actual effect, consumes
the reducers and retains performed miracles at the tail. One original-owner
tick follows a resolved turn. Per-use deferred/suppressed receipts, illness,
revival, real ending precedence and global truncation remain shared behavior.

Weapon compositions can contain multiple miracle/attachment pairs, each
waiving only its own predecessor. Removing a miracle rebuilds public click
order and prunes its orphaned attachment, without inspecting hidden models.
Removing an attachment restores its predecessor's displayed cost. Undoing a
leader cancels the entire attack or utility reservation without effects.
Defense undo uses the existing displayed compatibility rebuild, including
filter prefix and special-response exclusivity.

At the 64-action selection limit, an affordable selection offers only
confirmation. An unaffordable attack/utility instead retains leader cancel;
an unaffordable defense retains selected-card undo. This prevents an empty
legal mask without granting a free cast or silently auto-playing. Cancel/undo
still advances decisions, so looping policies hit the global bound normally.
Flash still permits undo when it forbids a second defense card.

Actual unsupported family swaps, fake reducers that are not actual reducers,
incompatible hidden adjacency and unaffordable actual costs remain explicit
atomic development errors. They are not silently forgiven or claimed as full
Dream fidelity. A late invalid row or duplicate environment rolls back the
whole submitted batch, including costs, credits, hands, RNG, gifts and ticks.
Commit remains allocation-free and nonthrowing. Raw callers can omit cost
profiles and preserve old immediate utility timing and preselection affordability.

## Public views and diagnostics

`utility_selection_observations[B,4]` is an owned read-only policy projection:
active flag, displayed effect kind, displayed value and displayed net MP cost.
It is populated only for the current actor's phase-2 utility reservation.
It does not expose actual hidden identity. Existing phase-2 selected/order
and preview views also represent utility selections with zero ATK/element;
pending, chance and attack-effect views remain empty for these reservations.

`cost_snapshot[B,5]` is owned read-only **diagnostic**, not policy input:
waivers, waived MP, utility waivers, attack waivers and defense waivers.
It contains no hidden model or victim identity. Epoch reset clears its rows;
lifetime `waived_mp` and `cost_waiver_count` remain. CP utility diagnostics
record actual paid MP, so a waived Treasure use records zero spending.

## Repeatable bounded diagnostic

`simulation full-game-cost-smoke --batch-size 600 --players 3 --seed 67`
cycles 15 scripted cases: all five reducers in Treasure, Flame and Wall turns,
each starting with zero MP. Decisions read public masks; full state is used
only to fingerprint diagnostic replay. Defaults:

- 600 completed turns through 2,800 commands, 200 turns in each action family.
- Cost totals `(600,3200,200,200,200)`: 3,200 MP waived, zero MP spent.
- 2,000 CP credited, 2,000 HP damage, 800 cards consumed and 600 retained
  miracle uses.
- 600 original-owner ticks, zero other-owner ticks, gifts or real endings;
  all environments return ready after one turn.
- Metadata: `7d1ea63f90e4f835c098c2aae46a0a09f907114e2f2da1f4013d3664d34d4786`.
- Replay: `66d13245f7c47d0d24fe903ef89fb930a266aaef93cb05cf0759e6b2e01225d9`.

This is neither 600 full games nor reward/teacher data. All training,
official-fidelity and promotion flags are literal false with strict accounting.
Report versions are utility 3, acquisition/combat 10, chance 7, attack-effect
6, counter 5, revival 4, removal 3, economy 2 and cost 1. Established chance,
attack-effect, counter and revival replay trajectories stay unchanged.
Removal's fingerprint changes with the next actor's legal reservation masks,
not removal sampling or damage. Economy now records 1,200 commands for 700
turns because 500 utilities require reservation and confirmation; resource
totals are unchanged. Combat also accounts for utility reservations explicitly.
Complete-pool startup still draws all 237 held models in 41,472 draws, now
with 6,299 unsupported draws. None of these diagnostics is a strength gate.

## Remaining dependencies and verification

The known local cap 100 versus saved-client display cap 99 discrepancy from
ADR 0113 remains explicitly provisional and unresolved. This milestone does
not change shared Venus payments or capped CP credits. Trading's amount and
response interface is still awaiting the user's phase-specific versus
structured-action choice; no unapproved command redesign is introduced.
The 16 remaining held models, virtual actions, guardians/events, teams,
endings/rewards, complete Dream families and learning interfaces remain
required by ADR 0097. The guardian-subset audit remains unchanged because it
describes a different environment.

All **4,407 non-browser tests passed**, including 176 new cost-rule/diagnostic
cases. Coverage includes all five reducers across utility/attack/chance/defense,
standalone roles, multiple adjacent waivers, zero-MP selection, confirmation
timing, undo/pruning, Flash, affordable/unaffordable toggle-limit escapes,
global truncation, copied diagnostics and reset, hidden mismatches, raw-profile
omission and malformed profiles, late-invalid/duplicate whole-batch rollback
and corrected retry. Default replay pins and partial batches across 2/3/9
players pass. The unchanged browser fixtures were not rerun and are excluded
from this count.

Ruff checks over source/tests, strict typing over 101 modules, 41 selected
Python formatting checks, native formatting, offline lock consistency and
`git diff --check` passed. Installed native version and all exported schema
constants match v12. The saved client's SHA matches the source pin above.
A repository-wide Ruff invocation still reports ten pre-existing native
Python lint issues (eight compact-stub lines, two export-order issues);
read-only checks of HEAD confirm they predate these changes. They were not
silently counted as a passing whole-repository lint check or bulk reformatted.

Git writes remain unavailable under the earlier approval-review limitation;
no alternate write mechanism or retry was used. v8–v12 are saved locally,
uncommitted.
