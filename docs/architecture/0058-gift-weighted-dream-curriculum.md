# ADR 0058: Gift-weighted Dream sampling curriculum

## Status

Accepted, 2026-09-28.

## Context

The native Dream curriculum contains 196 supported artifacts, but samples
individual cards uniformly. The official Bible assigns unequal gift rates:
Hatchet has numerator 6, while Silver Club has numerator 1, both over 500.
Uniform sampling changes how often policies encounter common and rare cards.
This is a plausible transfer gap, not proof that it causes the online losses.

The public client at <https://godfield.net/main.dart.js> was fetched again on
2026-09-28. Its SHA-256 remains
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`, matching
the accepted Bible snapshot. The client loads artifact definitions from
<https://godfield.net/i18n/en.json>, stores `giftRate` on each artifact, and
displays it over the sum of gift numerators. We separately refetched those
definitions and compared all raw item records with the accepted API catalog.
All 296 records are unchanged; the gift numerator sum is 500. The freshly
downloaded `en.json` bytes have SHA-256
`bb1b433ba6d336765589aec940cca0bac8b7c0bdcee33969c207a17365509188`.

## Decision

Add `gift-weighted-dream-resource-hand`, leaving `dream-resource-hand` and all
earlier curricula unchanged. The new mode retains schema 10, 24 globals, 21
actions, nine slots, two seats, and the same supported mechanics. It is usable
through league creation, training, paired evaluation, and native benchmarking.

Gift numerators come exclusively from accepted Bible records. Every supported
card must have one well-formed positive integer rate with denominator 500.
Missing, repeated, malformed, zero, or incompatible rates fail closed. Both
numerator and denominator enter the rule-catalog digest. A distinct ruleset ID
and sampling label prevent a uniform roster from being reused accidentally.

The native sampler precomputes integer cumulative distributions for all card
families. Initial role counts stay 2 weapons, 1 booster, 2 armor, 1 utility,
1 attack miracle, 1 chance miracle, and 1 effect miracle. Within each initial
role, family selection and card selection are weighted by gift numerators.
Ordinary redraws use the weighted supported pool. Mandatory weapon replacement
for attack liveness uses the weighted weapon pool. Dream false identities keep
their existing uniform disguise sampling; receipt rates do not alter disguise
mechanics.

Native weight configuration is one-time, only on an unstepped Dream batch.
It validates exact catalog coverage, unique tokens, and positive weights before
changing any state. Configuration rewinds the initial RNG and episode IDs,
then redeals so the constructor's discarded uniform hand cannot affect seeded
weighted trajectories. The Python factory configures the batch before returning
its immutable distribution metadata. Native package version becomes 0.32.0.

## Verification

Tests cover distribution identity, unchanged legacy catalog digest, malformed
Bible rates, native input validation and atomic failure, one-time configuration,
deterministic seeded games and resets, legal actions and completed episodes,
and the observed 6:1 initial Hatchet/Silver Club ratio versus the legacy 1:1
ratio. A separate consumed-card test measures all 196 supported redraw
frequencies against the normalized gift weights, without initial role
conditioning or weapon-guard substitution. Accepted Bible rates are also
checked against the raw official API catalog. A small real PPO league run verifies sampler provenance and rejects a
uniform simulator against the weighted league contract.

A 4,096-environment, 256-step native benchmark collected 1,048,576 transitions
and 13,899 completed episodes in approximately 0.18 seconds on this machine
(5.78 million transitions/second). This excludes inference and PPO and is not
an end-to-end training throughput claim.

## First weighted training experiment

Freeze league `2504a6db-49b7-4482-b807-f438c13895df`, SHA-256
`eb91aeac6cc9a8edf00707b4d92b6394c855fb33dac307716e9cb3c7998a0b06`.
It contains the heuristic at weight 2 and five frozen models at weight 1:
`63de1747`, `dd5bde4f`, `3dfe4a94`, `088ef7a5`, and `df08842c`. The exact
identities and checkpoint digests are in the persisted roster. The parent is
`63de1747-f43f-4ef1-ae99-a1cd72dd3ec1`. The weighted rule-catalog digest is
`d29ec8edde5a270ab4738b06820e56f8c09dc91c22b42208e14fe10334d03eb6`.

Training produced `f99e35f6-f677-4fa1-a835-4cd586ddb467`, weights SHA-256
`0db1fcf2a5f5ad2af01d49d764443300879e5e8cda7107195fc881be30779b50`.
It used seed 38067, 512 environments, 64 rollout steps, 160 updates, two PPO
epochs, 128-environment minibatches, no teacher updates, learning rate 0.0001,
entropy weight 0.02, and CPU. It collected 5,242,880 transitions and 65,656
completed local episodes. Every frozen model supplied over 9,000 completed
episodes and 369,000 decisions; the heuristic supplied 18,933 episodes and
753,849 decisions.

The unchanged candidate passed the strict per-opponent gate on three independent
8,192-pair deal seeds. Each report contains 98,304 actual games across six
opponents; all 294,912 games completed. Every individual paired lower bound
exceeded 50%. The parent improvement is modest; it is not evidence of a large
strategic gain or of official-game performance.

| Seed | Parent score | Parent lower bound | Heuristic score | Report |
| ---: | ---: | ---: | ---: | --- |
| 39067 | 50.65% | 50.05% | 57.56% | `f2bdc5e8-1be3-47dd-87a1-e2b632a7b93a` |
| 39068 | 50.73% | 50.12% | 57.98% | `4d808d7f-f87c-4abf-837f-2e4624b505ed` |
| 39069 | 50.68% | 50.09% | 58.03% | `7dff3f4f-ca7a-4aef-ac4c-b3c35c21b6ca` |

Scores against older models ranged from 51.56–51.95% (`dd5bde4f`),
52.28–52.97% (`3dfe4a94`), 54.88–55.20% (`088ef7a5`), and 56.73–57.68%
(`df08842c`). The candidate is the weighted-mode local baseline. The original
uniform-mode baseline and all existing reports remain intact. Registry status
is still `candidate`, with no promotion or change to official controls.

Verification finished with 497 non-browser tests passing, Ruff lint passing, Mypy
passing across all 55 modules, and the rebuilt native package installed through
uv. The two browser-control tests were excluded because this milestone changes
no browser code.
The repository-wide formatter check reports existing style drift; unrelated
files were not reformatted. Formatting checks pass for the sampler factory,
new tests, and changed native sources.

## Limitations

This is supported-pool, role-conditioned gift weighting, not a replica of the
official deal algorithm. Unsupported artifacts are excluded and remaining
weights are renormalized. Initial role stratification and the forced weapon
liveness rule remain curriculum conveniences. The nine-slot hand cannot model
official hand overflow, and trade, guardians, multiplayer, and other rules
remain absent. No official authority, browser controls, model promotion, or
existing accepted checkpoint is changed. Gains must be measured with fresh
paired deals under this distribution and validated separately on official play.
