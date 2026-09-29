# ADR 0083: Bounded guardian turns and consumable armor

## Status

Accepted, 2026-09-29. Native package 0.42.0 adds `GuardianTurnBatch`, with
kernel and observation schemas 1 and ruleset
`round-robin-guardian-armor-turns-provisional-v1`. The existing guardian combat
schema 2 and all trained duel curricula/checkpoints are unchanged.

## Scope and provisional scheduling

The new batch composes `GuardianCombatBatch` rather than allowing a policy to
invent defense values. Two to nine players rotate through living-player turns.
Each turn permits one caller-selected effect from a guardian belonging to the
current player, or an explicit pass. Immediate utility effects advance the turn;
attacks first await the target player's defense. Random selection and hit tickets
are caller supplied. Wrong owners and unsupported selected effects fail the
entire call without mutation or resampling.

**This is a bounded local arena scheduler, not the official guardian trigger
schedule.** Catalog weights and this timing remain provisional. Guardians of
eliminated players are retained in diagnostic state but cannot act. The last
living player wins; teams, draws, resurrection, death-trigger cleanup, Earth,
Moon, and Diamond Axe classification are not implemented here.

## Inventory and legal actions

The pinned Bible and API catalog must agree on 47 effect-free armor models and
their exact defense values and elements. Native profiles are model/DEF/element.
Cards have caller-supplied instance IDs and occupy up to 18 stable padded slots
per player. Deals must address empty slots and have unique instance IDs within
each environment. There are no automatic draws, acquisition probabilities,
overflow effects, or hand compaction in this component.

For `H` hand slots, defense actions `0..H-1` toggle a compatible owned armor
card; `H` forgives and `H+1` confirms the selected combination. The action mask
is zero outside defense. Empty or element-incompatible cards are masked;
confirmation requires at least one selection. Each selected card must be
compatible independently. Selected defense sums are saturated at 65535, the
combat kernel's attack bound. Light attacks have no legal armor selection.

Only confirmation consumes the selected armor. Forgiveness clears selections
without consuming cards. Unselected inventory is preserved. Deals and guardian
lifecycle edits are prohibited while defense is pending. Every batch call
validates all rows before any selection, consumption, resource, or turn update.
These effect-free armor cards have no MP costs; reusable miracle defenses and
special armor effects are still missing.

## Bounded episodes and observations

`max_turns` is required to be positive, defaults to 1000, and caps at one billion.
Reaching the turn limit truncates the episode, not a win/loss. Repeating card
selection toggles also truncates after 64 actions in one defense. This keeps a
policy that never confirms from stalling a rollout forever. A win on the last
allowed turn takes precedence over truncation. Truncated pending combat state is
retained for diagnosis, has no legal actions, and can only be reset.

Copied read-only observations:

- Turns `[environment, 8]`: phase (0 ready, 1 defense, 2 won, 3 truncated),
  turn owner, acting player (-1 after finish), completed turns, winner (-1 if
  absent), truncated flag, selected defense, and defense-toggle count.
- Inventory `[environment, player, hand slot, 3]`: instance ID, model ID,
  selected flag. Empty slots have zero IDs.
- Defense masks `[environment, H+2]`, plus the existing guardian, combat, and
  HP/MP/CP/curse observations.

Reset validates the complete environment list before restoring resources and
clearing guardians, inventory, selections, and turns. Lifetime resolved-effect
and consumed-card counters remain cumulative for observability.

Regression checks cover every one of the 39 supported pinned effect models,
combined defense consumption, mixed selection/confirmation/forgiveness batches,
atomic failures, both truncation limits, nine-player rotation, and winning on
the last allowed turn. Thirty-two seeded synthetic Mars arenas finish within
the declared bound and reproduce identical resources, turns, and inventory
when replayed. These checks demonstrate component consistency, not official
timing or mechanics parity.

## Readiness and next boundary

`simulation guardian-batch-plan --turns` inspects the pinned configuration without
playing online or training. Metadata still marks local-training eligibility,
full-game readiness, official fidelity, and promotion false. This arena does not
share the old 21/30-action checkpoint vocabulary: with 18 slots its defense-only
vocabulary has 20 actions. No checkpoint is implicitly migrated or enabled live.

Next, reusable defenses need inventory retention, affordability, MP deductions,
and effect-specific legality. An episode/rollout adapter then needs seeded
scenario generation, defender observations, rewards, reproducible evaluation,
and separately versioned checkpoints. Full-game training additionally requires
offensive card turns, acquisition/overflow, special effects, illness/curse
behavior, multiplayer teams, and official parity evidence.
