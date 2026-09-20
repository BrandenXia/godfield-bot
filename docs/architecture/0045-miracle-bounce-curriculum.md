# ADR 0045: Miracle-bounce armor curriculum

## Status

Accepted, 2026-09-19.

## Context

The accepted Bible identifies five neutral Sky armor cards with the exact
effect `Bounce a miracle`: Boots DEF1, Gauntlet DEF3, Helm DEF5, Shield DEF7,
and Armor DEF9. The accepted 2026-09-07 and 2026-09-09 API catalogs agree on
their defense values and `ability: bounceMiracle`. The Bible's armor rule says
that a bounced attack goes to somebody.

## Decision

Add `miracle-bounce-resource-hand` as a cumulative ruleset layered on
`miracle-block-weapon-resource-hand`. Its 180-card catalog adds the five Sky
armor cards through native card kind 30.

Against a fixed, chance, or effect attack miracle, a Sky armor card redirects
the complete pending attack to a uniformly sampled living duel player. The
sampled target receives a fresh defense response. A redirect is exclusive with
other defense cards, and both bounce and reflection are masked after the first
redirect. This one-hop boundary prevents bounce/reflection cycles while the
official ordering of longer chains remains unverified.

Against a weapon, Sky armor behaves as ordinary neutral armor with its printed
DEF and the established element-compatibility rules. Bounce does not change
the original attack source or end-turn owner. The observation remains schema 7
with 16 global features; `pending_bounced` is an explicit diagnostic native
view and is not added to the neural tensor. The native package advances to
0.26.0 while the kernel schema remains version 1.

## Safety boundary

The environment remains non-promotable. Sky Harpoon and `<Turbulence>`,
miracle reflection, weapon bounce, multiplayer targeting beyond the duel, and
unverified compound redirect interactions remain outside this increment.

## Verification

Parser and factory tests pin the five exact values, neutral element, schema-v7
identity, 180-card catalog, and native card kind. Native tests cover miracle
redirection, both living duel targets, printed weapon defense, and the one-hop
guard. Policy tests pin full-redirect valuation and policy identity. The full
suite passes 407 tests.

The release benchmark completed 4,096,000 transitions over 70,007 episodes at
6,277,919 transitions per second. Smoke training produced candidate
`38b336ef-5ce5-4d5a-9eca-de21788e7850` from 1,024 teacher and 1,024 PPO
transitions without training failures. Evaluation
`b326d59f-cf3a-49ea-849e-d94a5ab2aac3` completed all 128 paired games against
the parent and all 128 paired games against the heuristic with zero incomplete
games. Its permissive smoke thresholds passed, but the ruleset remains
non-promotable and this result is not a performance claim.
