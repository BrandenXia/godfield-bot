# ADR 0109: Native counter families and shared payment waterfall

## Status and scope

2026-10-02, native 0.57.0, `integrated-full-game-development-v8`, following
`ac9875c`. The separate authoritative engine gains eight rings, Rainbow
Curtain, Fever Mask and seven ordinary dual-role ATK/DEF weapons. Full-game
readiness is not achieved. Existing arenas, checkpoints, API pin, accounts and
live controllers are unchanged. No live game was started.

The user approved sharing CP → MP → HP payment arithmetic between Venus Ring
and future trading, with credit equal to the requested damage amount up to the
local cap. Credit timing/caps and broader scheduling remain provisional.
No new architecture choice or account authority is inferred from this approval.

## Sources and contracts

Pinned Oct 1 API catalog SHA:
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
Pinned Bible and saved client SHA:
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
No new client/server version or official timing validation is claimed.

Client `ev/ip/kP/dt` establishes ordered defense selection, a filter prefix,
filtered compatibility, exclusivity after that prefix, and cascading undo.
`A.aN.e1/kO` establishes origin-sensitive specials and elemental armor matching.
Prepared counter models retain armor category: treating a ring as a miracle
would incorrectly allow miracle-only blocks/bounces/reflections. Super Mirror
can reflect armor-origin payloads; ordinary weapon/miracle specials cannot.
Client player `bc/dH/eW` arithmetic spills negative CP into MP, then HP, clamping
balances at zero. This arithmetic does not prove server scheduling or credit
timing. Existing local resource caps remain 100, not a newly claimed official cap.

The source builder checks identities, descriptions, numeric fields, abilities,
curse/guardian names, elements/images, gift weights, prices and categories.
Combat plan schema 6 pins all seven profile families to:
`3f03bfeb664a0c37e9fae590ff7dffce4208c6d4a51c50416e0c4b1c9b493b64`.
Defense-only SHA:
`c984180f2027ee4d0899917582509378efd5657e7c94c050274ca7ebaab90044`.
Kernel, observations, plan and metadata advance to schema 8; commands stay 1.

| Defense kind | Models | Payload |
| --- | --- | --- |
| 1: counter ATK | 181 Mars, 184 Saturn | 75% Fire ×damage; Stone ×2damage |
| 2: counter mask | 182 Mercury, 183 Jupiter, 185 Uranus, 186 Pluto | Fog, Dream, Flash, Dark Cloud |
| 3: counter MP | 187 Neptune | self MP +2damage |
| 4: counter CP | 188 Venus | levy damage from current source |
| 5: element filter | 189 Rainbow Curtain | clear incoming element |
| 6: self-illness | 168 Fever Mask | Fire DEF10, then Fever |

Seven additional dual weapons are 11 Saver Rod, 17 Spiked Belt, 20 Plate of
Strike, 24 Elbow Sack, 37 Sword Shield, 49 Legendary Scabbard and 77 Flaming Roll.
There are now 99 leaders, 72 positive numeric defenses and nine zero-DEF
counter/filter profiles, 29 attack additions, 23 specials, 24 chance rows,
20 held attack effects and ten defense effects. Their overlapping roles cover
200 combat models plus twelve utility/cure models: **212/237 held models**.
The denominator excludes other guardian/event mechanics and is not a readiness
percentage. Twenty-five held models still lack integrated effects.

## Provisional joined scheduling

After actual defense, apply incoming damage/effects, then living defender
self-illness in selected order. Ring reactions use actual positive HP removed,
not nominal ATK or predicted damage. A fully absorbed hit creates no reaction.
Lethal defender reactions are enqueued then explicitly suppressed because the
reactor is dead. No posthumous cast or resurrection is invented.

Counters use the current damage source, not the original turn owner. Neptune
targets its own reactor. Each generated payload enters a real phase-4 response,
including zero-ATK curse/resource counters. Rings can combine with compatible
armor. Mars alone needs a percentage ticket: its separate native stream checks
the fixed target's Cloud, skips guaranteed tickets and never rerolls on redirect.
Generated origin=2 means armor; generated attack effect kind 6 means MP and
kind 7 means CP. Held attack-effect kinds remain 1–5.

The private reaction stack resolves defense click order, depth-first. It is
bounded by player count × capacity: every ring is consumed once and all gifts
are deferred. Dead queued sources/targets are skipped with diagnostics. Nested
families preserve the root turn owner. One owner illness tick, outcome check
and replacement-gift release occur when the stack empties. Explicit decision
limits truncate unfinished families truthfully, without adding ticks or gifts.
All these trigger/liveness/order choices remain provisional pending official
trace comparison.

