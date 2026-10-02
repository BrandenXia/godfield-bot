# ADR 0108: Joined attack effects and target-first chance resolution

## Status and scope

2026-10-01, native 0.56.0, `integrated-full-game-development-v7`, following
`2f7723e`. This milestone adds 20 held-card effects to the separate authoritative
engine: four HP absorbers, eleven damage curses, and five direct curse miracles.
It also corrects the prior chance primitive for Dark Cloud. The complete
full-game training goal remains active, not achieved.

Existing arenas, checkpoints, live accounts/controllers and the upstream API
revision are unchanged. No live game was joined or played. Full-game learning,
official fidelity and live promotion remain literal false. The approved
automatic oldest-held eviction at an explicit provisional 18-card cap is
preserved; neither its victim rule nor the cap is declared official behavior.

## Pinned source and evidence boundaries

Sources remain the Oct 1 API catalog
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and the Sep 20 Bible/saved client
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The builder cross-checks each new identity, category, complete description,
element image, ATK, percentage, ability/curse, price or cost, and gift weight.
It does not strip an effect to fit a plain attack parser.

New effect rows `[model, kind, value]` are:

| Kind | Meaning | Models |
| --- | --- | --- |
| 1 | HP absorption; value zero | 27,45,98,216 |
| 2 | Mask bit on positive damage | 36,41,70,72,80,97,224 |
| 3 | Illness stage on positive damage | 30,33,48,62 |
| 4 | Direct zero-ATK mask curse | 221,222,223 |
| 5 | Direct zero-ATK illness | 219,220 |

Masks are Fog=1, Dream=2, Flash=4, Dark Cloud=8. Illness stages reuse
None=0, Cold=1, Fever=2, Hell=3, Heaven=4. Ghost Sword, Real Ghost Sword,
Vine Shoot and Absorption heal; Hell Scissors inflicts Hell, Gale/Severe Gale
Sword/Wind Talons inflict Cold; Fog Gun/Fan, Flash Dagger/Flash, Bogus
Spear/Dream Mallet and Hexagon Doom inflict their described masks. Wind and
Heaven Wind directly inflict illness, while Fog, Dream and Dark Cloud directly
inflict masks. Fog Fan/Vine Shoot/Flash extend chance profiles to 24; Ascension
Bow remains unimplemented.

The client attack-target eligibility method `ce` excludes self and same-team
targets. This engine remains free-for-all and permits living enemies only,
including for Heaven Wind. Existing evidence in
[ADR 0034](0034-absorption-weapon-curriculum.md) records Ghost Sword removing
7 HP/healing 7, and a reflected Real Ghost Sword healing the reflector by 12.
[ADR 0048](0048-fog-flash-curriculum.md),
[ADR 0049](0049-dark-cloud-curriculum.md), and the pinned help establish
positive-damage mask triggers, direct curse descriptions/costs, Flash's defense
limit, Fog's visibility/target behavior and Dark Cloud's percentage-hit certainty.
[ADR 0098](0098-portable-native-curse-dynamics.md) and
[ADR 0100](0100-portable-ordered-dream-inventory.md) provide the shared disease
and non-retroactive Dream primitives. These observations do not validate the
entire compound full-game scheduler.

Combat-plan schema 5 pins the complete attack/armor/boost/special/chance/effect
tuple to
`9440a09fe928fbb6c4c1b2a58e3d6703a530230dc2baa4edec927a623dd6833c`.
Effect-only SHA is
`643e097f239903060e7b022a5367467c03199de895fd4439c2b74cc25f74a781`;
the 24-model chance SHA is
`fed7e6d50a4761ffff8e81c338b42abb27e4423482c58dbd9395393028e8e3e1`.
The engine now has 92 leaders, 64 numeric defenses, 29 ordered additions,
23 special responses, 24 chance rows and 20 effects. Their overlapping roles
represent 183 distinct combat models plus 12 own-utility/cure models: **195
of 237 held models**, with 42 still unimplemented. This denominator excludes
the event/guardian catalog and does not establish complete action coverage.

## Joined transactions and explicitly provisional rules

Effects are owned by the native pending attack, not a separate Python scheduler.
Fixed weapon effects apply to the actual whole ordered attack. Chance leaders
still forbid additions; direct curses are standalone miracles with zero ATK.
Zero-ATK profiles without a corresponding direct effect fail construction, not
silently become no-ops. Direct curses reject numeric armor but allow applicable
exclusive block/reflect/bounce responses. They pay MP and retain the used
miracle under the existing inventory rules.

After final defense, ordinary damage and positive Darkness finishing resolve
first. Positive actual HP removed enables damage effects. A block or zero
post-defense damage suppresses them; direct curses do not require HP loss,
but a special block suppresses their effect. Absorption heals the current living
damage source by actual HP removed, capped at 100. Reflection transfers that
source; bounce preserves it. The original turn owner remains distinct and
ticks exactly once after the final response, never between redirects.

Illness infliction uses the shared exclusive-stage kernel: a new illness sets
its stage when none exists, otherwise worsens the existing one. Worsening
Heaven kills immediately. `hp_damage` continues to count attack HP removed;
`illness_effect_damage` separately counts infliction-related HP loss. Infliction
does not prematurely tick the defender. Dream leaves existing real/fake models
unchanged and influences newly received cards, including deferred defense
receipts under this provisional same-hit ordering. Mild cures retain the
documented Fog/Flash mask scope, not the legacy widened Dream/Cloud scope.

General compound ordering, same-hit receipts, dead-target treatment and
self-bounce absorption remain **provisional**. Dead targets are not newly
afflicted; a source killed by a lethal self-bounce is not resurrected by
absorption. Partial self-damage can be healed if the source survives. These
choices are recorded in strict metadata and do not unlock official validation
or promotion.

