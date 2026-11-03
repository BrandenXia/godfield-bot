# ADR 0113: Native Treasure and shared wallet credit

## Status and boundary

2026-10-02, native 0.60.0, `integrated-full-game-development-v11`.
Kernel, observations, plan and metadata advance to 11. Commands remain 1;
combat plan 6, passive/removal plans 1. New economy plan 1 adds one CP utility
model, raising held-model execution coverage to **216/237**, with 21 remaining.
That denominator excludes guardians/events and is not a readiness percentage.

This milestone implements Treasure, not Exchange/Sell/Buy or full economics.
Full-game local training, complete neural interfaces, official fidelity and
live promotion remain false. Old guardian profiles, arenas, checkpoints,
strict replay admission, API library pin, accounts and live controllers are
unchanged. No official game or browser interaction was started. Git writes
remain unavailable under the earlier approval-review failure; no alternate
write mechanism was used and v8–v11 remain saved locally, uncommitted.

## Sources and provisional rules

Pins remain catalog
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and Bible/client
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
Catalog model 236 is a Venus miracle with `boostCP`, value 10, cost 5 MP,
gift weight 1 and no attack/element. The Bible's exact Treasure entry agrees:
`$+10`, `5MP`, weight 1/500. The source builder revalidates both snapshots,
their exact matching rows/images and the existing verified CP-utility parser.

Economy tuple `((236,5,10,5),)` hashes to
`efc35968f55a511a7c573d015572addddeb3a659f923f82179d1c98212de1918`.
The joined 13-effect utility/cure/CP tuple hashes to
`a24750fb5709e66d6000f3e3a8d4eae02e58554efecadcce419c47c6083ae6ce`.
Utility codes 3/4 stay mild/full cure; appended code 5 is CP. Original guardian
HP/MP profiles stay schema 1 with exactly eight cards and their original hash.

The pinned client's `glk` does not list `boostCP` among enemy-targeted actions;
its `boostCP` event updates the owner's CP. This supports the resource
direction, but the native immediate/no-defense schedule, availability below
the local cap, gift timing and all compound ordering remain explicitly
provisional. No new official event is admitted and no official cap is claimed.

The saved client also visibly clamps HP/MP/CP displays to 99 in `eW`/`dH`/`bc`,
and Exchange preview controls clamp to 99. This is affirmative client-display
evidence, not evidence for native cap 100. The existing development engine
deliberately retains its versioned, explicitly provisional 100 cap in v11.
That known discrepancy must be resolved in a later source-fidelity version;
neither this plan nor its diagnostic is a cap-validation oracle.

The user approved sharing CP→MP→HP debit arithmetic with Venus and future
trade transactions. `payment_rules.h` retains that pure helper and adds
`credit_cp_capped(wallet, requested, cap)`. It returns actual credit and capped
remainder, preserves HP/MP and cannot resurrect a player. Preconditions are
caller-validated nonnegative amounts and bounded balances. Venus still credits
its stated damage up to cap 100, not merely collectible funds; self-transfer
remains a no-op. Existing Venus/Amulet regression results stay unchanged.

## Joined CP utility lifecycle

At ready, use displayed identity and the actor's public wallet: living owner,
MP at least 5, CP below 100. Equal-cost MP is allowed. An unavailable choice
is rejected without spending, using, ticking, drawing or crediting.

On accepting a displayed utility, resolve its actual card in the staged hand.
Check actual MP cost, spend exactly that cost, credit actual CP up to 100,
mark/move the miracle to the tail, then run the original owner's single tick
and real ending checks before limits and deferred gifts. No source CP charge
is inferred from price, no target defense phase is inserted and no separate
subcomponent scheduler is driven.

Reused Treasure still costs 5 and yields up to 10. Hidden same-family utility
swaps can resolve a different resource/cost; a CP-full actual Treasure
displayed as Spring spends 5 but credits zero, while actual Spring displayed
as Treasure spends 7 and heals HP. This follows the existing actual-utility
boundary, not official validation of these particular swaps. Unimplemented
actual action-family transitions and unaffordable actual costs still fail as
explicit atomic development errors. Complete Dream handling remains required.

