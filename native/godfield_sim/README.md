# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `reflection-weapon-resource-hand`, includes elemental multi-card
combat, HP/MP utility, fixed and chance miracles, Absorption, reusable additive
miracles, and evidence-bounded one-hop reflection with Super Mirror and the
dual-role Reflection Sword. See ADR 0002, ADR 0029, ADR 0030, and ADR 0031 in
the root project for the interface and safety boundary.
