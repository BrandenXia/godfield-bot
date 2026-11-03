# ADR 0125: Versioned numeric trading choices and joined Exchange

## Decision and scope

2026-10-15. The human approved retaining six-column commands and using
versioned phase-specific numeric choices for trading. Native0.72.0 implements
the first dependency, Exchange3, in the separate full-game development engine.
Ruleset/kernel/observation/plan/metadata are23; command1/shared-family5 remain.
Held-route coverage is235/237. This is not237/237 or full-game readiness.
Sell4/Buy5, Earth285/Moon286, complete Apocalypse/Sacrifice, teams/rewards,
hidden cross-role resolution, cap99 migration and complete neural action,
observation/checkpoint/episode/learning interfaces and gates remain required.
All readiness/fidelity/promotion flags stay false. Older arenas, checkpoints,
live controls, accounts and credentials are unchanged; no live game or training
job is started.

## Source audit, not a new freshness or fidelity claim

Frozen API/client SHA pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The saved client `A.fo`/`A.fp`11864–11917 uses four ±10/1 controls on
each MP/CP axis. Each transfers with HP one-for-one, clips to current resources
and headroom, and caps at99. `A.jQ`9587–9665 submits **final** MP/CP, not
deltas. The received Exchange event11080–11097 sets HP/MP/CP together.

Exact API identities3/4/5 have category trade, respective exchange/sell/buy
abilities, price5 and giftRate20. There are no corresponding Bible catalog
entries; the source adapter does not manufacture them. All237 held prices
are frozen as `(model,trade-kind,raw-price)`; absent price is0, Treasure's
credit value is not a price. The table sums1795 and SHA is
`2a748a50cc390df76da833a02d09a34bf857b5eb9d6b17a4c76b72e3a93e6679`.
This table is a future Sell/Buy dependency, not an implemented transfer engine.

The client additionally requires Sell's leader plus exactly one owned item;
performed miracles are excluded. Sell events remove the offered card from
the displayed attack and award it to the receiver. Buy/setBought/canNotBuy
have a separate revealed-item/purchase workflow; the pending source makes
the purchase choice, not the ordinary defender. These require their own
ownership/reflection/refusal/overflow audit and joined tests. They are not
approximated here as numeric damage or silently omitted from unsupported
confusion draws.

The installed `godfield` API's `GameState.awaiting_player_id` independently
routes a nonempty `buyingItemModelId` to the attack's `player_id`. Saved
acquisition fixtures `acquisition-v4-1d87e285.json` and
`acquisition-v4-32d8eeeb.json` contain `sell` and `buy`/`setBought` event
order respectively, but the shown trade item/owner/value payloads are redacted.
Those traces do not establish prices, actual transferred ownership, offers,
refusal or general reflection rules. This audit does not promote them into
complete trading differential evidence.

## Numeric phase contract

Trade-choice schema1 is separate from command schema1. Phase6 (`trade-response`)
mode1 denotes an Exchange preview. Choice0 confirms;1/2/3/4 move MP by
+10/+1/-1/-10;5/6/7/8 do the same for CP;9 cancels. Increments clip rather
than demanding ten funds/headroom; zero-change edits are unavailable. HP pays
positive increments and receives negative ones. All balances stay0..100 and
their sum is conserved. Retaining the existing provisional100 cap is explicit:
this is not pinned-client99 parity or a silent whole-engine resource migration.
The card's price5 is not charged as a use fee or MP cost.

Reservation and edits touch only episode preview fields. The native authoritative
wallet/card, death hooks, turn tick and gifts are unchanged until confirmation.
Confirm validates the actual owned Exchange, consumes it once, commits all
three balances and finishes the original turn once through the existing
illness/guardian/receipt scheduler. Cancel returns ready with no consumption,
tick, payment, gift or actual-role lookup. Both remain legal after64 amount
edits. Global decision limits still terminate repeated reservations/cancels;
an unconfirmed preview at truncation does not become an artifact use.

Choice-mask width stays capacity+10. Phase-specific labels resolve overlap
between numeric choices and card slots; phase/context/epoch/decision validation
remains mandatory. Preserving six integers is **not** proof of neural
action/observation/checkpoint compatibility. Raw constructor omission keeps
old unsupported fixtures; the source factory appends `[3]` only.

## Joined death, control and atomic state

Preview HP0 never triggers early death. Committed positive→zero HP provisionally
uses actual owned Sun before final death/Bow reactions and ending checks, with
the same single original-owner tick. Cause8 appends an Exchange revival column;
the first nine historical revival columns retain their indices. Conversion
is not incoming attack damage, payment-waterfall loss or positive damage for
guardian departure. Final death still clears confusion/guardian ownership.
This compound timing is unverified and explicitly provisional.

