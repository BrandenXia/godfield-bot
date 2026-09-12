# ADR 0032: Dual-role weapon curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0031

## Context

Seven accepted Bible entries have exact fixed attack and defense values:

- Saver Rod (`ATK2`, `DEF6`);
- Spiked Belt (`ATK4`, `DEF2`);
- Plate of Strike (`ATK5`, `DEF7`);
- Elbow Sack (`ATK6`, `DEF3`);
- Sword Shield (`ATK10`, `DEF10`);
- Legendary Scabbard (`ATK13`, `DEF1`); and
- Flaming Roll (Fire `ATK4`, `DEF4`).

Three direct API recordings verify that these weapon-category items participate
in ordinary numeric defense and are consumed. Run
`e4a7956e-4224-4eae-9112-72a2ff613a34`, transition 772, used Saver Rod against
ATK4 and took no damage. Run `98afab8d-70a8-400a-b917-ab983a70e51c`,
transition 162, used Saver Rod against ATK5 and took no damage. Run
`ccdd5148-ab08-4b9c-9ac3-989ead713c55`, transition 46, used Plate of Strike
against ATK9 and took 2 damage. In all three, the selected instance disappeared
from the hand after resolution.

The established elemental armor rule supplies the remaining interpretation:
the item's single combat element governs defense compatibility as well as its
attack. No special target or follow-up decision is involved.

## Decision

Add `dual-role-resource-hand` as a distinct native ruleset layered on
`reflection-weapon-resource-hand`. It adds all seven exact ATK/DEF entries,
producing a 135-card catalog while preserving observation schema v6, 14 global
inputs, and the 21-action sequential head.

Each dual-role card is sampled as part of the weapon family and satisfies the
attack-liveness invariant. On an attack turn it behaves as a weapon base and
contributes its ATK value. On a defense turn it behaves as ordinary numeric
armor, contributes its DEF value, follows the existing elemental compatibility
rule, and may be combined with other compatible numeric defenses. Confirmation
consumes and redraws it from the full catalog.

ATK and DEF remain distinct internal values for the same visible token. The
active phase and legal-action mask determine which value is applied, so no new
neural feature or action is necessary. The heuristic likewise indexes the token
in both its attack and defense value tables.

## Consequences

Native self-play can learn the opportunity cost of attacking with a flexible
card versus retaining its defense value, including the asymmetric tradeoffs of
high-ATK/low-DEF and low-ATK/high-DEF items. Existing schema-v6 checkpoints are
shape-compatible, while the new ruleset and catalog fingerprints isolate its
trajectories and evaluations.

This ruleset remains non-promotable. Bouncing Sword target selection, miracle
reflection and blocking, repeated reflections, counterattack rings, status
effects, guardians, phenomena, and the CP purchase economy remain separate
evidence-gated increments.

Effect-free chance weapons and the chance/defense dual role of Jinn's Rocking
Horse are addressed by ADR 0033.

## Validation

- The full Python and native-integrated suite passes with 324 tests.
- Ruff, mypy across 49 source files, the uv lock check, and the repository diff
  check pass.
- A 4,096,000-transition native benchmark completed at approximately 8.20
  million transitions per second on the development machine.
- A CPU teacher-warm-start plus PPO smoke run produced schema-v3 candidate
  `45bbc6ff-6a19-48fd-9381-a281f06f8aad`. Its training context records
  observation schema v6, 21 actions, 14 global features, the 135-card catalog,
  and heuristic policy `evidenced-dual-role-resource-combo-v1`.
