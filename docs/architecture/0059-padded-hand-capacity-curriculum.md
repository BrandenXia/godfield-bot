# ADR 0059: Padded 18-slot curriculum and checkpoint migration

## Status

Accepted, 2026-09-28. The user selected the padded curriculum and explicit
checkpoint migration instead of a variable-length action architecture redesign.

## Context and evidence boundary

The accepted nine-slot Dream curriculum cannot learn decisions involving larger
hands. Recorded Training states include physical hands of 10–16 visible cards,
but these are not deduplicated and may include retained used-miracle displays.
They establish an observation-capacity gap, not the official inventory limits
or the frequency of independently actionable overflow decisions.

The current public client at <https://godfield.net/main.dart.js> was checked on
2026-09-28. SHA-256 remains
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
Its hand renderer uses two rows of nine positions and removes an empty
placeholder when its display list reaches 18 entries. The initial hand view
creates nine placeholders; consumed artifacts and retained miracles update
that view differently. This verifies a display-layout constraint, not a full
official gift, prayer, inventory, or discard transition algorithm.

## Decision

Add the separate `wide-hand-gift-weighted-dream-resource-hand` curriculum.
It uses schema 11, the same 24 global features, 18 padded hand slots, and
30 actions. Existing curricula, checkpoints, reports, and live bridges remain
unchanged. The supported 196-card catalog and gift weights are unchanged,
while a new ruleset identity and sampling label require a new frozen league.

Each player's initial occupied size is independently uniform over 9–18.
The first nine cards retain the existing role-conditioned weighted deal.
Extra occupied slots draw from the entire weighted supported pool. Remaining
slots are token zero, with false hand and action masks. Consumed cards redraw
in place and miracles remain reusable, exactly as in the existing curriculum.
Occupied size stays fixed until episode reset; this is **capacity stress**,
not simulation of official hand growth or the gift/discard lifecycle.

| Meaning | Nine-slot action | Eighteen-slot action |
| --- | ---: | ---: |
| Wait | 0 | 0 |
| Existing artifacts | 1–9 | 1–9 |
| Extra artifacts | absent | 10–18 |
| Reserved target slots | 10–18 | 19–27 |
| Forgive | 19 | 28 |
| Confirm | 20 | 29 |

Target actions remain masked in the two-seat curriculum. Nine reserved target
slots are retained to match the established action-map convention; this does
not add multiplayer simulation.

Native dimensions default to nine slots and 21 actions. One-time capacity
configuration requires an unstepped gift-weighted batch and must precede any
hand/action view exposure, preventing dangling NumPy/DLPack views on resize.
Invalid ranges fail without mutation, and all resized buffers are allocated
before swapping into the batch. Configuration rewinds RNG and episode IDs.
A fixed 9–9 initial size is available for compatibility tests and consumes no
additional RNG; the public Python factory always uses 9–18.

The heuristic derives dimensions from the batch arrays and has a distinct
wide-hand policy identity. PPO logs and candidate metrics include the count
and fraction of actions selecting slots 10–18. These measurements include
both learner and opponent actor decisions; they are coverage diagnostics,
not strength evidence. Armor diagnostics now use the actual hand width.
The native package version is 0.33.0.

## Checkpoint migration and authority

`models migrate-hand-capacity` accepts only a slot-aware schema-10 checkpoint
with 21 actions, 24 globals, and matching client/vocabulary fingerprints.
It copies the shared artifact scorer, embeddings, encoders, GRU, and value head
unchanged. Non-artifact classifier rows are explicitly remapped. Added
classifier rows 10–18 are zeroed and overwritten at inference by the shared
artifact scorer; there is no newly initialized artifact-selection network.

The result has schema 11 and 30 actions, a new model ID, `initialized` status,
parent identity, source weight digest, and hashed migration provenance.
It inherits no metrics, simulator validation, league readiness, or official
control authority. Schema-11 initialization and loading reject incompatible
action layouts. The feature encoder requires explicit 18-slot/nine-target
dimensions. Existing official API, shadow, and canary admission rules are
not broadened and continue rejecting schema 11.

