# ADR 0121: Integrated native multi-card Discard

This records historical v19 verification. Current v20 adds guardian lifecycle
under [ADR 0122](0122-native-guardian-post-turn-lifecycle.md); historical source
and replay evidence below is not relabeled into current metadata identities.

## Scope and architecture

2026-10-13. Continue the full-game objective while the separate trading amount
interface choice is pending. Implement the actual multi-card pre-Apocalypse
Discard selection path, not the old one-card caller-driven guardian primitive.
The previously accepted discard curriculum and provisional-layer permissions
remain applicable. The separate engine advances to native0.68.0,
`integrated-full-game-development-v19`, kernel/observation/plan/metadata19;
command1 and shared attack-family2 remain. Existing arenas, checkpoints and
live/account controls are unchanged. No learning or live game is run.

This implements a virtual control/removal workflow, not the abilities of the
six missing held cards. Execution coverage stays **231/237 held abilities**;
discarding an unsupported effect is not evidence that its effect executes.
Full-game learning/readiness, official fidelity and promotion remain false.

## Source contract and boundaries

Retain the Oct1 catalog and Sep20 Bible/client pins:
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
This is a frozen-source implementation, not an Oct13 freshness assertion.

Bible trade restrictions are exactly:

- Weapons, Sun Amulet, and Dangerous Mortar can not be discarded.
- After the Apocalypse, Discard is replaced into Sacrifice.

Raw virtual model1 is `discard/trade/discard/Discard`, without price/gift fields.
Sun208 has `revive` and Mortar209 `attractDanger`; neither is a manual leader
or an eligible discard. The saved client's `A.jM.ev` around9499 permits
multiple selections after Discard/Sacrifice, excluding weapons and those
passive abilities. `A.jQ` around9603 requires at least one selected held item
in addition to the virtual control. The restriction doesn't exclude performed
miracles, unlike the adjacent Sell selection and explicit Buy/Sell Bible note.

The source builder derives **128** eligible IDs from all237 held profiles.
Its canonical ID-list SHA is
`2df3973944e31c672893fa041ba24e4cc31ed64a146efcf790dfe1e519332b80`.
This includes trade and event-producing held cards even before their abilities
execute. No virtual/event model is accidentally inserted into the hand list.
Snapshots, exact control/protected identities, restrictions and canonical
eligibility are revalidated; altered/unchecked sources fail closed.

The client's use/removal rendering (`useAttackItems` around10740,
inventory handler `ee` around12692–12729) distinguishes Discard from
ordinary receipt-producing use. Selected discarded rows are removed without
the ordinary gift placeholder path. Local no-victim-replacement scheduling
remains explicitly provisional, not claimed server timing. Listed prices
are not discard payments. This full-game path doesn't silently inherit the
older guardian curriculum's one-card replacement hypothesis.

Apocalypse/GF progression and Sacrifice effects are **not implemented** in this
milestone. The engine cannot be declared complete until the virtual control
switch, Apocalypse events and sacrifice effects are connected and verified.

## Native command and selection flow

Reuse the six-column command tokens and existing phase7 (removal-selection).
Choice-mask width remains capacity+10. Choice `capacity+1` means reserve
Discard in ready phase and cancel in phase7; its meaning is phase-specific,
so it doesn't collide with phase3's target-seat controls. A ready reservation
is offered only when an own displayed eligible card exists. The virtual
control isn't dealt, owned, consumed or a policy-supplied true model ID.

In phase7, slot+1 toggles an eligible own displayed row and records click
order. Undo removes just that row; other independently eligible selections
remain. Choice0 confirms only a nonempty selection. Cancel is always available
and clears the selection/reservation without advancing the owner turn, altering
resources, removing cards or creating a gift. Every accepted command still
advances its decision token, so a stale repeat rejects atomically.

`FULL_GAME_MAX_DISCARD_ACTIONS=64` bounds toggles, separately from attack and
defense counters. At that bound, nonempty confirm and cancel remain; if empty,
only cancel remains. The global decision limit independently truncates endless
reserve/cancel or toggle behavior. This local escape policy is provisional.

Confirmation validates every actual selected model first. Displayed legal
masks never inspect hidden protected identities; a falsely displayed eligible
Sun/Mortar rejects the entire batch at confirmation under the existing
development-error policy. No partial earlier removal/tick/RNG advancement is
committed. Undo/cancel gives an explicit recovery path. Broader official hidden
resolution still needs validation before full-game readiness.

Remove the whole selected set once, preserving all survivor identities, order,
fake models and performed flags. A discarded performed miracle isn't performed
again; an unperformed miracle isn't marked used before disappearing. No MP/CP
price or direct HP effect, defense response, virtual artifact consumption or
victim replacement is invented. Counts are distinct from ordinary consumed
uses, miracle uses and Broom/Soap attack removals.

## Turn, lifecycle, observations and transaction invariants

After all removal, the original owner ticks once using existing illness,
Sun and final-death hooks. Protected owned Suns/Bows remain in the surviving
hand. A periodic/worsening death can generate post-tick Bow shots; the shared
queue finishes those before ending checks and never ticks a second time.
Only actual passive uses can earn their existing deferred receipts. Discarded
victims never receive those use receipts. Real endings retain precedence over
turn limits; decision-limit exits remain explicit truncations.

