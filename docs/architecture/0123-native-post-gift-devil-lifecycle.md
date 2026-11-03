# ADR 0123: Joined post-gift devils and bounded automatic receipt families

## Scope and compatibility

2026-10-13. Native0.70.0 is `integrated-full-game-development-v21`, kernel,
observation, plan and metadata21, shared-family4 and command1. This adds the
five devil events to the separate incomplete full-game engine. Held abilities
stay233/237; standard guardians stay40/42. Other12 event artifacts, trading,
String of Fate, complete Apocalypse/Sacrifice, teams/rewards, hidden resolution,
cap99 migration and complete neural interfaces/learning probes remain missing.
ADR0097's full acceptance objective remains active. All local-training,
full-game-readiness, official-fidelity and live-promotion gates remain false.
No training, checkpoint, live game, account or credential is changed.

Earth/Moon special producers include trading/ordinary generated artifact actions;
their implementation is not narrowed to harmless gifts or a plainATK10 attack.
The pending trading-interface choice remains separate from this independent work.

## Frozen source evidence

Catalog/client SHA pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are the saved Oct1 catalog/Sep20 Bible and client, not a new Oct13 snapshot.
The Bible explicitly places devils after Apocalypse,25% per artifact receipt.
Small/Medium/Large Devil appearance percentages7/5/3 and damage10/20/30,
Trickster5% stealing2 artifacts or performed miracles, and Charity5% granting
HP/MP/CP+10 establish the complete five-event numeric source scope.
The saved client handles `gift`, `useDevilItem`, `dealDamage`, `removeSomething`
and resource boosts separately. It does not establish server RNG, victim sampling,
exact compound timing or an official default Apocalypse threshold.

Pinned native rows `(240,7,1,10),(241,5,1,20),(242,3,1,30),(243,5,2,2),(244,5,3,10)`
have SHA `a6b1927315e0a08937c1d46f995fbe825b9866d9b063440b5bd88097313eeef4`.
The full Bible asset/path/detail/element table has SHA
`a52921e10bc30710479184bc3746bce0c873e5817ce3b0d7e3da1c04f42762c3`.
Complete API/Bible identities, notes, numbers, fields and pins are revalidated;
strict plans/reports cannot claim official fidelity or promotion.

## Explicit opt-in Apocalypse, not an invented official default

`apocalypse_after_turns=0` disables the experiment and preserves old acquisition.
A positive explicit threshold, bounded1..1e9, requires gift/devil profiles.
After that many completed original turns, the episode's public Apocalypse flag
becomes true exactly once. Initial deals never trigger devils. No default official
threshold, GF interpretation, server timing or complete Apocalypse is claimed.
Existing ending and pending-command limits suppress new receipt waves first.
Virtual Discard becomes unavailable after this experimental flag: the engine
does not silently reuse pre-Apocalypse removal as missing Sacrifice.

In enabled experiments every deferred receipt enters automatic family5, retaining
the original turn owner, `turn_ticked` and one guardian-wave flag until complete.
Tasks resolve ascending owner order then receipt order provisionally. Each owned
gift arrives before its independent0..99 ticket selects one of the disjoint
7/5/3/5/5 intervals or no devil. Event models never become held inventory cards.
The default complete-pool weights still total500 and exclude57 event artifacts.

Direct devil loss has no armor/special response or fabricated attack origin.
It uses actual owned Sun first, separate revival cause7, then guardian departure
and final-death Ascension. Bow responses/counters finish depth-first before
sibling receipts, with no extra owner tick or recursive guardian activation.
Devil HP loss is separate from incoming attack/utility damage counters.

Trickster's actual eligible pool is every nonmiracle or performed miracle,
including Sun/Mortar/weapons: Discard's protected exclusions are not borrowed.
An unused miracle remains protected even when disguised. Up to2 native uniform
partial-Fisher–Yates draws select victims; survivor IDs/models/fakes/flags/order
are stable, with no use/performance/payment or replacement for stolen cards.
Charity uniformly chooses HP/MP/CP, including already-capped choices, and credits
up to the provisional100 cap without resurrecting dead queued recipients.
Recipient/short-pool/sampling/gift timing/caps all remain provisional.

## Iterative bounded scheduler and atomic diagnostics

