# ADR 0082: Guardian resource and curse state in the versioned batch

## Status

Accepted, 2026-09-29. Native package 0.41.0 advances the guardian combat kernel,
observation, and report schemas to 2. The basic v1 contract is retained in Git
history; no models were trained under it. Existing duel curricula are unchanged.

## Supported provisional effects

The catalog-pinned factory now admits 39 of the 40 weighted planet effects.
Profiles contain model, ATK, element, hit rate, effect code, utility value, and
curse bit. Codes are 0 ordinary attack, 1 HP absorption, 2 curse on damage,
3 direct curse, 4 erase owner's curse mask, 5 owner HP gain, 6 owner MP gain,
7 owner CP gain, 8 CP gain for every living player, 9 enemy CP gain, and
10 enemy-to-owner CP transfer. Diamond Axe's `categoryWeapons` classification
is rejected; Earth and Moon are absent from weighted selection.

Offensive effects and enemy money effects require a living target distinct
from the owner. Owner utilities require target equal to owner. Direct effects
resolve immediately; attacks, absorption, and curses on damage await defense.
All targets and profile lookups validate before any row in the call mutates.
HP/MP/CP are bounded by 100. Absorption uses actual HP lost after defense and
HP capping. CP transfer is limited by the enemy's balance and the owner's
remaining capacity, preserving the transferred money. Reset restores initial
HP/MP/CP and clears curse flags and guardian/combat state.

Curse bits are Fog=1, Dream=2, Flash=4, and Dark Cloud=8. Direct curses set the
target flag on a hit; curses on damage require positive actual damage and a
surviving target. The owner-clearing effect clears these four flags. This
component does not yet implement the behavioral effects of those curses,
illness progression, hand disguise, or interactions with trade and inventory.
Effect targeting, resource caps, and transfer behavior are provisional catalog
interpretations awaiting official parity checks.

## Observation and verification

Resources are copied `[environment, player, field]` arrays for HP, MP, CP, and
curse mask. The combat observation now has ten columns: phase, model, owner,
target, ATK after hit, element, last HP lost, effect code, utility, and curse bit.
The effect code is -1 for a missed event. The completed event remains visible
with phase 0 until the next event or reset. Counters distinguish defended
attacks from all resolved effects. Random tickets and activation timing remain
caller supplied.

Tests exercise blocked and unblocked curse attacks, direct curses, curing,
absorption, caps, shared CP gifts, transfer capacity, atomic utility errors, and
resource reset. The report still sets local-training eligibility, full-game
readiness, official fidelity, and promotion false. A full environment still
needs guardian trigger scheduling, defense-card inventory/costs, death handling,
Earth/Moon and weapon classification, episode rewards, and a rollout interface.
