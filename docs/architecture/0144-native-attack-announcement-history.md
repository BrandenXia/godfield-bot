# ADR0144 — Native attack announcement history

The kernel 33 encoder observes the current decision. Its recurrent memory
updates for the active seat after an accepted decision. A seat can therefore
miss the announcement of an attack it launched, especially when another seat
answers the attack and the next decision starts a new turn. The native engine
now retains these announcements in a separately versioned view.

Captured official Training browser observations from run
`0cd8f1ef-412b-4f3a-8112-bf4d6db0924d` show attack actor, target and power from
both participant perspectives. The reviewed observations with both actor and
target visible are two-player views with visible player resources. This
evidence supports participant visibility and leaves spectator and Fog-source
visibility open. The simulator gives the announcement to the defender, whose
existing response view already exposes the incoming attack. It also gives it
to the source if the source has no Fog at announcement time. Uninvolved seats
receive no entry. This projection and the eight-entry retention limit are
local choices.

Native 0.84.0 exposes `FULL_GAME_ATTACK_HISTORY_SCHEMA_VERSION = 1` and
`attack_history_observations()` with shape `[batch, 8, 8]` and dtype `int64`.
Each nonpadding row contains, in order, present flag, source seat, target
seat, attack power, element, origin, hit rate and completed turns at opening.
Rows are oldest to newest with leading zero padding. Source means current
damage source, so a reflection can change it. Only the current acting seat's
history is exposed. Setup and inactive rows are zero. Results are owned
read-only copies.

An announcement is recorded when a command opens an interactive combat
response. Reflections and bounces that open a new response append a separate
entry. Commit writes the revealed fields to a preallocated per-seat ring after
every command row has validated. Reset clears the rings of the selected
environments. The native command and gameplay schemas remain at 1 and 33.

## Learner and checkpoint transfer

`full-game-train --attack-history` enables observation and architecture
version 2. Each of the eight rows adds a presence flag, actor-relative seat
one-hots, element and origin one-hots, log-scaled ATK and age in completed
turns, and hit-rate fraction. Padded rows are zero. The encoder checks row
order, actor participation and bounds before passing the features into the
policy. Episode collection and behavior replay pin the versioned input
layout. Recurrent memory still belongs to each seat independently.

The original 112 global features and existing policy layers keep their
layouts. A bias-free linear layer projects the appended history and adds it
to the existing context embedding before the GRU. Starting this projection
at zero preserves the original logits, values and next recurrent state for
the same base observation and previous memory. Its weights can receive a
gradient from the first batch with observed history.

`--initialize-from` loads a compatible version 1 policy checkpoint, copies
its weights and initializes fresh Adam state for the version 2 run. Source
pins, roster and gameplay settings must match. Batch size and seeds may
differ. The run records both policy hashes and the source's seed range.
Training and resume reject overlap with the source range. The evaluator
requires an explicit baseline for transferred candidates and can project a
compatible version 1 baseline in memory without changing its predictions.
Evaluation excludes the training seed ranges of both sides and their source
runs. Version 1 inputs and checkpoint loading remain available by default.

Full-game readiness, official fidelity and live promotion remain gated.

## Local validation

The transfer test compares logits, value and next GRU state exactly on an
observation with a populated history and nonzero previous memory. The CLI
test verifies that PPO changes the new projection weights and that a split
transferred run produces the same report as an uninterrupted run. Native
tests cover selective reset, ring wraparound, reflections, market separation,
transaction rollback and counterfactual hidden-state visibility.

A transferred 2v2 pilot completed 128 training games over 16 updates and
produced 54,530 terminal targets. Against its frozen version 1 parent it
scored 33–31 and 29–35 on two 64-game held-out sets. A separate ablation
zeroed only the trained history projection in the opponent. The history
candidate scored 32–32 on each of two 64-game held-out sets against that
ablation. Every evaluation game reached a terminal outcome. These tests
leave the strength gate open. A fresh nine-player mixed-team pilot completed
all eight training games and produced 6,186 terminal targets.

The non-browser regression suite passed 13,196 tests. Ruff, mypy and the
offline lock consistency check passed.
