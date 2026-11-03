# ADR 0122: Joined native guardian ownership and post-turn reactions

## Scope and honest remaining coverage

2026-10-13. Continue the separate full-game environment, not the old guardian
arena, with a joined owner/trigger/effect/departure lifecycle. Native0.69.0 is
`integrated-full-game-development-v20`, kernel/observation/plan/metadata20,
command1 and shared-family3. Existing arenas/checkpoints/live controls and
credentials are unchanged. No learning job or live game is started.

Guardian Pot201 and Release239 add two executable held summon abilities,
raising that ledger to **233/237**. The guardian-event ledger separately joins
**40/42** standard effects, including formerly omitted Diamond Axe264.
All ten ownership outcomes remain representable and sampled. Earth285/Drop and
Moon286/Full Moon Blade's special producers remain unsupported at activation:
they reject the whole command atomically, rather than disappear from sampling
or silently become no-ops. This deliberate incomplete development state is
not full-game training-ready; all readiness/fidelity/promotion gates stay false.
The complete objective and ADR0097 acceptance requirements remain active.

## Frozen primary-source contracts

Retain catalog/client pins
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are frozen Oct1/Sep20 sources, not a new Oct13 freshness claim.

The saved Bible specifies activation after an enemy turn at25%, and departure
when damaged at10%. Each standard god has five effects with action percentages
30/25/20/15/10, matching catalog weights6/5/4/3/2 and the client's divide-by20
display. The client has one `guardian` per player and replaces its portrait
in `sd1`; its ten-group order is Mars, Mercury, Jupiter, Saturn, Uranus, Pluto,
Neptune, Venus, Earth, Moon. Earth uses trade/weapons/armor/sundries; Moon uses
miracles. Those special producers must not be claimed complete from a base
artifact or portrait alone.

The separate strict guardian table is40 rows of model/group/weight/ATK/element/
hit-rate/kind/value/curse/origin; SHA
`d5275fde52d4fb421dd387e65a8866d4535216263a534e91d4af595dc468c471`.
The complete42 Bible asset/path/detail/element table is independently pinned
to `0febd23f793202ac6e5ec96e5cb7721dc902341d51075ee9effe7c0088142ae5`.
Exact notes and both complete source pins are revalidated. Mutated numeric
text/assets/element metadata cannot pass just because action percentages match.

Summon rows `(201,0),(239,15)` have SHA
`3761e8f41af915bacf6f6db4e8874bea0ec6c95c0d1960e762bbd1cb6f0ff606`.
Pot's listed price10 is not a use charge; Release costs15MP, performs/retains
its owned miracle, and permits an adjacent waiver. Their exact API/Bible
identity/cost/price/gift contracts are checked. They are separately joined,
not appended to or relabeled into the historical15-row utility hash.

Read-only primary acquisition evidence has only three redacted activation
snapshots: run `1d87e285-f408-4d66-8e81-4a0215f32849`, evidence events111198,
111311 and111414, sequences20/26/33. They show ordinary use/defense/damage
before `attackByGuardian`, and the third shows a guardian money event before
gift/advanceGF. Guardian/model/numeric payloads are redacted. This supports
event-family order only, not exact general timing, model weights, group sampling,
numeric effects, targets, RNG or compound outcomes. No official validation is
inferred from event labels or owned unrelated item arrays.

## Integrated ownership and stochastic lifecycle

Each seat owns `(group+1,identity)`, with zero absence and ten legal groups.
Actual summons provisionally choose all ten uniformly, replace the old guardian
and issue a new monotonic guardian identity independent of artifact IDs.
Reservation never spends/summons; actual identity and net MP resolve only at
confirmation. All uses preserve ordinary per-use deferred receipt rules.
Trusted `seed_guardians` exists for setup/testing only: it is owner-bounded,
batch-atomic, token-independent and rejected after the environment starts.

