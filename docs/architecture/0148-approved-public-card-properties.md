# Version 3 public card properties

The user approved adding displayed-card attack, defense, cost, element and role
features with an explicit prediction-preserving checkpoint transfer. The goal
is to reduce the amount of basic card knowledge that the recurrent policy must
learn through card-ID embeddings alone. Gameplay remains kernel 33/native
0.84.0. This changes the separate learner's observation and architecture to
version 3, preserving versions 1 and 2.

`full-game-train --public-card-features` enables version 3, including the
existing attack-announcement history. Each of the 18 displayed own-hand slots
gets 42 additional properties. These include fixed attack, a separate
MP-dependent attack coefficient, defense, costs separated by action role,
utility value, price, hit rate, strike count, element, capability bits, utility
kind, special defense type, element-setting/doubling flags, reusable-miracle
status and Fate. Numeric magnitudes use the existing signed log scaling;
probabilities, strike fractions and flags have explicit field names.

Properties come only from the source-pinned public profiles of the displayed
model ID. Dynamic attacks retain their coefficient rather than claiming a fixed
resolved attack. Adjacent reductions, compositions and actual hidden costs
remain stateful native rules; these properties do not predict their outcome.
Dream's actual card never selects the feature row. Fog-hidden opponents, private
inventories, future events and diagnostic snapshots are never consulted.
Padding and inactive rows stay zero. All 237 held models have their public
capability bits represented, including the three trade cards.

The original 27 hand fields retain their order. The new 42 fields append to
that tensor, while the existing card encoder continues to read only its original
prefix. A bias-free linear projection maps the new properties into the existing
card representation. It starts at zero. Version 3 retains the version 2 history
input shape, recurrent memory and 28 native choices.

## Transfer, training and provenance

Add `--initialize-from VERSION_2_CHECKPOINT` to copy a compatible history policy.
Every old tensor is preserved and the new projection starts at zero, preserving
logits, value and next recurrent state before training. Transfer keeps the
caller's Torch RNG state and starts fresh Adam state. It requires the parent's
roster and gameplay bounds. The parent checkpoint is never overwritten.

Optional imitation may follow this version 2-to-3 transfer, followed by the
approved complete-episode terminal PPO objective. The report records the chain
from the parent's policy to the initialized policy, through imitation when
present, and into the first PPO behavior policy. Source seed lineage includes
both the parent's teacher seeds and PPO seeds, plus earlier transfers.
New imitation and PPO schedules must avoid the entire lineage. Resume preserves
it, and evaluation rejects any of those training seeds.

A compatible version 1 or 2 baseline can be lifted to the candidate's version
for frozen evaluation through zero projections. The reported baseline identity
remains the original checkpoint's hash. Local candidates still require explicit
baseline selection when initialization prevents reconstruction from a fresh
random seed. No live model registry or control path changes.

The complete-episode validator checks that version 3 property values exactly
match the recorded displayed IDs and pinned environment profiles. This check
is necessary even when the new projection is still zero, because replayed
logits alone could then fail to detect tampered property inputs.

## Verification

Tests cover all 237 role/price mappings, attack and special-defense costs,
MP-scaled attacks, two-strike attacks, Fate, miracle reuse, padding and inactive
rows for 2–9 players, Dream/Fog counterfactuals, exact transfer with nonzero
history/memory, learned new weights, CLI transfer plus imitation/PPO, unchanged
parent files, exact split-run resume, transitive seed exclusions and tampered
feature/provenance rejection.

The full non-browser suite passes 13,228 tests. Ruff, formatting for changed
Python files, strict typing across 141 source modules, offline lock consistency
and whitespace checks pass.

The first pilot copied the larger-data version 2 checkpoint, used PPO seed
1330000, 32 teacher batches beginning at 1340000, eight games per batch, eight
supervised epochs per batch and 64 PPO batches. Teacher collection completed
252 winner games and four draws. PPO completed 509 winner games and two draws,
with one decision-limit truncation excluded from learning. On seed sets
1370000 and 1380000 the candidate scored 18–46–0 and 19–44–1
(win/loss/draw), compared with its version 2 parent's 22–40–2 and 26–38–0.
Neither evaluation truncated. The new candidate's 37/128 wins regress from
the parent's 48/128; it does not replace that parent as a stronger candidate.

A diagnostic ablation zeroed only the trained property projection, retaining
all other trained parameters. It scored 12–52 and 22–42 on the same seeds,
with no draws or truncations. The resulting 34/128 wins compared with 37/128
for the full projection do not establish a reliable benefit. More training
alone and additional inputs have not yet closed the strength gap.

The version 3 candidate and diagnostic reports are retained under
`runs/full-game-property-candidates/6fceef31-efc9-4d75-aa85-e7113c25c7bc`.
The version 2 parent remains under its existing directory, with its own
matched evaluation reports.

These are local source-aligned features and provisional-game results. They do
not establish official fidelity, competitive strength or live promotion.
