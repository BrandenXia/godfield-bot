# ADR 0133: retain hidden protected Discard/Sacrifice selections

## Status and decision

User-approved after the schema30 nine-player episode probe stopped on actual
Sun Amulet208 disguised as MP utility196. The selected slot was legal through
its display, but the actual card is protected from removal. Implemented as
native0.80.0/schema31 and verified below. Schema30/old raw behavior still errors
atomically.

Add a separately versioned opt-in raw rule. On a displayed-legal confirmation,
retain selected protected actual cards in their original custody/order/flags;
remove only eligible actual selections. Record the rejected removals privately.
Finish the original turn even when every selection is retained. Only genuinely
removed cards earn Sacrifice replacements. No ordinary Discard replacements,
price/MP payment, held-use consumption or miracle performance is invented.

Keep public masks and selections display-only, strict old raw behavior by
default, existing arenas/checkpoints/live controls unchanged, and promotion
blocked. The rule is a labeled local hypothesis, not official fidelity. Do not
change the pinned prohibition on discarding weapons, Sun Amulet or Dangerous
Mortar. Test partial/empty removal, both protected identities, discard/Sacrifice,
survivor order, receipts, no premature tick and atomic rejection of real errors.

Trusted reproduction: schema30 default9-player/32-env probe, environment28,
command `(28,1,406,3,7,0)`, slot3 actual208/display196/unused. Other held cards
were actual27/display96 and actual209/no disguise. These identities remain
diagnostic-only and must not become a policy feature.

## Native/source boundary

Append readonly `resolve_hidden_removals=false` after the role manifest argument.
It requires registered discard profiles. The complete factory sets it true and
pins the semantics in metadata31. Only actual protected208/209 behind a
discardable display enter retention; other invalid confirmations still fail.
No category restriction or official pinned eligibility table is weakened.

The physical survivor list preserves original order and identity/fake/used
flags. Removal/performed-victim counts and tagged Sacrifice receipts use the
eligible actual count, not the displayed selection count. A confirmed empty
removal is one completed confirmation/turn, but zero removed victims, zero use
consumption and zero replacement receipts. The normal original-owner tick,
Sun/Bow, guardian/event and deferred-receipt lifecycle still runs. A retained
Sun may subsequently be legitimately consumed by its normal post-tick revival;
retention does not grant immortality or skip death hooks.

`hidden_removal_snapshot[B,7]` is owned readonly reset-per-epoch private
diagnostics: affected Discard confirmations, affected Sacrifice confirmations,
retained selections, effective removals in affected confirmations, empty
confirmations, retained Suns, retained Mortars. Counts describe the resolution
event, not a guarantee of custody after later death effects. Episode report3
adds conserved totals and includes the view in rollback/replay fingerprints.
No true identity or failure counter enters public masks, previews or policy
features. Command1/family8/trade-choice2 and the role-manifest hash are unchanged.

## Observed diagnostics

- Source-factory seed67/policy901 probes now finish64/64 two-player,64/64
  three-player and32/32 nine-player episodes without errors or truncations.
  The nine-player probe accepts17939 commands and records3 empty protected
  Sacrifices, retaining3 Sun selections, with no replacement for those cards.
- Across2–9 seats, seeds0/1/67 and32 environments per setting:759 completed
  episodes (749 winner endings/10 draws),9 explicit unaffordable hidden-cost
  errors,0 turn/decision truncations and293027 accepted commands. Removal
  totals are `(1,3,4,1,3,4,0)`; no protected-removal error remains in this sweep.
- All24 scripted diagnostic replays, plus explicit legacy100 resource replay,
  remain unchanged; only metadata hashes change. Existing arenas, checkpoints,
  live controls and promotion flags remain unchanged.
- Focused protected-removal/episode/Discard/strict-guardian tests pass877 cases;
  a subsequent separate retained-Sun post-tick revival test also passes.
- Final complete nonbrowser regression:12393 passed in224.83 seconds. Focused
  ineffective-component/protected-removal/episode tests pass728 cases. Ruff,
  formatting, mypy129 modules, native formatting, offline lock validation and
  `git diff --check` pass. The normal offline frozen CLI returns report3 and
  completes64/64 default episodes with16015 accepted commands and no errors.

Git metadata requires the separate permission flow in this workspace. After
the user's commit reminder, the verified milestone is staged for a checkpoint
commit; the public pinned client fixture is now inside tracked snapshots rather
than an ignored local run directory. The source-provenance test passes with
the portable path and identical client bytes.
No accounts, live games, credentials, policy checkpoints or training jobs were
created or changed for these local verification steps.

These are weak random-policy integration diagnostics, not candidate strength,
official evidence or training-ready certification. Actual hidden unaffordable
costs remain explicit errors pending a separate approved rule. ADR0097's full
mechanics/teams/rewards/learner/action-observation contracts and useful-learning
validation remain required; promotion stays blocked.

One retained cost-error reproduction is2-player/32-env seed0/policy901,
environment15, command `(15,1,122,0,3,20)`. The owner has0 MP; actual miracle214
is followed by actual armor181 disguised as reducer163. The displayed sequence
has a waiver but the actual sequence does not. That cost rejection must remain
atomic, not leak true identity into selection masks, and not be hidden by the
ineffective-component rule. Resolving insufficient actual MP is a separate
decision, not part of protected removal retention.
