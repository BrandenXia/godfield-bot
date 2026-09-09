# ADR 0012: Official Training campaign harness

- Status: **Accepted**
- Date: 2026-09-08
- Amends: ADR 0001

## Context

God Field's official Training opponent is implemented inside the web client.
Its turns are not represented by the server-side room state consumed by
pygodfield, so the private API runtime cannot play against that opponent.

The existing browser runner can enter and play one bounded Training game, but
an external shell loop cannot distinguish a normal terminal episode from an
aborted safety run. Reusing one run record for multiple games would also break
the outcome-replay invariant that one run has exactly one terminal outcome and
one sparse reward.

## Decision

Add a `play-training` campaign command. Each campaign iteration invokes the
bounded browser runner with the persisted ロキ-67 profile and creates a fresh
append-only run record. The command is headless by default, uses the reviewed
browser `heuristic-v0` policy, and keeps policy decisions and storage outside
the browser client.

`--max-games 0` means no completed-game limit. A classified terminal game is
counted and followed by another isolated game after a configurable delay. The
campaign stops on the first gameplay abort or failure and returns a nonzero
status; it does not restart an unsupported state indefinitely. Pre-game setup
failures can be transient, so they receive a separate bounded retry allowance
and remain recorded as failed runs. The summary includes the ordered run IDs,
setup-failure count, completed-game count, and win/loss/draw totals.

Per-game wall-clock, no-progress, browser-click, room-entry, and client-hash
checks remain mandatory. Public Duel remains disabled.

The browser action surface admits all 107 Bible-audited one-click weapons with
an exact rendered attack expression and state-aware expected-damage score,
affordable fixed-damage miracles, neutral plain armor, and verified Forgive
controls. This browser-only expansion includes additive attacks used alone,
MP-scaled attacks, automatic side effects, repeated attacks, random targets,
and the alternate Ascension display; it does not enlarge the stricter native
simulator curriculum. Probabilistic and random-target weapons have a distinct
untargeted resolution action because the client does not name a target until
that phase resolves. That action shares the existing neural confirmation
index: untargeted and targeted confirmation controls cannot coexist in one
legal set, so the model output dimension does not change. Empty Prayer is legal
only when no weapon is present in the hand.

## Consequences

The bot can now gather repeated evidence against the actual official CPU while
preserving replay and terminal-reward integrity. A failure points to exactly
one diagnostic run in the existing SQLite store.

This does not make the pygodfield tactical action bridge available in Training.
The browser policy still supports a narrower action surface, and expanding that
surface requires separately verified DOM observations and hit targets.

Live campaigns on 2026-09-08 validated fixed neutral attacks, elemental
attacks, fixed miracles, neutral defense, Forgive, terminal classification, and
sparse reward recording. Run `16aff090-919e-46dc-a475-b2074921ebe6` completed
normally against the official CPU and was classified as a loss. Earlier
diagnostic runs established that the client rejects empty Prayer when a weapon
is held and that probabilistic attacks first render an untargeted chance panel;
both rules are now explicit rather than inferred from a timeout.

The longer soak also showed that an accepted Prayer can leave a short-lived
frame with the `Pray` label but without its clickable panel. Legal generation
now requires the normalized panel hit target, preventing a duplicate click.
A reflected attack can similarly place `Forgive` on the left panel; that
mirrored control is admitted only with the original actor, sole named opponent,
exact reflected artifact, displayed attack, and left-panel hit target.

Run `7d1d9c27-da9f-437b-b38e-01d1f5f2200f` then completed normally and was
classified as a loss after exercising an accepted probabilistic attack and
multiple accepted weapon-free Prayers.

On 2026-09-09, a five-game campaign completed with five classified terminal
outcomes, two wins, three losses, and zero setup failures. It directly exercised
the MP-scaled Magical Stick path and the newly admitted Evil Broadsword and Saw
Boom Boom effects without a stall. The campaign also exposed and fixed action
artifacts rendered below large guardians and now retries transient pre-game
room failures within the configured bounded allowance.

Two later campaign aborts exposed curse-specific observation contracts. Under
Fog, the client keeps the player-row hit targets but hides the opponent's text.
The parser now carries forward the last known opponent identity and resources
only when the Fog scene, the self Fog marker, the known self row, and the exact
ordered row targets all agree. Carried values are marked `stats_visible=false`;
terminal classification and the current neural feature encoder abstain rather
than treating stale HP as observed. Exact untargeted attack panels remain
executable under Fog because the official rule randomizes the target, while the
Training game has exactly one living opponent.

Under Dream, the client renders a same-bounds mask between an artifact image
and its clickable `div`. Observation and execution now follow only that exact
overlay chain to a pointer target. The hand normalizer also excludes Trade
commands and preserves all rows in spatial order. This prevents a disguised
weapon from being dropped from the hand and prevents the illegal empty Prayer
that ended run `d2d97273-724b-431b-a312-34475641570c`. The Fog failure from run
`bef9d31f-2245-4e6b-9a9e-bfa06f96a570` now replays as a typed partial
observation rather than a parse error.
