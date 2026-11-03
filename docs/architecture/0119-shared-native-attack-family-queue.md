# ADR 0119: Shared native attack-family queue and Ascension Bow

This records the historical v17/family1 implementation and verification.
[ADR 0120](0120-native-mirage-and-multi-recipient-families.md) advances the
current engine to v18/family2 with Mirage producers; the results below remain
versioned v17 evidence, not current metadata hashes or readiness claims.

## Accepted design and scope

2026-10-03. The user approved one shared, versioned queue for post-death Bow
shots and future multi-recipient attacks, with provisional recipient order and
unobserved timing, and live promotion blocked. Native 0.66.0 implements that
queue as version1 in `integrated-full-game-development-v17`.
Kernel/observation/plan/metadata advance to 17; command remains 1.
Original response-bearing shots, repeated strikes and armor counter payloads
now use the same scheduler instead of a counter-only stack plus a special
second-strike continuation. The separate Hat component is ADR 0118.

Ascension adds one held model, raising execution coverage to 230/237. This is
not a complete game engine, verified official fidelity or training readiness.
No checkpoint migration, existing-arena rewrite, API revision, credential,
browser/live control change, live game or learning job is included.

## Saved primary sources

Catalog/client SHA pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are saved primary sources, not a new Oct 3 freshness claim. The complete
source builder revalidates snapshots, exact raw model112, Bible text/assets
and the strict profile hash, rejecting even rehashed source drift.

Ascension Bow is Light, base 25%ATK1, `attackDyingly`, ability value30;
Bible specifies 75%ATK30 at Ascension. Price10 is not an MP use cost. Profile
`(112,1,25,30,75,5)` is model/base-ATK/base-rate/dying-ATK/dying-rate/element;
SHA `d20664fab4740f69ea2a039a502dba71bbb8bd0744e0c47563edec271b3b7264`.
Ascension is death, not an invented low-HP threshold or Heaven disease stage.

The pinned client's `attackDyingly` handler at 11680–11734 displays the
event's owned weapon and payload before the subsequent `endGame` handler.
Local primary evidence confirms this ordering: private official run
`23c7b935-5fb7-40bf-863c-05e73ed1c3d5`, evidence event259, field19,
source sequence16, two players/self2, contains in order:
`useDefenseItems`, `dealDamage`, `die`, `attackDyingly`, `miss`, `endGame`.
Its redacted payload does not establish multiplayer order, copy handling,
Sun priority, every death cause or the full random generator. The existing
pinned API `Game.is_over` also explicitly waits while attacks/dying players
remain, avoiding premature winner detection. Secondary descriptions are not
used as verified rules.

## Queue contract

Every queued payload fixes source, target, ATK, element, origin, rate and
optional generated effect/basis. Kinds are counter1, original-recipient2,
post-death3. The private LIFO scheduler preserves explicit sibling order via
reverse insertion; nested reactions precede older siblings. Two-strike
weapons preserve their original composed payload/target and record actual
completed/suppressed strikes without another use, charge or owner tick.

The ordinary chance scheduler retains its existing explicitly provisional
one-living-enemy target-before-hit rule, including Bow's base cast. This step
does not silently claim to correct all official area/chance attacks. Future
multi-recipient producers can enqueue original-recipient payloads, but those
producers and their verified targeting semantics are still outstanding.

The final-death hook runs only on positive-to-zero HP transitions. It first
resolves an actual owned Sun, leaving a revived owner and held Bows intact.
After no revival it registers the final-dead owner once per episode. Actual
remaining held Bows are consumed once in held-copy order, regardless of fake
identity; a merely displayed Bow cannot trigger. Dead setup/idle/deal state,
nonlethal HP loss and already-registered death do not trigger.

