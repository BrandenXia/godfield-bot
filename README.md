# ロキ-67 — a learning God Field bot

This repository is for an observable God Field agent that
keeps a stable in-game identity and improves from completed games.

The architecture is accepted and implementation is underway. The dedicated
`ロキ-67` browser identity has been created and used only in bounded Training probes. The current
official client and its in-game reference data were surveyed on 2026-09-06,
enriched with element metadata on 2026-09-07, and freshly revalidated on
2026-09-20; see
[the research snapshot](docs/research/2026-09-06-godfield.md) and the
[architecture decision](docs/architecture/0001-proposed-system.md). The
[complete extracted Bible](data/snapshots/2026-09-20/bible.json) contains all
291 visible artifact records. The pinned pygodfield client independently
captured the current 296-model API catalog, including five trade models, in
[the API catalog snapshot](data/snapshots/2026-09-09/api-catalog-en.json).

## Working principles

- Use the exact-pinned pygodfield client for private live-game transport and
  the dedicated browser profile for identity bootstrap, official Training,
  and visible-client contract checks.
- Keep authentication state, screenshots containing private information,
  model checkpoints, and run databases out of Git.
- Separate perception, legal action generation, policy inference, execution,
  learning, and operator control so each can be tested independently.
- Record every observation, candidate action, decision, outcome, model
  version, and client fingerprint needed to explain a move.
- Improve between games through a gated train/evaluate/promote workflow; do
  not mutate the deployed policy midway through a match.
- Stop safely when the site changes, state confidence is low, or an action is
  not known to be legal.

## Development

