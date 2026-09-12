# ADR 0029: Additive attack-miracle curriculum

- Status: **Accepted**
- Date: 2026-09-11
- Amends: ADR 0024

## Context

The schema-v6 stochastic resource curriculum models fixed and probabilistic
attack miracles, Absorption, deterministic HP/MP utility, and MP costs. The
accepted Bible also describes two additive attack miracles with exact values,
elements, and costs: Fireball (`+ATK2`, fire, 2 MP) and Meteor (`+ATK10`, light,
7 MP). Omitting them leaves a deterministic gap in the sequential combo policy.

Other tempting increments are not yet sound. Treasure has no strategic value
until the simulator models purchases, and the audited HP-or-damage sundry does
not publish its outcome probability. Special armor ordering is also not yet
established by authoritative transition evidence.

## Decision

Add `expanded-resource-hand` as a separate native ruleset. It retains
observation schema v6, the 14 global inputs, and the 21-action sequential head,
while adding the two Bible-verified additive miracles to a 126-card fingerprinted
catalog.

An additive miracle:

- can be selected only after an effect-free weapon base;
- contributes its exact attack value and element through the existing combo
  composition rule;
- is legal only when the complete selected combo cost is affordable;
- charges its MP cost once when the combo is confirmed; and
- remains in hand after use, matching reusable miracle behavior.

The initial nine-card layout retains the stochastic curriculum's two weapons,
one booster-family slot, two armor, one utility, one fixed miracle, one chance
miracle, and one effect miracle. The booster-family slot samples the combined
effect-free weapon-booster and additive-miracle catalogs uniformly by card.
Subsequent redraws sample the complete expanded catalog while retaining base
weapon liveness.

The ruleset uses a distinct kernel/ruleset identity even though its observation
shape is unchanged. Earlier schema-v6 evaluations remain immutable and cannot
be compared as if they used this catalog.

## Consequences

Native self-play can now learn when an MP-funded additive combo is worth more
than saving MP for a fixed, chance, healing, or absorption miracle. Because the
feature shape is unchanged, an existing schema-v6 checkpoint can enter this
curriculum without another weight migration.

The simulator remains non-promotable. Multi-hit resolution, curses, guardians,
phenomena, stochastic self-damage probabilities, and the CP purchase economy
still require separately evidenced ruleset increments. The first special-armor
increment is addressed by [ADR 0030](0030-evidenced-super-mirror-curriculum.md).

## Implementation evidence

The native extension exposes the 126-card catalog under observation schema v6,
and the complete repository test suite passes with the new transitions. A local
4,096-environment benchmark processed 4,096,000 transitions at approximately
9.02 million transitions per second, leaving enough throughput for the existing
PPO and teacher-distillation loop. A one-update training smoke test also
completed from an existing schema-v6 checkpoint with the new heuristic teacher
and ruleset fingerprint.
