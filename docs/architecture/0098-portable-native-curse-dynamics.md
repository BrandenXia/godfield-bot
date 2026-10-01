# ADR 0098: Portable native disease progression and documented cures

## Status and scope

Accepted component work, 2026-10-01. The user requested continued progress toward
full-game training readiness. The broader architecture choice in ADR 0097 still
awaits user direction. This step extracts shared status math and adds a bounded
2–9-player caller interface usable by either design; it does **not** start a new
full-game environment or change any checkpoint/action/observation contract.

Native package 0.47.0 adds `CurseDynamicsBatch`, schema 1, with ruleset
`caller-driven-documented-curse-dynamics-provisional-v1`. Pure, allocation-free
functions in `curse_rules.h` can be composed directly with an arena's resources
without copying a second resource state. The existing legacy attack/defense
engine now uses the same illness functions and retains its own random stream,
turn scheduler, terminal handling, and cure behavior.

## Primary sources and provisional boundary

The current public [official help](https://godfield.net/i18n/en.json) was read on
2026-10-01. Its `texts/curseDescriptions`, disease-reference notes, and cure
ability descriptions agree with the pinned Bible's curse section and four cure
cards. The help establishes the illness chain, periodic amounts, five-percent
worsening chance, and worsening on receipt of another disease. The source-pinned
[official client](https://godfield.net/main.dart.js) represents one disease plus
independent non-disease curses; its public representation is consistent with
these separate fields, not an illness bitmask.

The component separates exclusive None/Cold/Fever/Hell/Heaven stages from the
existing guardian mask: Fog=1, Dream=2, Flash=4, Dark Cloud=8. Periodic HP changes
are 0, -1, -2, -5, +5 respectively, with a 100-HP cap. Healthy recipients get
the incoming illness; already ill recipients worsen one stage regardless of the
incoming stage. Worsening Heaven sets HP to zero and leaves its diagnostic stage
at Heaven, not an invented fifth living illness. Death from periodic damage
prevents subsequent worsening or healing.

The caller completes the ill owner's turn and supplies a ticket in [0, 99];
tickets below five worsen a surviving ill player. Applying the periodic effect
**before** worsening, the exact scheduling boundary, and cure-before-tick order
remain explicitly provisional. Public descriptions are not complete event-order
evidence, and a ticket map does not establish the official random stream.

Mild cures follow the documented scope: Cold/Fever and Fog/Flash only. Dream,
Dark Cloud, Hell, and Heaven remain; full cures clear every represented status.
This differs intentionally from the legacy curriculum's broader non-disease
cure implementation. ADR 0051's mild-Dream rule and the legacy mild-Dark-Cloud
behavior are not silently copied into the new documented component or corrected
in place under an old ruleset/checkpoint identity.

## Caller contract and observability

`load_players` validates and synchronizes HP/stage/mask while preserving each
player's completed tick count. This is a **trusted caller operation**, not a
policy action or an authorized revival mechanic. Loading zero HP does not count
as an illness-caused death. `apply_illnesses`, `apply_curses`, `cure_players`, and
`finish_turns` reject dead players. A cure must have an effect. Non-disease
infliction is idempotent and never worsens an illness.

Every operation checks lengths, dimensions, player uniqueness, values and all
later rows before mutating any state or counter. Different players in the same
environment may appear in one batch; duplicate environment/player pairs may
not. `finish_turns` also requires the expected per-owner tick token, preventing
an accidental duplicate tick from dealing damage twice. Explicit environment
reset clears per-game state/ticks but preserves lifetime counters. Episode IDs
and stale messages across resets remain the composing scheduler's responsibility.

Copied, read-only diagnostic snapshots expose HP, illness stage, curse mask, and
completed ticks. Transition snapshots record operation, previous HP/stage/mask,
net HP delta, and newly-dead status. Lifetime counters distinguish disease
applications, non-disease applications, cures, ticks, and illness-caused deaths.
There is no inventory in either snapshot. These are **not policy observations**:
Fog may hide other players' resources from an acting policy, whereas this
trusted-caller state remains authoritative. Any future policy projection must
implement that visibility boundary separately; the metadata explicitly marks
policy projection unimplemented.

`src/godfield_bot/curse_dynamics.py` configures the optional native dependency
offline, pins both source fingerprints, validates the full Bible curse-help
section and exact API/Bible cure models, and rejects serialized profile/field
drift. The plan fingerprints the illness definitions, mask mapping, and four
cure profiles with SHA-256
`916cfa809ee2e607c8cedafed77604a5d98c82eaf66949936fae517a7b8df38b`.
The profiles preserve Smile Shell/Heart Shell consumability and Tone/Song's
documented 2/5 MP costs **as metadata**, not implemented item use or MP charging.

The component has no item legality, action masks, costs, turn scheduler,
automatic randomness, winner calculation, Fog targeting, Flash defense limit,
Dark Cloud hit adjustment, or Dream disguise/redraw effect. Those workflows
still require integration. Local-training eligibility, full-game readiness,
official fidelity, and promotion remain false.

## Validation and remaining integration

Ninety-one new tests cover all five stages, six HP boundaries, all hundred
progression tickets at 2/3/9 seats; every incoming/existing illness pairing;
all 80 illness/mask combinations under both cure scopes; cure-before-tick;
death/no-healing rules; idempotent masks; atomic later-row rejection; stale ticks;
dimensions/input types; empty batches; read-only snapshots; selective resets;
source, metadata and optional-dependency failures. Independent seeded Python
references match 200 mixed operations for each of 2/3/9 seats.

A 32-environment, 1,024-decision legacy fingerprint was captured on 0.46.0 before
refactoring. On 0.47.0 it still completes exactly 241 games, visits every illness
stage, and matches state/action SHA-256
`1437712753d61312efff7716bb91ae34ba30c05e18ca8980f636f1c25a40bcc6`.
This checks compatibility, not official correctness of legacy rules.

A separate bounded stress probe initialized 4,096 environments with nine seats
and synthetic statuses, seed 99067. Across 128 owner selections it resolved
450,642 owner ticks and 12,947 illness deaths in approximately 0.039 seconds,
including copied snapshots and NumPy ticket generation. This is status-kernel
throughput, **not** full-game rollout or training throughput.

The full-game audit now links the portable component but retains the disease
workflow as partial, all four cures as unintegrated in the guardian arena, and
all existing inclusion counts/readiness flags. No model, roster, retained
reference, game account, live policy or game session changes.

Final verification passes 1,888 non-browser tests plus two local browser fixture
tests, Ruff and changed-file formatting, strict typing across 82 source modules,
native component formatting, offline lock consistency, and whitespace checks.

The next integration work is still the explicitly versioned full-state/action
environment choice in ADR 0097, followed by actual inventory/turn/status and
effect-order interaction tests. A standalone tested kernel cannot satisfy that
acceptance boundary.
