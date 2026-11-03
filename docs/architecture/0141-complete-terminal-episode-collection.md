# ADR0141: complete terminal episode collection

## Implemented boundary

`collect_full_game_episodes` implements the collection half of approved
ADR0140. It uses the kernel33 environment, public encoder1, recurrent policy1
and native terminal reward1. Neither the gameplay version nor any old arena,
checkpoint or live control changes. Full-game training and promotion remain
gated; this is validated training input, without a full-game optimizer yet.

One invocation owns one zero-command epoch per environment. It accepts trusted
setup or an already started zero-command episode, rejects previously played
rows, and checks actual team seeds against configured metadata. It starts
unstarted rows and collects terminal rewards before reading any further steps.
There is no reset, hidden substitution, or episode continuation across calls.
The explicit worst-case bound `batch_size × max_decisions ≤ max_stored_decisions`
is checked before play, with an absolute limit of32,768 retained decisions.

Behavior is a private CPU float32 policy copy whose canonical architecture and
tensor SHA-256 are checked before/after collection. Metadata also pins the
environment/source/cost rules, encoder and reward schemas, sampling seed,
storage bound, and a diagnostic fingerprint of actual initial setup. The
fingerprint is not a serialized resume state, and private setup is never an
encoder or neural feature. No caller policy weights are changed.

## Accepted data and exclusions

The collector records accepted public observations, six-column commands,
pre-action seat memory, behavior log probabilities and values. It retains the
exact actor, epoch, decision and phase for every accepted action. After a real
ending, each actual command receives the undiscounted terminal value of its
acting seat. Eliminated team members retain team credit; absent or eliminated
players never receive invented decisions. Forced turns keep value targets and
zero policy weight. A true draw has valid zero targets. A real ending before
any action has an empty sample table, not an invented training action.

Turn/decision limits retain ending/accounting diagnostics but expose no sample
table, including their previously accepted moves. A native rejected batch
preserves its exact attempted commands and error, verifies no command-cursor
change, stops collection, and excludes all still-incomplete rows. It does not
guess which row failed or resample actions; already verified complete episodes
retain credit. Encoder/policy/credit contract errors propagate as errors,
instead of being mislabeled as failed games.

`validate_full_game_collection` checks outcome/roster conservation, exact team
payoffs and validity, accepted command leases/masks, finite tensor layouts,
first-decision zero memory for each seat and the per-actor target mapping.
Retained arrays are owned readonly snapshots. Unaccepted commands appear only
in rejection diagnostics. `verify_full_game_behavior` replays each recorded
GRU edge under the pinned weights and checks its action log probability,
value, and memory handoff to the next decision of the same seat. It returns
ordered seat histories via `full_game_seat_sequences`; the optimizer will use
these histories for differentiable recurrence. Verification chunks only bound
storage and do not define an optimization gradient boundary.

## Verification

28 focused collector/replay tests pass. They exercise actual terminal interleaving
with eliminated teammate credit, forced value-only decisions, a real
post-death Bow draw, zero-command wins/draws, both native truncation kinds,
strict hidden-cost rejection after accepted commands, preservation of a
previously completed environment, frozen behavior isolation, preallocation
bounds, and rejection of forged targets/leases/values/memory starts. Replay also
rejects wrong behavior weights, forged probabilities and a broken seat handoff
even when its altered individual probability/value are internally consistent.

The32-game complete-pool diagnostic uses the same seeds and four rosters as
ADR0139. All32 finish without errors or limits, preserving the earlier
12,391 accepted decisions. All12,391 have valid per-seat targets; this random
network run did not encounter forced turns, which are covered by direct tests.
The same32 games verify all12,391 behavior decisions across144 seat histories;
maximum absolute log-probability error is2.3842e-7, value error2.2352e-8 and
memory-handoff error5.9605e-8. The collection regression passes13,178 tests in
218.11s, and the final focused suite covers the added replay checks. Static
checks pass135 modules. Diagnostic records are local at
`/private/tmp/godfield-full-terminal-collection-probe.jsonl` and
`/private/tmp/godfield-full-behavior-replay-probe.jsonl`. No checkpoint,
optimizer update, live game or user training data was written.

The next milestone is the bounded recurrent optimizer and restore/evaluation
path. Successful collection proves correct data flow and credit, not useful
learning or official fidelity.
