# ADR 0033: Effect-free chance weapon curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0032

## Context

The accepted Bible contains 14 weapons whose complete behavior is an exact
probability, a fixed attack value, and a combat element. It also contains Jinn's
Rocking Horse, whose complete numeric behavior is `75%ATK8`, `DEF6`, and Wood.

A consistent backup of the official Training recorder contains 227 completed
matches and 6,361 transitions. It records 112 successfully dispatched
`confirm:chance` actions across these 15 cards, including five Jinn's Rocking
Horse attacks that exposed `75%ATK8` in the official client. The already
accepted stochastic-miracle curriculum supplies the hit/miss transition, while
ADR 0032 supplies the independently verified dual-role defense semantics.

Fog Fan, Vine Shoot, and Ascension Bow are deliberately excluded. Their Bible
entries add, respectively, Fog on damage, HP absorption, and an
Ascension-dependent alternate distribution. Those effects need separate state
and evidence even though the live policy can execute the cards.

## Decision

Add `chance-weapon-resource-hand` as a distinct native ruleset layered on
`dual-role-resource-hand`. It adds 14 effect-free chance weapons plus Jinn's
Rocking Horse, producing a 150-card catalog while preserving observation schema
v6, 14 global inputs, and the 21-action sequential head.

Each chance weapon is a consumable weapon base. Confirmation samples its exact
Bible hit rate once: a hit opens ordinary defense with the fixed ATK and combat
element, while a miss consumes the card, advances the turn, and deals no
damage. Compatible additive weapon or miracle boosters preserve the base hit
rate. Reflection Sword can respond only to a non-element chance weapon, and the
existing one-hop reflection boundary remains in force.

Jinn's Rocking Horse uses that chance transition when attacking. During
defense, it contributes fixed DEF6 without a probability roll, follows Wood
armor compatibility, combines with other numeric defenses, and is consumed.

The heuristic compares chance weapons by rounded expected damage and marks them
as stochastic so expected damage is never treated as guaranteed lethal damage.
It evaluates Jinn's defensive role at its fixed value.

## Consequences

Native self-play can now learn risk/reward and hand-retention decisions for the
official chance-weapon family, including the attack-versus-defense opportunity
cost of Jinn's Rocking Horse. Existing schema-v6 checkpoints remain
shape-compatible, while the ruleset and catalog fingerprints isolate new
trajectories and evaluations.

This ruleset remains non-promotable. Chance weapons with status or absorption
effects, Ascension state, multi-hit attacks, miracle reflection and blocking,
bounce, counterattacks, guardians, phenomena, and the CP purchase economy
remain separate evidence-gated increments.

## Validation

- The full Python and native-integrated suite passes with 328 tests.
- Ruff, mypy across 49 source files, the uv lock check, and the repository diff
  check pass.
- A 4,096,000-transition native benchmark completed at approximately 8.28
  million transitions per second on the development machine.
- A CPU teacher-warm-start plus PPO smoke run produced schema-v3 candidate
  `9a249413-899d-41f3-823d-8d3c2a26a142`. Its training context records
  observation schema v6, 21 actions, 14 global features, the 150-card catalog,
  and heuristic policy `evidenced-chance-weapon-resource-combo-v1`.
