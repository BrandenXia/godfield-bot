# ADR 0043: Miracle-block armor curriculum

## Status

Accepted, 2026-09-14.

## Context

The accepted 2026-09-07 Bible snapshot identifies Angel Gauntlet, Angel Cap,
Angel Shield, and Angel Armor as neutral armor with DEF9, DEF11, DEF13, and
DEF15 respectively, and the exact effect text `Block a miracle`. The accepted
API catalog independently records the same four armor cards with
`ability: blockMiracle` and matching defense values.

The live API policy treats `blockMiracle` as preventing the entire pending
miracle rather than adding the printed DEF alone. The schema-v7 curriculum
already distinguishes fixed, chance, and effect attack-miracle card kinds
inside the native engine, so this rule does not require a larger neural
observation.

## Decision

Add `miracle-block-resource-hand` as a distinct cumulative ruleset layered on
`fever-mask-resource-hand`. It adds the four Angel armor cards to a 171-card
catalog through a minimal native interface containing token IDs and printed
defense values. These cards use native card kind 27 and are consumable armor.

Against fixed, chance, and effect attack miracles, Angel armor is legal
regardless of elemental compatibility and contributes the full pending attack
value. A successful chance check still occurs before defense, and a fully
blocked absorption miracle deals and heals zero. Against a weapon-based attack,
Angel armor behaves as ordinary neutral armor: it contributes only its printed
DEF and obeys the existing elemental compatibility table. Additive miracles do
not change the base attack kind, so an Angel card blocks the complete combined
miracle attack only when the base card itself is a miracle.

Expose `pending_base_kinds` as a read-only diagnostic native view. The heuristic
uses it to value an Angel card as a full block only during miracle defense. The
view is not added to the neural tensor tuple, so the observation schema remains
version 7 with 16 global features. The native package advances to 0.24.0 while
the kernel schema remains version 1.

## Safety boundary

The environment remains non-promotable. This milestone does not add the
weapon-side Angel family, miracle bounce/reflect armor, multi-player targeting,
or other omitted official effects. Whether miracle blocking applies to every
unmodeled compound or reflected interaction remains subject to live-trace
verification.

## Verification

Parser and factory tests pin the four exact cards, values, neutral element,
schema-v7 identity, 171-card catalog, diagnostic pending-kind view, and native
card kind. Native behavior tests cover full blocking of an elementally
incompatible attack miracle, printed DEF against an ordinary weapon, and normal
element restrictions against an elemental weapon. Policy tests cover catalog
construction, full-block valuation for miracles, and printed-DEF valuation for
weapons. Final regression, benchmark, and smoke-training results are recorded
with the milestone commit. The full 392-test regression suite passes with
strict Ruff, mypy across 49 source files, lockfile, diff, and native format
checks. A 4,096-environment, 1,000-step benchmark sustained 6.68 million native
transitions per second and completed 71,030 episodes. A 1,024-transition
teacher plus 1,024-transition PPO smoke run created schema-v7 candidate
`cd603d43-3cee-4156-b0e0-a02ae2a61240`; permissive paired 64-deal evaluation
`919fa324-b125-4770-b603-300c83a78405` completed all 128 games in each matchup
against the parent and heuristic without an incomplete game. These permissive
thresholds verify the execution path and are not a promotion gate.
