# ADR 0091: Pass-only diagnostics and an isolated native discard component

## Decision and diagnosis

Accepted, 2026-09-30. The user approved a separate provisional discard/replacement
curriculum after the investigation found inventory dead ends. This milestone
implements observability and the **caller-driven C++ discard component**, not
its neural rollout/action migration. Existing training and live controls remain
unchanged; all official/full-game/promotion gates remain blocked.

Follow-up: [ADR 0092](0092-discard-arena-training-and-action-migration.md) implements
the accepted separate 48-action adapter and explicit migration. This ADR records
the original component milestone and its historical measurements.

Utility child `d496547f-3fb4-4ca4-80ba-20e51bf89b84` was evaluated raw, unchanged,
against the existing utility greedy opponent at diagnostic seed 1,000,070,
with both learner seats and the same synthetic deal/refill rules. The following
read-only experiments explicitly varied turn and decision bounds together:

| Turn / decision bounds | Child W/L/truncation | Transferred source W/L/truncation | Greedy reference W/L/truncation |
| --- | --- | --- | --- |
| 32 / 128 | 8/6/18 | 9/4/19 | 6/6/20 |
| 64 / 256 | 9/12/11 | 14/7/11 | 9/9/14 |
| 128 / 512 | 11/14/7 | 17/11/4 | 11/11/10 |

Each row contains 32 attempted games per policy. Transfer uses the old
`4d611acb-410e-40dd-8520-0257b5679d79` weights explicitly widened in memory under
ADR 0090, without further training. No saved configuration or weights changed.
Normalized turn/decision inputs also change with these bounds, so neural rows
are **not prefix-equivalent continuations** of shorter games. The greedy
reference ignores those two features. These are development diagnostics, not
official comparisons, strength evidence, or permission to resume with new bounds.

At 128 turns, six of seven child truncations and all ten greedy-reference
truncations witnessed consecutive forced passes by both distinct living actors.
The child made 586 forced passes and the greedy reference 892; neither chose
a voluntary pass. The six child's final MP pairs were `(1,0), (1,2), (0,1),
(1,0), (3,0), (0,1)`. Retained miracles were unaffordable and no other ready
card was legal. In this subset, passing only rotates the owner: no automatic
prayer, trade, discard, guardian event, or resource regeneration changes these
states. A larger horizon cannot repair that dead end. Most shorter truncations
still occur before such a witness; low horizons are a separate limitation.

## Non-mutating play diagnostics

Fresh `GuardianEvaluation` reports contain `play_statistics`:

- active decisions by the six existing phases;
- ready attacks, utility uses, forced passes, and voluntary passes across both
  actors, plus separate learner-only ready counts;
- games witnessing two consecutive distinct actors with only pass legal;
- truncations among those witnessed games.

The witness identity is
`consecutive-distinct-actors-with-pass-only-ready-masks-v1`. Repeated observations
of one actor do not suffice; intervening attack, utility, defense, or voluntary
pass decisions break the consecutive witness. Finished rows do not contribute
decisions. It is a witness under the current incomplete rules, not a general
official-game stalemate detector or a new draw rule.

The tracker uses acting-player policy projections and actions, never hidden
hands. It consumes no randomness and never changes actions, termination,
rewards, masks, recurrent memories, or zero-bootstrap targets. Counts must
account for ready decisions, learner counts cannot exceed totals, and utility
counts agree with effective-use measurements. Historical reports missing this
field stay null, not inferred zero; historical checkpoint loading remains valid.
Newly trained manifests persist the measurements alongside existing evaluations.

## Native component contract

Native package 0.46.0 adds `GuardianDiscardTurnBatch`, kernel/observation schema 1,
ruleset `round-robin-inventory-discard-guardian-turns-provisional-v1`. It inherits
the utility implementation without copying its state. The old `GuardianTurnBatch`
and `GuardianUtilityTurnBatch` gain no public discard methods or altered masks.
The new actor-only projection stays `[B,H,11]` and retains existing role codes.

The Bible's pinned trade restrictions exclude weapons, Sun Amulet (model 208),
and Dangerous Mortar (209), and identify the unimplemented Apocalypse/Sacrifice
boundary. The factory cross-checks these exception identities and the exact
restriction text against the existing pinned catalog/client. Its discard
allowlist contains exactly 63 of the current 102 inventory models: 47 plain
armors, seven utility sundries, and nine supported miracles. Canonical IDs SHA-256:
`08f057a83f01bbe4b7a8f8b585f3c00ce6142f0a09165324e04651415701d80f`.
The C++ constructor independently rejects weapon profiles, 208/209, unsupported
or duplicate allowlist IDs. No new inventory card model is implemented.

Eligibility is an occupied allowed slot of the current living ready owner.
Defense, bounce selection, wrong owners, empty slots, invalid arrays/IDs, and
finished rows reject. `discard_action_masks` is a copied read-only `[B,H]`
projection, separate from attack/utility masks. Every submitted row validates
before any removal or turn/counter mutation; duplicate environments reject.

One self-discard removes exactly that card and provisionally completes one turn,
without a defense response, MP/HP/CP effect, price payment, or compaction. Origin
code 4 distinguishes it from attacks, guardians, and utility use. The lifetime
`discarded_card_count` persists through reset, while existing consumed-use,
miracle-cast, MP-spent, and HP/MP-gained counters **do not** count discards.

There is no native auto-gift. The caller may supply one replacement to the same
empty slot through the existing validated deal API, only in a ready nonterminal
row; finished/truncated rows reject replacement. The recovery regression starts
with armor plus unaffordable Spring, discards armor, explicitly deals an MP item
into that slot, and funds Spring without changing its retained ownership or cost.
This proves the minimal component interaction, not a weighted acquisition loop.

Removal timing, one-turn scheduling, same-slot replacement, and supported-miracle
discard eligibility remain **provisional**. The component does not model a
per-instance performed-miracle flag, Apocalypse/Sacrifice, exchange, buying,
selling, official prayer acquisition, or general overflow/discard scheduling.
Source restriction checks alone do not prove those missing interactions.

## Inspection and training boundary

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-batch-plan --turns --inventory-utilities \
  --inventory-discards --batch-size 512
```

