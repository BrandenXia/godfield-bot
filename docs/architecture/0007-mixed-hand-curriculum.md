# ADR 0007: Mixed-hand attack/defense curriculum

- Status: **Accepted**
- Date: 2026-09-07

## Context

The fixed-role attack/defense curriculum always places weapons in slots one
through five and armor in slots six through nine. That makes early training
stable, but a policy can exploit position instead of recognizing a card's
role. The live game has mixed artifact hands, while adding elements or card
effects would also require new observations and rule evidence.

The next curriculum must broaden decisions without invalidating the existing
feature tensors, action head, trained checkpoint, or paired gate.

## Decision

Add `plain-mixed-hand-attack-defense-redraw-duel-v1` as a separately
fingerprinted mode of the native C++ attack/defense batch. Keep the existing
fixed-role ruleset available and unchanged.

Each reset deals exactly five neutral plain weapons and four neutral plain
armor cards to each player, then deterministically shuffles their slots from
the environment RNG. Using either kind redraws that slot uniformly from the
combined catalog, so the number and positions of each role can change. Attack
masks expose only current weapon slots. Defense masks expose Forgive plus any
current armor slots.

The simulator maintains an explicit attack-liveness invariant: every player
has at least one weapon. If a mixed redraw after an attack would remove the
last weapon, that consumed slot is redrawn from the weapon catalog. A defender
with no armor can always use Forgive, and the versioned curriculum heuristic
does so. This avoids permanent no-action states without pretending that the
simulator implements the live game's broader inventory, trade, or miracle
mechanics.

Expose the mode through `--ruleset mixed-hand` for simulation training and
evaluation and through `--ruleset mixed-attack-defense` for benchmarking.
Record its ruleset ID and
`mixed-role-uniform-redraw-with-attack-liveness` sampling distribution in
every training context, evaluation report, and benchmark result. The mode
keeps observation schema v2, action count 21, and `promotion_eligible: false`.

## Consequences

The slot-aware policy must recognize the artifact occupying each slot instead
of learning a fixed role by position. Existing slot-aware checkpoints can be
continued because tensor shapes and vocabulary are unchanged, but evidence
from the fixed-role gate does not transfer: a mixed-hand candidate needs a new
report whose simulator metadata names this ruleset.

The enforced weapon invariant slightly biases redraws in the rare last-weapon
case. That behavior is deliberate, observable in the sampling identifier, and
preferable to an unbounded synthetic deadlock. Elements, resource costs,
multi-card actions, effects, and multiplayer remain later versioned rule
boundaries.
