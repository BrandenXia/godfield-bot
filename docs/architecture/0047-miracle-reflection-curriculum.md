# ADR 0047: Miracle-reflection curriculum

## Status

Accepted, 2026-09-20.

## Context

The accepted Bible identifies four neutral cards with the exact effect
`Reflect a miracle`: Moonlight Helm, Shield, and Armor with printed DEF8,
DEF10, and DEF12, plus Moonlight Axe with printed ATK10. Reflection differs
from the existing Sky-family bounce: it returns the complete pending attack
miracle to its original caster instead of sampling a random living player.

## Decision

Add `miracle-reflection-resource-hand` as a cumulative schema-v7 ruleset on top
of `miracle-bounce-miracle-resource-hand`. Native card kind 33 represents the
three Moonlight armor cards and kind 34 represents Moonlight Axe, growing the
catalog from 182 to 186 cards.

Moonlight armor retains its printed neutral defense against compatible weapon
attacks. Against an attack miracle it ignores that numeric defense and reflects
the full pending attack to the original caster, who receives a new defense
response. Moonlight Axe is a consumable neutral ATK10 base weapon on attack and
offers the same miracle-only reflection defense, but cannot defend an ordinary
weapon attack.

The existing `pending_reflected` guard is shared by reflection and bounce, so a
redirected miracle cannot be redirected again. The observation remains schema
7 with 16 global features and kernel schema 1. The native package advances to
0.28.0. The 186-card catalog, sampling distribution, and heuristic identity are
fingerprinted independently.

## Safety boundary

The environment remains incomplete and non-promotable. Multiplayer targeting
beyond a duel and unverified compound redirect ordering remain outside this
increment. The smoke gate below uses deliberately permissive thresholds and is
only a liveness check, not evidence that the candidate is stronger.

## Verification

Parser tests pin the complete Moonlight family and its printed values. Factory
tests pin the cumulative 186-card catalog, native card kinds, schema, sampling
identity, and ruleset identity. Native behavior tests cover reflection to the
original caster, printed armor defense, Moonlight Axe attack and defense roles,
and the shared one-hop redirect guard. The full Python suite passes, Ruff
passes, mypy passes all 49 source files, and the native sources pass formatting
verification.

The release benchmark completed 4,096,000 transitions over 69,226 episodes at
6,658,023 transitions per second. Smoke training produced candidate
`a91cc826-0ea9-44f1-ae47-ed1554374efb` from 1,024 teacher and 1,024 PPO
transitions without training failures. Evaluation
`ce5c0fbd-6b00-468a-984f-c1161f024ada` completed all 128 paired games against
the parent and all 128 paired games against the heuristic with zero incomplete
games. The candidate scored 55.47% against its parent and 53.13% against the
heuristic. Its permissive smoke thresholds passed, but the ruleset remains
non-promotable and this result is not a performance claim.
