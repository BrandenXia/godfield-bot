# ADR 0060: Long-rollout league training and reproducible tail diagnostics

## Status

Accepted, 2026-09-28. Local training and diagnostic work only; no live authority
or official ruleset changes.

## Context

The first schema-11 candidate beats its migrated parent but one of three
512-decision evaluation gates fails. Seed 41068, environment 3442, candidate
seat zero finishes only at decision 609, with a candidate loss. Its explicit
21-to-30-action migration is valid; the failure is an actual long game,
not an action-map error or an infinite native loop.

`collect_self_play_rollout` deliberately resets all environments and recurrent
memories at every rollout start. The previous 64-step recipe therefore never
collects decisions later than 64 in an individual episode. Bootstrapped values
help, but they do not replace observing late positions and terminal outcomes.
This is a training exposure gap; it does not prove that longer rollouts alone
will eliminate every long game.

## Decision

Keep the collector's reset behavior, rewards, native rules, model architecture,
and strict evaluation gate unchanged. Use 512-decision rollouts in a separate
experiment, with 256 environments, 32-environment recurrent minibatches,
80 updates, two PPO epochs, no teacher updates, learning rate 0.0001, entropy
weight 0.02, seed 42067, CPU. This permits learning from later positions without
introducing cross-update recurrent-state staleness or changing terminal labels.
The collector still resets games at the next rollout boundary; this is not
unbounded episode continuation.

Freeze a broader schema-11 league with eight opponents: the heuristic at
weight 2, the first wide candidate, its migrated parent, and five explicitly
migrated historical checkpoints at weight 1 each. Migrating or freezing a
checkpoint is not acceptance, promotion, or a claim about official strength.
The first candidate's failed report remains unchanged.

League `da29243f-5bf8-41f1-acdc-162c12c38e8f`, SHA-256
`d43cef08e9dcee5590219799cdf61a1249d1a275fe7f5142c31c26ff53f75936`,
includes these source-to-target migrations, with exact weight hashes in the
persisted roster and migration manifests:

| Nine-slot source | Eighteen-slot target |
| --- | --- |
| `63de1747-f43f-4ef1-ae99-a1cd72dd3ec1` | `68fc1ecb-b236-4a13-bc58-40edcd19eacb` |
| `dd5bde4f-c5d5-44f2-b1db-4b4f1d049f56` | `968b78d4-9e5c-4d67-a995-fdb7d44e2767` |
| `3dfe4a94-4bc3-4d90-9691-853a7b543cd4` | `5157bbfa-b8c7-4760-adf5-11d4c07952a5` |
| `088ef7a5-c8bf-46e2-8469-4d2390719839` | `91bb3ce2-7f5d-427d-b742-eec5c524e791` |
| `df08842c-f5e8-4317-8721-0245310c92ac` | `c4e113d3-623c-43b3-b161-1577dc79d80a` |

## Observability

Self-play rollouts now record one-based episode decision ages, reset only on
actual terminals within the rollout. Logs and candidate manifests record the
longest observed episode and the count/fraction of learner decisions later than
64. They also record the unfinished fraction at rollout boundaries. Most games
are nonterminal on the final sampled step because completed games are replaced
throughout collection; that boundary fraction is **not** a timeout rate.
The extra-slot diagnostic remains separate and counts both actor policies.

Evaluation matchups add p95/p99 and maximum lengths among completed games,
plus up to eight `(candidate_seat, environment_index)` incomplete examples per
seat. Incomplete games are excluded from duration quantiles, never relabeled
as draws or wins, and still fail the gate. Missing fields in old reports remain
readable with unrecorded defaults. Scores, pairing, and confidence calculations
are unchanged.

Evaluation also has an opt-in `--compact-inference` mode. It skips neural
inference for first games already completed, while the full native batch still
steps legal filler actions on those rows. Per-environment RNGs are independent,
so filler games cannot affect remaining first deals. The legacy inference path
is still the default. Mode selection enters the hashed evaluation configuration.
As with singleton replay, smaller neural matrix sizes may change floating-point
ties; regression tests compare first-game outcomes, decision counts, completion,
and physical kernel transitions for both seats and opponent kinds. Confidence,
pairing, completion requirements, and the decision cap do not change.

A compact replay of the old 8,192-pair heuristic matchup on seed 41068 took
approximately 12.3 seconds on this machine while training was running. It
reproduced the original paired score exactly (`0.5713588084482969`), retained
one incomplete game, and reported example `(0, 3442)`. Maximum completed length
was 380. This is a diagnostic performance comparison, not a new acceptance
report or evidence that compact and legacy paths are bitwise identical on all
checkpoints. Any new apparent gate pass will also be checked with the legacy
path before accepting a local baseline.

`simulation trace-game` replays one native first-deal index against a frozen
checkpoint or the versioned heuristic, with separate memory per player. It
maps a batched environment to a singleton using
`(seed + environment * 0x9E3779B97F4A7C15) mod 2**64`, matching the native RNG
initialization. Tests verify mapped trajectories through actions and resets,
including overflow and unsigned wraparound. Different neural matrix batch sizes
can change floating-point ties; singleton traces are diagnostic evidence, not
a replacement for paired evaluation.

Traces contain actions, legal action names, observed HP (null when Fog-hidden),
diagnostic MP and illness state, before/after values, and terminal outcomes.
They are private files with model weight, client, vocabulary, ruleset, and input
fingerprints. They do not change model manifests, enter a training dataset,
or expose a gate-pass field. Source kind is `native-game-diagnostic-not-gate`,
with `promotion_eligible=false`.

