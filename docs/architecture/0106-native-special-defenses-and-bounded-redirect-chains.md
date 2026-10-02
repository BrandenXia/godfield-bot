# ADR 0106: Joined special defenses and bounded redirect chains

## Status and scope

2026-10-01, native 0.54.0, separate `integrated-full-game-development-v5`.
This extends the same native engine from ADR 0105; it does not add another
independently driven scheduler, overwrite checkpoints or alter live controls.
Full-game learning admission, official fidelity and promotion remain false.
The approved oldest-held eviction still applies only at the explicitly
provisional local 18-card cap; no server ownership maximum is asserted.

Commit `79f913e` was the preceding completed milestone. This change integrates
the next missing mechanics, not a redefinition of full-game training readiness.
No new account or official game was used for this milestone.

## Pinned rules and distinct model coverage

The Oct 1 API catalog and Sep 20 Bible keep ADR 0104's source hashes. All 23
special records cross-check identity, category, printed ATK/DEF, additive flag,
ability, element, complete description, cost/price and gift weight. Plan schema 3
fingerprints attacks, numeric armor, additions and special profiles together:
`3fd5d21227b280d9a53405e0e41b1c9f8f0b37d7a08a39ad4a520f0037de1aff`.

Special rows are `[model, kind, origin, neutral_only, MP cost]`. Kinds are
block 1, reflection 2, bounce 3. Origin is weapon 0, miracle 1 or any -1.
This is an independent response role, not a numeric defense approximation.

- Bouncing Sword/Reflection Sword respond only to NE weapons.
- Wall blocks NE weapons at 6 MP; Turbulence bounces miracles at 5 MP.
- Angel weapons/armor block miracles; Sky weapons/armor bounce miracles.
- Moonlight Axe/armor reflect miracles; Super Mirror reflects all currently
  supported elements and origins.

The saved client's `e1` establishes these applicability rules. Its `ev`
establishes exclusive special selection; unimplemented filtering/cost-cut
exceptions are not invented. Positive printed armor defense remains available
when its special does not apply and the ordinary element rule permits it.
Defense weapons do not invent DEF from printed ATK.

Six added fixed weapons retain their attacking role; Sky Harpoon/Angel Bow
join the additive map; twelve added armor retain numeric DEF. Super Mirror and
the two defensive miracles contribute only response roles. There are 51 leader,
63 numeric armor, 29 addition and 23 special rows, representing **142 unique
combat models**, plus twelve utilities/cures = **154**. The unchanged 237-model,
500-weight pool still includes 83 models without integrated effects. Mirage
still requires a multiple-recipient workflow.

## Explicitly provisional whole-chain rules

ADRs 0030/0031 establish official first-hop Super Mirror/Reflection Sword
returns and fresh defense. The direct API Reflection Sword transition in run
`e4a7956e-4224-4eae-9112-72a2ff613a34` transfers source to the reflector.
It does not establish every repeated chain or multiplayer outcome. Earlier
guardian arenas' one-hop mask was a curriculum limitation, not an official rule;
their unchanged checkpoints retain that limitation.

Here reflection targets the **current** damage source and transfers that source
to the reflector. Bounce uniformly samples living seats, including the current
defender, and preserves source. Uniform sampling, bounce ownership and universal
repeated-hop ordering are **provisional**. Bounce has an independent native
SplitMix stream, never caller tickets or a player-selected victim. Its rejection
sampler has a 16-attempt bound.

Redirects preserve original turn owner, attack, element and origin. Confirmation
pays/consumes/retains the selected response and opens fresh defense with cleared
flags/toggle count. There is no intermediate damage, illness tick, turn advance
or gift grant. Numeric defense/full block finally resolves the attack; Darkness
still requires positive post-defense damage. Only the original owner ticks.
Hands, resources, pending ownership, RNG states and counters all stage before
any environment commits.

There is no silent one-hop restriction. Each response has a 64-toggle bound,
then confirmation only; repeated redirects reach the real episode decision
limit. That is explicit truncation, not a draw, damage or completed turn.
Pending receipts are suppressed on truncation; 64-bit queues prevent a long
reusable-miracle chain wrapping a 16-bit count.

## Interfaces and verification

Kernel, observation, plan and metadata schemas advance to 5; command schema
remains 1. Phases 0,1,2,3,4,12,13 remain implemented. Automatic redirects re-enter
defense phase 4 rather than inventing a player-target choice in reserved phase 5.
`special_defense_observations[B,5]` exposes active, current source, hop count,
displayed response kind and displayed MP cost. Pending numeric DEF is zero for
a special. All views are owned read-only copies. Masks/previews use displayed
identities; hidden unsupported, incompatible, nonexclusive or unaffordable
effects fail atomically. Lifetime counters track blocks/reflections/bounces.
The factory always supplies pinned profiles; raw optional-map fixtures do not
acquire source-checked full-game metadata or learning admission.

Tests cover all 23 models across seven elements and both origins, every confirmed
response, fallback armor, dual attack roles, repeated reflections, Darkness/full
armor, dead/self bounce targets, separate Fog/acquisition streams, reusable costs/
retention, Flash/undo/exclusivity, decision limits, hidden-identity failures,
metadata forgery and late-batch RNG rollback. A 32-environment, nine-seat stress
fixture confirms fourteen reusable bounces each, then decision truncation:
448 redirects, zero resolutions/damage/owner ticks/grants, 480 suppressed receipts.
This is liveness, not strength evidence.

The fixed-combination combat smoke still completes 32 winners in 179 turns /
693 commands, with 84 cast/resolved attacks and no truncations/unfinished games.
It contains no special defenses and is not relabeled as their coverage.
Schema 3 replay SHA:
`3e529bf1145ecb6d753c7a408819b9bab310108448fa9ea657b75aec7f9240e3`;
metadata SHA:
`19054cdebad5ddde856e618a53bc550ab6555b217ec4f7945e29be00d86bdfa4`.

The default startup probe draws 41,472 cards with all 237 models observed,
12,068 unsupported-effect draws and four initial actors without implemented
choices. It executes zero gameplay commands and completes zero games.
Schema 3 replay SHA:
`eb5f3a10b64d982a03e9e223af9a987fea2927422cad181f46c949e9def4a9bd`;
metadata SHA:
`1bd1a4a1abc8ed5be01689bc6a0710fb3f2cfdfa5ffd38e115403677b027ed84`.
The utility/cure probe retains ADR 0102's replay; current metadata SHA is
`a9e150dd30d23bf38ac41b71fe8578b471efc9321e41de1ba31051e1a5d7096b`.
The legacy 0.46 trajectory golden and existing learning/live controllers remain
independent regression gates.

Final verification: 3,394 non-browser tests plus two offline Chromium fixture
tests pass (3,396 total), including 381 new defense tests and the unchanged
legacy trajectory checksum. Ruff passes across source/tests; mypy passes all
90 source modules. Changed Python formatting, native source/header formatting,
frozen offline lockfile and whitespace checks pass. The lockfile changes only
the local native package version, not the external API revision.

## Remaining goal work

Next: chance/effect attacks, counters, filtering/cost cuts and multiple recipients.
Remaining utilities/status targets, economy/trade, events, guardians, removal/
revival, Apocalypse, teams and complete observation/action/reward/neural interfaces
still require joined native implementation and learning/held-out replay checks.
Full-game readiness is not inferred from registration, draws or fixed-hand endings.
