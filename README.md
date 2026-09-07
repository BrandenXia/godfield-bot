# ロキ-67 — a learning God Field bot

This repository is for a browser-controlled, observable God Field agent that
keeps a stable in-game identity and improves from completed games.

The architecture is accepted and implementation is underway. The dedicated
`ロキ-67` browser identity has been created and used only in bounded Training probes. The current
official client and its in-game reference data were surveyed on 2026-09-06; see
[the research snapshot](docs/research/2026-09-06-godfield.md) and the
[architecture decision](docs/architecture/0001-proposed-system.md). The
[complete extracted Bible](data/snapshots/2026-09-06/bible.json) contains all
291 current artifact records.

## Working principles

- Control the supported web UI through a dedicated browser profile; do not
  couple the bot to undocumented backend endpoints.
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
uv run pytest
```

Account creation is intentionally gated. It writes the anonymous login session
to a dedicated owner-only browser profile outside the repository and requires
the explicit `--confirm-create` flag:

```console
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot account status
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot account create --confirm-create
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot observe
PLAYWRIGHT_BROWSERS_PATH=.playwright uv run godfield-bot run --max-seconds 90 \
  --screenshot-directory runs/screenshots
uv run godfield-bot state parse runs/observations/game-spatial.json
uv run godfield-bot runs init
uv run godfield-bot runs list
uv run godfield-bot runs events <run-id> --include-payload
uv run godfield-bot runs record-probe <observation.json> --client-sha256 <sha256>
uv run godfield-bot runs export-replay runs/replay.jsonl
uv run godfield-bot models init
```

Install the optional learning stack with `uv sync --extra training --group dev`.
`models init` creates a checksum-protected, ignored model directory whose
manifest is tied to the current Bible client hash and artifact vocabulary. Its
status is `initialized`; evaluation and explicit promotion are required before
any learned checkpoint can control the browser.

`run` defaults to an observation-only Training policy. It is headed by default,
checks the live client bundle against the accepted snapshot, permits one
Training game, and records only changed states. Its room wait, gameplay
duration, no-progress interval, and in-match click count are independently
bounded. If gameplay leaves the known screen, the runner records a terminal
candidate instead of guessing whether the match was won or lost.

The default `safe-observer-v0` remains observation-only. The explicitly chosen
`heuristic-v0` path can select the strongest Bible-verified fixed-attack weapon
and confirm it against an already named sole opponent. The attack allowlist
includes plain weapons, six weapons whose only extra effect is passive Bounce,
Reflect, or Block behavior, and the live-verified neutral Legendary Scabbard.
It can also Forgive a fully
identified incoming effect, and select plain armor during a verified neutral
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
deltas. Rewards are deliberately not inferred during export.

Training and operator-owned private rooms are the only approved early play
scope. Learning will be simulator-first with real-game fine-tuning.
