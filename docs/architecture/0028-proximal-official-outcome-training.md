# ADR 0028: Proximal updates for official outcome training

- Status: **Accepted**
- Date: 2026-09-11
- Amends: ADR 0026

## Context

The first official-outcome trainer updated once per episode for 20 passes. An
initial batch of eight completed games contained one win and seven losses. Its
default child scored 37.99% against the native parent, and several smaller
updates still failed the paired parent gate. The loss-heavy batch let sparse,
high-variance results move a policy that had already learned substantially more
from the C++ curriculum.

The evaluation gate prevented deployment, but producing predictably regressed
candidates wastes data and obscures whether a failure comes from live control,
dataset quality, or optimization.

## Decision

Replace `official-training-outcome-actor-critic-v1` with
`official-training-proximal-outcome-v2`.

The trainer keeps an immutable frozen copy of the behavior policy and applies
one full-dataset update per epoch. It:

- computes advantages from the parent value estimates and normalizes them over
  the complete batch;
- clips selected-action probability ratios and value changes;
- penalizes KL divergence from the parent on recorded official states;
- anchors all parameters to the parent weights; and
- clips the global gradient norm.

After training, the candidate is saved only when both mean behavior-policy KL
and global parameter RMS change remain below configured ceilings. The manifest
records the limits and observed drift.

By default, training also requires at least 20 completed parent-controlled
official games with at least two wins and two losses. Tests and explicit
experiments may raise or lower these readiness thresholds, but doing so does
not bypass native evaluation or make a child deployable.

The defaults are four full-batch epochs at a `1e-4` learning rate. Evaluation
remains the authority: a low-drift update is not presumed better and still must
show paired superiority to its parent plus non-inferiority to the heuristic.

## Consequences

The eight-game diagnostic batch now yields a low-drift child (mean KL 0.00080,
parameter RMS change 0.00031) that scores 50.20% against its parent and 54.59%
against the heuristic in a 1,024-game-per-matchup diagnostic. It does not pass
the parent-superiority confidence bound and therefore remains offline.

More official games, including additional wins, are required for the next
candidate. This preserves native competence while making lack of evidence an
explicit data-readiness result rather than an optimizer-induced regression.
