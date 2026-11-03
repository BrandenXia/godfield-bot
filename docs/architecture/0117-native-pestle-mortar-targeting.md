# ADR 0117: Native Pestle/Mortar targeting

## Status and scope

2026-10-03, native 0.64.0, `integrated-full-game-development-v15`.
Kernel, observation, plan and metadata advance to 15; command schema stays 1.
New danger-plan schema 1 adds Dangerous Pestle and Dangerous Mortar, raising
joined execution coverage from 226 to **228/237 held models**. Other component
profile identities, existing arenas, neural checkpoints, API revision, account
credentials and live controls are unchanged. No live game or learning job was
launched. Full-game training readiness, official fidelity and promotion remain
literal false.

## Pinned sources and evidence

Catalog/client SHA pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are saved primary sources, not a new Oct 3 freshness claim. The builder
revalidates complete snapshots, exact raw rows, Bible text/images/elements
and the strict existing random-weapon parser; rehashed catalog drift fails.

| Model | Pinned role | Joined profile |
| --- | --- | --- |
| 94 Dangerous Pestle | Light ATK30, `danger`, attack somebody | `(94,1,30,5)` |
| 209 Dangerous Mortar | passive `attractDanger`, 99 damage by a Pestle | `(209,2,99,0)` |

Profile SHA:
`ebfd6728c84580fc20ff3729bd39f742e01d4f6b93cdbc9a732bfa788e0540b3`.
Catalog price is not an MP/CP use charge. The saved client `A.aN.gkN` excludes
`attractDanger` from manual leaders and discard selection also excludes it.
`glk` still requests weapon target preview. `A.jM.ev` admits weapon additions
when hitRate is zero, including Pestle; `A.tw` defines their ordered arithmetic
and the adjacent cutCost exception. The `useAttackItems` Fog branch explicitly
excludes `danger`. The `danger`/`attractDanger` event handlers animate outcomes
but do not disclose server target weights or fixed-damage/consumption timing.

Existing ADR 0038 records private-API target override and browser self-hit
without a response. Read-only run inspection confirms private run
`25338ece-15b2-4d5c-86b3-c774ae7bca0b`, event 1754, acknowledges requested
`use:8:94:4`, while event 1756 reports source seat3 and actual target seat2.
Browser run `57960f7d-b634-4f30-b890-cde23e6f48a2` displays ATK30 with the
source at HP9, then the source at HP0 (events 221/228/232). This verifies the
base self outcome, not composed self-hit timing or multiplayer probabilities.
No captured Mortar event in the local evidence table verifies its timing.
Older arena restrictions on boosters/reflectors were conservative evidence
boundaries, not proof that the general source rules forbid them.

## Explicit provisional resolution

Following the approved provisional-rule layer, the separate engine uses:

- No actual living Mortar owner: uniform selection among all living seats,
  including the attacker, regardless of requested target or Fog.
- Actual living Mortar owners: prioritize them, sample uniformly by owner
  rather than copy, and consume that owner's first actual held Mortar.
- Attracted damage: fixed direct loss of up to 99 HP, no response phase,
  numeric mitigation, counter choice or composed ATK99 interpretation.
- Initial self target without Mortar: resolve the composed attack immediately;
  the no-response base outcome is observed, broader composition is provisional.
- Normal enemy target: use normal Light/numeric compatibility, filter prefixes,
  applicable specials, reflections, bounce and bounded counter families.
- Attraction/random targeting happens only at the initial cast. A redirect to
  the source opens ordinary defense and never re-samples attraction.

Multiple Mortar copies do not provide extra weight; only one is consumed.
Dead holders are excluded. Displayed disguises never substitute for actual
ownership; a fake Mortar does not attract and a real Mortar disguised as Sun
still does. Survivors retain flags/fakes/order. Raw profiles can be omitted;
explicit malformed/empty profiles, duplicates, categories/bounds and role
collisions are rejected. The local HP100 cap means fixed99 may leave HP1;
this gap from the pinned client's 99 cap remains declared and unverified.

Costs and composition are resolved before the target draw. One actual Pestle
and each selected addon are used once, miracles are retained/performed, and
adjacent waiver accounting is unchanged. Automatic lethal loss invokes the
same actual owned Sun hook as incoming attacks, before final endings. All
uses, including Mortar and Amulet, defer their provisional receipts until the
single original-owner tick. Dead owners and terminal/limit states suppress
their receipts. Defender damage does not tick the defender. Real endings take
precedence over limits; an unfinished normal response may truncate without
an invented resolution/tick or gift.

Random streams derive from the episode illness seed:
`0xa4093822299f31d0` XOR for ordinary Pestle targeting and
`0x082efa98ec4e6c89` XOR for multiple Mortar owners. Singleton attraction needs
no ticket. The existing bounded SplitMix rejection sampler is reused.
Reservation and cancellation never sample; callers cannot supply tickets.
Every draw, cost, inventory mutation, revival, queue, tick and counter stages
for the entire command batch before the allocation-free/nonthrowing commit.
Late rejected rows preserve all environments; corrected retries match fresh
independent runs.

