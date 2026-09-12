# ADR 0031: Evidenced Reflection Sword curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0030

## Context

Reflection Sword is a dual-role weapon: its accepted Bible entry is `ATK10`
and `Reflect a NE weapon`. The Bible establishes its static shape, but the
simulator also needs authoritative response ordering and consumption behavior.

Twenty official two-player Training recordings show an attack confirmation
entering a Reflect phase whose artifact is Reflection Sword, followed by the
original attacker receiving a defense decision against the unchanged attack.
Sixteen completed Forgive responses applied the displayed attack value to the
original attacker; four incomplete or unchanged responses are not used to infer
damage behavior.

The direct API recording `e4a7956e-4224-4eae-9112-72a2ff613a34`, transition
1,387, removes the remaining ambiguity. Before defense, a neutral weapon attack
of 23 was pending from player 1 to player 2. Submitting Reflection Sword model
38 removed its instance from player 2's hand, preserved the attack value and
item IDs, changed the source to player 2 and target to player 1, produced no HP
change, and made player 1 the awaited defender.

Bouncing Sword is deliberately excluded. Three direct two-player API uses of
model 21 resolved the full attack against the current defender rather than
redirecting it, while other recordings redirected it. Its target distribution
is therefore stochastic and is not equivalent to Reflection Sword even in a
duel.

## Decision

Add `reflection-weapon-resource-hand` as a distinct native ruleset layered on
`reflection-resource-hand`. It adds only Reflection Sword, producing a
128-card catalog while preserving observation schema v6, 14 global inputs, and
the 21-action sequential head.

Reflection Sword is sampled as part of the weapon family and can lead a normal
ATK10 non-element attack. During defense, it is legal only when the pending
attack has a weapon base and remains non-elemental. Like Super Mirror, it is an
exclusive selection. Confirmation consumes and redraws the card, preserves the
pending attack, and redirects defense to the original attacker.

The existing one-hop boundary remains: all reflection actions are masked on
the redirected response. This avoids inventing repeated-reflection ordering
while ensuring every state retains Forgive as a legal action. The action mask
expresses the category and element restrictions, so no observation migration
is required.

The curriculum heuristic indexes Reflection Sword as both an ATK10 base and a
special defense. It uses a legal reflection only when ordinary armor is absent
or cannot prevent lethal damage.

## Validation

The full repository suite passes with 320 tests. Ruff, mypy, lock consistency,
and `git diff --check` also pass. A release-build benchmark at batch size 4,096
completed 4,096,000 transitions at approximately 8.43 million transitions per
second.

An end-to-end CPU smoke run initialized `reflection-weapon-resource-hand` from
an existing schema-v6 checkpoint, completed one heuristic teacher update and
one PPO update, and wrote a schema-v3 candidate manifest with 21 actions and 14
global inputs. This verifies shape compatibility without treating the smoke
candidate as a performance result.

## Consequences

Native self-play can now learn the opportunity cost of spending a dual-role
weapon on attack versus retaining it as a reactive defense. Existing schema-v6
checkpoints remain shape-compatible, while the new ruleset and catalog
fingerprints isolate its trajectories and evaluations.

This ruleset remains non-promotable. Bouncing Sword target selection, repeated
reflections, miracle reflection and blocking, counterattack rings, status
effects, guardians, phenomena, and the CP purchase economy remain separate
evidence-gated increments. Numeric dual-role weapons are addressed by ADR 0032.
