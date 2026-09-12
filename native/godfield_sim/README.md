# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

Every included curriculum is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. The broadest current
ruleset, `dual-role-resource-hand`, includes elemental multi-card combat, HP/MP
utility, fixed and chance miracles, Absorption, reusable additive miracles,
evidence-bounded one-hop reflection, and seven ATK/DEF weapons. See ADR 0002 and
ADRs 0029 through 0032 in the root project for the interface and safety
boundary.