Owned/read-only policy `discard_observations[B,4]` contains active, selected
count, toggle count and limit. `discard_order[B,capacity]` contains only own
selected slot IDs. They are zero outside phase7 and reveal no actual hidden
roles, future queue state or random tickets. Existing actor/Fog projections
and Python decision-context packing remain authoritative.

Diagnostic-only `discard_snapshot[B,6]` contains reservations, toggles, cancels,
completed discard turns, removed cards and removed performed miracles.
Lifetime `discard_count` and `discarded_card_count` survive resets. Reset clears
episode selection/order/statistics and queues, reseeds streams and increments
epoch; previous returned arrays remain owned/read-only snapshots.

Removal, survivor hands, periodic draws, Sun/Bow tasks, resources/statuses,
ticks, diagnostics and lifetime deltas stage with the complete command batch.
A rejected last hidden role, stale/duplicate/wrong-owner command or mixed
finished row cannot commit earlier removals or revival. Corrected retries
match an untouched reference. Raw optional ID arrays reject empty/excessive
sets, unknown or forbidden categories, duplicates, bad rank/dtype and implicit
noncontiguous copies. Omission preserves old unsupported raw fixtures.

## Bounded probe and historical replay compatibility

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-discard-smoke \
  --batch-size 512 --players 3 --seed 67
```

Six fixed scenarios cover an ordinary row, performed miracle, four-card removal,
periodic Sun revival, periodic Bow death, and cancel/redo. Public masks/phases
and fixed fixture choices drive commands; diagnostics only validate/fingerprint
results. Targets have Dark Cloud to isolate post-tick scheduling; separate
existing Bow tests retain their independent unforced-ticket coverage.

- 512 completed discard turns and original owner ticks; no other-owner ticks.
- 597 reservations,1,022 toggles,85 cancels,767 removed cards including171
  performed miracles;2,386 total commands.
- 85 Sun revivals,85 Bows consumed,170 post-tick shots/5,100 Bow HP loss.
- 170 consumed passive uses, but no ordinary attack, miracle performance,
  discard replacement receipt, MP charge or limit exit.
- Metadata `433dbca4704a6b43baff87f56253b334bc72d6a4e3f7b5355d90098055e7e881`.
- Replay `2b4e56ffd0462decef6036184a9dddb682fb11038afa9a16c0ee6f56abea0b84`.

The actual512/nine-player CLI probe also completes:2,896 commands,680 post-tick
Bow recipients/20,400 HP loss,512 ticks and no unfinished family or limit exit.
These are scripted turns, not full matches, training, strength or official
validation. Strict reports cannot be relabeled teacher/reward data or readiness.

Ready masks now expose the virtual control, so fingerprints that include masks
change. A throwaway comparative probe removes only the new ready-phase mask
column and exactly reproduces **all14** historical v18 replay fingerprints.
No gameplay selection/effect/RNG drift is hidden by updating goldens. New
metadata/mask fingerprints are versioned, not assigned to old evidence.
The historical utility-only smoke driver previously selected any nonzero mask
choice as a hand slot; it now restricts its scripted candidates to actual hand
slots, leaving virtual controls to their own phase-aware probe. This prevents
an unintended phase7 entry from stalling that old narrow diagnostic.

All earlier effect/source ledgers remain distinct. Full-game artifact effects
stay231/237, all237 acquisition weights stay pinned, and5,423 of41,472 startup
draws still lack implemented held abilities. The six missing effects are
Exchange, Sell, Buy, Guardian Pot, String of Fate and Release. Events/guardians,
Apocalypse/Sacrifice, teams/rewards, hidden resolution, cap migration, complete
neural tensors/actions and mixed-episode learning requirements remain under
ADR0097. The overall goal is active; local full-game training and live promotion
stay blocked. Trading's amount-interface question remains pending.

## Verification

The two new modules pass **624 tests**: 550 mechanics/source/layout/transaction
cases and 74 strict report/replay/CLI cases. They cover every eligible and
protected held model, 2/3/9-player rosters, all curse masks, full18-card removal,
used/fake identities, undo/cancel, toggle/global/turn limits, periodic Sun/Bow,
whole-batch rollback, mixed finished rows, epochs, optional raw omission,
invalid native profiles, owned readonly views, metadata/source drift and gates.

The final non-browser suite command
`pytest --ignore=tests/test_browser_controls.py -o addopts='' -q --tb=short --maxfail=5`
passes **6,411 tests in 115.60 seconds**. Strict mypy passes all114 source
modules; Ruff passes `src`/`tests`, and all67 selected full-game Python/CLI files
pass formatting. Native clang-format, `uv lock --check --offline` and
`git diff --check` pass. `uv` rebuilt/installed native0.68.0 and the installed
kernel19/observation19/command1/family2/max-discard64 exports match the adapter.
The actual nine-player default-sized CLI probe passed the recorded accounting.

No browser fixture, official validation, live game or learning run was performed.
Pre-existing native Python import-order/compact-stub findings are outside the
source/test lint scope, not claimed fixed. Git writes remain unavailable under
the current read-only Git permission boundary; changes are locally saved but
not committed. No workaround Git write path is used.
