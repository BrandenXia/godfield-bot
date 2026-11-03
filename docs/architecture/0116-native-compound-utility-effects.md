# ADR 0116: Native compound utility effects

## Status and scope

2026-10-03, native 0.63.0, `integrated-full-game-development-v14`.
Kernel, observation, plan and metadata advance to 14; command schema stays 1.
Heaven Herb and Thump-thump Tear raise joined execution coverage to **226/237
held models**, not full-game fidelity. New compound utility plan 1 is distinct
from the unchanged guardian utility plan and combat/passive/economy/cost/weapon
plans. Existing arenas, checkpoints, account credentials, API revision and live
controllers are unchanged. No live game or training job was launched.

## Sources and provisional boundary

Catalog/client pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are pinned sources, not a new Oct 3 freshness check or official trace.
Builders revalidate complete snapshots, exact raw rows, Bible descriptions,
images and existing strict Heaven Herb/stochastic HP parsers. Rehashed catalog
drift is rejected by exact contracts, not merely by a stale outer checksum.

| Model | Source effect | Joined profile |
| --- | --- | --- |
| 198 Heaven Herb | MP+20, Heaven | `(198,6,20,0)` |
| 202 Thump-thump Tear | HP+10 or 10 damage | `(202,7,10,0)` |

Compound profile hash:
`144effaeeaaf78e5c8d60b5f6fcef04ce272ec7b6bf6c89a5a9f3f32817ee0f7`.
The complete 15-row joined utility profile hash becomes
`c89243685670bf98b4fb7d9175be66de1eb94f0e8ac4681c3bb1636614edae6d`.
Neither model is a targeted attack or a manual revival command. The saved
client allows their ordinary sundry leaders; the existing live API parser
already recognizes the Tear as a self utility. ADR 0041 provides the prior
Heaven Herb composition, but its old arena is not evidence for complete joined
official timing.

The sources do **not** specify the Tear's probability. Following the approved
provisional-rule layer, the separate engine uses a labeled uniform binary
50/50 draw. MP gain before infliction, consumption before passive resolution,
revival before the final owner tick, end-of-turn gifts and all unobserved
compound ordering remain explicitly provisional. The local cap100 versus
pinned-client99 gap is retained and declared, not silently treated as official.
All probability/compound verification, full-game training and promotion flags
remain literal false.

## Joined lifecycle

All utility uses stage their actual consumed/retained cards before applying
effects. This lets an effect that reaches zero HP consume an actual owned Sun
Amulet from the remaining hand without staging the same hand twice or erasing
revival's changes. Existing utility outcomes, reusable miracle flags/order,
cost waivers and Dream restoration retain their tested behavior.

Herb gains the actual capped 20 MP, then calls the existing illness primitive:
healthy becomes Heaven, an existing illness worsens one stage, and Heaven
infliction sets HP to zero. The same owned Amulet hook resolves that infliction
edge. A living owner subsequently gets the normal periodic effect and native
worsening ticket. A dead owner is never healed by Heaven's periodic effect;
the existing owner-turn accounting still completes once before ending checks.
Full MP does not mask the card because its illness component remains relevant.

Tear samples once, after actual use, then heals capped HP or loses up to its
current HP. Its heal/damage outcomes do not open enemy target/defense, chance
miss or counter phases. Dark Cloud does not override a self-utility ticket.
A lethal damage outcome uses the same owned Amulet hook, then the original
owner tick. Full HP remains a legal risk-bearing use. Curses/illness, MP, CP
and unrelated inventory remain intact. There is no free revival of an already
dead player, fake Amulet ownership or caller-supplied random ticket.

The new stream is episode illness-seed XOR `0x13198a2e03707344`, using the
existing bounded native SplitMix sampler. It is independent of illness, gifts,
combat, disguise, Fog, bounce, chance, counters and removal. Cancellation and
mere reservation never draw or apply effects. Actual unsupported family or
unaffordable hidden cost still fails as an atomic development error.

Every resource change, illness state, random ticket, consumption, revival,
counter, tick and receipt stages with the entire command batch. Late invalid,
stale or duplicate rows leave all environments unchanged. Corrected retries
match independent fresh state. Commit remains allocation-free/nonthrowing.

## Observable and diagnostic contracts

Policy `utility_selection_observations[B,4]` keeps its layout and uses displayed
kind/value/net cost only. New kinds 6/7 reveal the known displayed family, not
the actual hidden identity or future random outcome. Actual identity resolves
only when confirmation commits. Same-category Dream disguises may switch
between compound and ordinary utility families without consulting hidden
identity for masks or previews.

