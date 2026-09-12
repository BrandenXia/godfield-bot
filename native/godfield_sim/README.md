# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `reflection-resource-hand`, includes elemental multi-card combat,
HP/MP utility, fixed and chance miracles, Absorption, reusable additive
miracles, and an evidence-bounded one-hop Super Mirror reflection. See ADR
0002, ADR 0029, and ADR 0030 in the root project for the interface and safety
boundary.
