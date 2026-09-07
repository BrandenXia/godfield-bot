# ADR 0002: Native batched simulator boundary

- Status: **Accepted**
- Date: 2026-09-07

## Context

Browser games are too slow and scarce to be the main source of reinforcement-
learning experience. The simulator must step many independent games without a
Python call per game, but the policy, training algorithm, replay format, and
browser integration are still changing quickly.

The current live client does not expose a public rules API. A fast simulator is
therefore also a model of observed rules, not an authority. It must identify its
rules and source-data fingerprints so that synthetic trajectories cannot be
mistaken for verified browser trajectories.

## Decision

Use a C++20 simulation kernel exposed to Python through nanobind. CMake and
scikit-build-core build the extension; uv resolves, locks, and installs it as
the optional local `godfield-sim` dependency.

C++ owns:

- deterministic environment state and pseudorandom streams;
- batched reset and step operations;
- legal-action masks and transition validation;
- contiguous observation, terminal-return, and episode metadata buffers.

Python owns:

- snapshot parsing and rule-catalog construction;
- PyTorch inference and optimization;
- rollout collection, replay persistence, evaluation, and model lineage;
- browser fine-tuning and every deployment gate.

The hot interface is batch-first. One `step(int64[batch])` advances every live
environment. Observation and result properties are read-only NumPy views into
C++-owned buffers, avoiding a copy across the binding. `reset_done()` recycles
only terminal rows after Python has consumed their final result.
The Python adapter converts these views to PyTorch through DLPack without a CPU
copy. They are explicitly ephemeral: collectors clone or copy a state only when
it must survive the next native step.

The `plain-attack-redraw-duel-v1` kernel is deliberately narrow. It samples
uniform synthetic nine-card hands from the 18 effect-free, neutral, fixed-ATK
weapons in an accepted Bible snapshot. Two players begin at the observed 40 HP;
one selected hand slot atomically deals its fixed ATK, then a nonterminal attack
draws a uniform replacement into that slot. There are no armor, elements,
resources, status effects, trades, or card effects. The v1 redraw rule replaces
v0's artificial empty-hand draw and reflects the stable nine-card hands in
recorded live transitions. This remains a curriculum abstraction and
performance harness, not a complete God Field implementation.

The kernel's slot selection is a macro action using action-head indices 1-9.
Browser confirmation actions remain separate and must continue to be learned
from real transition evidence. Simulator field numbers count macro turns and
must not be assumed to prove the live client's exact G.F. timing semantics.

The separately versioned
`plain-attack-defense-redraw-duel-v1` kernel adds the first response phase
without changing attack-only v1 trajectories. Each synthetic hand has five
weapon slots and four armor slots. Weapon slots redraw uniformly from the 18
effect-free neutral fixed-ATK weapons; armor slots redraw uniformly from the 15
effect-free neutral fixed-DEF armor cards. Elemental armor is excluded even
when its Bible entry has no text effect. On attack, the chosen weapon is
consumed and redrawn, control moves to the defender, and the pending ATK is
exposed. The defender either uses the live action head's Forgive index 19 or
chooses one armor slot (actions 6-9); damage is `max(ATK - DEF, 0)`. The
defender begins the next attack after resolution. Returns remain sparse seat
results only.

Defense observations expose `phases`, `pending_attacks`, and
`hand_card_kinds` as separate read-only arrays. They are not smuggled into the
four global features, whose positions retain the live feature meanings. The
existing `simulation_feature_tensors()` adapter therefore remains restricted
to attack-only v1. Connecting defense rollouts to the neural policy requires a
deliberate observation-schema and model-architecture decision shared with the
live state encoder.

## Compatibility and safety

Every simulator instance reports:

- kernel and observation schema versions;
- ruleset ID;
- accepted client SHA-256;
- canonical rule-catalog SHA-256;
- category-preserving sampling semantics where applicable;
- whether its output is eligible for promotion.

The kernel is always `promotion_eligible = false`. Models trained from
it may become candidates, but no future command may promote one based solely on
this curriculum. Adding a live rule, changing a distribution, discounting a
return, or allowing simulator-only promotion requires an explicit version and
evaluation decision.

PyTorch is intentionally not linked into C++. Keeping inference in Python
avoids a libtorch ABI and packaging boundary while batched calls remove the
dominant interpreter overhead. C++ inference should be reconsidered only after
profiling shows the binding or Python rollout orchestration is the bottleneck.
