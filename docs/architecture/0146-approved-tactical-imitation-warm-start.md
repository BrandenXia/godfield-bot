# Tactical imitation before terminal PPO

The user approved a separate warm start from the public tactical baseline,
followed by the existing complete-episode terminal PPO objective.

`full-game-train --imitation-batches N` creates a fresh policy, plays bounded
batches with `full-game-public-greedy-v1` controlling every seat, and fits masked
cross-entropy to accepted teacher choices. Both observation versions and all
native solo/team rosters are supported. The default of zero batches preserves
the existing training path. `--imitation-seed` and `--imitation-epochs` control
the demonstration schedule and passes over each batch.

The teacher receives only encoded public observations and pinned displayed-card
profiles. It has no engine handle, private card identities or hidden resource
values. The native six-column command validator remains authoritative. Any
command or engine error aborts warm-up before a candidate is published. All
prior choices from truncated episodes are excluded. Real winners and draws
are admitted. Demonstrations retain the native forced-turn mask, and confusion
choices receive no supervised loss.

Each environment/seat sequence starts with zero recurrent memory and proceeds
chronologically. Forward memory crosses truncated backpropagation windows
through a detached tensor. Seats and episodes never share memory. Each epoch
accumulates a mean supervised loss over voluntary terminal decisions and takes
one clipped Adam step. The value head receives no supervised labels or direct
updates. Shared encoder updates can still change its predictions. A failed fit
restores both policy and optimizer state. One demonstration batch is retained
at a time, bounded to 32,768 accepted decisions with at most 2,048 decisions
per differentiable group.

PPO starts a fresh Adam optimizer from the resulting weights. Its complete
terminal faction rewards, forced value-only updates, incomplete-episode
exclusion and replay checks are unchanged. The optional imitation report
records the teacher version, environment, observation version, seed schedule,
demonstration content hashes, outcome and phase counts, before/after supervised
metrics, and policy hash chain. It is attached to the existing candidate
manifest. Old manifests remain readable. Resume retains this report and resumes
PPO without repeating imitation. Checkpoints with imitation require an explicit
`--greedy-baseline` or compatible `--baseline` for evaluation.

Teacher seeds must be disjoint from the entire PPO schedule. Resume checks the
extended schedule, and evaluation excludes both teacher and PPO seed ranges.
This implementation starts imitation from fresh weights. Combining it with
`--initialize-from`, or history transfer from an imitation checkpoint, is
rejected explicitly until that additional provenance path is implemented.
Choose `--attack-history` at the start to train observation version 2 directly.

## Local evidence

The duel pilot used 32 batches of eight teacher games, 16 supervised epochs per
batch, then 16 PPO batches of eight games. Teacher collection completed 249
wins and seven draws with 27,212 voluntary decisions. PPO completed 126 wins
and two draws. No episode hit a turn/decision limit or engine error.

Against the final fixed tactical baseline, the duel candidate scored 16–48
and 20–44 on two 64-game seed sets, with no draws or truncations. These results
establish a functioning local learning path and leave the strength gate open.
The earlier history checkpoint used 2v2 teams, so its results cannot be used
as a direct comparison with this duel pilot.

A matching 2v2 history pilot used PPO seed 1130000, teacher seeds 1140000
through 1140031, and the same batch/epoch counts. Its 256 teacher games ended
with 252 wins and four draws, supplying 47,017 voluntary decisions. Its 128
PPO games ended with 127 wins and one draw. All games completed.

On seed sets 1150000 and 1160000, the new candidate scored 13 wins, 49 losses,
two draws and 19 wins, 44 losses, one draw against the tactical baseline.
The previous history checkpoint scored zero wins, 63 losses, one draw and
two wins, 62 losses, zero draws on the same roster and seed sets. Neither
candidate had truncations. The new candidate's 32/128 wins improve on the
previous checkpoint's 2/128, while remaining below competitive strength.
This comparison measures the resulting candidates and does not isolate the
contribution of each training choice.

The 2v2 checkpoint and evaluation reports are retained locally under
`runs/full-game-imitation-candidates/2b349d44-d29b-46ca-82e4-209ca04f1b7c`.

A further 48 PPO updates resumed that checkpoint without repeating imitation.
The additional 384 games completed with 381 wins and three draws. On the same
two diagnostic seed sets, the resumed candidate scored 14–50 and 24–40 with
no draws or truncations. Its 38/128 wins are a modest increase over 32/128;
this comparison does not establish a reliable strength gain. The resumed
checkpoint and evaluations are retained under
`runs/full-game-imitation-candidates/6b3e8729-719b-432a-9910-069cff5ceab8`.

A separate 16-game teacher-state diagnostic at seed 1190000 measured the
16-update candidate's argmax agreement by phase. Ready/card selection was
59.0% over 842 decisions, composition 93.0% over 826, targeting 86.5% over
555, and defense 72.3% over 1,107. These are decisions encountered under the
teacher's policy, rather than win rates or the candidate's own state
distribution. They identify opening-card selection and defense as useful
next training targets. The diagnostic is saved with that checkpoint.

Tests cover terminal/truncation filtering, forced-turn exclusion, teacher-label
agreement, seat order, supervised improvement, value-head preservation,
rollback, invalid labels, exact split-run PPO resume, provenance tampering,
seed overlap, CLI integration and native multiplayer rosters.

The local mechanics remain provisional where previously labeled. Neither
imitation accuracy nor local wins establish official fidelity or eligibility
for live promotion. All readiness and promotion flags remain false.

The final non-browser regression suite passed 13,210 tests. Ruff, mypy across
139 source files, formatting checks and the offline lock consistency check
also passed. A CLI test initially leaked its captured logging stream into
later tests; it now isolates logging configuration using the existing test
pattern, and the full suite passed after that correction.
