# ADR 0054: Official Training one-intervention canary

## Status

Accepted.

## Context

The schema-v10 candidate passed the immutable official-Training shadow readiness
gate, but that gate measures adapter coverage and integrity rather than candidate
win rate. Giving the model an entire official game would cross too many safety
boundaries at once and would make a failure difficult to attribute.

## Decision

Add an explicitly authorized mixed-policy canary for official Training games.
Admission requires all of the following:

- a schema-v10 candidate or champion whose client, vocabulary, architecture, and
  native simulation contract match the pinned Bible snapshot;
- a typed shadow-readiness report that passed, is marked ready for guarded
  intervention, has no gate or evidence errors, and names the exact model ID and
  weights digest;
- `--confirm-canary-intervention` at the CLI boundary.

The heuristic makes every decision except the first candidate disagreement that
is fully representable, has candidate probability at least `0.75`, and leads the
heuristic action by at least `0.25`. Candidate agreement does not consume the
budget. A low-confidence disagreement, hidden-stat state, encoding gap, or
non-executable state leaves control with the heuristic. After one intervention,
candidate inference stops for the remainder of that game and recurrent state is
reset. A new game creates a new policy instance and therefore a new budget of
one.

Every decision is followed atomically by typed `official_training_canary`
evidence containing the heuristic action, candidate proposal and probabilities,
chosen action, readiness identity, reason, budget state, and whether an
intervention occurred. The run policy identifies the mixed canary, while the run
`model_id` remains empty. Candidate identity is stored in the canary-specific run
configuration and evidence. Consequently, model-filtered outcome export and
outcome training cannot misclassify a mixed-policy game as a fully
candidate-controlled episode.

An unaccepted browser action still ends the game under the existing fail-closed
runner contract. The consumed intervention is never replayed or replaced by a
second candidate action. Any gameplay abort ends a canary campaign without the
normal automatic gameplay retry, because starting another game would refresh the
intervention budget. Pre-game setup recovery remains bounded and cannot spend an
intervention.

## Consequences

The first live test can measure command validity and immediate state transition
under minimal exposure. Its terminal result is evidence about the mixed canary,
not candidate win rate and not promotion evidence. Broader control requires a
new decision after canary trajectories have been audited.
