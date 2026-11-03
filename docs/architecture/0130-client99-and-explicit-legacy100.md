# ADR 0130: client99 factory default and explicit legacy100 diagnostics

## Decision and scope

The user approved a versioned transition: the separate full-game source factory
defaults to a 99 HP/MP/CP ceiling and retains an explicit `resource_cap=100`
option. Native0.77.0 advances full-game kernel, observation, source-plan and
metadata versions to28 (`integrated-full-game-development-v28`). Six-column
command1, family8 and trade-choice2 remain unchanged.

This is not a checkpoint migration. Existing arena classes, checkpoints, live
controls and promotion gates are unchanged. Raw `FullGameBatch` retains its
100 default for positional fixture compatibility; the source factory always
passes its selected ceiling explicitly. Only99 and100 are admitted. The
readonly native property and serialized metadata identify the selected rule.

## Evidence and compatibility boundary

The pinned public client Exchange controls disable HP/MP/CP increases at99;
see `runs/experiments/official-client-2026-09-28.js`, lines11883 and11890,
SHA256 `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
The public client was independently re-fetched on2026-10-18UTC with the same
hash; provenance is in `data/snapshots/2026-10-17/i18n-en-provenance.json`.
These client controls support the chosen ceiling, not a claim that every
server effect order or cap boundary has official differential validation.

Old scripted probes explicitly select100 and now report that cap. All22
legacy probe behavioral replay fingerprints remain identical to v27;
metadata fingerprints change with the versioned contract and selected cap.
The modern Sacrifice probe uses99, so its resource replay changes deliberately.
Its weighted card/devil selections and event counts remain unchanged.

Initial HP/MP/CP and trusted seeded resources above the selected ceiling are
rejected, never silently clipped or migrated. A late invalid setup row leaves
the whole setup call unchanged. An atomic, staged per-command invariant rejects
any resulting resource outside0..cap before committing a batched step.

## Joined resource paths

The selected ceiling is used by HP/MP/Treasure utilities and legal masks,
Heaven Herb, both Thump-Thump Tear branches, periodic Heaven and worsening,
Sun revival, Absorption, Neptune/Venus credits, standard guardian HP/MP/CP
effects, Charity, Fate healing/gold, Sell/Buy seller credits, and Exchange's
preview, clipped edits, confirmation and native allocation enumeration.

Generated guardian actions and native confusion use the same effect and
exchange implementations rather than a separate legacy100 path. Percentages,
printed prices/cost profile bounds, hit rates and other numeric100 constants
are not resource ceilings and are preserved. Shared parent-arena illness and
wallet defaults are not changed; full-game callers apply the selected cap.

## Observable diagnostic probe

`simulation full-game-resource-smoke` defaults to99; `--resource-cap 100` opts
into the legacy rule. Its schema1 strict report identifies the ceiling, source
metadata and behavioral replay. Six near-ceiling scenarios cover HP utility,
MP utility, Treasure payment/credit, Heaven Herb, Exchange and periodic Heaven.
The complete source factory is used, without automatic gifts. Sun protects
the two Heaven scenarios from worsening deaths, exercising real revival.

Both default4096-environment probes accept8192 commands with4096 original-owner
ticks,683 Treasure uses/3415 MP spent,682 exchanges and70 Sun revivals/700
revived HP. Cap99 credits683 CP and exchanges682 HP→MP; cap100 credits1366 CP
and exchanges1364 HP→MP. Every intermediate state is checked against its cap.
Per-row resource oracles and strict aggregate conservation reject inconsistent
counts, extra ticks, pending families, gifts and forged readiness flags.

The probes contain no completed full games, policy gradients, reward labels,
strength results or official fidelity evidence. All training/readiness/
promotion eligibility fields remain false.

## Verification and remaining objective

Targeted cap tests exercise all237 generated card routes at2/3/9 seats,
resource utilities and masks, atomic setup, both Tear outcomes, revival,
defense credits, all Charity resource branches, guardians, Fate, trading,
generated Exchange's full99 wallet and native confused allocations against an
independent bounded-wallet oracle. Independent illness RNG tests check the
probe's Heaven revivals; corruption tests cover every scenario's resource
totals and report boundaries. Cap-specific tests pass794 cases. The new probe
and existing guardian-activity training tests pass152 cases together, including
CLI logging isolation after invalid options.

The complete non-browser regression passes11177 tests in187.53seconds. Ruff,
mypy over127 source modules, formatting of98 changed/relevant Python files,
native clang-format, offline lock and whitespace checks pass. The ordinary
offline uv CLI launches both99 and explicit100 probes; the default4096
near-cap probe reports zero bound violations with readiness/promotion false.
Browser/live differential tests and real training jobs were not run.

ADR0097's full-game objective remains open: broader Apocalypse/endgame and
team/elimination/reward handling, hidden cross-role combinations, complete
observation/action/checkpoint/learner interfaces, seeded full-episode liveness
and useful-learning probes are still required. Official validation and live
promotion have their own acceptance gates and remain blocked. The cap change
does not redefine a scripted mechanics probe as full-game training readiness.
