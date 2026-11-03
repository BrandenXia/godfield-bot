# ADR 0131: private Dream targeting/trades and complete-episode diagnostics

## Objective and decisions

The full-game objective in ADR0097 remains open. Native0.78.0 advances the
separate full-game kernel/observation/source-plan/metadata contracts to29,
`integrated-full-game-development-v29`. Command1, family8, trade-choice2 and the
approved99 ceiling are unchanged. No existing arena, checkpoint or live control
is switched to these rules.

Unscripted complete-pool play exposed failures not reached by the existing
scripted turns: ordinary attacks disguised as chance cards aborted on targeting
mode differences; subsequently Sell disguised as Exchange aborted at confirmation.
The user approved three explicitly provisional rules:

1. Preserve displayed controls, but privately resolve the actual attack's
   targeting. If a displayed chance card supplied no target for an actual fixed
   attack, sample a living enemy using an independent stream.
2. Resolve all six Exchange/Sell/Buy disguise swaps using actual trade effects.
   Reuse applicable displayed choices and sample missing parameters privately.
   A real Buy offer is revealed only after defense.
3. A hidden actual Sell without another unused parcel consumes Sell and records
   an empty sale, with no transfer, payment or invented response family.

These are local completion hypotheses, not official Dream/server behavior.
Pinned client/catalog identities and existing public chance/trade controls are
reused; no new official differential evidence is claimed.

## Compatibility and private attack targeting

Append raw constructor options `resolve_hidden_targeting=false` and
`resolve_hidden_trades=false` after `resource_cap`. The complete source factory
explicitly enables both; old raw diagnostic fixtures retain their errors.
Both properties are readonly and the source metadata pins the hypotheses.

Reservation, legal masks, preview and player target prompts still depend only
on displayed cards. At cast, an actual chance attack always uses its existing
`chance_target_rng`, ignoring a player target supplied through a fixed disguise.
An actual fixed attack lacking a public target samples living enemies using
`illness_rng XOR 0x6c9e0e8bb01e8a3e`. Ordinary fixed/Fog and chance streams are
otherwise unchanged. Actual hit rates/effects/costs and queue settlement remain
authoritative.

Dangerous Pestle retains its own all-living/Mortar-recipient algorithm. When its
disguise supplied no target, a living source placeholder admits the queued
producer; it is not the final sampled recipient. Do not enqueue an invalid
negative placeholder that the shared scheduler would suppress.

`hidden_targeting_snapshot[B,4]` is trusted diagnostics only: mismatched casts,
actual-chance-over-fixed, actual-fixed-over-chance and provisional fallback
enemy draws. No true identity, mismatch counter or private RNG enters a policy
view or changes a legal mask before cast.

## Private trade parameters and shared settlement

The two independent options are not a generic hidden-role fallback. Only actual
and displayed held trade models3/4/5 enter the private trade resolver, and only
with complete Exchange/market registration. Unsupported other roles still fail
atomically rather than being discarded or changed into unrelated effects.

An actual Exchange behind Sell/Buy samples a conserved bounded wallet using the
existing exact allocation enumerator and a separate private stream. The public
sale parcel and enemy target are not transfers or costs; they are ignored.
Actual Sell/Buy behind Exchange ignores its uncommitted wallet preview and
samples a living enemy. Actual Sell samples a different unused owned parcel,
excluding performed miracles. Sell/Buy disguised as one another retain the
displayed enemy decision, subject to existing Fog rules; Buy ignores a selected
sale parcel, leaving that owned item unchanged.

Missing-parameter streams are derived independently from `illness_rng`:

- Exchange allocation: `0x7c4a7f8c93c4d7a1`.
- Sale parcel: `0xb31f2c8e57a04d69`.
- Enemy target: `0x9e87c4d1b62a503f`.

A private target is not sampled again by Fog. A real Buy follows ordinary
defense/custody before revealing the offer and asking the current buyer to buy
or refuse. Missing pre-cast UI does not invent an automatic purchase decision.
Super Mirror/reflection, refunds, receiver Dream/caps, CP→MP→HP payment and
seller credit, Sun/Bow, receipt scheduling and single-original-tick settlement
reuse the shared market/Exchange paths.

Empty hidden sales retire only the actual leader and tick once; performed
miracles remain owned, with no transfer/payment. If native refill is enabled,
the ordinary one-use replacement path still applies. This is an explicitly
modeled empty transaction, not a successful sale or an omitted artifact effect.

