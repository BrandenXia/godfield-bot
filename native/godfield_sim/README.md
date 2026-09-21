# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `dark-cloud-resource-hand`, includes elemental multi-card
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

The unobserved same-damage/reflection, attack-twice booster/reflection,
random-target booster/reflection, and damage-triggered Fog/Flash/Dark Cloud
redirect or Fever Mask interactions remain masked. Dream and multiplayer Fog
targeting remain outside the represented state. Dark Cloud counterattacks and
guardians remain excluded. See ADR 0002 and ADRs 0029 through 0049 in the root
project for the interface and safety boundary.
