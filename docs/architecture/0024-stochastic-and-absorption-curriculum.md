# ADR 0024: Stochastic and absorption miracle curriculum

- Status: **Accepted**
- Date: 2026-09-10
- Amends: ADR 0013

## Context

The schema-v5 resource curriculum models fixed attack miracles, HP/MP utility,
and miracle costs. The accepted Bible also gives exact values for six plain
percentage-hit attack miracles and one automatic attack effect: Absorption.
Leaving those cards outside native training creates a material gap between the
learned policy and live play.

Special armor is not included in this step. The catalog names bounce, reflect,
and block abilities, but it does not establish their authoritative ordering,
damage ownership, or interaction with absorption. Guessing those transitions
would produce fast but misleading training data.

## Decision

Add `stochastic-resource-hand` as a separate native ruleset with observation
schema v6. Schema-v5 behavior, fingerprints, and model lineage remain
unchanged. The new ruleset keeps the 21-action head and adds:

- the six audited percentage-hit attack miracles, including exact attack,
  element, MP cost, and hit rate;
- Absorption as a reusable light attack miracle that restores the attacker's
  HP by the defender's actual HP loss, capped at 100;
- one global binary feature indicating a pending absorption effect during the
  defense phase.

The simulator charges MP once on confirmation whether a chance miracle hits or
misses. A miss consumes the turn without entering the defense phase. Random
resolution uses the deterministic per-environment generator, so a seed fully
reproduces a rollout. Chance and effect miracles are reusable. The initial
nine-card deal contains two weapons, one booster, two armor, one utility, one
fixed miracle, one chance miracle, and one effect miracle. Redraws sample the
complete catalog while retaining weapon liveness.

The schema-v6 heuristic ranks chance miracles by expected attack but never
treats them as guaranteed lethal. A migration command expands the schema-v5
global encoder from 13 to 14 inputs and initializes the absorption input to
zero, preserving outputs for all schema-v5 observations.

## Consequences

Native self-play can train MP decisions under attack uncertainty and learn the
defensive implications of life-steal. Catalog fingerprints now cover 124
cards, including chance rates and effect identifiers. Existing schema-v5 live
shadow evidence remains valid and must not be mixed with schema-v6 evaluation.

Reflection, bounce, miracle blocking, curse/status effects, additive miracles,
guardians, trade, and phenomena remain future ruleset increments. Special
armor should be added only after tests encode the observed official-server
resolution order.

## Initial implementation evidence

`godfield-sim` 0.9.0 completed 262,144 schema-v6 transitions across 1,024
environments, including 3,854 finished episodes, at approximately 7.54 million
transitions per second. Migration node
`f411bdc8-ed21-46ee-a253-3d593601d5e1` expands schema-v5 candidate
`d349d664-bfce-4997-9ff9-eb94482c20d1` with a zero-initialized fourteenth
global input. An end-to-end 512-transition training smoke run produced
candidate `8050b75c-bcc3-4879-9470-7f027b3c7f14`; it validates the pipeline
only and is not evaluation evidence.
