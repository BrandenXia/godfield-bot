# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
The separate full-game development engine is now native0.81.0/schema32. Its
source factory defaults to99 HP/MP/CP, with an explicit legacy100 option;
raw native fixtures retain100 by default. This does not change existing arenas
or make full-game training/live promotion ready. See
[ADR 0130](../../docs/architecture/0130-client99-and-explicit-legacy100.md).
Appended opt-in raw flags resolve private fixed/chance targeting and the three
held trade identities under Dream; the source factory enables both. Public
masks stay display-only. Whole-episode diagnostics retain remaining errors and
cannot authorize training/promotion. See
[ADR 0131](../../docs/architecture/0131-private-dream-targeting-trades-and-episode-diagnostics.md).
Two further raw-default-off rules resolve known hidden incompatible components
at actual affordable costs, and retain protected hidden Discard/Sacrifice cards.
The complete source factory enables both. A checked237-card native/Python role
manifest distinguishes an incompatible context from a missing registration.
`ineffective_snapshot`, `ineffective_model_counts` and `hidden_removal_snapshot`
are owned readonly private diagnostics; no policy features are widened.
Unaffordable actual costs still fail atomically. Default3-player64-env and
9-player32-env seed67 episode probes now finish, but the broader2–9-seat sweep
retains9 unaffordable-cost errors out of768 episodes. Full-game training and
promotion remain blocked. See
[ADR 0132](../../docs/architecture/0132-approved-ineffective-hidden-components.md) and
[ADR 0133](../../docs/architecture/0133-approved-hidden-protected-removal-retention.md).
Append raw `teams_enabled=false`; the complete factory enables team rules and
accepts an initial `teams` layout. `seed_teams(environments, owners, teams)` is
atomic trusted pre-start setup, with0 solo and1-4 shared teams. Reset clears
episode team seeds to solo, so callers must explicitly reseed new episodes.
`team_ids[B,9]`, actor-cyclic `team_observations[B,9,4]` (seat/present/team/relation)
and terminal-only `winning_seats[B,9]` are owned readonly arrays. Relations have
no hidden HP/inventory/liveness and are not existing-checkpoint compatible.
Native enemy selection/guardian triggers and last-living-faction endings share
one relation; special bounce/danger/global/reaction scopes remain distinct.
Winner masks include eliminated teammates, not a newly invented reward scale.
Existing arenas/checkpoints/live controls are unchanged; training/promotion
stay blocked. See
[ADR 0135](../../docs/architecture/0135-approved-native-team-ownership-and-targeting.md).
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Native 0.45.0 adds the isolated `GuardianUtilityTurnBatch`, combining the
existing provisional guardian/card scheduler with eight inventory-backed
HP/MP cards. Its schema-1 actor hand includes HP/MP values; the old
`GuardianTurnBatch` schema and trained arena contracts stay unchanged. This
component has no native automatic refill. A separately versioned Python
rollout/training adapter now supplies nine own-hand features, immediate utility
dispatch, and an opt-in pinned 102-card provisional refill pool. An explicit
7→9-feature checkpoint migration preserves old models; ordinary resume cannot
widen them. This subset can train locally, but full-game readiness and live
promotion remain false. See the native contract in
[ADR 0089](../../docs/architecture/0089-inventory-utility-guardian-batch.md) and
the adapter/migration in
[ADR 0090](../../docs/architecture/0090-utility-arena-training-and-checkpoint-migration.md).

Native 0.46.0 adds the distinct `GuardianDiscardTurnBatch`, retaining the old
utility projection while admitting source-restricted removal in ready turns.
It does not widen old batches, generate gifts automatically, or connect discard
to existing neural checkpoints. Caller-supplied replacements can recover
pass-only inventories; timing and miracle eligibility remain provisional, and
Sacrifice is excluded. A separate Python schema-3 adapter now connects 48-action
rollouts and local imitation/PPO training, with explicit 30→48 checkpoint
migration and its own provisional replacement RNG. Old native batches, action
layouts, models, and live controls remain unchanged. See
[ADR 0091](../../docs/architecture/0091-pass-only-diagnostics-and-discard-component.md)
and [ADR 0092](../../docs/architecture/0092-discard-arena-training-and-action-migration.md).

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `dream-resource-hand`, includes elemental multi-card
combat, HP/MP utility, fixed and chance miracles, Absorption, reusable additive
miracles, evidence-bounded one-hop reflection, seven fixed ATK/DEF weapons, 14
effect-free chance weapons, and the chance/defense dual role of Jinn's Rocking
Horse. It additionally models all three evidenced HP-absorbing weapons,
including actual-damage healing and reflected ownership, Magical Stick's
current-MP attack and all-MP consumption, Evil Broadsword's post-defense
same-damage effect with lethal-target short-circuiting, and Saw Boom Boom's two
independently defended strikes, plus Dangerous Pestle's uniformly random
opponent-or-self ATK30 with immediate, indefensible self-target resolution.
It also models the four Bible-exact Cold/Hell weapons, damage-gated infliction,
Cold/Fever/Hell end-turn damage, Heaven healing, repeated-status escalation,
and 5% end-turn worsening. Two actor-relative status features make the state
Markov for training. Smile Shell and Tone cure Cold/Fever, while Heart Shell
and Song cure every modeled illness; miracle costs and reusable ownership are
preserved. Heaven Herb is a consumable utility that gains 20 MP, applies the
Heaven curse through the established illness-escalation rules, redraws, and
then runs the normal end-turn status effect.
Fever Mask adds a consumable Fire DEF10 defense that inflicts Fever on its
surviving user after defense resolution. Its combination with Cold/Hell
on-damage weapons remains masked until the effect order is independently
verified.
Angel Gauntlet, Cap, Shield, and Armor retain their printed neutral DEF against
weapons and fully block fixed, chance, or effect attack miracles regardless of
element. The engine exposes the pending base card kind for diagnostics and the
heuristic without changing the neural observation schema.
Angel Knife, Sword, and Axe are consumable neutral base weapons that also fully
block miracles. Angel Bow remains an additive +ATK15 weapon on attack while
retaining the same miracle-only defense; none can defend ordinary weapon hits.
Sky Boots, Gauntlet, Helm, Shield, and Armor retain neutral DEF1/3/5/7/9
against compatible weapon attacks and bounce attack miracles to a uniformly
sampled living duel player. The redirected target receives a new defense
response, and bounce/reflection chains are capped at one hop.
Sky Harpoon adds a consumable neutral +ATK9 booster that can also bounce a
miracle, but cannot defend a weapon attack. `<Turbulence>` adds the reusable
5-MP miracle form of the same one-hop bounce effect.
Moonlight Helm, Shield, and Armor retain neutral DEF8/10/12 against compatible
weapon attacks and reflect attack miracles to the original caster. Moonlight
Axe is a consumable neutral ATK10 base weapon with the same miracle-only
reflection defense. Bounce and reflection use the same one-hop redirect guard.
Fog Gun, Fog Fan, Flash Dagger, `<Flash>`, and `<Fog>` add independent Fog and
Flash state. A fogged actor receives zeroed opponent HP/MP observations, while
a flashed defender may select exactly one defensive artifact. Damage-triggered
curses require positive damage. Direct Fog is a reusable 3-MP attack miracle;
ordinary armor cannot answer it, while Angel block, Sky bounce, and Moonlight
reflection retain their miracle behavior. Existing mild and full cures remove
Fog and Flash. Four actor-relative curse features expand the observation to
schema v8.
Hexagon Doom and `<Dark Cloud>` add independent Dark Cloud state. The weapon
inflicts it only after positive damage; the reusable direct miracle costs 5 MP.
Percentage attacks aimed at a clouded player hit certainly, and existing mild
or full cures remove the status. Two actor-relative inputs expand the
observation to schema v9.
Bogus Spear, Dream Mallet, and `<Dream>` add independent Dream state. The two
weapons inflict it only after positive damage; the reusable direct miracle
costs 6 MP. Each newly drawn ordinary fixed-value weapon or armor has an
independent 50% chance to expose an identity sampled uniformly from the same
semantic catalog.
The neural observation and action mask contain only that displayed token,
value, and element, while combat resolves the hidden true card. Two
actor-relative inputs expand the observation to schema v10. The true-token
view is diagnostic-only and is not included in training tensors or heuristic
policy input.

The unobserved same-damage/reflection, attack-twice booster/reflection,
random-target booster/reflection, and damage-triggered Fog/Flash/Dark Cloud
redirect or Fever Mask interactions remain masked. Dream disguises for special
weapons, miracles, sundries, and armor with active effects remain truthful
rather than speculating about their displayed semantics. Dreaming Hat, Jupiter
Ring, Dream guardians, Dark Cloud counterattacks, and multiplayer Fog targeting
remain excluded. See ADR 0002 and ADRs 0029 through 0051 in the root project
for the interface and safety boundary.

The separate `wide-hand-gift-weighted-dream-resource-hand` capacity-stress mode
uses 18 padded slots, 30 actions, and schema 11. Its 9–18-card occupied initial
hands keep their size until reset; this is not the official gift/discard cycle.
Call `configure_hand_capacity()` once after gift-weight configuration and before
exposing any hand/action views or stepping. Runtime `hand_slots`, `action_count`,
`hand_sizes`, `forgive_action_index`, and `confirm_action_index` describe the
layout. Legacy module constants and default batches remain nine-slot/21-action.
See root ADR 0059 for migration and safety boundaries.

Version 0.34.0 adds `OrderedInventoryReplay`, a separate diagnostic lifecycle
building block, not a selectable curriculum. Its explicit ordinary consumption
and ordered gift appends reproduce all four self inventories from the first
verified v2 official capture. No existing environment or observation layout
changes.

Inputs are contiguous `int64` NumPy arrays. Each item is
`[instance_id, model_id, fake_model_id, used]`; missing client-default fake/used
values must be interpreted outside C++ after verifying capture ownership and
provenance. Construct with `(initial_items, ordinary_consumable_model_ids,
capacity=512)`. The allowlist must contain only catalog-verified ordinary
consumables. `consume(expected_items)` validates the full selection before
removing it and preserves survivor order. `gift(item)` appends without
overwriting a currently owned ID. A consumed ID may be reused by a later gift.
`snapshot()` returns an independent, read-only `(N, 4)` array. Size, explicit
capacity, and successful consumption/gift counters are available for diagnostics.

