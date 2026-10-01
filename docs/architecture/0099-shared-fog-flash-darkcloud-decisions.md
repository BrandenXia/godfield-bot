# ADR 0099: Shared native Fog, Flash, and Dark Cloud decisions

## Status and boundary

Accepted shared-component progress, 2026-10-01. Continue the full-game objective
without assuming approval for the broader state/action architecture still
pending in ADR 0097. This step adds status decisions on the **same native state**
as ADR 0098 and extracts common legacy calculations; it does not add another
turn engine, train a checkpoint, or change live control.

Native 0.48.0 preserves the disease kernel schema/ruleset and adds separate
decision schema 1, ruleset
`caller-driven-fog-flash-darkcloud-decisions-provisional-v1`. Existing diagnostic
snapshots remain diagnostic. The new status view is not a complete policy
observation and is not checkpoint-compatible with any existing neural arena.

## Source and remaining hypotheses

The pinned Bible and the current [official public help](https://godfield.net/i18n/en.json),
checked on 2026-10-01 for ADR 0098, identify Fog's hidden surroundings and random
enemy targeting, Flash's single-artifact defense restriction, and Dark Cloud's
certain receipt of percentage attacks. Their generic descriptions do not define
every visibility, team, selection, random-stream, or event-order interaction.

The new Fog view conservatively hides other seats' HP, illness, and curse masks.
Hiding all of those fields is explicitly **provisional**, not a claim that every
field is hidden by the official UI in every situation. Fog recipient selection
uses a caller-supplied eligible-enemy rank ticket, with hypothetical uniform
rank sampling if the caller supplies uniform tickets. The kernel does not infer
teams, generate tickets, or establish official random-stream fidelity.

The legacy duel keeps its established narrower Fog feature projection, broader
legacy cure behavior, action masks, random streams, and checkpoint identities.
Refactoring its resource-hiding, Flash limit, and chance-hit calculations to pure
shared helpers must preserve those behaviors exactly, not silently apply new
provisional observation rules to an old policy.

## Native caller interface

Four read-only methods on `CurseDynamicsBatch` use its current authoritative
HP/illness/mask state. None alters counters, transitions, resources, or statuses.
Each validates complete inputs before returning a copied, read-only array:

- `status_observations(environments, actors)` returns `[rows, 9, 6]` with seat,
  present, visible, HP, illness, and mask columns. Seats are actor-first cyclic
  with an explicit absolute-seat map. Padding has seat -1 and all other fields
  zero. A dead seat remains present; its visible zero HP is distinct from an
  unknown Fog row with `visible=0`. Own status remains visible under Fog.
- `defense_card_limits(environments, players, ordinary_limits)` returns zero for
  dead defenders, one under Flash, otherwise the caller's limit in [1, 512].
  This is a capacity calculation, not item legality, selection or confirmation.
- `hit_decisions(environments, targets, hit_rates, hit_tickets)` returns hit and
  randomness-required columns. Dark Cloud is checked on the actual target, not
  the attacker. Rates are [1, 100], tickets [0, 99]. Ordinary guaranteed attacks
  and clouded recipients do not require a hit ticket; other hits compare ticket
  against rate. Supplying a ticket is not an internal RNG draw.
- `enemy_targets(environments, actors, intended_targets, eligible_enemies,
  selection_tickets)` accepts a binary `[rows, 9]` caller enemy mask. Self, dead,
  and padded candidates are invalid; intended targets must be eligible. Fog
  replaces the intended target with the ticket's rank in ascending eligible
  seats. Without Fog the intended target is preserved. Empty candidate sets are
  rejected; the composing engine must handle victory/no-enemy flow first.

The status view excludes inventory, MP/CP, owner tick counts, transitions, random
tickets, and lifetime counters. Hidden HP changes, illness, curse flags, and
liveness cannot affect Fog-masked rows. An explicit visibility channel avoids
teaching that unknown resources are actually zero. Future full policy projections
must separately cover MP/CP, inventories, teams, phases, costs, histories, and
the complete source-appropriate visibility boundary.

Defense/hit/recipient calculations are **trusted scheduler outputs**, not policy
features. Feeding their internal outcomes or tickets into a learner would cross
that boundary; they must not be concatenated to the status view. Different
actors and duplicate read-only query rows are supported, unlike duplicate
mutating player rows. Status queries are limited to 222,222 rows and other
decision queries to 1,000,000, checked before allocation/processing. Returned
arrays survive subsequent mutation and destruction of the native object.

`godfield_bot.curse_decisions.create_provisional_curse_decision_batch` reuses the
source-pinned disease factory and one native state, checks the additional native
schema/ruleset/methods, and emits immutable, strict decision metadata. Field
layouts, visibility policy, exclusions, and false compatibility/readiness claims
cannot be relabeled in serialized metadata. All local-training eligibility,
full-game readiness, complete-policy projection, complete-team rules, Dream
disguise, official fidelity, and promotion flags remain false.

## Verification

Eighty-two new tests cover:

- Actor rotation, padding, every relevant status mask, live/dead views and own
  visibility at 2/3/9 seats; one hundred hidden-state perturbations per seat
  configuration; no tick/transition/counter leakage; curing Fog restores the
  view without mutating retained observations.
- Every curse mask at defense limits 1/18/512; all hundred tickets at percentage
  rates 1/25/50/99/100; correct target ownership; documented mild/full cure
  effects on Dark Cloud and RNG requirements.
- Every nonempty enemy subset, each intended target and each rank ticket at
  2/3/9 seats, with and without Fog; caller-mask restrictions; invalid self/dead/
  padded/nonbinary candidates, targets/tickets, dimensions and types.
- Atomic rejection/nonmutation, empty and duplicate queries, bounded allocation,
  copied read-only output lifetime, source-pinned metadata, drift rejection and
  old-native rejection.

The unchanged legacy golden run still completes 241 games, visits all illness
stages and matches SHA-256
`1437712753d61312efff7716bb91ae34ba30c05e18ca8980f636f1c25a40bcc6`.
This verifies compatibility, not full-game fidelity or improved playing strength.

A synthetic read-only stress probe, seed 100067, used 4,096 environments and
nine seats across 128 query rounds: 524,288 status-view rows plus 1,572,864 scalar
decision rows, approximately 0.037 seconds including NumPy tickets and copies.
Native state remains unchanged. This is **query throughput**, not full-game
steps, episodes, training throughput, or a win-rate result.

The complete suite passes 1,970 non-browser tests and two local browser fixtures.
Ruff, changed-file and native-component formatting, strict typing over 83 source
modules, offline lock consistency, and whitespace checks pass.

The full-game audit links these components but still marks the curse workflow
partial. It does not count its cure/status models as integrated guardian-arena
inventory actions or loosen any readiness gate. The next necessary integration
work remains the versioned full-game state/action design in ADR 0097, followed
by real inventory/turn/visibility/defense/recipient interactions and Dream.
