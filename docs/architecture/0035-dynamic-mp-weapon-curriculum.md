# ADR 0035: Evidenced dynamic-MP weapon curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0034

## Context

The accepted Bible defines Magical Stick as `ATK{2×MP}` with `Consume all the
MP`. A consistent backup of the official Training recorder contains eight
successfully confirmed Magical Stick attacks. In every recorded use, the bot
had 10 MP, the client rendered `ATK20`, and the next actionable state showed
the bot at 0 MP. Run `26d6e9bc-1800-44ec-a7d4-e3732d9f8e4c` additionally shows
the ATK20 response being reflected while the original user still pays all 10
MP. An observed official opponent combination rendered Magical Stick plus
Blowgun as ATK21, supporting ordinary additive weapon composition.

The existing resource curriculum already observes current MP, enforces miracle
costs, and carries attacks through one-hop reflection. Magical Stick can
therefore be added without changing the model interface. The official ordering
of paid additive miracles with an all-MP weapon is not yet evidenced.

## Decision

Add `dynamic-mp-weapon-resource-hand` as a distinct native ruleset layered on
`absorption-weapon-resource-hand`. It adds Magical Stick as a consumable
non-element weapon, producing a 154-card catalog while preserving observation
schema v6, 14 global inputs, and the 21-action sequential head.

The catalog stores the Bible coefficient, not a fixed attack. Selecting Magical
Stick as the base snapshots the acting player's current MP, sets the selected
attack to `coefficient × MP`, and reserves all current MP as the selection cost.
Confirmation consumes the weapon and reduces that player's MP to zero before
opening defense. Subsequent MP changes cannot alter the pending attack, and
reflection transfers the already-snapshotted attack without refunding MP.

Zero-cost additive weapons remain legal after Magical Stick and add normally.
Paid additive miracles are conservatively illegal because all available MP is
already reserved; their official ordering remains outside this increment.
Selecting Magical Stick at 0 MP is legal and consumes it as an ATK0 action,
preserving turn progress and redraw liveness.

The heuristic stores dynamic-MP coefficients separately from fixed attack
values. It ranks Magical Stick using current MP, recognizes guaranteed lethal
damage at that resolved value, and can prefer an available MP utility when the
restored dynamic attack would exceed every currently legal attack.

## Consequences

Native self-play can learn whether to spend or retain MP for a deterministic
weapon attack, including zero-cost weapon boosts, defense, and one-hop
reflection. Existing schema-v6 checkpoints remain shape-compatible, while the
new ruleset and 154-card catalog fingerprints isolate trajectories and
evaluations.

This ruleset remains non-promotable. Paid-miracle composition with Magical
Stick, status effects, Ascension, multi-hit attacks, miracle reflection and
blocking, bounce, counterattacks, guardians, phenomena, and the CP purchase
economy remain separate evidence-gated increments.

## Validation

- The full Python and native-integrated suite passes with 336 tests.
- Ruff, mypy across 49 source files, the uv lock check, and the repository diff
  check pass.
- A 4,096,000-transition native benchmark completed at approximately 8.23
  million transitions per second on the development machine.
- A CPU teacher-warm-start plus PPO smoke run produced schema-v3 candidate
  `85fd7579-4a3c-4a2b-8290-2bcd60245f5f`. Its training context records
  observation schema v6, 21 actions, 14 global features, the 154-card catalog,
  and heuristic policy `evidenced-dynamic-mp-weapon-resource-combo-v1`.
