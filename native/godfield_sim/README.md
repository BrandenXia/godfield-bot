# godfield-sim

This optional native package contains the batched C++20 curriculum simulator.
It is built and installed from the repository root with:

```console
uv sync --extra simulation --group dev
```

`plain-attack-duel-v0` is intentionally incomplete and its generated
trajectories are not eligible for live model promotion. See ADR 0002 in the
root project for the interface and safety boundary.
