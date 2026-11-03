# ADR0143 — Full-game Adam resume

`simulation full-game-train` writes version 2 checkpoints when a checkpoint
root is supplied. A checkpoint directory contains policy weights, Adam
moments and a manifest. The writer verifies the state and publishes all three
files together. Version 1 weights remain available through the candidate
loader and can serve as frozen evaluation opponents.

`simulation full-game-resume` starts at the next batch boundary. It inherits
the roster, rules, optimizer configuration and original seed from the
checkpoint. The number of additional batches extends the report's total
update budget, up to 256. Each batch uses the original seed schedule and
creates a fresh native environment. A saved checkpoint includes all reports
through its last batch. Skipped batches retain their seed position.

The loader checks each file's checksum and loads CPU tensors through
PyTorch's weights-only reader. Resume also checks parameter order, the Adam
group settings, finite moment tensors and the step count implied by the
completed optimizer updates. For the actor head, batches with only forced
decisions contribute value updates and leave the actor step count unchanged.
The manifest pins the PyTorch build, machine and numeric settings. Resume
also checks the configured native environment against the original source
and ruleset before collecting the next batch.

`simulation full-game-evaluate --baseline` accepts a compatible frozen
checkpoint. Its policy architecture and environment pins must match the
candidate. The evaluation seed pair must be disjoint from the recorded
training seeds of both models. Each faction receives the candidate in a
separate assignment, with the baseline controlling the other factions.

The focused test splits a 2v2 run after one batch, resumes for two batches
and compares it with an uninterrupted run. The update report, policy digest,
Adam parameter groups and every moment tensor match exactly. The test also
checks the source checkpoint files after the resumed run. A separate test
recomputes the checksum after altering a saved step counter and verifies
that resume rejects the altered state.

The non-browser regression suite passed 13,189 tests before the frozen
checkpoint evaluation option was added. All 10 focused training and
evaluation tests passed with that option included.

A longer 2v2 run saved after 12 batches and resumed for another 84. Its first
32 update reports match the earlier uninterrupted run, including policy
hashes. It finished 768 games and trained on 285,748 terminal targets.

The 96-update candidate scored 68 wins, 59 losses and one draw in 128 games
against its initial weights at seeds 500000 and 600000. Against the frozen
32-update checkpoint it scored 68 wins, 58 losses and two draws in 128 games
at seeds 700000 and 800000. Every evaluation game reached a terminal outcome.
The two sets against the earlier checkpoint scored 30–33–1 and 38–25–1.
The strength gate remains open. Reports are under
`/private/tmp/godfield-full-ppo-v2-*.json`.
