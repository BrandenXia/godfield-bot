# ADR 0132: approved ineffective hidden-component resolution

## Status

Implemented as native0.79.0/schema30. The nonbrowser regression run had12169
passes and one obsolete strict-error fixture; moving that fixture to complete
raw strict mode passed its targeted rerun. Native0.80.0/schema31 subsequently
layers the separately approved protected-removal rule (ADR0133). Raw constructor
defaults remain strict. The full-game
objective in ADR0097 remains open; this is not a training-ready release.

## Approved local rule

For displayed-legal selections whose actual hidden roles/elements are
incompatible, consume or mark used the actual selected cards at their actual
affordable costs, apply compatible actual components, and explicitly count
ineffective components. Keep displayed controls and masks hidden-safe. This
is a provisional local rule, not official server fidelity.

Do not substitute an unrelated actual ability: an attack selected as a defense
does not become an unsolicited counterattack, and an addition-only leader does
not receive an invented virtual base. Preserve ordered compatibility and the
existing effect/cost-reducer rules. Actual unaffordable costs remain atomic
explicit errors pending a separate decision; this approval does not authorize
a new MP→HP payment waterfall or automatic free use.

## Concrete integration failures to cover

The schema29 episode probe's seed67/policy-seed901/64-environment/3-player run
identifies reproducible cases:

- Environments8/20/21: selected displayed defenses reveal actual cards unable
  to defend that incoming origin/role.
- Environment9: a selected displayed defense reveals incompatible actual
  elements.
- Environment26: actual model231 appears as attack leader228, but the actual
  card is addition-only.
- Environment51: an actual weapon19 appears as addition12 alongside leader34,
  but cannot provide the displayed addition effect.

Inspect current profiles and command state before implementing these paths.
The exact unaccepted commands are retained by the structured episode report;
trusted diagnostics can reconstruct true identities without exposing them to
the policy.

## Required implementation boundaries

- Add a separately versioned opt-in raw rule, preserving strict old raw fixtures,
  existing arenas/checkpoints and live controls. The complete source factory
  can enable the reviewed new rule explicitly.
- Distinguish **known effects in incompatible contexts** from missing native
  registrations or genuinely unsupported effects. A generic catch-and-ignore,
  broad zero-effect placeholder or card-pool filter is not this decision.
- Apply actual costs and waivers once, retain used-miracle ownership/order,
  charge/consume ineffective selections consistently, and tick the original
  owner only once. Full-action fizzle and partially effective sequences need
  distinct diagnostic accounting.
- Keep actual-role/ineffectiveness counters private and readonly. No true
  identity may change legal masks, reservations or previews before resolution.
- Preserve atomic batches and all private RNG streams on real errors, including
  unaffordable costs. Do not weaken the diagnostic driver's stop-on-error rule.
- Cover all registered role families, actual leader/addition/defense/cost-cut
  combinations, exclusive/filter ordering, element mismatch, repeated responses,
  reset/replay and both raw strict/new source-factory modes.
- Rerun whole-pool episodes at2–9 seats and report genuine endings, truncations
  and remaining errors separately. Removing these six default failures is not
  proof that all other seeds or all full-game requirements pass.

Keep local full-game training and live promotion gated until ADR0097's complete
mechanics, teams/rewards, action/observation/learner contracts and useful-learning
validation are actually satisfied. This decision does not shrink that objective.

## Implemented contracts

Append `resolve_hidden_components=false` and `role_profiles=None`. The source
factory enables the rule and supplies a checked237-row capability manifest.
Its nine bits cover attack/utility leaders, additions, numeric/special defense,
filters, reducers, passive ownership and trade. Python pins its digest to
`2ba9b5958eac738e74ba303f836bc1d01e696c073dde2a1da59b73743350807c`;
native construction independently checks each row against final registrations,
including injected guardian/Fate/Dream-Hat/area/complex-weapon capabilities.
Omitting an expected dual-role registration cannot silently become a fizzle.

Only a selected sequence with a differing actual/displayed identity enters the
new resolver. Displayed previews and masks remain unchanged. Compatible actual
effects apply in click order. The first compatible special is exclusive;
subsequent numeric/special cards are ineffective. A special following effective
numeric armor is ineffective. A filter must still precede effective defenses.
An ineffective component does not occupy an effective prefix position. A true
adjacent reducer still waives the preceding true miracle once, even when that
miracle's requested ability is ineffective. Dangling offensive reducers are
ineffective; standalone reducer armor retains its true numeric defense.

All actual selected costs are charged once, not just effective costs. MP-powered
Magical Stick retains its existing all-MP debit. Used miracles remain owned at
the hand's tail; other used components are consumed, with ordinary deferred
per-use receipts. An ineffective leader finishes the original turn without an
invented attack, target draw or unrelated utility. Effective attack-component
counts exclude ineffective additions. Strict raw/generated paths are preserved.

`role_profiles()` is an owned readonly catalog table, not held identities.
`ineffective_snapshot[B,14]` and `ineffective_model_counts[B,237]` are owned,
readonly, reset-per-epoch **trusted diagnostics only**. The former records
affected attack/utility/defense resolutions, leaders/additions/defense cards,
consumed nonmiracles/performed miracles, ineffective MP debit, full/partial
offense, element/order failures and all-selected-ineffective defenses.
Episode-probe report2 includes conservation-checked totals and adds both views
to its private rollback/replay fingerprint. No policy input is widened.

## Observed verification

- 401 new focused tests pass, including every leader-displayable and
  defense-displayable held family, true role/cost crossings, ordering,
  ownership, strict compatibility, reset and atomic rollback.
- 850 existing core/composition/defense/private-targeting/trade tests pass.
- All24 existing scripted diagnostic replays are unchanged; metadata digests
  change because the rule/manifest/version are explicit.
- Default3-player seed67/policy901 probe:64 native winner endings,0 errors or
  truncations,16015 accepted commands. Ineffective totals are
  `(2,0,4,1,1,6,7,1,6,1,1,2,0,2)`. These are random-policy game endings, not
 64 wins by a trained candidate.
- 2-player64-env probe:64 endings,0 errors,9086 commands.9-player32-env probe:
 31 endings and1 explicit hidden protected Sacrifice error,17816 commands.
- Across2–9 seats, seeds0/1/67,32 environments each:757 completed episodes
 (747 winner endings/10 draws),11 errors,0 truncations,292710 commands. Nine
 errors are unaffordable hidden actual miracle costs; one is protected Discard
 and one protected Sacrifice. These are retained, not substituted or filtered.

The user separately approved retaining protected actual removal selections;
that next rule is tracked in ADR0133. Actual unaffordable costs still require
a separate design decision and remain errors here.
