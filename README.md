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
[the API catalog snapshot](data/snapshots/2026-09-09/api-catalog-en.json).

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
uv run godfield-bot models migrate-resource-features models/<schema-v4-model-id>
uv run godfield-bot models train-simulation models/<schema-v5-model-id> \
  --ruleset resource-hand --batch-size 256 --rollout-steps 32 --updates 10
uv run godfield-bot models evaluate-simulation models/<resource-candidate-id> \
  --ruleset resource-hand --games-per-seat 512 --minimum-score 0.5 \
  --heuristic-noninferiority-margin 0.025
uv run godfield-bot simulation benchmark --ruleset resource-attack-defense \
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
remain active.
Use `--team 0` for solo/free-for-all entry, or `--team 1` through `--team 4`
for allied teams A through D. The selected team is retained across automatic
entry into subsequent matches. Active curse presence is recorded in the
normalized API state. `api-combo-utility-heuristic-v2` uses strict
base-plus-booster attacks, compatible multi-armor defenses, affordable
targeted fixed-damage and curse miracles, special block/bounce/reflect
defenses admitted by the API, and deterministic HP/MP recovery. It takes an
attack with potentially lethal power before healing and otherwise restores HP
at 25 or less.
On a cursed turn, it prefers a verified all-curse cleanser and otherwise uses
only individually reliable, undisguised actions. When no attack or recovery is
available, Sell can offer the weakest verified plain armor to an opponent. If
no supported action remains, it abstains locally rather than submit an empty
turn command, which the live service rejects in this state; the run records an
`unsupported_self_turn` outcome instead of waiting for the no-progress timer.

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

`live-resource-shadow-readiness-v2` accepts only runs that carry the exact v2
adapter, schema, model and weight checksum, and tactical behavior identity. It
validates state/legal-action/decision pairing and terminal rewards, then gates
on completed games, attack and defense opportunities, all four resource action
families, proposal coverage, behavior agreement, and operational failures.
Proportions use Wilson lower confidence bounds. The resulting owner-only report
can mark a candidate ready for a separately authorized controlled trial, but its
`promotion_eligible` field remains false: outcomes from heuristic-controlled
shadow games are not candidate performance. See
[ADR 0015](docs/architecture/0015-live-shadow-readiness-gate.md).

God Field's official Training computer runs inside the web client rather than
the server-side API. `play-training` therefore drives the official browser in
headless mode by default while keeping policy inference, evidence storage, and
campaign control in Python. It preserves one append-only run per game so every
terminal reward remains a valid replay episode. `--max-games 0` continues
through completed games and stops on the first gameplay abort or failure,
making the first unsupported state easy to inspect. Transient pre-game room
failures are retried three times by default; use `--max-setup-retries` to
change that bounded allowance:

```console
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot play-training \
  --headless \
  --max-games 0 \
  --max-seconds 3600 \
  --max-actions 100 \
  --no-progress-seconds 60 \
  --max-setup-retries 3
```

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
`heuristic-v0` path can select the highest-expected-damage Bible-verified
one-click weapon and confirm it against an already named sole opponent. The
browser allowlist contains 80 exact-display attacks: 63 fixed attacks across
all seven elements and 17 probabilistic attacks whose chance roll requires no
player choice. Chance attacks use a separately validated untargeted resolution
step before any named-target confirmation. Six fixed-damage, single-element
miracles are also available when their exact MP cost is affordable. Empty
Prayer is allowed only when the hand contains no weapon, matching the live
client's rejection rule. Additive boosters, multi-hit, resource-consuming,
state-dependent, and self-damaging weapons remain excluded.
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