Used, disguised, or non-allowlisted consumption is rejected; opaque artifacts
may be retained or gifted without simulating their abilities. The capacity is
a resource bound, not an official maximum. Overflow removal, performed-miracle
retention, trade/discard effects, gift timing, and random acquisition are not
inferred. Evidence and generated trajectories are not admitted to training or
promotion by this API. See root ADR 0064.

Version 0.35.0 extends this diagnostic replay to schema 2 with an explicit
retained-miracle operation. Before any operation, call
`configure_retained_miracles(model_ids)` once with a catalog-verified allowlist
disjoint from ordinary consumables. `perform_retained_miracle(expected_item)`
requires an exact owned, undisguised item, retains its instance/model, sets used
to 1, and appends it to the tail. Both first use and an already-used item are
accepted; population and ordinary-consumption/gift counters do not change.
Successful operation counts and configuration state are exposed separately.

The official observation fixture uses only `<Flame>`/model 215 and reproduces
two contiguous v1 inventory pairs. V1 consumption bodies are missing, so these
are observed-state replays, not full event verification or training examples.
Miracle configuration cannot change after any successful operation, including
an empty selection. Disguises, mixed selections, automatic lifecycle dispatch,
MP/combat, overflow, and scheduling remain outside this operation. Ordinary-only
constructor and method behavior remain supported. See root ADR 0065.

The later official v4 fixture `acquisition-v4-32d8eeeb.json` closes the missing
single-Flame event-verification case: two explicit self-bound attack selections
identify the same received instance/model, first with the raw used flag omitted
and then with boolean true. Both independent native retention-and-explicit-gift
pairs match every owned row, including reuse tail reordering. Neither cast
consumes or replaces Flame; a separate recorded gift grows each inventory.
This verifies the existing primitive without changing native 0.35.0 or promoting
the full run: omitted defenses and other models remain unsupported. Universal
gift timing, removal/overflow, other miracles, and acquisition training remain
unverified. See root ADR 0071.

The first real v3 acquisition capture adds explicit ordinary inventory pairs
for Glaive Classic, Final Tusk, Power Halberd, Hexagon Doom, Direct Smash Axe,
Angel Axe, Iron Gauntlet, Iron Armor, and Heart Dew. The read-only differential
caller now supplies an 11-model witnessed allowlist to the same native API;
no kernel or package identity changes. Its dispatcher accepts only witnessed
single-item ordinary uses, not unobserved combinations or every ordinary catalog
model. Curse, trade, omitted selection arrays, overflow, and gift scheduling
remain unsupported. These are lifecycle diagnostics, not a new trainable
curriculum. See root ADR 0068.

A second real v3 fixture witnesses six more ordinary model families, including
Smile Flower's MP utility, for a total witnessed caller allowlist of 17 models.
It also verifies a deferred ordinary gift: `consume()` produces eight owned
items after a reflected attack; only the next explicit `gift()` restores nine.
The kernel must not fuse these into an automatic redraw. Empty serialized
placeholders are normalized outside C++; unresolved reflected defenses remain
unreplayed. This is a recorded timing case, not a complete scheduler or a new
training ruleset. See root ADR 0069.

Version 0.36.0 advances the separate ordered-inventory diagnostic to schema 3
with `configure_observed_removal_models(model_ids)` and
`remove_observed_three(expected_items)`. The sole admitted observation is a
self-targeted `removeItems` event in a private game: selected models 75, 139,
and 99 disappear, while all six other items keep their order. Supply only
these three witnessed model IDs to the configuration; the native operation
requires exactly the three configured, explicit, unused, undisguised, exactly owned rows and
validates all of them before mutation. It does not infer selected items from
an inventory difference, simulate the Broom card or opponent, or enter the
training curriculum. The same server update has an omitted defense array, so
the full acquisition differential remains unsupported. See root ADR 0074.

Version 0.37.0 adds a **separate provisional** `ProvisionalSoapProjection`,
schema 1/ruleset `catalog-derived-selected-two-used-miracles-provisional-v1`.
The pinned catalog identifies model 206 as `removeUsedMiracles`, while the
pinned Bible describes washing away two performed miracles. The caller supplies
the 30 catalog miracle models and an explicit two-item selection. The primitive
requires both rows to be exact owned, used, undisguised miracles, validates the
whole selection atomically, and preserves survivor order. It does not choose
targets, determine whether fewer than two can be removed, simulate the card's
cost or replacement gifts, or assert official fidelity. There is no `step` or
training interface. The observed replay schema 3 and all existing curriculum
identities remain unchanged. See root ADR 0076.

Version 0.49.0 adds the isolated `DreamInventoryBatch` and source-pinned Python
factory `create_provisional_dream_inventory_batch`. It stores all 237 held
models (234 artifacts plus Exchange/Sell/Buy), separate actual/displayed
identities, stable explicit consumption/removal, and provisional retained
miracle ordering. Caller-selected Dream tickets and full-cure restoration are
explicit; atomic overflow rejection never drops items. Copied actor hands
contain only own displayed identities, whereas full snapshots are trusted
diagnostics. There is no battle/turn/cost/training interface or implicit gift
schedule. Existing replay allowlists, curricula, checkpoints and live controls
remain unchanged. See [ADR 0100](../../docs/architecture/0100-portable-ordered-dream-inventory.md).

Version 0.50.0 starts the approved separate `FullGameBatch` engine. Its initial
development slice joins resources, ordered inventory, 12 HP/MP utility/cure
effects, owner disease ticks and bounded free-for-all turns in one authoritative
state. Packed commands bind episode/decision/actor/phase; all rows are staged
before resource/status/inventory/RNG commits. Trusted setup seals on start and
reset changes the episode epoch. True inventory diagnostics stay separate from
actor-visible hands and Fog-masked resources. Unsupported effects and hidden
unaffordable costs fail atomically instead of silently succeeding.

`godfield-bot simulation full-game-development-smoke` runs a reproducible offline
utility/cure liveness probe, not combat evaluation or learning. It reports real
endings separately from limit truncations. Combat, acquisition cadence, targets,
teams, events and the complete neural interface are still missing; the new
engine remains training/promotion-ineligible. Old curricula, checkpoint shapes,
official replay admission and live controls are unchanged. See
[ADR 0102](../../docs/architecture/0102-integrated-native-full-game-state-and-transactions.md).

Version 0.51.0 widens that separate engine to explicit single-attack target and
ordinary multi-armor phases: 45 attacks, 47 armor models and the prior 12
utility/cure effects. This is 104 integrated effects, not all 237 registered
held models. Kernel/observation schema 2 and ruleset
`integrated-full-game-development-v2` keep command schema 1. Native bounded
selection, Fog targeting, costs, two-owner damage/disease and hand consumption
share the same atomic transaction. After 64 armor toggles only confirmation is
legal. True identities stay outside public masks and pending previews.

`godfield-bot simulation full-game-combat-smoke` exercises complete provisional
combat loops offline; it is not neural training or an official-bot strength
test. Special combat effects, normal acquisition/overflow, events, teams and
the complete learner are still missing. Full-game training/live promotion remain
blocked; existing arenas and checkpoints are unchanged. See
[ADR 0103](../../docs/architecture/0103-integrated-attack-target-and-armor-phases.md).

Version 0.52.0 adds native acquisition to the same separate engine, with kernel
and observation schema 3 / `integrated-full-game-development-v3`. The opt-in
source-pinned `all-held-weighted` mode samples **all 237 held models**, including
Exchange/Sell/Buy, from weights totaling 500. It deals nine cards per living
seat and queues one replacement per used card, including every reuse of a
retained miracle. Attack receipts wait for defense resolution; terminal,
truncated and dead-owner receipts are suppressed. Prayer admits one gift only
without a nonused displayed weapon. These scheduling rules remain provisional.
The approved local 18-card cap automatically evicts the first card in current
held order, not a player-selected victim or the lowest instance ID. Neither
that cap nor the eviction algorithm is asserted as official server behavior.

`godfield-bot simulation full-game-acquisition-smoke` checks complete-pool native
startup draws and reports unsupported effects explicitly. The default draws
41,472 cards and samples all 237 models; only 104 effects are currently joined
to the separate turn engine. No gameplay, learning or strength conclusion is
claimed. Acquisition counters are copied/read-only diagnostics; model draws,
disguises, illness and Fog use independent native streams. Manual fixtures,
legacy environments/checkpoints, live controls and promotion remain unchanged.
See [ADR 0104](../../docs/architecture/0104-native-complete-pool-acquisition-and-provisional-overflow.md).

Version 0.53.0 integrates ordered attack selection in the same engine: kernel
and observation schema 4 / `integrated-full-game-development-v4`. The factory
supplies 27 source-pinned additions: nineteen weapons, four Ogre armor with
both ATK and DEF roles, Strength Powder and Fireball/Meteor/Aura. Additive
weapons and positive-ATK miracles may lead alone; only an ordinary weapon leader
admits further additions. Aura doubling and wand element setting use selection
order. Costs, actual hidden effects, consumption, ordered miracle retention
and one-per-used-card deferred receipts commit together at casting. Darkness
now sets HP to zero after positive post-defense damage; full armor blocks do
not trigger it.

Attack selection exposes copied public order, flags and displayed ATK/element/
MP previews. Undo recomputes that order; leader undo cancels it. After 64
selection actions only confirmation is legal, and exact-integer overflow is
rejected atomically. Existing legacy arenas, models and live controls remain
untouched. Full-game training and promotion are still blocked: 131 held models
are now integrated, while 106 remain unimplemented. The complete gift pool is
unchanged. Current acquisition/combat smoke reports are schema 2; historical
measurements above refer to their native versions. See
[ADR 0105](../../docs/architecture/0105-native-ordered-attack-composition-and-darkness.md).

Version 0.54.0 adds 23 special-defense profiles to this same engine, advancing
kernel/observation/metadata schema to 5 and the development ruleset to v5.
Numeric defense rows stay separate from exclusive block/reflect/bounce rows.
Dual-role weapons and armor retain their attack/printed-DEF roles.
Wall/Turbulence pay once per confirmed use, stay in inventory and move to its
tail. Reflection transfers current source to the reflector; bounce samples
any living seat including self from its own native RNG stream. Universal
chain ownership, sampling and timing remain explicitly provisional.