Owned read-only diagnostic `compound_utility_snapshot[B,10]` records Herb uses,
actual MP gain, capped uses, illness applications and direct infliction loss;
then Tear uses, heal outcomes/actual gain, damage outcomes/actual loss. It is
not a learner feature. Lifetime `utility_hp_damage` totals Herb infliction and
Tear self-damage separately from incoming `hp_damage`, recoil and periodic
illness. General illness-application accounting includes Herb, but attack-effect
diagnostics do not claim its application as an attack.

Owned diagnostic `revival_snapshot` advances from `[B,7]` to `[B,8]`, appending
the direct utility damage cause after the existing attack/infliction/payment/
periodic/worsening causes. Herb uses the existing infliction cause. Episode
reset clears rows/reseeds randomness; lifetime counters remain. Old checkpoints
are not declared compatible with this engine. Raw utility profiles without
these rows leave the effects unavailable; omission of optional reservation
profiles retains the older one-command utility timing.

## Repeatable local checks

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-compound-utility-smoke \
  --batch-size 768 --players 3 --seed 67
```

Twelve scripted cases cover all five initial illness stages, immediate lethal
infliction with/without Amulet, capped/full MP, healthy Tear, full-HP Tear and
low-HP Tear with/without Amulet. Commands read public phases/masks. True state
is used only to verify/fingerprint diagnostic outcomes, not choose hidden actions.

- 768 completed turns, 1,536 commands, exactly 768 original-owner ticks.
- 512 Herb uses, 8,000 actual MP gained, 128 capped uses/infliction HP lost.
- 256 Tear uses: 123 healing/133 damage outcomes, 900 HP gained/727 HP lost.
- 96 actual owned revivals, 864 consumed cards, 855 total direct utility loss.
- Zero incoming attacks, other-owner ticks, gifts or limit truncations.
  Three-player games remain active even after 113 actor deaths; two-player
  variants correctly account for those real endings.
- Metadata: `0caff728673ca91a3c8ce12570ac5d459dea95bf287ba54ef35f0e56c7d8dda9`.
- Replay: `ef0ec464b6e775700a3756e42d595d151cb7faad1001e16c75d479edc16c2107`.

These are scripted turns, not 768 complete games, strength evaluation or a
learning dataset. Reports advance to utility 5, acquisition/combat 12, chance
9, attack-effect 8, counter 7, revival 6, removal 5, economy 4, cost 3 and
weapon 2; compound utility starts at 1. Existing chance/combat/counter/effect
behavior hashes stay unchanged. Diagnostics that fingerprint revival rows
change because of their new width. Acquisition's mask fingerprint also changes:
41,472 draws still cover all 237 held models, now with 5,792 unsupported draws.
All numeric outcome assertions are retained alongside versioned hash pins.

## Remaining full-game work and verification

Eleven held models remain: Exchange, Sell, Buy, Dangerous Pestle, Ascension Bow,
Dreaming Hat, Guardian Pot, String of Fate, Dangerous Mortar, Mirage and Release.
Virtual Discard/Sacrifice, regular guardian/devil/phenomenon lifecycles,
apocalypse, teams/rewards, hidden-family fidelity, complete neural interfaces,
reset/learning probes and the resource-cap gap remain required under ADR 0097.
The next source audit concerns special targeting and its passive interactions.
Trading's action-interface question remains pending. The guardian-subset
readiness audit is unchanged and must not be relabeled as this engine's gate.

New compound utility/source tests: 204 passing; diagnostic/CLI/report tests:
65 passing. Coverage includes MP/HP caps and full-resource legality, five
illness stages, both native stochastic outcomes, Fog/Dream/Flash/Dark Cloud
masks, real ending ownership at 2/3/9 seats, owned revival and receipts, late
hidden-family/hidden-cost/stale/duplicate rollback, corrected retry, cancellation,
reservation truncation, displayed-only previews, raw constructor omissions,
malformed profiles, copied read-only diagnostics/reset, source revalidation and
strict accounting/provisional-scope relabeling rejection.

All **4,834 non-browser tests passed in 77.26 seconds**, including 269 new
compound utility/source/diagnostic cases and two extended profile cases.
Source/test Ruff, strict typing across 105 modules, 49 selected Python format
checks, native formatting, offline lock consistency and `git diff --check`
passed. The installed native package is 0.63.0 and exports kernel/observation
schema 14, command schema 1 and the v14 ruleset identity.
Browser fixtures are unchanged, not rerun and excluded. The existing ten native Python
lint findings documented in ADR 0114 are not changed or represented as green.
Git writes remain unavailable under the earlier approval-review limitation;
no retry or alternate Git-write path is used. v8–v14 are saved locally,
uncommitted.
