# ADR 0041: Heaven Herb curriculum

## Status

Accepted, 2026-09-13.

## Context

The accepted 2026-09-07 Bible snapshot identifies Heaven Herb as a consumable
sundry with `MP+20` and `Heaven`. The accepted API catalog independently names
its ability `boostMPAndAddCurse`, supplies `abilityValue: 20`, and identifies
the curse as `heaven`.

The schema-v7 curriculum already models MP, Heaven, illness escalation,
end-turn status effects, and consumable redraw. Leaving this compound utility
out omits an important choice where immediate resource gain must be weighed
against status risk.

## Decision

Add `heaven-herb-resource-hand` as a distinct cumulative ruleset layered on
`illness-cure-resource-hand`. It adds Heaven Herb to a 166-card catalog and
uses a minimal native interface containing its token ID and MP gain.

Resolution is atomic: gain 20 MP capped at 100, apply Heaven using the existing
curse primitive, consume and redraw the sundry, then—unless curse application
was immediately lethal—run the actor's normal end-turn illness effect. This
means a healthy actor enters Heaven, an already ill actor advances one stage
regardless of the incoming curse, and use while already in Heaven is lethal.
The action stays legal at full MP because its curse component still changes
state.

This resolution order is an explicit composition of the API's verified
`boostMPAndAddCurse` effect with the established status and turn rules. It is
an inference to verify against future live evidence, rather than a separately
observed client trace.

The observation schema remains version 7 with 16 global features. The native
package advances to 0.22.0 while the kernel schema remains version 1.

The heuristic cures first. It then uses Heaven Herb only when the actor is
healthy or in Hell and has at most 80 MP. It avoids worsening Cold/Fever,
suicide in Heaven, and wasting any of the verified 20 MP gain.

## Safety boundary

The environment remains non-promotable. Heaven Herb does not establish full
official fidelity, and its inferred compound-effect order must not be used as
live-promotion evidence. Fog, Flash, curse transfer, curse removal by defeat,
and unevidenced status/effect compositions remain outside the ruleset.

The illness behavior composed here remains grounded in the
[current strategy wiki illness page](https://w.atwiki.jp/piong/pages/23.html)
and the [beginner wiki illness summary](https://godfield-beginner.game-info.wiki/).

## Verification

Parser and factory tests pin the exact card, value, schema, 166-card catalog,
sampling identity, and native card kind. Native tests cover MP capping,
healthy/Cold/Hell progression, same-turn status ticks, consumable redraw, and
lethal reuse from Heaven. Policy tests cover catalog construction, healthy and
Hell use, and avoidance while mildly ill. The full 379-test regression suite
passes with strict Ruff, mypy across 49 source files, lockfile, diff, and native
format checks. A 4,096-environment, 1,000-step benchmark sustained 7.43 million
native transitions per second and completed 73,619 episodes. A 1,024-transition
teacher plus 1,024-transition PPO smoke run created schema-v7 candidate
`3b05e928-84bb-477c-b534-d4b815e2a6c4`; a permissive paired 64-game smoke
evaluation against both its parent and the heuristic completed with zero
timeouts or incomplete games. These smoke thresholds are not a promotion gate.
