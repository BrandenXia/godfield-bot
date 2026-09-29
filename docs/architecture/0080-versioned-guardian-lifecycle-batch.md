# ADR 0080: New versioned C++ batch for guardian lifecycle state

## Status

Accepted, 2026-09-29. The operator chose a new versioned C++ batch instead of
extending the existing duel batch. This implements the first state slice, not
a full-game or locally trainable environment.

## Decision

Native package 0.39.0 adds `GuardianLifecycleBatch` with kernel and observation
schema 1 and ruleset `caller-driven-guardian-lifecycle-provisional-v1`. It is
separate from `AttackDefenseBatch` and its checkpoint/ruleset identities. A
batch holds 1..2,000,000 bounded guardian slots across parallel environments,
2..9 players per environment, and 1..64 guardian slots per environment. Each
slot's copied observation has three integer fields: instance ID, owner index,
and guardian group index; zeroes mean empty. Slots, not a guessed one-guardian
limit, allow future multi-guardian evidence without changing the state shape.

The caller supplies explicit batch events. `summon` checks all rows before
writing, rejects occupied targets and duplicate instance IDs within an
environment, and requires a known weighted group. `remove` requires exact
instance IDs. `reset_environments` clears selected environments. Each operation
is atomic at call level. `attack_models` uses the separate provisional ticket
picker to return model IDs without mutating state or generating randomness.
Counters expose active, summoned, removed, and reset counts. Snapshot/model
outputs own their memory and remain stable after later mutations.

A Python factory validates the pinned guardian catalog/Bible and both native
identities before construction. The offline `simulation guardian-batch-plan`
command reports the schema, bounds, source hashes, and explicit false flags
for effect resolution, local training, full-game readiness, and promotion.
Synthetic tests cover batched ownership, atomic failures, resets, output
isolation, and up to nine players. They do not validate official mechanics.

## Remaining boundary

This is not yet a playable turn engine. It does not decide summon eligibility,
trigger timing, targeting, defense, curse/resource effects, Earth/Moon special
guardian behavior, or official random distributions. It has no `step` or PPO
rollout interface. Those rules must be added under new schema/ruleset identities
as needed, followed by parity checks against contiguous official traces.
Existing 196-card evidenced and 197-card opt-in Strength Powder curricula are
unchanged; guardians remain absent from their training catalogs.
