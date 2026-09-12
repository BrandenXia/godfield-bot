# ADR 0034: Evidenced HP-absorption weapon curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0033

## Context

The accepted Bible contains three weapons whose complete behavior is an attack
and `Absorb HP`: Ghost Sword (`ATK7`, Non-element), Real Ghost Sword (`ATK12`,
Non-element), and Vine Shoot (`75%ATK3`, Wood). A consistent backup of the
official Training recorder contains 20 successfully dispatched actions across
these cards: nine Ghost Sword, seven Real Ghost Sword, and four Vine Shoot.

The recorder also supplies outcome-level evidence. In run
`55c96312-5a41-4ac7-8cf9-f5e7df3f4e9d`, Ghost Sword reduced the defender from
32 HP to 25 HP and raised the attacker from 40 HP to 47 HP. Healing therefore
uses damage that actually passed defense rather than the printed attack value.
In run `d9ceda2f-4e0a-4162-a270-8d509cc8b80a`, a reflected Real Ghost Sword
reduced its original user from 39 HP to 27 HP and raised the reflector from 30
HP to 42 HP. Reflection transfers the absorbing attack's ownership to the
reflector.

## Decision

Add `absorption-weapon-resource-hand` as a distinct native ruleset layered on
`chance-weapon-resource-hand`. It adds the two fixed absorption weapons and the
one chance absorption weapon, producing a 153-card catalog while preserving
observation schema v6, 14 global inputs, and the 21-action sequential head.

Confirmation follows the existing fixed or chance weapon path. On resolution,
the pending attack owner receives HP equal to the defender's actual HP loss,
capped at the existing 100 HP resource ceiling. Fully blocked attacks, misses,
and zero-damage outcomes heal zero. Compatible additive boosters increase
damage before defense and therefore may increase healing only by the amount
that penetrates defense. One-hop reflection changes the pending owner, so its
eventual healing belongs to the reflector.

The new cards are weapon bases, not defenses or boosters. Their exact Bible
element controls armor compatibility and Reflection Sword eligibility. The
heuristic values fixed absorption weapons at printed damage and Vine Shoot at
rounded expected damage; Vine Shoot remains marked stochastic so it is never
treated as guaranteed lethal damage.

## Consequences

Native self-play can now learn the survival value of weapon-based life steal,
including the interaction with numeric defense, chance, additive attack, and
reflection. Existing schema-v6 checkpoints remain shape-compatible, while the
new ruleset and 153-card catalog fingerprints isolate its trajectories and
evaluations.

This ruleset remains non-promotable. Absorption's tactical value is represented
only through the resulting HP observation and reward, without a dedicated
effect feature. Status effects, Ascension, multi-hit attacks, miracle
reflection and blocking, bounce, counterattacks, guardians, phenomena, and the
CP purchase economy remain separate evidence-gated increments.

ADR 0035 extends this boundary with the separately evidenced dynamic-MP weapon.

## Validation

- The full Python and native-integrated suite passes with 332 tests.
- Ruff, mypy across 49 source files, the uv lock check, and the repository diff
  check pass.
- A 4,096,000-transition native benchmark completed at approximately 8.04
  million transitions per second on the development machine.
- A CPU teacher-warm-start plus PPO smoke run produced schema-v3 candidate
  `49d7d2c4-3ef9-44ff-92b6-eb39f7ad70df`. Its training context records
  observation schema v6, 21 actions, 14 global features, the 153-card catalog,
  and heuristic policy `evidenced-absorption-weapon-resource-combo-v1`.