Rainbow Curtain must precede ordinary/counter armor or one exclusive special.
The public preview uses displayed filter identity; actual confirmation uses
actual identity and rejects incompatible hidden order, roles, elements or costs
atomically. Undo rebuilds selections using only displayed identities and drops
an incompatible suffix after filter removal. Filtered attacks are NE for
defense, redirects and Darkness finishing. Flash limits still apply.

Fever Mask reuses the exclusive illness-stage primitive after incoming effects.
Existing illness worsens; Heaven worsening can kill. Unlike the earlier narrow
arena, this explicitly provisional full-game ordering permits incoming illness
plus self-illness rather than silently discarding one. Infliction-event counters
now count every application, not a single boolean per command.

`payment_rules.h` is an allocation-free reusable wallet helper. Venus debits
the target's CP, then MP, then HP, retaining any unpaid remainder diagnostically
in the helper result. Its reactor receives the requested damage amount up to
local CP100 even if the target cannot fully pay, as approved. Same-wallet
transfers do nothing. HP removed by payment is separate from attack damage and
illness-infliction damage. Trading itself is not yet implemented.

## Observability and transactions

Public owned read-only views:

- `defense_order[B,capacity]`: displayed selection order in phase 4 only.
- `counter_observations[B,6]`: active, kind, current source, current target,
  damage basis, hit rate. No pending sibling's hidden identity is exposed.

Diagnostic-only `counter_snapshot[B,12]`: enqueued, casts, resolved, misses,
dead suppressed, counter-ATK HP, MP gained, CP credited, CP-spill HP, filters,
self-illnesses, queued. Lifetime properties remain after epoch reset; reset
clears the episode stack/counters. Ordinary chance observations are inactive
for counters, avoiding a false automatic-enemy targeting flag.

Every queue, RNG, wallet, status, selected order, hand, receipt and counter is
staged before any command batch commits. Queue commits use vector swap and
allocate nothing. A later hidden unsupported response rolls back earlier
staged credit and queue advancement across the entire batch.

## Offline evidence

`simulation full-game-counter-smoke --batch-size 512 --players 3 --seed 67`
executes 512 deliberately scripted families, 64 per ring. Source Cloud forces
Mars hits; all replies forgive. This is not 512 matches or a training dataset.
Results: 3,072 commands, 512 original and counter resolutions, 512 original-owner
ticks, no other ticks, no misses/suppression/leftover queue, 7,040 total attack
HP including 1,920 counter HP, 1,280 MP gained, 640 CP credited, 1,024 consumed
cards, zero real endings. Metadata SHA:
`aeae77648a976fe331e696048f241d243c2f9a7c7064f73d25cac70e0203f953`.
Diagnostic replay SHA:
`41a29f765018a6a367b1aa5d687e08ec91068e80eb1bdc8249194b687e8b17ac`.

Existing chance/effect/fixed-combat/utility replay hashes are unchanged; strict
metadata hashes advance. Complete-pool startup still draws 41,472 cards/all237
models, now 7,150 unsupported draws (25 distinct unsupported effects), with zero
starting actors lacking an implemented choice. It runs zero gameplay commands.
Acquisition/combat reports advance to schema 6, chance 3, attack-effect 2.

Focused tests cover each payload, caps, insufficient funds and lethal spill,
same-wallet self-bounce, elemental armor origin, reflected credits, nested click
order, dead queued targets, filters/undo/hidden atomic errors, Flash, illness
ordering, native Mars probabilities by epoch and Cloud's skipped ticket, bounded
truncation, rollback and owned views. All readiness/promotion fields remain
literal false. Final verification: 3,820 non-browser tests and two local Chromium
fixtures passed (3,822 total); Ruff source/test lint, 20 changed Python file
format checks, mypy across 93 modules, changed C++ formatting and frozen offline
lock verification passed. The compact native type stub retains its existing
formatting style; unrelated repository-wide formatting differences were not
rewritten. A new embedded CLI test initially polluted global logging with its
closed captured stdout; isolating CLI logging like the existing fixtures fixed
the resulting later training-test failures, and the full suite then passed.

## Remaining path

Next integrate held-item removal/revival/redraw and economy into this scheduler,
then the remaining special attacks, multi-target actions, guardian/event phases,
team rules and complete neural action/observation/reward interfaces. The shared
payment rule can be reused by trading without silently enabling it now. Broader
local playability is allowed under labeled provisional rules; official
validation and live promotion stay gated. This milestone does not claim the
user's full-game training objective is complete.
