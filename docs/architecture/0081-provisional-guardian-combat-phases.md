# ADR 0081: Basic guardian combat phases in the new native batch

## Status

Accepted, 2026-09-29. Native package 0.40.0 adds a separate provisional combat
batch with schema 1. This is a mechanics component toward the requested full
game environment; turn scheduling and a training rollout interface remain.

## Rules and sources

The pinned catalog contains 21 weighted guardian entries with ATK, element,
optional hit rate, and no additional ability. The Python factory admits those
entries into `GuardianCombatBatch`, which composes the existing versioned
guardian lifecycle state. All 40 original group weights stay intact; selecting
one of the 19 other effects fails the entire queue without resampling or state
mutation. Earth and Moon remain excluded from weighted selection.

The caller supplies summon events, enemy targets, selection tickets, and hit
tickets in 0..99. An attack queues a defense phase with ATK set to zero on a
miss. Defense uses the existing curriculum's elemental contract: Fire/Water
and Wood/Stone pair against each other, Light defense also covers those four,
Light attack rejects positive defenses, and Non-element/Darkness permit any
defense element. HP loss is max(ATK-DEF, 0), capped at current HP; positive
Darkness damage removes all remaining HP. This mapping to guardian combat is
provisional pending official validation.

Each environment has one pending defense at a time. Lifecycle mutation is
blocked during that phase. Targets and owners must be alive, targets differ
from owners, and multi-row updates validate fully before applying. Explicit
reset clears pending combat, guardian slots, and HP in selected environments.
Copied HP and combat snapshots plus a resolved-attack counter expose state.
The observation columns are phase, model, owner, target, ATK after hit,
element, and last actual HP loss.

## Identity and verification

Ruleset `caller-driven-basic-guardian-combat-provisional-v1`, kernel schema 1,
and observation schema 1 are independent of every existing duel curriculum.
`simulation guardian-batch-plan --combat` verifies source/native identities and
reports 21 supported models and 19 unsupported weighted models. Local training,
full-game readiness, and promotion remain false. Tests cover probability
boundaries, elemental legality, death, atomic errors, pending lifecycle locks,
and reset. These synthetic checks do not supply official parity evidence.
