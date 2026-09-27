# ADR 0052: Official Training schema-v10 shadow bridge

## Status

Accepted, 2026-09-27.

## Context

The schema-v10 Dream candidate has repeatable native-gate evidence, but its
simulator observation contract was not available in official browser Training.
The older browser adapter stops at schema v5 and cannot represent pending
stochastic effects, illness, Fog, Flash, Dark Cloud, or Dream. Granting the
candidate control before measuring this boundary would conflate adapter gaps
with policy quality.

Official Training observations do expose the small per-player curse icons and
the displayed action artifact. They do not expose an attack-twice weapon's
remaining strike count. Fog can also hide an opponent's statistics, and a
browser hand can temporarily exceed the model's nine slots.

## Decision

Add `official-training-neural-shadow-v1` as a passive sidecar to
`play-training`. `--shadow-model` accepts only a candidate or champion bound to
the exact schema-v10 client, vocabulary, 21-action head, 24-wide global input,
and strict Dream sequential ruleset. It cannot be combined with
`--neural-model`. The existing heuristic remains the only browser controller.

The browser parser records actor-visible illness stage, Fog, Flash, Dark Cloud,
and Dream from exact small curse assets associated with each visible player
row. Medium action-panel curse art is not player status. The schema-v10 adapter
matches native pending-effect codes for absorption, same-damage, Cold, Hell,
Fog, Flash, Dark Cloud, and Dream. It fixes CP inputs at zero because the
current native curriculum does not model CP. It fails closed for hidden player
statistics, selectable hand slots beyond slot eight, non-duel games, action-head
collisions, and attack-twice responses whose remaining strike is not visible.

Each changed-state policy group stores one typed `EVIDENCE` event containing
the immutable model identity, behavior and proposal action IDs, coverage,
agreement, action probabilities, abstention reason, and recurrent reset state.
The sidecar never makes the evidence executable. Recurrent state advances only
when the shadow proposal agrees with the executed heuristic action; any
disagreement or unrepresentable observation resets it so counterfactual memory
cannot drift away from the real game.

`runs training-shadow` summarizes newly recorded evidence. `runs
evaluate-training-shadow` re-parses raw observations from older Training runs
with the current status parser and evaluates them without modifying the
append-only store. Status-free `GameState` digests retain their legacy byte
representation so existing replay trajectories remain valid.

## Initial retrospective evidence

The frozen candidate `df08842c-f5e8-4317-8721-0245310c92ac`, weights SHA-256
`471b096142e7468d9e7ff8189aa5c8490927cfefa5d103c57a32f362ef4e522c`, was
replayed over 30 recent official-CPU Training runs. Of 676 executable heuristic
decisions, 671 were representable: 99.26% coverage. The five abstentions were
two selectable overflow-hand states and three hidden-stat states. The candidate
agreed with 614 of 671 covered decisions, or 91.51%.

Confirmations, defenses, passing, and Forgive decisions agreed in this sample.
Most disagreement was artifact selection: the candidate selected weapons less
often and sundries more often than the heuristic. This may expose a useful
policy difference, but agreement is not a performance metric and historical
heuristic games contain no counterfactual outcome for the candidate's choice.

## Safety boundary

This bridge does not authorize schema-v10 live control, promotion, or outcome
training. A control gate still needs prospective official-bot games with a
safe intervention design, exact native-to-browser action support, sufficient
Dream/status coverage, and outcome evidence. Hidden Fog information must not be
filled from stale state merely to increase coverage.

## Verification

Unit tests cover curse-icon association, schema widths and status ordering,
pending effects including the Absorption miracle, hidden-stat and overflow
abstentions, immutable model admission, recurrent reset behavior, and summary
accounting. Full Python lint, type checking, and tests remain required, followed
by a prospective official Training game that records shadow evidence while the
heuristic controls every click.

Prospective official-CPU run `b3a534db-26df-49af-a274-04f88bf12a80`
completed normally on 2026-09-27. All nine executable decisions were covered,
all nine proposals agreed with the heuristic, and the interleaved Dream evidence
remained independently readable. The game was a loss; agreement in one game
does not alter the non-control safety boundary.

The broader prospective cohort and its adapter-readiness gate are recorded in
[ADR 0053](0053-official-training-shadow-readiness.md).
