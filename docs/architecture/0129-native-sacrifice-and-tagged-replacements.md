# ADR 0129: Native Sacrifice and tagged replacement receipts

## Scope and remaining objective

2026-10-19. Complete the in-progress Sacrifice integration following v26's
generated guardian work, continuing ADR0097's full-game local-training objective.
This is a joined native mechanic, not a separate primitive or training-readiness
declaration. Native0.76.0 advances kernel/observation/plan/metadata to27 and the
attack-family contract to8. Six-column command1 and numeric trade-choice2 stay
unchanged. Existing arenas, models, checkpoints, live controls, accounts and
credentials are unchanged; no live games or training jobs are started.

The user approved labeled provisional local rules while preserving separate
official-fidelity/promotion gates. Reuse the existing bounded multi-removal
selection interface rather than introduce a new command architecture. Full-game
training, official fidelity and live promotion remain false. Git is read-only;
changes remain saved in the working tree, not committed.

## Dated source evidence

Read the public English translations on2026-10-17 local/2026-10-18 UTC and save
the complete response plus provenance in `data/snapshots/2026-10-17/`. Public
source: [official translations](https://godfield.net/i18n/en.json).

- Response SHA excluding archive newline:
  `bb1b433ba6d336765589aec940cca0bac8b7c0bdcee33969c207a17365509188`.
- The296 item rows retain catalog digest
  `df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.
- A separate read of the [official client](https://godfield.net/main.dart.js)
  matches saved client digest
  `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
- The independently pinned four relevant translation notes have SHA
  `aea0050ccb9c39ad3bde328857d8ed6c14011e33851e97bb7b660c5750941070`.

The notes distinguish Discard's absence of gifts from Sacrifice's replacements,
and replacement of the virtual control after Apocalypse. Client selection9499
shares non-weapon/non-revive/non-attractDanger restrictions for both actions;
confirmation9606 requires a selected victim. Cost handling3997 exempts these
leaders from ordinary miracle debits. Removal10740 and10762–10775 handles the
selected list, with Sacrifice rendering distinct from ordinary removal.

This supports the shared128-model eligibility, virtual identities1/2,
multi-selection, no selected-miracle use charge, and existence of replacements.
It does **not** establish server receipt quantity/timing, Apocalypse's official
trigger, recipient-Dream/cap semantics or compound ordering. Use the explicitly
provisional rule: one complete-pool replacement per removed card, after the
original owner's tick and queued guardian reactions. Keep the existing opt-in
completed-turn threshold, zero disabled; do not relabel it as official timing.

Source freshness here means matching public bytes at the recorded check, not
official behavioral validation or continuing freshness on a later date.

## Native control and removal

Append `sacrifice_enabled=false` to raw `FullGameBatch`; opting in requires
discard and gift profiles. The complete source factory passes true. Raw fixtures
that deliberately omit the new feature retain their explicit post-Apocalypse
unavailability rather than silently execute ordinary Discard.

Ready controlcapacity+1 reserves phase7. Slot+1 toggles eligible displayed cards;
0 confirms a nonempty selection; capacity+1 cancels without a tick. The64-edit
bound preserves confirm/cancel escapes. Before Apocalypse the operation is
Discard; afterward it is Sacrifice. Extend `discard_observations[B,4]` to[B,5]
with the public virtual model1/2, preserving the first4 fields. Other phases
return zero. Six-column commands and phase numbering remain unchanged.

Masks inspect displayed identities, never hidden actual protected roles. At
confirmation, validate every actual selection before removing any row. Keep
stable survivors, allow performed miracles, protect weapons/Sun/Mortar, and
do not execute removed cards' ordinary abilities. Neither operation is a held
use, miracle performance, ordinary consumption, MP/price payment, attack or
defense window. Sacrifice statistics remain separate from ordinary Discard.

Confusion's bounded native controller can select Sacrifice after Apocalypse.
It executes one native removal directly, without learner toggle steps; the
existing pre-step gradient mask excludes that forced turn. Voluntary selection
remains a genuine learner decision.

## Tagged shared receipt lifecycle

Sacrifice records requested replacements both in pending gift totals and a
private per-owner tagged subtotal. Family5 frames carry a private attribution
bit. Per owner, Sacrifice replacements run before ordinary pending receipts;
native seat order and nested depth-first behavior remain explicit provisional
choices. Original-owner periodic effects and guardian reactions happen first.

Each delivered receipt shares fresh monotonic IDs, unused flags, actual
receiver-Dream, complete weighted gifts, explicit hand caps, devil selection,
Sun revival and actual-held Bow reactions. Ordinary use/Sun/Bow replacements
retain their own attribution; they cannot inflate Sacrifice delivery counters.
Dead/ended unscheduled requests and suppressed queued frames increment the
tagged suppression count exactly once. No extra owner tick or recursive
guardian wave is introduced.

A limit during a Bow response can leave a tagged receipt pending in the
private queue. Requested minus delivered minus suppressed is then pending
work, not a fictitious successful/suppressed delivery. Terminal controls reject
further commands; explicit reset clears the queue and episode diagnostics.

The existing finite automatic-receipt bound also covers Sacrifice-triggered
Sun/replacement cycles. A focused always-Sun/always-damage adversarial fixture
reaches that bound and rolls back the entire command instead of hanging or
leaking partial receipts, revivals, RNG or counters.

## Observability and independent checks

`sacrifice_snapshot[B,9]` contains reservations, toggles, cancellations,
completed removals, removed cards, removed performed miracles, requested,
delivered and suppressed replacements. `sacrifice_model_counts[B,237]` counts
actual delivered tagged models3..239, including cards immediately stolen by a
devil. These are owned readonly private diagnostics, not policy observations.
Reset clears current episode counts without mutating earlier returned arrays.

Source-plan schema2 pins both virtual identities, notes, eligibility and
explicit provisional replacement semantics. Metadata pins the new public
observation width, tagged diagnostic fields and receipt model indices.
Discard's pre-Apocalypse report now says Apocalypse/Sacrifice are not exercised
in that probe, rather than incorrectly saying the feature is unimplemented.

New `simulation full-game-sacrifice-smoke` report schema1 uses complete native
gift/devil pools and unforced tickets. It scripts one preparation pass then one
three-card Sacrifice per environment. Preparation ticks and Sacrifice ticks
are separately counted; it never calls these full games or training evidence.
At4096/3/seed67:

- 4096 preparation turns plus4096 Sacrifice turns,24576 commands.
- 12288 requested/delivered replacements; all237 held models observed.
- 3027 devil appearances covering all five models;1234 stolen cards.
- 30850 devil HP loss; no ordinary consumption/MP charges or pending families.

The report checks exact turn, queue, receipt, hand and resource conservation;
source/count/scope tampering and any attempted readiness relabeling fail closed.
Independent Python ticket checks reproduce the native complete-weight histogram
across six seeds, including the maximum unsigned seed. Unit tests cover all128
eligible models at2/3/9 seats, every protected role, multi-selection/undo/cancel,
used miracles, hidden-role atomic rollback with complete-pool RNG, death before
delivery, limits, nested Sun/Bow attribution, forced confusion and reset/privacy.

Replay audit: behavioral fingerprints outside Discard and the devil probe are
unchanged. Discard changes because the phase7 observation adds its virtual ID;
the devil probe changes because the completed source factory now exposes the
correct post-Apocalypse control. Existing gameplay totals remain independently
pinned. All metadata hashes change with the versioned source/queue contract.

The completed v27 non-browser regression passes10272 tests in187.21seconds.
Ruff, mypy over126 source modules, changed-file formatting, offline lock and
whitespace checks pass. The ordinary offline uv CLI launches the Sacrifice
probe with readiness/promotion false. Browser/live differential tests were not
run. These results describe v27 before the separately approved cap99 transition.

## Remaining full-game work

Sacrifice is joined, but complete local-training readiness remains unproven.
Broader Apocalypse/endgame and team/elimination/reward handling, hidden
cross-role resolution, the explicit cap99 transition, complete observation/
action/checkpoint/learner interfaces, and seeded full-episode liveness and useful
learning probes remain required by ADR0097. Official differential evidence has
its own separate acceptance boundary; provisional local training must not be
made contingent on falsely claiming official fidelity. Do not shrink the full
objective to this scripted-turn milestone or change live promotion gates.
