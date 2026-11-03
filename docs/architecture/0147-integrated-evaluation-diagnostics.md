# Integrated evaluation diagnostics

`full-game-evaluate CHECKPOINT --diagnostics` adds a versioned diagnostic block
for each candidate faction. It supports both checkpoint and tactical opponents.
The default evaluation path is unchanged. Old reports remain readable with an
absent diagnostic block. The existing `full-game-readiness` command still
audits the earlier guardian subset and is not an audit of this newer engine.

Candidate decisions in the actual evaluation games are separated by native
phase. Reports include voluntary and forced counts, sampled and argmax agreement
with the fixed public tactical teacher, summed probability of the teacher's
choice, and both policies' 28-choice histograms. The teacher is a reference
heuristic, not an optimal-action oracle. Forced decisions have no agreement
denominator. These counts include decisions from truncated games and are
explicitly ineligible as training data.

Displayed slot choices have a 237-model histogram. Attack, defense and discard
selection toggles are counted, with deselections separately identified from
public selection ranks. Sell parcel choices are slots; Exchange amount edits
and Buy purchase decisions are numeric choices and cannot be counted as cards.
Dream's displayed identity remains the identity recorded in this histogram.
This is not a histogram of actual effect executions.

Only after all games have ended does the reporter read 33 native diagnostic
views. Their full field lists and sum of final per-episode rows are retained,
including acquisition by all owners, costs, combat, revivals, removals,
guardians, generated effects, devils, phenomena, economy and provisional hidden
resolution. Generated-model draws and dispatch counts remain distinct. These
statistics cover all seats in the matchup. Queue size, final remaining status
and peak-depth sums are not interpreted as effect execution counts. Zero counts
remain visible. Private diagnostics never enter a policy input or teacher label.

Diagnostic collection neither samples actions nor updates memory. Tests compare
ordinary and instrumented frozen results, check policy/memory/RNG preservation,
validate raw native totals, and cover forced turns, truncation, deselection,
numeric Exchange choices, CLI opt-in and tampered reports. Accepted commands
must form the original ordered episode sequence, and final totals must agree
with the engine. No report declares local readiness, fidelity or promotion.

## Larger-data learning experiment

The approved imitation/PPO recipe was rerun with more diverse teacher games,
using PPO seed 1210000, 128 teacher batches starting at 1220000, eight games
per batch, eight supervised epochs per batch and 64 PPO batches. This uses
181,063 voluntary teacher decisions. Of 512 PPO games, 506 had winners, five
were draws and one reached the decision limit. That incomplete episode's
choices were excluded from learning under the existing terminal-only rule.

On new seed sets 1250000 and 1260000 the candidate scored 20–43–1 and 19–45–0
(win/loss/draw) against the tactical baseline. The previous 64-update candidate
scored 12–50–2 and 14–50–0 on the same seed sets. All evaluation games ended.
The larger-data result is 39/128 wins against 26/128 for the previous candidate;
playing strength remains below the tactical baseline.

The new diagnostic measures candidate-visited states, which differ from the
teacher-visited states in ADR0146. Opening-card argmax agreement was 51.8% and
42.5%, while defense agreement was 63.0% and 60.7%. Additional data alone did
not resolve these gaps. A versioned public-card-feature extension was separately
approved after these measurements.

The candidate is retained under
`runs/full-game-imitation-candidates/34c67920-c2d7-4a10-9fec-bd24f62ad241`.
The two diagnostic reports are stored with it. The older candidate's reports
are retained with its own checkpoint. No live registry or controls changed.

The final non-browser suite passed 13,215 tests. Changed-source mypy, Ruff,
formatting, whitespace and offline lock checks passed.