## Verification

Tests compare seeded nine-card trajectories across both capacities after
action remapping, including true/displayed tokens, globals, masks, and resets.
Migration tests compare every copied weight and verify logits, probabilities,
values, and recurrent memory on padded nine-card states. Extra-slot inference,
padding masks, reserved targets, deterministic wide-hand play and completion,
invalid/repeated/post-step configuration, every exposed resized view,
layout validation, local PPO training, and live rejection are covered.

The rebuilt native package passed all 512 non-browser tests. Ruff lint and
Mypy (55 modules) also passed. A native-only 4,096-environment, 256-step
benchmark collected 1,048,576 transitions and 11,235 completed episodes in
approximately 0.315 seconds (3.33 million transitions/second). That excludes
neural inference and PPO; it is not end-to-end training throughput.

## First local training experiment

The migrated weighted baseline is
`d6a3f9bb-c38f-4263-a689-0c7c9ce617c7`, weights SHA-256
`9aa51c971179915649b3c5629eef5639db600fd0ae954bf5396c96627f7d0dfb`.
It preserves source `f99e35f6-f677-4fa1-a835-4cd586ddb467` unchanged.
The new two-opponent league is `38a29af9-d86f-474a-8ea9-5cad670464ab`,
SHA-256 `48df2b1f2eefab04ce7590e45c21b02ea11dc6b0a3349bc553efbaff01bc7011`.
It contains the wide-hand heuristic at weight 2 and the migrated parent at
weight 1. This initial transfer gate does not replace the earlier six-member
nine-slot robustness league; broader schema-11 opponent diversity remains work.

Training produced `07759a38-203e-45cf-ba7a-c87e2d1dbf18`, weights SHA-256
`1a499018a1a264ac04b79279d42753eef8db8565770da4c9ed98931351447aa8`.
Configuration: seed 40067, 512 environments, 64 rollout steps, 160 updates,
two PPO epochs, 128-environment minibatches, zero teacher updates,
learning rate 0.0001, entropy weight 0.02, CPU. It collected 5,242,880
transitions and 50,862 completed local episodes. Slots 10–18 accounted for
1,122,434 decisions (21.41%) across both actor policies.

Fresh evaluation uses 8,192 paired deals per opponent, both seats, and the
unchanged 512-decision cap. Across three seeds, 98,304 actual games were
evaluated; 98,303 completed. All score lower bounds exceed 50%, but one
incomplete game means the candidate **does not pass all three gates** and
is not accepted as a reliable wide-hand baseline.

| Seed | Heuristic score | Parent score | Incomplete | Gate | Report |
| ---: | ---: | ---: | ---: | --- | --- |
| 41067 | 56.55% | 52.55% | 0 | pass | `eb18973b-17b6-4bd4-b9be-b4d5ed7c4282` |
| 41068 | 57.14% | 53.03% | 1 | fail | `638b1d56-eaf2-4fc1-bf32-945ce722b80d` |
| 41069 | 56.95% | 52.33% | 0 | pass | `1a809b11-4834-45cb-a9c1-3262a632a4a5` |

Registry status stays `candidate`, with no promotion or change to live controls.

A diagnostic-only replay of seed 41068 against the heuristic, retaining the
same 8,192 deals and both seats but allowing up to 2,048 decisions, completes
every game. The sole tail is environment 3442 with candidate seat zero: it
finishes at decision 609 with a candidate loss. This proves that this observed
case is finite, not a native infinite loop. The original 512-decision failure
is retained, the acceptance cap is not relaxed, and no diagnostic result is
counted as a gate pass. Next training work should address this tail and widen
the frozen opponent roster before accepting a reliable schema-11 baseline.

## Remaining fidelity work

Verify official item acquisition, consumed-versus-retained ownership, hand
growth and any overflow removal behavior before implementing that lifecycle.
Eighteen slots are a bounded learning layout, not a claim about the official
maximum owned or selectable artifact count. Guardians, trade, and multiplayer
remain outside this ruleset. Local gate success cannot establish official-bot
strength or authorize live deployment.