Each redirect offers fresh defense with its own 64-toggle bound. There is
no silent one-hop mask; the actual episode decision limit truncates cycles
without fake HP damage or owner ticks. Deferred gift counts are 64-bit so
reusable chains cannot wrap a 16-bit queue. Cards, costs, pending sources,
random states and counters participate in full-batch rollback.
`special_defense_observations` is a copied five-column public view: active,
current damage source, redirect count, displayed response kind and displayed
MP cost. True identities remain diagnostic-only. The source-pinned factory
always supplies complete defense profiles; raw narrow fixtures may omit
them without receiving training metadata. There are 154 distinct integrated
held models, not the sum of overlapping profile rows, and 83 still lack
effects. Acquisition/combat reports are now schema 3; training/official/live
promotion admission remains false. See
[ADR 0106](../../docs/architecture/0106-native-special-defenses-and-bounded-redirect-chains.md).

Version 0.55.0 integrates 21 plain chance attacks and Jinn's fixed defensive
role into the same engine. Kernel/observation/metadata schema is 6, ruleset v6;
command schema remains 1. Optional chance rows `[model, hit percent]` complement
72 leader rows and 64 numeric-defense rows, not a caller roll or target ticket.
The source factory always supplies these profiles. Raw arithmetic fixtures may
omit probability maps but have no source-checked learning metadata.

Chance selection permits cancel or confirmation, not additions or target
choices, matching the pinned client's restrictions. Confirmation atomically
pays MP, consumes/moves the used card, and rolls exactly once. Misses complete
the original owner's turn without defense/damage. Hits provisionally sample a
living enemy from their own native target stream, then enter the existing full
defense/redirect chain without another hit check. Roll, target, Fog, bounce,
illness and acquisition streams are separate. Displayed/actual target-mode
mismatches remain explicit atomic development errors, not guessed Dream rules.

Public copied `chance_observations[B,4]` exposes active, displayed hit rate,
already-hit and automatic-target flags. `chance_snapshot[B,3]` reports per-epoch
casts/hits/misses diagnostically, with lifetime totals as counters. Jinn's Wood
DEF6 is fixed and never samples probability. There are now 175 distinct executable
held models and 62 unimplemented held effects. Existing acquisition/combat
reports advance to schema 4; the new one-turn `full-game-chance-smoke` is schema
1 and explicitly cannot admit learning, full-game readiness or promotion. See
[ADR 0107](../../docs/architecture/0107-native-chance-attacks-and-automatic-targets.md).

Version 0.56.0 adds 20 damage/direct effects to the separate engine, with
kernel/observation/plan/metadata schema 7 and ruleset v7; command schema stays 1.
Combat-plan schema 5 supplies 92 leaders, 64 numeric defenses, 29 ordered
additions, 23 specials, 24 chance rows and 20 attack-effect rows. Distinct
executable held models total 195 (42 still unimplemented), not the sum of
overlapping roles. Optional `[model, kind, value]` effect rows use absorb=1,
mask-on-damage=2, illness-on-damage=3, direct-mask=4 and direct-illness=5.
Zero-ATK leaders require a corresponding direct miracle effect profile;
omitting the map does not silently turn them into no-op attacks.

Absorption heals the current living source by actual HP removed after defense,
capped at 100. Reflect transfers healing ownership; bounce preserves it.
Damage curses require positive actual HP loss, while direct curses require
no damage, reject numeric armor and admit applicable special responses.
Illness reuses the documented exclusive-stage kernel; Heaven worsening damage
is separately accounted from attack HP loss. Effects precede the original
owner's single tick and deferred gifts. Dead targets/sources are not afflicted
or resurrected. Dream affects subsequent gifts, not existing disguises.
Compound timing, dead-target treatment and self-bounce ordering remain
provisional, with full-game learning and live promotion still blocked.

v7 corrects v6's roll-before-target order: chance samples its living enemy
first even on misses, checks that target's Dark Cloud, skips the hit ticket
when guaranteed, and otherwise rolls. A successful attack is not rechecked
after redirects. All random streams and effect counters stage transactionally.
`attack_effect_observations[B,4]` is a public owned read-only copy of active,
displayed/resolved kind, value and current source. The six-column
`attack_effect_snapshot` holds per-epoch absorption events/HP, curse events,
illness events, illness HP loss and forced Cloud hits, diagnostically only;
reset clears it, while lifetime counters remain.

The new `simulation full-game-attack-effect-smoke` reports bounded one-turn
mechanics diagnostics with explicitly forced hits, not full-game outcomes or
a training dataset. Chance smoke advances to schema 2 and acquisition/combat
reports to schema 5. Existing arenas/checkpoints/live controls are unchanged.
See [ADR 0108](../../docs/architecture/0108-native-attack-effects-and-target-first-chance.md).

Version 0.57.0 advances the separate engine to kernel/observation/plan/metadata
schema 8 and ruleset v8; commands stay schema 1. Combat-plan schema 6 includes
99 leaders, 72 numeric defenses plus nine zero-DEF counter/filter armor, 29
additions, 23 specials, 24 chance rows, 20 held attack effects and ten defense
effects. These overlapping roles cover 212 of 237 held models, not all game
mechanics. Older arenas, training checkpoints and live controllers are unchanged.

Optional `defense_effect_profiles[N,5]` contains model/kind/value/element/rate:
counter ATK=1, mask=2, MP=3, CP=4, element filter=5, self-illness=6. Nine zero-DEF
armor require a matching effect map; omitting it fails construction. The seven
effect-free dual-role weapons add both attack and defense rows. Fever Mask
supplies Fire DEF10 then inflicts self-illness on a living defender after
incoming effects; this compound ordering remains provisional.

Defenses retain public click order. Filters must form a prefix; following them
one exclusive applicable special or compatible numeric/counter armor may be
selected. Removing a card rebuilds the remaining sequence using displayed IDs,
pruning incompatible entries. Actual hidden role/element/cost conflicts fail
atomically. Filters clear the actual element before defense, redirects and
Darkness finishing. Flash still limits additional selections and permits undo.

Selected rings provisionally react to actual positive HP loss. Their private
stack is bounded by player count times capacity: rings are consumed once and
replacement gifts wait until the family ends. Reverse insertion preserves
click order and nested reactions resolve depth-first. Dead sources/targets are
suppressed diagnostically. Generated responses use armor origin 2 (only Super
Mirror reflects them), fixed current-source targets, and one separate Mars RNG;
Cloud skips its hit ticket and redirects never reroll. Neptune targets its own
living owner for double-damage MP. Generated effect kinds 6 and 7 represent MP
and CP payloads, not held attack-effect profiles.

`payment_rules.h` exposes allocation-free CP → MP → HP waterfall arithmetic,
shared by Venus and future trading callers. Venus credits its requested damage
amount, capped at local 100; same-wallet transfers are no-ops. Caps, credit
timing, trigger/liveness treatment and counter scheduling remain provisional.
Attack HP, illness-infliction HP and CP-spill HP have separate diagnostics.

Owned read-only `defense_order[B,capacity]` exposes phase-4 displayed choices.
`counter_observations[B,6]` contains active/kind/source/target/damage-basis/rate,
with no queued hidden payloads. `counter_snapshot[B,12]` is diagnostic-only:
enqueued, casts, resolved, misses, dead-suppressed, counter-ATK HP, MP gain,
CP credit, CP-spill HP, filters, self-illnesses, queued. Epoch reset clears the
stack/counters, preserving lifetime totals. Queue/RNG/hands/payments/resources
are staged for all environments before allocation-free commits.

`simulation full-game-counter-smoke` checks one forced-hit family per
environment, not matches, learning or strength. Default 512 covers each ring
64 times, 3,072 commands, 1,920 counter HP, 1,280 MP and 640 CP; only original
owners tick, with no leftovers. Other reports advance to acquisition/combat
schema 6, chance 3 and attack-effect 2. Full-game training and live promotion
remain blocked. See
[ADR 0109](../../docs/architecture/0109-native-counter-families-and-payment-waterfall.md).

Version 0.58.0 advances the separate engine to kernel/observation/plan/metadata
schema 9 and ruleset v9; commands stay schema 1 and combat profiles stay schema
6. Optional `passive_profiles[N,2]` adds model/HP-gain pairs; the pinned adapter
supplies Sun Amulet `(208,10)`, a passive sundry, not a manual revival action.
This increases held-model coverage to 213/237 without claiming complete rules.

Every positive-to-zero HP transition checks current staged actual ownership:
ordinary/Darkness damage, illness infliction, CP-spill, owner periodic illness
and Heaven worsening. The first real owned Amulet is consumed with survivor
order preserved, HP becomes 10, and other statuses/resources are retained.
One copy triggers per edge; separate edges in one command can consume multiple
copies. No setup/deal/idle resurrection, recursion, extra tick or immediate
replacement gift is introduced. Revival precedes subsequent effects, counter
liveness and final outcome checks. Timing, retained state, copy selection and
receipt rules are explicitly provisional, not official replay validation.
Omitting passive profiles retains raw-batch pre-revival behavior.

`passive_observations[B,capacity,2]` supplies displayed kind/HP only for the
current interactive actor; fake identities and Fog never reveal actual passive
eligibility. `revival_snapshot[B,7]` is diagnostic-only: count, HP granted,
attack, infliction, payment, periodic and worsening counts. Both are owned,
read-only arrays. Epoch reset clears diagnostic counts but preserves lifetime
`revival_count` and `revived_hp`. Consumption, resources, queue state, receipts,
RNG and revival counters commit atomically across the entire submitted batch.

`simulation full-game-revival-smoke` scripts 500 one-turn scenarios by default:
405 revivals/4,050 HP, 1,600 commands, 100 Venus resolutions and 500 original
owner ticks. Five Heaven-worsening events use normal native random tickets,
not forced successes. No full matches or training rewards are generated.
Other report schemas advance to acquisition/combat 7, chance 4, attack-effect
3 and counter 2. Their previous behavioral replay hashes remain unchanged.
Full-game training and live promotion remain blocked; old arenas/checkpoints
and live controllers are unchanged. See
[ADR 0111](../../docs/architecture/0111-native-passive-sun-amulet-lifecycle.md).

