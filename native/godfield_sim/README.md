# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `heaven-herb-resource-hand`, includes elemental multi-card
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

The unobserved same-damage/reflection, attack-twice booster/reflection,
random-target booster/reflection, and status/reflection interactions remain
masked. Fog, Flash, and their cure effects remain outside the represented
state. See ADR 0002 and ADRs 0029 through 0041 in the root project for the
interface and safety boundary.
