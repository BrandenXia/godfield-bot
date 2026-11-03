# ADR 0128: Generated guardian direct actions with virtual fallbacks

## Scope and approval

2026-10-17. Human approved: use sampled cards directly when they can lead;
reserve Earth Drop and Full Moon Blade for cards that cannot lead. This
supersedes ADR0127's deliberately narrow Earth Drop-only approximation.
Continue the separate integrated engine toward ADR0097's full acceptance
requirements. Do not equate a complete route ledger with complete game fidelity.

Native0.75.0, kernel/observation/plan/metadata26,
`integrated-full-game-development-v26`; attack-family schema7. Six-column
command1 and phase-specific numeric trade-choice2 are unchanged. Old arenas,
models, checkpoints, live controls, accounts and credentials stay unchanged.
No training or live games are started. All local-training, full-game readiness,
official-fidelity and promotion flags remain false. Git is read-only in this
task: changes are saved in the working tree, not committed.

## Evidence and inference boundary

Use the frozen catalog and client, not a new freshness claim:

- Catalog SHA `df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
- Client SHA `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.

Pinned `attackByGuardian`10607–10665 accepts generated model lists, skips the
held-use branch and ordinary selected-miracle debit, but explicitly charges the
MP-powered weapon's ownerMP. `gkN`13024–13032 distinguishes leaders: trades and
weapons lead; additive-only/passive sundries and additive/defense-only miracles
cannot. Virtual286 has ATK10 and the weapon-category override; ordered attack
composition includes its additions. These client facts do **not** establish
the server's generated-list construction, probability, multiplicity, targets,
compound ordering, exchange allocations, sale parcel or purchase decisions.

Those choices remain labeled provisional: one sampled card, category-filtered
pinned gift weights, direct lead when possible, otherwise Earth `[285,card]`
or Moon `[286,card]`. Earth keeps207 models/weight470, Moon30/weight30; pool SHA
`f3dba9f996e4c41eb61a4e0c16630713974e5d75c422d25038b12a0ee61bc3f8`.
No rare/passive/defensive/trade model or summon group is filtered out.

The independently pinned `(model,route)` ledger has237 rows; SHA
`de73db352861dc25b0f091b0e34b0715fb3e2cad04fba19deb4ea82a486d020f`.
Route1 direct attack130, route2 utility18, Exchange/Sell/Buy one each,
route6 Earth Drop82, route7 Moon Blade4. Source construction independently
re-derives leader roles from the pinned abilities and checks the exact ledger.
Raw native subsets support focused tests; the source factory supplies all rows.

Moon Aura231 doubles ATK10 to20; Mirage232 fans out; Wall233 and Turbulence234
do not invent offensive defensive effects and preserve baseATK10. Defensive
miracles remain in the pool, not resampled until an offensive outcome appears.
Their server construction is unverified.

## Shared composition, effects and queue

Model-only composition has explicit held/generated source contexts. Held
order still computes actual/displayed identities and costs. Generated context
does not inspect a held slot, consume a real card, mark a miracle performed,
charge ordinary miracleMP, grant a replacement or advance a guardian's turn.
Magical Stick58 still computes from and debits ownerMP once. Defenders retain
their actual selected costs and cost reducers.

Producer family8 stores guardian identity and sampled model. It is suppressed
if its owner dies or guardian is replaced before dispatch. Eligible attacks
enter family9 using shared chance, armor, specials, reflection, counter, removal,
recoil, dangerous target, curse, Sun and actual-held Bow behavior. No eligible
enemy suppresses the producer without an invented self-target or MP debit;
Pestle keeps its explicit living-seat controller. Enemy-only phenomena likewise
do not sample an empty roster: a private absent-recipient sentinel enters and
is suppressed by the shared queue, preserving queued/suppressed conservation
without revealing a hypothetical target.

Utilities share effects without held bookkeeping. Fate enqueues phenomena;
it never recursively resumes/ticks. Solar can invalidate later guardian frames
without creating another guardian wave. Nested reactions finish before siblings,
gifts, ending checks and the already-owned original turn boundary. New source
and child families participate in the existing atomic staged mutation/rollback.

Each queued shot owns its weapon kind/value, area and danger metadata. Native
resume restores that payload rather than carrying a previous attack's view
through a counter/Bow/guardian response. Repeated original/generated strikes
restore their own view after nested counters. CP utility accounting accumulates
multiple Treasures within a command rather than overwriting the prior gain.

## Generated economy and custody

Generated Exchange samples uniformly among cap100 MP/CP wallet allocations
whose shared CP→MP→HP conversion is payable, then calls shared settlement.
This allocation distribution, local caps and event timing are provisional.
New independent allocation XOR stream: `0xd7a34e5f18b9026c`.

