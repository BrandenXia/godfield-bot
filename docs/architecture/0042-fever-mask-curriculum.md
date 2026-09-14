# ADR 0042: Fever Mask curriculum

## Status

Accepted, 2026-09-13.

## Context

The accepted 2026-09-07 Bible snapshot identifies Fever Mask as Fire armor
with `DEF10` and `Catch Fever`. The accepted API catalog independently records
the same card as Fire `def: 10`, with `ability: selfCurse` and
`curse: fever`.

The schema-v7 curriculum already represents elemental defense, consumable
redraw, Fever, repeated-status escalation, and end-turn illness effects. Fever
Mask is therefore the next evidence-bounded compound defense: the policy must
trade immediate prevention against a delayed health cost and escalation risk.

## Decision

Add `fever-mask-resource-hand` as a distinct cumulative ruleset layered on
`heaven-herb-resource-hand`. It adds Fever Mask to a 167-card catalog through a
minimal native interface containing token IDs, defense values, and elements.

Fever Mask follows ordinary elemental armor compatibility. On confirmed
defense it contributes DEF10, is consumed and redrawn, and inflicts Fever only
if its user survives the incoming damage. A healthy user enters Fever; an
already ill user advances one stage; use in Heaven is lethal. Because defense
happens during the attacker's turn, the new Fever does not tick until the
defender later completes their own turn.

This order composes the API's `selfCurse` signal with the established defense
and illness primitives. It is an inference to verify against a future live
trace. Fever Mask is masked against Cold/Hell-on-damage weapons because the
relative order of two curse effects is not yet evidenced.

The observation schema remains version 7 with 16 global features. The native
package advances to 0.23.0 while the kernel schema remains version 1.

The heuristic treats Fever Mask as emergency armor. It ignores the card when
ordinary compatible armor can make the hit nonlethal, when the mask still
cannot prevent defeat, or while already in Heaven. It accepts the curse only
when the mask changes an otherwise lethal defense into survival.

## Safety boundary

The environment remains non-promotable. Fever Mask does not establish full
official fidelity. Fog, Flash, curse transfer, curse removal by defeat, and
unevidenced dual-effect ordering remain outside the ruleset.

The underlying illness behavior remains grounded in the
[current strategy wiki illness page](https://w.atwiki.jp/piong/pages/23.html),
while current armor data is cross-checked against the
[strategy wiki armor catalog](https://w.atwiki.jp/piong/pages/17.html).

## Verification

Parser and factory tests pin the exact card, Fire element, DEF10 value,
schema-v7 identity, 167-card catalog, and native card kind. Native tests cover
damage prevention, post-survival Fever, delayed ticking, consumable selection,
and masking against illness weapons. Policy tests cover catalog construction,
ordinary-armor preference, and emergency use to prevent lethal damage.
The full 384-test regression suite passes with strict Ruff, mypy across 49
source files, lockfile, diff, and native format checks. A 4,096-environment,
1,000-step benchmark sustained 7.20 million native transitions per second and
completed 74,055 episodes. A 1,024-transition teacher plus 1,024-transition PPO
smoke run created schema-v7 candidate
`8c967016-3f84-4776-8763-d39046aefd66`; permissive paired 64-deal evaluation
`12f0d135-2cf8-4533-8cff-d74c9688d0c6` completed all 128 games in each matchup
against the parent and heuristic without an incomplete game. These smoke thresholds
are not a promotion gate.