Forced-ready confusion resolves an actual Exchange in one native command,
uniformly sampling a final conserved0..100 wallet from at most10,201 feasible
MP/CP pairs. Bounded enumeration avoids retry/policy edit loops. The staged
stream is illness-seed XOR `0xb8e1afed6a267e96`. Sampling/zero-HP timing remain
provisional. The pre-step policy mask stays false; rewards/value targets are
not zeroed. Normal phase6 commands retain voluntary policy weight1.

Hidden actual trades share the same displayed reservation/preview/masks.
A mismatched actual role rejects at confirmation without partial commit.
Broader hidden cross-role execution is still missing, not falsely counted as
verified. All wallet, hand/Sun/Bow, statuses, queue, gifts, RNG and counters
stage before whole-batch commit. Late bad rows cannot advance earlier rows.

Policy `trade_observations[B,7]`: active,mode,previewHP,previewMP,previewCP,
edit-count,reserved-displayed-slot. It is zero outside phase6. Readonly owned
`trade_snapshot[B,10]`: reservations,edits,cancels,commits,netHP→MP,netMP→HP,
netHP→CP,netCP→HP,forced-commits,allocation-draws. Stats use net committed
axis changes, not gross intermediate preview clicks. Reset clears new state;
previously returned arrays remain owned/unchanged. No future identity/RNG,
other player's hidden wallet or item is exposed.

## Scripted probe and regression boundary

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-exchange-smoke \
  --batch-size 512 --players 3 --seed 67
```

Eight ordinary amount scenarios and two zero-HP Sun/Bow scenarios use controlled
hands and Dark Cloud recipients. It reports512 scripted owner ticks,
1,638 commands,51 Sun revivals,102 Bow shots/3,060 incoming damage and614
consumed cards. Trade totals are
`512,512,0,512,674,561,561,306,0,0`. No family remains active, other owner
ticks or limit exits occur. This is not a full match, strength result,
reward/teacher dataset or learning gate. Metadata SHA
`480d3e83eddbc7dcb1548f502389b04f8319cfbb56cee976074f1afbc04b73ac`, replay
`69a818309aedb9157adcdb28559d23bbc7ae19c87a6f2200a6c7b310fdcea4b4`.

The actual4096/nine-seat CLI run also completes every original turn:15,560
commands,409 Sun revivals,3,272 Bow shots/98,160 incoming damage and4,914
consumed cards. No reactions, extra ticks or limit exits remain. Metadata SHA
`269104104f156a016cbd268e92fb6ce3fcc044190f91510cae25a280d4b49f29`, replay
`a4714d32bbb75747e86e48d9d989ab7cb897712dc648e2a5f978e7e9f8087c3b`.

The150 new focused cases cover all eight clipped controls, conservation,
sampled full-wallet reachability within64 edits, cancellation/limits,
late-row rollback, private displayed roles, Sun/Bow, forced allocation/action
independent oracles, owned/reset views, source/price/schema/gate validation,
partial-batch report algebra and CLI parity.

Complete-pool startup still draws41,472 cards/all237 models. Unsupported
held draws are3398 (Sell1697+Buy1701), reduced exactly by1630 Exchange draws.
There are193 new public Exchange startup choices. Masking only these reproduces
the v22 startup replay
`4b7d7142e6b00709be85ee3212aece1db5fdf2ea72001222e0745bd9da00d859`;
no draw distribution is filtered or renamed. The complete-pool devil first-turn
probe now genuinely chooses Exchange when legal:14,077 commands,998 devil
appearances,4,096 ticks and1,643 theft-eligible cards. New one-use trades change
some hands/receipts; unchanged historical counts are not fabricated. Revival
diagnostic hashes also explicitly change where the new tenth column is included.
Report/source schemas and golden records are versioned rather than relabeled.

Final verification against installed native0.72.0: **7,324 non-browser tests
pass in140.87 seconds**. Ruff passes `src`/`tests`; strict mypy passes122 source
modules; all83 selected full-game/CLI Python files pass formatting. Native
clang-format checks pass for the engine header and all three implementation
files. Offline lock consistency, installed23/23/command1/trade1/family5
identities and Git diff checks pass. No browser fixture, live game, account,
checkpoint or learning job is changed. Git is read-only in this environment;
changes are saved locally, not committed. The full-game goal remains active.
