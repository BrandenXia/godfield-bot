# ADR 0048: Fog and Flash partial-information curriculum

## Status

Accepted, 2026-09-20.

## Context

The refreshed official Bible snapshot still contains 291 artifacts and has the
same client SHA-256 as the accepted September 7 snapshot. Its curse reference
defines Fog as hiding the surroundings and randomizing enemy targets, and Flash
as allowing only one artifact for defense. The verified cards in this increment
are Water Fog Gun (`ATK3`), Water Fog Fan (`50%ATK3`), Light Flash Dagger
(`ATK2`), Light `<Flash>` (`25%ATK1`, 3 MP), and Water `<Fog>` (3 MP).

Fog changes what the policy may observe, while Flash changes the number of
legal defense selections. Treating either as an ordinary damage modifier would
let a neural policy train against information or actions unavailable in the
official game.

## Decision

Add `fog-flash-resource-hand` as a cumulative ruleset on top of
`miracle-reflection-resource-hand`. Native card kinds 35, 36, and 37 represent
Fog/Flash weapons, the Flash attack miracle, and the direct Fog miracle. The
catalog grows from 186 to 191 cards and the native package advances to 0.29.0.

Fog and Flash are independent per-player flags. A fogged acting player sees
its opponent's HP and MP as zero in the ordinary player-feature rows; its own
resources remain visible. Observation schema v8 appends actor-relative
self-Fog, opponent-Fog, self-Flash, and opponent-Flash inputs, taking the global
feature count from 16 to 20. `models migrate-curse-features` is the explicit
schema-v7 to schema-v8 path and preserves every prior parameter while
zero-initializing the four new input columns.

Fog Gun, Fog Fan, Flash Dagger, and `<Flash>` apply their curse only when their
attack hits and causes positive damage. `<Fog>` is a reusable, zero-damage
attack miracle that costs 3 MP and applies Fog when accepted. Ordinary armor
cannot answer direct Fog. The established Angel miracle block, Sky bounce, and
Moonlight reflection responses remain legal, and all redirects retain the
shared one-hop bound. Damage-triggered Fog/Flash combined with Fever Mask or a
redirect remains masked until official effect ordering is independently
verified.

A flashed defender may select one legal defensive artifact and then may only
confirm it. Both mild and all-curse cures remove Fog and Flash; mild cures do
not remove Hell or Heaven. Because this simulator is a two-player duel, Fog's
random enemy-target rule has no additional target choice to make.

## Safety boundary

The environment remains incomplete and non-promotable. Dream, Dark Cloud,
multiplayer target randomization, and unverified compound status interactions
remain outside the represented state. Zeroed opponent HP/MP is an explicit
unknown-value encoding, not a claim that the hidden resources are zero. The
smoke gate below verifies liveness only and is not a performance claim.

## Verification

Parser and factory tests pin all five cards, the 191-card catalog, schema v8,
20 global inputs, native card kinds, sampling identity, and policy identity.
Native behavior tests cover damage-gated Fog/Flash, hidden opponent resources,
the one-artifact Flash limit, direct Fog cost and reusable ownership, Angel
block, Moonlight reflection, the shared one-hop guard, and cure behavior. The
focused simulator/training suite passes 199 tests. Ruff, mypy across all 49
source files, and native formatting checks pass.

The release benchmark completed 4,096,000 transitions over 66,842 episodes at
6,255,620 transitions per second. Migration produced schema-v8 initialized
model `7b233a73-fa0f-4c07-a9ec-d4b6b334894d`. A 1,024-transition teacher plus
1,024-transition PPO smoke run produced candidate
`d4fa243f-92e9-4a21-8ed2-992f7621c828` without training failures. Evaluation
`815a63d9-ae73-4e23-a757-719eab6cd94e` completed all 128 paired games against
the migrated parent and all 128 paired games against the heuristic with zero
incomplete games. The candidate scored 49.22% against its parent and 35.94%
against the heuristic. Those deliberately permissive smoke thresholds passed,
but the result confirms only end-to-end execution and the ruleset remains
non-promotable.
