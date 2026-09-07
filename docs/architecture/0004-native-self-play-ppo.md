# ADR 0004: Recurrent PPO for native self-play

- Status: **Accepted**
- Date: 2026-09-07

## Context

The native attack/defense curriculum can collect decisions far faster than the
browser, but a useful training loop must preserve the deployed action head,
recurrent state, active-player perspective, sparse rewards, and exact simulator
identity. A two-player zero-sum transition changes viewpoint whenever control
moves to the other seat. Treating the next player's value as though it belonged
to the current player would reverse attack credit and train the wrong value
function.

## Decision

Use clipped proximal policy optimization (PPO) with generalized advantage
estimation (GAE) and one recurrent policy/value network shared by both seats.
The Python trainer owns inference and optimization; the C++ environment remains
a small batched transition engine.

Each environment maintains two GRU states, one per seat. Only the active seat's
state advances on a decision. Both states reset at an episode boundary. PPO
minibatches contain whole environments rather than shuffled individual steps,
so training replays each seat's recurrent history in order.

Values are defined from the active seat's perspective. When the next decision
belongs to the other seat, its bootstrapped value and advantage are multiplied
by `-1`; when the same seat continues from defense into its attack, their signs
are preserved. Terminal rewards remain exactly `-1`, `0`, or `+1`, with no HP,
armor, or damage shaping. Rollouts reset at each update boundary and bootstrap
only nonterminal final observations.

Every run is bounded by explicit batch, rollout, update, epoch, and minibatch
arguments. Per-update structured logs report losses, entropy, approximate KL,
clip fraction, gradient norm, completed episodes, armor-selection rate, and
advantage magnitude. The candidate manifest records:

- algorithm ID `recurrent-ppo-self-play-v0`;
- parent model and weight identity;
- simulator metadata and exact rule-catalog fingerprint;
- all rollout and optimizer settings;
- aggregate training metrics.

The resulting model is always a candidate. Native self-play cannot promote a
model or authorize it to control a live room.

## Consequences

PPO naturally supports masked stochastic actions and avoids adding a replay
buffer or target network before the simulated rules are broad enough to make
those systems useful. Recurrent replay costs more Python/PyTorch work than a
fully feed-forward update, but environment minibatching keeps the sequence
contract correct and can later be replaced with a fused recurrent encoder if
profiling justifies it.

This first trainer is curriculum learning, not evidence of full-game strength.
It has no opponent league, checkpoint sampling, elements, multi-card defense,
resources, or browser evaluation gate. Those require separately versioned
decisions and live evidence.