After original response/death families and the single original-owner tick,
other living owned guardians receive25% checks in provisional ascending seat
order. Activated standard effects select their pinned relative-weight row and
fix target/payload before queueing. Offensive/enemy-money targets use a separate
uniform living-enemy stream; Fog does not replace that endogenous selection.
No-target payloads suppress without entering a dead actor. Generic guardian
origin is4; Diamond Axe's `categoryWeapons` origin is0, so typed defenses don't
misclassify it as a generic guardian or miracle.

These post-turn tasks share family4 with the existing counter1/original2/Bow3
queue. Nested reactions finish before siblings. Every wave is scheduled once
per original completed turn; guardian/counter/Bow responses never recursively
schedule another guardian wave or advance another owner tick. Gifts, real
endings and turn limits wait for the queue. The hard decision limit still
bounds an unfinished response family. Identity mismatch, dead source or dead
target suppresses a queued guardian task; current revealed shots retain their
fixed payload. The existing hard queue bound remains enforced atomically.

Each positive HP debit can check10% departure after owned Sun handling. Final
death clears ownership without consuming a departure ticket. Covered paths
include ordinary/Darkness attacks, direct Pestle/Mortar damage, recoil,
CP→MP→HP spill, illness infliction, direct utility damage, periodic illness and
worsening. Multiple debits in one command remain separate edges. Source-defined
percentages do not prove this complete compound order or damage interpretation;
those choices remain explicitly provisional.

New dedicated illness-seed XOR streams are summon `0x3f84d5b5b5470917`, trigger
`0x9216d5d98979fb1b`, model `0xd1310ba698dfb5ac`, target
`0x2ffd72dbd01adfb7`, hit `0xb8e1afed6a267e96` and departure
`0xba7c9045f12c7f99`. Existing streams are unchanged; target Dark Cloud skips
the guardian hit ticket. All streams stage with the complete command batch.

## Joined effect resolution

Standard attacks, absorption and curses reuse the existing normal/filter/
special/redirect/counter/death paths. Direct curse and enemy money effects
open a zero-ATK special-response window, not a numeric-armor response.
Reflections change current source/target, not original turn ownership; they
don't reroll the guardian hit. Only Super Mirror handles generic guardian
origin, while Diamond Axe retains the weapon classification.

Neptune effects automatically cure all illness/documented curse flags, restoring
Dream disguises, or grant owner HP/MP. Venus automatically credits owner CP
or every living player's CP; Bribe credits the chosen enemy, and Fine shares
CP→MP→HP debit plus requested-amount credit. Local100 caps, living-recipient
scope, requested credit and payment timing remain provisional. Fine can trigger
Sun/death/departure, but its payment loss is separate from attack damage and
doesn't pollute Venus-counter accounting. Absorption and automatic HP gains
are both attributed to guardian HP-gain diagnostics. None of these reactions
ticks its owner or spends an invented guardian MP/price cost.

## Observable, private and atomic

Owned/read-only diagnostic arrays:

- `guardian_snapshot[B,P,2]`: true group/identity for each seat.
- `guardian_statistics[B,19]`: summons, replacements, checks/activations,
  model/target draws, queued/resolved/missed/suppressed tasks, damage checks,
  stochastic/death departures, attack HP loss, HP/MP/CP gain, payment HP and cure.
- `guardian_model_counts[B,40]`: per-episode standard-model draw histogram.

Policy `guardian_observations[B,9,4]` contains cyclic seat/present/visible/group;
Fog hides others' portraits and no diagnostic identity is emitted. Current
`guardian_effect_observations[B,4]` reveals active/model/current-source/target
only during an active guardian response. Pending models/recipients/queue/tickets
are never policy features. Metadata validates layouts and full source/coverage
ledgers; complete-action/checkpoint compatibility remains false.

Lifetime summon/activation/resolution/HP-loss/departure counters survive reset.
Reset clears owned guardians, episode statistics/histograms/flags/queue, reseeds
streams and increments epoch. Returned old arrays stay owned/read-only.
All ownership, automatic effects, resources/statuses, hands/disguise changes,
Sun/Bow tasks, native draws and lifetime deltas stage before nonthrowing commit.
A rejected last special/hidden role, stale/duplicate/finished row or raw invalid
profile cannot leak earlier effects or RNG. Corrected retries match a reference.