Sell draws a second category-weighted Earth artifact in fresh private custody,
owner sentinel−2. It is not selected from or charged to the guardian owner's
hand. Reflection retains custody; accepted delivery uses shared fresh identity,
Dream/caps and payment. Suppressed/undelivered generated parcels retire rather
than minting a refund to an actual hand. Terminal truncation preserves unresolved
diagnostic custody until explicit reset. This parcel-construction rule is
provisional, not asserted official behavior.

Buy retains the original generated source as automatic buyer. Its native
purchase decision applies only while that same seat remains current source.
Reflection to a new current source exposes voluntary phase6. It does not turn
another seat's purchase decision into an autonomous action. Existing owned
Exchange/Sell/Buy controls and private escrow behavior remain unchanged.

## Observable contract and reports

`guardian_generated_snapshot[B,23]` preserves the first7 columns and appends
Moon, route, attack, specialMP and generated custody accounting. Private owned
readonly histograms index models3..239:

- `guardian_generated_model_counts[B,237]`: scheduling draws, including later
  suppressed producer frames.
- `guardian_generated_execution_counts[B,237]`: dispatched effects, not resolved
  attacks or receipts; one utility may enqueue another phenomenon.

`generated_action_observations[B,6]` reveals active flag, producer, generated
model, virtual leader, current source and target only for current generated
attack/market responses. No queued model, guardian identity, custody ID, RNG or
future recipient is exposed to policy features. Reset clears counters; prior
returned arrays remain owned and intact.

New `full-game-generated-smoke --guardian earth|moon|mixed` report schema2
checks weighted scripted first turns, not full games/training. Old
`full-game-earth-smoke` delegates to all-Earth mode. The controlled probe requires
draws equal dispatched effects, exact route/strike/debit/custody accounting and
one original tick; separate tests cover suppression. Full outcome coverage is
always false in this bounded stochastic report, even if a sample hits all models.

Phenomenon report schema4 separately counts generated Fate executions. Its
exact initial-world arithmetic remains enforced without nested Fate; nested
events instead use explicit effect/count/conservation bounds because hands,
wallets and living recipients may already have changed. An extra event is not
an extra turn. Deliberately incomplete raw configuration still exercises atomic
batch failure, unchanged per-row preimages and bounded diagnostic copying.

## Build correctness and verification

Native uv cache keys now include CMake configuration, C++ headers/sources,
bindings and type stubs, preventing a stale local wheel after a C++ edit.
This follows uv's documented dynamic-cache-key behavior:
[uv cache documentation](https://docs.astral.sh/uv/concepts/cache/#dynamic-metadata).
The source glob keys supplement the explicit project file key; custom keys
replace defaults. Offline rebuilds use existing local backend packages, not
manual edits to cached wheels.

Verification covers all237 routes at2/3/9 seats; four Blade additions; generated
and owned complex/area attacks across counters; special defenses; ownerMP debit;
same-command Treasure accumulation; Fate replacement and nested Fate; generated
Sell/Buy reflection/custody/payment/Sun; staged Mortar visibility; missing
dependencies with full rollback; no-recipient suppression and private views.
The non-browser regression passes9678 tests; the latest rebuilt no-recipient
queue path also passes all888 generated-action unit tests. Ruff and mypy pass;
the92 full-game/CLI Python files and modified C++ sources pass format checks.
Offline lock validation and the normal offline uv launch command pass. Browser
tests and official-game differential validation were not run. Unrelated existing
format-only differences elsewhere in the repository are left untouched.

At4096/3/seed67, mixed probe:1045 generated dispatches,840 attack entries,
179 Drop receipts,4911 commands,186 observed models. The all-Moon sample reaches
all30 miracle models. At4096/9/seed0, Fate probe has4097 phenomenon events but
4096 original ticks, including one generated Fate. None are full-match evidence.

Replay audit: acquisition, combat, effects, chance, counters, danger, costs,
compound utility, discard, standard guardians, devils, trades, removal and revival
behavioral hashes remain unchanged. Area/complex-weapon hashes change for the
corrected per-shot response views; Earth/phenomenon hashes change for approved
generated routes and explicit new diagnostic arrays. All metadata hashes change
with v26. Exact gameplay totals remain checked independently of fingerprints.

## Remaining full-game objective

The factory joins42 guardian model labels, not42 fully verified interactions.
Complete Apocalypse/Sacrifice and virtual commands, team/reward/elimination
rules, hidden cross-role resolution, official-cap99 migration, complete native
observation/action/checkpoint/learner adapters, full-episode liveness and useful
local learning, plus official differential validation remain required. Existing
provisional distribution/timing assumptions must remain visible and live
promotion blocked until their acceptance criteria are met.
