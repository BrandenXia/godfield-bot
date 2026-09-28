# ADR 0070: Targeted miracle collection and reflected-duel ownership

## Status

Accepted, 2026-09-28. The operator explicitly approved bounded targeted miracle
collection. Normal heuristic, model authority, C++ kernel/native 0.35.0, local
curricula, checkpoints, promotion gates, and the external API pin are unchanged.
This is mechanics evidence collection, not automatic policy improvement.

## Collection-only policy

`play-training --acquisition-miracle-focus flame` opts into
`official-training-acquisition-miracle-v1`. The focus must belong to the existing
Bible-reviewed fixed-attack miracle rules. The ordinary heuristic resolves the
legal state first. Only an attack-artifact choice can be replaced: the focus
must already be present in the exact recorded legal set, match the current
owned slot/asset, and be affordable at the observed MP. A stale state digest is
rejected. No new actions, gift requests, inventory injection, or mechanics
assumptions are introduced.

Each fresh game has two prioritized-selection decisions. Consecutive identical
state/legal-set polls return the same decision without spending another unit.
Once the budget is spent, revisiting a previous digest cannot replenish it.
The counter is not proof of acceptance or casting; the passive evidence must
establish that separately. The fallback remains the normal heuristic and may
naturally select more miracles after the focus budget. Targets, confirmations,
defense, selected HP/MP utilities, passing, forgiving, and waiting are preserved.
No guarantee is made that a random deal includes the focus or allows reuse.

The run config requires the acquisition probe, reviewed client and catalog,
positive finite per-game time, and a positive browser-click budget. The campaign
requires a positive finite game count. Neural, shadow, and canary models or
control confirmations cannot be mixed with collection. Existing finite retry
limits still apply; the documented collection command disables retries.

Every decision has the collection policy ID, including fallback decisions.
Run metadata records the focus and priority budget, `collection_only=true`,
`training_eligible=false`, and `promotion_eligible=false`. Action and outcome
replay exporters skip this policy or explicitly collection-only runs before
producing training samples. JSONL readers also reject collection-policy samples.
The shadow readiness gate already requires heuristic-v0 and therefore cannot
accept these runs. A collection win/loss is runtime telemetry, not candidate
performance evidence.

## Capture v4

The reviewed client `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`
handles `reflect` by calling its role-flipping `cZ`, then targeting the original
attacker through `aT`. Those handlers do not mutate owned inventory. A fully
seeded, distinct two-player turn/target pair can therefore be swapped for later
item ownership. Capture v3 instead cleared the pair, causing the unresolved
reflected-defense body in ADR 0069.

New passive captures use schema 4 and a new evidence source kind. V4 alone
permits this exact swap; unknown roles, invalid/self targets, more than two
players, gaps, membership changes, and other effects remain default-deny.
The Python strict validator independently replays the same interpretation.
Opponent and unresolved item bodies and wire sidecars remain redacted.
Durable-write-before-ACK, bounded queue, final drain, self-event wire metadata,
and inconsistent-repeat detection are retained.

V1/v2/v3 types still apply their original rules, so historical evidence is not
silently upgraded or rehashed. An old erased selection cannot be recovered.
Capture version 4 is unrelated to the neural feature schema or projection ID.
Even clean v4 transport is not permission to adopt gift scheduling, miracle
reuse, overflow, combat, or acquisition training rules.

## Verification boundary

Synthetic tests exercise role swap in both directions, consecutive updates,
gaps, default-deny effects, malformed/forged ownership, exact schema integers,
client/digest pinning, legacy semantics, and changed repeat payloads. Policy
tests cover normal-policy invariance, two-selection accounting, stale digests,
affordability/legality, control preservation, bounded CLI/config validation,
and export/dataset isolation. Synthetic tests are not official mechanics oracles.

A bounded official-computer smoke test used the unchanged account ロキ-67,
`--max-games 1 --max-seconds 300`, and zero setup/gameplay retries. Run
`1d87e285-f408-4d66-8e81-4a0215f32849` made 54 browser clicks, then stopped at
`aborted:wall_clock_limit` while play was progressing. No completed-game result
is asserted. Ten transient incomplete DOM frames were recorded as parse errors
and recovered; no no-progress failure, disconnect, or probe I/O failure occurred.

All decisions carry the collection policy ID and the run metadata declares v4
and false training/promotion eligibility. No Flame was dealt and no prioritized
selection or reflection occurred, so this live test verifies fallback and v4
transport, not focus execution, reuse, or reflected ownership.

The sanitized `tests/fixtures/acquisition-v4-1d87e285.json` preserves all 67
evidence records, original sequences, and batch digests. Input hash:
`ed1426edd95483b6a5c9052989b91d6883dc0776e8e23f42d5d7064ec846f7fc`.
There are 66 batches, 34 snapshots, and 33 adjacent pairs. Source/server gaps,
repeats, drops, rejections, hook/read/ACK failures, malformed fields, and final
drain errors are zero. Three unresolved owners, ten ambiguous omitted self
selection arrays, and no terminal snapshot remain visible. Eight inventory
growth pairs are not counted as miracle activations. The existing allowlisted
native projection matches the initial deal and five transitions with zero
mismatches; 28 updates remain unsupported. No new models are automatically
admitted based on this collection.

The documented collection command uses a finite 900-second per-game cap to
give longer matches more room. Any wall-clock budget stop still ends the
campaign instead of silently retrying until a favorable deal.

A first/repeated miracle use and eventual removal or overflow still need
contiguous official capture before changing C++ training acquisition mechanics.

All 867 non-browser tests pass. Ruff lint, selected-file formatting checks,
Mypy across 64 source modules, and the offline uv lock check pass. The two
existing browser-control tests were not run; the bounded official smoke test
exercised the existing Training browser harness. Historical official fixture
fingerprints and native curriculum/model promotion boundaries remain unchanged.
