# ADR 0112: Native joined Broom and Soap removal

## Status and scope

2026-10-02, native 0.59.0, `integrated-full-game-development-v10`, after the
v9 passive lifecycle. Commands stay schema 1; kernel, observations, plan and
metadata advance to 10. Combat plan remains 6, passive plan 1; removal plan
is 1. The engine now executes **215/237 held models**, leaving 22 unimplemented.
That denominator excludes guardians/events and is not a readiness percentage.

Full-game training, official fidelity and live promotion remain false. Existing
arenas, checkpoints, strict replay admission, API pin, accounts and live
controllers are unchanged. No official game or browser interaction was started.
The v8–v10 work is saved locally but uncommitted while Git approval review is
unavailable; no alternate Git write path is used.

## Source-derived contracts and explicit hypotheses

Pins remain:

- Oct 1 catalog: `df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
- Bible/client: `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
- Removal tuple `((205,1,3),(206,2,2))`:
  `0889134e85ed8c838ffef89cb76502b9957f08d12af51063e3442a5394ba9f84`.

The builder revalidates snapshots and exact Broom/Soap catalog rows, Bible
descriptions/images/elements, and the help restriction excluding performed
miracles from Broom. Model 205 sweeps three artifacts; model 206 washes two
performed miracles. Both are sundries, price 10, gift weight 1, with no use
cost field. **Price is not a CP use charge**; the older ADR 0076 wording is
clarified without changing that primitive's historical identity.

Saved client `A.aN.gkN` permits these sundry leaders. `glk` includes both
removal abilities in enemy targeting; `A.jM.ip` retargets an initially selected
self to another eligible player. The captured self-bound event means the
viewer was the recipient; it does not prove the caster can target itself.
Client `A.aN.e1` applies ordinary special responses only to weapon or miracle
categories; `reflectAnything` is category-independent. Thus these zero-ATK
sundries admit Super Mirror, not ordinary weapon/miracle defenses or numeric
armor. Their `removeItems`/`removeUsedMiracles` event bodies supply victim rows;
the client does not expose player-selected private victim IDs.

The narrow Broom trace from ADR 0074 proves only its explicit three-item
survivor projection. Its missing preceding defense array and redacted source
card do not establish generic sampling or complete replay. Soap still has no
admitted official event. Neither native integration nor synthetic tests change
those evidence boundaries.

| Decision | Local rule | Evidence boundary |
| --- | --- | --- |
| Broom pool | all actual held cards except performed miracles | trade inclusion provisional; no exemption proven |
| Soap pool | actual used category-4 miracles only | source-derived description; generic timing unverified |
| Victims | uniform native sampling without replacement | sampling wholly provisional |
| Short/empty pool | remove minimum of limit and eligible count | wholly provisional; no retry/stall |
| Removed-card gifts | no per-victim replacement | provisional; no immediate redraw inferred |
| Source/defense gifts | existing deferred use receipts | still provisional |

Including held trade cards avoids inventing an exemption absent from the
sources. `official_broom_trade_eligibility_verified` remains false. It must be
validated or revised alongside sampling before official fidelity is claimed.

## Joined implementation

Optional `removal_profiles[N,3]` stores model/kind/maximum. Constructor checks
registered sundry category, kinds 1/2, counts 3/2, nonempty bounds, duplicates
and collisions with other implemented roles. The pinned adapter supplies
exactly the two profiles. Raw batches may omit them; standalone raw removal
can also run without optional attack composition/curse profile families.

The engine internally registers zero-ATK sundry-origin leaders. Public ready,
ordered selection/cancel, living-enemy target and chained-defense commands
remain in existing phases 1–4. Sundry origin is 3; effect codes 8 and 9 carry
Broom/Soap limits. Displayed kind controls previews, while actual identity is
resolved on cast. Source cost is zero, regardless of the catalog price.
Reflections move current source/target without an intermediate owner tick,
removal or gift. Only final response confirmation removes victim cards.

