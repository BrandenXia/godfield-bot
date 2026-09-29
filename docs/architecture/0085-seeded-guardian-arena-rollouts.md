# ADR 0085: Seeded, actor-relative arena rollouts

## Status

Accepted, 2026-09-29, for the rollout interface only. Native package 0.44.0
adds actor-hand projection schema 1 without changing turn/combat schema 2.
The separate Python arena has source identity
`provisional-guardian-arena-rollout-v1` and observation identity
`actor-relative-guardian-arena-v1`. No existing feature schema, checkpoint,
training curriculum, live controller, or account changes.

The first neural trainer is a subsequent decision: a separate local duel
checkpoint is recommended before multiplayer learning. Multiplayer episodes
are supported here, but duel signed-advantage math must not be silently used
for three or more players.

## Bounded local curriculum, not official full-game fidelity

The pinned-source arena contains 94 inventory models: 47 ordinary armor,
39 fixed-attack weapons, six fixed-attack miracles, and Wall/Turbulence. Each
player starts with a synthetic shuffled nine-card hand: one weapon, one attack
miracle, one armor, one defense miracle, and five uniform samples from all 94.
There are 18 stable padded slots. This is neither the official deal distribution
nor a redraw, acquisition, overflow, or hand-compaction implementation.

Episodes start at seat zero. `cards-only` starts at an offensive turn;
`mars-opening` performs one seeded Mars guardian effect from seat zero to an
enemy; `mixed` alternates these openings by environment index and episode.
Mars has five simple fire attacks, including its catalog hit rate. The adapter
does not randomly inject the other 34 supported guardian effects: curse flags
are not yet complete curse dynamics. Guardians remain diagnostic state after
the opening; later turns do not automatically trigger them. The one-event-per-
turn native schedule is still explicitly provisional.

Random streams are independently keyed by seed, environment index, and episode
number. Resetting rows together, separately, or in a different order gives the
same hands and guardian opening. Native state is reset before each explicit
deal. Lifetime diagnostic counters retain their existing native semantics.

## Observation boundary and action contract

`actor_hand_snapshot()` projects only the acting player's `[B, H, 9]` native
hand: instance, model, selected, role, ATK, DEF, element, MP cost, reusable.
It returns a copied read-only array and zeros for finished native rows. The
adapter does not retrieve full inventory or hand-feature snapshots. Instance
IDs are used only to identify occupied slots, not as neural features.

Policy observations contain 43 global features, nine padded public-player
rows with eight features each, 18 own model IDs, seven numeric features per
own slot, and a 30-action mask. Players and targets rotate into actor-relative
order; self is row zero. Public HP/MP/CP, alive state, and curse bits are visible,
but opponent hands and counts are not. Numeric hand features include selection
and reusable/cost information. Terminal observations zero policy features,
hands, and masks and use actor -1. Absolute actor/episode/decision fields are
rollout bookkeeping, not policy inputs.

The approved padded action layout is retained conceptually, not claimed to be
checkpoint compatible: pass 0, card slots 1–18, relative target slots 19–27,
forgive 28, confirm 29. Selecting an offensive card enters adapter phase 5;
selecting a legal target then calls native declaration. The card and MP remain
unchanged until target commitment. Defense uses native selection/confirmation
legality. Native phase 4 is a live Turbulence target decision, **not** terminal.
Its target action rotates back to an absolute living seat before native bounce
resolution. Confirm and forgive map to native actions H+1 and H respectively.

`step()` accepts a contiguous int64 vector of B actions. Every row is checked
against fresh authoritative masks before grouped mutation. Finished rows use
-1 while remaining rows proceed, with no repeated terminal reward. Explicit
`reset_done()` preserves the final observation until the caller resets it.
Returned observations and transition arrays are copied/read-only.

## Rewards and anti-stall limits

Each absolute seat receives a zero-sum reward. Let
`u_i = (HP_i + 0.05 * MP_i) / 100` and
`phi_i = u_i - mean(u_other_seats)`. Dense reward is
`shaping_weight * (gamma * phi_next - phi_previous)` (default weight 0.1,
gamma 0.99). A winner receives +1; other seats receive `-1/(P-1)`. CP and
unimplemented curse behavior carry no additional utility reward.

Native turn and 64-toggle limits remain active; the adapter adds a decision
budget covering virtual targets and all defense/bounce decisions. A native
winner takes precedence over the same-step decision limit. Limit exits are
reported separately as truncations, never fabricated draws or wins. Both
terminal wins and these deliberately bounded absorbing episodes use zero
next potential and zero bootstrap. A trainer must therefore use
`terminated OR truncated`, rather than standard continuing time-limit
bootstrapping. Tests verify the discounted potential cancellation at this
boundary. Underlying pending state is retained for forensics on adapter limits.

## Offline inspection and validation

`simulation guardian-rollout` streams legal greedy-baseline transitions and
reports counts by phase/action, completions, truncations, seat wins, source
pins, configuration, and a transition digest. It does not write trajectories
or train weights. Collection is capped at one million decisions, with native
batch size capped at 4096. The baseline never deselects already-selected armor
while trying to accumulate defense; it remains only a smoke-test opponent,
not an expert or a performance gate.

The 25 new tests cover actor projection, immutable snapshots, opponent-hand
isolation, actor rotation, target commitments, exact MP spending, explicit
bounce choices, mixed-batch invalid input atomicity, native toggle limits,
adapter decision limits, absorbing rewards, terminal precedence, independent
resets, 2/3/9-player legal rollouts, seed replay, and CLI/readiness contracts.

A seed-67, 32-environment, 512-step mixed smoke run with max-turns 24 and
max-decisions 128 generated 16,384 legal decisions: 107 wins (59 seat zero,
48 seat one), 266 truncations, and 296 bounce-target decisions. Its digest was
`1ec34bcc2fe56430ede9caaf0405e831fc1619bc146790ae3b245670f863a449`.
These are bounded-loop checks, not learned-policy results or full-game wins.

The full non-browser regression suite passes, along with Python lint/format,
strict typing (70 modules), the frozen lock check, native formatting, and
whitespace checks. Browser-control tests are excluded because this milestone
does not change browser behavior.

`local_rollout_ready` is true; full-game readiness, official verification,
live checkpoint compatibility, and promotion remain false. The next work is
an explicitly separate checkpoint/trainer, held-out local evaluation, and
broader acquisition/guardian/mechanics fidelity. Reaching all catalog IDs
alone will not remove the official validation gate.