`hidden_trade_snapshot[B,9]` records mismatched casts; actual Exchange/Sell/Buy;
private allocation, parcel and target draws; empty sales; and casts discarding
inapplicable public parameters. Existing reservation counters describe the
displayed UI; commit counters describe actual effects. They need not match by
trade kind during a disguise swap. Cross-counters provide explicit attribution.
All snapshots are owned readonly private diagnostics and reset with epochs.

## Unscripted whole-episode diagnostic interface

New `simulation full-game-episode-probe` starts native nine-card deals from all
237 held models, automatic use/Prayer replacement, provisional18-slot overflow,
the99 ceiling and an explicit provisional Apocalypse threshold. Default bounds
are64 environments,3 players,256 completed turns,2048 accepted decisions, seed67,
policy seed901 and Apocalypse after64 turns. Configuration/report metadata pins
these choices; `--players` admits2 through9.

The weak `bounded-public-random-v1` policy receives public decision rows and
legal masks only. It has an independent per-environment RNG and confirms an
available selection after two consecutive edit decisions. It does not consult
true hands, private effect counters, tickets or scheduler diagnostics. This is
not a teacher, strength benchmark, learned policy or reward dataset.

Atomic batch errors are reproduced with the exact same commands, without
resampling. Failed environments stop at their unaccepted native decision;
healthy independent environments continue. No error is recovered by passing,
canceling, skipping a turn, resetting, dropping a card or suppressing a rule.
Diagnostic state changes on a failed batch/row and non-reproducing batch errors
fail the whole probe. Each result retains its epoch, decision, phase, accepted
count, error command/reason and native outcome.

Winners, all-dead draws, turn limits, decision limits and engine errors remain
distinct. Native absorbing limits and an outer decision bound prevent unbounded
loops. Strict report accounting covers every environment, accepted phase/forced
command counts and hidden-resolution conservation. Diagnostic fingerprints are
not policy observations or a claim to expose every private RNG state.

The CLI prints the structured report and exits1 if any engine error remains.
Truncations are reported as truncations, never completed games or draws. Training,
official-fidelity and promotion eligibility remain false even if every episode
in a particular diagnostic batch reaches a native ending.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-episode-probe \
  --batch-size 64 --players 3 --seed 67 --policy-seed 901
```

## Observed integration state

The default current probe accepts15576 commands.58/64 environments reach native
winner endings;6 stop on explicit hidden defense/composition errors, with no
draws or limit truncations. These are all-seat random-policy games, not58 wins
for a candidate. The two-seat64-environment probe completes63 and records1 error;
the nine-seat32-environment probe completes25 and records7 errors. Native
endings do not prove complete rules, useful learning or official fidelity.

Default failed environments8/20/21 select hidden actual cards that cannot defend
in the displayed role;9 reveals incompatible actual armor elements;26 reveals
an addition-only actual miracle as a displayed attack leader;51 reveals an
actual weapon incompatible with its displayed addition role. Keep these failures
visible until their private-resolution semantics are explicitly chosen and
implemented. Do not filter their cards from acquisition to manufacture success.

All24 existing scripted probe behavioral fingerprints remain identical to v28.
Metadata fingerprints change with the new versioned hypotheses. Targeting tests
exercise all same-category attack leaders at2/3/9 seats and independent target
oracles, dead-seat exclusions, Pestle, reset/privacy and rollback. Trade tests
cover all six swaps, both Fog states at2/3/9 seats, independent missing-parameter
oracles, ignored previews/parcels, empty sales/refill, Buy refusal, zero-HP
Exchange Sun/Bow and rollback. Episode tests cover honest failure/limit outcomes,
deterministic independent policies, corrupted report rejection and injected
atomicity failures. The combined focused suite passes655 tests, including
strict bounded failed-command tokens. The final non-browser regression passes
11766 tests in192.66seconds. Ruff, mypy over128 source modules,102-file Python
formatting, native clang-format, offline lock and whitespace checks pass. The
ordinary offline uv CLI reproduces58 completed episodes and6 explicit errors,
with its expected exit1 and all readiness/promotion flags false. No official
games, real training jobs, account changes or checkpoint/live-policy writes
were performed.

Full-game readiness remains unproven: remaining hidden-role/cost/composition
semantics, team/elimination/reward and broader endgame handling, complete
neural observation/action/checkpoint/learner interfaces, all-family full-episode
liveness and useful-learning validation remain required by ADR0097. Official
validation and live promotion retain separate gates. This milestone does not
shrink the full objective to diagnostic completion rates.
