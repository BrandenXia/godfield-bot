# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `expanded-resource-hand`, includes elemental multi-card combat,
HP/MP utility, fixed and chance miracles, Absorption, and reusable additive
miracles. See ADR 0002 and ADR 0029 in the root project for the interface and
safety boundary.
