# ADR 0026: Candidate learning from the official Training computer

- Status: **Accepted**
- Date: 2026-09-11
- Amends: ADR 0012

## Context

The official Training computer is browser-local, so its games cannot be reached
through pygodfield. The browser campaign already records accepted actions and
sparse terminal outcomes, but `heuristic-v0` controlled every game and the
outcome trainer imitated winning and losing moves equally. No learned candidate
could gather candidate-controlled evidence against the official computer.

The browser exposes more effects than the current native curriculum, and some
Fog frames intentionally hide opponent statistics. Letting a model infer either
an unreviewed click or a value for missing input would weaken the existing
browser safety boundary.

## Decision

Add `official-training-neural-v1` as an explicitly confirmed policy for
`play-training`. It accepts only candidate or champion schema-v4/v5 models tied
to the accepted client, vocabulary, 21-action architecture, and matching native
sequential-action ruleset. Every run records the immutable model ID, weight
checksum, feature schema, and sampling seed.

The model samples only among non-Wait actions produced by the existing
Bible/DOM verifier. It cannot create an action or click target. When no reviewed
action exists, it waits without advancing neural memory. When a state with an
executable action cannot be represented because player statistics are hidden,
the policy resets recurrent memory and delegates that decision to
`heuristic-v0`. Each campaign game increments a recorded seed so
the action sampling is reproducible without repeating one exploration stream.

An over-capacity hand is representable when every legal artifact selection is
still within the model's first nine slots. The encoder truncates only the
non-selectable overflow cards; if an overflow slot is selectable, neural control
continues to fail closed and delegates the decision. This keeps the immutable
21-action head safe while retaining forced pass/confirmation decisions that
occur during temporary ten-card hands.

Outcome-replay schema v2 records the source run mode. Export can be restricted
to one model ID. Official outcome training accepts a dataset only when every
episode:

- is a completed, terminal-classified Training run;
- was controlled by `official-training-neural-v1`;
- names the exact base model being updated; and
- matches the base model's client fingerprint.

Representable neural decisions use a signed sparse terminal advantage: winning
actions are reinforced, losing actions are suppressed, draws use the learned
value baseline, and the value head learns the final result. The training mask
also removes Wait, matching the control-time policy. Hidden-stat fallback steps
and selectable overflow steps are excluded and split recurrent sequences at
the same memory-reset boundary. Candidate provenance records both the skipped
step count and a count grouped by encoding failure reason.

Training writes a new immutable candidate. It preserves the parent's native
simulation contract, adds official-training provenance, and never changes the
model controlling an in-progress game. The child must pass fresh native and
live readiness gates; collection or training never promotes it automatically.

## Consequences

The bot can now collect its own outcomes against the actual official computer
and improve between bounded batches while retaining exact model/data lineage.
Heuristic history, private-room shadow games, mixed-model datasets, incomplete
games, and unsupported observations cannot silently enter this update.

This is not unrestricted browser control and it does not broaden the reviewed
artifact/action surface. Learning quality still depends on enough completed
games and on re-evaluating every child candidate before broader deployment.
