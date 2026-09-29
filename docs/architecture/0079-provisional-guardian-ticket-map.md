# ADR 0079: Isolate guardian weight mapping before lifecycle and combat

## Status

Accepted, 2026-09-29. This is a provisional catalog-derived primitive, not a
trainable guardian ruleset or promotion evidence. No official game or account
was touched.

## Evidence and scope

The pinned 2026-09-21 API catalog has 42 guardian artifacts. Eight named
planet groups have five effects each, with `guardianAttackRate` values 6, 5,
4, 3, and 2 in model order. Earth and Moon have one special effect each and
no such rate. The pinned Bible has corresponding assets. Available private
traces include only four `setGuardian`, three `attackByGuardian`, and one
`removeGuardian` event labels in the acquisition snapshots, without bound
payload sufficient to verify timing, weight interpretation, or combat effects.

Native package 0.38.0 adds `ProvisionalGuardianPicker` with schema 1 and a
separate ruleset ID. It validates bounded group/model/positive-weight rows,
distinct model IDs, and overflow. Given a group and an integer ticket, it
returns the model at that cumulative-weight position. Random ticket
generation is deliberately the caller's responsibility; the class has no
`step` or `reset` training interface and no game-state mutation. The term
*weight* is a hypothesis about `guardianAttackRate`, not a claim that the
official game draws it this way.

The offline plan command validates both source pins, all 40 standard profiles,
the two excluded specials, and the native identity. It reports no official
weight-selection trace, no effect resolution, and false local-training,
full-game-readiness, and promotion eligibility. Tests cover exact ticket
boundaries and malformed inputs with synthetic data; they are not official
mechanics validation.

## Next boundary

A trainable guardian curriculum needs explicit lifecycle state (summon,
owner, trigger timing, removal), action/target and defense phases, effect
resolution including curses and resource changes, seeded stochastic behavior,
and parity checks against official traces. The 42 guardian artifacts remain
absent from the current 197-card provisional training catalog. The picker is
only a reusable low-level table for that later kernel.