## Bounded probes and verification boundary

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-guardian-smoke \
  --batch-size 4096 --players 3 --seed 67
```

This deliberately scripts one enemy turn per environment and cycles all eight
standard groups. Trigger/model/target tickets remain unforced; targets have
Dark Cloud to isolate effects. Hidden state fingerprints/checks results only.
Independent tests separately exercise unforced guardian hit/miss tickets.

- 4,096 completed turns/owner ticks and4,928 commands, no extra owner tick.
- 1,045 activation/model draws/tasks resolved; all40 standard models observed.
- 832 enemy targets/responses, no pending family or limit exit.
- 12,748 incoming HP loss,427 guardian HP gain including102 absorption,
  305 MP gain,753 CP credit,52 full cures/disguise restorations and106 Suns.
- Metadata `93bf575f0bd949b9eed6ee72fe2f91161a94a220d2e2218b0cd991add4048f5c`.
- Replay `62cc41d1964b18f5eef26631332f0d2c8b9b53b346e2cb857ad67c1afaa4ee4b`.

The actual4,096/nine-player CLI probe also passes: all40 models,1,045
activations,4,928 commands and4,096 owner ticks, with987 CP credit due to larger
global recipient pools. These are scripted turns, not full matches, rewards,
learning, strength or official validation. Strict reports cannot be relabeled.

Three additional bounded multi-turn16-episode batches use 2/3/9 players,
standard guardian rosters, known inventory and illness, public observations/
legal choices only. They finish in real endings or explicit truncations within
recorded bounds and conserve owner ticks. This exercises the joined scheduler
under mixed active/finished rows, but still isn't complete full-game acceptance.

Old behavioral fingerprints remain unchanged except complete-pool startup's
new summon legal masks. Metadata fingerprints are explicitly versioned.
Startup still samples all237 held models/41,472 cards; unsupported held-ability
draws fall from5,423 to5,091 (332 Pot/Release draws now have summon routes).
The remaining held abilities are Exchange, Sell, Buy and String of Fate.
Earth/Moon's special producers, five devils, ten phenomena, Apocalypse/Sacrifice,
teams/rewards, hidden-resolution completeness, cap migration and full neural
action/observation/learning gates remain. Trading's amount-interface choice is
still pending. The full objective is active and no readiness flag is loosened.

## Verification results

The two new test modules pass **349 tests**: 288 mechanics/source/transaction
cases and61 strict report/replay/CLI cases. They cover all40 standard effects,
Diamond Axe origin, independent activation/model/target/hit/departure oracles,
all10 summon outcomes and replacement/waiver, money spill/Sun, cures/disguises,
reflections/counters, nested Bow/dead-guardian suppression, nonrecursive ticks,
post-tick limits, late special/hidden failure rollback, reset/owned readonly
views, complete Bible/profile drift, raw invalid inputs, gates and multi-turn
liveness. The three captured redacted snapshots are not admitted as general
official differential proof.

The final non-browser regression command
`pytest --ignore=tests/test_browser_controls.py -o addopts='' -q --tb=short --maxfail=5`
passes **6,760 tests in 120.96 seconds**. Strict mypy passes116 source modules;
Ruff passes `src`/`tests`, and all71 selected full-game Python/CLI files pass
formatting. Native clang-format, offline lock consistency and Git diff checks
pass. `uv` rebuilt/installed native0.69.0; the installed exported identities are
kernel20/observation20/command1/family3 and match the adapter. The actual
default-sized nine-player CLI probe passed the recorded accounting.

No browser fixture or live game/learning run was performed. Pre-existing native
Python import-order/compact-stub findings are outside the source/test lint
scope, not claimed fixed. Git writes remain unavailable under this workspace's
read-only Git boundary; changes are saved locally but not committed. No
alternate Git write path is used. None of these checks proves full-game local
training readiness, official fidelity or candidate strength.