Every mutation, status, resource, hand, consumed/reused card, queued receipt,
effect counter and random state is staged for the entire command batch before
any environment commits. A later hidden unsupported defense rolls back an
earlier staged absorption and its counters. Setup remains sealed after start;
tests do not inject status changes into active games.

## Corrected chance order

v6 rolled before sampling a target. That could not implement the target's
Dark Cloud guarantee. v7 samples the living enemy **before** checking hit:
Cloud skips the chance ticket entirely; other targets use the independent
chance stream. The caster's Cloud does not guarantee outgoing attacks.
The target stream now advances even on misses, an intentional versioned
correction. Target sampling and all RNG algorithms remain labeled provisional.

Chance success is still retained across the full defense chain: redirecting
to an uncursed player does not trigger another roll. Fog cannot reveal hidden
target masks through pre-cast observations; no future ticket/RNG state becomes
a policy feature. Tests cure Cloud through an actual legal full-cure action
and prove that the following uncursed cast uses the first unconsumed ticket.

## Observability and compatibility

Kernel, observation, plan and metadata versions are 7; command schema remains
1 and phases stay 0,1,2,3,4,12,13. The source factory always supplies the full
effect map. Narrow raw unit fixtures explicitly omit probability/effect maps
to isolate positive attack arithmetic, without full-game learning metadata.
The old numeric fixtures exclude zero-ATK direct profiles rather than pretending
to simulate them without their effect.

`attack_effect_observations[B,4]` is an owned read-only public copy of active,
displayed/resolved effect kind, value and current source. True leader identity
does not leak during selection. `attack_effect_snapshot[B,6]` is diagnostic:
absorption applications, HP healed, mask applications, illness applications,
illness-infliction HP loss and Cloud-guaranteed hits. Reset clears these
per-epoch counts; lifetime counters persist. Mask/illness application counters
count accepted effects, including reapplication, not only newly added bits.

Chance smoke advances to schema 2, acquisition/combat reports to schema 5.
The new attack-effect smoke is schema 1. All explicitly reject admission as
a training/reward dataset, full-game readiness, official fidelity or promotion.

## Reproducible offline evidence

`simulation full-game-attack-effect-smoke --batch-size 640 --players 3 --seed 67`
cycles the 20 new models 32 times. The scenario **deliberately gives enemies
Dark Cloud**, isolates effects with guaranteed hits, and forgives attacks.
It performs 2,464 commands and 640 resolved turns: 128 absorption applications
healing 1,024 HP, 320 mask applications, 192 illness applications, 96 forced
chance hits, 3,104 attack HP removed, 1,536 MP paid, 416 ordinary cards consumed
and 224 retained miracle uses. All episodes remain ready after one turn;
this is not 640 games/wins or a chance-rate evaluation.
Metadata SHA:
`1f6a7e864e5450cddbcf52a4b15b6f09be758728e8a16408dfeb94ec75d35040`;
replay SHA:
`21fec423a2335216d8153abefc80c9c9c9155aae4c728c04f6d761f8350a3ec7`.

The separate unforced chance probe cycles all 24 models 21 times:
305 hits, 199 misses, 1,313 commands, 504 completed turns, 2,654 attack HP
removed, 1,323 MP paid, 357 cards consumed and 147 retained miracle uses.
Metadata SHA:
`0b8bef30397954308874db3dcb583cbf02e80252b41f95e6a6a314565aab142a`;
replay SHA:
`3e8430dde07921af47204bc3b03b49b24bbe4eda6e3f5aa2ec8bd956a3e4c2c3`.

The full-pool startup probe still executes zero gameplay commands/completed
games. It draws 41,472 cards, observes all 237 held models and counts 8,634
unsupported-effect draws; zero starting actors lack an implemented choice.
This does not certify later hands or complete matches.
Metadata SHA:
`48fa83d27f5da03984f6f6ef945a21158d1813e87ad86a946eb62d32f7e5ca89`;
replay SHA:
`ab0612b4a4fd424a0f47ed5e4b3e69dda32a3ac034a05d263a9b3f1bbb2bbfe9`.

The fixed-known-combination combat probe retains 32 winners, 179 turns and
693 commands, without truncations. Its unchanged replay is
`eacf95e2c633e8a093f7d5b8abd0efb1af059adb9c2a755cdf15903cfe47ed27`;
v7 metadata SHA is
`eedf7266002dcf95faf3c00bff2db2499bd085e85e19e4952e0e02d77151de0a`.
The utility/cure probe keeps its existing replay and 2,048 commands,
384 utilities/1,664 passes; metadata SHA is
`722ab31dd3b391d881d4440a726ccd4fd1e621094b187e226d88bd772405e317`.
Neither old fixed scenario is relabeled as new-effect strength evidence.

Final verification: **3,704 non-browser tests and two local Chromium fixtures
pass (3,706 total)**, including 142 new effect tests, 37 new effect-probe tests,
and the unchanged legacy 0.46 trajectory golden. Ruff passes source/tests;
mypy passes all 92 source modules. Changed Python formatting, native
source/header formatting, frozen offline synchronization/lock checks and
whitespace checks pass. Only the local native package release changes in the
lockfile; the API Git revision remains pinned.

## Remaining objective

Counter defenses, self-curses, dynamic/resource-dependent attacks, cost cuts,
multi-hit/multi-recipient attacks, mixed utilities, removal/revival, trade,
events, guardians, Apocalypse and teams still need joined native execution.
Complete policy observation/action/reward interfaces and neural rollouts need
separate implementation and gates; held-out official replay verification and
live promotion remain independent. Next work should integrate the remaining
combat/inventory effects rather than train on silently dropped mechanics.
