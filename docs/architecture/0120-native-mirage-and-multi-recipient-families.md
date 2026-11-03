# ADR 0120: Native Mirage and multi-recipient attack families

This records historical v18 results. Current v19 adds multi-card Discard under
[ADR 0121](0121-native-multi-card-discard.md); its metadata/mask fingerprints
are versioned separately rather than relabeling the v18 evidence below.

## Scope and versioned boundary

2026-10-03. This extends the user-approved shared attack queue with Mirage
producers. Native 0.67.0 exports kernel/observation/plan/metadata18,
`integrated-full-game-development-v18`, command1 and attack-family2.
The v2 task payload adds a private per-shot danger flag and recipient-local
remaining-strike count. Existing arenas, checkpoints, live controls and
credentials are unchanged. No live game, browser or learning run is included.

Held execution coverage increases from 230 to **231/237**. Draw weights still
cover every held model; sampling is not execution fidelity. All full-game
learning/readiness, official fidelity and promotion flags remain literal false.
The user authorized provisional rules, not relabeling them official or opening
the live gate. ADR 0097's complete acceptance requirements still apply.

## Saved primary-source contract

Catalog/client pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are saved primary sources, not a new freshness claim. The Mirage builder
revalidates both snapshots and exact raw/Bible contracts before joining them.

Model232 is a miracle with `isPlusAtk=true`, `attackEveryEnemy`, cost5 and
giftRate1. It has no attack or element field. Bible specifies attack all
enemies, cost5MP, gift rate1/500, asset `mirage` and
`/images/items/miracles/mirage.webp`, with no element image. The separate
`area_profiles[N,2]` row is `(232,5)` model/MP-cost; profile SHA is
`84016251775afdf821b5097e03d58311423f6df583c8cddc15aad2bee107d8e5`.

The saved client's selection handler `A.jM.ev` (around9460–9500) permits an
addition only after a non-chance weapon, with the adjacent cost-reducer
exception handled separately. `A.aN.gkN` rejects a zero-ATK addition as a
leader. `A.jM.dt` pays selected net miracle costs before the MP-scaled weapon.
`new A.kr()` around10910 and its callback around11862 exclude selections
containing `attackEveryEnemy` from Fog retargeting. Mirage's numeric effect
does not mix a neutral element into the preceding composition.

These pins establish selection, cost and Fog-exclusion constraints, not server
recipient order or every compound interaction. The local database contains
Mirage in inventory/hand-alignment evidence, but the reviewed search did not
establish a triggered official Mirage family. It is not counted as a verified
use. A web search produced no additional authoritative result.

The combat component advances to schema7 with unchanged profile SHA; its
Mirage/Ascension exclusions now explicitly refer to the separately joined
area/Ascension profiles instead of incorrectly describing them unimplemented.

## Explicit provisional scheduling

- Pay/performance-mark each selected Mirage copy; collapse duplicate area
  flags to one fanout, not one enemy wave per copy.
- Snapshot ascending other living seats at cast. The legacy phase3 target
  command remains a legal placeholder and does not select an area recipient.
- Enqueue the fixed original ATK/element/origin/effect for each recipient.
  Saw Boom Boom enqueues two consecutive strikes per recipient, not one
  complete first wave followed by a complete second wave.
- Drain nested defenses, counters and death shots before older siblings.
  Reflection/bounce affect the current shot, not queued original targets or
  the original turn owner. Costs/cards are used once per cast, not per shot.
- Skip a nominal recipient that subsequently died, and suppress ordinary
  pending shots after source death. Only post-death Bow tasks may have a dead
  source. Later suppression still completes original-cast accounting.
- Complete the original owner's single tick and deferred gifts only after the
  entire family; preserve post-tick death handling and real-ending precedence.
  The hard decision bound may still truncate an unfinished response family.

These are local provisional rules, including recipient order, duplicate-copy
semantics, repeated-strike grouping and compound counter/Bow timing. They do
not establish team targeting or broad official area/chance fidelity.

## Per-shot Pestle/Mortar preparation

Danger routing moves from the cast body into preparation of an original
queued task. Ordinary Pestle casts still produce exactly one task and preserve
prior draws, ownership, damage and replay results. Mirage provisionally emits
one nominal task per enemy, then reroutes each surviving nominal task through
the existing actual-living Mortar/Pestle targeting rule.

The nominal liveness check happens before rerouting. Each shot consumes the
first actual held Mortar of a chosen living owner when present, using uniform
owner priority rather than copy tickets; otherwise sample all living players,
including the source. Initial self-hit or attraction applies direct loss
without defense. Other targets open normal responses. Redirects never reroll
this shot. This precedence and per-generated-shot behavior are provisional.

Cast statistics count original casts; draw/attraction/direct-resolution
statistics count shots. Multiple direct losses and revivals can occur within
one staged command. Incoming damage, area damage and Darkness-finish counts
aggregate every edge instead of collapsing multiple finishes into one boolean.
Sun/final-death hooks and generated queue tasks run before finishing the family.
Existing streams are reused without caller-supplied tickets or extra Fog draws.

## Hidden-safe observations and atomic state

`area_observations[B,3]` is owned/read-only: active flag, displayed-or-revealed
component count, all-enemies flag. Before cast it uses displayed selections;
after cast it reports the revealed family. It carries no future-recipient
count, queue size, true unplayed role, holder or random state. Repeated area
weapon observations use recipient-local strikes, not all private pending
strikes; two otherwise Fog-identical positions with different hidden living
recipient counts produce identical policy views.

