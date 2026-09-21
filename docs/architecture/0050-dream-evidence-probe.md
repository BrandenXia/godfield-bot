# ADR 0050: Passive official-client Dream evidence probe

## Status

Accepted, 2026-09-21.

## Context

The official Bible says Dream makes 50% of received artifacts look false. The
current client bundle decodes both `modelId` and `fakeModelId` and renders the
fake model's image and details when the latter is present. Static inspection
does not establish whether the client exposes the true model to the cursed
player or whether card selectability leaks its true role. Choosing either a
fully observed or strict no-leak simulator before measuring this boundary
would train against an assumption rather than official behavior.

The 2026-09-21 Bible client and API catalog refresh retain client SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd` and
catalog content SHA-256
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.

## Decision

Add an opt-in `--dream-evidence-probe` sidecar to `play-training`. An
initialization script wraps the official client's Firestore `onSnapshot`
listener before application code runs. The wrapper calls the original listener
unchanged and retains a sanitized projection containing only:

- the field and update counters, turn player, pending response IDs, and terminal
  flag;
- ロキ-67's numeric player ID, curse names, and artifact instance, true model,
  fake model, and used fields; and
- the number of players.

It deliberately omits Firebase identity, room and document paths, credentials,
tokens, opponent identities, and opponent hands. Python pairs the sanitized
state with the currently rendered artifact path and same-bounds pointer
availability. Model IDs are decoded only through the pinned, checksummed API
catalog.

The official client sorts its displayed hand independently of the raw item
array. Evidence therefore joins an item to a visual slot by displayed asset
path, not array position. A unique path match is exact. Repeated displayed
paths are marked `ambiguous` and receive no per-item selectability; count or
asset-multiset differences are also explicit. The collector never guesses a
pairing.

Each run stores exactly one ordinary health sample proving that the listener
and raw-to-rendered alignment are active. After that, only samples with Dream
or a `fakeModelId` are stored. `runs dream-evidence <run-id>` summarizes known
versus server-hidden true identities, cross-category disguises, self-action
phases, selectability, and alignment quality.

## Information boundary

The sidecar is invoked only after policy decision recording. Its objects are
never added to `ScreenObservation`, `GameState`, legal actions, neural features,
or policy inputs. The browser script contains no click or command path. A probe
failure fails the game run instead of silently disabling evidence.

This probe does not yet authorize Dream in the native simulator. The simulator
design will be selected only after official-CPU evidence establishes whether
true identity is delivered and whether action availability discloses true card
role. Until then, existing Dream liveness recovery remains heuristic-only and
Dream observations remain outside neural control.

## Verification

Unit tests cover true/displayed cross-category binding, server-hidden true
identity, attack and defense phase classification, non-Dream health samples,
client-sorted hand alignment, duplicate-path ambiguity, report aggregation,
and the passive initialization-script boundary.

Live official-CPU run `1196f3b8-1f64-4191-ad57-db9ccc57caa7` completed after 24
accepted actions with no probe-induced liveness or action-acceptance failure.
No Dream occurred in that game. Bounded health run
`0c4c1518-e6ea-4111-881e-bee5679433e9` then recorded one sample with exact
raw-to-rendered alignment before stopping at its intentional one-action limit.

A subsequent passive campaign observed Dream in two games. Run
`a9e89c28-af49-4b9f-a4aa-41e79a2871f5` contained a brief two-sample Dream and
completed normally. Run `87cdd1a0-ab15-413f-a582-4adc36f738d7` retained Dream
from G.F.4 through G.F.17 and produced 35 Dream samples. Across that sustained
run, 165 disguised-item observations included 95 whose true and displayed
model IDs differed. Every true identity was present in the sanitized client
state, every disguise remained in the true artifact's category, and no
cross-category disguise was observed. These are observations of the sampled
official client, not a claim that cross-category disguises are impossible.

The sustained run also exposed a browser liveness defect. Dream nests the true
image and displayed mask inside an inner container while the clickable `div`
can be a sibling of that container. Immediate-sibling-only discovery therefore
reported only `wait` at G.F.17 even though the evidence sidecar independently
reported five selectable displayed weapons. Observation and execution now
retain the ordinary direct-sibling path and add a fail-closed fallback requiring
exactly one rendered pointer `div` with the same bounds as the normalized hand
image. Replaying the archived G.F.17 observation recovers all five weapon
actions. Live run `8216aac0-6aaf-4b01-9eb0-460e40d870ba` then completed after
28 accepted actions, confirming that the fallback does not regress ordinary
hand selection; Dream did not occur in that validation game.
