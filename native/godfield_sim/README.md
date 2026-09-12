# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `dynamic-mp-weapon-resource-hand`, includes elemental multi-card combat, HP/MP
utility, fixed and chance miracles, Absorption, reusable additive miracles,
evidence-bounded one-hop reflection, seven fixed ATK/DEF weapons, 14
effect-free chance weapons, and the chance/defense dual role of Jinn's Rocking
Horse. It additionally models all three evidenced HP-absorbing weapons,
including actual-damage healing and reflected ownership, plus Magical Stick's
current-MP attack and all-MP consumption. See ADR 0002 and ADRs 0029 through
0035 in the root project for the interface and safety boundary.
