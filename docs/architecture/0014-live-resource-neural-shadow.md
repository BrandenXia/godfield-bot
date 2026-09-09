# ADR 0014: Live resource neural shadow

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0010 and ADR 0013

## Context

The schema-v5 `resource-hand` curriculum adds stateful HP and MP, deterministic
HP/MP utility cards, fixed-cost attack miracles, and Spring. Its candidate
passed the native paired gate, but the schema-v4 live adapter intentionally
rejected it. The live tactical API surface already exposes these deterministic
actions, while native and live execution differ: utilities resolve with one
selection, attack miracles require selection plus Confirm in the policy head,
and the API submits either result as one `Command.use` call.

## Decision

Extend the neural shadow loader with the versioned
`api-resource-neural-shadow-v2` adapter. A model is admitted only when feature
schema v5 is paired with the exact
`plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1`
ruleset and `sequential-combo-selection` semantics. Schema-v4 models retain the
v1 adapter and must remain paired with the earlier combo ruleset.

For every proposed live resource card, the adapter cross-checks the normalized
API identity against the accepted Bible:

- sundry category, asset, `boostHP` or `boostMP` ability, exact utility value,
  zero MP cost, and no element;
- miracle category, asset, exact attack or healing value, exact MP cost, exact
  element, and supported ability shape;
- reliable undisguised instance identity and admission by the tactical legal
  action surface.

HP recovery is masked at 100 HP, MP recovery at 100 MP, and a miracle is masked
when its exact cost is unaffordable. HP/MP sundries and Spring resolve after one
slot selection, matching the native atomic transition. Fixed-attack miracles
expose only Confirm after selection, cannot accept weapon boosters, and resolve
to the corresponding one-card targeted API macro. Weapon and armor matching is
also strengthened to verify live value, element, effect, cost, and additive
role rather than relying on asset identity alone.

The observation preserves schema-v5 identity while retaining the established
13 global features, including normalized live HP and MP. Proposals record the
complete sequential action trace under the v2 policy ID; run metadata records
both that adapter ID and feature-schema version. Proposals are always
non-executable; `api-combo-utility-heuristic-v1` remains the behavior policy.

## Consequences

The gated resource candidate can now be evaluated counterfactually on accepted
private API states, including recovery and fixed-miracle decisions, without
receiving account control. Schema/ruleset mismatches, catalog drift, resource
caps, insufficient MP, curses, multiplayer, and unsupported actions fail
closed and reset recurrent state.

This adapter does not promote the candidate for live execution. A future live
gate still needs representative completed shadow games, decision agreement and
outcome criteria, an explicit promotion record, and separately confirmed
deployment authority.