## Reproduction

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot simulation trace-game \
  models/07759a38-203e-45cf-ba7a-c87e2d1dbf18 \
  --seed 41068 --environment 3442 --candidate-seat 0 --max-decisions 2048
```

Trace `c2c40208-c478-4f6e-95ea-afd7ac8727dc` reproduces the old 609-decision
loss. It contains 199 prior turn completions and repeated resource recovery:
the heuristic selected `<Big Tree>` 20 times and `<Spring>` seven times.
At decision 512, HP is still 45 versus 23. This was a prolonged resource-and-
combat sequence, not a frozen UI state. The original failure stays failed.

## Verification

All 534 non-browser tests pass, along with Ruff lint and Mypy across 56 modules.
New tests cover native seed mapping through actions and resets, uint64 wrapping,
range rejection, private deterministic non-promoting traces, compatible frozen
model opponents, checkpoint contract rejection, episode age accounting,
Fog-visible HP mapping to physical seats, persisted training-exposure metrics,
backward-readable report fields, strict failure despite winning scores when
games are incomplete, and compact-versus-legacy first-game comparisons.
The two browser-control tests are excluded because no browser code changed.

## Long-rollout experiment

The run produced candidate `e2555901-6f73-4ff3-9923-aae171b46c76`, weights
SHA-256 `09ace83baad5ba5d1acb3cb350cce1cc7cfbc12c7afb5ec39f9578c0ef698c38`,
with parent `07759a38-203e-45cf-ba7a-c87e2d1dbf18`. Its configuration and
eight-member league are described above. Training collected 10,485,760
transitions and 148,960 completed local episodes. Of 5,241,040 learner
decisions, 1,154,486 (22.03%) occurred later than decision 64. The longest
observed training episode reached 408 decisions. Extra hand slots accounted
for 2,247,885 decisions (21.44%) across both actor policies.

Every frozen checkpoint supplied at least 16,400 completed games and 571,000
actor decisions; the heuristic supplied 32,961 games and 1,161,989 decisions.
These are exposure metrics, not evaluation win-rate claims. Fresh gate seeds
are 43067, 43068, and 43069, with 8,192 paired deals per opponent, both seats,
unchanged strict score confidence thresholds, and a 512-decision limit.

The new candidate also completes the previously failing indexed deal at
decision 120 with a win, within the original 512-decision budget. Trace
`dbe3e573-a0fa-4795-bdea-d3de7d7c92c1` records this result. That known-case
regression is separate from the fresh held-out gate seeds; it is not counted
as independent acceptance evidence.

All three compact-inference gates pass every one of the eight opponents,
with zero incomplete games. Their evidence IDs are:

| Seed | Compact report | Longest completed game |
| ---: | --- | ---: |
| 43067 | `48eb6786-7003-4e36-8756-5ff07b06bbe8` | 403 |
| 43068 | `a00395b0-a7c0-43e3-8613-9eee22088783` | 483 |
| 43069 | `815592e3-cb9f-4050-8179-de91fb8ca549` | 445 |

The default, original inference path independently confirms all three passes
against the same eight-member roster. Each report contains 131,072 first-game
evaluations, with zero incomplete games and every paired lower bound strictly
above 50%. These are 393,216 fresh seed/opponent/seat evaluations; the compact
replays are not counted as three additional independent seeds.

| Seed | Heuristic score | Parent score | Parent lower bound | Default-path report |
| ---: | ---: | ---: | ---: | --- |
| 43067 | 58.49% | 51.03% | 50.47% | `af7e30aa-f009-4afc-a6db-786587506110` |
| 43068 | 57.71% | 51.54% | 50.99% | `5dd7c551-ac1c-48ed-8968-4ca16b211e46` |
| 43069 | 57.09% | 51.43% | 50.87% | `65970ce2-b21a-4d54-9653-43ad0b2c78d7` |

The five migrated historical opponents have scores between 54.02% and 60.70%
across these default-path reports; the migrated weighted parent scores
54.20–54.35%. The longest completed games remain 403, 483, and 445 decisions,
respectively, below the unchanged 512-decision cap.

Compact and default aggregate outcomes are close but not bitwise identical:
the largest matchup win-count difference is three out of 16,384 games
(0.0184 percentage points). One matchup's maximum length differs by five
decisions. This is consistent with the documented batch-size floating-point
sensitivity, not proof of identical policy trajectories. Both paths pass;
the default-path reports are the acceptance evidence.

To reproduce a default-path gate, repeat this command with seeds 43067, 43068,
and 43069:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models evaluate-simulation-league \
  models/e2555901-6f73-4ff3-9923-aae171b46c76 \
  --league models/leagues/da29243f-5bf8-41f1-acdc-162c12c38e8f.json \
  --ruleset wide-hand-gift-weighted-dream-resource-hand \
  --games-per-seat 8192 --max-decisions-per-game 512 --seed 43067 --device cpu
```

Candidate `e2555901-6f73-4ff3-9923-aae171b46c76` is now the verified local
schema-11 training baseline for this frozen capacity-stress curriculum.
Registry status remains `candidate`; no model promotion, official admission,
or live control setting changes. Passing this local gate does not demonstrate
official-bot strength or full game fidelity. Acquisition, ownership, hand
growth, overflow, guardians, trade, and multiplayer remain fidelity work.