Version 0.59.0 advances the separate engine to kernel/observation/plan/metadata
schema 10 and ruleset v10; commands remain 1, combat profiles 6 and passives 1.
New pinned removal-plan schema 1 adds `removal_profiles[N,3]` containing
model/kind/maximum: `(205,1,3)` Broom and `(206,2,2)` Soap. The constructor
rejects invalid counts/kinds/categories, duplicates and implemented-role
collisions. Their two standalone sundry leaders join the existing selection,
target and chained-defense scheduler; held-model coverage is now 215/237.

Sundry origin 3 is distinct from weapon=0, miracle=1 and armor=2. Only Super
Mirror's origin-independent reflection applies. No numeric armor, rings,
filters or weapon/miracle-only specials defend against their zero-ATK payloads.
Targets are living enemies in the free-for-all engine, not arbitrary inventory
victims. `attack_effect_observations` gains kind 8 Broom and 9 Soap, with maximum
count as value. Before casting it uses displayed identity; afterward the actual
effect follows current source/target through reflections. $10 is catalog price,
not CP or MP cost. Raw batches may omit removal profiles and keep old leader
availability; removal-only raw batches can use the non-composition scheduler.

Broom provisionally considers all actual held cards except performed miracles,
including held trade cards: their exemption is not established. Soap considers
only actual category-4 cards with used=1. After final defense, staged native
partial Fisher-Yates samples uniformly without replacement, removes
`min(limit, eligible_count)` and preserves all surviving rows/flags/fakes/order.
A separate RNG is initialized from illness seed XOR `0x243f6a8885a308d3`;
empty/singleton choices skip tickets. Each bounded rank call uses the existing
16-attempt rejection limit. All sampling and short-pool behavior is provisional.
No manual victim-ID action phase or per-victim replacement gifts are invented.
Only source/defense uses retain their usual deferred/suppressed receipts.

`removal_snapshot[B,8]` is owned read-only diagnostic data: Broom and Soap
resolutions, their removed-card counts, empty and partial resolutions,
eligible-card total and native rank calls. Empty pools also count as partial.
It exposes no victim identities and is not a policy input. `removal_count`
counts removed cards separately from consumed source/defense cards;
`removal_effect_count` counts resolved effects. Epoch reset clears diagnostics
and reseeds the stream; lifetime totals remain. All hands/tickets/counters/ticks
and receipts stage before allocation-free whole-batch commit.

The new `simulation full-game-removal-smoke` defaults to 600 scripted one-turn
cases: 700 cards removed, 600 sundries consumed, 200 empty and 400 partial pools,
1,300 eligible cards, 500 native rank calls, 2,400 commands and 600 original
owner ticks. It produces no full matches, official replay proof or reward data.
Other report schemas advance to acquisition/combat 8, chance 5, attack-effect
4, counter 3 and revival 2. Complete-pool acquisition's legal masks/replay hash
change because Broom/Soap are now selectable; previous chance, attack-effect,
counter and revival behavior hashes stay unchanged. Full-game training/live
promotion remain blocked. See
[ADR 0112](../../docs/architecture/0112-native-joined-broom-soap-removal.md).

Version 0.60.0 advances the separate engine to kernel/observation/plan/metadata
11, ruleset v11; commands stay 1, combat 6, passive/removal 1. Economy-plan 1
pins `(236,5,10,5)` Treasure: utility kind 5 is CP (kinds 3/4 remain cures).
Held-model coverage is 216/237. Original guardian utility profiles, training
checkpoints and live controllers are unchanged.

`payment_rules.h` now shares both the source-derived CP→MP→HP debit arithmetic
and the explicitly provisional capped CP credit. Venus's requested-amount
credit behavior is unchanged. Treasure spends exactly 5 MP, credits up to 10
CP at cap 100, retains its performed miracle at the tail, then runs the single
original-owner tick, outcome checks and deferred/suppressed gift receipts.
Public eligibility uses displayed identity, affordable MP and CP below 100;
actual identity determines the committed effect. An actual CP card disguised
as another legal utility can spend MP at a full wallet without generating CP.
Hidden cross-family/unaffordable costs still fail atomically; this does not
claim complete Dream handling. Raw CP profiles require a registered miracle,
positive gain ≤100 and positive MP cost ≤100; raw old profiles can omit CP.

Owned read-only `cp_utility_snapshot[B,4]` reports episode CP utility uses,
credited CP, exact MP spent and capped uses. It is diagnostic-only, not a
policy input; reset clears it, lifetime `cp_utility_count` and `utility_cp_gain`
remain. Its state and use/credit/cost/receipts stage before the unchanged
allocation-free whole-batch commit.

`simulation full-game-economy-smoke` completes 700 scripted turns by default:
400 Treasure uses credit 2,500 CP, 100 disguised Spring uses grant HP, 200
unavailable cases pass, and all 500 retained miracle uses spend 2,700 MP.
No real match, official timing proof, trade transaction or reward dataset is
claimed. Existing report schemas advance to utility/removal 2,
acquisition/combat 9, chance 6, attack-effect 5, counter 4 and revival 3.
Acquisition's legal masks change; other established mechanics replay hashes
remain unchanged. Full-game training and live promotion stay blocked. See
[ADR 0113](../../docs/architecture/0113-native-treasure-and-shared-wallet-credit.md).

Version 0.61.0 advances the separate engine to kernel/observation/plan/metadata
12, ruleset v12; command 1, combat 6 and passive/removal/economy 1 remain.
Cost-plan 1 adds five adjacent miracle reducers, raising held-model execution
coverage to 221/237. This count excludes guardians and events; full-game
training, official fidelity and live promotion remain false.

Reducer tuples are `(model,category,standalone_ATK,standalone_DEF)`:
Staff `(46,1,12,0)`, Socks `(143,2,0,6)`, Hood `(163,2,0,9)`,
Sash `(173,2,0,12)` and Doll `(204,3,0,0)`. A reducer follows one miracle
in click order and waives that miracle's whole cost, never a whole turn or
an earlier card. Attack composition ignores its attached ATK/element.
Standalone Staff and armor keep their normal numeric roles. Current miracle
defenses are exclusive Wall/Turbulence, whose special response does not gain
numeric armor from the attachment; no general attached-DEF exemption is claimed.
Flash's one-card defense limit still applies before the attachment exception.

With cost profiles enabled, **all utilities** use existing phase 2 for public
reservation and optional attachment before confirmation. No resource, card,
receipt or tick changes on reservation. Unaffordable displayed miracles may
be selected; confirmation requires the displayed net cost. Actual identity
resolves the staged cost/effect and hidden unsupported or incompatible roles
fail atomically. Raw constructors can omit the new optional profiles, retaining
old immediate utility timing and affordability. Existing guardian arenas and
checkpoint shapes are unchanged.

Phase-2 `selected_attacks`, `attack_order` and selection previews now also
represent utilities (ATK/element zero). Public owned read-only
`utility_selection_observations[B,4]` gives active, displayed kind/value and
displayed net MP cost. Pending/chance/attack-effect views remain empty for
utility reservations. Owned read-only diagnostic `cost_snapshot[B,5]` gives
waivers, waived MP, utility/attack/defense waiver counts, never hidden models.
Epoch reset clears it; lifetime `waived_mp` and `cost_waiver_count` remain.
All effects, costs, consumed reducers, retained miracles, receipts and owner
ticks still stage before allocation-free whole-batch commit.

Undo rebuilds displayed order and prunes orphaned attachments. After 64
selection/toggle actions, affordable selections are confirm-only; an
unaffordable attack/utility retains leader cancel, and an unaffordable defense
retains selected-card undo. The global decision bound still truncates looping
policies without an invented automatic play or empty legal mask.

`simulation full-game-cost-smoke` runs 600 zero-MP scripted turns by default:
200 utility, 200 attack, 200 special-defense waivers; 3,200 MP saved, zero MP
spent, 2,800 commands, 2,000 CP gained, 2,000 HP damage, 800 consumed cards and
600 retained miracle uses. There is exactly one original-owner tick per turn,
no other-owner tick, gift or real ending. It is not a full-match or learning
probe. Reports advance to utility 3, acquisition/combat 10, chance 7,
attack-effect 6, counter 5, revival 4, removal 3 and economy 2; cost starts at 1.
Existing chance/effect/counter/revival trajectories stay unchanged. Removal's
replay hash changes only because next-actor reservation masks change; economy
and combat now account for utility selection commands. Acquisition still draws
all 237 models, with 6,299 of 41,472 draws unsupported. The local resource cap
of 100 remains explicitly provisional despite pinned client displays of 99.
See [ADR 0114](../../docs/architecture/0114-native-adjacent-miracle-cost-waivers.md).

Version 0.62.0 advances the separate engine to kernel/observation/plan/metadata
13, ruleset v13. Command 1 and existing combat/lifecycle/economy/cost plans
are unchanged. New weapon-plan 1 pins Magical Stick, Evil Broadsword and Saw
Boom Boom, raising held-model execution coverage to 224/237. Complete learning
interfaces, full-game training and live promotion remain unavailable.

Optional `complex_weapon_profiles[N,4]` rows are `(model,kind,value,element)`:
`(14,3,3,0)`, `(53,2,14,0)`, `(58,1,2,0)`; kinds 1/2/3 mean dynamic MP,
same-damage recoil and two strikes. Raw omission keeps these roles unsupported;
existing arena trajectories/checkpoint shapes are untouched.

Dynamic MP preview first computes net selected miracle costs (including
adjacent waivers), scales remaining MP, then applies ordered boosts. Preview
cost is net miracle affordability, not total MP consumption; cast spends all
actual own MP. Pending attacks are snapshots and never rescale on redirects.
Same-damage uses incoming actual HP loss only if the final target is still
living; it debits the current source and shares the weapon-derived HP-zero
revival hook. Current-source ownership after redirects and revival-before-recoil
are provisional. `hp_damage` still counts incoming damage; separate
`recoil_hp_damage` counts actual recoil, without inflating counter damage bases.
Attack-effect observation kind 10 identifies recoil.

