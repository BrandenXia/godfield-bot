# ADR 0115: Native complex weapons and repeated defenses

## Status and scope

2026-10-02, native 0.62.0, `integrated-full-game-development-v13`.
Kernel, observations, plan and metadata advance to 13; commands remain 1.
Combat plan 6 and existing passive/removal/economy/cost plans stay unchanged.
New weapon plan 1 integrates three held models, raising execution coverage
to **224/237** with 13 remaining. This excludes guardians/events and does not
establish full-game readiness. Existing arenas, model checkpoints, API revision,
accounts and live controllers are untouched; no live game was launched.

## Sources and explicit provisional boundary

Catalog/client pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The builder revalidates exact catalog and Bible rows, names, ability strings,
statistics, image paths, prices, weights and all three existing strict parsers.

| Model | Weapon | Kind | Parameter |
| --- | --- | --- | --- |
| 14 | Saw Boom Boom | Two strikes (3) | ATK3 per strike |
| 53 | Evil Broadsword | Same-damage recoil (2) | ATK14 |
| 58 | Magical Stick | Dynamic MP (1) | ATK coefficient 2 |

All are neutral weapons. Profiles `(model,kind,parameter,element)` hash to
`f74d9d6a875d8dac98b66926fe202c20d558254dcb035879b05605673c1baa4d`.
Raw optional profiles validate registration/category, bounds, duplicate IDs
and collisions with other roles. Their omission preserves unsupported status.

Accepted earlier trace audits (ADRs 0035–0037) establish MP consumption,
nonlethal post-defense recoil, lethal-target recoil suppression and separate
defenses for two strikes. Those audits are not new official-game validation
of this joined scheduler. Saved-client `A.jM.dt` (9553–9556) shows dynamic
preview uses current MP minus `A.la` net miracle cost; `A.tw` subsequently
applies boosters in selection order. The `useAttackItems` event debits `A.la`
before displaying the dynamic remainder and zeroing MP (10736–10747).
Thus the broader engine can handle paid-miracle combinations that the earlier
conservative arena deliberately excluded. Official general compound timing
and all unobserved interactions remain unverified.

## Dynamic MP arithmetic and hidden identities

Compose from current own MP minus all net selected miracle costs, including
each adjacent waiver; floor the remainder at zero for an unaffordable preview.
Multiply by the pinned coefficient, then apply additive/doubling/element boosts
in click order. Confirmation still requires net miracle affordability. Cast
validates actual costs, spends **all** actual own MP, consumes each attack card
once and freezes the pending payload. Zero-MP uses are legal ATK0 progress;
a free Fireball attachment can still contribute ATK2.

For example, at MP10, Fireball costs 2 and contributes 2, so Magical Stick plus
Fireball has ATK18, not ATK22. An adjacent waiver restores ATK22, while total
MP spent remains 10. Preview cost remains net miracle affordability; a separate
metadata boundary prevents confusing it with total MP consumption. Hidden
actual unaffordable boosts or unsupported roles fail atomically. Displayed
identity alone determines all precast previews and role observations.

## Recoil and repeated-strike scheduler

After incoming damage and the shared Amulet hook, same-damage applies only
if the final target remains living and positive actual HP loss occurred.
Debit the current living damage source by that loss, clamped to its HP, and
use the same weapon-derived HP-zero hook. Dead-target suppression is preserved
even when another seat keeps a multiplayer match running. Current-source
ownership after reflection/bounce, self-bounce, revival-before-recoil and
their ordering with counters remain explicitly provisional. No blanket
reflection restriction is imposed just to make the evidence-only subset pass.

Saw snapshots the original source, chosen target, composed ATK and element.
Each strike opens a fresh independent defense, including full legal numeric,
special, filter and counter handling. First-strike redirects cannot rewrite
the next strike's original snapshot. Counters resolve depth-first through the
existing reaction scheduler before returning to the original target. Fog is
sampled once at cast, not again for each strike. A dead source or target after
reactions/revival suppresses remaining strikes; a revived one can continue.

Attack composition, costs, miracle-use markers and source-card consumption
occur only once. The single original-owner tick and all replacement gifts
remain deferred until the complete family finishes. This compound timing is
provisional and intentionally not claimed from the earlier arena's immediate
armor refill implementation. First-strike lethality does not hit a dead target
again. A mid-sequence decision limit truncates without extra damage, tick or
invented gift. `resolved_attack_count` counts an original payload once, not
two separate casts. Real ending precedence remains shared behavior.

The bounded reaction queue, second-strike snapshot, costs, recoil, revival,
diagnostics, hands, receipts and RNG all stage with the submitted command batch.
A late invalid/stale/duplicate row leaves every environment unchanged; retry
matches fresh state. Commit remains allocation-free/nonthrowing.

