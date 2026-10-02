# ADR 0105: Native ordered attack composition, dual roles and Darkness

## Status and scope

2026-10-01. Native 0.53.0 integrates ordered attack selection into the separate
`FullGameBatch` from ADRs 0102–0104. This is authoritative native turn state,
not another separately scheduled component or a caller-provided aggregate.
Full-game learning admission, official fidelity and live promotion stay false.
Legacy arenas/checkpoints, live controls/accounts and the external API pin are
unchanged.

The preceding goal turn was progress: commit `367b06c` added the complete gift
pool and approved provisional automatic overflow. This turn makes previously
drawn additions playable and corrects a source-established element rule.
It does not redefine the requested full-game milestone as combination support.

## Source checks and coverage

The saved Oct 1 API catalog and Sep 20 Bible retain ADR 0104's hashes. The
combat plan now checks the catalog's actual records/checksum and both source
pins itself, as well as every selected API/Bible value, element image, cost,
category, ability and complete description. The seventeen effect-free additive
weapons reuse the established Bible parser without borrowing its scheduler.

In addition to the 39 ordinary leaders, six fixed attack miracles and 47 plain
armor from ADR 0103, composition integrates:

- Nineteen additive weapons: seventeen ordinary additions plus Wand of Ignition
  and Wand of Mystic Water with their element-setting operations.
- Ogre's Shoes, Gauntlet, Helm and Armor with both additive ATK and ordinary DEF.
- Strength Powder with its provisional catalog-derived additive interpretation.
- Fireball and Meteor, positive-ATK reusable additions that can also lead alone.
- Aura as an ordered doubling operation, not a positive-ATK standalone attack.

That is 27 new held models. There are 45 leader profiles, 27 addition profiles
and 51 armor profiles; four Ogre models overlap addition/armor roles. The
119 unique combat models plus twelve utilities/cures yield **131**, not the
sum of profile row counts. The complete 237-model gift distribution is
unchanged; 106 gifted models still lack integrated effects. Sky Harpoon and
Angel Bow remain excluded pending their special defense roles, and Mirage
remains excluded pending a proper multiple-recipient attack workflow. They are
not admitted as effect-free additions merely to increase coverage.

The combined sorted profile SHA-256 is
`0848b37812c513cc42839b549c0c46ab37195599417a36f694a87d554b954565`.
Addition rows are `[model, ATK, element, MP cost, composition kind, can lead]`.
Kinds are add, set-element-and-add, and double-and-mix-element. Plan schema 2
pins arrays, role counts, source hashes, exclusions and effect descriptions.

## What the saved client establishes

The saved client at
`runs/experiments/official-client-2026-09-28.js` carries the pinned client
fingerprint. Its `gkN` and `ev` logic permit an additive weapon to be the first
attack card. Armor and additive sundries cannot lead. A positive-ATK additive
miracle can lead, but a zero-ATK additive miracle cannot. Further additions
require the first card to be an ordinary, non-chance weapon; a miracle leader
cannot receive them. The implemented fixed weapon leaders satisfy that source
restriction; chance leaders remain unsupported.

`tw` computes ATK in selection order, doubling at Aura and adding numeric ATK
for ordinary additions. `l9` computes elements in the same order, overriding
at an element-setting wand and otherwise mixing: equal elements survive,
Light substitutes for Fire/Water/Wood/Stone, and other mixtures become NE.
Aura has no element and thus mixes as NE; it is not silently assigned the
leader's element. `la` sums selected miracle costs. Cost-cutting tokens are a
separate future operation, not accidentally included in this slice.

These client/source checks establish displayed composition and category
restrictions, **not** complete server timing or Dream behavior. Intermediate
toggle/cancel ergonomics, retention ordering and universal receipt cadence
remain explicitly provisional. Strength Powder retains ADR 0078's unverified
interaction boundary. No new official game was run for this change.

## Native phase and transaction contract

Development ruleset v4 uses kernel/observation/metadata schema 4 and unchanged
six-column command schema 1. Implemented phases are 0,1,2,3,4,12,13. The
source-pinned factory always supplies all addition profiles; raw native calls
may omit them for older single-card diagnostic fixtures. Such raw fixtures
have no full-game metadata or training admission.

Ready slot+1 reserves a public leader and enters attack-selection phase 2.
Slot+1 then toggles eligible additions; ready/selection choices do not pay,
consume, draw or tick illness. Selection affordability uses only displayed
total costs. Choice 0 confirms and enters target phase 3. Undoing an addition
removes that exact choice and recomputes the remaining order; re-adding appends
it at the tail. Undoing the leader cancels all outgoing selections and returns
to ready, without inventing a completed turn. Each choice advances the native
decision token. After 64 selection/toggle actions, only confirmation remains;
repeated leader-cancel cycles still terminate at the real decision limit.

Target dispatch resolves every true selected effect in the retained order,
checks actual total cost and compatibility before mutation, pays total MP,
consumes ordinary weapon/armor/sundry components, and appends retained used
miracles in selection order. Unselected items keep their order. The primary
category determines attack origin: a weapon plus miracle additions remains
a weapon attack, while a standalone miracle remains a miracle attack.

