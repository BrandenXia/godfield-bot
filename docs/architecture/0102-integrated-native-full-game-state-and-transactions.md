# ADR 0102: Integrated native full-game state and transactional turns

## Status

2026-10-01. Native 0.50.0 implements the first vertical slice of the **separate
engine approved by the user** in ADR 0101. `FullGameBatch` joins resources,
ordered inventories, documented cures, simple HP/MP utility and disease ticks
under one native episode/decision/turn authority. This is an incomplete
development engine, not full-game readiness or a trainable replacement for the
existing guardian arena. No checkpoint, account, live policy or promotion gate
changes. The pinned API dependency revision remains unchanged.

## Sources and implemented effects

The factory reuses the pinned full inventory plan (237 held models), disease
plan and eight-card utility plan from ADRs 0100, 0098 and 0089. Catalog/client
hashes and all relevant API/Bible profiles must agree. The twelve integrated
effect rows have SHA-256
`834c9fe8bce6185e2bb3729c64813e85ef84daf07c77fd7a8030b32362ccaae1`:

- Four HP sundries, models 191–194, gain 5/10/15/20.
- Three MP sundries, 195–197, gain 5/10/15.
- Smile Shell/Heart Shell, 199/200, perform documented mild/all cures.
- Spring, 235, gains 10 HP for 7 MP; Tone/Song, 237/238, cure mild/all for 2/5 MP.

Gains/costs and mild cure exclusions agree with the pinned sources. Immediate
self targeting, owner-end scheduling, periodic effect before natural worsening,
all-miracle retention/reordering, resource caps, conservative Fog visibility,
pass availability and free-for-all ending order remain **provisional**. The
legacy arena retains its established rules and source/model identities.

Registration of every held model is not battle-effect coverage. Current combat,
trade, guardian and event effects are not executed. A Dream-disguised card can
look like a supported utility while its true effect is unsupported: dispatch
must fail explicitly and atomically, not silently consume it as a successful
no-op. Hidden actual costs may also exceed MP while the display appears
affordable; this remains an explicit development error. Broader Dream execution
and insufficient-hidden-cost semantics must be resolved before learning
admission. The displayed action mask must not use hidden identity to make that
development gap invisible to a future policy.

## Native state and setup

`FullGameBatch` privately owns `CurseDynamicsBatch`, `DreamInventoryBatch`,
MP/CP resources and native episode control/RNG state. Their separate schedulers
are never exposed or called by another driver. The new engine reuses pure
disease/cure/visibility arithmetic and ordered inventory validation/commit
helpers, while owning the joint action transaction. No Python-supplied HP,
status or RNG override can modify an already started episode.

Two through nine free-for-all seats are supported. Capacity 1–512 and two
million total inventory slots are development memory bounds, not an official
hand limit. HP/MP/CP bounds are 0–100; initial HP is positive. Teams/rewards are
not yet implemented and the old duel signed-advantage learner is not reused.

Trusted setup operations are `seed_players` (HP/MP/CP/illness plus curse masks),
`seed_hand` (exact owned rows) and `deal_cards` (explicit gifts with endogenous
Dream sampling). Start seals setup. Reset clears resources/status/inventories,
increments the episode epoch and reopens setup; lifetime diagnostic counters
remain. There is no automatic initial deal, replacement cadence or overflow
resolution: those belong in the future engine, not hidden caller fixes.

## Packed commands and joint commits

Kernel, command and observation schemas are independently named version 1,
ruleset `integrated-full-game-development-v1`. Contiguous `int64[N,6]` commands
are `[environment, episode, decision, actor, phase, choice_id]`. Stable phase
codes follow ADR 0101's strings with newly explicit setup=0; implemented phases
are setup 0, ready 1, terminal 12 and truncated 13. Other codes are reserved,
not implemented mechanics. Ready choice 0 passes; occupied slot+1 chooses an
available displayed utility. Episode/decision/actor/phase are all checked
again natively, independent of optional Python admission.

The native mask checks only the own displayed effect, current visible self
resources/status and displayed affordability. Resolve a valid selected card's
true effect and cost within the trusted engine, keeping the public view free
of true-model leaks. Consume sundries; retain used miracles at the tail. A
full cure that ends Dream restores all remaining fake identities in the same
transaction as costs/status changes. Mild cures retain Dream and Dark Cloud.

Stage every row's resource/status/hand changes, RNG and episode state before
any commit. Validate late rows, duplicate environments, costs, phase tokens and
choices before mutating earlier environments. Commit contains no allocations,
checks or random draws. A rejected row cannot partly spend MP, mark a miracle,
restore a display, consume a card, advance a turn or change later random results.