## Observable boundaries and repeatable diagnostic

Public owned read-only `complex_weapon_observations[B,4]` contains active,
displayed-or-revealed original-family kind, parameter and remaining strikes.
Before cast it uses only displayed models; afterward the committed role is
revealed and retained as known family context during counters. It contains no
hidden resource balance or original target field. Existing attack-effect view
code 10 denotes recoil, using displayed identity before cast as well.

Owned read-only `complex_weapon_snapshot[B,8]` is diagnostic-only: dynamic
casts/MP spent, same-damage casts, recoil resolutions/actual HP lost, double
casts, strikes resolved/suppressed. `hp_damage` retains incoming-loss semantics;
new lifetime `recoil_hp_damage` is separate and does not enlarge counter bases.
Episode reset clears these rows and reseeds streams, but retains lifetime
recoil totals. No complete neural adapter or checkpoint migration is claimed.

`simulation full-game-weapon-smoke --batch-size 720 --players 3 --seed 67`
cycles twelve scripted cases: zero/paid/waived dynamic attacks; ordinary,
armored, lethal-target and self-KO recoil; double Forgive, independent armor,
reflection, Saturn counter and first-strike lethal cases. Choices read public
masks/selections; full state is used only for diagnostic fingerprints.

- 720 completed turns, 3,720 commands, exactly 720 original-owner ticks.
- Weapon totals `(180,1200,240,180,1440,300,540,60)`; 1,200 MP paid,
  1,440 recoil HP lost, 540 repeated strikes resolved and 60 suppressed.
- 6,720 incoming HP loss, 1,080 consumed cards, 120 retained miracle uses,
  60 waivers saving 120 MP, 60 reflections and 60 counters.
- Zero other-owner ticks, gifts, truncations or default three-player endings.
  Two-player variants account explicitly for their scripted terminal fixtures.
- Metadata: `22da40113fc6c364e0ecc5c639ea078f056091a78d0a8e7d53f575e67c624b86`.
- Replay: `d8b44766b070f8d1339a5f521e94fef1954c171bf2ebba38a3b9c2610657f20b`.

These are turns, not 720 full matches or training data. All learning, full-game,
official-fidelity and live-promotion flags remain literal false. Reports advance
to utility 4, acquisition/combat 11, chance 8, attack-effect 7, counter 6,
revival 5, removal 4, economy 3 and cost 2; weapon starts at 1. Established
behavior hashes stay unchanged except acquisition, whose added legal models
change masks. Its 41,472 draws still cover all 237 held models, now with 6,063
unsupported draws; sampling does not implement those effects.

## Remaining work and verification

Remaining held models: Exchange, Sell, Buy, Danger, Ascension, Dreaming Hat,
Heaven Herb, Guardian Pot, Thumptear, Fate, Dangerous Mortar, Mirage and Release.
Virtual Discard/Sacrifice, guardians/devils/phenomena, apocalypse, teams,
rewards, complete hidden-family resolution and full learning/reset interfaces
also remain required by ADR 0097. The known provisional cap100/client-display99
gap is unchanged. Trading's command-interface choice is still pending; this
milestone does not redesign commands. The guardian-subset readiness audit is
unchanged because it describes a different environment.

All **4,563 non-browser tests passed**, including 156 new weapon and diagnostic
cases. Coverage includes MP0/1/9/10/99/100, paid and waived miracle composition,
ordered doubling, frozen reflected values, reduced/blocked/nonlethal/lethal
recoil, self-KO and Amulet hooks, independent armor per strike, original-payload
restoration after filters/reflection/counters, suppression on death and
continuation after revival, one-time costs/consumption, deferred receipts,
mid-sequence truncation, Fog across multiple seeds and 2/3/9 players, hidden
roles/costs, late-invalid/stale/duplicate whole-batch rollback and corrected
retry, copied diagnostics/reset, raw omission/malformed profiles and source
copy revalidation. Partial diagnostic batches and strict report relabeling
checks also pass.

Source/test Ruff checks, strict typing across 103 modules, 45 selected Python
format checks, native formatting, offline lock consistency and `git diff --check`
passed. Installed native 0.62.0 exports kernel/observations 13 and command 1.
The known pre-existing ten native Python lint findings documented in ADR 0114
remain unchanged; no passing whole-repository lint claim is made. Browser
fixtures are unchanged, not rerun and excluded from the 4,563 count.

Git writes remain
unavailable under the earlier approval-review limitation; no retry or alternate
Git-write mechanism was used. v8–v13 remain saved locally, uncommitted.