At resolution, inspect the latest staged actual target hand, not a stale
pre-defense copy or fake display. A dedicated stream, initialized from the
illness seed XOR `0x243f6a8885a308d3`, performs partial Fisher-Yates on eligible
slots. Singleton choices need no ticket; empty pools advance no stream. Each
rank draw uses the existing unbiased bounded sampler and 16-attempt cap.
Uniformity here describes the implemented algorithm, not the official server.

Remove the chosen subset once, then preserve every surviving row and its
instance/model/fake/used fields in original order. Removed cards are not
ordinary consumed uses and do not generate replacement receipts. Source and
selected Super Mirror consumption retain existing receipts, deferred until
the original owner's single tick and outcome check. Endings/truncations
suppress them as before. A reflected Broom can remove the original owner's
Amulet before its lethal illness tick; a removed copy cannot trigger revival.

No player-driven removal-selection phase, manual victim ID, source wallet
payment, ghost gift, forced random ticket or already-dead resurrection is
introduced. Limits can stop before effect resolution without claiming a
completed removal, or after a real removal without issuing gifts.

## Observability and atomicity

The existing actor-only `attack_effect_observations` gains codes 8/9. Before
casting it reads displayed identities only. Victim pool cardinality/identities
are not exposed in the source actor's policy projections.

Owned read-only `removal_snapshot[B,8]` is diagnostic-only: Broom/Soap
resolutions, Broom/Soap removed cards, empty resolutions, partial resolutions,
eligible-card total and native bounded rank calls. Empty pools also count as
partial. Rejection-internal random words are not a separate reported count.
`removal_count` counts removed cards; `removal_effect_count` counts effects,
including empty ones. Reset clears episode diagnostics and reseeds the stream,
but lifetime counts remain.

Hands, sampling state, owner ticks/outcomes, consumption, counters and receipts
stage across the entire submitted batch. A later hidden defense error,
malformed command or duplicate environment leaves earlier prepared removals
uncommitted. Corrected retry matches a reference that never attempted the
failed command. Commit retains the allocation-free/nonthrowing boundary.

## Bounded diagnostic and version identities

`simulation full-game-removal-smoke --batch-size 600 --players 3 --seed 67`
cycles Broom/Soap large, singleton and empty eligible pools. Large Broom pools
include a trade card plus protected used miracles. The scripted choices read
public legal masks; full victim hands are fingerprinted only for diagnostics.

Default accounting: 600 turns, 2,400 commands, 700 removed cards, 600 consumed
sundries, 300 Broom and 300 Soap resolutions, 200 empty and 400 partial pools,
1,300 eligible cards and 500 rank draws. Only original owners tick. HP damage,
MP spend, miracle use, gifts and real terminal endings are all zero. These
are mechanics turns, not full matches, learning exports or performance proof.

- Metadata: `137a4f2444588a5cf0523ad89514f52180701dbac7c65875a28f9b547c614cd1`.
- Replay: `551c5a5d0f6a0132c71be267cfca6a06a5a6ee1772ce068ee381770f19dfd179`.

Other report schemas advance to acquisition/combat 8, chance 5, attack-effect
4, counter 3 and revival 2. Previous chance, attack-effect, counter and revival
behavior hashes remain unchanged. Complete-pool acquisition now reports 6,896
unsupported draws among the same 41,472 draws and all 237 observed models.
Its replay hash intentionally changes because Broom/Soap become legal leaders:
`bbce2f785ce433d3e81e9a6d662408c06029813b3dcf4a1f1d1ea7414ee23754`.

## Remaining full-game work

This does not complete training readiness. Economy/trading and CP utilities,
other inventory/passive mechanics, special/area attacks, guardians/events,
teams/rewards, hidden action-family resolution and complete neural interfaces
remain. Implementing all held-card effects alone will not establish official
timing, correct hidden transitions or independent bot strength. Continue the
joined engine and retain explicit provisional/official promotion gates.

## Verification

All 4,081 non-browser tests passed, including 133 new removal and diagnostic
cases. Ruff, strict typing across 97 modules, selected Python formatting,
native formatting, offline frozen dependency checks and `git diff --check`
passed. The unchanged browser fixtures were not rerun in this milestone;
their earlier results are not included in the 4,081 count. No Git write was
retried while approval review remained unavailable.