Dedicated illness-seed XOR streams are appearance `0x24a19947b3916cf7`, theft
`0x0801f2e2858efc16` and Charity `0x636920d871574e69`. Existing streams are
unchanged. Sun during a receipt can owe another receipt; new waves wait until
the current queue drains, then recheck real endings/limits. Waves run iteratively,
not by recursively growing finish/resume frames. At most2*players*capacity
receipt events are processed per original turn; exceeding that finite limit
throws atomically. This is an incomplete-development safety boundary, not an
official cap or successful gameplay truncation. Raw forced100% devil/always-Sun
fixtures exercise it at18/three-player and512/nine-player configurations.

Public `apocalypse_observations[B,3]` is enabled/active/configured threshold;
setup/finished rows are zero. Fog does not hide this global state. No future
gift/appearance/model/victim/resource-ticket or private queue becomes a feature.
Readonly `devil_snapshot[B,18]` records entries, checks, appearances, damage
events/HP loss, thefts/eligible/removed, charities/gains, draws, queued/resolved/
suppressed receipts and waves. `devil_model_counts[B,5]` has240..244 histograms.
Lifetime appearance/loss/theft counts survive reset; per-episode streams, state,
counts, queues and flag reset. Returned previous arrays remain owned/read-only.
Revival diagnostics add one separate devil column, becoming `[B,9]`.

The complete command batch stages gifts, native RNG, theft, resources, Sun/Bow,
guardian departure, queues and counters before nonthrowing commit. Late stale
rows or automatic bound failures leave the full earlier state and lifetimes
unchanged; corrected retries and reset epochs reproduce a reference.

## Bounded complete-pool first-turn probe

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-devil-smoke \
  --batch-size 4096 --players 3 --seed 67
```

Nine full500-weight gifts per seat precede the explicit threshold1. The driver
uses only public masks, own displayed cards/costs/resources, the first affordable
turn and forgiven responses. True diagnostics only check/fingerprint outcomes,
never choose hidden victims/events. It does not repeat matches or learn.

Default4096/three-seat/67:110,592 initial gifts,4,098 postturn receipts,999 devil
appearances with model counts272/202/109/192/224,10,010 devil HP loss,384 stolen
cards,690MP/910CP Charity gains,14,620 commands and exactly4,096 original ticks.
Two dead queued receipts suppress normally. No pending family, extra tick or
limit exit. Metadata SHA
`5d502b0d49669fbea63acae1152a981a9f0cf226633793e295ec26caaccd63a9`, replay
`d605580123e1794796e64160e297afd735fcdb76d9b0fb19dd94457b3fd205c4`.

Actual4096/nine-seat/67 CLI:331,776 initial gifts,4,100 postturn receipts,1,000
appearances272/202/109/193/224,10,010 devil loss,386 theft,14,626 commands,
4,096 ticks and no pending/limit/extra tick. Metadata
`37d12bed724d25c285d7455ae68787fc52ab5902f502f4b7e92fdb19f072e628`, replay
`8e17f382e97b09ceba8b04443b6fceb2b12d76bc4c6505d60516f6a213c8ff53`.
These are4,096 first turns, not full episodes/rewards/strength/official evidence.

All16 old bounded probes reproduce their v20 behavioral fingerprints when the
new zero revival column is excluded. Nine probes that fingerprint that tensor
have storage-only replay changes; metadata and report identities are explicitly
versioned. Native family/schema contracts are checked independently, and forged
schema tests still fail closed. The current checkpoint architecture is unchanged.

## Verification boundary

Focused tests cover all5 effects, independent ticket/victim/resource/departure
oracles, delayed/disabled/initial-deal behavior, Sun→new receipt→Bow, separate
tick/damage accounting, hidden-safe views, stable theft, late-row rollback,
reset/owned views, raw dependencies/bounds, source drift and strict report/CLI
gates. The two new modules pass176 focused tests. The final non-browser suite
passes **6,936 tests in125.37 seconds** against the rebuilt iterative native
engine. Ruff passes `src`/`tests`, strict mypy passes118 source modules, and all75
selected full-game Python/CLI files pass formatting. Native clang-format,
offline lock consistency and Git diff checks pass. Installed identities are
native0.70.0/kernel21/observation21/command1/family4, matching the source adapter.
No browser fixture, live game or training job is run. Git remains read-only;
changes are saved locally, not committed, with no alternate Git write path.
