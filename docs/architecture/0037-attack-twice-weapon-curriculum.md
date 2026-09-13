# ADR 0037: Evidenced attack-twice weapon curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0036

## Context

The accepted Bible defines Saw Boom Boom as neutral `ATK3` with `Attack
twice`; the API catalog names the ability `attackTwice`. The official Training
recorder contains 17 related transitions across seven runs. Several traces
establish that this is a repeated response sequence rather than one ATK6
damage event.

Run `990f2455-5e25-42e5-b05e-769e8faf7131` records two consecutive Forgive
responses, each removing 3 HP, without advancing the field between them. In
run `3ab95364-2601-487f-b4b2-7e70cd123af7`, the defender independently selected
and confirmed DEF1 for each strike; each response removed 2 HP, and the two
armor instances were consumed separately. Run
`fd582bd6-6720-4259-890e-2efd6489e318` combines those cases: DEF1 reduced the
first loss to 2, then Forgive accepted the second loss of 3. Bot-originated
attacks in runs `bccb02eb-39ce-4cfb-be02-e02e03b13fb9` and
`d91ef006-0358-46d1-9502-8a8b01f58ba2` each removed 6 HP from the official
opponent before the next field.

No recorded trace combines Saw Boom Boom with an attack booster, Super Mirror,
or Reflection Sword.

## Decision

Add `attack-twice-weapon-resource-hand` as a distinct native ruleset layered on
`same-damage-weapon-resource-hand`. It adds Saw Boom Boom as a consumable
neutral weapon and produces a 156-card catalog while retaining observation
schema v6, 14 global inputs, and the 21-action sequential head.

Confirmation snapshots ATK3 and opens defense with two strikes remaining.
Resolving the first nonlethal strike keeps the same defender active, redraws
any consumed armor normally, does not advance the turn counter, and opens a
fresh defense selection for the second ATK3 strike. Resolving the second strike
advances the turn once. Lethal damage terminates immediately, so a second
strike cannot be applied to a defeated player.

Schema v6's final pending-effect feature remains backward compatible and now
also exposes repeated-strike progress. Saw Boom Boom reports `0.5` before the
first response and `0.25` before the second; absorption remains `+1`,
same-damage remains `-1`, and ordinary attacks remain `0`. The native batch
also exposes the exact remaining-strike count for diagnostics.

Because composition is not yet observed, attack boosters are masked after Saw
Boom Boom is selected, and reflection cards are masked during either response.
Numeric and compatible elemental defenses remain independently available for
both strikes.

The heuristic values Saw Boom Boom at its evidenced total of 6 damage. The
native transition, rather than the teacher, retains the two independent defense
decisions.

## Consequences

Native self-play can now learn hand depletion and redraw across a repeated
defense sequence instead of approximating the card as ATK6. Existing schema-v6
checkpoints remain shape compatible, while the distinct ruleset, catalog, and
sampling fingerprints prevent its trajectories from mixing with earlier
curricula.

This ruleset remains non-promotable. Attack-twice composition with boosters or
reflection, random targeting, status effects, Ascension, miracle reflection and
blocking, bounce, counterattacks, guardians, phenomena, and the CP purchase
economy remain separate evidence-gated increments.

## Validation

- The full Python and native-integrated suite passes with 346 tests. New tests
  cover the strict Bible parser, catalog construction, separate DEF1 and
  Forgive responses, remaining-strike observations, first-strike lethal
  termination, and composition masks.
- Ruff, mypy across 49 source files, native formatting, the uv lock check, and
  the repository diff check pass.
- A 4,096,000-transition native benchmark completed at approximately 8.34
  million transitions per second on the development machine.
- A CPU teacher-warm-start plus PPO smoke run produced schema-v3 candidate
  `8429cb62-5c7f-4a90-a1f3-8bad2bdee9a0`. Its training context records
  observation schema v6, 21 actions, 14 global features, the 156-card catalog,
  and heuristic policy `evidenced-attack-twice-weapon-resource-combo-v1`.
