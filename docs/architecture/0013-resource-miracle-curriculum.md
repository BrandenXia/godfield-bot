# ADR 0013: HP/MP utility and miracle-cost curriculum

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0009 and ADR 0011

## Context

The schema-v4 native curriculum teaches elemental weapon/booster combinations
and multi-card defense, but it leaves the MP feature fixed at zero. The live
behavior policy can use deterministic recovery items and fixed-attack miracles,
while the learned policy must filter them out. This is now a material gap in
both decision quality and the fidelity of offline training.

Adding every miracle at once would mix exact resource decisions with random
damage, curses, targeting changes, and special effects. Those mechanics need
separate rules and evidence.

## Decision

Add the `resource-hand` native ruleset with observation schema v5 and keep the
existing 21-action head. Its accepted-Bible catalog is the schema-v4 combat
catalog plus:

- four unconditional HP sundries (+5, +10, +15, and +20);
- three unconditional MP sundries (+5, +10, and +15);
- six fixed-attack miracles with their exact element and MP cost;
- Spring, an unconditional +10 HP miracle costing 7 MP.

The initial nine-card deal contains three weapons, one booster, two armor
cards, two utility cards, and one fixed-attack miracle, shuffled per seat.
Consumed cards redraw uniformly from the complete catalog while preserving at
least one weapon. Miracles are reusable and remain in their slot. A miracle's
cost is checked before selection and deducted exactly once when its action is
committed. Weapon boosters cannot be attached to a miracle.

HP and MP are stateful per seat, observable in the existing normalized global
and player feature positions, and bounded to 100. A recovery action that cannot
change its resource is masked. Utility resolves as one complete turn; attacks
and defenses retain the schema-v4 sequential selection contract and sparse
terminal return.

Schema v5 changes semantics without changing tensor dimensions, so
`models migrate-resource-features` copies a slot-aware schema-v4 checkpoint
exactly into an immutable schema-v5 lineage node. Training and paired
evaluation require exact simulator/model schema equality. The versioned
resource heuristic prioritizes lethal attacks, emergency healing, MP recovery
that unlocks a stronger held miracle, and then the strongest available attack.

## Consequences

Native training can now learn resource timing and the opportunity cost of
miracles using the same policy head as live play. Catalog identity includes
utility values and miracle costs, so Bible drift invalidates stale comparisons.
The 100-point bound and ineffective-action masks prevent pure recovery loops
from becoming unbounded no-op trajectories; evaluation retains its explicit
decision horizon as a final liveness gate.

Conditional recovery, curse miracles, probabilistic attacks, additive
miracles, special defenses, guardians, trade, and phenomena remain outside
this ruleset. Schema-v5 candidates remain non-promotable until separately
validated against the resource heuristic and the established live safety gate.

## Initial milestone evidence

Candidate `d349d664-bfce-4997-9ff9-eb94482c20d1` was trained from schema-v5
migration node `374e463f-d976-49e4-b816-e617e6d82afc`, whose source was
schema-v4 candidate `4d4ecff5-45ed-4776-a0ef-2720d8204abe`. Training collected
2,752,512 resource-curriculum transitions, and teacher accuracy rose from
85.31% to 97.76%.

Evaluation `74c09a6c-e682-46b9-88e4-79032677ce62` used 4,096 paired deals per
seat and the 512-decision horizon. All 16,384 matchup games completed. The
candidate scored 62.92% against its frozen migrated parent with a 0.6194 paired
lower bound, and 51.16% against `plain-resource-aware-combo-v1` with a 0.5022
paired lower bound. Both exceed their respective 0.500 superiority and 0.475
non-inferiority thresholds. The stored model and evaluation remain ignored
local artifacts; the IDs and immutable checksums preserve their lineage.
