# ADR 0044: Miracle-block weapon curriculum

## Status

Accepted, 2026-09-19.

## Context

The accepted Bible identifies four neutral Angel weapons with the exact effect
`Block a miracle`: Angel Knife ATK11, Angel Sword ATK13, Angel Axe ATK15, and
Angel Bow +ATK15. The accepted 2026-09-07 and 2026-09-09 API snapshots agree on
the attack values and `ability: blockMiracle`; they additionally mark Angel Bow
as `isPlusAtk: true`.

These cards do not fit one ordinary category. Knife, Sword, and Axe are base
attacks that can also defend against a miracle. Bow is an additive weapon that
requires an existing weapon base when attacking, but it has the same defensive
miracle-block ability.

## Decision

Add `miracle-block-weapon-resource-hand` as a cumulative ruleset layered on
`miracle-block-resource-hand`. The 175-card catalog adds the three base weapons
through native card kind 28 and Angel Bow through native card kind 29.

On attack, the three base weapons behave as consumable neutral weapons. Angel
Bow is masked until a weapon base is selected, then adds ATK15 and is consumed
with the combo. On defense, all four cards are legal only against fixed, chance,
or effect attack miracles and contribute the full pending attack value. They
cannot defend weapon attacks because none has printed DEF. Additive miracles do
not change the pending base kind, preserving the distinction between a miracle
attack and a weapon enhanced by a miracle.

The heuristic catalogs Knife/Sword/Axe as attacks, Bow as a booster, and all
four as miracle-only full-block defenses. The observation schema remains
version 7 with 16 global features. The native package advances to 0.25.0 while
the kernel schema remains version 1.

## Safety boundary

The environment remains non-promotable. Miracle bounce and reflection, other
dual-purpose effect weapons, multi-player targeting, and unmodeled compound
interactions remain outside this curriculum.

## Verification

Parser and factory tests pin the exact four-card split, neutral element,
schema-v7 identity, 175-card catalog, and both native card kinds. Native tests
cover base-attack use, Bow's base requirement and additive value, full blocking
by both card kinds, and masking against weapon attacks. Policy tests pin attack,
booster, defense, and policy identities. The full suite passes 399 tests.

The release benchmark completed 4,096,000 transitions over 71,686 episodes at
6,898,743 transitions per second. Smoke training produced candidate
`a0b2d3e3-bc63-45bb-bee1-082514761473` from 1,024 teacher and 1,024 PPO
transitions without training failures. Evaluation
`3161f997-ec33-4268-a085-59dfe6817af3` completed all 128 paired games against
the parent and all 128 paired games against the heuristic with zero incomplete
games. Its permissive smoke thresholds passed, but the ruleset remains
non-promotable and this result is not a performance claim.