One receipt is queued for each used component, including already-used
miracles. None arrives before defense confirmation. ADR 0104's living/ending/
limit checks then govern draws and automatic oldest-held eviction. Consuming
one ordinary leader with two retained additions from a full hand can therefore
produce three receipts and two provisional evictions, all in one transaction.
Defender consumption and owner illness still share that completed turn.

Displayed power is bounded by `2^53-1`. A candidate that would exceed it is
masked using only the public preview. A hidden actual aggregate that exceeds
the bound fails atomically before payment, consumption or random targeting.
No signed overflow or lossy display-to-command conversion is permitted. Native
profile category, kind, cost, dimensions and duplicate checks are independent
of the Python/source wrapper. Every batch row stages before allocation-free
commit, including the ordered choice array and new counters.

## Darkness correction

The pinned Bible's element section states that positive Darkness damage sets
HP to zero. The earlier development engine only subtracted ATK, which was
incorrect even for its six already-supported Darkness leaders. V4 first
resolves actual compatible armor and HP-clamped damage; a positive remainder
sets the target's HP to zero. Zero damage under sufficient armor does not
trigger the finish. An aggregate mixed out of Darkness likewise does not.

`darkness_finish_count` records those positive hits. `hp_damage` remains actual
combat HP removed, including the remaining HP lost to the Darkness finish,
not nominal printed ATK. Ending is checked before administrative limits and
receipts as usual. This correction is confined to the separate engine; no
legacy trajectory or checkpoint semantics are silently changed.

## Public observations and offline probes

New copied/read-only views are `selected_attacks[B,C]`, `attack_order[B,C]`
(slot+1, zero padding) and `attack_selection_observations[B,5]` (count, displayed
ATK, displayed element, displayed MP cost, selection-action count). They are
public handles/previews, never true identities or hidden costs. Pending views
now cover selection and target; their action-count field is named
`selection_actions` under the v4 observation identity. Views clear on casting,
ending, truncation and reset; old snapshots remain independent copies.

Lifetime counters record addition toggles, attack confirmations, used attack
components and Darkness finishes. The schema-2 combat smoke includes those
counts and public order/preview arrays in its diagnostic replay hash. It uses
only public hand/mask/preview data to choose moves; redacting true diagnostics
must leave choices/outcomes/counters unchanged. No checkpoint is trained.

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation \
  godfield-bot simulation full-game-combat-smoke \
  --batch-size 32 --players 3 --seed 67 --max-turns 64
```

The fixed fixture includes twelve known cards per seat, now with Unknown
Feather, Wand of Ignition and Fireball. Its default produces 32 winners, no
draws/truncations/unfinished games, 179 turns and 693 commands: 95 utilities,
84 leader selections, 192 addition toggles, 84 confirmations, 84 casts, 84
resolutions and 70 armor toggles. It records 276 used attack components,
2,359 actual HP removed, 522 MP spent, 280 consumed ordinary cards and 161
retained miracle uses. This is **liveness, not a measured neural improvement**;
the larger known hands differ from ADR 0103's fixture and are not a win-rate
comparison.

Combat metadata SHA-256:
`4ccf4e5323688dfa8b2e6e74ab42f214a5cb5e04c5ee7156b86310c73e0f4612`;
diagnostic replay SHA-256:
`5ee2ad68e09ee02d9309cb573bac2e806a0e78b119ecf21645dca1d58a2fa43f`.

The schema-2 complete-pool startup probe still draws the same 41,472 true cards
and observes all 237 models. It now reports 14,636 unsupported-effect draws
and six initial actors without an implemented action. It executes zero moves
and completes zero games. Acquisition metadata SHA-256:
`3b38c73532c58d00054550949f89f898aea0dbbd7b3a89c6b1421818126e195b`;
diagnostic replay SHA-256:
`f74aa72ad268d52574aa13e81c3bba64b60cb5888aa6af6ce9cd43caeb4448f3`.
The utility smoke retains its preceding replay/counter totals; current metadata
SHA-256 is `c1b1e028b4b4f94a06e393815e18c05cb6bd856237588ccf2b0bdf2670c38b26`.

## Verification and remaining integration

158 added composition tests cover every new role, all 49 element mixtures,
ordered Aura/wands/undo, standalone restrictions, aggregate cost reservation,
first/repeated miracle retention, multi-card gifts/overflow, exact public and
hidden integer limits, Dream mask equality and actual rejection, 64-action
selection liveness, cancel-cycle truncation, mixed-phase/batch rollback,
Darkness armor/death, snapshots/reset, protocol parity and source/metadata
forgery. Four additional Ogre-defense cases join the prior armor tests. The
full non-browser suite passes 2,991 tests; both local headless browser fixtures
pass outside the macOS IPC sandbox, for 2,993 total. Ruff, changed Python
formatting, mypy across 90 source modules, native formatting, frozen offline
lock consistency and whitespace checks pass. Legacy golden behavior remains
unchanged; the lockfile changes only the local native version.

Next is special defensive responses and native redirect workflows, followed
by chance/special/area attacks, remaining targeted utilities/curses, economy,
events/guardians, removal/revival, apocalypse, teams/rewards and complete
native neural interfaces. Full-game liveness/replay/learning validation must
pass before local training readiness; official parity remains a separate gate
before live promotion. Unsupported actual effects are explicit development
errors, never substituted no-op labels or reward-producing full games.
