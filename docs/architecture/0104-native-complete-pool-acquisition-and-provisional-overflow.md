# ADR 0104: Native complete-pool acquisition and provisional automatic overflow

## Status and scope

2026-10-01. Native 0.52.0 adds acquisition to the user-approved **separate**
`FullGameBatch` from ADRs 0102/0103. Inventory, resources, attack/defense, owner
illness ticks, ending/limit checks and receipts are one native transaction;
Python does not supply replacement models or random tickets during play.

The user approved automatic oldest-held eviction at an explicit local 18-card
cap, with its behavior labeled provisional. No player-controlled overflow
phase is invented. Initial deals, universal refill quantities/timing, Prayer
receipts, terminal suppression and ID allocation likewise remain provisional.
All full-game readiness, training admission, official fidelity and live
promotion flags remain false. Old environments, trained checkpoint layouts,
account/session data, live controls and external API revision stay unchanged.

Follow-up: [ADR 0105](0105-native-ordered-attack-composition-and-darkness.md)
adds ordered additions and Darkness correction under native 0.53.0 / development
v4. The v3 probe numbers/hashes in this document are historical. The unchanged
237-model draw stream now reports 131 integrated models and six initial actors
without an implemented choice; current report identity is schema 2.

## Source/evidence boundary

The pinned Oct 1 API catalog has 296 records and SHA-256
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
The Sep 20 Bible is tied to client SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
Source freshness was rechecked Oct 1 in the preceding integration work; this
change uses those saved source pins, not an unversioned live catalog.

All 237 held models are giftable: 107 weapons, 78 armor, 19 sundries, 30 miracles
and three held trade cards. Discard/Sacrifice are virtual controls, excluded
from draws, as are the 57 non-held event models. Relative weights total exactly
500: weapon 181, armor 147, sundry 82, miracle 30 and trade 60. Every artifact's
API `giftRate` agrees with its Bible `Gift Rate: N/500`. Exchange/Sell/Buy are
checked independently against their raw category, image, ability, price 5 and
weight 20. The distribution SHA-256 is
`70905153bedfb92f216afc791132e0bc190f457245e59e4a563256297551b182`.

The factory samples the complete distribution, **not** a renormalized pool
restricted to the 104 currently implemented effects. Including trade or
special cards in inventory does not execute their effects. A single-model raw
native test pool is an isolated scheduling fixture, never complete-game data.
Source/hash/weight/metadata validation prevents relabeling a restricted pool.

The captured Flame fixture `acquisition-v4-32d8eeeb.json` (SHA-256
`c640ac037072e63ea616ae450a2d31c27123747394ba750e592c7fe9fc0f837a`)
shows an explicit gift after **both first use and reuse**. The same miracle
instance survives, is marked used and moves to the held tail. A receipt cannot
therefore be defined solely as replacing consumed ordinary cards. The separate
ordinary trace in ADR 0069 demonstrates consumption and a later gift in
different updates. Those narrow observations motivate the local scheduler but
do not prove a universal server cadence or every multi-card combination.

The saved client's Prayer check rejects a nonused displayed weapon, including
weapons not yet implemented as attack leaders. Its hand renderer has 18
displayed positions but removes an empty placeholder; this does **not** prove
an 18-card ownership maximum or a victim-selection algorithm. An
`overflowItem` event identifies a server-provided victim without establishing
how it was selected. The local cap and algorithm are explicitly approved
provisional choices, not an interpretation of those events as official proof.

## Version and modes

Ruleset `integrated-full-game-development-v3` uses kernel/observation schema 3
and unchanged six-column command schema 1. Metadata/plan schema is 3; old
development metadata cannot resume under this identity. This engine has no
admitted neural checkpoint, so there is no implicit model migration.

The source-pinned factory exposes two exact configurations:

- `manual` (default): no automatic deal/refill/Prayer, physical capacity as
  local limit, overflow rejection; ADR 0103's fixture action behavior remains.
- `all-held-weighted` (opt-in): all 237 weights, nine initial cards per living
  seat, per-use refill, Prayer gifts, local limit 18 and automatic provisional
  oldest-held eviction. Physical padding capacity must be at least 18.

Modes cannot be mixed by editing metadata flags. Raw native configurable
profiles exist for narrowly scoped tests, not training-registry admission.
Storage retains the `B*players*capacity <= 2,000,000` bound; dimensions, profile
counts, weights, unique models, initial size and hand limit validate before use.

## Receipt scheduling, overflow and IDs

Starting an environment stages the whole requested batch. Living hands must
be empty in automatic-deal mode. Each living seat receives nine independent
weighted draws, in ascending seat order. Already-terminal setup receives no
cards or random draws. This independent deal is provisional, not a claim about
official correlated deals or guaranteed card categories.