Two strikes share one consumed/paid attack composition, with fresh defenses
each time. The original source/target/value/element are snapshotted separately
from the current redirected or counter payload. Counters finish between strikes;
the next strike restores the original snapshot, clears defense selections and
does not reroll a Fog target. If source or target is dead after reactions and
revivals, pending strikes are suppressed. Gifts and the original owner's one
tick remain deferred until family end. This compound schedule is provisional,
not inferred from the earlier evidence-only arena's immediate armor redraw.
Decision limits can truncate mid-sequence without inventing a second hit.
`resolved_attack_count` increments once for the original attack, not per strike.

Public owned read-only `complex_weapon_observations[B,4]` gives active, displayed
or revealed original-family kind, parameter and remaining strikes. Before cast
it uses displayed identity; after cast it keeps revealed family context during
counter interruptions. It exposes no hidden wallet, future target or inventory.
Owned read-only diagnostic `complex_weapon_snapshot[B,8]` gives dynamic casts
and MP spent, same-damage casts, recoil resolutions and HP lost, double casts,
strikes resolved and strikes suppressed. Reset clears episode data; lifetime
recoil totals remain. New state, payments, hands, queue changes, revival and
receipts stage before allocation-free whole-batch commit.

`simulation full-game-weapon-smoke` defaults to 720 scripted turns/3,720 commands:
weapon totals `(180,1200,240,180,1440,300,540,60)`, 6,720 incoming HP damage,
1,080 consumed cards, 120 miracle uses, 60 waivers saving 120 MP, 60 reflections
and 60 counters. Only two-player variants have the scripted real endings; these
are still turn fixtures, not full matches, official validation or training data.
Reports advance to utility 4, acquisition/combat 11, chance 8, attack-effect 7,
counter 6, revival 5, removal 4, economy 3 and cost 2; weapon starts at 1.
Established diagnostics retain their behavior replay hashes, except acquisition
whose legal masks change. Its 41,472 complete-pool draws now include 6,063
unsupported effects. See
[ADR 0115](../../docs/architecture/0115-native-complex-weapons-and-repeated-defenses.md).

## Integrated full-game development v14

Native 0.63.0 advances kernel/observation schema to 14 (command schema 1),
adding Heaven Herb and Thump-thump Tear to the shared utility scheduler.
Execution coverage is 226/237 held models; local full-game learning and official
promotion are still disabled. Existing arenas, checkpoints and live controls
retain their prior identities.

Source-pinned joined utility profiles gain `(198,6,20,0)` and `(202,7,10,0)`.
Kind 6 consumes the owned sundry, grants capped MP, inflicts Heaven using the
existing illness primitive, resolves owned revival, then applies the original
owner tick. Kind 7 consumes the sundry and samples self-healing or self-damage;
it never opens an opponent target/defense or uses percentage-attack Dark Cloud
rules. Both can reserve at full resources. Policy utility previews use only
displayed effects; actual identity resolves on confirmation. Raw profiles omit
these roles if not supplied, and optional reservation omission remains supported.

The Tear's local 50/50 probability is **not established by the sources**. Its
staged stream uses the episode illness seed XOR `0x13198a2e03707344`, independent
of illness progression, gifts, combat, chance, counters and removal. Compound
ordering and the local cap100/client99 gap remain explicitly provisional.

All utility consumption is staged before applying effects so a same-command
lethal effect can consume an actual owned Sun Amulet from the surviving hand.
No idle/dead-seat revival or resource/status reset is introduced. Direct utility
damage adds cause 6 to the passive hook: owned diagnostic `revival_snapshot`
changes from `[B,7]` to `[B,8]`, appending `utility` without moving earlier fields.
No training/checkpoint compatibility is inferred from this diagnostic extension.

Owned read-only `compound_utility_snapshot[B,10]` records Herb uses, actual MP
gain, capped uses, illness applications/loss, and Tear uses, heal outcomes/gain,
damage outcomes/loss. It is diagnostic-only, never an input exposing future
random outcomes. Lifetime `utility_hp_damage` excludes incoming attack damage
and periodic illness loss; episode reset clears rows but preserves lifetime
counters. Whole-batch rejection rolls back random tickets, effects, revival,
hands, owner ticks, receipts and every counter before nonthrowing commit.

`simulation full-game-compound-utility-smoke --batch-size 768 --players 3 --seed 67`
checks twelve scripted cases with public legal commands. It completes 768 turns
and 1,536 commands, 512 Herb and 256 Tear uses, 96 revivals, 8,000 MP gain,
900 Tear HP gain and 855 direct utility HP loss. It has no extra owner ticks,
attacks, gifts or limit truncations. This is not full-match training/evaluation.
At v14, complete-pool startup had 5,792 unsupported draws out of 41,472;
11 held models and the event/learning workflows still remain. See
[ADR 0116](../../docs/architecture/0116-native-compound-utility-effects.md).

## Integrated full-game development v15

Native 0.64.0 advances kernel/observation/plan/metadata to 15, leaving command
schema 1 and previous component profiles unchanged. New danger-plan schema 1
adds `danger_profiles[N,4]`: model/kind/base-attack-or-fixed-damage/element,
`(94,1,30,5)` Pestle and `(209,2,99,0)` Mortar. Joined execution coverage is
228/237 held models, not full-game training or fidelity. Raw constructors can
omit the optional profiles; invalid categories, counts, bounds, duplicates and
implemented-role collisions fail before construction.

Pestle keeps public ordered selection and the existing phase-3 requested enemy
target envelope, but the actual cast overrides that placeholder. Without a
living actual Mortar holder it provisionally samples all living seats uniformly,
including its source, ignoring Fog. Initial self-hits resolve composed attack
immediately with no response; normal enemy hits enter the existing Light
compatibility/filter/reflect/counter scheduler. A later redirect to the source
is a fresh normal defense, not another automatic self-hit. Normal ordered
boosts and adjacent waivers are source-derived general composition rules, but
their joined Pestle timing is not officially verified.

Mortar provisionally prioritizes equally weighted living actual owners, not
held copies. The first actual held copy is consumed, survivor order is stable,
and the holder loses up to fixed 99 HP directly, not a composed ATK99 payload.
There is no response, numeric mitigation or invented counter selection.
Fake/displayed identities never determine eligibility. Automatic loss uses
the shared owned Sun hook before ending checks. Attraction is checked only at
the initial cast; redirects and counters never re-sample or consume another
Mortar. Dead owners are excluded. Mortar ownership/timing/probability and the
local cap100/client99 gap remain explicitly provisional.

Dedicated episode streams are illness-seed XOR `0xa4093822299f31d0` for ordinary
Pestle targeting and XOR `0x082efa98ec4e6c89` for multiple Mortar owners. A single
holder consumes no random ticket. Reservation/cancellation do not sample.
All RNG, hands, costs, revival, counters, receipts and ticks stage before the
whole-batch nonthrowing commit; rejected late rows can retry identically.

Owned policy `danger_observations[B,3]` exposes active/base ATK/element only
from displayed selection or revealed response context. It exposes no hidden
holders, future targets or tickets. `passive_observations[B,capacity,2]` keeps
its shape and uses displayed kind/value: Sun=1/10, Mortar=2/99. Its metadata
field is now `displayed_value`, not a misleading revival-only name. Neither
passive is a manual use choice. Diagnostic-only `danger_snapshot[B,8]` records
casts, ordinary target draws, self targets, attractions, multi-owner draws,
attracted self targets, automatic resolutions and automatic HP loss.
Episode reset clears these rows and reseeds streams; lifetime `danger_count`
and `automatic_danger_hp_damage` remain. Existing checkpoints/live controls are
not switched or declared compatible.

`simulation full-game-danger-smoke --batch-size 512 --players 3 --seed 67`
checks eight scripted cases using public legal commands. It completes 512
turns, 1,631 commands, 128 random draws, 384 attractions and 145 revivals;
all 512 original owners tick once, with no other-owner ticks or limits. This
is not complete matches, reward data or learning evidence. Complete-pool
startup still draws all 237 models; unsupported draws fall to 5,649/41,472.
Nine held effects plus trading, guardians/events, full hidden-family handling
and the complete policy/training interface remain. All training readiness,
official verification and live promotion flags stay false. See
[ADR 0117](../../docs/architecture/0117-native-pestle-mortar-targeting.md).

## Integrated full-game development v17: Hat and shared attack families

Native 0.66.0 advances kernel/observation/plan/metadata to 17, command remains 1,
and `FULL_GAME_ATTACK_FAMILY_SCHEMA_VERSION` starts at 1. Joined held-model
coverage is 230/237; full-game readiness, fidelity and promotion stay false.

Optional `dream_defense_profiles[N,4]` joins `(178,14,3,2)` DEF14/Wood/Dream.
Confirmed actual Hats apply Dream and provisionally replace every remaining
held row, including performed miracles, preserving count but issuing fresh IDs,
weighted models, unused miracle flags and fresh same-category disguises.
Dream precedes redraw; Sun precedes final-death suppression; mixed self-effects
follow click order. Gift weights are required even with automatic receipts off.
Redraw isn't a gift, overflow, resource change or another owner tick.
Dedicated illness-seed XOR streams are `0x452821e638d01377` (model) and
`0xbe5466cf34e90c6c` (disguise). `dream_defense_snapshot[B,8]` is diagnostic;
lifetime `redraw_count` and `redrawn_count` persist across episode resets.
See [ADR 0118](../../docs/architecture/0118-native-dreaming-hat-redraw.md).

Optional `ascension_profiles[N,6]` joins `(112,1,25,30,75,5)`:
model/base-ATK/base-rate/dying-ATK/dying-rate/Light. Its base cast preserves the
existing provisional one-enemy target-first chance scheduler. Actual held Bows
fire on final positive-to-zero edges after Sun, never dead setup or low HP.
Provisional held-copy order and ascending other living seats produce separate
75%ATK30 shots; later-dead recipients are skipped. A dedicated illness-seed XOR
`0xc0ac29b7c97c50dd` hit stream honors target Dark Cloud without a ticket.

