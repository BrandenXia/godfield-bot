# ADR 0006: Slot-aware curriculum training

- Status: **Accepted**
- Date: 2026-09-07

## Context

The first recurrent actor-critic pooled the embeddings of every visible hand
card into one mean vector, then emitted artifact actions from fixed output
positions. Swapping two cards left that pooled representation unchanged, so
the network could not bind a card's identity or value to the action slot that
would play it. Additional PPO experience could not repair that architectural
symmetry.

Pure self-play also permits two copies of the same weak policy to co-adapt
without approaching the deterministic curriculum reference. The training loop
needs an efficient way to teach legal card selection and then retain pressure
from a stable opponent without adding shaped rewards.

## Decision

Model-manifest schema v3 adds `architecture.policy_architecture`. New models
use `slot-aware-v1`: the recurrent context is concatenated with each hand-slot
embedding and passed through one shared artifact scorer. Its outputs replace
artifact action logits 1 through 9, preserving the existing 21-action API and
the pooled hand summary used by the GRU and value head.

Schema-v2 manifests that omit the field are interpreted as
`pooled-hand-v0`. They remain loadable for historical evaluation and offline
inspection, but native simulator training rejects them with a migration
message. Continuing training requires a newly initialized schema-v3 base
because the new scorer has parameters that do not exist in old checkpoints.

Native training now has two stages:

1. Recurrent behavior cloning collects fresh simulator sequences from the
   versioned max-attack/conservative-defense heuristic. It preserves separate
   GRU state for each physical seat and resets both states at episode
   boundaries.
2. PPO uses the same sparse terminal rewards as before. A configurable share
   of environments assigns one alternating seat to the frozen heuristic. The
   sampled learner actions retain PPO policy, entropy, KL, and clipping loss;
   frozen opponent actions are masked out of those terms. Value loss uses the
   whole zero-sum trajectory.

The algorithm identity is
`heuristic-warmstart-recurrent-ppo-self-play-v1`. Configuration, teacher
metrics, frozen-opponent fraction, simulator identity, and PPO metrics are
stored in the immutable candidate manifest. The C++ simulator interface and
reward contract do not change.

## Consequences

Artifact logits now move with their cards when hand slots are permuted, making
max-attack and context-dependent armor selection learnable. Behavior cloning
quickly establishes those mechanics, while frozen-opponent PPO can optimize a
best response and self-play can preserve broader robustness. The training
path remains fully local and batched.

Schema-v2 and schema-v3 policies cannot share simulator-training lineage.
Checkpoint migration by copying pooled weights into a partially initialized
slot-aware model is intentionally not supported because it would give the new
action scorer an ambiguous provenance.

The reference heuristic is deliberately strong for the current effect-free
ruleset. How parity with that reference should be expressed in the paired
evaluation gate is a separate evaluation-policy decision; this ADR does not
change promotion thresholds or authorize live play.