Every accepted utility/attack use queues one receipt, including every first or
repeat miracle use. Selected ordinary armor queues one per consumed card only
when confirmed. Attack reservation and defense toggles do not draw. Casts pay
and change inventory, but their receipt remains due during defense. After a
completed turn, damage and the original owner's illness tick resolve, actual
ending takes precedence over turn/decision limits, then only living owners in
an ongoing ready phase receive due gifts, in seat order. Dead/terminal/truncated
receipts are cleared and separately counted as suppressed. Mid-cast decision
truncation also clears due receipts without sampling or reporting a completed
attack. Those timing/order/suppression rules are provisional.

Prayer is ready choice 0 only without a nonused displayed weapon, and queues
one gift even if per-use refill is disabled in a raw test configuration.
Manual choice 0 remains the old fixture pass with no receipt. An unsupported
weapon can thus legitimately leave **no implemented action** in this unfinished
engine; it is not silently replaced by a fake legal pass or recorded as a
successfully completed full game.

At the approved cap, a new gift evicts the **first item in the current ordered
hand** before appending. This is not lowest instance ID or original-acquisition
timestamp; reuse already moves a retained miracle to the tail. Overflow is
automatic and separately counted, not card consumption and not a new policy
choice. Reject-mode overflow fails the entire staged command batch instead.
Physical padding above 18 does not change the opt-in local ownership cap.

The new model-only SplitMix stream samples cumulative positive weights with
binary search and at most 16 rejection attempts. Separate model, disguise,
illness and Fog-target streams isolate their draws. Dream samples same-category
displays from the full registered pool; source-pinned model identities remain
private to effect resolution/diagnostics. Full cures restore existing displays
before a new undisguised receipt. Every stream stages with the episode, so
late-row errors cannot partly sample or advance any stream.

Fresh instance IDs increase monotonically per environment/epoch, starting
above trusted setup IDs and stopping before exceeding `2^53-1`. This is **not**
the observed server ID-reuse algorithm. Reset clears IDs, hands, due/received/
evicted counters and streams while retaining lifetime counters. Setup seed/deal
failure cannot advance the automatic ID counter. Commit is allocation-free
and has no random draws or validation.

## Diagnostics and reproducible probe

`acquisition_snapshot[B,players,3]` is a copied/read-only diagnostic: queued
gifts, episode automatic receipts and episode automatic evictions. It is not
policy input. Lifetime counters distinguish automatic gifts, suppressed gifts,
overflow and Prayer; total gift count includes explicit setup deals too.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-acquisition-smoke \
  --batch-size 512 --players 9 --seed 67
```

The probe starts native full-pool inventories and reports all 237 model weights
and sampled counts, including zero counts for small runs. Its default samples
41,472 cards, observes all 237 models, records 16,964 draws without an integrated
effect and 12 of 512 initial actors without an implemented choice. It issues
**zero gameplay commands and completes zero games**. No reward/teacher/strength
or full-game learning evidence is claimed.

Default metadata SHA-256:
`d3e9d0e23b83d7b8922c52b356fb4cb278e01512f2d1e308292d35e88fc8c1f9`;
diagnostic replay SHA-256:
`822adf9d6574278726852b54b4f973e10246866c5ca71cc7cc38276f71ccfbc1`.
Manual combat/utility replay arrays remain unchanged from ADR 0103; metadata
hashes necessarily change with the v3 identity and explicit acquisition plan.
Current manual combat metadata SHA-256 is
`1bab41e97f0c1cf329ad11e30c33e8deaa1a0f7135be533d7061f2c499bb6073`;
manual utility metadata SHA-256 is
`09f03bd252ef65a0b5d94c98bf543f7e353b688ca7f50b1daefbc2fb18144cf7`.

## Verification and remaining work

The 347 added acquisition/probe tests exercise each of the 237 giftable models,
independent weighted-draw arithmetic, source forgeries, all utility effects,
first/repeat Flame gifts, defense receipts, owner ticks, dead/terminal/limit
suppression, Prayer exclusions, current-order eviction, physical padding,
batch/RNG/ID rollback, Dream/cure behavior, stream isolation, reset/counter
lifetimes, snapshots, factory/metadata boundaries and CLI/report admission.
These complement the existing 345 joined state/utility/combat tests.

The full non-browser suite passes 2,829 tests; both local headless browser
fixtures pass outside the macOS IPC sandbox, for 2,831 total. The initial full
suite exposed a test-isolation mistake in the new CLI fixture: it left global
logging attached to a closed captured output stream. The fixture now follows
the existing CLI tests' logging isolation; no production logger or learner was
changed to hide that failure. Ruff, all changed Python formatting, mypy across
90 modules, native new-file formatting, frozen offline lock consistency and
whitespace checks pass. The legacy native golden replay remains unchanged.

Next: integrate special attack composition and defense workflows into this
same engine, then remaining utilities/targets, economy, events, guardians,
removal/revival, apocalypse, teams/rewards and complete native neural action
and observation interfaces. Full-game liveness, replay and learning acceptance
must pass before local training readiness; official evidence remains a
separate requirement before live promotion. No subset pool or startup probe
can satisfy either gate by renaming its output.
