# ADR 0107: Joined chance attacks and automatic targets

## Status and scope

2026-10-01, native 0.55.0, `integrated-full-game-development-v6`. This follows
the committed special-defense milestone `235c1b3`. It integrates chance into
the same authoritative native inventory/resources/turn/defense transaction,
not a second scheduler or caller-sampled roll. The preceding goal turn was
progress; the complete full-game training objective remains active.

Legacy models, arenas, live accounts/controllers and upstream API revision are
unchanged. No live game was run for this milestone. Full-game learning admission,
official fidelity and promotion stay false. This is not all chance or all game
mechanics: it adds the probability/target primitive used by further effects.

## Source checks and exact restrictions

The Oct 1 API catalog and Sep 20 Bible keep ADR 0104's source pins. Existing
Bible parsers identify fourteen effect-free chance weapons, Jinn's Rocking
Horse (75%ATK8 and Wood DEF6), and six percentage-hit miracles. The full-game
builder independently cross-checks exact API identity, category, ATK/DEF, hit
rate, cost, element image, complete description, price and gift suffix. No
status or absorption description is discarded to fit the plain family.

The chance rows `[model, percent]` have SHA-256
`c37e6b17aad95ba7cc59835c9f7bf3c1eb69d824cd58133891014696f4ecc096`.
The complete combat plan now fingerprints leader/armor/addition/special/chance
rows together:
`8c26c1430223f2034bdf09e464bad64765944e26ea3f1bf825ff6a81441d5f62`.
There are 72 leaders, 64 numeric defenses, 29 additions and 23 special rows,
representing 163 distinct combat models plus twelve utilities/cures = **175**.
Jinn overlaps leader/defense roles. The unchanged 237-model gift pool still
contains 62 unimplemented held effects; registration is not execution.

The pinned client's `aN.glk` returns false for percentage-hit cards (`w > 0`),
so they are not player-targeted. Selection `ev` accepts ordinary additions only
when the first item is a weapon with `w === 0`. Therefore the joined engine
does **not** copy ADR 0033's older arena booster allowance for chance weapons.
This is a deliberate source-based correction in the separate engine; old
arena trajectories/checkpoints are preserved. Chance miracles remain reusable.

Fog Fan (97), Vine Shoot (98), Ascension Bow (112) and Flash (224) remain
unsupported pending status-on-damage, absorption and alternate distribution
state integration. Guardian/phenomenon chance attacks also require their proper
lifecycles, not admission as held cards.

## Joined decision and provisional timing contract

Ready slot+1 reserves the displayed leader and enters selection phase 2. A
chance leader permits only choice 0 (confirm) or undoing its own selection.
Confirmation casts immediately without entering player-target phase 3.
The actual effect/cost/targeting mode is validated before native mutation commits.
Displayed chance versus actual fixed, or displayed fixed versus actual chance,
fails atomically with a targeting-mode error. General Dream dispatch semantics
remain unverified and must be integrated before full learning admission; no
secret target is fabricated to force a successful command.

The staged cast pays actual MP, consumes an ordinary card or moves a used
miracle to the tail, records its deferred receipt and samples one native hit
roll. On miss, it resolves with zero attack damage and no defender response,
then ticks the original owner once and advances the turn. Owner illness can
cause a real ending, which still takes precedence over limits. A hit samples
one uniformly selected living enemy (excluding dead seats and the source),
then enters phase 4 with the fixed ATK/element/origin and already-hit state.
Chance target distribution and universal cast/receipt/owner-tick timing are
**provisional**, not established server randomness or ordering.

Hit rolls and automatic targets have separate SplitMix streams, themselves
separate from Fog targeting, bounce, illness, gift models and disguises. Both
use the native 16-attempt bounded rejection sampler and epoch reset seed. There
are no caller roll tickets or chance target choices. Defense, blocks and
repeated reflection/bounce responses preserve the successful attack and do
not reroll. Darkness still requires positive final post-defense damage. Jinn
contributes fixed DEF6 when defending and never samples chance in that role.

All state, streams, counters, hands, costs, leases and queued receipts stage
for the full command batch before committing any environment. Selection/cancel
cycles still reach the actual episode decision limit; probability does not
invent completed turns or extra defense choices. Receipts are suppressed on
terminal/truncation boundaries exactly as in the preceding development rules.

