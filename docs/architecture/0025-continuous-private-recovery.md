# ADR 0025: Continuous private recovery and two-player evidence isolation

## Status

Accepted on 2026-09-11.

## Context

Four recent private API runs ended after `submit-command` timed out and the room
state remained unchanged through the reconciliation window. Every instance was
in a four- or five-player game. Replaying the command is unsafe because the
server may have consumed it despite losing the response. Stopping the process is
also inconsistent with the explicit `--max-seconds 0` contract.

A separate two-player run reached a Dream-cursed self turn with only additive
weapons and Thump-thump Tear as a reliable turn-leading card. The conservative
surface correctly refused an empty command, but it had omitted the Bible-audited
HP-or-damage sundry and mild-curse cleansers.

The schema-v5 neural adapter intentionally abstains outside two-player games,
while the live readiness evaluator previously counted failures and unclassified
terminals from multiplayer games in the same evidence cohort. Those runs cannot
measure the candidate's covered behavior.

## Decision

- Version the tactical behavior as `api-combo-utility-heuristic-v6`.
- Admit `removeMildCurses` cards as reliable cursed-turn actions.
- Admit Thump-thump Tear only when both its HP gain and damage outcomes match the
  accepted Bible and API catalog. Keep it behind deterministic utility and
  chance-attack options as a liveness fallback.
- Never replay a command with an ambiguous response. A finite run still fails
  after bounded reconciliation. An unlimited run records an unknown transition,
  leaves the affected match, rejoins the same private room, and continues.
- In unlimited mode, continue retrying retryable room reads with capped
  exponential delay. Recover an unsupported self turn, active-game no-progress
  limit, or per-match action limit by leaving and rejoining. Do not apply the
  no-progress recovery to an idle lobby.
- Reset the action budget after each match or recovery.
- Version the evidence contract as `live-resource-shadow-readiness-v6`, report
  schema 6. Exclude an entire run if any valid normalized game state has a player
  count other than two, before counting its failure status or terminal events.
  Malformed two-player evidence still fails closed as an integrity error.

## Consequences

Unlimited operation survives the observed network and policy dead ends without
duplicating a potentially consumed move. Recovery can concede the affected game;
this is preferable to blocking the room indefinitely and is recorded explicitly.
The readiness gate now measures only states on which the candidate is eligible to
propose actions. Existing v5 behavior runs remain immutable historical evidence
but do not satisfy the new cohort, so fresh two-player shadow games are required.
