# ADR 0084: Typed card attacks and reusable MP-cost defenses

## Status

Accepted, 2026-09-29. Native package 0.43.0 advances `GuardianTurnBatch` kernel,
observation, and report schemas to 2, with ruleset
`round-robin-card-guardian-resource-turns-provisional-v2`. Guardian combat remains
schema 2. The previous arena had no trained checkpoints; existing duel curricula,
trained policies, and live controls are unchanged.

## Why attack origin is explicit

The pinned catalog has no plain numeric-DEF miracles. Wall (233) has the Bible
description `Block a NE weapon` and costs 6MP; Turbulence (234) has `Bounce a
miracle` and costs 5MP. Pretending these were ordinary armor would invent rules.
The new arena therefore adds typed, single-card offensive turns: 39 effect-free
fixed-attack weapons and six fixed-attack miracles. Exact values, elements,
categories, and costs must agree between the pinned Bible and API catalog.
These attacks have 100% hit rate and no special effects or additive behavior.

Attack origins are 0 weapon, 1 miracle, and 2 unclassified guardian. Guardian
events are deliberately not guessed to be weapons or miracles, so Wall and
Turbulence are masked against them. Diamond Axe and the Earth/Moon special
guardians remain unsupported. The turn schedule is still provisional: one card
attack, caller-selected guardian effect, or pass per living-player turn.

## Inventory, costs, and defenses

`deal_cards` accepts the 94 configured inventory models: 47 ordinary armor,
39 basic weapons, six basic attack miracles, and two defense miracles.
`deal_defenses` retains its defense-only restriction. The batch still uses up
to 18 stable slots, explicit instance IDs, and caller-controlled deals; it has
no redraw, acquisition/overflow policy, or hand compaction.

`begin_card_attacks` validates the entire batch before mutation: current living
turn owner, owned attack card, affordable cost, and a distinct living target.
Weapons are consumed at declaration. Attack miracles stay in hand and spend
MP at declaration, even if subsequently blocked, bounced, or defended. Their
cost is not charged again during defense or redirection.

Wall is legal only against a non-element weapon and with at least 6MP.
Confirmation blocks the whole attack, spends exactly 6MP, retains Wall, and
advances the original turn once. Turbulence is legal only against the supported
basic miracle attacks, with at least 5MP and no prior bounce. These special
defenses must be used alone; they cannot be combined with each other or armor.
Selection, deselection, and forgiveness do not spend MP. Ordinary armor combos
retain the prior legality and consumption rules.

## Explicit multiplayer bounce choice

Confirming Turbulence enters phase 4 (choose bounce target), without spending MP.
`bounce_target_masks` admits every other living player, including the original
caster; self-targets, eliminated players, and invalid indices are rejected.
`resolve_bounces` validates all rows before spending the defender's 5MP,
retaining Turbulence, clearing selections, and redirecting the unchanged attack
to the chosen player's defense phase. The original turn owner and attack model
remain unchanged. Only the final damage resolution completes the original turn.

This arena permits only one bounce per attack, matching the limited prior duel
curriculum but **not asserting official bounce-chain fidelity**. Ability-bearing
miracles, bouncing guardian events, compound attacks, and repeated bounces need
separate rules and evidence. The existing 64-toggle bound spans the bounce, and
turn limits still distinguish truncation from a winner.

## Observation and observability

The turn snapshot now has 11 columns. The original eight fields are followed by
selected MP cost, attack origin (-1 before any event), and bounce count (0/1).
Phase 4 has an acting player but no legal ordinary attack or defense actions;
callers must use its target-choice mask. Finished phases remain 2 won and
3 truncated, so callers must not treat all phases >=2 as finished.

`attack_action_masks` exposes hand-slot attacks plus pass (`H`); defense actions
remain hand-slot toggles, forgive (`H`), and confirm (`H+1`). Separate attack and
bounce target masks have one column per player. `hand_feature_snapshot` provides
copied, read-only `[environment, player, slot, 6]` arrays: role, ATK, DEF, element,
MP cost, reusable flag. Roles are 0 empty, 1 armor, 2 weapon, 3 attack miracle,
4 Wall, and 5 Turbulence. Full-hand snapshots are diagnostic state, not approved
policy observations of opponents' hidden hands.

Lifetime counters expose consumed cards, resolved effects, miracle casts, and
total MP spent. Reset clears inventory, resources, selections, turn and bounce
state while retaining lifetime counters. Input errors leave all state and
counters unchanged, including mixed confirmation and target-choice batches.

## Verification and readiness

Tests cover all 45 pinned offensive models, source-sensitive defense masks,
Wall reuse and exhaustion, exact offensive and defensive costs, redirecting to
the original caster or a third player, bounce target validation, special-defense
exclusivity, atomic multi-row errors, and reset/read-only observation behavior.
Seeded eight-environment card arenas exercise bounce target choice, finish
within their declared bound, and replay identical state and counters without
negative MP. MP-gain guardian events restore affordability in the same resource
state. These are consistency checks, not proof of official mechanics fidelity.
`simulation guardian-batch-plan --turns` now accepts initial MP and CP options.

This is not a full-game environment and remains ineligible for training and
promotion. The next boundary is a seeded rollout adapter with legal
actor-relative observations, rewards, evaluation, and a distinct checkpoint
schema. Full-game readiness additionally requires acquisition/overflow,
offensive combinations, utility/curse/illness behavior, special artifacts,
guardian timing/classification, teams, and official parity evidence.
