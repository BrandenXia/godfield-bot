# ADR 0124: Joined phenomena and bounded native lost-control turns

## Scope and remaining full-game work

2026-10-15. Native0.71.0 is `integrated-full-game-development-v22`, kernel,
observation, plan and metadata22, shared-family5 and command1. String of Fate207
and all10 phenomenon handlers287..296 join the separate development engine.
Held-route coverage is234/237, with Exchange/Sell/Buy still missing. This ledger
does not prove every action/outcome executable: Solar Eclipse can summon an
Earth/Moon guardian whose later activation still rejects atomically. All10
outcomes remain sampled; unsupported dependencies aren't removed or replaced
by no-ops. Standard guardians40/42 and devils5/5 remain separate ledgers.

The original ADR0097 objective and acceptance requirements remain active.
Full trade, Earth/Moon producers, complete Apocalypse/Sacrifice, teams/rewards,
hidden-resolution completeness, cap99 migration and complete neural action,
observation, checkpoint and learning interfaces/probes remain. No local-training,
full-game-readiness, official-fidelity or live-promotion gate is loosened. No
checkpoint, learning job, live bot/game, account or credential is changed.
The human approved preserving six-column commands with versioned phase-specific
numeric amount/purchase choices for trading. Trading itself is not yet joined;
this design approval does not imply action-tensor/checkpoint compatibility.
The human also approved native forced-turn control with zero policy-gradient
weight for confusion.

## Frozen evidence, not an October15 freshness claim

Catalog/client SHA pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The complete ten-row Bible asset/path/detail/element table hashes to
`6c622567813dacf552120f190c8c05308b74f016da4bd2781e107887305a352b`.
Strict API/Bible identities, names, numbers, elements, abilities, guardian
associations, Fate price/gift rate and notes are revalidated from those snapshots.
The five-column `(model,kind,value,element,hit-rate)` table hashes to
`600b2314b68a4809797395afcaa2c711b0e8aa705bcd2bdf5f248ffd49645c55`.
The historical combat/base-utility profiles and hashes are not relabeled.

The saved client supplies several stronger contracts: `aG` filters final-dead
players (`lz`); `setCurseOfEverybody` replaces illness with the received curse;
`confuseEverybody` adds3 to the existing count; original card use decrements old
confusion before subsequent effects; `hP` clears confusion on final death.
`replaceItems` clears performed-miracle portraits and replaces occupied slots
one-for-one. That UI behavior does not prove server redistribution/used flags,
IDs, disguises or random selection, which remain explicitly provisional.

Read-only evidence event111607, run
`23c7b935-5fb7-40bf-863c-05e73ed1c3d5`, source sequence11, contains card use,
`phenomenon`, `setCurseOfEverybody`, then `advanceGF`. Model, numeric curse and
ownership payloads are redacted. It supports order only, not which phenomenon,
numeric effects, sampling, timing generalization or official differential parity.

## Joined global effects and reactions

Fate consumes its actual owned sundry at confirmation, pays no invented price,
and samples all10 uniformly from a dedicated provisional stream. Reservation
reveals no future model or target. Its per-use receipt follows the existing
enabled/disabled deferred acquisition policy; no event artifact becomes a held
inventory card. Raw optional profile omission preserves incomplete fixtures.

- Afterglow sets living players' illness stage2 without infliction/worsening or
  immediate HP loss. The original owner then gets its normal single illness tick.
- Dense Fog adds the Fog flag to living seats and uses existing private views.
- Mushroom adds3 confusion turns; a newly applied duration isn't decremented by
  the current already-used normal Fate. A forced Fate consumes the old turn
  first, then adds3, matching the client event order.
- Tornado assigns HP1 to living seats, not attack damage, Sun or a departure check.
  Later periodic illness/death still uses the shared lifecycle. That damage
  interpretation remains provisional; dead seats are never resurrected.
- Warm Current uniformly selects one living seat, including the caster, for up
  to50HP at the provisional100 cap.