Original recipients, repeated strikes, counter payloads and post-death shots
share one staged LIFO queue. Nested reactions finish ahead of pending siblings,
gifts and the single original-owner tick. Only post-death tasks permit dead
sources. Reflection toward a dead source consumes the response and resolves
empty, never entering a dead actor's defense. Periodic/worsening death queues
drain after the already-completed tick, before endings/turn limits; a persistent
tick flag prevents double ticking. The decision limit still bounds unfinished
families. Queue storage is bounded by players²×capacity+2; counter subqueues
retain their existing players×capacity bound.

`attack_family_snapshot[B,16]` is owned/read-only diagnostic state: enqueued,
started, resolved, suppressed, missed, peak depth, final death edges, actual
Bows consumed, death recipients/hits/misses/suppressions/HP loss, queued count,
active kind and owner-already-ticked. Kinds are counter1/original2/post-death3.
No future ticket, hidden ownership or pending queue is a policy feature.
Displayed passive view adds kind3/value30 without revealing actual Bow owners.
Lifetime `ascension_count` counts consumed Bows, not recipients, and
`ascension_hp_damage` counts their actual attack loss. Original and counter
resolution counts remain separate. All queues, streams, hands, wallet/status
effects, receipts and counters stage before whole-batch nonthrowing commit.
Reset clears episode queues/statistics and reseeds streams, retaining lifetime
counters and preserving previously returned owned arrays.

`simulation full-game-attack-family-smoke --batch-size 512 --players 3 --seed 67`
checks six scripted families: final death, Sun, periodic death, nested death,
Hat defense and repeated-strike suppression. It resolves 1,364 of 1,449 queue
tasks and suppresses 85 dead-recipient repeats, with 937 post-death recipients,
86 revivals, 85 redraws, 512 original-owner ticks and no extra ticks or limits.
These are turns, not full-game training/evaluation. Acquisition startup remains
all 237 held models; unsupported draws fall to 5,494/41,472. Seven held effects
and the complete event/policy/learning workflows remain. See
[ADR 0119](../../docs/architecture/0119-shared-native-attack-family-queue.md).

## Integrated full-game development v18: Mirage recipient families

Native 0.67.0 advances kernel/observation/plan/metadata to 18 and the attack
family queue contract to 2; command remains 1. Current execution coverage is
231/237 held models. Full-game learning, fidelity and promotion stay false.

Optional `area_profiles[N,2]` joins `(232,5)` model/cost as an addition-only
non-chance weapon component. It changes neither ATK nor element and remains
eligible for adjacent cost waiver. The source-pinned cost is applied before
Magical Stick scales/consumes remaining MP. Fog does not retarget an area cast.
Provisional duplicate copies pay/perform individually but fan out only once.

The shared queue snapshots ascending other living seats. Each recipient gets
one original payload, or two consecutive payloads for Saw Boom Boom, with
nested counters/Bows resolving before pending siblings. Original-source or
nominal-recipient death suppresses remaining ordinary shots. Cast payment,
consumption and one original-owner tick apply once to the whole family. Gifts
remain deferred to its ending. The original rate/origin/effect context is fixed
per task, not overwritten by intervening counter or death tasks.

Pestle targeting is now a per-task preparation step. Non-area casts preserve
the prior single-shot behavior; provisional area shots reroute after their
nominal recipient passes its liveness check. Actual Mortar priority/first-copy
consumption, direct 99 loss and initial self-hit no-response semantics remain;
redirected responses do not reroll. Original Pestle cast counters count casts,
while draw/attraction/automatic resolution counters count generated shots.
Multiple direct losses in one command aggregate HP and Darkness-finish counts.

Owned/read-only `area_observations[B,3]` exposes active, displayed-or-revealed
selected component count, and all-enemies flag. It reveals no future recipient
count, queue length, hidden roles or random state. `complex_weapon_observations`
uses recipient-local remaining strikes rather than private total area shots.
Diagnostic `area_snapshot[B,8]` records casts, components, recipient slots,
scheduled/resolved/suppressed shots, original incoming HP loss and Fog bypasses.
Lifetime `area_count`/`area_hp_damage` survive resets; episode data/queues clear.
Whole-batch staging includes these counters and all per-shot targeting draws.

`simulation full-game-area-smoke --batch-size 512 --players 3 --seed 67`
checks ordinary, repeated, dynamic-MP, recoil, waived and counter scenarios:
512 casts/turns, 1,196 originals plus 85 counters, 13,632 original incoming HP
loss, 3,410 MP spending and exactly 512 owner ticks. It is not a full-match
learning probe. Complete-pool startup unsupported draws fall to 5,423/41,472.
The six missing held models are Exchange, Sell, Buy, Guardian Pot, String of
Fate and Release. All event/apocalypse/team/reward and complete neural/learning
acceptance requirements remain. Previous behavioral replay hashes are unchanged;
metadata hashes are explicitly versioned. See
[ADR 0120](../../docs/architecture/0120-native-mirage-and-multi-recipient-families.md).

## Integrated full-game development v19: multi-card Discard

Native 0.68.0 advances kernel/observation/plan/metadata to 19. Command1 and
attack-family2 remain unchanged. Optional `discard_model_ids[N]` joins the
128 complete eligible held models: all nonweapons except Sun208/Mortar209.
The source factory enables this virtual pre-Apocalypse control; raw omission
preserves unsupported fixtures. This is removal coverage, not execution of
the six still-missing held abilities; the artifact-effect count remains231/237.

Choice `capacity+1` reserves Discard in ready phase and cancels it in phase7
(removal-selection). Slot+1 toggles any eligible own displayed row; choice0
confirms a nonempty selection. `FULL_GAME_MAX_DISCARD_ACTIONS=64` bounds toggles;
afterward only nonempty confirm or cancellation remain, never an empty mask.
Cancel drops the reservation/selection without removal, cost, tick or gift.
Virtual Discard is not inserted into owned inventory or faked as a card.

Confirmation rechecks actual eligibility before removing all selected rows.
Survivors retain original order, IDs, fake identities and performed flags.
Performed miracles are discardable; Sell/Buy exclusions are not generalized.
Discard doesn't perform miracles, consume an artifact use, pay its listed
price or generate victim receipts. Existing illness/Sun/Bow hooks run during
the one original-owner tick. Nested post-tick shots finish before endings
without another tick. These timing/receipt assumptions remain provisional.

`discard_observations[B,4]` exposes active, selected count, toggle count and
maximum toggles; `discard_order[B,capacity]` exposes only own selected slot IDs.
Diagnostic `discard_snapshot[B,6]` records reservations, toggles, cancels,
completed discard turns, removed cards and removed performed miracles.
Lifetime `discard_count`/`discarded_card_count` are separate from consumed-use,
miracle-use and Broom/Soap removal counts. Whole-batch staging includes removal,
ticks, random worsening, Sun/Bow reactions and counters. Reset clears episode
state/queues and preserves lifetime counters and owned readonly old views.

`simulation full-game-discard-smoke --batch-size 512 --players 3 --seed 67` checks
six scripted scenarios: ordinary, performed miracle, multi-card, periodic Sun,
periodic Bow and cancellation. The default removes767 cards in512 turns, with
85 Sun revivals,85 Bows/170 post-tick recipients,2,386 commands, no replacement
receipt/cost/extra tick/limit exit. These aren't full matches or learning data.

Historical replay hashes that include ready masks change for the new public
control. Excluding only that new mask column reproduces all14 old behavioral
fingerprints. The historical utility driver now selects actual hand slots,
not virtual controls; broader mechanics have their own phase-aware probes.
Apocalypse/Sacrifice, full trade/event/team/reward and neural interfaces remain
outstanding, and readiness/fidelity/promotion remain false. See
[ADR 0121](../../docs/architecture/0121-native-multi-card-discard.md).

## Integrated full-game development v20: guardian post-turn lifecycle

Native 0.69.0 advances kernel/observation/plan/metadata to20 and shared-family
schema to3; command1 remains. Optional `guardian_profiles[N,10]` joins40 standard
effects, including Diamond Axe264's weapon origin. `summon_profiles[N,2]` joins
Guardian Pot201/cost0 and Release239/cost15; these aren't added to the historical
15-row base utility profile/hash. The source factory enables both tables.
Held-effect coverage is233/237; standard guardian coverage is40/42, not a claim
that all events or full-game learning execute.

Each seat owns at most one `(group+1,identity)` guardian. Zero is absence;
groups1..10 are Mars/Mercury/Jupiter/Saturn/Uranus/Pluto/Neptune/Venus/Earth/Moon.
Trusted `seed_guardians` is setup-only, batch-atomic, and not a learner action.
Actual summons preserve all ten uniformly sampled provisional outcomes and
replace old identity. Release is performed/retained and accepts adjacent waiver;
Pot is consumed without an invented price charge. All uses retain their existing
deferred receipt accounting. Earth/Moon activation currently rejects atomically
with an explicit unsupported producer error; they aren't hidden from sampling.

Once the original turn's responses/deaths and owner tick finish, other living
owned guardians get25% checks in provisional ascending seat order. Standard
effects sample their pinned relative weights, fix payload/target, and enter
family4. Utilities resolve automatically; attacks and enemy money/curse effects
use normal typed/filter/special defenses, redirects and counters. Generic
guardians have origin4; Diamond Axe has weapon origin0. Nested reactions finish
before siblings. No guardian event recursively creates another turn or trigger
wave; gifts/endings/limits wait for the post-tick queue to drain.

HP/MP/CP gains and full cure, absorption, curses, group CP gifts, Bribe and Fine
are joined. Fine shares CP→MP→HP debit/requested-credit arithmetic; caps100 and
compound timing remain provisional. Every positive HP debit can trigger10%
guardian departure after Sun; final death clears ownership without a departure
ticket. Queued tasks whose source dies or guardian identity changes suppress
normally. Departure and activation/model/target/hit/summon streams are separate.

Owned/read-only diagnostics are `guardian_snapshot[B,P,2]`,
`guardian_statistics[B,19]` and `guardian_model_counts[B,40]`. Policy
`guardian_observations[B,9,4]` projects cyclic seat/present/visible/group, hiding
others under Fog. `guardian_effect_observations[B,4]` reveals only the current
active model/source/target, never pending models/queue/tickets/identities.
Lifetime summon/activation/resolution/HP-damage/departure counters survive reset;
episode ownership, queues, counters and streams clear. All guardian state,
automatic effects, RNG, hands and receipts stage before nonthrowing batch commit.

