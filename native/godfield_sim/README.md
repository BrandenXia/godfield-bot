# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
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
Sacrifice is excluded. The planned 48-action training adapter/migration is
still pending. See
[ADR 0091](../../docs/architecture/0091-pass-only-diagnostics-and-discard-component.md).

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