- Gold Mountain uniformly selects a living receiver, zeros all living CP and
  credits the total up to100. Collection/grant/cap loss are separate diagnostics,
  with no invented CP-payment spill into MP/HP. Dead resources remain unchanged.
- Magnetic Storm uniformly shuffles all living held actual models, preserves
  each seat's post-Fate card count, creates fresh native IDs, clears performed
  flags and resamples same-category Dream disguises by recipient. Cross-owner
  setup ID collisions cannot leak into a new hand. Redistribution scope, fresh
  IDs, clearing and refaking remain provisional; no replacement gift/use/cost
  or dead-hand change is fabricated. Tests compare exact native streams.
- Solar Eclipse uses the shared all10 guardian summon/replacement rule for every
  living seat. New guardians participate in the ordinary post-turn wave. That
  compound timing is provisional and unsupported Earth/Moon activation is still
  an explicit atomic development error.
- Tub and Black Hole enter shared family6 with generic origin5. Provisional
  ownership is the Fate caster; Tub uniformly targets any living seat, including
  self, and Black Hole any living enemy. Self Tub still opens a normal response.
  Black Hole uses its pinned75% hit, separate stream and Dark Cloud rule. Typed
  defenses, filters, Super Mirror, redirects, counters, Sun/Bow and final endings
  reuse the joined scheduler without another original-owner tick. Reflections
  preserve the revealed model and don't reroll the hit.

The new route exposed an old response-view issue: utility reservation flags
survived into generated guardian/phenomenon responses. Queue entry now clears
that old reservation, so defenders see the revealed attack and origin correctly.
This isn't a change to hidden future-model disclosure.

## Native bounded control and policy-weight interface

Confused ready rows expose only public choice0 regardless of hidden actual card
roles, and execute one native bounded choice over actual single-card plays,
single-card discards and legal Prayer. There is no selection/toggle/retry loop.
The controller excludes unaffordable/meaningless registered utilities and uses
ordinary cost/consumption/target/Fog/chance/reaction code. Unsupported held trade
leaders stay in its pool and fail atomically when chosen; they aren't silently
omitted. Exact sampling/combinations and ready-only control remain provisional.

Old duration decrements once before the effect, including a new Mushroom event.
Final death clears duration; a successful Sun retains it. Defense responses remain
voluntary even if their actor still has confusion. Trusted `seed_confusion` is
setup-only, bounded, owner/duplicate checked and whole-batch atomic, not a
learner action. Empty/setup/finished policy masks remain safe.

`policy_gradient_masks[B,1]` is false for forced ready/setup/finished rows, true
for voluntary interactive phases. Capture it **before** the command. The adapter
`full_game_policy_gradient_weights` validates the public command context and
returns readonly float32 weights in command order, with forced rows0 and voluntary
rows1. It does not advance state, assign zero reward/value targets or implement
the complete trainer. Future learning still needs learner-seat/episode/recurrent
handling and complete environment acceptance; those flags stay false.

Policy `control_observations[B,9,4]` is cyclic seat/present/visible/remaining;
Fog hides other seats. Revealed-only `phenomenon_observations[B,4]` contains
active/model/current-source/target in an active family6, never a future queue,
victim, model, RNG or diagnostic identity. Readonly episode diagnostics are
`confusion_snapshot[B,17]` (nine seat counts plus eight controller counters),
`phenomenon_snapshot[B,23]` and `phenomenon_model_counts[B,10]`. Reset clears
new state/streams/counters; old returned snapshots remain owned and unchanged.
All resources, global hands/IDs/disguises, effects, ownership, native draws,
death/revival/reaction tasks and counters stage before nonthrowing batch commit.

Native event/control logic is separated into `full_game_events.cpp`. A shared
inline bounded SplitMix helper avoids duplicating random implementations;
positive-bound behavior is unchanged and a zero pool now fails explicitly.
New illness-seed XOR streams: model `0xa458fea3f4933d7e`, target
`0x0d95748f728eb658`, hit `0x718bcd5882154aee`, shuffle
`0x7b54a41dc25a59b5`, disguise `0x9c30d5392af26013`, forced action
`0xc5d1b023286085f0`, forced target `0xca417918b8db38ef`.