`simulation full-game-guardian-smoke --batch-size 4096 --players 3 --seed 67`
checks all eight standard groups with unforced activation/model/target streams,
Dark Cloud targets to isolate effects, and one enemy turn per environment.
It observes all40 effects through1,045 activations/4,928 commands,106 Suns and
exactly4,096 owner ticks. These are scripted turns, not full games/training.
Source hashes and all42 Bible records are pinned; official guardian payloads
remain too redacted to verify general mechanics. The missing held abilities are
Exchange/Sell/Buy/String of Fate; special guardians, devils/phenomena,
Apocalypse/Sacrifice, teams/rewards and full neural interfaces remain. Readiness,
official fidelity and promotion stay false. See
[ADR 0122](../../docs/architecture/0122-native-guardian-post-turn-lifecycle.md).

## Integrated full-game development v21: post-gift devil lifecycle

Native0.70.0 advances kernel/observation/plan/metadata to21 and shared-family
schema4, preserving command1 and old arenas/checkpoints/live controls. Optional
`devil_profiles[N,4]` are `(model,appearance-percent,kind,value)` for240..244.
The pinned adapter supplies all5 at7/5/3/5/5%, but runtime activation requires
an explicit `apocalypse_after_turns>0`. Default0 keeps prior gift behavior;
no official threshold is inferred. First9-card deals remain pre-Apocalypse.

In enabled experiments, completed-turn receipts enter automatic family5 after
the original tick/guardian wave and existing ending/limit checks. The owned gift
arrives before its single0..99 appearance ticket. Direct damage handles Sun,
guardian departure and Bow before queued sibling receipts. Trickster samples
up to2 actual nonmiracles/performed miracles, removes stable survivors without
victim replacements, and can steal Sun/Mortar unlike virtual Discard. Charity
chooses HP/MP/CP uniformly including capped choices. These order/sampling/cap
choices remain provisional; devils don't open defenses or tick another owner.

Post-revival gift waves are iterative, with a2*players*capacity receipt limit
per original turn and a batch-atomic error if exceeded. Dead queued recipients
suppress their receipts. Newly owed receipts wait until the current family wave
drains; endings/limits can suppress them. Discard is disabled after experimental
Apocalypse instead of silently pretending to be the unimplemented Sacrifice.

Policy `apocalypse_observations[B,3]` contains enabled/active/configured threshold,
not hidden future events or tickets. Readonly diagnostic `devil_snapshot[B,18]`
and `devil_model_counts[B,5]` record episode counters; lifetime appearance/HP-loss/
theft counts survive reset. `revival_snapshot` now has9 columns, adding the
separate devil cause. All16 prior smoke fingerprints match when that new zero
column is excluded; changed storage/metadata hashes are versioned explicitly.

`simulation full-game-devil-smoke --batch-size 4096 --players 3 --seed 67` uses
complete weighted9-card starting hands, the first affordable public action and
forgiven responses for one original turn. It records999 appearances across all5
models,10,010 devil HP loss,384 stolen cards,14,620 commands,4,096 ticks and no
pending/limit/extra tick. The nine-seat CLI probe also finishes4,096 turns.
These are bounded first turns, not matches/learning or official validation.
All readiness/fidelity/promotion flags remain false. Held coverage stays233/237;
Earth/Moon, phenomena, trade/Fate, full Apocalypse/Sacrifice, teams/rewards,
hidden resolution and neural interfaces remain. See
[ADR 0123](../../docs/architecture/0123-native-post-gift-devil-lifecycle.md).

## Integrated full-game development v22: phenomena and forced control

Native0.71.0 advances kernel/observation/plan/metadata to22 and shared-family5;
command1 and the historical combat/base-utility profile hashes are preserved.
Optional `phenomenon_profiles[N,5]` and `fate_model_ids[N]` join all10 event
models287..296 and held207. The adapter supplies the complete pinned tables;
raw omission preserves unsupported fixtures. Held-route coverage becomes234/237,
but Earth/Moon activation, trading and other full-game dependencies remain.

Fate is a consumed cost0 sundry, not a $3 use charge. At confirmation a dedicated
native stream chooses uniformly among all10 provisional outcomes. Global effects
apply to living players, matching the pinned client's `aG` scope. Afterglow sets
Fever, not illness infliction/worsening. Tornado assigns HP1, not an attack or
departure event. Mushroom adds3 turns of lost control before the owner tick.
Warm Current heals one native-selected living seat; Gold Mountain collects living
CP and caps the selected recipient at100, separately recording cap loss.
Recipient sampling and these compound interpretations remain provisional.

Magnetic Storm shuffles held actual models across living seats, preserving each
seat's remaining card count. Fresh monotonic IDs avoid cross-owner setup-ID
collisions. Performed flags clear and Dream disguises resample by recipient;
all of these ownership/timing choices are explicitly provisional. Dead hands
remain unchanged. Solar Eclipse uses shared all10 guardian summons/replacement;
immediate Earth/Moon activation still fails atomically, never gets filtered out.

Tub/Black Hole attacks use shared-family6, generic origin5, revealed model/current
source/target, normal typed/filter/special/redirect/counter/Sun/Bow reactions and
one original-owner tick. Target/source semantics are provisional. Utility
reservation state now clears on entering any family, fixing hidden response
views after a completed utility generates an attack.

Confusion's ready-only forced0 controller samples a bounded native pool of actual
single plays/discards/legal Prayer, consumes duration before effects, and does
not hide unsupported held trades. No toggle/selection loop is created. Defense
choices stay voluntary. Pinned final-death handling clears duration; Sun retains
it. Trusted `seed_confusion` is setup-only and batch-atomic. Policy
`control_observations[B,9,4]` respects cyclic seats/Fog; `policy_gradient_masks[B,1]`
is false for forced-ready/setup/finished rows. Capture it before stepping, or use
the validated readonly float32 adapter weights. This does not implement or enable
the complete trainer. Diagnostics are `confusion_snapshot[B,17]`,
`phenomenon_snapshot[B,23]`, `phenomenon_model_counts[B,10]`; revealed-only
`phenomenon_observations[B,4]` exposes no future draw, victim or private identity.

`simulation full-game-phenomenon-smoke --batch-size 512 --players 3 --seed 67`
keeps all10 native outcomes and reports507 completed first turns plus5 explicit
Solar/Earth/Moon dependency failures. The4096/nine-seat run reports3957 completed
first turns and139 dependency failures, no extra ticks/limit exits in completed
rows. Known failed rows aren't retried or relabeled as success. Diagnostic
rollback snapshots are captured once per failed batch, not once per successful
row. These probes are not full episodes, reward/teacher data or promotion gates.

All readiness/fidelity/promotion flags remain false; old arenas/checkpoints/live
controls are unchanged. The prior16 behavioral fingerprints remain unchanged
except startup's new Fate mask (masking only Fate reproduces v21) and the
complete-pool devil probe's newly executable Fate turns. See
[ADR 0124](../../docs/architecture/0124-native-phenomena-and-forced-control.md).

## Integrated full-game development v23: numeric Exchange

Native0.72.0 advances kernel/observation/plan/metadata to23. Command1 remains
six integers; shared-family5 is unchanged. The appended optional
`exchange_model_ids` registers exactly `[3]`; omission preserves incomplete raw
fixtures. The source factory supplies it. Held-route coverage is235/237,
not full-game readiness: Sell/Buy transfers and Earth/Moon producers remain.

`FULL_GAME_TRADE_CHOICE_SCHEMA_VERSION=1` defines phase6 mode1:
0 confirm,1 MP+10,2 MP+1,3 MP-1,4 MP-10,5 CP+10,6 CP+1,7 CP-1,
8 CP-10,9 cancel. Each increment transfers one-for-one with HP and clips to
available funds/headroom. The existing mask width is unchanged. Amount edits
are bounded by `FULL_GAME_MAX_TRADE_ACTIONS=64`; confirm/cancel survive the
bound. A preview does not debit resources, consume cards, trigger death or tick
the owner. Confirmation uses the actual owned Exchange once; cancel leaves
resources/inventory/ticks unchanged. Wrong hidden actual roles reject the whole
batch atomically, without inspecting them at reservation or cancellation.

`trade_observations[B,7]` is active/mode/previewHP/previewMP/previewCP/edits/
reserved displayed slot. It is zero outside the interactive trade phase.
`trade_snapshot[B,10]` counts reservations/edits/cancels/commits, four net
MP/CP conversion directions, forced commits and allocation draws. Views are
owned readonly snapshots; reset clears state. `revival_snapshot` appends an
Exchange cause column (now10), without shifting the nine older columns.
This explicit observation migration does not imply checkpoint compatibility.

The pinned client uses ±10/1 controls and submits final MP/CP balances. Its cap
is99; this engine deliberately retains its provisional100 cap until an explicit
whole-engine migration. Price5 is not an Exchange fee. Zero-HP conversion uses
the shared Sun/final-death/Bow queue before exactly one original-owner tick,
with a separate cause8. That timing remains provisional. Conversion is not
attack damage, payment-waterfall loss or guardian-damage departure. Confusion
uses bounded native uniform sampling over conserved final wallets, from a
dedicated staged stream, with no policy amount prompts/gradients; that sampling
is also provisional. Voluntary amount commands retain policy weight1.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-exchange-smoke \
  --batch-size 512 --players 3 --seed 67