Each accepted command completes one provisional owner turn: periodic disease
effect, then 5% worsening of surviving affected owners. Utility/cure runs first.
Alive seats advance round-robin; dead seats are skipped. Exactly one surviving
seat wins; all-dead setup is a draw. Terminal endings precede limits. Turn and
decision limits yield separate **truncation** outcomes, never fabricated draws
or wins. Terminal/truncated/setup masks have no policy choices. All loops,
allocations and command/owner batches are bounded.

Each episode owns separate provisional SplitMix gift and illness streams.
Bounded rejection sampling uses at most 16 attempts and fails atomically if
exhausted. Reset deterministically derives new streams from environment, seed
and epoch. Failed gifts/commands do not consume streams; gifting cannot change
illness rolls. This is deterministic local simulation, not official RNG fidelity.

## Observability and adapter boundaries

`episode_snapshot` returns diagnostic/control rows: episode, decision, actor,
phase, completed turns, outcome, winner, accepted commands and last choice.
`diagnostic_players` includes all HP/MP/CP, illness, masks and owner tick counts;
`diagnostic_inventory` includes every actual/fake item. These are not learning
features. Lifetime actions, passes, utility uses, MP spending, gifts, ordinary
consumption, miracle use and restored displays are separately observable.

`player_observations` returns actor-first cyclic `[batch,9,8]` seat, present,
visible, HP/MP/CP, illness and curse mask. Padding has seat -1, all other fields
zero. Fog conservatively hides all other resources/status but not own fields.
`actor_hands` exposes only own instance handles, displayed models and use flags;
`choice_masks` adds no hidden identities. Instance handles are selection
addresses, not numerical policy inputs. These remain an incomplete observation
contract, without complete phases, teams, public history or all legal actions.

All arrays are copied/read-only and outlive mutation/reset/object destruction.
The source-pinned `create_development_full_game_batch` emits strict immutable
metadata. CLI/diagnostic helpers translate public protocol envelopes and compare
native contexts; the training hot loop will use native arrays without per-move
Pydantic or hidden-state copies. Training and promotion registries cannot select
this developmental engine. The current guardian readiness audit still reports
102 usable artifacts and 150 not integrated, without adding separate-engine
effects to its count.

## Offline development probe

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-development-smoke \
  --batch-size 32 --players 3 --seed 67 --max-turns 64
```

The probe seeds fixed own utility/cure hands and disease states and selects the
first available displayed utility, otherwise passing. It never trains, uses
opponent inventory for choices, changes a model or contacts the official game.
Metadata and diagnostic replay hashes make the run reproducible, but diagnostic
state is not a teacher/reward dataset. It is **not a combat/strength test**.

The default probe executes 2,048 commands: 384 utilities, 1,664 passes, 192
ordinary consumptions, 192 retained miracle uses and 672 MP spent. All 32
environments reach the explicit turn limit with zero unfinished environments.
They are 32 truncations, not 32 completed wins/draws. Its metadata SHA-256 is
`4a919125b4ed268bf31d193f83728a22ed2aa0a1fe9a9b0718f08a1b7fd5e6ae`
and diagnostic replay SHA-256
`496d2b699d7135c1f0a2132e09bd2a078f499072c426b5e17a5b6a3a4ce5e8c2`.

## Verification and remaining milestone

Tests cover every effect, cure state/mask and illness/HP boundary; end-turn
Heaven death after a mild cure; exact seeded progression; costs/reuse/compaction;
Fog and true/displayed separation; unavailable/unsupported/hidden-cost errors;
atomic late-row/setup/gift failures; preserved separate RNG streams; sealed
setup and reset epochs; dead-seat skipping; terminal-before-limit precedence;
explicit truncation liveness; copied/typed/empty/bounded arrays; adapter/native
token parity; immutable source metadata and deterministic CLI smoke accounting.

The new CLI test isolates captured logging like existing CLI tests: leaving a
closed runner stream in global loggers initially polluted later training-test
fixtures. This is a test-isolation defect, not a native/gameplay failure; the
focused reproduction and complete suite pass after correction. Verification:
2,265 non-browser tests and both local browser-fixture tests pass; Ruff checks,
changed Python formatting, mypy (86 modules), new native-file formatting,
the offline frozen lock check and whitespace checks also pass. The new engine
has 128 focused tests. No operator checkpoint training or live game was started.

Next is combat selection, target/defense phases and pending-effect resolution
in **this same native engine**, followed by full acquisition, events, economy,
removal/revival, apocalypse, teams and a complete neural adapter. Full-game local
training readiness, official fidelity, checkpoint compatibility, reward/teacher
dataset eligibility and promotion remain false. This slice must not redefine
the goal as a twelve-card utility curriculum.

Follow-up: ADR 0103 adds native 0.51.0's version-2 attack/target/ordinary armor
phases in the same engine. This document records the original version-1 slice
and hashes, not a claim that combat remains absent from the later version.
