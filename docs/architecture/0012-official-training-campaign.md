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

The browser action surface admits all 107 Bible-audited selectable weapons with
an exact rendered attack expression and state-aware expected-damage score,
affordable fixed-damage miracles, unconditional HP/MP sundries, neutral plain
armor, and verified Forgive controls. Utility sundries are admitted only when
their exact accepted-Bible asset has a current hand hit target and the resource
is below its cap. The official client resolves utility cards through a separate
left-panel confirmation after selection. That confirmation is exposed only when
the actor, accepted asset, exact `HP+N` or `MP+N` effect label, empty target, and
panel hit target all agree. Each step must change normalized state just like
every other browser action. The heuristic
prefers a lethal attack, then HP recovery at 25 HP or less, then an available
attack, and finally HP or MP recovery for liveness. This browser-only expansion
includes additive attacks used alone, MP-scaled attacks, automatic side
effects, repeated attacks, random targets, and the alternate Ascension display;
it does not enlarge the stricter native simulator curriculum. Probabilistic and
random-target weapons have a distinct untargeted resolution action because the
client does not name a target until that phase resolves. That action shares the
existing neural confirmation index: untargeted and targeted confirmation
controls cannot coexist in one legal set, so the model output dimension does
not change. Empty Prayer is legal only when no weapon is present in the hand.

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

Run `308002d7-352a-48d9-880e-137acfe3e2b2` exposed the next liveness boundary.
At field 13, ロキ-67 had 2 HP and 10 MP under Fog; Evil Broadsword was masked,
Waterfall cost 12 MP, and Smile Flower was the only independently identified,
clickable useful card. The attack-only browser policy exposed only `wait` and
eventually reached the no-progress limit. With the deterministic utility rule,
the stored state instead selects the Bible-verified Smile Flower for MP+5,
without making the masked weapon executable or weakening the empty-Prayer
guard.

Bounded validation run `351c0e37-5d7c-4891-958b-6840dd21a3a5` then exposed a
distinct Fog response frame after 13 accepted actions. Nocturnal Broom targeted
ロキ-67 and displayed a clickable `Forgive`, but the response animation removed
all player-row controls and hid the opponent's stats. The original Fog recovery
required both player-row controls, so parsing waited until the no-progress
limit. The targeted-response fallback now carries the sole previous opponent
only when the Fog marker remains anchored to the visible self row, the current
actor exactly matches that opponent, the target exactly matches ロキ-67, a
current action artifact is present, and the right-side `Forgive` panel is
clickable. Carried opponent stats remain explicitly stale and neither player
receives a fabricated row hit target; this is sufficient to expose `Forgive`
without enabling targeting from stale geometry.

Post-fix live run `93a69f7a-609d-4ddd-86ce-c3088c15561b` completed with a
classified terminal result after 25 accepted browser actions and did not reach
the no-progress limit.

Run `dfcb06f8-4da9-485e-a013-c8882ce3c33e` showed that browser utility use was
incorrectly modeled as atomic. Selecting Smile Dew produced a stable left
action panel with the accepted asset and `HP+5` detail but did not apply the
effect. The stored frame now replays to an explicit utility confirmation using
the existing neural confirmation slot, so the action-head size is unchanged.

The first bounded validation, run `178aac17-a5ec-45a5-98c8-3cc4edcbc32c`,
advanced through 18 accepted actions before finding a separate Fog parser gap.
After Energy Helm was selected against a neutral `ATK2`, Fog hid the opponent
row while leaving the exact opponent actor, self target, left attack asset,
right armor asset, neutral `DEF10`, self Fog marker, and right-panel hit target
visible. The targeted Fog carry-forward now accepts this armor-confirmation
shape as well as Forgive; it still carries opponent stats as stale, fabricates
no row hit targets, and leaves the Bible allowlist to decide whether the armor
is executable.

Fresh official-client run `e0a18763-5070-4add-aed2-fac09462d3c3` completed
with a classified terminal result after 40 dispatched actions and no parse
errors. It directly exercised the corrected two-step utility path: Heart Flower
selection was followed by `confirm:utility:heart-flower:MP+10`, whose recorded
transition changed normalized state before the game advanced.

Continuous campaign run `125c421e-51e9-4ab9-863d-53a4f01eba3a` exposed a
screen-transition false positive after nine accepted actions. The last stored
gameplay frame remained internally consistent, but one subsequent capture had
kind `unknown` and no visible text. The runner immediately classified that
single blank sample as leaving gameplay and discarded the raw observation,
preventing both recovery and diagnosis.

Unknown gameplay captures now receive a configurable 15-second grace period,
bounded by the independent no-progress limit. Distinct unknown frames are
stored with a diagnostic event and optional owner-only screenshot. Returning
to a game clears the transient state; a sustained unknown frame ends with the
specific `unknown_screen_timeout` reason. Known non-game screens still end the
episode immediately, so this does not reinterpret setup or menu screens as
gameplay and does not fabricate a terminal reward.

The post-fix two-game soak crossed the campaign boundary and completed runs
`741d2c58-32d5-4f55-9f02-c990eecdd06d` and
`c3d19de4-d774-4e26-adf0-80e49398bcac` with classified terminal losses after
22 and 25 dispatched actions. The campaign stopped at its requested game limit
with two completed episodes and no aborts. Three incomplete frames immediately
before the second terminal classification recovered through the existing
parse-frame retry path, confirming that transient animation remains distinct
from the new screen-level recovery path.

A later unlimited campaign completed nine of ten games before run
`1b9537cc-01bf-4705-afdb-83fd131a1f33` reached a new Fog interaction at G.F.33.
The CPU reflected the bot's Rock miracle, placing `Forgive` in the left action
panel and the reflected `ATK8` plus Rock context in the right phase panel. Fog
hid the opponent's stats row. Hidden-player recovery only accepted the ordinary
incoming layout, so the otherwise supported reflected-Forgive action was never
reconstructed and the unchanged frame reached `no_progress_limit`.

Fog recovery now recognizes that reversed layout only when the prior state has
exactly one opponent, the visible headers name self and that opponent in the
expected columns, the left panel is a clickable `Forgive`, and the right panel
contains one selected weapon or miracle with an attack display. Replaying the
stored failure frame now yields `forgive:reflected`; missing attack context still
fails closed.

Official Training run `a19bce03-2bdc-4d52-b896-e9f9eeb28d33` then completed
with a classified terminal loss after 30 dispatched actions. It exercised a
live reflected attack inside a Fog scene at G.F.4: `forgive:reflected` was
dispatched from the left panel and produced a changed normalized state. This
live frame retained both stats rows, while the archived G.F.33 replay covers
the hidden-row recovery branch that caused the original stall.