## Observation and diagnostic boundaries

Owned read-only policy `danger_observations[B,3]` is active, base ATK and base
element, using displayed identity before casting and revealed family context
through subsequent response/counter phases. It reveals no hidden holders,
future random target or ticket. `passive_observations[B,capacity,2]` retains
its shape, adding displayed Mortar code2/value99 alongside Sun code1/value10.
Metadata renames the second field to `displayed_value`; neither card becomes
a manual ready-phase use. Terminal/setup views are empty.

Owned read-only diagnostic `danger_snapshot[B,8]` is casts, ordinary target
draws, self targets, attractions, multi-owner draws, attracted self targets,
automatic resolutions, and automatic HP loss. Automatic resolutions equal
self targets plus attractions minus attracted self targets. They are not
learner inputs. Lifetime `danger_count`/`automatic_danger_hp_damage` accumulate;
epoch reset clears rows and reseeds streams without resetting lifetime totals.
Existing HP damage continues to include automatic weapon/direct Mortar loss;
it is not utility or periodic illness damage.

## Repeatable local probe

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-danger-smoke \
  --batch-size 512 --players 3 --seed 67
```

Eight scripted cases cover ordinary random targets, low-HP source with Sun,
surviving enemy Mortar, enemy lethal Mortar with/without Sun, source lethal
Mortar with/without Sun and two competing living owners. Commands read public
phase/masks; true state fingerprints/verifies outcomes only.

- 512 completed turns/attacks/resolutions and original-owner ticks.
- 1,631 commands, 95 ordinary defense responses, zero limit truncations.
- 128 random targets, including 33 source targets; 384 attractions, including
  157 source targets, and 64 multi-owner draws (29 source/35 enemy).
- 417 automatic resolutions, 13,425 automatic HP lost; total loss 16,275.
- 145 owned revivals, 1,041 consumed cards; no gifts, MP cost or counters in
  this probe. Separate integration tests exercise those response families.
- Three-player cases remain active after 64 source/64 enemy deaths; two-player
  variants record the corresponding real terminal endings.
- Metadata: `0d64f878a9ab260c002b670a0fe195f5096c9f04041366a9c9bd27f356c3b6b0`.
- Replay: `3ac3b9d9d6249d35a3051e2a6afb32dc7db46be28ff345ec6c2cda23b2c15235`.

These are scripted turns, not 512 complete games, reward/teacher data, learning
progress, strength results or official replay validation. Acquisition startup
still draws all 237 held models with the unchanged distribution; newly joined
Pestle/Mortar reduce unsupported draws by 66+77 to **5,649/41,472**. Its public
legal masks/replay hash change; established older probe trajectories remain
unchanged, with versioned metadata updated to include this ruleset.

## Remaining full-game work

Nine held models remain: Exchange, Sell, Buy, Ascension Bow, Dreaming Hat,
Guardian Pot, String of Fate, Mirage and Release. Held-model accounting excludes
virtual Discard/Sacrifice, 42 guardians, five devils and ten phenomena. Trading
actions, guardian/event/apocalypse timing, teams/rewards, unsupported hidden
family resolution, the cap99 migration, a complete hidden-safe tensor interface
and mixed-episode local learning/reset/liveness probes still block full-game
readiness. Existing subset readiness reports are not relabeled or aggregated
as complete game proof. The overall goal remains active.

## Verification

The native package rebuilt and installed successfully with `uv`, version
0.64.0, kernel/observation schema 15, command 1 and the v15 ruleset identity.
The two new test modules contribute **225 passing tests**, including independent
target-ticket oracles across 2/3/9 seats, all documented curse combinations,
owner-vs-copy weights, actual/fake passives, HP edges/revival/gift suppression,
composition and waivers, normal Light filters/reflection/counters, cancellation,
reset, limits, late-row rollback/retry, source drift and report/CLI boundaries.

The final non-browser regression command
`pytest --ignore=tests/test_browser_controls.py -o addopts='' -q --tb=short --maxfail=5`
passed **5,059 tests in 76.28 seconds**, with the current source/metadata/replay
goldens. No browser fixture, live game or learning run was performed. Strict
mypy passed all 107 source modules; Ruff passed `src`/`tests`; all 53 selected
full-game Python/CLI files passed format checks. Native clang-format,
`uv lock --check --offline` and `git diff --check` also passed. Known pre-existing
compact native-stub/import lint findings are not claimed fixed or included in
the source/test lint result.

Older behavioral replay hashes remain unchanged except complete-pool startup,
whose legal masks change with Pestle availability. Existing reports advance to
utility 6, acquisition/combat 13, chance 10, attack-effect 9, counter 8, revival
7, removal 6, economy 5, cost 4, weapon 3 and compound utility 2. The new danger
report starts at 1. Metadata hashes change to record the full pinned v15 plan;
unchanged legacy trajectory tests still pass. None of these reports is evidence
of complete-game learning or live candidate promotion.

Git metadata writes remain unavailable after the earlier approval-review
usage-limit failure. No retry or alternate write path is used. Changes are
saved locally, not committed; normal commits remain required when Git writes
are available.
