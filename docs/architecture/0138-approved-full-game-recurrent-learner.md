# ADR0138: approved separate full-game recurrent learner

## Decision

User-approved2026-11-03; observation encoding, recurrent inference and per-seat
memory implemented in ADR0139; complete rollout/learning still pending. Build a separate recurrent
policy for the full-game environment with18 padded hand slots, all28 native
phase-specific choices and independent memory for each player in each episode.
Use the approved terminal faction rewards (ADR0136). Preserve existing arenas,
models, checkpoint shapes and live controls. No implicit old-checkpoint loading
or migration is authorized by the new shape.

The policy must support2–9 players and native teams, not a two-player wrapper
whose targets or payoff silently change in multiplayer. Raw gameplay commands
remain six columns; only native-displayed legal choices can be submitted.
Forced confusion turns have zero policy-gradient weight. Their outcomes and
memory lifecycle are not fabricated losses or omitted episode endings.

## First implementation boundary

Start with a versioned public observation encoder for kernel33. Admit only
reviewed public getters, including displayed own cards, Fog-safe player and
guardian views, public teams, ordered selections, pending attacks/reactions,
trade/market choices and public event/control views. Keep missing/hidden/padded
values distinguishable. Instance IDs and episode/action leases may be retained
for action validation and memory dispatch, but are not learned identity hints.

Do not read true inventories, hidden HP/status diagnostics, pending generated
models, future recipients, random-stream state, private escrow or cumulative
diagnostic counters as policy input. Tests must change hidden actual cards and
Fog-hidden opponents independently and assert identical encoded observations
and policy inputs where the public situation is unchanged. Native masks and
raw views remain the reference; the encoder cannot invent legal actions.

Recurrent state is indexed by environment, episode and absolute player seat.
Update only the acting player's state for an accepted decision; another seat
cannot inherit it. Rejected commands cannot append learner samples or commit
memory updates. Explicit reset clears every seat in that environment, including
eliminated teammates. No cross-episode memory or shared team-hidden hand state.

After encoder/memory validation, connect complete rollouts and the terminal
credit adapter, then a bounded local learner and held-out learning tests. Choose
and record optimization/discount/truncation treatment explicitly; reward plumbing
does not imply a correct bootstrap or useful learning. Checkpoints and reports
must pin source/effect metadata, gameplay/cost policy, encoder/recurrent schema,
resource/hand/episode bounds, optimizer and random seeds.

## Acceptance boundary

The3072-game v33 random-policy integration sweep is a liveness checkpoint, not
training readiness or strength. Keep full-game training/promotion flags false
until complete encoding, episode/seat memory, accepted-command rollout credit
and useful local-learning validation pass. Official fidelity and live promotion
remain separate gates; the user's provisional mechanics approval is unchanged.
