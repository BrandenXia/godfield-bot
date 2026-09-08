# ロキ-67 — a learning God Field bot

This repository is for an observable God Field agent that
keeps a stable in-game identity and improves from completed games.

The architecture is accepted and implementation is underway. The dedicated
`ロキ-67` browser identity has been created and used only in bounded Training probes. The current
official client and its in-game reference data were surveyed on 2026-09-06 and
revalidated with element metadata on 2026-09-07; see
[the research snapshot](docs/research/2026-09-06-godfield.md) and the
[architecture decision](docs/architecture/0001-proposed-system.md). The
[complete extracted Bible](data/snapshots/2026-09-07/bible.json) contains all
291 visible artifact records. The pinned pygodfield client independently
captured the current 296-model API catalog, including five trade models, in
[the API catalog snapshot](data/snapshots/2026-09-07/api-catalog-en.json).

## Working principles

- Use the exact-pinned pygodfield client for private live-game transport and
  the dedicated browser profile for identity bootstrap, browser-local Training,
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
uv run godfield-bot runs export-outcomes runs/outcomes.jsonl
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
```

`api observe-private --password-stdin` uses God Field's keyed private-room
matchmaking, then records bounded state without playing cards. An owner-only
(`0600`) `--password-file` can be used for unattended runs. An internal room ID
may instead be supplied with `--room-id`. Matchmaking keys are never accepted
as ordinary CLI values or stored in the run database. The observer always stays
a spectator. `api play-private --confirm-play --password-stdin` explicitly
enters the next match with the bounded conservative API policy. For an
unlimited wall-clock session that remains available for subsequent matches,
pass `--max-seconds 0`; the independent no-progress and action-count safeguards
remain active.
Use `--team 0` for solo/free-for-all entry, or `--team 1` through `--team 4`
for allied teams A through D. The selected team is retained across automatic
entry into subsequent matches. Active curse presence is recorded in the
normalized API state. When a curse makes card identity unsafe, the policy uses
a verified curse cleanser when available and otherwise passes, preventing the
bot from waiting forever on its own turn.

Install the optional learning stack with `uv sync --extra training --group dev`.
Install the native C++ curriculum simulator with
`uv sync --extra simulation --extra training --group dev`. Its batch-first
interface and strict fidelity boundary are documented in
[ADR 0002](docs/architecture/0002-native-simulator.md).
`models init` creates a checksum-protected, ignored model directory whose
manifest is tied to the current Bible client hash and artifact vocabulary. Its
status is `initialized`; evaluation and explicit promotion are required before
any learned checkpoint can control the browser.

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
`heuristic-v0` path can select the strongest Bible-verified fixed-attack weapon
and confirm it against an already named sole opponent. The attack allowlist
contains 32 icon-verified neutral weapons: 18 plain weapons, six whose extra
effect is passive Bounce, Reflect, or Block behavior, seven whose on-damage
effect resolves without another choice, and the live-verified neutral
Legendary Scabbard. Random, multi-hit, elemental, resource-consuming, and
self-damaging weapons remain excluded.
It can also Forgive a targeted incoming interaction after revalidating every
visible context artifact, and select plain armor during a verified neutral
defense before confirming that armor in its response panel. Every browser
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

`models train-outcomes` accepts only the stricter terminal-labeled episode
dataset. It uses the undiscounted sparse terminal result as the value target
for each recorded action in an episode while continuing to imitate only the
accepted action evidence. It writes another immutable candidate with before
and after policy/value metrics; it also cannot control the browser until a
separate evaluation and promotion gate exists.

Training and operator-owned private rooms are the only approved early play
scope. Public Duel and automated chat are disabled. The live private adapter is
documented in [ADR 0003](docs/architecture/0003-pygodfield-live-api.md). API
matches require another participant or separately authorized host account,
because Training gameplay exists only inside the browser client. Learning will
be simulator-first with real-game fine-tuning.

The native simulator provides four fast, deterministic curricula. The original
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
