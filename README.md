# ロキ-67 — a learning God Field bot

This repository is for a browser-controlled, observable God Field agent that
keeps a stable in-game identity and improves from completed games.

The project is currently in its research and architecture phase. No game
account has been created and no public match has been joined yet. The current
official client and its in-game reference data were surveyed on 2026-09-06;
see [the research snapshot](docs/research/2026-09-06-godfield.md) and the
[proposed architecture](docs/architecture/0001-proposed-system.md).

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

## Current decision gate

Implementation begins after two choices are confirmed:

1. whether early play is restricted to Training/private rooms or may enter
   public Duel matchmaking; and
2. whether learning is simulator-first with real-game fine-tuning (proposed)
   or live-game-only.
