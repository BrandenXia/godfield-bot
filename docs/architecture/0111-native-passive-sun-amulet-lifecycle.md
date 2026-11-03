# ADR 0111: Native passive Sun Amulet lifecycle

## Status and scope

2026-10-02, native 0.58.0, `integrated-full-game-development-v9`. This joins
one passive ownership effect into the separate authoritative engine. Commands
remain schema 1; native kernel, observations, plan and metadata advance to 9.
Combat plan remains 6, passive plan is 1. Existing arenas, checkpoints, API
pin, accounts and live controls are unchanged. No live game was started.

Full-game training readiness, official fidelity and live promotion remain false.
Held-model integration rises from 212 to **213/237**, leaving 24 held models
without effects. That denominator excludes guardian/event mechanics and is
not a readiness percentage. Economy, removal, other passives, area attacks,
guardians/events, teams and complete neural interfaces still require work.

The preceding v8 changes and this milestone are saved locally but uncommitted:
Git staging was not executed when approval review reported its usage limit.
No alternate Git write path is used.

## Source-pinned contract

Pins remain the Oct 1 API catalog and Sep 20 Bible/client from ADR 0109:

- Catalog: `df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
- Bible/client: `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
- Passive tuple `(208,10)` SHA:
  `108e08cd030d7b3bbde6f6ec4b1bce640aef17ee2a1bc7086c6fe5623b1e70ba`.

The builder revalidates both snapshots, checks the exact Sun Amulet API row
and Bible description/image/element contract, then pins model 208 with HP+10.
The saved client excludes `revive` sundries from ordinary ready leaders.
Therefore the implementation is **passive**, not a manual target action to
resurrect an already eliminated seat. ADR 0110 records the source audit.
There is no new official Sun event or server timing evidence.

## Provisional joined ordering

| HP-zero source | Native hook point |
| --- | --- |
| Ordinary or Darkness damage | after HP debit/finish, before incoming effects |
| Illness infliction | after a lethal worsening of existing Heaven |
| CP payment | after shared CP→MP→HP debit and stated capped Venus credit |
| Owner periodic illness | after its periodic loss, before its native worsening ticket |
| Owner Heaven worsening | after the native worsening ticket, before outcome checks |

On each **positive-to-zero transition**, inspect the latest staged owner's
hand using actual identities, including any attack/defense consumption already
applied. Consume the first real owned Amulet; preserve all surviving rows and
their order; set HP to 10. Do not cure illness/curses, reset MP/CP, restore the
consumed attack, or alter used-miracle flags. A disguised real Amulet triggers;
another card merely displayed as Amulet does not.

One copy is consumed per edge, with no recursive check or retry loop. Distinct
edges can occur in one command: an attack may cause revival, followed by lethal
Heaven infliction causing a second revival. Setting HP to zero during setup,
dealing a copy to a dead seat, or executing another player's idle turn never
revives that dead seat.

Revival happens before incoming effects, self-illness, ring liveness, pending
sibling suppression and winner checks. It can therefore keep a reactor or
queued target alive, or allow a revived self-bounced absorption source to heal.
The original owner still ticks exactly once when the family finishes. A revived
owner retains its illness, and may die again later. Real outcomes still precede
explicit turn/decision limits.

When provisional per-use refill is enabled, consumption adds one deferred
receipt using the same scheduling as other consumed cards. No gifts appear
between counter/redirect hops. Endings and truncations suppress due receipts.
**Copy order, retained state, all compound timing and receipt rules are
provisional**, not source-proven server behavior. The shared payment arithmetic
itself retains the user-approved source-pinned CP→MP→HP waterfall.

## Interface and atomicity

Native `passive_profiles[N,2]` rejects empty/duplicate/out-of-range profiles,
non-sundries and conflicting implemented roles. The pinned Python factory
supplies `(208,10)`; raw batches can omit the map and retain old death behavior.
Full-game checkpoints are still explicitly incompatible with the old arenas.

Owned read-only `passive_observations[B,H,2]` exposes displayed kind/HP for the
current actor in interactive phases only. It never exposes actual trigger
eligibility under fake identities or Fog, other players' hands, or a hidden
queue. `revival_snapshot[B,7]` exposes diagnostic count/HP and the five cause
counts, not policy inputs. Epoch reset clears those counters, preserving
lifetime `revival_count` and `revived_hp`.

Revival hands, resources, statuses, queue, native tickets, consumption and due
receipts remain in a staged mutation. A failing later environment commits
nothing from earlier successful environments. Removing the hidden invalid
selection and retrying yields the same complete state as a fresh reference
that never submitted the failing batch. Allocation happens during preparation;
the existing commit stays allocation-free and nonthrowing.

## Bounded diagnostic

`simulation full-game-revival-smoke --batch-size 500 --players 3 --seed 67`
cycles attack, infliction, payment, periodic illness and native Heaven-worsening
cases. It scripts public legal choices and uses hidden snapshots only for
diagnostics. No caller-provided RNG, forced illness ticket, teacher action,
reward dataset or full-match success is produced.

Default result: 500 original-owner turns/ticks, 1,600 commands, 405 revivals,
4,050 HP granted, 705 consumed cards, 100 retained miracle uses, 100 Venus
counter resolutions, no other-owner ticks, queued leftovers or real endings.
Cause counts are `(100,100,100,100,5)`; the last five are ordinary native
5-percent worsening tickets, not an invented deterministic event.

- Metadata SHA:
  `c2efe99a4e75730f447a5e1cbbec22c9e7853a7891e717d7263c7137006b2091`.
- Complete diagnostic replay SHA:
  `1ab889d262ec43896612926066420872ed8120bdafb64bcb090c8b3e126f0610`.

Existing attack-effect, chance, counter and complete-pool acquisition replay
hashes remain unchanged; metadata/report versions intentionally change. The
default acquisition diagnostic now reports 7,067 unsupported-effect draws
(83 Sun draws now count as integrated), with the same 41,472 draws and all
237 models observed. This is inventory sampling, not gameplay.

## Verification

The native extension rebuild and frozen offline uv synchronization succeed;
`uv lock --check --offline` resolves 66 packages without changing upstream
pins. Ruff, strict mypy (95 source modules), changed-file formatting, native
formatting and Git whitespace checks pass.

The complete **non-browser suite passes 3,948 tests**. The two unchanged local
Chromium fixtures passed during v8 verification; they were not rerun for v9
while approval review was unavailable. No new browser or official-game
validation is claimed.

The 128 new revival/probe cases include all death sources, first-copy consumption,
retained state, separate same-command deaths, independent native worsening
RNG across reset epochs, fake identities, byte-identical public projections
despite different actual ownership, no dead-setup resurrection, counter and
reflection/self-bounce interactions, deferred/suppressed gifts, limits versus
real outcomes, late hidden-failure rollback and equivalent retry. Strict
metadata/report tests reject changed schema IDs, unverified semantics, bad
accounting or readiness/promotion claims. Old raw behavior without passive
profiles and existing arena/checkpoint suites remain green.

## Next integration

Join Broom/Soap into the authoritative target-and-response scheduler. Keep
victim sampling native and explicitly provisional; do not expose arbitrary
private victim instance IDs as learner choices. Preserve used-miracle flags,
survivor order, staged RNG and separate removal counters. The narrow captured
Broom trace is not evidence for arbitrary victim sampling, and Soap still has
no admitted official event.
