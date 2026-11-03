# ADR 0118: Joined Dreaming Hat and provisional whole-hand redraw

## Status and scope

2026-10-03. Hat was implemented during the v16 development step and verified
together with the shared-family scheduler in native 0.66.0,
`integrated-full-game-development-v17`. Kernel/observation/plan/metadata are 17,
command remains 1. The new Dream-defense source plan is version 1.
Hat contributes one held model; with ADR 0119 the joined total is 230/237.
This is implementation coverage, not official fidelity or training readiness.
Existing arenas, checkpoints, API revision, credentials and live controls stay
unchanged. No live game or training job was launched.

## Pinned source boundary

Saved catalog/client SHA pins remain
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`
and `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
These are primary saved sources, not a new Oct 3 freshness claim. Catalog
model178 is armor, Wood, DEF14, ability `selfCurseAndRedraw`, curse Dream,
price15, gift weight1. Bible text/assets agree. The builder validates complete
snapshots, the exact raw row, Bible detail, image and element paths; changing
and rehashing the catalog cannot silently alter this contract.

Profile `(178,14,3,2)` is model/DEF/element/self-curse mask; SHA
`d635aa3250b0d358ede00401a1cadaf1a3c3872bf924425d5d25a35f89a909ff`.
The saved client's `replaceItems` handler (11574–11586) clears/replaces the
actual held display. `A.fG.lJ` (12646–12670) maps replacement rows onto nonempty
held widgets; their `e` field is the actual catalog model initialized by
`A.aC.hn` (12859), not merely a disguise marker. Therefore replacing only
already-disguised cards would be a misreading of the client.

The event does not disclose server draw weights, instance-ID generation,
used-miracle exceptions, duplicate-Hat composition or exact timing. Read-only
inspection found Hat catalog text in runs but no captured `replaceItems`
evidence establishing a triggered Hat redraw. Those boundaries remain
explicitly provisional; no gameplay replay is invented.

## Joined execution

- Public selection/preview uses displayed DEF14/Wood and normal compatibility,
  optional Curtain prefix and Flash limits. Confirmation resolves actual roles.
- Consume selected cards first, resolve incoming HP/effects and Sun, then apply
  self-effects in click order before queued counters. A finally dead Hat owner
  is diagnosed and suppressed, not revived or given a new hand.
- Each actual selected Hat on a living owner applies Dream, then redraws all
  remaining held rows, preserving count. Performed miracles are replaced;
  newly drawn miracles are unused. Multiple selected Hats each trigger a redraw
  in click order, including bounded empty-hand redraws.
- Replacement models use pinned full-held gift weights, fresh unique IDs and
  dedicated streams. Dream is active before fresh independent 50% same-category
  disguise sampling; unchanged fake/actual IDs are legitimate draws, not errors.
- Redraw is not an acquisition gift, overflow, use, resource change or owner
  tick. Actual Hat consumption earns only its existing deferred use receipt.

All of these joined timing/generation choices are provisional. The native
constructor accepts optional `dream_defense_profiles[N,4]`; supplied profiles
require draw weights even when automatic gifts are off. Explicit empty/malformed
profiles, bounds, categories, duplicates and implemented-role collisions fail.
Omitting profiles preserves the unsupported Hat role in raw older fixtures.

SplitMix/rejection sampling reuses the bounded native sampler, with episode
illness-seed XOR `0x452821e638d01377` for replacement models and XOR
`0xbe5466cf34e90c6c` for disguises. Reservation/cancellation never samples.
Every stream, hand, identity, resource/status mutation, receipt and counter
stages before whole-batch nonthrowing commit. Late errors preserve all rows;
corrected retries match independent runs.

## Observability and verification

`dream_defense_snapshot[B,8]` is owned, read-only, diagnostic-only: Hat uses,
Dream applications, redraws, replaced cards, disguise draws, changed displays,
dead suppressions and empty redraws. Lifetime `redraw_count`/`redrawn_count`
persist; reset clears episode rows/reseeds streams without mutating old views.
No private random ticket, future model or other owner's true hand is added to
the policy interface. Existing displayed armor/hand/legal views suffice.

The dedicated Hat module passes 126 cases: independent full-weight/fake
oracles across 2/3/9 players and curse combinations, same-count fresh IDs,
used miracles, duplicate/empty Hats, actual-vs-displayed identity, HP edges,
Sun priority, full blocks, mixed Fever/Hat order, gift suppression, reset/limits,
late-row rollback and exact source/metadata drift. The shared-family probe in
ADR 0119 additionally exercises 85 Hat defenses/redraws of 170 remaining cards
at the default batch size. These are mechanics tests, not strength results or
complete-game learning. Fidelity, full-game readiness and promotion stay false.

Seven held models remain after ADR 0119, and held accounting does not include
virtual commands, guardians/devils/phenomena or complete event/learning systems.
The overall goal remains active. Git metadata writes remain unavailable after
the prior approval-review failure; source changes are saved locally, not
committed, without retrying or bypassing the blocked Git write path.