The project uses [uv](https://docs.astral.sh/uv/) for Python and virtual
environment management:

```console
uv sync --group dev
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run playwright install chromium
uv run godfield-bot doctor
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot data refresh
uv run godfield-bot data diff data/snapshots/<accepted>/bible.json runs/current-bible.json
uv run pytest
```

Account creation is intentionally gated. It writes the anonymous login session
to a dedicated owner-only browser profile outside the repository and requires
the explicit `--confirm-create` flag:

```console
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot account status
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot account create --confirm-create
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot account enable-api --confirm-enable
uv run godfield-bot api verify
uv run godfield-bot data refresh-api-catalog
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot observe
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot run --max-seconds 90 \
  --screenshot-directory runs/screenshots
uv run godfield-bot state parse runs/observations/game-spatial.json
uv run godfield-bot runs init
uv run godfield-bot runs list
uv run godfield-bot runs events <run-id> --include-payload
uv run godfield-bot runs record-probe <observation.json> --client-sha256 <sha256>
uv run godfield-bot runs export-replay runs/replay.jsonl
uv run godfield-bot runs export-outcomes runs/outcomes.jsonl --model-id <base-model-id>
uv run godfield-bot models init
uv run godfield-bot models train-replay models/<base-model-id> runs/replay.jsonl
uv run godfield-bot models train-outcomes models/<base-model-id> runs/outcomes.jsonl
uv run godfield-bot models train-simulation models/<base-model-id> \
  --ruleset mixed-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<candidate-model-id> \
  --ruleset mixed-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset mixed-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-element-features models/<schema-v2-model-id>
uv run godfield-bot models train-simulation models/<migrated-model-id> \
  --ruleset elemental-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot simulation benchmark --ruleset elemental-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-resource-features models/<schema-v4-model-id>
uv run godfield-bot models train-simulation models/<schema-v5-model-id> \
  --ruleset resource-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<resource-candidate-id> \
  --ruleset resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-stochastic-resource-features \
  models/<schema-v5-model-id>
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset stochastic-resource-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<stochastic-candidate-id> \
  --ruleset stochastic-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset stochastic-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset expanded-resource-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<expanded-candidate-id> \
  --ruleset expanded-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset expanded-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset reflection-resource-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<reflection-candidate-id> \
  --ruleset reflection-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset reflection-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset reflection-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<reflection-weapon-candidate-id> \
  --ruleset reflection-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset reflection-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset dual-role-resource-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<dual-role-candidate-id> \
  --ruleset dual-role-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset dual-role-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset chance-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<chance-weapon-candidate-id> \
  --ruleset chance-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset chance-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset absorption-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<absorption-weapon-candidate-id> \
  --ruleset absorption-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset absorption-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset dynamic-mp-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<dynamic-mp-candidate-id> \
  --ruleset dynamic-mp-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset dynamic-mp-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset same-damage-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<same-damage-candidate-id> \
  --ruleset same-damage-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset same-damage-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset attack-twice-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<attack-twice-candidate-id> \
  --ruleset attack-twice-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset attack-twice-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v6-model-id> \
  --ruleset random-target-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<random-target-candidate-id> \
  --ruleset random-target-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset random-target-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-illness-features models/<schema-v6-model-id>
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset illness-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<illness-candidate-id> \
  --ruleset illness-weapon-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset illness-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset illness-cure-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<illness-cure-candidate-id> \
  --ruleset illness-cure-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset illness-cure-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset heaven-herb-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<heaven-herb-candidate-id> \
  --ruleset heaven-herb-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset heaven-herb-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset fever-mask-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<fever-mask-candidate-id> \
  --ruleset fever-mask-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset fever-mask-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset miracle-block-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<miracle-block-candidate-id> \
  --ruleset miracle-block-resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset miracle-block-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset miracle-block-weapon-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<miracle-block-weapon-candidate-id> \
  --ruleset miracle-block-weapon-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset miracle-block-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset miracle-bounce-resource-hand --batch-size 256 --rollout-steps 32 \
  --updates 10
uv run godfield-bot models evaluate-simulation models/<miracle-bounce-candidate-id> \
  --ruleset miracle-bounce-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset miracle-bounce-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset miracle-bounce-weapon-resource-hand --batch-size 256 \
  --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation \
  models/<miracle-bounce-weapon-candidate-id> \
  --ruleset miracle-bounce-weapon-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset miracle-bounce-weapon-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset miracle-bounce-miracle-resource-hand --batch-size 256 \
  --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation \
  models/<miracle-bounce-miracle-candidate-id> \
  --ruleset miracle-bounce-miracle-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset miracle-bounce-miracle-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models train-simulation models/<schema-v7-model-id> \
  --ruleset miracle-reflection-resource-hand --batch-size 256 \
  --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation \
  models/<miracle-reflection-candidate-id> \
  --ruleset miracle-reflection-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset miracle-reflection-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-curse-features models/<schema-v7-model-id>
uv run godfield-bot models train-simulation models/<schema-v8-model-id> \
  --ruleset fog-flash-resource-hand --batch-size 256 \
  --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation \
  models/<fog-flash-candidate-id> \
  --ruleset fog-flash-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset fog-flash-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-dark-cloud-features models/<schema-v8-model-id>
uv run godfield-bot models train-simulation models/<schema-v9-model-id> \
  --ruleset dark-cloud-resource-hand --batch-size 256 \
  --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation \
  models/<dark-cloud-candidate-id> \
  --ruleset dark-cloud-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset dark-cloud-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
uv run godfield-bot models migrate-dream-features models/<schema-v9-model-id>
uv run godfield-bot models train-simulation models/<schema-v10-model-id> \
  --ruleset dream-resource-hand --batch-size 512 \
  --rollout-steps 32 --updates 40 --ppo-epochs 2 \
  --environment-minibatch-size 128 --teacher-updates 128 \
  --teacher-epochs 2 --heuristic-opponent-fraction 1.0
uv run godfield-bot models evaluate-simulation \
  models/<dream-candidate-id> \
  --ruleset dream-resource-hand --games-per-seat 512 \
  --minimum-score 0.5 --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark \
  --ruleset dream-resource-attack-defense \
  --batch-size 4096 --batch-steps 1000
```

`api observe-private --password-stdin` uses God Field's keyed private-room
matchmaking, then records bounded state without playing cards. An owner-only
(`0600`) `--password-file` can be used for unattended runs. An internal room ID
may instead be supplied with `--room-id`. Matchmaking keys are never accepted
as ordinary CLI values or stored in the run database. The observer always stays
a spectator. `api play-private --confirm-play --password-stdin` explicitly
enters the next match with the bounded tactical API policy. For an
unlimited wall-clock session that remains available for subsequent matches,
pass `--max-seconds 0`; the independent no-progress and action-count safeguards
remain active. Transient room-state reads are retried five times with bounded
exponential backoff by default; `--state-read-retries` and
`--state-read-retry-seconds` tune that read-only recovery budget. Submitted
game actions with an ambiguous network outcome are never retried. Instead, the
runtime keeps reading room state for up to 30 seconds and continues the session
once a changed state reconciles the uncertain action. `--command-reconcile-seconds`
tunes that bound. A definite HTTP 400 rejection is different: the runtime first
obtains a fresh room read, retries only if the normalized state is unchanged,
and stops after two retries by default. `--command-retries` tunes that bounded
rejection-recovery budget, and every uncertain or rejected attempt and observed
transition is stored locally.
The runtime also verifies that ロキ-67 remains in the room's live membership
list before processing each game snapshot. If membership disappears, it mirrors
the official client's recovery path by requesting `join-room` once and waiting
for a confirming snapshot before resuming policy actions. A temporary HTTP 403
while entering the next match after a completed game is retried with bounded
backoff; the normal no-progress safeguard still terminates a persistent fault.
Use `--team 0` for solo/free-for-all entry, or `--team 1` through `--team 4`
for allied teams A through D. The selected team is retained across automatic
entry into subsequent matches. Active curse presence is recorded in the
normalized API state. `api-combo-utility-heuristic-v6` uses strict
base-plus-booster attacks, compatible multi-armor defenses, affordable
targeted fixed-damage, `<Absorption>`, and curse miracles, special
block/bounce/reflect defenses admitted by the API, Bible-verified untargeted
chance miracles, and deterministic HP/MP recovery. It takes an attack with
potentially lethal power before healing and otherwise restores HP at 25 or
less. Chance miracles are a late fallback after deterministic attacks and
HP/MP utility. The Bible-verified `<Treasure>` CP miracle is a final
reliable-card fallback before Sell.
On a cursed turn, it prefers a verified all-curse cleanser, then a mild-curse
cleanser, and otherwise uses only individually reliable, undisguised actions.
The Bible-audited Thump-thump Tear HP-or-damage effect is a last-resort turn
leader, after reliable CP utility and before Sell, covering a dead end observed
under Dream. When no attack or recovery is available, Sell can offer the weakest
verified plain armor to an opponent. If no supported action remains, it abstains
locally rather than submit an empty turn command, which the live service rejects
in this state.
An empty attack-turn command is never offered while the displayed hand contains
a weapon, including a `+ATK` weapon that cannot lead the attack by itself.

Pass `--shadow-model models/<candidate-id>` to `api play-private` to run either
the schema-v4 combo network or schema-v5 resource network on each covered
two-player state without giving it live control. Schema v5 additionally maps
HP/MP recovery, Spring's MP cost, and fixed-attack miracles onto the exact
atomic-or-Confirm semantics used by the native curriculum. The tactical
heuristic still submits every command. The run records the candidate's proposed
card sequence, probabilities, value estimates, model checksum, behavior
decision, accepted transition, and terminal reward:

```console
uv run godfield-bot api play-private --confirm-play --password-stdin \
  --shadow-model models/d349d664-bfce-4997-9ff9-eb94482c20d1 \
  --max-seconds 0
```

Shadow inference accepts only candidate or champion models tied to the accepted
Bible client and the exact schema-matched combo or resource curriculum. It
abstains on multiplayer, cursed, unknown-phase, identity-drifted, or
out-of-curriculum states and clears counterfactual recurrent memory whenever the
tactical behavior differs from its proposal. Schema-v5 proposals use
`api-resource-neural-shadow-v2` and remain non-executable even though the
candidate passed its native gate. See
[ADR 0010](docs/architecture/0010-live-neural-shadow.md),
[ADR 0013](docs/architecture/0013-resource-miracle-curriculum.md), and
[ADR 0014](docs/architecture/0014-live-resource-neural-shadow.md).

After collecting schema-v5 shadow games, run the versioned live evidence gate
against the same immutable candidate and its passing native report:

```console
uv run godfield-bot models evaluate-live-shadow \
  models/d349d664-bfce-4997-9ff9-eb94482c20d1 \
  --native-evaluation \
  models/evaluations/74c09a6c-e682-46b9-88e4-79032677ce62.json
```

`live-resource-shadow-readiness-v6` accepts only runs that carry the exact v6
behavior identity, schema-v5 shadow adapter, model, and weight checksum. Whole
runs containing any non-two-player game are excluded because the candidate
abstains outside its two-player curriculum. It validates state/legal-action/
decision pairing and terminal rewards, then gates
on completed games, attack and defense opportunities, all four resource action
families, proposal coverage, behavior agreement, and operational failures.
Proportions use Wilson lower confidence bounds. The resulting owner-only report
can mark a candidate ready for a separately authorized controlled trial, but its
`promotion_eligible` field remains false: outcomes from heuristic-controlled
shadow games are not candidate performance. See
[ADR 0015](docs/architecture/0015-live-shadow-readiness-gate.md).

With `--max-seconds 0`, transient room-read failures continue retrying with a
capped delay. An unresolved command response is never replayed; after the
reconciliation window the runner leaves that match, rejoins the same private
room, and continues. The same recovery applies to a truly unsupported self turn,
an in-match no-progress limit, or the per-match action limit. Lobby waiting does
not trigger no-progress recovery, and the action counter resets for each match.
Finite sessions retain bounded fail-closed exits for diagnosis.

God Field's official Training computer runs inside the web client rather than
the server-side API. `play-training` therefore drives the official browser in
headless mode by default while keeping policy inference, evidence storage, and
campaign control in Python. It preserves one append-only run per game so every
terminal reward remains a valid replay episode. `--max-games 0` continues
through completed games and stops on the first gameplay abort or failure,
making the first unsupported state easy to inspect. Transient pre-game room
failures are retried three times by default; use `--max-setup-retries` to
change that bounded allowance. A single `unknown` gameplay capture is treated
as a transient render for 15 seconds rather than immediate terminal evidence;
`--unknown-screen-grace-seconds` tunes that bounded recovery window. Each
distinct unknown frame is recorded and screenshotted when screenshot capture
is enabled:

```console
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot play-training \
  --headless \
  --max-games 0 \
  --max-seconds 0 \
  --max-actions 300 \
  --no-progress-seconds 60 \
  --unknown-screen-grace-seconds 15 \
  --max-setup-retries 3 \
  --max-gameplay-retries 3
```

A game whose official client exposes no progress for the configured interval is
stored as an aborted, training-ineligible episode. The campaign starts a clean
Training game and tolerates three consecutive frozen games by default; a
completed game resets that retry streak. The default browser-click budget is
300 because a verified progressing official game exceeded the former 100-click
ceiling; the independent no-progress timer remains the deadlock guard.

Dream remains outside live browser-neural control, but schema-v10 candidates
can now run as passive shadows behind the live heuristic. The bridge parses
visible illness and curse icons, uses only reviewed browser actions, and stores
the candidate's proposal without allowing it to click. It abstains when player
statistics are hidden, a selectable card lies beyond the nine-slot input, or
the current response cannot be represented exactly:

```console
uv run --extra training godfield-bot play-training \
  --shadow-model models/df08842c-f5e8-4317-8721-0245310c92ac \
  --headless \
  --max-games 0 \
  --max-seconds 0 \
  --max-actions 300
uv run godfield-bot runs training-shadow <run-id> [<run-id> ...]
```

The recurrent shadow state advances only when the proposal agrees with the
action the heuristic actually executed; disagreement or an unrepresentable
state resets it. To evaluate existing raw Training observations without writing
to the trajectory database:

```console
uv run godfield-bot runs evaluate-training-shadow \
  models/df08842c-f5e8-4317-8721-0245310c92ac \
  <run-id> [<run-id> ...]
```

Coverage and agreement are diagnostics, not win-rate evidence and not
authorization for neural control. Once a prospective cohort is available, bind
it to the candidate's immutable native reports and audit the adapter boundary:

```console
uv run godfield-bot models evaluate-training-shadow-readiness \
  models/df08842c-f5e8-4317-8721-0245310c92ac
```

The v2 readiness report separates deliberate hidden-Fog abstentions from actual
exact-view encoding gaps, validates every event group and terminal outcome, and
requires a 98% Wilson lower bound on exact-view coverage across Dream and other
represented statuses plus every browser action family. Encoding failures remain
fail-closed and heuristic-controlled; their rate, rather than a non-monotonic
absolute count, governs admission. A passing report permits design of a
separately authorized guarded intervention; it is not deployment or promotion
approval.
See [ADR 0052](docs/architecture/0052-official-training-schema-v10-shadow.md),
[ADR 0053](docs/architecture/0053-official-training-shadow-readiness.md), and
[ADR 0056](docs/architecture/0056-monotonic-training-shadow-coverage.md).

The guarded canary is now available as a separate, explicit mode. It admits only
the exact schema-v10 weights named by a passing readiness report. The candidate
may replace the heuristic on at most one exact-view disagreement in a game, and
only when its proposal probability is at least `0.75` and its lead over the
heuristic action is at least `0.25`. The heuristic controls the rest of the game:

```console
uv run --extra training godfield-bot play-training \
  --canary-model models/df08842c-f5e8-4317-8721-0245310c92ac \
  --canary-readiness-report \
    models/training-shadow-evaluations/da85614f-695e-4045-93c6-b5839741d6d0.json \
  --confirm-canary-intervention \
  --headless \
  --max-games 1 \
  --max-gameplay-retries 0 \
  --max-seconds 0 \
  --max-actions 300
```

Start with one game and audit its `official_training_canary` evidence before
increasing `--max-games`. These mixed-policy runs intentionally have no run-level
`model_id`, so candidate-filtered outcome export cannot treat them as fully
neural-controlled games. Canary gameplay aborts are never retried automatically,
even if the general campaign retry allowance is nonzero, because a retry would
refresh the one-intervention budget. See
[ADR 0054](docs/architecture/0054-official-training-one-intervention-canary.md).

A stronger PPO-continuation candidate is now awaiting prospective shadow
evidence. It passed three independent native gates, including a 4,096-game
check, but prior shadow runs cannot be reused because the readiness contract is
bound to the exact model and weight digest. Collect a fresh continuous cohort
while the heuristic retains every browser click:

```console
UV_CACHE_DIR=.uv-cache uv run --extra training godfield-bot play-training \
  --shadow-model models/088ef7a5-c8bf-46e2-8469-4d2390719839 \
  --headless \
  --max-games 0 \
  --max-seconds 0 \
  --max-actions 300
```

Then rerun `models evaluate-training-shadow-readiness` for that candidate.
Until it passes, continue using the earlier candidate and readiness report for
any explicitly authorized canary. See
[ADR 0055](docs/architecture/0055-schema-v10-ppo-continuation.md).

The evidence-bounded native schema-v10 curriculum uses a strict
displayed-identity observation boundary. Enable the passive Dream evidence
sidecar while running the existing live heuristic to record only ロキ-67's
true/displayed model IDs, the
current phase, displayed image, and whether each displayed card is selectable:

```console
uv run godfield-bot play-training \
  --headless \
  --max-games 0 \
  --max-seconds 0 \
  --dream-evidence-probe
uv run godfield-bot runs dream-evidence <run-id>
```

The sidecar is installed before the official client starts, stores no account,
room, token, or opponent-hand identifiers, and is read only after the policy
has decided. It records one non-Dream health sample per game and then only
Dream/disguise samples. Raw client hand order is joined to visual slots by the
displayed asset; duplicate displayed assets are explicitly ambiguous rather
than paired by guesswork. The evidence never enters `GameState`, legal-action
generation, or policy inference. See
[ADR 0050](docs/architecture/0050-dream-evidence-probe.md).

To collect candidate-controlled games against the official computer, install
the learning dependency and explicitly authorize one immutable schema-v4/v5
candidate. The model can choose only among the same reviewed browser actions;
unsupported observations fall back to the heuristic:

```console
uv sync --extra training --group dev
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot play-training \
  --neural-model models/d349d664-bfce-4997-9ff9-eb94482c20d1 \
  --confirm-neural-control \
  --max-games 20 \
  --max-actions 300
uv run godfield-bot runs export-outcomes runs/official-d349d664.jsonl \
  --model-id d349d664-bfce-4997-9ff9-eb94482c20d1
uv run godfield-bot models train-outcomes \
  models/d349d664-bfce-4997-9ff9-eb94482c20d1 \
  runs/official-d349d664.jsonl
```

The final command creates a child candidate; it does not replace the model or
promote it. Outcome training requires at least 20 completed games, including
two wins and two losses, by default. It performs a clipped full-batch update
anchored to the frozen parent, then rejects the update if policy or parameter
drift crosses its trust-region limit. Evaluate the child on the matching native
ruleset before another official batch. See
[ADR 0026](docs/architecture/0026-official-training-learning-loop.md).
Temporary hands larger than the nine-slot model input are truncated only when
no overflow card is selectable; selectable overflow states still use the safe
heuristic fallback. The child manifest reports skipped decision counts grouped
by encoding reason so lost training coverage remains visible.

Official Training recognizes both direct and nested Dream overlays. A nested
card is executable only when the observer and click path find exactly one
rendered pointer target with the same bounds; ambiguous matches fail closed.
The client-only `/images/items/fake.webp` Dream mask is not an artifact identity
and is excluded consistently from both observed and click-time action-panel
asset sets.
If a displayed weapon still blocks Prayer, no reviewed artifact is clickable,
and the client exposes exactly one verified Exchange control, the heuristic
redraws the hand. Neural control resets its recurrent state across that
fallback, so the outcome trainer does not attribute the unmodeled trade
decision to the candidate. Buy remains unsupported because it has target and
purchase-response phases. See
[ADR 0027](docs/architecture/0027-official-training-exchange-liveness.md).

Use `--headed` to watch the official client. Each game is stored separately in
`runs/godfield.sqlite`; a campaign summary reports its run IDs and aggregate
wins, losses, and draws. See
[ADR 0012](docs/architecture/0012-official-training-campaign.md).

Install the optional learning stack with `uv sync --extra training --group dev`.
Install the native C++ curriculum simulator with
`uv sync --extra simulation --extra training --group dev`. Its batch-first
interface and strict fidelity boundary are documented in
[ADR 0002](docs/architecture/0002-native-simulator.md).
`models init` creates a checksum-protected, ignored model directory whose
manifest is tied to the current Bible client hash and artifact vocabulary. Its
status is `initialized` and cannot control the browser. A compatible candidate
can control only the official Training computer after the operator supplies
both `--neural-model` and `--confirm-neural-control`; broader live use retains
its separate evaluation and promotion gates.

`run` defaults to an observation-only Training policy. It is headed by default,
checks the live client bundle against the accepted snapshot, permits one
Training game, and records only changed states. Its room wait, gameplay
duration, no-progress interval, and in-match click count are independently
bounded. If gameplay leaves the known screen, the runner records a terminal
candidate instead of guessing whether the match was won or lost. Only an
explicit two-player Training state with at least one player at zero HP is
classified as complete. It emits exactly one outcome-only reward: win `+1`,
loss `-1`, or draw `0`. Intermediate HP, resource, and field deltas remain
diagnostics and never become shaped rewards.

The default `safe-observer-v0` remains observation-only. The explicitly chosen
`heuristic-v0` path can select the highest-expected-damage Bible-verified
weapon and confirm it against an already named sole opponent. The
browser allowlist contains 80 exact-display attacks: 63 fixed attacks across
all seven elements and 17 probabilistic attacks whose chance roll requires no
player choice. Chance attacks use a separately validated untargeted resolution
step before any named-target confirmation. Six fixed-damage, single-element
miracles are also available when their exact MP cost is affordable. Empty
Prayer is allowed only when the hand contains no weapon, matching the live
client's rejection rule. Bible-audited unconditional HP and MP sundries are
also available through separate selection and confirmation actions. Utility
confirmation requires the exact actor, accepted card asset, `HP+N` or `MP+N`
effect label, empty target, and left-panel hit target. The heuristic takes a
lethal attack before healing, otherwise restores HP at 25 or less, and uses MP
recovery as a fallback when no attack or HP recovery is currently usable. This
prevents a disabled or Dream-masked weapon from deadlocking a turn when an
independently verified utility remains clickable. Additive boosters, multi-hit,
resource-consuming, state-dependent, and self-damaging weapons remain excluded.
The browser bridge also recognizes the exact two-card panel produced when one
audited fixed attack and one deterministic HP/MP utility resolve together. It
requires both card assets, the utility's card-local effect label, the aggregate
attack display, the actor, and the sole named target to match again at click
time; larger or unknown combinations remain blocked.
It can also Forgive a targeted incoming interaction or mirrored reflected
attack after revalidating every visible context artifact and panel identity,
and select plain armor during a verified neutral defense before confirming
that armor in its response panel. Every browser
interaction counts against `--max-actions`; unknown,
elemental-defense, multi-target, discard, and other phases remain blocked.

God Field returns to its Prophet Name screen when the browser restarts. The
`observe` command re-enters Genesis as `ロキ-67`, verifies a one-way fingerprint
of the same persisted anonymous Firebase identity, and stops at the menu. It
never prints tokens, profile contents, or the underlying account identifier.
Saved observations include bounding boxes for visible text, controls, and image
assets. `state parse` converts a gameplay observation into a typed policy-facing
state containing players, resources, field number, hand slots, and scene layers.
The ignored SQLite store is append-only while a run is active and records
ordered typed events plus client, policy, and model lineage. Finished runs
reject additional events so training data cannot silently change afterward.
Executable runs also record whether each dispatched click changed normalized
state, plus field and player-HP deltas; inert clicks terminate the run and are
not silently treated as accepted transitions.
`runs export-replay` atomically creates an owner-only JSONL dataset containing
only fully evidenced, dispatched actions that changed normalized state. Each
sample preserves the before and after states, legal action set, chosen action,
policy decision, execution result, client fingerprint, and raw transition
deltas. Rewards are deliberately not inferred from those deltas during export.
`runs export-outcomes` is stricter: it includes only completed episodes with
one atomically recorded terminal outcome/reward pair, a matching terminal
state, and complete accepted-action evidence. Aborted, failed, partial, and
unclassified runs cannot enter this reward-labeled dataset.

`models train-replay` performs behavior cloning over each run as a recurrent
sequence and writes a new immutable candidate rather than modifying its base
model. The manifest records the parent model, replay checksum, client and
vocabulary fingerprints, contributing run IDs, and before/after imitation
metrics. A replay-trained model remains a candidate: this command does not
evaluate, promote, or allow it to control the browser, and it does not train
the value head from invented returns.

`models train-outcomes` accepts only the stricter outcome-replay-v2 dataset from
official Training games controlled by the exact base model. The proximal-v2
trainer uses the undiscounted sparse terminal result as the value target and a
normalized advantage relative to the frozen behavior policy. Action probability
ratios and value changes are clipped, while KL and global parameter drift are
measured against that parent. Small or one-sided datasets are refused by
default, and an update beyond either drift ceiling is not saved. Hidden-stat
heuristic fallback steps are excluded at their neural memory-reset boundary.
The command writes another immutable candidate with before/after policy-value
and drift metrics and inherited simulator provenance; it never changes a
running policy or promotes the child automatically. See
[ADR 0028](docs/architecture/0028-proximal-official-outcome-training.md).

Training and operator-owned private rooms are the only approved early play
scope. Public Duel and automated chat are disabled. The live private adapter is
documented in [ADR 0003](docs/architecture/0003-pygodfield-live-api.md). API
matches require another participant or separately authorized host account,
because Training gameplay exists only inside the browser client. Learning will
be simulator-first with real-game fine-tuning.

The native simulator provides a sequence of fast, versioned curricula. The original
`plain-attack-redraw-duel-v1` ruleset isolates effect-free neutral attacks. The
default `plain-attack-defense-redraw-duel-v1` benchmark adds a separate defense
decision: five weapon slots and four armor slots redraw within their own
categories, defense may pass or consume one neutral plain armor card, and
damage is `max(ATK - DEF, 0)`. Phase, pending ATK, and card role are explicit
native views. Observation schema v2 appends the response-phase flag and pending
ATK to the original four globals. Existing four-feature checkpoints are
deliberately incompatible. `models init` creates a manifest-schema-v3,
slot-aware policy with the current 13-value feature schema. Six-value
feature-schema-v2 checkpoints remain readable for historical fixed-role and
mixed-hand evaluation, and can be explicitly migrated for elemental training.
The separately versioned mixed-hand ruleset starts each player with
the same five-weapon/four-armor composition in shuffled slots, then redraws
consumed cards uniformly across both catalogs. Legal actions follow each
card's current role, and the kernel guarantees that every attack phase retains
at least one weapon. This removes the fixed-slot shortcut without changing the
model interface. The elemental mixed-hand ruleset expands the strict catalog to
39 single-card weapons and 47 armor cards and enforces opposite-element
defenses, Light armor substitution, unblockable Light attacks, and Darkness
lethality only when damage penetrates defense. Observation schema v3 adds a
seven-way pending-element signal. A recorded model migration preserves the six
old global inputs and zero-initializes the new columns before elemental
training. All rulesets are fingerprinted against the accepted client,
artifact vocabulary, and exact rule catalog, and none is promotion-eligible.
The cumulative ruleset line now reaches `dream-resource-hand`. Its
`illness-weapon-resource-hand` foundation builds on schema-v7
stochastic combat, additive miracles, Super Mirror, and Reflection Sword, then
adds seven Bible-exact and API-verified ATK/DEF weapons, 14 effect-free chance weapons,
Jinn's Rocking Horse with `75%ATK8`/`DEF6`, and the three evidenced HP-absorbing
weapons. It also adds Magical Stick with a current-MP-dependent attack and
all-MP consumption, Evil Broadsword's post-defense same-damage effect, and Saw
Boom Boom's two separately defended ATK3 strikes. It also models Dangerous
Pestle as a uniformly random ATK30 against either living duel player: an
opponent target receives a normal response, while a self-target resolves
immediately and can self-KO. It further adds the four exact Cold/Hell weapons;
status is applied only when damage penetrates defense, damages or heals at the
end of the ill player's turn, and has a 5% chance to worsen. Schema v7 adds two
actor-relative illness-stage inputs, with an explicit zero-column migration
from schema v6. Absorption heals only damage that penetrates
defense; a reflected absorbing attack heals the reflector. Chance attacks
sample once on confirmation, numeric defense remains deterministic, and the
reflected response remains one-hop bounded. The unevidenced Evil
Broadsword/reflection interaction is masked. Unevidenced Saw Boom Boom booster
and reflection composition is also masked. Dangerous Pestle booster and
reflection composition is likewise masked. Later increments add verified
illness cures, Heaven Herb, Fever Mask, the Angel miracle-block armor and
weapon families, five Sky armor cards, Sky Harpoon, and `<Turbulence>`. These
cards bounce attack miracles to a uniformly sampled living duel player. Sky
Harpoon is also a consumable +ATK9 weapon booster; `<Turbulence>` is a reusable
miracle costing 5 MP. Redirects receive a fresh defense and are one-hop
bounded. The latest increment adds Moonlight Helm, Shield, and Armor with
neutral DEF8/10/12 and Moonlight Axe as a consumable ATK10 base weapon. All
four reflect attack miracles specifically to the original caster; Moonlight
armor retains its printed defense against ordinary weapons, while Moonlight
Axe cannot defend them. Reflection and bounce share the one-hop redirect
guard. The latest increment adds Fog Gun, Fog Fan, Flash Dagger, `<Flash>`,
and `<Fog>`. Fog hides the opponent's HP/MP from a fogged actor, Flash limits
defense to one artifact, and damage-triggered curses apply only after a
penetrating hit. Direct Fog is a reusable 3-MP miracle answered by the existing
Angel, Sky, and Moonlight miracle defenses rather than ordinary armor. Mild
and full cures remove Fog and Flash. Schema v8 adds four actor-relative
Fog/Flash inputs with an explicit zero-column migration from schema v7. The
newest increment adds Hexagon Doom and `<Dark Cloud>`. Damage from Hexagon Doom
inflicts Dark Cloud, while the reusable direct miracle costs 5 MP. Percentage
attacks aimed at a clouded player hit certainly, and mild or full cures remove
the status. Schema v9 adds actor-relative Dark Cloud inputs with an explicit
zero-column migration from schema v8. The newest increment adds Bogus Spear,
Dream Mallet, and `<Dream>`. Positive weapon damage and the reusable 6-MP
miracle inflict Dream. Newly received ordinary weapons and armor are disguised
independently at 50%; policy observations and legal masks use only displayed
identity/value/element while resolution retains the hidden true card. Schema
v10 adds actor-relative Dream inputs through another zero-column migration. The
evidence-bounded cumulative catalog contains 196 cards. Special-card disguise
semantics, Dreaming Hat, Jupiter Ring, and guardians remain excluded. The
catalog and sampling distribution are independently fingerprinted. See
[ADR 0029](docs/architecture/0029-additive-miracle-curriculum.md),
[ADR 0030](docs/architecture/0030-evidenced-super-mirror-curriculum.md),
[ADR 0031](docs/architecture/0031-evidenced-reflection-sword-curriculum.md),
[ADR 0032](docs/architecture/0032-dual-role-weapon-curriculum.md),
[ADR 0033](docs/architecture/0033-chance-weapon-curriculum.md),
[ADR 0034](docs/architecture/0034-absorption-weapon-curriculum.md),
[ADR 0035](docs/architecture/0035-dynamic-mp-weapon-curriculum.md),
[ADR 0036](docs/architecture/0036-same-damage-weapon-curriculum.md),
[ADR 0037](docs/architecture/0037-attack-twice-weapon-curriculum.md),
[ADR 0038](docs/architecture/0038-random-target-weapon-curriculum.md),
[ADR 0039](docs/architecture/0039-illness-weapon-curriculum.md),
[ADR 0045](docs/architecture/0045-miracle-bounce-curriculum.md),
[ADR 0046](docs/architecture/0046-miracle-bounce-weapon-miracle-curriculum.md),
[ADR 0047](docs/architecture/0047-miracle-reflection-curriculum.md),
[ADR 0048](docs/architecture/0048-fog-flash-curriculum.md),
[ADR 0049](docs/architecture/0049-dark-cloud-curriculum.md), and
[ADR 0051](docs/architecture/0051-dream-curriculum.md).

`models train-simulation` creates a bounded
`heuristic-warmstart-recurrent-ppo-self-play-v1` candidate. The slot-aware
artifact scorer binds each visible card embedding to its corresponding action
logit. Before PPO, recurrent behavior cloning teaches the versioned
max-attack/conservative-defense policy. PPO then mixes self-play with games
where one alternating seat is controlled by that frozen heuristic; policy
loss excludes frozen actions while the value function still learns from the
complete trajectory. `--teacher-updates` and
`--heuristic-opponent-fraction` control the mix. Zero-sum GAE flips the
bootstrapped perspective when control passes to the opponent and preserves it
when a defender begins their next attack. Structured logs expose teacher
accuracy, losses, entropy, approximate KL, gradient norm, completed episodes,
armor-selection rate, and the actual fraction of frozen-opponent actions. The
candidate manifest retains the complete optimizer configuration and simulator
fingerprints. Native training never promotes a model; see
[ADR 0006](docs/architecture/0006-slot-aware-curriculum-training.md).

`models evaluate-simulation` runs deterministic argmax play against both the
candidate's frozen parent and a versioned max-attack/conservative-defense
heuristic. Every initial deal is evaluated twice with candidate and opponent
seats swapped. The gate requires every game to finish within its decision
horizon. Its paired lower confidence bound must strictly exceed
`--minimum-score` against the parent and remain within
`--heuristic-noninferiority-margin` of that score against the heuristic. The
aggregate Wilson bound remains diagnostic only. It writes an owner-only report
containing model, simulator, configuration, pairing, and confidence evidence. A passing
report is curriculum evidence only: its `promotion_eligible` field is always
false and it does not change any model manifest or authorize live play. See
[ADR 0005](docs/architecture/0005-paired-curriculum-evaluation.md).

For local training against several historical policies, freeze a league once.
These commands reproduce the first league experiment:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models create-simulation-league \
  models/dd5bde4f-c5d5-44f2-b1db-4b4f1d049f56 \
  --opponent-model models/3dfe4a94-4bc3-4d90-9691-853a7b543cd4 \
  --opponent-model models/088ef7a5-c8bf-46e2-8469-4d2390719839 \
  --opponent-model models/df08842c-f5e8-4317-8721-0245310c92ac \
  --heuristic-weight 2
```

The result prints `league_path`. Use that exact file for both training and
evaluation:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot --json-logs models train-simulation \
  models/dd5bde4f-c5d5-44f2-b1db-4b4f1d049f56 \
  --league models/leagues/<league-id>.json --ruleset dream-resource-hand \
  --batch-size 512 --rollout-steps 64 --updates 160 \
  --ppo-epochs 2 --environment-minibatch-size 128 --teacher-updates 0 \
  --learning-rate 0.0001 --entropy-weight 0.02 --seed 36067 --device cpu

UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models evaluate-simulation-league models/<candidate-id> \
  --league models/leagues/<league-id>.json \
  --games-per-seat 8192 --seed 37067 --device cpu
```

League mode replaces `--heuristic-opponent-fraction`: every game has one learner
seat and one frozen opponent, sampled by roster weights for the entire episode.
Each model has weight 1; the heuristic's weight is configurable when creating
the roster. Frozen models use deterministic argmax actions with their own
recurrent memory. The learner's starting seats alternate by environment and
swap when each episode completes. Opponent identities, checkpoint hashes,
simulator fingerprints, sampling weights, and actual per-opponent action/game
counts are retained in the candidate manifest and structured logs.

`models evaluate-simulation-league` requires the paired lower confidence bound
to strictly exceed 50% against **every** member, including the heuristic, with
no incomplete games. It uses equal evaluation budgets for all opponents,
regardless of training weights. Changed weights, missing parents, different
simulator contracts, or substituting a different training roster are rejected.
Reports go to `models/league-evaluations/` and remain local curriculum evidence.
Passing cannot establish strength under official rules absent from the C++
simulator. See [ADR 0057](docs/architecture/0057-local-frozen-opponent-league.md).

The resulting local baseline is `63de1747-f43f-4ef1-ae99-a1cd72dd3ec1`. It
passed every member on three independent 8,192-pair evaluations (245,760 games,
zero incomplete). Its heuristic score was 57.22–57.71% and its parent score was
50.80–50.98%. To continue from this baseline, create a **new** league with it
as the base model, then pass that new roster to training and evaluation.

For a more realistic common/rare card mix, use the separate
`gift-weighted-dream-resource-hand` curriculum. It uses accepted Bible gift
numerators within the supported 196-card pool, including initial role pools
and redraws. It preserves schema 10, so existing Dream checkpoints can initialize
training, but requires a **new weighted league**. Existing uniform-mode reports
and league snapshots remain unchanged and cannot be mixed with weighted ones.

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models create-simulation-league \
  models/63de1747-f43f-4ef1-ae99-a1cd72dd3ec1 \
  --opponent-model models/dd5bde4f-c5d5-44f2-b1db-4b4f1d049f56 \
  --ruleset gift-weighted-dream-resource-hand --heuristic-weight 2

UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models train-simulation \
  models/63de1747-f43f-4ef1-ae99-a1cd72dd3ec1 \
  --league models/leagues/<weighted-league-id>.json \
  --ruleset gift-weighted-dream-resource-hand \
  --batch-size 512 --rollout-steps 64 --updates 160 \
  --ppo-epochs 2 --environment-minibatch-size 128 --teacher-updates 0 \
  --learning-rate 0.0001 --entropy-weight 0.02 --seed 38067 --device cpu

UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models evaluate-simulation-league models/<weighted-candidate-id> \
  --league models/leagues/<weighted-league-id>.json \
  --games-per-seat 8192 --seed 39067 --device cpu
```

Native throughput can be checked with `simulation benchmark --ruleset
gift-weighted-dream-resource-attack-defense`. Gift weighting is still conditional
on supported cards, fixed initial role counts, and the mandatory weapon liveness
rule. Nine-slot hands, missing official mechanics, and Dream disguise sampling
are unchanged. Passing this local gate does not authorize live neural control.
See [ADR 0058](docs/architecture/0058-gift-weighted-dream-curriculum.md).

The weighted-mode local baseline is `f99e35f6-f677-4fa1-a835-4cd586ddb467`.
It passed all six frozen opponents on three independent 8,192-pair evaluations
(294,912 games, zero incomplete). Its curriculum heuristic score was
57.56–58.03%, and its parent score was 50.65–50.73%. Continuing from it requires
another new weighted league with this checkpoint as the base model. These
results do not measure performance against the official bot.

For capacity-stress training with larger hands, explicitly migrate a schema-10
checkpoint and create a new league. Existing nine-slot checkpoints are retained.

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models migrate-hand-capacity \
  models/f99e35f6-f677-4fa1-a835-4cd586ddb467

UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models create-simulation-league models/<migrated-model-id> \
  --ruleset wide-hand-gift-weighted-dream-resource-hand --heuristic-weight 2

UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models train-simulation models/<migrated-model-id> \
  --league models/leagues/<wide-league-id>.json \
  --ruleset wide-hand-gift-weighted-dream-resource-hand \
  --batch-size 512 --rollout-steps 64 --updates 160 \
  --ppo-epochs 2 --environment-minibatch-size 128 --teacher-updates 0 \
  --learning-rate 0.0001 --entropy-weight 0.02 --seed 40067 --device cpu

UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models evaluate-simulation-league models/<wide-candidate-id> \
  --league models/leagues/<wide-league-id>.json \
  --games-per-seat 8192 --seed 41067 --device cpu
```

Schema 11 has 18 padded slots and 30 actions. Each local episode starts with
9–18 occupied cards; the occupied count stays fixed until reset. This teaches
larger-hand selection but does **not** implement the official gift/discard or
hand-growth lifecycle. Migration preserves shared card-scoring weights and
nine-card outputs after action remapping, but inherits no evaluation or live
readiness. Official neural bridges still reject schema 11.
See [ADR 0059](docs/architecture/0059-padded-hand-capacity-curriculum.md).

For longer-game exposure and a broader frozen roster, the next local recipe
uses 512-step rollouts with smaller recurrent minibatches:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot models train-simulation \
  models/07759a38-203e-45cf-ba7a-c87e2d1dbf18 \
  --league models/leagues/da29243f-5bf8-41f1-acdc-162c12c38e8f.json \
  --ruleset wide-hand-gift-weighted-dream-resource-hand \
  --batch-size 256 --rollout-steps 512 --updates 80 \
  --environment-minibatch-size 32 --ppo-epochs 2 --teacher-updates 0 \
  --learning-rate 0.0001 --entropy-weight 0.02 --seed 42067 --device cpu
```

The parent above is an experimental candidate, **not** an accepted or live-ready
baseline. This roster contains the heuristic and seven frozen checkpoints.
Longer rollouts expose later positions; they do not relax the 512-decision gate.
Candidate metrics show the actual fraction of learner decisions beyond 64.

Local failure traces can be reproduced without replaying the whole batch:

```bash
UV_CACHE_DIR=.uv-cache uv run --extra simulation --extra training \
  godfield-bot simulation trace-game \
  models/07759a38-203e-45cf-ba7a-c87e2d1dbf18 \
  --seed 41068 --environment 3442 --candidate-seat 0 --max-decisions 2048
```

This writes a private, action-by-action diagnostic trace, not a gate report.
It can also take `--opponent-model models/<id>` instead of the heuristic.
Evaluation reports now include duration quantiles, the longest completed game,
and bounded `(candidate_seat, environment_index)` incomplete examples. A larger
diagnostic budget never changes the original failed evaluation.
See [ADR 0060](docs/architecture/0060-long-rollout-league-and-tail-diagnostics.md).

`models evaluate-simulation` and `models evaluate-simulation-league` also accept
`--compact-inference` to skip neural inference on already-completed first games.
The mode is recorded in each evaluation's hashed configuration; it changes no
score or completion thresholds. The original inference path remains the
default, and an apparent pass should be confirmed with that path.

The longer-rollout result, `e2555901-6f73-4ff3-9923-aae171b46c76`, now passes
the eight-opponent league on three fresh seeds through both inference paths.
The default-path gates complete all 393,216 first-game evaluations within
512 decisions, with every opponent's paired lower bound above 50%. It is the
verified **local schema-11 training baseline**, not a live-ready model. The
earlier failed candidate and report remain unchanged. Official acquisition and
hand-growth rules are still not simulated; these local results do not establish
strength against the official bot. Full provenance is recorded in ADR 0060.

Before implementing acquisition rules, audit existing raw item-instance evidence:

```bash
UV_CACHE_DIR=.uv-cache uv run godfield-bot runs inventory-evidence \
  70db32df-5949-43f8-97a9-3fe7df5d5662 --database runs/godfield.sqlite
```

This read-only report distinguishes raw ownership observations from rendered
slots, used flags, and version gaps. It does not infer gifts or produce training
labels. The stored run contains 17 distinct IDs and 16 known unused items;
the official growth/overflow algorithm still needs contiguous event evidence.
The current client also warrants revisiting the earlier browser-local Training
assumption, but the API driver's Training rejection and all live controls remain
unchanged. See [ADR 0061](docs/architecture/0061-inventory-observation-audit.md).

The separate acquisition collector is opt-in. It queues ordered self-item
snapshots and reviewed, redacted event metadata; records overflow/rejection
counters; and saves before acknowledging updates. It does not change policy
authority or provide training labels. Three operator-run v1 recordings verified
transport, but exposed a coverage bug: attack/defense events normally lack an
explicit player ID, so their item bodies were redacted. V2 binds self consumption
through conservatively verified, ordered phase context. V3 adds self-only event
item wire classifications. V4 preserves the seeded two-player attacker/defender
swap at reflection, verified against the pinned client. New captures use v5,
which also saves self `removeItems`/`removeUsedMiracles` payloads when that same
fully seeded duel context proves the recipient. Removal effects clear the
carried context; explicit event player IDs alone cannot bind them. Unseeded,
self-targeted, multiplayer, and other redirect effects remain unresolved;
historical v1/v2/v3/v4 records and checksums are not rewritten.
Opponent and unresolved bodies remain redacted. Raw omitted flags stay
unknown; the pinned client's defaults are reported separately. V1 recordings
and their checksums remain unchanged.

Run `bc54a888-de09-4654-9b7a-80533d525c2a` verifies v2 capture for ordinary self
attack/defense consumption, including cross-update ownership. All four recorded
inventories now match a separate native ordered replay: remove consumed items,
then append explicit gifts even when they reuse an ID. This is a diagnostic
building block, not a new training curriculum; miracles, gift scheduling, and
overflow still need verified lifecycle fixtures. See
[ADR 0064](docs/architecture/0064-verified-ordinary-inventory-replay.md).

Native 0.35.0 adds explicit retained-miracle replay support. Two inventory
transitions from the older v1 run `f456703e-a514-44fc-b474-ba95a676b264` retain
the same `<Flame>` instance/model, including reuse after its used flag is true.
The replay matches those ordered states, but missing v1 consumption bodies mean
this is not a complete event replay or training-label source. The operator's
v4 run `32d8eeeb-e23c-4196-a18e-be68ee1fc1e2` now provides explicit self-bound
Flame selections for both first use and reuse of instance 4/model 215. Both
native operation pairs match: keep the instance, mark it used, move it to the
tail, then append the recorded gift. Two matched use events are not the same
as its seven repeated true-flag observations. The full run still contains
unsupported updates; removal, overflow, and general gift timing are not verified.
See [ADR 0065](docs/architecture/0065-retained-miracle-observation-replay.md)
and [ADR 0071](docs/architecture/0071-official-flame-first-use-and-reuse.md).
The read-only audit of all ten saved acquisition runs found no explicit removal
or overflow event. Capture v5 prepares future removal evidence, but those effects
remain unsupported in the native replay and C++ training rules are unchanged.
See [ADR 0072](docs/architecture/0072-self-targeted-removal-evidence.md).

For further bounded collection against the official Training computer, with the
existing heuristic keeping control:

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot play-training --headless --max-games 1 \
  --max-seconds 0 --max-actions 1000 --no-progress-seconds 120 \
  --acquisition-evidence-probe
```

For opt-in targeted miracle collection, use a reviewed fixed-attack miracle slug
such as `flame`. This separate collection-only policy prioritizes an affordable,
already-legal miracle selection at most twice per game. It preserves normal
target/confirmation, defense, and selected healing/utility controls, then falls
back to the unchanged heuristic; that fallback can still choose miracles.
Repeated unchanged-state polls do not spend another priority selection. The
budget measures decisions, **not** accepted casts or proven reuse. No items are
injected, and a random deal may never contain the chosen miracle.

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot play-training --headless --max-games 3 \
  --max-seconds 900 --max-actions 1000 --no-progress-seconds 90 \
  --max-setup-retries 0 --max-gameplay-retries 0 \
  --acquisition-evidence-probe --acquisition-miracle-focus flame
```

Focused collection requires finite positive game/time limits and the acquisition
probe. It cannot be combined with neural, shadow, or canary control. Runs carry
policy ID `official-training-acquisition-miracle-v1`, explicit collection-only
metadata, and false training/promotion eligibility. Both replay exporters skip
them, and dataset readers reject this policy; their win rates are not strength
evaluation. Omitting the focus option preserves normal play. See
[ADR 0070](docs/architecture/0070-targeted-miracle-collection-and-reflection-capture.md).
The wall-clock cap ends an unfinished game and stops the campaign with
`aborted:wall_clock_limit`; it is a budget stop, not a freeze. Do not run another
campaign on the same profile while collecting.

For human-assisted removal capture, use a **two-player private room**. This is
not another official-computer campaign. The later three v5 recordings
`62af4169-69be-4fbf-a552-8c045faed389`, `57fe5532-b8ad-422a-9c2d-8f899f1de061`,
and `c197e02f-58d1-47b4-a9f7-fb88d05a340f` completed without operational errors,
but contained no removal event or self-owned browser-supported fixed-attack
miracle; zero focused selections were expected. More random deals alone do
not guarantee the missing mechanics evidence.

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot api play-private --confirm-play --password-stdin \
  --catalog-snapshot data/snapshots/2026-09-21/api-catalog-en.json \
  --acquisition-evidence-probe --team 0 --max-seconds 900 \
  --max-actions 1000 --poll-seconds 0.25 --no-progress-seconds 180
```

Enter `astra-vs-humans` at the hidden room-key prompt, then join the same room
on the official website with your **different human account** and enter solo.
Do not connect another runner/browser session as ロキ-67. Once the bot has
performed a reusable miracle, use Goddess's Soap on it when you receive that
card: Soap targets performed miracles, whereas Nocturnal Broom targets unused
artifacts. No cards are injected, so the deal can still delay this experiment.
Send the printed `run_id`, even if the relevant card never appeared.

Private capture requires finite positive time, tactical control without a
model, solo entry, and the explicitly supplied reviewed catalog (normal API
play retains its older default). It waits past a pre-existing completed game,
then stops at the first observed match result or an existing safety limit.
It saves sanitized raw self-event evidence before normalized-state deduplication
and decisions, using existing API reads. No extra capture requests are made.
These reads are **polling, not browser push deliveries**: intervening server
updates may be missed and cannot be reconstructed from inventory differences.
Room keys, account IDs, arbitrary raw strings, and opponent item bodies never
enter the evidence. Runs are collection-only and excluded from training
exports; normal API play is unchanged when the flag is absent. See
[ADR 0073](docs/architecture/0073-private-api-acquisition-evidence.md).

The browser collector's default pinned catalog is
`data/snapshots/2026-09-21/api-catalog-en.json` and its queue capacity is 256.
Inspect each browser or private collection run ID:

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot runs acquisition-evidence RUN_ID --database runs/godfield.sqlite
```

This read-only report exposes missing source/server versions, hook and delivery
failures, raw unknown flags, separately interpreted client-unused counts,
ownership coverage, and reviewed event counts. Its audit schema version is 4;
`capture_schema_versions` identifies whether the actual evidence is v1–v5.
It also reports raw true-flag observations, inventory-growth pairs, and
client-interpreted used activations. Growth/activation comparisons never cross
source/server gaps, invalid identities, or changed player membership counts;
replacement gifts and changed model identities cannot count as retained
activations. These are observations, not cast counts or causal rule labels.
V3 additionally reports self-event wire coverage, malformed event fields, and
ambiguous missing/null selection arrays. An explicitly empty array remains
distinct from an omitted selection; v1/v2 data is not retrofitted with sidecars.
Audit v3 introduced counters for self-bound removal events/items, unresolved
removal recipients, and ambiguous removal arrays. These are payload observations,
not successfully simulated removals. V4 also distinguishes API polling from
browser snapshot streams: API captures honestly report zero hooks/listeners,
`final_poll_succeeded: null`, and a separate `final_flush_succeeded: true`.
The API run's `client_sha256` is its environment fingerprint; the separate
`acquisition_decoder_client_sha256` identifies the reviewed decoder, not an
observed browser client. Historical evidence input fingerprints remain unchanged.
The native replay report is schema 3; full-run removal replay remains unsupported.
Even a clean transport report is not evidence for adopting acquisition rules.
Do not start a concurrent campaign on the same browser profile. Capture and
review contiguous fixtures before changing C++ consumption/gift/overflow
mechanics. See [ADR 0062](docs/architecture/0062-passive-acquisition-evidence-collector.md)
and [ADR 0063](docs/architecture/0063-acquisition-phase-ownership-and-wire-defaults.md).

To compare the captured self-inventory projection against the native C++ replay:

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot runs acquisition-replay RUN_ID --database runs/godfield.sqlite
```

This read-only command automatically checks ordered item rows, consumption, and
explicit gifts, including reused IDs. It reports matches, mismatches, unsupported
updates, gaps, and repeated versions. Run `bc54a888-de09-4654-9b7a-80533d525c2a`
matches all four inventories: the initial deal and three adjacent transitions,
with two ordinary items consumed and 11 gifts appended. Original evidence and
input fingerprints remain unchanged.

The checker deliberately limits single-item ordinary consumption to 45 models
with explicit captured uses: the earlier 17 and 28 additional models witnessed
in adjacent private API updates. It also admits nine exact, ordered two-item
ordinary selections; 12 models witnessed only in those pairs remain unsupported
when played alone. The [curated single-use fixture](tests/fixtures/acquisition-private-ordinary-single-use-v1.json)
and [paired-use fixture](tests/fixtures/acquisition-private-ordinary-paired-use-v1.json)
pin those boundaries. Single-item retained-miracle comparison is still limited
to model 215.
Other models may remain as opaque owned/gifted records, not automatically acquire supported
lifecycle rules. Each transition uses a fresh native object seeded from its
recorded previous inventory; a mismatch remains visible even if a later pair
matches. V1 captures, unresolved owners, unreviewed effects, overflow, disguised
selections, and unsupported combinations are not inferred or counted as matches.
`complete_projection_replay` is not a promotion pass: combat, gift timing, and
overflow remain unverified, and all training/promotion/acquisition-rule
eligibility flags stay false. The replay report has schema 3 and separately
reports `event_item_wire_metadata_complete`: v3 supplies classifications
for every reviewed self-bound event, and this flag also requires resolved
ownership and verified phase coverage. It rejects malformed event fields and
missing/null use arrays; the flag measures metadata coverage, not mechanics
fidelity. Historical v2 replay still works with that flag false. Exit code zero
means the diagnostic report was produced, not that the run passed a gate.
See [ADR 0066](docs/architecture/0066-native-acquisition-differential-audit.md).
V3 also invalidates repeated-update owner context when self event payloads or
wire classifications change despite unchanged inventory. Opponent payloads do
not enter this comparison. Restart collection with the same command above to
use v3; do not start a concurrent campaign on the same browser profile.
See [ADR 0067](docs/architecture/0067-event-item-wire-and-repeat-integrity.md).

Private-room capture broadened only the read-only inventory projection: 36
single-card transitions and nine two-card transitions match native replay.
Across the eight reviewed private runs, none has a complete projection replay;
missing/ambiguous events and other mechanics remain visible. Neither the C++
training curriculum nor live neural control changed. See
[ADR 0075](docs/architecture/0075-private-ordinary-selection-projection.md).

The first isolated provisional rule component models a caller-selected
two-performed-miracle removal for Goddess's Soap from the pinned catalog and
Bible. It is **not** official evidence or a trainable environment. Inspect its
source pins, assumptions, and false eligibility flags offline with:

```bash
UV_CACHE_DIR=.uv-cache uv run --locked --offline --extra simulation --extra training \
  godfield-bot simulation provisional-soap-plan
```

This leaves observed replay, the existing C++ training curriculum, model
promotion, and live control unchanged. See
[ADR 0076](docs/architecture/0076-provisional-soap-layer.md).

To inspect the next native ruleset gap without mistaking card inclusion for
mechanics fidelity, run `godfield-bot simulation coverage-report`. Against the
pinned Bible, the latest trainable curriculum configures 196 of 291 artifacts;
the report lists the other 95 by category. Its full-game readiness and promotion
flags remain false, even if the artifact count later reaches 291. Isolated
provisional components such as Soap are excluded from the trainable count.

An opt-in provisional curriculum now admits Strength Powder as a neutral
`+ATK10` booster using the existing C++ combo primitive. The pinned Bible and
API catalog must agree exactly; the ruleset has a distinct identity and does
not alter older checkpoints. Its catalog inclusion is 197/291, but its
behavior has not been validated against official play, and promotion remains
blocked. Inspect it with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation coverage-report \
  --ruleset provisional-strength-powder-wide-hand
```

This is a local-training bridge for a single catalog-derived effect, not a
full-game environment. See [ADR 0078](docs/architecture/0078-provisional-strength-powder-curriculum.md).

The next isolated C++ primitive maps a caller-supplied weight ticket to one of
40 attacks in the eight five-effect planet guardian groups. Inspect its pinned
catalog-derived, explicitly unvalidated plan with
`godfield-bot simulation provisional-guardian-plan`. Earth and Moon are
excluded, and the primitive does not summon a guardian, decide when one acts,
resolve an attack, or qualify for local training. See
[ADR 0079](docs/architecture/0079-provisional-guardian-ticket-map.md).

The next versioned C++ batch keeps caller-driven guardian instance, owner, and
group state across parallel environments. It supports explicit summon,
removal, reset, and model lookup with atomic multi-row validation and copied
snapshots. Inspect its pinned-source identity and limits offline with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-batch-plan
```

Native package 0.39.0 keeps this batch separate from all existing duel
curricula. It has no game-turn `step`, effect resolution, local-training
eligibility, or live promotion path. See
[ADR 0080](docs/architecture/0080-versioned-guardian-lifecycle-batch.md).

Add `--combat` to `simulation guardian-batch-plan` to inspect the guardian
combat batch. Schema 2 supports 39 of the 40 weighted effects: elemental attack
and defense, absorption, HP/MP/money changes, and curse flags. Diamond Axe's
weapon classification and the Earth/Moon special guardians remain unsupported.
The inspection report marks local training, full-game readiness, official
fidelity, and promotion false. See the initial combat contract in
[ADR 0081](docs/architecture/0081-provisional-guardian-combat-phases.md) and the
resource/curse expansion in
[ADR 0082](docs/architecture/0082-provisional-guardian-resources-and-curses.md).

Add `--turns` to inspect native 0.43.0's separate, bounded card/guardian arena:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-batch-plan --turns --max-turns 1000
```

It rotates through living players and supports 47 ordinary armor models,
39 basic weapons, six fixed-attack miracles, and reusable Wall/Turbulence
defenses with exact MP costs. Turbulence requires an explicit living-player
bounce target. Guardian attacks remain unclassified for these special defenses.
Turn and defense-selection limits prevent indefinite passing or toggling.
The one-card-or-guardian-effect-per-turn schedule is explicitly provisional,
and cards are caller-dealt without redraw. It is not a full-game training
environment or compatible with existing live checkpoint action schemas;
training and promotion remain blocked. See the original arena contract in
[ADR 0083](docs/architecture/0083-provisional-guardian-turns-and-armor.md) and
[ADR 0084](docs/architecture/0084-card-attacks-and-reusable-defenses.md).

Native 0.44.0 adds a separate seeded rollout adapter with acting-player-only
hands, relative multiplayer targets, zero-sum HP/MP rewards, and decision/turn
limits. Exercise it locally without starting online games:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-rollout \
  --batch-size 64 --steps 256 --seed 67 --opening mixed
```

This runs a legal greedy smoke-test baseline; it **does not train weights**.
Add `--player-count 3` (up to nine) to exercise multiplayer target choices.
The report distinguishes wins from truncations and includes a reproducible
transition digest. Its synthetic initial nine-card deal has no redraw, and
the optional guardian opening uses only Mars's five simple effects. This is
not full-game fidelity, a live-model migration, or a promotion gate. See
[ADR 0085](docs/architecture/0085-seeded-guardian-arena-rollouts.md).

The arena now has a separate CPU neural trainer. It uses recurrent imitation
followed by PPO, independent player memories, and paired unseen-seed local
evaluations. Run a bounded experiment with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --batch-size 32 --teacher-updates 64 --teacher-selected-defense-weight 4 \
  --updates 10 --max-turns 32 --max-decisions 128
```

The result prints a new `checkpoint_directory`. Inspect it read-only with
`simulation guardian-evaluate --checkpoint <checkpoint_directory> --games 64`.
Resume learning with `guardian-train --resume <checkpoint_directory>` and the
same arena bounds/opening and architecture; this writes a new child checkpoint
with fresh optimizers. These checkpoints cannot control live games. Initial
experiments reduced defense-toggle loops, but did not establish baseline
superiority; no-redraw turn limits remain common. See
[ADR 0086](docs/architecture/0086-local-guardian-neural-training.md).

An opt-in refill curriculum now replaces consumed weapons and confirmed armor
using pinned relative gift weights for the same 94 supported cards. To start
a **new** local candidate under this separate provisional ruleset:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --batch-size 32 --teacher-updates 64 --teacher-selected-defense-weight 4 \
  --updates 10 --max-turns 32 --max-decisions 128 \
  --refill weighted-consumption-v1
```

The same flag works with `guardian-rollout`; `guardian-evaluate` reads the
checkpoint's recorded rules automatically. Gifts wait until defense/bounce
finishes, and reports count them. Without the flag, no redraw remains the
default. No-redraw/refill checkpoints cannot silently resume across curricula.
On one paired baseline diagnostic set, decisive games increased from 8/32 to
24/32. Neural candidates still lose and sometimes reach toggle/decision limits.
This is not official acquisition timing, the full gift pool, full-game readiness,
or live promotion. See [ADR 0087](docs/architecture/0087-provisional-weighted-refill-curriculum.md).

Local PPO training can now add `--defense-feedback-weight 1` to learn teacher
labels on the defense states the candidate actually visits. It is disabled by
default, does not replace sampled learner actions, and adds no inference-time
fallback. The default `all-defense` scope performed better in the diagnostic
than the experimental `--defense-feedback-scope finish-decisions` option.
The selected refill candidate had zero defense-toggle limit exits in 288 local
evaluation games versus 14 for its parent. Wins remain mixed across seeds;
this improves observed defense stability, not full-game or live readiness.
See [ADR 0088](docs/architecture/0088-on-policy-defense-feedback.md) for the
reproducible continuation command and complete comparisons.

Native 0.45.0 also adds a separate inventory-utility guardian batch: four HP
items, three MP items, and reusable 7-MP Spring, increasing its supported
inventory to 102 models. Inspect the versioned component with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-batch-plan --turns --inventory-utilities \
  --batch-size 512
```

This is a component inspection, **not a training command**. Utility turns are
provisional self-use, with capped gains, exact costs, and no native redraw.
See [ADR 0089](docs/architecture/0089-inventory-utility-guardian-batch.md).

The component now has an opt-in, separately versioned nine-feature neural
curriculum. The recommended transfer preserves the existing seven-feature
candidate, copies its recurrent/action weights, and initializes the two HP/MP
value columns to zero. It writes a new local child with explicit migration
provenance and fresh optimizers; ordinary `--resume` cannot perform the transfer.
The utility refill pool has its own pinned 102-card profile. Existing models,
the 94-card pool, and live controls remain unchanged.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --migrate-utilities-from checkpoints/guardian-arena/4d611acb-410e-40dd-8520-0257b5679d79 \
  --inventory-utilities --refill weighted-utility-consumption-v1 \
  --batch-size 32 --teacher-updates 16 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --max-turns 32 --max-decisions 128
```

This requires the referenced local parent. To continue an already migrated
child, use `--resume <utility_checkpoint_directory>` instead of
`--migrate-utilities-from`, retaining the utility/refill flags and matching
arena bounds. `guardian-evaluate` reads those recorded rules automatically.
Teacher/PPO/evaluation reports include capped HP/MP gains, consumptions, Spring
casts, and utility MP costs across both actors. A 98,304-decision local run
exercises the complete pipeline, but evaluations do **not** establish greater
playing strength; healed games frequently reach the turn limit. Full-game
training readiness and live promotion remain false. Commands, migration
contracts, and comparisons are in
[ADR 0090](docs/architecture/0090-utility-arena-training-and-checkpoint-migration.md).

Evaluations now report `play_statistics`, separating attacks, utility use,
forced/voluntary passing, and mutual pass-only witnesses, with learner-only
ready-action counts beside totals. These diagnostics do not end games early
or change rewards. Longer-horizon checks revealed genuine inventory dead ends:
retained miracles cannot be afforded and neither player has another legal card
play. Raising the turn limit alone cannot resolve such states in this subset.

Native 0.46.0 adds a **separate caller-driven discard component** for the
approved provisional recovery path. Inspect it with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation guardian-batch-plan --turns --inventory-utilities \
  --inventory-discards --batch-size 512
```

It admits 63 supported nonweapon models, excludes the documented exceptions,
validates removal atomically, and leaves replacement gifts to its caller.
That inspection command does not train. A separate schema-3 rollout/trainer now
appends 18 discard-slot actions to the unchanged 30-action layout. It requires
its own refill identity/RNG and an explicit 30→48-action checkpoint migration:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-train \
  --migrate-discards-from checkpoints/guardian-arena/d496547f-3fb4-4ca4-80ba-20e51bf89b84 \
  --inventory-utilities --inventory-discards --refill weighted-discard-consumption-v1 \
  --batch-size 32 --teacher-updates 16 --updates 32 \
  --teacher-selected-defense-weight 8 --defense-feedback-weight 1 \
  --max-turns 32 --max-decisions 128
```

This copies every learned parent tensor unchanged, adds a shared discard scorer,
and creates a private local child with fresh optimizers. `--resume` cannot
silently widen actions or change episode bounds. To continue a migrated child,
replace the migration flag with `--resume <discard_checkpoint_directory>` and
retain its recorded inventory/refill/bound flags. The two inventory flags and
new refill mode also work with `guardian-rollout`; `guardian-evaluate` reads
checkpoint rules automatically. Reports count discards separately from utility
use and consumed cards, with learner-only discard counts in evaluation.

The first 98,304-decision child exercised 895 discards during collection. It
made no forced/voluntary passes in 192 bounded diagnostic games, but evaluations
do **not** establish stronger play; short healed games still frequently truncate.
Existing models/live controls remain unchanged. Timing, miracle discard
eligibility, and replacement are provisional; Sacrifice, official verification,
full-game readiness, and live promotion remain blocked. See
[ADR 0091](docs/architecture/0091-pass-only-diagnostics-and-discard-component.md)
for the native component and
[ADR 0092](docs/architecture/0092-discard-arena-training-and-action-migration.md)
for migration, commands, and complete comparisons.

Longer 128-turn / 512-decision **local subset** training is now exercised from a
fresh model, without changing or implicitly transferring old checkpoints.
New teacher/PPO metrics report `outcome_coverage`: sampled decisions whose
episode reaches a winner inside that window, those ending at a truncation, and
unfinished tails. Teacher labels and PPO-eligible decisions are counted
separately; a winner can be a learner loss. These measurements do not alter
actions, rewards, GAE, or bootstrap boundaries, and are not a promotion gate.

Fresh runs also evaluate the imitation endpoint before PPO. An opt-in
`guardian-train --updates 0` exports an imitation-only checkpoint, requiring
positive teacher updates and disabled PPO defense feedback. Normal training
defaults are unchanged. Inspect checksum-verified training exposure with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation guardian-training-report \
  --checkpoint checkpoints/guardian-arena/b53ba01b-0f2c-4137-92d3-0e543e6c50f0
```

That command runs no games. Historical absent coverage/stage measurements stay
unknown rather than being inferred from later outcomes. On two extra diagnostic
seed sets, the 128-step PPO candidate reached winners in 125/128 games but won
only 44; completion can improve by losing earlier. A 256-step continuation
raised measured winner coverage from 44% to 69% of eligible decisions, but did
not improve win rate and is **not** recommended over its parent. Full-game
readiness, official fidelity, and live promotion stay blocked. See
[ADR 0093](docs/architecture/0093-long-horizon-training-and-outcome-coverage.md)
for recipes, stage comparisons, frozen-trajectory checks, and remaining work.

To reuse a short-bound guardian checkpoint at longer limits, opt in with
`simulation guardian-train --migrate-horizon-from CHECKPOINT` and specify the
target `--max-turns` / `--max-decisions`. It saves a new child and rescales only
the two horizon-input weight columns, preserving same-position predictions
before the old limits within floating-point tolerance. Neither limit can
shrink; rules, source pins, architecture, rewards, and live controls remain
unchanged. Ordinary `--resume` still rejects changed limits. This cannot be
combined with utility/discard migration. See
[ADR 0094](docs/architecture/0094-explicit-horizon-checkpoint-transfer.md)
for the approved transfer contract and local training command.

Ready-phase tactical diagnostics now include an opt-in training-only
`--ready-activity-weight`: it discourages the pass probability group only when
a learner-ready state has a legal alternative. Forced passes and opponent
turns are excluded; no card is labeled correct, rewards/masks stay unchanged,
and there is no inference-time pass ban. The default is 0. Matched continuation
won 94/192 additional diagnostic games with ordinary PPO versus 86/192 with
weight 0.25, with zero voluntary passes in both. Keep the prior **disabled**;
it has not demonstrated an advantage. Neither result is a live/official gate.
See [ADR 0095](docs/architecture/0095-ready-activity-prior-and-matched-continuation.md)
for controls, artifact hashes, commands, and training-only boundaries.
The retained experimental control,
`checkpoints/guardian-arena/3d09213e-6c5e-4ca4-86f0-f8725d6678fd`, scored
122 wins / 122 losses / 12 turn-limit truncations across four 64-game seed
sets, without voluntary/forced passes or defense/decision-limit exits. A further
64-update continuation did not improve that aggregate; it is not recommended
over this parent. Neither is an accepted or live-ready baseline.

The approved **opt-in frozen-opponent curriculum** is available through
`simulation guardian-create-league`, `guardian-train --league FILE`, and
`guardian-evaluate-league`. It pins compatible checkpoint manifest/weight hashes,
keeps one greedy or frozen neural opponent per episode with private recurrent
memory, and excludes opponent moves from learner policy gradients. Normal
greedy/self-play training and live controls remain unchanged. League training
requires its exact `--resume` reference and `--teacher-updates 0`; creating a
new child does not update the frozen roster automatically. Training reports
now include roster-ordered exposure counters.

A matched 48-update experiment showed **no strength gain**: across two seed
sets and four opponents, the league child won 255/512 diagnostic games versus
277/512 for the retained reference and 273/512 for a greedy-only child. Keep
the reference; neither new child is recommended or promoted. This adds local
opponent diversity, not new C++ game mechanics or full-game readiness. See
[ADR 0096](docs/architecture/0096-frozen-guardian-opponent-curriculum.md)
for commands, source hashes, gradient boundaries, and per-opponent results.

For the **actual integrated training environment**, inspect:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-readiness
```

This offline audit distinguishes 102 inventory-usable models, five opening-only
Mars effects, 34 standalone guardian effects, and 150 wholly unintegrated
artifacts. It lists fourteen remaining full-game workflow requirements. The
older 196-artifact component catalog is not the same training environment;
component inclusion does not imply playable integrated mechanics or fidelity.
The catalog and official client were rechecked on 2026-10-01 and match their
existing source pins. Full-game readiness remains false. See
[ADR 0097](docs/architecture/0097-full-game-integration-audit-and-readiness-plan.md)
for source freshness, the acceptance boundary, and the remaining work.

Native 0.47.0 now provides a reusable 2–9-player disease/cure component with
atomic operations, caller-supplied progression tickets, duplicate-tick
protection, and copied diagnostic snapshots. It shares illness math with the
legacy simulator without changing legacy trajectories or checkpoints. New
mild cures use the documented Cold/Fever/Fog/Flash scope; legacy cure semantics
remain unchanged. The source-pinned factory is
`godfield_bot.curse_dynamics.create_provisional_curse_dynamics_batch`.
This is not yet connected to inventory use or neural rollouts, so the full-game
audit still marks the curse workflow partial and readiness false. See
[ADR 0098](docs/architecture/0098-portable-native-curse-dynamics.md).

Native 0.48.0 adds separately versioned status decisions on that same state:
Fog-safe padded status views, Flash defense-card limits, Dark Cloud chance-hit
decisions, and Fog recipient selection from caller-supplied enemy masks. The
factory is `godfield_bot.curse_decisions.create_provisional_curse_decision_batch`.
The view labels unknown data explicitly; hit/defense/target calculations are
scheduler-only, not learner features. These are still shared components, not a
complete policy observation or a full-game turn engine; no current checkpoint
or live control is switched to them. See
[ADR 0099](docs/architecture/0099-shared-fog-flash-darkcloud-decisions.md).

The approved **separate full-game development engine** is now native 0.83.0,
`integrated-full-game-development-v33`. It joins authoritative inventory,
HP/MP/CP, disease/cures, ordered attack composition, targets/chained defenses and
opt-in native acquisition. All 237 held models have pinned draw weights
totaling 500, and all 237 held-card abilities now have joined routes in this engine.

The separate reward schema1 now exposes terminal faction credit: each winning
team member receives +1, including eliminated teammates, other present seats
receive −1, and draws receive valid zeroes. Truncations and rejected commands
never become synthetic losses. `FullGameRewardAdapter` records this credit once
per adapter episode, captures the actor and forced-turn policy mask before each
accepted command, and requires explicit reset after collecting an ending.
The episode diagnostic accepts `--terminal-rewards`; its schema6 report includes
validated reward totals and counts without changing gameplay or replay hashes.
This supplies reward plumbing; complete rollout learning and its acceptance
checks remain unfinished. See
[ADR 0136](docs/architecture/0136-terminal-faction-rewards-and-explicit-credit.md).

For displayed-legal selections with insufficient MP for their actual hidden
cost, the source factory now uses the approved provisional fizzle: spend the
available MP, consume/mark the selected cards and apply none of their effects.
An incoming attack still resolves against a failed defense. There is no HP
debt. Raw native fixtures default off; `hidden_cost_policy="strict-error"`
retains explicit diagnostic failures. Private `hidden_cost_snapshot` counters
record requested/paid/unpaid MP and affected cards. See
[ADR 0137](docs/architecture/0137-approved-insufficient-mp-fizzle.md).

The approved separate18-slot policy now has a versioned public observation
encoder and a recurrent inference controller with28 native numeric choices.
It supports2–9 players/teams, displayed own cards, Fog-safe resources/status,
ordered selections and public trade/reaction/event views. Command identities
remain separate from learned features. Memory belongs to each player in each
environment and updates only after accepted commands; failed commands also
restore the sampling generator. Explicit reset clears every seat's memory.
The untrained policy completes32 local integration games across solo and team
layouts with12,391 legal commands and no errors/limits. This is an interface
check, not useful learning or a strength result. Current public views are
encoded; an official event-history stream is not added. The complete-episode
collector now retains accepted observations/actions and assigns each acting
seat its undiscounted terminal faction outcome. It excludes all samples from
truncated or failed episodes and preserves rejected commands for diagnosis.
In the32-game integration sweep all12,391 decisions receive valid terminal
targets. The local recurrent PPO trainer now uses those complete episodes and
saves an optional candidate for frozen evaluation. The 12-update and 32-update
2v2 runs scored 62–66 and 68–60 against their initial weights on separate
128-game held-out sets. Optimizer resume and the strength gate remain open. See
[ADR 0139](docs/architecture/0139-public-full-game-encoding-and-transactional-seat-memory.md)
and the approved
[complete-episode collector](docs/architecture/0141-complete-terminal-episode-collection.md)
and [local recurrent PPO](docs/architecture/0142-local-full-game-recurrent-ppo.md).

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation full-game-train --updates 12 --batch-size 8 \
  --players 4 --teams 1,1,2,2 --checkpoint-root runs/full-game-candidates

UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  godfield-bot simulation full-game-evaluate '/path/from/training/report' \
  --games-per-faction 32 --seed 100000
```

Use the `checkpoint` path from the training report as the evaluation directory.

That is not full-game fidelity: unobserved combinations, hidden cross-role
resolution, complete event/virtual commands and learning interfaces remain gated. Attack additions
include twenty-one weapons, four dual-role Ogre armor, Strength Powder, Fireball,
Meteor, Aura and Mirage. Selection order controls doubling and element setting, and
positive Darkness damage correctly finishes the target. Its local
nine-card deals, per-use receipts (including miracle reuse), Prayer timing and
automatic oldest-held eviction at an 18-card cap are explicitly provisional.
The cap and eviction rule are not established official server behavior.
Twenty-three special defenses now block, reflect or bounce; numeric armor and
special choices are exclusive after an optional Rainbow Curtain filter prefix.
Wall/Turbulence have MP costs and remain reusable; adjacent reducers can waive
those costs.
Reflections target the current source; bounce samples living seats including
self from a separate native stream. Chained responses preserve the original
turn owner and stop on resolution or explicit decision-limit truncation, not
an invented one-hop rule. General chain timing/source/sampling remains provisional.
Eighteen chance weapons (including Ascension Bow's base cast) and seven chance miracles resolve on native
confirmation. The saved client disallows attack-stat additions and player-chosen
targets for chance cards; a miracle may still be followed by a cost reducer.
A living enemy is selected before rolling using a separate
provisional stream; a target's Dark Cloud guarantees the hit without consuming
a roll ticket. Misses still use the card/pay MP, tick the
original owner once, and skip defense. Chance hits do not reroll during
reflection/bounce. Jinn's Rocking Horse also supplies fixed Wood DEF6.
Twenty new effects integrate HP absorption, curses on positive damage and
zero-ATK direct curse miracles. Healing follows the current source after
reflection and is capped; direct curses admit special defenses, not numeric
armor. Infliction affects the final living target; Dream alters new receipts,
not existing disguises. General compound timing remains explicitly provisional.

All eight counter rings now enter bounded native response families. They use
actual positive HP loss, resolve in defense click order with nested counters
first, and defer the original owner's single tick and all replacement gifts.
Counter payloads retain armor origin, so only Super Mirror can reflect them;
Mars uses a separate hit stream and target Dark Cloud skips its ticket.
Neptune supplies twice the damage as MP to its owner. Venus shares the pinned
client's CP → MP → HP payment arithmetic with future economy integration;
crediting the requested amount up to the local 100 cap remains provisional.
Rainbow Curtain clears the incoming element before defense and Darkness
finishing; undo rebuilds and prunes incompatible selections. Fever Mask applies
its self-illness after incoming effects, without ticking the defender.
Seven ordinary ATK/DEF weapons now execute both roles.

Treasure has a base cost of 5 MP and grants up to 10 CP through a shared
capped-credit helper, also used by Venus Ring. The miracle remains reusable,
is marked performed and moves to the hand's tail; each use completes the
original owner's turn. CP below 100 determines displayed reservation availability;
confirmation requires the displayed net MP cost after any adjacent waiver.
Actual identity resolves the resource and cost. CP caps, self-targeting and
compound timing remain explicitly provisional. No CP use charge is inferred
from catalog price. Exchange, Sell and Buy are now joined below.

Spiritual Staff, Socks, Hood, Sash and Doll now waive the cost of the
**immediately preceding miracle**, in utility, attack and defense selections.
They do not add attack strength or an attack element when attached; Wall and
Turbulence retain their exclusive special response. Staff still supplies ATK12
when used alone, and the three armor cards retain their standalone DEF6/9/12.
All utility uses now reserve a displayed card, optionally select a reducer,
then confirm; reservation alone never spends, consumes, ticks or grants a
benefit. Unaffordable miracles may be reserved, but cannot be confirmed without
covering their net cost. At the selection limit, unaffordable attacks/utilities
can cancel and defenses can undo, so the policy never receives an empty legal
mask. Existing arenas, checkpoints and live controls are unchanged.

To check all five reducers across zero-MP utility, attack and special-defense
turns offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-cost-smoke \
  --batch-size 600 --players 3 --seed 67
```

This completes 600 scripted **turns**, not full matches or training: 600 waivers
save 3,200 MP, actual spending is zero, and 2,800 commands resolve 200 cases of
each action family. It does not validate official compound timing. See
[ADR 0114](docs/architecture/0114-native-adjacent-miracle-cost-waivers.md).

Magical Stick now scales from MP **after** net selected miracle costs, applies
later boosters in click order, then consumes all the user's MP. Evil Broadsword
applies same-damage recoil only while the final target survives; Saw Boom Boom
opens two independent defenses rather than approximating one ATK6 hit. Each
strike uses the original composed payload and target, with queued counters
resolved before the next strike. Costs and attack cards are used once, not
once per strike. Recoil after redirects/revival, double-attack compound timing,
and deferring gifts and the single owner tick until the family ends remain
explicitly provisional. No existing learning checkpoint or live policy changes.

To check these complex weapon turns offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-weapon-smoke \
  --batch-size 720 --players 3 --seed 67
```

This completes 720 scripted **turns**, not full matches or training: 1,200 MP
spent, 1,440 recoil HP lost, 540 double-attack strikes resolved and 60 second
strikes suppressed. It also checks 60 reflections and 60 counter responses.
See [ADR 0115](docs/architecture/0115-native-complex-weapons-and-repeated-defenses.md).

Heaven Herb now consumes its owned instance, gains up to 20 MP, then inflicts
Heaven (or worsens an existing illness) before the original owner's final tick.
Thump-thump Tear samples either HP+10 or 10 self-damage from a dedicated native
stream. Both remain legal at full resources because their status/risk component
still matters. Lethal effects use the shared owned Sun Amulet hook before
ending checks. The Tear's local 50/50 distribution, compound timing and cap100
remain explicitly provisional, not official validation. Utility damage is
tracked separately from incoming attack damage.

To check these compound utility turns offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-compound-utility-smoke \
  --batch-size 768 --players 3 --seed 67
```

This completes 768 scripted **turns**, not full matches or training: 512 Herb
uses grant 8,000 MP, 256 Tear uses produce 123 healing and 133 damage outcomes,
and 96 Amulets revive their owners. No learning checkpoint or live policy changes.
See [ADR 0116](docs/architecture/0116-native-compound-utility-effects.md).

Dangerous Pestle now chooses a living player, including its owner, inside the
native cast; the requested target and Fog do not control that choice. Initial
self-hits resolve without a defense phase. Other targets use normal Light
defense, filters, reflections and counters. General ordered boosters and
adjacent miracle waivers apply; ordinary casts sample one target, while the
provisional Mirage combination reroutes each generated shot independently.
An actual living Dangerous Mortar holder takes priority, consumes one real
owned copy and loses up to 99 HP without opening a response. Uniform owner
sampling, Mortar timing/direct damage and broader composition are explicitly
provisional; they are not verified official multiplayer behavior. Owned Sun
Amulets resolve before endings, and all family uses defer gifts and the one
original-owner tick. Neither passive is a manual ready-phase action.

To reproduce the bounded targeting probe offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-danger-smoke \
  --batch-size 512 --players 3 --seed 67
```

This completes 512 scripted **turns**, not full matches or training: 128 random
target draws, 384 Mortar attractions, 145 revivals and 1,631 commands, with no
extra owner ticks or limit truncations. Earth/Moon workflows and
the complete learning interface still remain; live promotion is blocked. See
[ADR 0117](docs/architecture/0117-native-pestle-mortar-targeting.md).

To check fresh, capped, full-wallet, unaffordable, reused and disguised utility
turns offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-economy-smoke \
  --batch-size 700 --players 3 --seed 67
```

This completes 700 scripted turns through 1,200 commands, not full matches or
training: 400 actual Treasure uses credit 2,500 CP, 100 disguised Spring uses
grant HP, and 200
unavailable Treasure cases pass. Exact MP spending is 2,700; no full-game
fidelity or strength is claimed. See
[ADR 0113](docs/architecture/0113-native-treasure-and-shared-wallet-credit.md).

Sun Amulet now automatically consumes a real owned copy when a living player's
HP reaches zero, restoring 10 HP. It is **not** a manual action for reviving
an eliminated player. Attack/Darkness damage, illness infliction, CP-payment
spillover, periodic illness, Heaven worsening and direct utility self-damage
all use the same staged hook.
It retains other state and resolves before counter liveness and outcome checks.
First-held selection, compound timing, retained statuses and deferred replacement
gifts remain explicitly provisional; dealing an Amulet to an already dead seat
does not revive it. The new actor projection uses displayed identities only.

To check these five death sources offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-revival-smoke \
  --batch-size 500 --players 3 --seed 67
```

This completes 500 scripted **turns**, not full matches or learning: 405
revivals supply 4,050 HP, including five native Heaven-worsening tickets. No
ticket is forced and no official revival event is claimed. See
[ADR 0111](docs/architecture/0111-native-passive-sun-amulet-lifecycle.md).

Broom and Soap now join the target/defense scheduler as standalone sundries,
not weapons or miracles: only Super Mirror can redirect them. Broom excludes
performed miracles and provisionally includes other held cards, including
trade cards; Soap removes only performed miracles. Native sampling uses actual
owned identities without replacement, preserves survivor order and used/fake
flags, and finishes normally on empty or short pools. Sampling, trade-card
eligibility, short-pool behavior and receipt timing remain unverified. Removed
victims receive no invented replacement gifts; the used sundry has its usual
provisional deferred receipt. Their listed $10 is a price, not a use charge.

To check removal offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-removal-smoke \
  --batch-size 600 --players 3 --seed 67
```

This completes 600 scripted **turns**, not matches or official validation:
700 removed cards, 600 consumed sundries, 200 empty-pool resolutions and one
original-owner tick per turn. No victim identities are learner choices. The
captured Broom trace remains narrowly admitted and Soap still has no official
event. See [ADR 0112](docs/architecture/0112-native-joined-broom-soap-removal.md).

To check counter accounting offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-counter-smoke \
  --batch-size 512 --players 3 --seed 67
```

This checks 512 scripted **counter families**, not full matches: each ring
receives 64 cases, Mars hits are deliberately forced, and all counters are
forgiven. It reports one original-owner tick per family, no leftover queue,
1,280 MP gained and 640 CP credited. It is not a training or promotion gate.
See [ADR 0109](docs/architecture/0109-native-counter-families-and-payment-waterfall.md).

To check these effects offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-attack-effect-smoke \
  --batch-size 640 --players 3 --seed 67
```

This deliberately gives targets Dark Cloud to isolate all 20 effects, then
forgives attacks. It completes 640 **turns**, not full games: 1,024 HP absorbed,
320 curse applications and 192 illness applications. These are mechanics
diagnostics, not training or strength evidence. See
[ADR 0108](docs/architecture/0108-native-attack-effects-and-target-first-chance.md).

To check these chance transitions offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-chance-smoke \
  --batch-size 504 --players 3 --seed 67
```

This makes one chance cast per environment, then forgives successful attacks.
The default cycles all 24 models and yields 305 hits, 199 misses and 504
completed **turns**, not full games or learning evidence. This historical
24-model probe does not exercise Ascension Bow. Its base cast and post-death
family are covered separately by ADR 0119.
[ADR 0107](docs/architecture/0107-native-chance-attacks-and-automatic-targets.md)
records the historical v6 probe; ADR 0108 records the v7 correction and evidence.

To check native complete-pool startup draws offline:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-acquisition-smoke \
  --batch-size 512 --players 9 --seed 67
```

This reports 41,472 diagnostic draws, all 237 models observed, 5,091 draws
without implemented effects and zero starting actors without an implemented
choice. It runs **zero gameplay commands**; sampling a model does not implement
its effect. Remaining special combat, utilities, economy, events, guardians,
other inventory mechanics and passives, teams and complete neural interfaces still require integration.
Existing training checkpoints and live controls are untouched; full-game
training and live promotion remain blocked. See
[ADR 0104](docs/architecture/0104-native-complete-pool-acquisition-and-provisional-overflow.md)
for acquisition, and
[ADR 0105](docs/architecture/0105-native-ordered-attack-composition-and-darkness.md)
for composition, dual roles, source pins and verification. The updated
`simulation full-game-combat-smoke` command exercises fixed known combination
hands offline; its outcomes are loop-liveness evidence, not bot strength.
See [ADR 0106](docs/architecture/0106-native-special-defenses-and-bounded-redirect-chains.md)
for special defenses, chain bounds and the unverified-mechanics boundary.

Pre-Apocalypse Discard now supports selecting multiple own held cards, toggling,
undoing, cancelling and confirming the complete removal once. It preserves
survivor identities/order and performed-miracle flags, charges no price or MP,
and generates no replacement receipt for discarded victims. The virtual control
is not a held artifact; weapons, Sun Amulet and Dangerous Mortar stay protected.
Displayed identities determine masks; actual eligibility is rechecked atomically
at confirmation. Compound timing and no-replacement scheduling remain provisional.
Sacrifice is now joined below, with provisional replacement timing; this does not increase the
artifact-effect count by itself or make full-game training ready.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-discard-smoke \
  --batch-size 512 --players 3 --seed 67
```

This completes 512 scripted **turns**, not matches or training: 767 discarded
cards, 85 cancellations, 85 Sun revivals and 170 post-tick Bow responses. There
are exactly 512 owner ticks and no discard replacement gifts or resource costs.
See [ADR 0121](docs/architecture/0121-native-multi-card-discard.md).

Dreaming Hat now joins DEF14/Wood, Dream and whole-hand redraw, including
performed miracles. Fresh weighted models, instance IDs, disguise sampling
and compound timing remain provisional. It uses displayed identity for legal
selection and actual identity only at confirmation. See
[ADR 0118](docs/architecture/0118-native-dreaming-hat-redraw.md).

A shared version-3 attack-family queue now schedules original recipients,
two-strike follow-ups, nested counters and Ascension Bow's post-death shots.
Ending checks cannot skip a dead owner's pending Bow; the original owner ticks
only once. A death during that tick drains its new family without ticking again.
Owned Sun revival takes precedence. Broader recipient order, duplicate Bow
behavior and event timing are provisional, not official fidelity claims.

Mirage is an addition to a non-chance weapon, not a standalone miracle. It
charges 5 MP per selected copy (or an adjacent waiver), preserves composed
ATK/element, and excludes Fog retargeting. The provisional engine snapshots
other living seats in ascending order, resolves repeated strikes per recipient,
and completes nested counters/death shots before later recipients. Duplicate
Mirages pay/perform each copy but produce one fanout. Later-dead recipients and
ordinary shots whose source dies are suppressed. Per-shot Pestle/Mortar
precedence, ordering and compound timing remain unverified. The response view
does not expose future recipients or private queue length.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-area-smoke \
  --batch-size 512 --players 3 --seed 67
```

This finishes 512 scripted **turns**, not matches or training: 1,196 original
recipient shots, 85 nested counters, 13,632 original incoming HP loss, and
exactly 512 owner ticks. See
[ADR 0120](docs/architecture/0120-native-mirage-and-multi-recipient-families.md).
Exchange, Sell and Buy are joined below; Earth/Moon now have provisional generated routes.
Broader event interactions, teams/rewards, hidden-safe
neural interfaces and complete mixed-episode learning gates are still required. No
existing arena, checkpoint, live policy or credential is changed.

Guardian Pot and Release now summon one owned guardian per seat, replacing any
existing guardian. Release retains its miracle and pays 15 MP or an adjacent
waiver; Guardian Pot's $10 is not a use charge. All ten ownership outcomes are
preserved. Summon distribution/order remain provisional. Forty standard guardian
effects—including Diamond Axe's weapon origin—join the shared version-7 queue.
After an enemy's completed turn, an owned living guardian has the pinned 25%
activation chance; positive HP debits use the pinned 10% departure chance.
Compound order, targets, RNG, caps and Fine's shared payment rule are provisional.
Post-turn reactions finish before gifts/endings without another owner tick or
recursive guardian triggering. Earth/Moon use the direct-action and virtual-fallback
paths below; all ten summon outcomes remain sampled. Full-game training and live
promotion remain blocked.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-guardian-smoke \
  --batch-size 4096 --players 3 --seed 67
```

This completes 4,096 scripted **turns**, not full matches or training: 1,045
unforced standard activations cover all 40 effects, with 106 Sun revivals and
exactly 4,096 original-owner ticks. Public guardian views respect Fog and reveal
no future queue/model/RNG or diagnostic identities. See
[ADR 0122](docs/architecture/0122-native-guardian-post-turn-lifecycle.md).

All five devils now join the gift lifecycle behind an explicit local
`apocalypse_after_turns` option (zero/disabled by default). The pinned appearance
percentages are 7/5/3/5/5 per post-Apocalypse receipt, totaling 25%. Damage is
automatic, with owned Sun revival, guardian departure and queued Ascension;
Trickster removes up to two actual nonmiracles/performed miracles, and Charity
chooses HP/MP/CP. Timing, theft sampling, caps and the configured Apocalypse
threshold remain provisional. Initial deals never trigger devils. After this
experimental Apocalypse, the same removal control now performs Sacrifice below.
Gift waves are iterative and explicitly bounded; no extra owner tick is added.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-devil-smoke \
  --batch-size 4096 --players 3 --seed 67
```

This starts with nine complete-pool weighted cards per seat, scripts one
affordable public turn, and forgives responses. The default covers all five
devils through 999 appearances and 4,096 owner ticks, with no pending family or
limit exit. It is **not full matches or training data**. Existing arenas,
checkpoints, live controls and credentials remain unchanged; readiness and live
promotion remain blocked. See
[ADR 0123](docs/architecture/0123-native-post-gift-devil-lifecycle.md).

String of Fate now selects among all ten phenomena natively at confirmation.
Global disease/Fog, confusion, HP assignment/healing, CP collection, inventory
shuffle, guardian replacement and both generated attacks have joined routes.
Unobserved selection/targets, shuffle ownership/IDs/used flags/disguises, caps
and compound timing remain explicitly provisional. Solar Eclipse preserves all
ten guardian outcomes, including the newly joined generated Earth/Moon routes.
Having all ten handlers is not complete interaction or full-game readiness.

Confusion uses the approved bounded native controller: ready phase exposes only
choice0, and the engine chooses a single play, discard or Prayer without
selection loops. Pre-step `policy_gradient_masks()` and the adapter's
`full_game_policy_gradient_weights` exclude forced turns from policy learning;
voluntary defense choices retain weight. These are training-interface components,
not a complete training pipeline. Death clears confusion; Sun revival retains it.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-phenomenon-smoke \
  --batch-size 512 --players 3 --seed 67
```

This is a uniform native first-turn probe, not full games or training. The
default records all ten committed models and512 completed first turns; both
Earth and Moon dependencies now resolve. The4096/nine-player/seed0 probe also
records one nested generated Fate:4097 events but4096 owner ticks. Deliberately
incomplete raw configurations still report atomic failures, never successful data.
Full-game training and live promotion
remain blocked. See
[ADR 0124](docs/architecture/0124-native-phenomena-and-forced-control.md).

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-attack-family-smoke \
  --batch-size 512 --players 3 --seed 67
```

This checks 512 scripted **turns**, not full matches or learning: 1,449 queue
entries, 937 post-death recipients, 86 Sun revivals and 85 Hat redraws. All
queues drain, every original owner ticks once, and there are no extra-owner
ticks or limit truncations. See
[ADR 0119](docs/architecture/0119-shared-native-attack-family-queue.md).
Broader Apocalypse/endgame interactions, teams/events/rewards, full hidden-family
handling and complete neural learning interfaces remain. The cap99 transition
is now implemented below, with explicit legacy100 diagnostics.
Full-game readiness and live promotion
stay blocked; existing checkpoints and live controls are unchanged.

Exchange now uses the approved six-column commands with a separate versioned
numeric menu in phase6: confirm, eight clipped MP/CP ±10/1 controls, and cancel.
Amounts are an uncommitted preview until confirmation; cancel never consumes
the card or advances its owner's turn. The legacy100 diagnostic cap and zero-HP Sun/Bow
timing are provisional, not official-client99 parity. Edits are bounded at64,
with confirm/cancel always available; confused turns resolve amounts natively.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-exchange-smoke \
  --batch-size 512 --players 3 --seed 67
```

This checks512 scripted turns, not full matches/training:1,638 commands,
51 Sun revivals and102 post-death Bow shots. Every original owner ticks once;
no reactions remain pending. Exchange's local cap and timing remain provisional,
and full-game learning/live promotion remain blocked. See
[ADR 0125](docs/architecture/0125-native-numeric-exchange.md).

Sell and Buy now join the native response queue with private owned-card custody.
Sell selects one unused owned card; Buy reveals a native-selected eligible card
after defense and asks the **current source**, including after Super Mirror
reflection, to refuse or purchase. Payment uses CP→MP→HP. Transfers and refunds
do not become artifact uses or replacement gifts. Offer sampling, timing,
received-card disguises, IDs, payment credit and overflow remain provisional.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-market-smoke \
  --batch-size 512 --players 3 --seed 67
```

This checks512 scripted turns, not full matches/training:2,560 commands,
410 transfers,51 refunds,102 reflections and102 Sun revivals. The4096/nine-player
probe also drains all custody/reactions with one original-owner tick per turn.
The remaining full-game/training work is still required. See
[ADR 0126](docs/architecture/0126-native-sell-buy-custody-and-responses.md).

Sacrifice now replaces Discard after the opt-in local Apocalypse threshold.
The current public translations confirm that Discard gives no replacements
and Sacrifice does; the catalog and client still match the frozen source pins.
Both share the128-model restrictions: no weapons, Sun Amulet or Dangerous
Mortar. The existing bounded phase7 selection/cancel control now reveals
virtual model1 (Discard) or2 (Sacrifice), without inspecting hidden actual roles
in legal masks. Confirmation validates actual identities atomically.

The local rule requests one complete-pool replacement per sacrificed card,
after the original tick and guardian reactions. Cardinality and timing remain
explicitly provisional. Tagged receipts preserve Dream/caps, devil effects,
Sun/Bow reactions and dead/ended suppression without another owner tick.
Sacrifice is removal, not an ordinary card use, miracle performance or MP cost.
Forced confusion can choose it natively, outside learner policy gradients.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-sacrifice-smoke \
  --batch-size 4096 --players 3 --seed 67
```

This runs4096 scripted Sacrifice turns plus4096 preparation turns, not full
matches or training:12288 tagged replacements,24576 commands, all237 held
receipt models and all five devils observed. Separate checks cover all128
eligible models at2/3/9 seats, hidden protected-role rollback, limits, death,
Sun/Bow and bounded self-renewing receipt loops. Full-game training, official
fidelity and live promotion remain blocked. See
[ADR 0129](docs/architecture/0129-native-sacrifice-and-tagged-replacements.md).

The full-game factory now defaults to **99 HP/MP/CP**, with an explicit
`resource_cap=100` compatibility option. Initial/seeded resources above the
selected ceiling reject atomically rather than silently migrating fixtures.
Healing, revival, wallet credits, guardian/generated actions, Heaven and
Exchange all share the selected ceiling. Raw native fixtures keep their100
default; previous probes are explicitly labeled legacy100. Existing arenas,
checkpoints and live controls are unchanged.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-resource-smoke
```

Add `--resource-cap 100` for the legacy comparison. Each default probe checks
4096 near-cap scripted turns,8192 commands and70 Heaven/Sun revivals, with no
resource-bound violations. These are mechanics probes, not full matches or
training. All22 legacy probe replays remain unchanged; the modern Sacrifice
probe now runs at99. Readiness and live promotion stay false. See
[ADR 0130](docs/architecture/0130-client99-and-explicit-legacy100.md).

Dream now privately resolves fixed/chance targeting mismatches and all six
Exchange/Sell/Buy disguise swaps, while retaining displayed controls and
hidden-safe masks. Missing trade parameters use independent native streams;
an empty hidden sale consumes its leader without a transfer/payment. These
user-approved rules remain explicitly provisional; raw fixtures default off.
Known hidden leader/addition/defense incompatibilities now resolve through the
approved ineffective-component rule: apply compatible actual effects, consume
or mark used the actual selected cards, and charge actual affordable costs.
A checked237-card capability manifest prevents missing registrations from being
silently treated as ineffective. Protected hidden Discard/Sacrifice selections
remain owned; only actually removed cards receive Sacrifice replacements.
These rules are labeled provisional and raw-default-off. Version33 adds the
approved whole-selection insufficient-MP fizzle described above; strict mode
still preserves atomic errors. Private diagnostics do not enter policy inputs.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-episode-probe \
  --batch-size 64 --players 3 --seed 67 --policy-seed 901
```

This runs unscripted complete-pool native episodes with a weak public-only
random policy, not learning or strength evaluation. The default now completes
64/64 episodes without errors; two-player64-env and nine-player32-env seed67
checks also finish. Across2–9 seats, seeds0/1/67 and32 environments per setting,
all768 solo episodes now finish. The expanded solo/team sweep completes3072/3072
games (3050 winner endings/22 draws), with zero engine errors or turn/decision
limits and1,066,610 accepted commands. It records26 insufficient-MP fizzles
(24 attack/2 utility). These are not wins by a trained candidate. On engine
errors the CLI exits1 with structured details.
Failed environments stop without action
substitution, while healthy environments continue. Wins/draws, native limits
and errors stay separate. Training and promotion remain blocked. See
[ADR 0131](docs/architecture/0131-private-dream-targeting-trades-and-episode-diagnostics.md),
[ADR 0132](docs/architecture/0132-approved-ineffective-hidden-components.md) and
[ADR 0133](docs/architecture/0133-approved-hidden-protected-removal-retention.md).

The separate engine now also has native team ownership and shared enemy
selection:0 means independent solo,1-4 identify shared teams. Guardians trigger
only after enemy turns; fixed/chance/Fog/private targets, area attacks,
post-death Bows, generated guardians, trades, forced turns and Black Hole use
the same enemy relation. Bounce, dangerous attraction, global effects and
directed reactions retain their distinct target scopes. A provisional ending
waits for the last living faction after queued work; terminal winner masks
include eliminated shared teammates. The separate reward adapter now supplies
the approved terminal credit, while complete policy encoding and learning
remain unfinished.

```bash
UV_CACHE_DIR=.uv-cache uv run --offline --frozen --extra simulation \
  godfield-bot simulation full-game-episode-probe \
  --batch-size 32 --players 4 --teams 1,1,2,2 --seed 67 --policy-seed 901 \
  --terminal-rewards
```

That diagnostic finishes32/32 default2v2 games with9111 accepted commands.
All2304 team episodes (2-9 seats, three roster patterns, seeds0/1/67) now finish,
alongside768 solo episodes. To reproduce the old cost errors explicitly, add
`--hidden-cost-policy strict-error`. These are random-policy
integration results, not trained-candidate wins. Current public source was
refreshed separately on2026-11-03; three names/assets changed but other raw item
fields did not. Old engine/model pins were not silently repinned. See
[ADR 0134](docs/architecture/0134-public-source-refresh-and-team-audit.md) and
[ADR 0135](docs/architecture/0135-approved-native-team-ownership-and-targeting.md).

Earth/Moon now use the approved **direct actions with virtual fallbacks**.
Category-filtered gift weights retain all207 Earth models (weight470) and all30
Moon miracles (weight30). A sampled card that can lead an action executes its
weapon, miracle, utility, Exchange, Sell or Buy route; otherwise Earth uses
Drop and Moon uses Full Moon Blade. Aura doubles the Blade, Mirage fans out,
and defensive additions retain its baseATK10. These are explicitly provisional
server-construction and sampling rules, not official fidelity claims.
Generated actions do not borrow or consume owned cards or pay ordinary miracle
costs; Magical Stick still consumes its owner's MP. Defenders pay their own costs.
Generated Sell holds a separate fresh parcel; generated Buy uses a native choice
for the original buyer, while a reflected new buyer gets a voluntary choice.
Shared responses, receipt-Dream/caps, Sun/Bow and nested reactions remain joined.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-generated-smoke \
  --guardian mixed --batch-size 4096 --players 3 --seed 67
```

This runs4096 scripted turns, not full matches or training:1045 generated actions,
840 attack entries,179 Drop receipts and4911 commands. It observes186 models;
`--guardian moon` reaches all30 miracles. Separate tests exercise all237 routes
at2/3/9 seats. Draw and execution histograms distinguish suppressed producers.
The42/42 joined guardian-model ledger is not a full-game readiness score.
`full-game-earth-smoke` remains an all-Earth compatibility entry point. Live
controls, checkpoints and promotion gates remain unchanged. See
[ADR 0128](docs/architecture/0128-native-generated-guardian-direct-actions.md).

A later private-room trace contains one self-targeted Nocturnal Broom-style
`removeItems` event. Its explicit three selected cards disappear in the next
inventory, and native 0.36.0/schema 3 can reproduce that narrow operation with
a fixture-specific model allowlist. The same update has an omitted defense
selection, so the full-run checker still reports it as unsupported; no
acquisition training or promotion gate changes. See
[ADR 0074](docs/architecture/0074-private-broom-observed-removal.md).

The first real v3 run, `60fe19b4-1ed3-42cf-9ce6-b63c52baa858`, completed against
the official computer without operational failures. Its checksummed regression
fixture verifies nine additional ordinary item lifecycles, including Heart Dew
consumption. The native differential audit matches the initial deal and eight
adjacent transitions, with zero mismatches; it leaves three updates unsupported
(a curse effect and two genuinely omitted defense selections, one alongside a
trade). Missing arrays are not rewritten as explicit empty arrays, and
individually witnessed items do not authorize unobserved combinations.
`boostHP`/`boostMP` are reviewed as inventory-neutral only, not simulated combat.
The chosen path is verified-only acquisition: no synthetic gift schedule,
overflow algorithm, training curriculum replacement, or live promotion.
See [ADR 0068](docs/architecture/0068-verified-only-acquisition-and-ordinary-expansion.md).

The next real v3 run, `cb9da594-c497-416f-86d6-444dc33e27c5`, verifies six more
ordinary models, including Smile Flower's MP-utility consumption. A reflected
attack also shows consumption and replacement gift arriving in different
updates: C++ keeps eight owned items until the later explicit gift restores
nine. This observed growth is not a miracle cast. The full audit matches the
initial deal and nine adjacent transitions with zero mismatches, while two
omitted selections and an unresolved reflected defense remain unsupported.
Reflection is inventory-neutral only; the diagnostic does not recover erased
defense bodies, infer a gift schedule, or generate training labels.
See [ADR 0069](docs/architecture/0069-deferred-ordinary-gifts-and-mp-utility-replay.md).