`--inventory-discards` requires both existing component flags. It only constructs
and inspects local metadata, and marks local training, full-game readiness,
official verification, and promotion false. It does not start live games,
train discard actions, or secretly activate discard in existing checkpoints.

The accepted next adapter design appends per-slot discard actions **30–47** to
unchanged actions 0–29, for a separate 48-action curriculum. Hand/public feature
widths can remain unchanged. It needs its own outer observation/action/policy
identities, explicit 30→48 checkpoint migration with original artifact/hash
preservation, a separately labeled deferred replacement plan/RNG stream, legal
visible-only recovery teacher labels, and recorded discard/gift measurements.
Those pieces are still pending; ordinary `guardian-train --resume` remains strict.
No discard-enabled neural candidate has been trained at this milestone.

The existing evaluation command now exposes the diagnostics without modifying
its recorded bounds:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-evaluate \
  --checkpoint checkpoints/guardian-arena/d496547f-3fb4-4ca4-80ba-20e51bf89b84 \
  --games 32 --seed 1000070
```

Its original 8/6/18 result is unchanged, with one mutual pass-only witness,
44 forced passes, 508 attack selections, and 325 utility uses. The old
seven-feature candidate also reproduces 15/10/7 unchanged, with no mutual witness.

## Verification

New tests cover every allowed model, source/profile/metadata tampering, current
owner and phase gates, rejected-last-row atomicity, invalid native arrays,
duplicate rows, empty calls, winner/turn termination, reset counters, explicit
same-slot recovery, and a 512-environment/nine-player removal oracle. Diagnostic
tests cover distinct-actor/consecutive witnesses, interruptions, learner/global
accounting, historical unknowns, reproducibility, and unchanged episode/reward
boundaries. Existing native, model, refill, and training regressions remain required.

All 116 added regressions and the full 1,553-test non-browser suite pass, as do
the two existing local browser tests with Chromium's macOS launch permission.
The native package builds with uv; lock consistency, Ruff, changed-file
formatting, strict mypy across 76 modules, and whitespace checks pass. Both
recorded candidate weight hashes and original evaluation outcomes are unchanged.
