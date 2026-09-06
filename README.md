# ロキ-67 — a learning God Field bot

This repository is for a browser-controlled, observable God Field agent that
keeps a stable in-game identity and improves from completed games.

The architecture is accepted and implementation is underway. No game account
has been created and no public match has been joined yet. The current official
client and its in-game reference data were surveyed on 2026-09-06; see
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
```

Training and operator-owned private rooms are the only approved early play
scope. Learning will be simulator-first with real-game fine-tuning.