```

The default ten-scenario diagnostic completes512 scripted turns/owner ticks,
1,638 commands,51 Sun revivals and102 Bow shots/3,060 incoming damage.
These are not full episodes, learning labels or strength evidence. All gates
remain false. See [ADR 0125](../../docs/architecture/0125-native-numeric-exchange.md).

## Integrated full-game development v27: Sacrifice and tagged replacements

Native0.76.0 advances kernel/observation/plan/metadata to27 and family schema8.
Six-column command1 and trade-choice2 are unchanged. Append optional
`sacrifice_enabled=false`; the complete source factory passes true. Raw opt-in
requires discard and gift profiles. Apocalypse remains opt-in with its labeled
provisional completed-turn threshold; zero disables it.

Phase7 keeps slot toggles, nonempty confirm0 and cancelcapacity+1. Before
Apocalypse it performs Discard; afterward it performs Sacrifice. Both share128
eligible held models; masks use displayed identities and confirmation validates
all actual identities atomically. `discard_observations[B,5]` retains the first4
fields and appends public virtual model1/2. It is zero outside selection.

Sacrifice removes without consumption/performance or price/MP charge. It
requests one provisional complete-pool gift per removed card, after the single
owner tick/guardians. Family5 carries a private Sacrifice attribution tag;
ordinary Sun/Bow/use receipts remain distinct. Receipt Dream/caps/devils,
nested deaths/Bows, dead/ended suppression, decision-limit pending queues and
the finite post-turn receipt bound remain joined. Forced confusion can choose
Sacrifice without creating learner selection steps or policy gradients.

Readonly private diagnostics `sacrifice_snapshot[B,9]` hold reservations,
toggles, cancels, turns, removed cards/performed miracles, requested/delivered/
suppressed replacements. `sacrifice_model_counts[B,237]` counts actual tagged
receipts, including cards immediately stolen by a devil, not only final holdings.
Queued pending tagged receipts remain the conservation difference until drained
or explicitly reset, not fictitious successful deliveries.

`simulation full-game-sacrifice-smoke --batch-size 4096 --players 3 --seed 67`
checks4096 Sacrifice turns plus4096 preparation turns:12288 replacements,
24576 commands, all237 receipt models and all five devils. It is not full games
or training evidence. Current catalog/client bytes match the reviewed pins;
server replacement quantity/timing, threshold, caps and compound order remain
provisional. Full-game readiness and live promotion are false. See
[ADR 0129](../../docs/architecture/0129-native-sacrifice-and-tagged-replacements.md).

## Integrated full-game development v26: generated guardian direct actions (historical)

Native0.75.0 advances kernel/observation/plan/metadata to26 and family schema
to7. Six-column command1 and numeric trade-choice2 remain unchanged. The
source factory supplies all237 generated pool rows and new
`guardian_action_profiles[N,2]` `(model,route)`; raw incomplete configurations
fail atomically on activation. Route codes are direct attack1, utility2,
Exchange3, Sell4, Buy5, Earth Drop6 and Moon Blade7. Complete source route
counts are130/18/1/1/1/82/4. No summon or generated outcome is filtered.

Generated producer family8 validates ownership/identity before dispatch;
model-only attack family9 uses shared responses, effects and nested reactions.
Utilities and phenomena enqueue children without recursively ticking/resuming.
No real held use, performed miracle, ordinary MP charge or replacement gift
is invented. The special MP weapon58 still debits all ownerMP once; defenders
pay their actual selected costs. No living enemy means explicit suppression,
not a self-hit or debit. Moon Blade286 has baseATK10; Aura231 doubles it,
Mirage232 adds recipients and Wall233/Turbulence234 preserve its base attack.
All this construction and compound timing remains provisional.

Generated Exchange uses a dedicated cap100 allocation stream. Sell generates
a second weighted Earth parcel in private custody owner−2; undelivered parcels
retire, never refund into a real hand. Buy uses a native original-buyer choice;
after reflection the new current source gets voluntary purchase phase6.
Owned trades and their checkpoint/control contracts remain unchanged.

`guardian_generated_snapshot[B,23]` preserves the first7 diagnostic columns
and adds Moon/routes/attack/debit/custody accounting. Both private readonly
`guardian_generated_model_counts[B,237]` and
`guardian_generated_execution_counts[B,237]` index3..239; the former includes
suppressed producers, the latter counts dispatched effects, not resolved hits.
`generated_action_observations[B,6]` reveals only the current generated
producer/model/virtual leader/source/target. Future models, custody IDs and RNG
stay private. Every queued shot restores its own weapon/area/danger metadata;
nested counters cannot inherit stale complex-weapon or Mirage views.

`simulation full-game-generated-smoke --guardian mixed --batch-size 4096
--players 3 --seed 67` completes4096 scripted first turns,1045 generated
dispatches and4911 commands, not full matches/training. All237 route tests and
the complete30-model Moon probe are separate evidence, not official validation.
Source factory joins42 guardian model labels; full interaction, learning,
official fidelity and promotion gates remain false. See
[ADR 0128](../../docs/architecture/0128-native-generated-guardian-direct-actions.md).

## Integrated full-game development v25: generated Earth Drop receipts (historical)

Native0.74.0 advances kernel/observation/plan/metadata to25; command1,
shared-family6 and trade-choice2 are unchanged. Append optional
`guardian_generated_profiles[N,4]` as `(group,model,category,weight)`.
Groups9/10 are Earth/Moon; models must be registered3..239, categories must
match actual inventory roles, and only Moon accepts miracles. Native subsets
are for focused tests; the source factory supplies all237 pinned rows:
Earth207/weight470 and Moon30/weight30, SHA
`f3dba9f996e4c41eb61a4e0c16630713974e5d75c422d25038b12a0ee61bc3f8`.
Using gift weights as guardian probabilities is explicitly provisional.

Earth uses one generated Drop receipt in shared-family4, zeroATK/origin4,
effect12 carrying the revealed artifact model. Native enemy targeting,
single-artifact construction and receipt timing remain provisional. Super
Mirror changes the current source/recipient; no ordinary held use, MP charge,
miracle performance, transfer accounting, replacement gift or devil trigger
is invented. `receive_artifact` shares fresh IDs, actual receiver-Dream and
explicit hand-cap/oldest eviction with gifts and accepted trades. A queued
dead/replaced guardian suppresses without delivering its artifact. Original
turn ownership, one tick, queue conservation and atomic rollback are retained.

`guardian_generated_snapshot[B,7]` contains Earth casts, model draws, receipts,
disguises, evictions, blocked and suppressed tasks.
`guardian_generated_model_counts[B,237]` indexes held models3..239, with zero
Moon counts until that producer is joined. Both are owned readonly diagnostics,
not policy features; current `attack_effect_observations` reveals the artifact
only in the active response. Future queued models/IDs/RNG stay private.
Reset clears these counters; old returned arrays remain intact.

New illness-seed XOR streams are generated model `0x2ba9c55d741831f6` and
receipt disguise `0xce5c3e169b87931e`. Standard guardian/gift/trade streams
and behavioral replay pins are unchanged outside newly supported Earth paths.

`simulation full-game-earth-smoke --batch-size 4096 --players 9 --seed 67`
finishes4096 scripted turns with1045 receipts,519 Dream disguises,5141 commands,
194 observed artifact models and one original-owner tick each. Unit tests
separately cover all207 Earth models across2/3/9 seats, redirects, native
weight tickets, caps, nested death suppression, private views and rollback.
The source factory now joins41/42 guardian models; Moon remains an explicit
atomic development error and is never filtered from summons. No full-game
readiness, official fidelity, neural compatibility or promotion flag changes.
See [ADR 0127](../../docs/architecture/0127-native-earth-drop-and-weighted-generated-pools.md).

## Integrated full-game development v24: Sell/Buy custody and responses

Native0.73.0 advances kernel/observation/plan/metadata to24, shared-family to6,
and numeric trade-choice schema to2. Six-column command1 and Exchange's menu
remain unchanged. The appended optional `market_profiles[N,3]` supplies
`(model,trade-kind,raw-price)` for every registered held model and registers
Sell4/Buy5. The source adapter pins all237 prices; omission preserves incomplete
raw fixtures. All237 held routes are joined, not full game/training readiness.
Earth285/Moon286 still reject atomically when sampled; all gates stay false.

Phase6 mode2 selects an owned unused sale card by slot+1,0 confirms the selection
and capacity+1 cancels before use. Selection edits stop at64, retaining cancel.
Phase3 chooses the living enemy (Fog samples natively). Cast uses only the trade
leader; the sold card moves into private custody, not artifact consumption.
Family7/origin6 has ATK0 and admits source-pinned Super Mirror, not numeric armor,
ordinary weapon/miracle defenses, filters or damage counters. Reflections keep
the parcel and change the current source and target, preserving one original tick.

Buy's eligible unused-card offer is sampled natively **after** defense, reserved
into private custody and revealed to the current source in phase6 mode3.
Choice0 refuses;1 buys. Performed miracles are excluded and an empty target
resolves without inventing a purchase prompt. Refusal returns the same original
ID/disguise/unused card at its original owner's tail, without payment or gift.
Accepted transactions receive the real item under a fresh native ID, provisionally
refake for receiver Dream and apply the existing explicit hand-cap/overflow policy.
Then shared CP→MP→HP payment and capped requested-price credit precede actual
Sun/final-death/Bow reactions. That compound order, source/ownership semantics,
uniform draws, cap100 and overflow are provisional. Transfer is not an item use,
income attack, counter, replacement gift or miracle performance.

`market_observations[B,9]` is active/kind/stage/current-source/target/
selected-sale-choice/revealed-model/revealed-price/edits. A Buy item remains hidden
until defense finishes. Only owned displayed slots affect selection legality;
hidden mismatched trade leaders reject atomically at cast. The existing seven
trade fields distinguish the three menus without exposing another owner's old
private slot. `market_snapshot[B,25]` holds event/payment counters;
`market_escrow_snapshot[B,6]` is trusted original-owner/ID/actual/fake/performed/
present diagnostics, never policy input. All arrays are owned readonly snapshots.
Truncation preserves unresolved custody diagnostically until reset; it is not
reported as transfer, refund or a completed turn.

Native confusion samples a sale parcel/target and the original buyer's purchase
decision without extra learner prompts; a reflector becomes a voluntary current
buyer. Old optional fixtures retain explicit unsupported-role errors. Dedicated
staged streams keep ordinary gift/combat/illness schedules independent.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-market-smoke \
  --batch-size 512 --players 3 --seed 67
```

The default ten-scenario probe records512 original ticks,410 transfers,51 refunds,
102 reflections,102 revivals and2,560 commands. These are scripted mechanics
turns, not full matches, strength, training labels or promotion. See
[ADR 0126](../../docs/architecture/0126-native-sell-buy-custody-and-responses.md).