Provisional Bow behavior emits a separate 75%ATK30 Light weapon-origin shot
for each other living seat, in ascending seat order for each held copy.
Recipients dying before their turn are skipped. A dedicated native episode
stream (illness-seed XOR `0xc0ac29b7c97c50dd`) samples per recipient; target
Dark Cloud guarantees a hit without consuming a ticket. Hit shots open fresh
ordinary defenses/filter/special/counter handling. Misses resolve without
response. Dead sources are permitted only for post-death tasks; normal queued
attacks and counters still require living sources and targets.

Reflection toward an already-dead source consumes its normal response and
resolves without entering a dead player's defense or resurrecting that player.
Ordinary block/filter/reflect/bounce rules and unchanged redirect hit semantics
apply. Neptune's self-targeted counter can resolve; counters aimed at the dead
source are suppressed normally. Their used-card receipts remain accounted.

Depth is bounded by players²×capacity+2; the counter subset separately retains
players×capacity. Consuming all actual Bows, registering each final death once,
deferring gifts and disallowing dead resurrection bound death families.
Existing defense/attack toggle and global decision limits remain enforced.
Bound violations reject the entire command batch, never silently drop work.

## Tick, ending and receipt ordering

1. Resolve the current shot, immediate HP/effect/Sun/self-effects, and enqueue
   resulting death tasks and counters. Newly added counters resolve ahead of
   pending death tasks/siblings; this combined priority remains provisional.
2. Drain every queued original recipient, nested reaction and death family.
   Skip no pending shot merely because only one player currently lives.
3. Apply the original owner's illness tick once. A final death caused by that
   periodic effect or worsening can enqueue Bows; retain owner/tick context
   while those tasks resolve, without applying a second tick.
4. With no pending work, check real winner/all-dead endings before the turn
   limit, advance to a living owner otherwise, and settle deferred gifts.

Attack, infliction, CP→MP→HP payment, recoil, periodic/worsening, compound Herb
and direct Tear damage share the same HP-zero hook. Defender responses never
tick that defender. A post-tick family is not prematurely cut off just because
the turn count reached its limit; the hard decision limit still truncates an
unfinished response and is correctly labeled decision-limit, not turn-limit.
Dead owners and terminal/truncated states suppress receipts. No per-shot Bow
recipient gift is invented; consumed Bows earn only the existing provisional
per-use due. Reset clears queue/active/tick/death registration and reseeds all
streams while preserving lifetime counters and previously returned views.

All hands, queues, resources/statuses, RNG, generated identities, receipts,
ticks and counters stage for the entire command batch. Allocation, validation
and random draws precede the nonthrowing commit. A late stale/duplicate/hidden
invalid command rolls everything back; corrected retries are reproducible.

## Observable but hidden-safe

`FULL_GAME_ATTACK_FAMILY_SCHEMA_VERSION=1` is exported and factory-checked.
Optional `ascension_profiles[N,6]` accepts validated weapon rows; omitted
profiles preserve unsupported Bow fixtures. Empty/malformed profiles,
categories, bounds, role collisions and duplicates are rejected.

Owned read-only diagnostic `attack_family_snapshot[B,16]` records enqueued,
started, resolved, suppressed, missed, peak depth, final death edges, consumed
Bows, death recipients/hits/misses/suppressions/HP loss, queued count, active
kind and owner-already-ticked. At every command boundary:
enqueued = resolved + suppressed + queued + active, and started = resolved +
active. Active is one iff active kind is nonzero. Misses count as resolved.
The existing counter diagnostic's final column still counts counters only,
not unrelated pending original/Bow tasks.

Lifetime `ascension_count` is consumed Bows, not targets;
`ascension_hp_damage` is actual resulting incoming attack HP loss, not utility,
payment, recoil or periodic loss. Original cast/resolution and counter counts
remain separate. Displayed passive view adds kind3/value30; no hidden real
owner, future recipient, ticket or pending private queue is a policy feature.
Metadata validates layouts and keeps readiness/fidelity/promotion literal false.

## Repeatable bounded probe

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-attack-family-smoke \
  --batch-size 512 --players 3 --seed 67
