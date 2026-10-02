# ADR 0103: Integrated attack, target and ordinary armor phases

## Status and scope

2026-10-01. Native 0.51.0 extends the user-approved **separate** `FullGameBatch`
engine from ADR 0102, rather than adding another caller-driven scheduler. The
same authoritative inventory, HP/MP/CP, illness, curses, episode and decision
state now execute single-card attacks, living-enemy target selection and
multi-card ordinary armor responses. Local full-game training, official
fidelity and live promotion remain false. Existing arenas, checkpoint shapes,
accounts, live controls and the pinned external API revision are unchanged.

Follow-up: [ADR 0104](0104-native-complete-pool-acquisition-and-provisional-overflow.md)
adds opt-in native complete-pool gifts and approved provisional overflow under
native 0.52.0 / development v3. The v2 measurements below remain historical;
manual replay arrays remain unchanged, but current metadata includes the new
version/acquisition identity.

This is still an incomplete development engine. It does not replace the
established guardian learner. Ordinary combat is one integration step toward
the full game, not a redefinition of the requested milestone.

## Source profiles and version boundaries

The API/Bible cross-checks used by the guardian card adapter are reused for
39 effect-free weapons, six fixed attack miracles and 47 ordinary armor
models. Wall and Turbulence are deliberately excluded from this slice. Together
with the twelve utility/cure effects in ADR 0102, the separate factory executes
104 distinct card effects. Registration of all 237 held models is **not**
execution support for the other 133. The guardian readiness audit's 102 usable
models remain a different scope and are not added to this count.

The sorted attack/armor profile SHA-256 is
`cdb29067a11535efeb6884b0fdee9968707c47e1cbf0a3d6e14adbd33bf341dd`.
Rows are `[model, ATK, element, origin, MP cost]` and
`[model, DEF, element, ordinary-kind-zero, cost-zero]`. The factory retains
ADR 0102's pinned catalog/client hashes. Values, categories, fixed hit rates,
absence of active abilities, costs and source descriptions must agree.

Ruleset `integrated-full-game-development-v2` has native kernel schema 2,
observation schema 2 and unchanged six-column command schema 1. Old development
metadata cannot claim the new identity. There is no checkpoint migration:
neither version of this engine has been admitted to the training registry.
The raw native constructor may omit both combat profile arrays for utility-only
fixtures; the source-pinned factory always supplies both complete profile sets.

Pure element compatibility is extracted into `combat_rules.h`. The existing
guardian kernel delegates to the exact same arithmetic with no behavior change.
Curse helpers continue to provide Flash selection restrictions, conservative
Fog visibility and periodic disease calculations.

## Integrated phases and choices

Implemented stable phase codes are setup 0, ready 1, target-selection 3,
defense-selection 4, terminal 12 and truncated 13. Attack-selection 2 and other
families remain reserved for future multi-card/special workflows.

For capacity `C`, the copied boolean mask has `C+10` choices:

- Ready: 0 passes; slot+1 chooses a displayed utility or reserves one attack.
- Target: `C+1+seat` selects a living enemy; self, dead and padded seats are masked.
- Defense: slot+1 toggles an ordinary compatible armor; 0 confirms the response.
- Noninteractive phases: no choices.

Reserving an attack advances only the decision, not resources, inventory,
disease or completed turns. Target dispatch resolves the true effect and cost,
consumes a weapon or marks/moves a retained miracle, pays MP, publishes the
pending attack and transfers control to its living defender. Defense toggles
consume nothing. Confirmation sums actual selected defenses, consumes only
those exact owned slots, applies HP-clamped positive damage and completes the
**original attacker's** turn. The defender does not receive an illness tick
merely for responding. Next turn order starts after the attacker, not after
the defender's seat. Attacker illness and defender damage are staged together
before deciding victory/draw, including both dying in the same resolution.

Flash permits one selected defense but still permits undo. After 64 toggles,
only confirmation is legal. It does not silently choose armor or truncate the
game. Both phase legality and episode/decision/actor/phase tokens are rechecked
inside native dispatch. Decision limits count every accepted selection, target,
toggle and confirmation; turn limits count completed owner turns. Mid-attack
administrative exits are explicit truncations, not wins, draws or evidence of
completed combat. Already accepted casts remain observable in diagnostics;
truncation masks and pending policy views are empty.

## Provisional behavior and visibility gaps

One-card turn scheduling, additive ordinary armor, commitment timing, cure/turn
ordering, free-for-all endings, resource caps and reusable miracle ordering
remain provisional. All supported attacks have fixed 100% hit rates. Chance,
boosters, area attacks, absorption, counters, reflection, bounces and special
defenses are absent in this engine, even where another legacy subset supports
them. No such subset effect is silently imported into a complete-game claim.

