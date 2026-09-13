# ADR 0039: Illness weapon curriculum and schema-v7 state

- Status: **Accepted**
- Date: 2026-09-13
- Amends: ADR 0038

## Context

The accepted Bible snapshot defines four fixed attacks with an illness-on-damage
effect: Hell Scissors (`ATK8`, Hell), Gale Sword (`ATK9`, Cold), Severe Gale
Sword (`ATK13`, Cold), and Wind Talons (Stone `ATK1`, Cold). The accepted API
catalog independently identifies these through `addCurseOnDamage` with `hell`
or `cold` curse parameters.

Current community rules describe one ordered illness track: Cold loses 1 HP,
Fever loses 2 HP, Hell loses 5 HP, and Heaven gains 5 HP at the end of the ill
player's turn. At every such turn end, illness has a 5% chance to advance one
stage; worsening Heaven is lethal. Receiving any illness while already ill
also advances one stage, regardless of the incoming illness. These details are
cross-checked against the current [God Field strategy wiki illness page](https://w.atwiki.jp/piong/pages/23.html)
and the [beginner wiki illness summary](https://godfield-beginner.game-info.wiki/).

Illness persists across decisions and changes future rewards. Omitting it from
the observation would make otherwise identical tensors represent different
states, so the schema-v6 observation is insufficient.

## Decision

Add `illness-weapon-resource-hand` as a distinct native ruleset layered on
`random-target-weapon-resource-hand`. It adds the four verified weapons to a
161-card cumulative catalog. Illness is inflicted only if attack damage remains
after defense. A healthy player receives the weapon's Cold or Hell stage; an
already ill player advances exactly one stage. Illness damage/healing and the
5% worsening roll resolve when that player's attack or utility turn finishes.
Illness-caused defeat assigns the terminal result to the actual ill player.

Observation schema v7 appends two normalized global inputs: the current actor's
illness stage and the opponent's illness stage, each divided by the Heaven stage
value of four. The pending-effect input uses distinct values for Cold and Hell
while a status attack is awaiting defense. The actor-relative ordering follows
the existing HP/MP observation contract.

Provide `models migrate-illness-features` as the only schema-v6 to schema-v7
path. It copies the existing 14 global encoder columns exactly, appends two zero
columns, retains every other weight, and records source checksums and migration
semantics in a new initialized manifest. This preserves the source checkpoint's
outputs before status features become nonzero.

Status attacks may use ordinary additive attack boosters because the verified
effect is explicitly damage-gated. Reflection is masked for pending status
attacks because no accepted trace establishes which player receives the illness
after reflection.

## Consequences

Native training can now learn the delayed HP utility and risk of persistent
Cold, Fever, Hell, and Heaven state. Ruleset, observation, catalog, and sampling
fingerprints prevent schema-v7 trajectories from being mixed with earlier
curricula.

The environment remains non-promotable. Cure sundries and miracles, illness
interaction with reflection, other status effects, guardians, counterattacks,
phenomena, multiplayer targeting, and the CP economy remain separate increments.
Without cures, long-lived illness is intentionally an incomplete curriculum
rather than a full official-game substitute.

## Validation

- Strict snapshot parsing covers all four exact card descriptions and API curse
  identities.
- Native tests cover damage-gated Cold/Hell infliction, blocked attacks, end-turn
  damage, 5% worsening, illness-caused defeat, actor-relative features, and
  status/reflection masking.
- Migration tests verify exact preservation of all old weights and zero
  initialization of both new columns.
- Factory and configuration tests cover schema v7, 16 global inputs, the
  161-card catalog, training/evaluation selection, and the benchmark alias.
- The full 360-test regression suite passes with strict Ruff, mypy, diff, and
  native-format checks.
- A 4,096-environment, 1,000-step benchmark sustained 7.46 million native
  transitions per second and completed 68,764 episodes.
- Explicit migration produced schema-v7 initialized model
  `a8d616c9-edd8-4cb6-8b95-d5691a026a97`; a 1,024-transition teacher plus
  1,024-transition PPO smoke run produced candidate
  `817d6116-9ccd-44fd-b1e8-367ce99640b2` with the 161-card fingerprint and
  illness heuristic recorded in its immutable manifest.