Diagnostic-only `area_snapshot[B,8]` records casts, miracle components,
recipient slots, scheduled/resolved/suppressed shots, original incoming HP
loss and Fog bypasses. Reflected original damage counts toward that family;
counter, Bow, recoil, payment, utility and periodic damage are separate.
Lifetime `area_count` and `area_hp_damage` survive resets. Reset clears episode
statistics, task queues/flags and streams; previously returned arrays remain
owned/read-only snapshots. Completed families conserve scheduled = resolved +
suppressed, with the shared queue's existing enqueued/resolved/active accounting.

All casts, queue resumptions, automatic danger draws, hands, resources/statuses,
receipts and counters stage before whole-batch nonthrowing commit. Late hidden
cost/defense or token failures cannot leak earlier area damage or RNG changes.
Corrected commands reproduce the untouched reference. Raw optional area rows
reject empty/malformed inputs, bounds, category mismatches, collisions and
duplicates. Omission preserves unsupported raw fixtures; the source factory
requires the new exported versions and adds the exact pinned profile.

The existing players²×capacity+2 hard queue bound and counter subset bound
remain. Area producers add at most two tasks per other living seat and require
at least two held slots. A bound violation is an atomic development error, not
silent truncation or permission to drop a task.

## Repeatable offline probe

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-area-smoke \
  --batch-size 512 --players 3 --seed 67
```

Six scripted scenarios cover ordinary, repeated, MP-scaled, recoil, waived and
counter families; every source has Fog to check exclusion. Public masks/phases
and fixed public fixture choices drive commands. Hidden state fingerprints and
checks results only; it never selects learner actions.

- 512 casts/resolutions and completed owner turns, 3,499 commands.
- 1,024 recipient slots, 1,196 original shots, 85 counters; 1,281 queued tasks
  resolve, with no pending family, extra owner tick, miss, gift or limit exit.
- 13,632 original incoming HP loss, 15,332 including counters; 2,380 recoil HP.
- 3,410 MP spent, 85 waivers saving425MP, 682 consumed cards/512 miracle uses.
- Metadata `46e6c77d343c46fa5fc8d9c183e09ef9b70ecedb57a2bb53da8c0fc086d61814`.
- Replay `666be2e3e10bcbea4496f8776bfa9e22fb0d1073f129481a2fe0b8ccd18380e9`.

The actual CLI also passes the nine-player512 batch: 4,784 original shots,
85 counters, 54,528 original HP loss, 7,087 commands and 512 owner ticks.
Its recoil fixture loses100 sourceHP on the last recipient, illustrating that
surviving-target recoil does not protect the source from lethal accumulated
loss. This is accounted separately, not relabeled an attack-loss reward.
No fixture is a full-match, learning, strength or official-validation gate.
Strict reports cannot be relabeled into teacher/reward or promotion evidence.

Existing diagnostic behavioral replay hashes remain unchanged, including
Pestle/Mortar and acquisition masks; metadata identities change with the pinned
v18 plan. Complete-pool startup still draws41,472 cards/all237 models, but
unsupported-effect draws fall to5,423 (71 Mirage draws now have an executable
role). Report schemas advance to utility9, acquisition/combat16, chance13,
attack-effect12, counter11, revival10, removal9, economy8, cost7, weapon6,
compound-utility5, danger4 and family2; the new area report starts at1.

## Remaining acceptance work

Six held models remain: Exchange, Sell, Buy, Guardian Pot, String of Fate and
Release. Held coverage excludes virtual Discard/Sacrifice, 42 guardians, five
devils and ten phenomena. Complete trading/event/apocalypse flows, timing,
teams/rewards, unsupported hidden-family handling, local100/client99 cap
migration, complete versioned hidden-safe neural tensors/actions, mixed-game
reset/liveness and learning probes remain. Existing subset gates do not sum to
full-game readiness. Official validation and live promotion remain blocked.
The overall goal remains active. Git writes are still unavailable in this
workspace; changes are saved locally, not committed.

Verification covers 2/3/9-player rosters, all curse masks, independent danger
oracles with dynamic liveness, Mirage duplicates/waivers/undo/element order,
actual-versus-displayed roles, nested counter/Bow/source death, Sun/Hat,
per-recipient payload effects, reset/owned views, late whole-batch rollback,
rehashed raw/Bible drift, strict source/metadata/report gates and CLI parity.

The two new modules pass **292 tests** (217 mechanics/source cases and75
report/CLI cases). The final non-browser regression command
`pytest --ignore=tests/test_browser_controls.py -o addopts='' -q --tb=short --maxfail=5`
passes **5,787 tests in87.57 seconds**. Strict mypy passes112 source modules;
Ruff passes `src`/`tests`; all63 selected full-game Python/CLI files pass
formatting. Native clang-format, offline lock validation and Git diff checks
pass. `uv` rebuilt/installed native0.67.0; the installed exported identities
are kernel18/observation18/command1/family2 and match the source adapter.
The actual nine-player default-sized CLI probe passed the accounting above.

No browser fixture or live game/learning run was performed. Pre-existing native
Python import-order/compact-stub findings are outside the source/test lint
scope and are not claimed fixed. Saved-source and provisional boundaries are
preserved; passing these mechanics tests does not open full-game training.
