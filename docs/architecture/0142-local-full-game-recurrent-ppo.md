# ADR0142 — Local full-game recurrent PPO

The first full-game learner uses native kernel 33, the public encoder and the
complete-episode collector. The terminal targets follow ADR0140. Training runs
locally with all 237 held models, 18 hand slots, 28 native choices and the
configured roster of 2–9 players. Full-game readiness, official fidelity and
live promotion remain gated.

Each batch uses frozen behavior weights and fresh recorded environment and
sampling seeds. Behavior replay verifies action probabilities, values and
seat memory before optimization. The optimizer splits each player's ordered
decisions into 32-decision windows by default. Each window starts at the
recorded behavior memory and unrolls the current GRU within the window.
Gradients accumulate across bounded groups before one Adam step per epoch.

The clipped policy objective uses terminal outcome minus the recorded value
as its advantage. Clipped value loss includes every valid terminal target.
Policy loss and entropy use the voluntary decision mask. A failed optimizer
step restores the policy and Adam state. Native errors stop the run with
rejected commands and outcome accounting. Batches with zero terminal samples
record a skipped update.

`simulation full-game-train` reports update progress and can write a separate
candidate directory containing weights and a checksummed manifest. The
manifest records source and ruleset pins, optimizer settings, the recurrent
boundary, seeds, outcomes and a chain of behavior and resulting policy hashes.
The loader validates and restores policy weights for inference. Optimizer
resume requires a follow-up training-state format.

`simulation full-game-evaluate` restores the candidate and recreates its
initial weights as a frozen baseline. It checks the initial tensor digest,
ruleset and source pins. Each native faction takes a turn using the candidate
while the other factions use the baseline. Each assignment starts with the
same held-out seed pair, and the report separates wins, losses, draws and
native limits.

A 12-update 2v2 run with seed 67 finished 96 games, used 35,062 terminal targets
and produced finite gradients in every update. Nine decisions carried value
credit with zero actor weight. Two updates on the nine-player mixed roster
finished eight games and used 6,090 terminal targets. Candidate restore and
repeat training from the same seed are covered by the focused tests.

On 128 held-out 2v2 games across seeds 100000 and 200000, the 12-update
candidate scored 62 wins and 66 losses. The scores were 29–35 and 33–31 on
the two seed batches. A 32-update run reproduced the first 12 update reports
and policy hashes exactly. It finished 256 games, used 94,647 terminal targets,
and changed weights in every update. On another 128 games at seeds 300000 and
400000 it scored 68 wins and 60 losses, split 35–29 and 33–31. Both evaluations
finished every game with a winner. The strength gate stays open.

The local records are `/private/tmp/godfield-full-ppo-v1-train12.json`,
`/private/tmp/godfield-full-ppo-v1-train32.json` and the corresponding
`/private/tmp/godfield-full-ppo-v1-eval*.json` reports.

The full nonbrowser suite passed 13,186 tests in 221.03 seconds. The focused
checks cover optimizer rollback, forced value-only updates, checkpoint
restore, deterministic training and both 2v2 evaluation assignments.
