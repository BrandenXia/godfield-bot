# ADR 0005: Paired curriculum evaluation

- Status: **Accepted**
- Date: 2026-09-07

## Context

Native PPO can produce a candidate quickly, but its training loss and self-play
return do not establish that it improved. Evaluation also has substantial seat
and initial-deal variance. Comparing one model only as the first player, or on
an unrelated set of deals, can mistake that variance for policy strength.

The attack/defense curriculum is still much smaller than God Field. Passing a
native comparison therefore must not be interpreted as permission to promote a
checkpoint or use it in a live room.

## Decision

Evaluate a candidate against two fixed opponents:

- the exact parent model named and checksummed by the candidate manifest;
- the versioned `plain-max-attack-conservative-defense-v0` heuristic, which
  attacks with its strongest available plain weapon and defends with the
  weakest sufficient plain armor, falling back to its strongest armor.

Both neural policies use deterministic masked argmax actions with independent
recurrent state per physical seat. The parent is loaded once in evaluation mode
and is never updated. For each opponent, run every seed twice: once with the
candidate in seat zero and once with it in seat one. The two runs start from the
same simulator seed, so each indexed environment receives the same initial
deal with seat ownership swapped. Report win-both, split, lose-both, and
incomplete pair counts in addition to aggregate results.

Score a win as one, a draw as one half, and a loss as zero. A matchup passes
only when every game terminates within the configured decision horizon and the
Wilson lower confidence bound on candidate score is at least the configured
minimum. The overall gate is the conjunction of the parent and heuristic
matchups. Defaults are 512 paired seeds per seat, a 512-decision horizon, a
minimum lower bound of 0.5, and `z = 1.96`.

Write each result as a new owner-only JSON report. The report binds candidate
and parent IDs and weight hashes, exact simulator metadata, heuristic version,
seed and evaluation settings into an input digest. It records the outcome,
confidence bound, pairing diagnostics, work performed, and human-readable gate
reasons. Evaluation does not modify either model manifest.

The report always carries `promotion_eligible: false`, including when the gate
passes. A future live-game gate and explicit operator promotion decision remain
separate work.

## Consequences

Seat swapping removes the largest known curriculum confound and makes an
unchanged candidate produce complementary paired outcomes against its parent.
The frozen heuristic prevents a candidate from appearing improved solely
because it co-adapted with its parent lineage. Wilson bounds make small samples
visibly inconclusive instead of silently passing on a point estimate.

Evaluation costs four batched simulator runs and uses deterministic policy
actions, so it measures current exploitation rather than stochastic training
behavior. Games that exceed the horizon fail closed. Passing still says only
that a model cleared this exact synthetic ruleset and these two opponents; it
does not measure elements, resources, multi-card defense, larger rooms, or the
live client contract.