## Uniform first-turn probe with failures retained

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-phenomenon-smoke \
  --batch-size 512 --players 3 --seed 67
```

Fixed Fate/armor/miracle/Sun hands and50HP/99CP/Dark Cloud isolate the routes.
Model/target/guardian draws remain native and unforced. The script uses public
Fate reservation/confirmation and forgiven responses; true diagnostics only
check and fingerprint results. When a whole batch atomically rejects a known
Earth/Moon dependency, each unchanged public command is retried once to identify
the failing rows. Those remain reported, are never retried indefinitely, and
are not reset, filtered by hidden model or counted successful. Unknown errors
still stop the command. Before-images are owned snapshots captured once per
failed batch; only actual failed rows query diagnostics again, avoiding an
unnecessary all-rows-squared copy/choice-mask cost.

Default512/three-seat/67 observes all10 committed models,507 completed first
turns/owner ticks,5 dependency failures (169,207,289,360,454),1,133 commands,
4,750 phenomenon incoming HP loss and4,839 total incoming HP loss. Model counts:
`61,44,53,55,50,45,53,55,36,55`. Metadata SHA
`90d1b1250d70ba02f1d8b6ce2441ea7485a9fde90bd34709d081465d75ddb211`, replay
`24f79a71f7b8744ebcec089749e87f00dfe1cd70a86e6adea09a8f68ed87385a`.

The actual4096/nine-seat probe observes all10 models:3,957 completed first
turns/owner ticks,139 dependency failures,9,213 commands,40,700 phenomenon HP
loss and43,976 total incoming loss. Counts:
`419,392,399,407,411,403,440,411,402,273`. Metadata
`4998c540e2886a6c362843f71176c501240cc8e6067d26789189a5009e1dde1c`, replay
`5f6acd28c64278c27a2d2bb73a7c2888594c354d77d7e34526c3cc8ee9a8703f`.
Completed rows have no pending family, extra-owner tick or limit truncation.
These are first turns, not full matches, strength, reward/teacher data or complete
episode/learning evidence. Dependency failures are a reason readiness is false.

## Regression and verification boundary

The two new modules pass238 focused tests:173 mechanics/control/source/atomic
cases and65 strict report/CLI/performance cases. They cover all10 handlers,
independent model/target/hit/shuffle/disguise oracles, living/dead scope, disease
assignment, caps, reflection and public response views, source/actual controller
roles, duration stacking/death/Sun, pre-step weights, reset/readonly views,
complete-source drift, bounds, rollback and full-pool dependency reporting.
The final non-browser suite passes **7,174 tests in143.51 seconds** against the
rebuilt native0.71.0 engine. Ruff passes `src`/`tests`; strict mypy passes120 source
modules; all79 selected full-game Python/CLI files pass formatting. Native
clang-format checks cover both implementation files, the engine header and
shared random helper. Offline lock consistency and Git diff checks pass. The
installed kernel22/observation22/command1/family5 identities match the adapter.
The optimized actual4096/nine-player CLI run reproduces the exact report/replay
above, including all139 dependency failures rather than an artificial clean pass.

The old16 probes retain behavioral fingerprints except startup's new Fate mask
and the complete-pool devil probe's newly executable Fate choices. Masking only
Fate's new startup choice reproduces v21 replay
`6a103e140464bff8f4fbe49fc6898dd31d4f8eeed687e7b09153bf6f8f201d97`.
Complete-pool draws remain41,472/all237 models; unsupported held-ability draws
drop by the63 Fate draws, from5,091 to5,028, exactly the trade draws. The devil
probe remains999 appearances/4,096 ticks; it now takes14,600 commands rather
than14,620, with1,645 rather than1,647 theft-eligible cards due to real Fate
turns. All source/layout/report identities are explicitly versioned; no stale
report is relabeled full-game ready. No browser fixture, live game or learning
job is run. Git remains read-only; changes are saved locally, not committed.
