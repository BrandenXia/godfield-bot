# ADR0140: approved complete-episode full-game training credit

## Decision

User-approved on 2026-11-03. ADR0141 implements collection and ADR0142 implements
the first recurrent optimizer and held-out evaluation.
The first full-game learner
uses complete native episodes and undiscounted terminal faction outcomes.
Every accepted decision by a present player gets that player's eventual
ADR0136 outcome: winning faction+1 including eliminated teammates, other
players−1 and true all-dead draws0. No HP/MP shaping, per-decision discount,
team-size normalization or opponent-sign shortcut is introduced.

Truncated and engine-failed episodes contribute no learner targets, including
their earlier accepted decisions. Do not bootstrap them from predicted values
or label them losses. Count and report them separately. A rejected native
command must not become a sample; do not substitute a different command.
Valid terminal zero is a draw, not an invalid/missing target.

## Rollout boundary

Collect accepted public observations, leases, actions, behavior log probabilities,
values, pre-action seat memories and forced-turn policy masks from ADR0139.
Pin the configured environment, encoder, policy architecture, behavior weights
and sampling seed. Keep behavior weights fixed for each collection batch.
Interleaved actors retain their own episode/seat histories; terminal outcomes
attach to their actual earlier decisions, with no invented post-death actions.

Forced confusion decisions have zero actor-gradient weight. Their native
outcome and valid value targets remain real. An episode ending at start with
no accepted command has no fabricated policy sample. Explicit reset happens
after terminal credit collection and clears every seat's state.

Validate observation/command/reward accounting before admitting complete
episodes to learning. Bound retained decisions and recurrent optimization
storage; a storage limit cannot silently turn a partial episode into a complete
return. A collection error remains observable and excludes that whole episode.

## Subsequent learner and gates

Use the existing project's clipped-policy/value/entropy optimization approach
where its contracts fit, with independently versioned full-game checkpoints.
Recompute differentiable recurrent sequences in each player's actual order,
record any explicit recurrent gradient boundary, preserve forced-turn masks,
and compare behavior probability/value references before updates. Record the
full undiscounted terminal target mapping and exclusions in reports/checkpoints.

Before full-game local-training readiness, verify real complete-pool learning,
checkpoint/restore determinism, finite updates, frozen held-out evaluation and
all player/team credit paths. Successful inference and terminal data collection
alone do not establish useful learning. Existing arenas/models/live controls
are unchanged, and official fidelity/live promotion remain separately gated.