```

Six scenarios exercise final death, Sun priority, periodic death, nested death,
Hat defense and second-strike suppression. Public phase/masks and fixed public
fixture choices drive commands; hidden state only fingerprints/checks outcomes.
Targets intentionally have Dark Cloud to isolate scheduling; separate tests
check independent unforced hit/miss oracles.

- 512 completed turns, 2,900 commands, 427 original casts/resolutions.
- 1,449 queued tasks: 1,364 resolved, 85 dead-target repeat suppressions,
  no pending task/active response at completion and zero limit truncations.
- 511 actual Bows consumed; 937 post-death recipients; 24,455 Bow HP loss.
- 86 Sun revivals, 85 Hat redraws/170 replacement cards, 1,194 consumed cards.
- Every original owner ticks once; no other-owner ticks, gifts or MP charge.
- 85 scripted real terminal endings and 427 ready episodes, not 512 full games.
- Metadata `c6e20a3f3de59c7fe8155c4061d9590729b2e4368b96458c50cea6294e7b0001`.
- Replay `23e07588983ef124019509494334e0904483276500fb9e9a9c995b00fc93b824`.

These reports cannot be relabeled teacher/reward data, local training, official
validation or strength evidence. Existing probes preserve all behavioral replay
hashes except acquisition legal masks; metadata identities are versioned.
Complete-pool startup still draws all 237 models, with 5,494/41,472 unsupported
draws (83 Hat and 72 Bow draws now have implemented roles).
Report versions advance to utility 8, acquisition/combat 15, chance 12,
attack-effect 11, counter 10, revival 9, removal 8, economy 7, cost 6, weapon 5,
compound-utility 4 and danger 3; the new family report starts at 1.

## Remaining work and verification boundary

Seven held models remain: Exchange, Sell, Buy, Guardian Pot, String of Fate,
Mirage and Release. Held accounting excludes virtual Discard/Sacrifice,
42 guardians, five devils and ten phenomena. Trading and event/apocalypse
timing, teams/rewards, unsupported hidden-family handling, the local100/client99
cap migration, a complete hidden-safe neural interface and mixed-episode
learning/reset/liveness probes still block full-game readiness. Existing subset
gates are not aggregated or relabeled as full-game proof. The overall goal is
active; official validation and live promotion remain blocked.

Focused mechanics/report tests cover independent tickets across player counts,
all documented curse combinations, base Bow chance, actual/fake ownership,
duplicate copies and zero recipients, nested death, Sun priority, every added
HP-zero path, post-tick limits, dead-source reflection/counters, repeated
strikes, rollback of queue-creating and queue-resuming batches, reset/owned
views, exact source drift, strict metadata/report gates and CLI parity.
The three new modules pass **436 tests** (126 Hat, 238 family mechanics and
72 family report/CLI cases). The final non-browser regression command
`pytest --ignore=tests/test_browser_controls.py -o addopts='' -q --tb=short --maxfail=5`
passes **5,495 tests in 84.02 seconds**. Strict mypy passes all 110 source
modules; Ruff passes `src`/`tests`, all 59 selected full-game Python/CLI files
pass formatting, native clang-format passes, and `uv lock --check --offline`
and `git diff --check` pass. The actual default CLI probe also passed with the
recorded metadata/replay identities and accounting. Native 0.66.0 rebuilt and
installed successfully through `uv`; its exported kernel 17, command 1 and
family 1 identities match the source adapter.

No browser fixture or live game/learning run was performed. Pre-existing native
Python import-order/compact-stub lint findings are not claimed fixed or included
in the source/test lint result. Older behavioral replay hashes remain unchanged
apart from complete-pool startup legal masks; metadata changes record the new
versioned plan rather than relabeling old evidence.

Git metadata writes remain unavailable after the prior approval-review failure.
No retry or alternate write path is used. Changes are saved locally, not
committed; normal commits remain required when Git writes become available.
