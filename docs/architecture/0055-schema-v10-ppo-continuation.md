# ADR 0055: Schema-v10 PPO continuation candidate

## Status

Accepted, 2026-09-27.

## Context

The first schema-v10 Dream candidate from ADR 0051 was safe enough for passive
shadowing and a one-intervention canary, but its three native scores against the
frozen Dream heuristic averaged only 51.11%. Thirteen completed official canary
games then produced no wins. Those mixed-policy outcomes do not measure the
candidate directly, but they do not justify widening its live authority either.

The existing candidate already matched the heuristic teacher with 96.69% final
action accuracy. Repeating teacher imitation would therefore spend most of the
training budget reproducing the same ceiling instead of optimizing game
outcomes.

## Decision

Continue immutable candidate
`df08842c-f5e8-4317-8721-0245310c92ac` with PPO only. Child candidate
`088ef7a5-c8bf-46e2-8469-4d2390719839`, weights SHA-256
`678550d932ff8063f8562cc68c73e08b601d350bc850523262fb738e70d78ac7`, uses
the unchanged strict schema-v10 Dream contract. Training used 80 updates, 64
rollout steps, batch size 512, two PPO epochs, 128-environment minibatches, a
learning rate of `0.0001`, and the heuristic for every opponent. It consumed
2,621,440 native transitions across 37,009 completed episodes and no teacher
transitions.

Keep the child a non-promoted candidate. Require the existing prospective
official-Training shadow gate for these exact weights before any guarded live
intervention. Evidence recorded for the parent cannot be reused.

## Verification

The child completed every game in four independent native evaluations. Three
reports passed the paired parent-superiority and heuristic-noninferiority gates;
one smaller report missed parent superiority because its 51.86% point estimate
had a 49.36% paired lower bound.

| Seed | Pairs per seat | Parent score | Parent lower bound | Heuristic score | Heuristic lower bound | Passed |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 27067 | 512 | 51.86% | 49.36% | 54.39% | 51.68% | No |
| 27068 | 512 | 52.93% | 50.36% | 54.39% | 51.68% | Yes |
| 27069 | 512 | 53.52% | 51.16% | 51.95% | 49.18% | Yes |
| 28067 | 2,048 | 51.86% | 50.59% | 53.76% | 52.34% | Yes |

Across the three smaller seeds, the child averaged 52.77% against its parent
and 53.61% against the heuristic. The larger 4,096-game evaluation separately
confirmed both effects. The readiness audit found the required three passing
native reports and correctly rejected guarded intervention because no
prospective official-Training shadow run yet names the new model and weight
digest.

## Consequences

This establishes a stronger native candidate, not official-game strength or
deployment approval. The heuristic continues to control prospective shadow
games. Only a new passing readiness report may admit this child to the existing
one-intervention canary, and broader neural control remains a separate design
decision.