Fog uses the native living-enemy set and its own deterministic provisional
combat RNG stream, ignoring which legal enemy the caller nominated. It never
accepts a caller ticket or selects self/dead/padded seats. Gifts and illness
draws use independent streams, including after epoch resets; rejected late rows
do not consume any of them. Elimination legality remains public while Fog hides
other resources/status. Exact official targeting/timing remains unverified.

Before casting, pending observations use the **displayed** reserved attack
value/element/origin, never its hidden actual model or cost. After casting, the
resolved attack is public to its defender. Own hand views contain displayed
identities and selection handles only. Selection masks and defense previews
use displayed armor, not hidden identity. Actual effect/cost/element resolves
within the trusted transaction. Unsupported actual effects, insufficient
hidden costs and incompatible hidden armor fail explicitly and atomically;
these unresolved Dream behaviors still prohibit learning admission. A user
can undo a bad disguised defense and confirm without it in diagnostic tests.

## Atomicity and observability

Each command stages all seat statuses/resources, episode/RNG state, selection
flags and any changed ordered hands. All rows validate before any environment
commits. A late-row failure cannot partly pay, consume, select armor, damage
either owner, cure, tick disease or advance decision/turn state. Commit has no
allocation, checks or random draws. Dead Heaven owners cannot be healed by an
end-turn periodic call. Inputs, loops, inventory and profile dimensions retain
the native development bounds.

Public copied/read-only additions are `selected_defenses[B,C]` and
`pending_observations[B,10]`: active, turn owner, target, attack, element, origin,
displayed selected defense, selected count, toggle count and reserved attack
choice. Empty/noninteractive rows are zero. Diagnostic true inventories and
all-player resources remain separate. Lifetime cast/resolution/toggle/damage
counters complement pass/utility/consumption/MP counters. Source-pinned immutable
metadata describes phase/choice layouts, defense bounds and randomness.

## Offline complete-loop probe

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-combat-smoke \
  --batch-size 32 --players 3 --seed 67 --max-turns 64
```

This probe seeds fixed known own hands and varied illness stages. It chooses
using only own displayed hands, masks, visible self resources and the public
pending attack. Diagnostic snapshots are used only for replay hashing. A test
redacts true inventory/all-player diagnostic arrays and verifies the same
choices/outcomes/counters, with only the diagnostic replay hash changing.
There is no real deal/refill, checkpoint training, account use or official play.

The default probe produces 32 winners, zero draws/truncations/unfinished games,
402 completed turns and 977 accepted commands: 191 utilities, 211 attack
selections, 211 casts, 211 resolutions and 153 armor toggles. It records 4,216
actual HP damage, 1,546 MP spent, 362 consumed cards and 193 retained miracle
uses. This is **loop liveness, not bot strength or an official-bot win rate**.
Metadata SHA-256:
`d06b0e979d06df9904a37bf0410275a01667fc0a4e702f5bf78ff29f757456de`;
diagnostic replay SHA-256:
`3afbf91451cdbf009aa43192fa3915e41027f4cf0e487b26608d1b3759e4f8ff`.

The utility-only probe still records ADR 0102's same effect/counter totals and
32 turn-limit truncations. V2's terminal control projection is explicitly
versioned, so its replay hash is now
`08dee281b662d951143dee23e906d446600d06e6ced4f40fa3dd7de6e3d2b254`,
not a claim of byte compatibility with the old development metadata. The
established legacy 0.46 golden trajectory remains unchanged.

## Verification and next integration

The new combat tests cover every source profile, all 49 element pairs, actual
costs/retention/consumption, additive selection/undo, Flash, the 64-toggle bound,
dead/self target rejection, two-to-nine seats, origin-based turn advancement,
simultaneous deaths, terminal-before-limit precedence, intermediate truncations,
stale/tampered envelopes, hidden identity/cost/element errors, mixed-phase batch
rollback, Fog RNG rollback/isolation/reset, copied views, protocol parity and
source/metadata admission. The sole initial focused failure was a test fixture
misclassifying Thump Thump Tear (202) as a miracle; the fixture now uses the
actual unsupported miracle Release (239), without weakening category checks.

All 345 joined-engine tests pass (128 utility/state and 217 combat/probe).
The full non-browser suite passes 2,482 tests; both local browser fixtures pass
outside the macOS sandbox after its local Chromium IPC was denied. Ruff,
changed Python formatting, mypy across 88 modules, new native-file formatting,
frozen offline lock consistency and whitespace checks pass.

Next is integrated acquisition/refill/overflow and special offensive/defensive
workflows, then the remaining utility targeting, economy, events, guardians,
removal/revival, apocalypse, teams and complete multiplayer neural interfaces.
Full-game episode/replay/learning validation is required before local readiness;
official evidence remains separately required before live promotion. Diagnostic
reports cannot relabel this incomplete engine as a reward/teacher dataset.
