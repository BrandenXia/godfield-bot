# ADR 0049: Dark Cloud certain-hit curriculum

## Status

Accepted, 2026-09-20.

## Context

The refreshed official Bible defines Dark Cloud as making received percentage
attacks hit certainly. Two cards fit the simulator's current mechanics:
non-element Hexagon Doom (`ATK11`, Dark Cloud on damage) and Darkness
`<Dark Cloud>` (5 MP, direct Dark Cloud). Pluto Ring and Dark Cloud guardians
remain excluded because counterattack and guardian resolution are not modeled.

## Decision

Add `dark-cloud-resource-hand` cumulatively on top of
`fog-flash-resource-hand`. Native card kinds 38 and 39 represent Hexagon Doom
and the direct miracle. The strict catalog grows from 191 to 193 cards and the
native package advances to 0.30.0.

Dark Cloud is an independent per-player flag. A percentage attack aimed at a
clouded player skips its hit roll; fixed attacks are unchanged. Hexagon Doom
applies Dark Cloud only when positive damage penetrates defense. `<Dark Cloud>`
is reusable, costs 5 MP, and applies the status when accepted. Ordinary armor
cannot answer the direct curse, while the existing Angel block, Sky bounce,
and Moonlight reflection rules remain available with the shared one-hop guard.
Mild and full cures remove Dark Cloud.

Observation schema v9 appends actor-relative self- and opponent-Dark-Cloud
inputs, taking the global feature count from 20 to 22.
`models migrate-dark-cloud-features` preserves every schema-v8 parameter and
zero-initializes the two new input columns. The heuristic values a new Dark
Cloud application but avoids reapplying it to an already clouded opponent.

## Safety boundary

The environment remains incomplete and non-promotable. Pluto Ring,
Dark-Cloud-inflicting guardians, unverified Fever Mask and redirect
compositions, Dream, and multiplayer targeting remain outside the represented
rules. Dream is intentionally separate because it requires displayed versus
actual card identity and belief-state observations rather than another public
status flag.

## Verification

Parser and factory tests pin both represented cards, native kinds, the 193-card
catalog, schema v9, 22 global inputs, sampling identity, and policy identity.
Behavior tests cover damage-gated infliction, full armor prevention, direct
miracle cost and reuse, ordinary-armor rejection, Angel blocking, percentage
attack certainty, actor-relative observations, reset, and mild-cure removal.
The complete simulator suite, schema migration tests, Ruff, mypy across all 49
source files, and native formatting checks pass.

The release benchmark completed 4,096,000 transitions over 67,250 episodes at
6,239,634 transitions per second. Migration produced schema-v9 initialized
model `820aafbb-5295-4763-b876-5a7c1efa2435`. A 1,024-transition teacher plus
1,024-transition PPO smoke run produced candidate
`195fa485-1077-407c-81bf-098c7e1e1f83`. Evaluation
`de7aa1a9-8c8c-4d70-91d4-b907971b140b` completed all 128 paired games against
the migrated parent and all 128 paired games against the heuristic with zero
incomplete games. The candidate scored 47.66% against its parent and 36.72%
against the heuristic. The deliberately permissive smoke thresholds passed,
but this verifies only end-to-end liveness; it is not a promotion result.
