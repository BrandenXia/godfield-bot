# ADR 0046: Miracle-bounce weapon and miracle curriculum

## Status

Accepted, 2026-09-20.

## Context

The accepted Bible identifies two remaining neutral cards with the exact
effect `Bounce a miracle`. Sky Harpoon is a weapon with `+ATK9`; `<Turbulence>`
is a miracle with `Cost 5MP`. The accepted catalog represents both as
`bounceMiracle`, agreeing with the Bible's printed values and categories.

## Decision

Add two cumulative schema-v7 rulesets on top of
`miracle-bounce-resource-hand`:

- `miracle-bounce-weapon-resource-hand` adds Sky Harpoon through native card
  kind 31, growing the catalog to 181 cards.
- `miracle-bounce-miracle-resource-hand` adds `<Turbulence>` through native
  card kind 32, growing the catalog to 182 cards.

Sky Harpoon is a consumable neutral booster. It requires a selected weapon
base, adds nine attack, and can be selected alone to bounce an incoming attack
miracle. It cannot defend an ordinary weapon attack.

`<Turbulence>` is defense-only in this curriculum. It is legal only against an
attack miracle while its user has at least 5 MP, deducts that cost on
confirmation, and remains in hand after use. Both cards redirect the complete
pending attack to a uniformly sampled living duel player. The new target gets
a fresh defense response. The existing one-hop guard prevents any second
bounce or reflection.

The observation remains schema 7 with 16 global features and the kernel schema
remains version 1. The native package advances to 0.27.0. Both catalogs,
sampling distributions, and heuristic identities are separately
fingerprinted.

## Safety boundary

These environments remain incomplete and non-promotable. Miracle reflection,
multiplayer targeting beyond a duel, and unverified compound redirect ordering
remain outside this increment. The smoke gate below uses deliberately
permissive thresholds and is only a liveness check, not evidence that the
candidate is stronger.

## Verification

Parser tests pin Sky Harpoon at +ATK9 and `<Turbulence>` at 5 MP. Factory tests
pin the cumulative 181- and 182-card catalogs, native card kinds, schema, and
sampling identities. Native behavior tests cover booster composition,
miracle-only defense, MP affordability and payment, reusable miracle
ownership, and one-hop redirect behavior. The full Python suite passes, Ruff
passes, mypy passes all 49 source files, and the native sources pass formatting
verification.

The release benchmark completed 4,096,000 transitions over 70,681 episodes at
5,948,999 transitions per second. Smoke training produced candidate
`6c7b192a-897d-42d8-9416-890dddf28b22` from 1,024 teacher and 1,024 PPO
transitions without training failures. Evaluation
`0d443548-3234-417e-a013-98f95b0f9018` completed all 128 paired games against
the parent and all 128 paired games against the heuristic with zero incomplete
games. Its permissive smoke thresholds passed, but the ruleset remains
non-promotable and this result is not a performance claim.
