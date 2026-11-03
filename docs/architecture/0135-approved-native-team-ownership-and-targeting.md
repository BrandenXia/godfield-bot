# ADR 0135: approved native team ownership and shared targeting

## Status and decision

User-approved2026-11-03; implemented and verified as native0.81.0/kernel-
observation-plan-metadata32.
Add opt-in
native team ownership and use one central enemy relation for all enemy-scoped
selection, guardian triggers and local team endings. Preserve raw default solo
behavior, old arenas/checkpoints/live controls and the insufficient-MP error.
Public current-source evidence is recorded in ADR0134. Promotion stays blocked.

## Intended boundary

- Trusted pre-start per-environment/seat team IDs:0 means independent solo;
  1–4 identify shared teams. Validate a whole seed batch before committing.
  Seeding after start is forbidden; reset clears episode-scoped team seeds.
- Fixed/chance/Fog/private targets, area attacks, post-death Bows, enemy guardian
  targets, generated guardian/trade targets, forced turns and Black Hole all
  share the same living-enemy eligibility. Guardians trigger only after an
  enemy's turn. Dead source owners retain their original team for Bow targeting.
- Do not globally reject allied damage in the shared queue: reflect/counter
  reactions, bounce, all-living phenomena and Dangerous Pestle/Mortar retain
  their existing target semantics. Self/ally targeting by those exceptions is
  not an excuse to let a voluntary enemy action select an ally.
- A local ending requires zero or one living faction after existing queued
  reactions and the original tick. Suppress ending receipts by factions, not
  living-seat count. Existing `winner` remains a representative living seat;
  expose all winning seats separately, including eliminated shared teammates.
  Do not invent a new reward scale or train dead-seat policy gradients here.
- Add owned readonly public team IDs/actor-relative relation views without
  hidden HP/inventory, plus terminal-only winner masks. Keep the complete
  observation/learner/checkpoint contract incompatible until explicitly built.
- Version the source/native contracts, record initial team layouts in factory
  and episode reports, preserve all-solo seeded replays, test mixed team/solo
  configurations2–9 seats, and retain errors/truncations separately.

Full-game training readiness still requires complete mechanics, rewards,
rollout/learner contracts and useful-learning validation from ADR0097. Neither
team support nor a passing random-policy probe alone meets that objective.

## Implemented contracts and observed checks

The raw option `teams_enabled=false` is appended after hidden removal retention.
The source factory enables it and records an optional initial roster. Trusted
`seed_teams` validates row counts, duplicate owners, IDs0-4 and pre-start seals
before committing. Epoch reset clears teams; callers must explicitly reseed.
The central native relation is self-excluding, treats distinct solos separately
and groups equal nonzero IDs. Faction counting uses independent solo keys.

Public owned readonly arrays are `team_ids[B,9]` (padding-1),
`team_observations[B,9,4]` (actor-cyclic seat/present/team/relation, padding
`[-1,0,-1,0]`) and terminal `winning_seats[B,9]`. Relation codes are self1,
ally2, enemy3; the view has no HP, liveness, resource, inventory or random data.
The source team plan independently cites the reviewed November client; all
other component/Bible/checkpoint source pins remain unchanged and explicit.

Episode report4 records roster and all winning player IDs, checks faction
membership, includes team/winner views in private replay/rollback fingerprints,
and retains representative `winner` for command compatibility. The CLI accepts
`--teams 1,1,2,2` with matching `--players 4`. This remains a public-random-policy
diagnostic, not learner rewards. No policy/credit-assignment scale was inferred.

Focused team/episode checks pass328 tests at this checkpoint. They include all
125 three-seat ID assignments;2-9-seat voluntary legality; native chance/Fog/
private-target paths; area exclusions; guardian trigger/generated routes;
post-death Bow/last-faction timing; dead teammate winner membership; receipt
suppression; bounce/counter friendly damage; all-living Tub versus enemy Black
Hole; ally Mortar attraction; atomic setup/seals/reset/read-only views; and CLI.
All24 scripted replays plus the legacy100 resource replay remain unchanged.

The32-env2v2 seed67 probe finishes32 winner games with9111 accepted commands.
A sweep across2-9 seats, pairs/mixed-solo/four-team rosters, seeds0/1/67 and32
environments per setting yields2287 completed games (2275 winner endings/12
draws),17 explicit hidden unaffordable-cost errors,0 turn/decision truncations
and770367 accepted commands. No new unsupported team path appears in that
sweep. These results are integration evidence only; game-wide source fidelity,
reward design, full neural interfaces and useful-learning validation remain open.

Final nonbrowser regression:12618 passed in202.93 seconds. Ruff, Python/native
formatting, mypy130 source modules, offline lock consistency, whitespace checks
and the normal offline frozen2v2 CLI pass. No existing arena/checkpoint/live
control was changed. An initial full run exposed a CLI-test isolation error:
captured stderr was left as the process-global logging sink, breaking later
training tests. The new test now preserves the logging factory, and a coupled
CLI/training run passes92 tests before the clean complete rerun above.
