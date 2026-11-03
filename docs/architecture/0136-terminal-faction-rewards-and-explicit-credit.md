# ADR0136: approved terminal faction rewards and explicit credit

## Status and decision

User-approved2026-11-03; implemented in native0.82.0/reward schema1. At a true
full-game ending, every winning faction member receives+1, including dead
teammates; other present players receive-1; an all-dead draw gives0 to every
present player. There is no HP/MP shaping or team-size normalization. Truncation
and engine errors are not synthetic losses or terminal-value targets.

## Compatibility and interface boundary

Add a separately versioned reward interface to the existing full-game engine,
not a gameplay rules change. Preserve kernel/observation/plan/metadata32,
command1/family8/trade-choice2, all random streams and existing arenas/models/
live controls. A native package release and explicit reward schema identify
the addition; a separate learner-side metadata record pins the approved mapping.

Native terminal values and validity masks are owned readonly absolute-seat
arrays padded to9 seats. Nonterminal/truncated rows and padding have no valid
terminal reward; a legitimate draw has valid zero values. Repeated native reads
are stable and nondestructive. They neither consume a game event nor move RNG.

The learner adapter must emit a terminal episode's credit at most once, preserve
the epoch/decision tokens, capture actor/forced-turn policy weights before an
accepted step, and never append a rejected action or hide a native error.
No automatic reset may drop an uncollected ending. Dead teammates' old decisions
retain their faction outcome; they do not receive invented post-death actions.
Forced turns have zero policy-gradient weight, not a fabricated zero reward.

This supplies terminal reward/credit plumbing, not a full policy encoder,
rollout dataset, optimizer, discount/bootstrap rule or trained checkpoint.
Full-game training, source fidelity and live promotion remain gated. Hidden
insufficient-MP handling is unchanged in this release and still raises atomic
errors. The user has approved a subsequent, separate provisional fizzle rule;
that gameplay change is not part of this reward-interface release.

## Verification

569 focused reward/episode tests pass. Independent reward oracles cover all125
three-player team maps and every possible winning representative; other cases
cover draws, eliminated allies, real post-death endings, forced turns, explicit
reset/credit lifetime, cursor drift, rejected atomic batches and corrupt native
views. CLI tests preserve process-global logging for later learner tests.

The real CLI's seed67/32-environment2v2 diagnostic completes all32 games, with
9,111 accepted commands and zero engine errors. Reward totals are
`[4,4,-4,-4,0,0,0,0,0]`; all four present seats have32 valid outcomes. Enabling
credit collection leaves the corresponding untracked gameplay and replay hash
unchanged. Episode reports advance from4 to5; untracked rewards are explicitly
unknown, not invented zeroes. Static checks and lock consistency pass.
The full nonbrowser regression passes13,046 tests in301.96s, including the
existing scripted replay pins and older curriculum/training compatibility.