## Versioned observability and tests

Kernel, observation, plan and metadata schemas advance to 6; command schema
remains 1 and implemented phases remain 0,1,2,3,4,12,13. The source factory
supplies the complete chance map. Raw unit fixtures may omit it to isolate
fixed arithmetic but receive no full-game learning metadata. Numeric weapon
defense rows require a complementary leader profile; Jinn is source-pinned,
not an invented DEF conversion from ATK.

`chance_observations[B,4]` is an owned read-only public copy containing active,
displayed hit rate, already-hit and automatic-target flags. It uses true
resolved rate only after a committed cast and exposes no future RNG state.
`chance_snapshot[B,3]` is per-epoch diagnostic casts/hits/misses; reset clears
it while lifetime counters remain. Plan/report fidelity and promotion fields
remain literal false and cannot be forged to widen admission.

Tests execute 128 environments for every new chance model, comparing exact
native rolls and targets against an independent SplitMix implementation. They
cover both outcomes, no additions/player targets, MP/consumption/retention,
deferred receipts, original-owner tick, dead/source exclusion, reset streams,
Fog/acquisition/illness independence, second miracle use, terminal precedence,
decision limits, hidden mode/effect/cost failures, fixed Jinn defense, special
responses, repeated reflection without reroll, Darkness fully blocked, late
batch rollback and strict source/metadata/report rejection.

## Reproducible offline evidence

`simulation full-game-chance-smoke` uses the source factory, one chance card
per environment, native confirmation and explicit forgive on hits. Its default
504 environments cycle all 21 models 24 times: **309 hits, 195 misses, 1,317
commands, 504 completed turns**, 2,783 attack HP removed, 1,440 MP paid, 360
ordinary cards consumed and 144 retained miracle uses. All 504 episodes remain
ready after one turn; these are not 504 wins or full games. The one-turn report
is schema 1; admission to learning/reward/full-game/promotion remains false.
Metadata SHA:
`160b6ece6d1875d802c7f0c3338954683341f88765fcf93312e7cb48a00ac367`;
replay SHA:
`b8351112be01aee9dba2c26b3a9dc9e864914eef72fe56027ab9de6b03d51103`.

The complete-pool startup probe remains zero gameplay commands/zero completed
games. It draws 41,472 cards, observes all 237 models, and reports 10,348 draws
without integrated effects and zero initial actors without implemented choices.
This does not establish absence of later unsupported hands or effects.
Schema 4 metadata SHA:
`5392c826965931e6a987ac07834bc5b74e4d4bd77fdac9b8a27bb915f72aeceb`;
replay SHA:
`3f72d6af0aae8da9cd0c22661f722083234fb1866c23396759b328ed72ed91f1`.

The fixed-combination combat probe retains 32 winners / 179 turns / 693 commands
without truncation or unfinished games. It contains no chance cards and is not
relabeled as chance or strength evidence. Schema 4 metadata SHA:
`55c087c8777469f3ec7ab05033e826ccbeaf74b138b4b5a7c843b91761f8c3aa`;
replay SHA:
`eacf95e2c633e8a093f7d5b8abd0efb1af059adb9c2a755cdf15903cfe47ed27`.
The utility/cure probe keeps ADR 0102's replay; current metadata SHA is
`20800e5dc798acf85857cde6ed195bab32b1e9466992f0fca9d2283f19f6c70e`.

Final verification: 3,507 non-browser tests and two offline Chromium fixtures
pass (3,509 total), including 91 new chance/probe tests and the unchanged
legacy 0.46 trajectory golden. Ruff passes across source/tests; mypy passes
all 91 source modules. Changed Python formatting, native source/header
formatting, frozen offline lockfile and whitespace checks pass. The lockfile
changes only the local native release, not upstream API dependencies.

## Remaining full objective

Next: damage-triggered effects and their source/target ownership, counters,
filtering/cost cuts and multi-recipient attacks. Utility/status targets, trade
economy, events, guardians, removal/revival, Apocalypse, teams and complete
action/observation/reward/neural rollout interfaces still require joined native
implementation and learning/held-out official replay checks. Full-game readiness
and live promotion are separate gates and remain unachieved.