CP credit happens before a lethal owner illness tick; death or Amulet revival
does not reverse it. Original-owner ticks, real win precedence, limit
truncations, no-receipts-on-terminal/truncated and per-use receipts including
reused miracles retain existing behavior. All state, cost, hand, credit,
diagnostics, random receipts and ticks stage across the submitted batch.
Commit remains allocation-free/nonthrowing; a later rejected command or
duplicate environment cannot leave earlier credits committed.

## Observability and diagnostic

`cp_utility_snapshot[B,4]` is owned read-only diagnostic data, not an actor
policy projection. Fields: CP utility uses, actual CP credited, exact MP cost,
capped uses. Capped uses include a zero-credit actual CP-full disguised use.
Epoch reset clears episode counts but not lifetime `cp_utility_count` or
`utility_cp_gain`. Public legal masks/hand projections do not read actual
hidden models before resolving a command.

`simulation full-game-economy-smoke --batch-size 700 --players 3 --seed 67`
cycles seven scripted cases: fresh, near-cap, full wallet, unaffordable, reused,
actual Treasure disguised as Spring, and actual Spring disguised as Treasure.
Choices read only public slot availability; full snapshots are fingerprinted
for diagnostics. Defaults: 700 accepted commands and owner turns, 500 retained
miracle uses, 200 passes, CP totals `(400,2500,2000,200)` and 2,700 total MP
spent. The extra 700 MP belongs to 100 actual Spring uses, not CP utility.
There is no consumed card, HP damage, automatic gift or real terminal ending.
These are mechanics turns, not full matches or a teacher/reward dataset.

- Metadata: `3c89a884d25397420c6d78b579b63894a3369214e593515e042dfd2480b6c4ce`.
- Replay: `fdf881e33d3fb9a1caadb9e8c76099bed5cf9718cb47566c673c3409bf15387c`.

Other report schemas advance to utility/removal 2, acquisition/combat 9,
chance 6, attack-effect 5, counter 4 and revival 3. Existing chance, effect,
counter, revival and removal behavior hashes remain unchanged. Complete-pool
startup still samples all 237 models in 41,472 draws, now with 6,817
unsupported draws. Its legal masks/replay intentionally change when Treasure
becomes available:
`62cd679d462d8a59e720e665937f2f63dc4ae48da3edc3388f5869022f25bdb9`.

## Next dependencies

Trading needs public amount/response choices and source-pinned restrictions,
then shared waterfall debits and capped credits inside joined transactions.
The saved client's `A.fo.iP` exposes ±1/±10 controls for MP and CP. `A.fp.k0`
and `k_` exchange each resource one-for-one with HP in a bounded preview;
`A.jQ` submits selected item IDs and **final** MP/CP values. Exchange is not
a CP purchase and should not be modeled as a requested charge to the payment
waterfall. Direction/preview/confirm choices need explicit phase semantics,
whereas Sell/Buy payments can reuse the shared wallet debit and credit. The
next interface design is awaiting the user's phase-specific versus structured
action choice; no unapproved command redesign is included here.
Other inventory/passive mechanics, guardians/events, teams/rewards, hidden
family resolution and complete learning interfaces remain required by ADR
0097. Neither CP utility coverage nor a green diagnostic establishes those
acceptance criteria. The guardian-subset readiness audit remains unchanged,
because it describes a different arena rather than this separate engine.

## Verification

All **4,231 non-browser tests passed**, including 148 new economy/diagnostic
cases. Coverage includes exact affordability, partial/zero cap credits,
first/repeated uses, actual-resource Dream swaps, public hidden-state
noninterference, lethal owner ticks, Amulet hooks, real ending/limit ordering,
receipt overflow rollback, late-invalid/duplicate whole-batch rollback with
corrected retry, episode reset, raw-profile omission and malformed profiles.
The established Venus/Amulet regression suites and replay hashes still pass.

Ruff checks, strict typing across 99 modules, 16 selected Python formatting
checks, native formatting, offline frozen dependency checks and
`git diff --check` passed. The saved source client's SHA matches the pin above.
An offline full dependency re-resolution initially attempted an unavailable
Git fetch; only the local native version in the existing lock was updated,
and `uv lock --check --offline` then confirmed consistency. No API revision,
dependency source or unrelated package version changed.

The unchanged browser fixtures were not rerun and are not included in the
4,231 count. No Git write was retried under the earlier approval-review
limitation, and no live controller or account was run.
