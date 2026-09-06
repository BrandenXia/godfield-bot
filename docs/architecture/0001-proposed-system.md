# ADR 0001: Proposed bot architecture

- Status: **Proposed — awaiting operator decisions**
- Date: 2026-09-06

## Context

God Field has no documented public API. The current web app is DOM-rendered
and uses an anonymous Firebase identity persisted by the browser. The agent
must remain observable, survive client changes safely, learn from play, and
eventually support a local control interface.

Learning directly from a small number of stochastic live matches would be
slow and unstable. A useful system also needs deterministic legal-action
checks so a model can never invent an invalid click sequence.

## Proposed stack

Use one Python 3.12+ codebase:

- **Playwright + dedicated Chromium profile** for browser control and stable
  account state.
- **Pydantic** for versioned configuration, observations, actions, and events.
- **Typer** for the initial CLI.
- **SQLite** for runs, transitions, decisions, errors, and model lineage;
  export training datasets to Parquet when volume warrants it.
- **PyTorch** for representation learning and the policy/value model.
- **structlog** for JSON logs and **Prometheus-compatible metrics** for live
  health. OpenTelemetry trace export can be added without changing domain
  interfaces.
- **FastAPI + Server-Sent Events** later for a localhost-only control panel;
  it will call the same command bus as the CLI rather than control the browser
  independently.

A Python-only first version keeps browser orchestration, trajectory capture,
training, and operator tooling in one typed process. Splitting a TypeScript
browser service from a Python trainer adds a protocol and deployment boundary
before it provides real value.

## Component boundaries

```text
CLI / future web UI
        |
   command bus ------------------------------+
        |                                    |
     runner ---> safety supervisor ---> browser adapter ---> godfield.net
        |                |                   |
        |                +-- selector/client drift checks
        v
    observer ---> typed GameState ---> legal action generator
                                         |
                              heuristic or neural policy
                                         |
                                  ActionDecision
                                         |
                                    executor
        |
        +-- event/trajectory store --> trainer --> evaluation gates
                                             --> versioned model registry
```

The browser adapter owns selectors and browser mechanics only. The observer
normalizes a page into a domain state. The legal action generator is the sole
source of executable actions. Policies rank those actions; they never emit raw
selectors or coordinates. The runner records the complete decision before it
executes anything.

## Identity and secrets

The stable identity will be `ロキ-67`. Account creation is a separate,
operator-confirmed command because it creates external state.

The default credential strategy is a dedicated persistent profile under a
platform state directory, never under the repository. The process verifies
owner-only permissions before launching. Logs redact tokens, storage values,
room passwords, and browser profile paths. A portable encrypted backup using
the operating-system keychain can be added after the first working profile;
plain Playwright storage-state files are not acceptable backups.

Only one bot process may lock the profile at once. Losing or duplicating that
profile is treated as an identity incident, not as a reason to create another
account automatically.

## Observability and control

Initial commands should be shaped around operator intent:

```text
godfield-bot data refresh
godfield-bot account create --name ロキ-67
godfield-bot observe --mode training
godfield-bot run --mode training --policy heuristic --max-games 1
godfield-bot train --dataset accepted
godfield-bot evaluate --candidate <model-id>
godfield-bot models promote <model-id>
```

Every run gets an ID and records client hash, account identity label, policy
and model versions, normalized states, legal action sets, selected actions,
latencies, rewards, screenshots on anomalies, and terminal outcome. A local
kill switch, pause/resume, single-step mode, maximum-game limit, and maximum
wall-clock limit are mandatory before unattended play.

## Learning design

Recommended path: a **hybrid legality engine plus recurrent neural policy**.

1. Ship a deterministic heuristic baseline and use it to validate the entire
   observation/action/reward loop.
2. Build a headless rules simulator from accepted Bible snapshots and observed
   Training-mode transitions.
3. Train a small GRU or transformer policy/value network with legal-action
   masking in high-volume self-play.
4. Add completed real-game trajectories to an offline replay dataset for
   calibration/fine-tuning.
5. Promote a candidate only if it beats the current champion across fixed
   seeds, shows no legality regressions, and meets latency/confidence gates.

Weights are frozen for the duration of a match. “Improves through playing”
means games expand the replay dataset and can produce a new candidate between
matches; it does not mean uncontrolled gradient updates during a live turn.

The exact algorithm should follow the simulator fidelity and data we obtain.
A masked recurrent actor-critic is a reasonable initial target, but it should
not be baked into browser or storage interfaces.

## Safety and compatibility gates

- Default to headed, single-game, Training-mode operation.
- Require an explicit opt-in flag for public matchmaking if public Duel play
  is approved at all.
- Stop rather than guess when state extraction is incomplete or the client
  fingerprint/selectors drift.
- Enforce human-observable pacing and hard request/action limits.
- Never solve or bypass CAPTCHAs, warnings, bans, or access controls.
- Never automate chat or other representational communication.
- Keep a deterministic heuristic fallback, but do not silently switch policy
  during a match.

## Decision required

1. **Play scope.** Recommended: Training and operator-owned private rooms only
   until the developer explicitly permits a bot; public Duel remains disabled.
   Alternative: permit public Duel behind an explicit per-run opt-in.
2. **Learning route.** Recommended: simulator-first self-play plus real-game
   fine-tuning. Alternative: live-game-only learning, which avoids simulator
   engineering but is much slower, harder to reproduce, and exposes other
   players to an immature policy.

Once these are decided, this ADR can be accepted and the repository can be
scaffolded without leaving foundational behavior ambiguous.
