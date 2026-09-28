# ADR 0057: Local frozen opponent league and per-opponent gate

## Status

Accepted, 2026-09-28.

## Context

Official Training shadow games execute the heuristic's actions, so their win
rate does not measure the shadow neural candidate. Browser collection is also
slow compared with the native simulator. Further local PPO produced candidate
`3dfe4a94-4bc3-4d90-9691-853a7b543cd4`, which passed three independent
2,048-pair comparisons against parent `088ef7a5-c8bf-46e2-8469-4d2390719839`
and scored 55.18–55.69% against the Dream heuristic. Child
`dd5bde4f-c5d5-44f2-b1db-4b4f1d049f56` then improved the heuristic matchup to
56.79% in an 8,192-pair evaluation. Its paired lower bound against its parent
was 50.47%, while its lower bound against the heuristic was 56.08%. All 32,768
games in that report completed. These two continuations consumed 10,485,760
native transitions.

The second child's advantage against its parent is small compared with its
advantage against the heuristic. This motivates a broader local training and
evaluation roster. The comparison alone does not establish overfitting or
official-game strength.

## Decision

Add immutable league snapshots through `models create-simulation-league`.
The explicit roster always includes the training parent and exactly one
versioned heuristic, plus up to 15 operator-selected historical checkpoints.
Each snapshot stores the exact simulator contract, observation schema,
opponent identities, checkpoint paths and SHA-256 hashes, and positive sampling
weights. Model weights default to 1; the heuristic weight is configurable.
Duplicate identities, incompatible schemas, changed checkpoints, and missing
parents fail before rollout collection.

`models train-simulation --league <file>` uses algorithm
`frozen-league-recurrent-ppo-v2`. A weighted categorical draw assigns a frozen
opponent at every episode boundary. That assignment is constant for the entire
game. The learner's initial seats alternate across environments and swap at
each episode boundary. The roster replaces the old heuristic/self-play mix;
`heuristic_opponent_fraction` in the supplied legacy optimizer configuration is
unused in this mode. The effective heuristic share is retained in metrics.

The learner samples masked stochastic actions. Frozen models use deterministic
argmax, matching evaluation, with separate recurrent memory that advances only
on their decisions. Opponent memory and both learner seat histories reset at
episode boundaries. No frozen checkpoint has gradients enabled or belongs to
the optimizer. Policy, entropy, KL, and clipping terms exclude all frozen
actions; value learning retains the existing signed zero-sum trajectory. Sparse
terminal rewards and native rules are unchanged. Teacher imitation is optional
and can be disabled with `--teacher-updates 0` when continuing trained weights.

Candidate provenance embeds the complete roster and its canonical digest,
in addition to optimizer settings and simulator fingerprints. Logs and metrics
record actual actions, completed episodes, learner wins, and draws for every
opponent. Training episode counts remain diagnostics: rollout boundaries
truncate unfinished games and training actions are stochastic.

`models evaluate-simulation-league` loads the same frozen roster and verifies
its digest against the candidate's training context. Each opponent receives an
equal number of initial deals, evaluated with both candidate seat assignments.
Every matchup must finish every game within the horizon and have a paired lower
confidence bound strictly above `minimum_score` (default 0.5, never below 0.5).
This also requires superiority over the heuristic. Training sampling weights
never weaken an opponent's gate or evaluation budget. The overall verdict is
the conjunction of all matchup verdicts, not an average.

League evaluation uses a distinct report type and directory,
`models/league-evaluations/`. It cannot satisfy the existing official Training
readiness gate, which checks the two-opponent curriculum report contract.
League reports and trained checkpoints remain non-promoted local evidence.

## Verification

Tests verify canonical roster identity, owner-only persistence, changed-weight
and simulator-contract rejection, parent inclusion, episode-stable sampling,
alternating learner seats, exact recurrent replay of frozen neural actions,
legal actions, masked policy replay, unchanged frozen parameters after PPO,
persisted per-opponent metrics, and gate rejection for an unchanged parent or
any incomplete matchup. Legacy trainer and evaluation tests remain intact.

The first experimental roster is
`27967f4d-99f5-4797-af53-45f126874ee1`, canonical SHA-256
`9b74f961172bd8ff954148517b4f4a2cb47f3a792a258a8f3f4f5ebd74efbba8`.
It contains `dd5bde4f`, `3dfe4a94`, `088ef7a5`, and `df08842c` (full identities
and weight digests are in the roster), each at weight 1, and the Dream heuristic
at weight 2. The training parent is `dd5bde4f`.

The experiment produced candidate
`63de1747-f43f-4ef1-ae99-a1cd72dd3ec1`, weights SHA-256
`61b25d72e869534edfdf683ecca1340e68e66c8e0f1204ab95535f0c63bb2016`.
Training used batch size 512, 64 rollout steps, 160 updates, two PPO epochs,
128-environment minibatches, no teacher updates, learning rate `0.0001`, entropy
weight `0.02`, CPU, and seed 36067. It collected 5,242,880 transitions and
72,082 completed local episodes. Every frozen opponent supplied at least
11,817 completed episodes and 429,668 decisions.

The unchanged candidate passed every opponent on three independent 8,192-pair
deal seeds. Each opponent completed 16,384 games per seed; the combined
245,760-game evaluation had no incomplete games. All individual paired lower
bounds exceeded 50%, including against the strongest parent.

| Seed | Parent score | Parent lower bound | Heuristic score | Heuristic lower bound | Report |
| ---: | ---: | ---: | ---: | ---: | --- |
| 37067 | 50.98% | 50.40% | 57.71% | 57.01% | `345b1275-5216-4126-8286-1bf0b6b9da8e` |
| 37068 | 50.83% | 50.25% | 57.70% | 56.99% | `caddfe56-3e7e-4ecf-a84f-8d2f6d07a3e4` |
| 37069 | 50.80% | 50.21% | 57.22% | 56.52% | `7c740d42-011c-4a5d-9532-2bfc5ff7a643` |

Against the other three ancestors, scores ranged from 51.37–52.29%
(`3dfe4a94`), 53.88–54.90% (`088ef7a5`), and 56.31–56.72% (`df08842c`). The
candidate is the new baseline for further local training. Its registry status
remains `candidate`; no official run or live authority was changed. Verification
finished with 483 non-browser tests passing, Ruff passing, and Mypy passing
across all 55 source modules.

## Consequences

Most training experience can now come from fast local games while official
collection is used to discover simulator gaps and validate transfer. League
training can improve robustness across the policies in its roster, but the
current 196-card, nine-slot, two-seat Dream curriculum still excludes official
mechanics. Passing this local gate cannot establish full-game fidelity.

Adding a newly accepted checkpoint means creating a new snapshot for the next
training run. An existing roster cannot silently acquire a new opponent or
different weights halfway through an experiment. Automatic roster selection,
adaptive sampling, and neural live authority remain separate decisions.
