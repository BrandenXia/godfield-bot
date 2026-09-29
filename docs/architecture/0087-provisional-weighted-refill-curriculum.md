# ADR 0087: Separate provisional weighted replacement gifts

## Status and scope

Accepted, 2026-09-29. The user explicitly chose a separate opt-in replacement-gift
curriculum after baseline-versus-baseline no-redraw duels frequently reached the
turn limit. This broadens local training, not official-game validation.

`GuardianRolloutConfig.refill` defaults to `none`. The opt-in value is
`weighted-consumption-v1`, with curriculum identity
`synthetic-guardian-weighted-refill-provisional-v1`, separate rollout source
identity, and an explicit `GuardianRefillPlan` in every new checkpoint.
Existing no-redraw behavior and checkpoints remain usable. Crossing between
the two curricula through ordinary resume is rejected in both directions.

Native 0.44.0, actor-hand projection 1, the 43/18/30 observation/action layout,
HP/MP rewards, and the live policy remain unchanged. Inventory and combat stay
in the C++ batch. The seeded adapter schedules gifts through one bulk
`deal_cards` call; it does not add a Python combat engine or bypass legality.

## Pinned distribution, hypothetical timing

The refill pool is exactly the native arena's 94 supported inventory models:
47 armor, 39 plain weapons, six basic attack miracles, Wall, and Turbulence.
Every weight is cross-checked between the pinned API `giftRate` and a unique
Bible `Gift Rate: n/500` record. Missing, malformed, duplicate, or differing
weights fail closed. The ordered `(model_id, numerator)` profile has total
weight 227 and SHA-256
`fecd58f31003c6a170cb41e0ef9f68e1659e9e5f0d817c4a0b98e094c32b6423`.
This content pin supplements the existing catalog and Bible-client pins.

Sampling uses relative weights **conditioned on those supported models**.
It is not the full official gift distribution; unsupported cards are neither
dealt nor relabeled as supported cards. Initial nine-card balanced deals and
optional Mars openings keep their original RNG streams unchanged.

The deliberately provisional schedule is:

- Queue one replacement for each ordinary weapon consumed at declaration and
  each ordinary armor slot consumed by confirmation.
- Do not replace retained miracles, including Wall/Turbulence. Selection,
  deselection, forgiveness, and passing do not create armor gifts.
- Wait until the original turn finishes, including any bounce target choice
  and redirected defense. Never deal during a pending attack or virtual card
  target selection.
- Replace the same empty slot for living owners only. Skip dead owners.
  Finished win/turn/toggle/decision rows discard pending gifts without drawing
  RNG tickets. Resets clear the queue and restart the episode's gift stream.

Per-row gift randomness uses `SeedSequence([seed, environment, episode, 6771])`
and integer cumulative-weight tickets. Sorted `(owner, slot)` queues make draw
order deterministic. New instance IDs start after the initial deal and are
unique per environment/episode. Refill preserves hand size; it does not model
official hand compaction, overflow, Miracle Soap, or acquisition triggers.

Only the pre-action acting player's hand projection is used to record consumed
slots. No opponent inventory is added to observations or used as a policy input.
The native inventory remains authoritative for inserting cards into empty slots.

## Observability and isolation

`guardian-rollout` and `guardian-train` accept the opt-in flag. Read-only
`guardian-evaluate` reconstructs the recorded curriculum automatically.
Acquisition/source/observation metadata and the full refill profile are compared
on resume/evaluation in addition to native, architecture, and reward contracts.
Historical manifests without refill fields default to no redraw.

Rollout reports, PPO updates/logs, and evaluations count replacement gifts.
Rollout/update counts cover only their window; the arena's diagnostic counter
is lifetime cumulative. Historical evaluation/update gift counts remain nullable
rather than inventing counts. Gift counts are not policy features or extra
shaping rewards. Existing absorbing boundaries and explicit resets remain intact.

Run a new isolated local experiment with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --batch-size 32 --teacher-updates 64 --teacher-selected-defense-weight 4 \
  --updates 10 --max-turns 32 --max-decisions 128 \
  --refill weighted-consumption-v1
```

Do not pass an existing no-redraw checkpoint to this command's `--resume`.
To resume a refill checkpoint, include the refill flag and its original arena
bounds/opening/architecture. Resume still writes a new child with cold optimizers.

## Bounded experiments and remaining limitations

All following comparisons use 32-turn/128-decision duels. On paired seed
1,000,070, baseline-versus-baseline with identical initial deals/openings had
eight decisive games and 24 turn-limit endings without redraw. With refill it
had 24 decisive games, four turn-limit endings, and four decision-limit endings,
with 1,218 replacement gifts. Refill materially increased decisive outcomes on
this diagnostic set; it did not establish official timing or a general rate.

Checkpoint `61564ab1-7f5f-4876-8869-56457c153539`, checksum
`2b042425637b4f8b0ec3193443599ea03edcaa766192909d0eab04a54fb9020d`,
trained from scratch with 64 imitation updates/selected-defense weight 4 and
10 PPO updates at batch 32/window 64. Its raw-neural evaluation had nine wins,
16 losses, and seven truncations (four toggle, three decision).

Child `c6ee0b25-6494-47c6-b669-bdb43300061a`, checksum
`a0fd51b1d87be1dbdd4676de6900a7d66c3cd1899c08b0ddeb94f83ef2029138`,
continued with 128 imitation updates/weight 8 and 10 PPO updates. On the same
diagnostic set it had 13 wins, eight losses, and 11 truncations (four turn,
three toggle, four decision). Two additional 64-game paired evaluations were:

| Seed | Wins | Losses | Turn limit | Toggle limit | Decision limit |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2,000,070 | 17 | 22 | 10 | 0 | 15 |
| 3,000,070 | 18 | 21 | 13 | 2 | 10 |

The diagnostic set informed development, so it is not an untouched promotion
test. Additional seeds do not demonstrate reliable superiority; policy loops
remain possible and are bounded, not hidden behind a teacher fallback.
Checkpoint `420b053f-9554-4491-8da2-b3efeb185720` was also re-evaluated after this
change and retained its original four wins/seven losses/21 turn limits.

The next local policy milestone is stronger defense termination/generalization
under the refill distribution, followed by additional resource/guardian/effect
coverage. This curriculum still lacks most official full-game mechanics.
Full-game readiness, official verification, live compatibility, and promotion
remain false for both candidates; no online games or live controls were changed.

## Verification

Tests cover source/profile integrity, unchanged initial observations, deferred
weapon/armor gifts, forgiveness, retained Wall/Turbulence, bounce defense,
dead-player exclusion, all absorbing boundaries without RNG draws, batch action
atomicity, deterministic subset resets, multiplayer legal rollouts, windowed
counts, CLI setup failures, actual local learning, and cross-curriculum rejection.
All 1,258 non-browser tests passed, along with lint, strict typing of 73 modules,
changed-file formatting, and lock/whitespace checks. Unrelated baseline formatting
differences are left untouched.
