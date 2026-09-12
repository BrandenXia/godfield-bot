# ADR 0036: Evidenced same-damage weapon curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0035

## Context

The accepted Bible defines Evil Broadsword as neutral `ATK14` with `Get the
same damage`; the API catalog names the ability `dealSameDamage`. The official
Training recorder contains nine confirmed uses by ロキ-67 and several uses by
the official opponent. These traces establish resolution ordering that is not
obvious from the card text.

Undefended nonlethal attacks remove 14 HP from both players. In run
`84f5a7b5-b3ca-4d18-a4db-6cb77ae7654d`, DEF5 reduced both players' loss to 9;
run `92b7550a-a7a8-4755-b367-cc9c6d1dfd8c` similarly reduced both losses to 8
with DEF6. DEF30 prevented both losses in run
`87321ad1-18bb-40ad-b1e8-c4cf3d47f616`.

The effect resolves only after a surviving target. In run
`4e7e889a-9097-4634-b743-b5035e8ae79d`, the bot entered defense at 5 HP, used
DEF3 against ATK14, and reached 0 HP; the official attacker remained at 15 HP
when the match ended. Conversely, run
`12e36926-278e-408a-ae22-5d6afbc617b7` records ロキ-67 using the weapon at 1 HP
against a 47-HP target: the target fell to 33 HP and the bot lost immediately.

No recorded official trace combines Evil Broadsword with Super Mirror or
Reflection Sword.

## Decision

Add `same-damage-weapon-resource-hand` as a distinct native ruleset layered on
`dynamic-mp-weapon-resource-hand`. It adds Evil Broadsword as a consumable
neutral weapon, producing a 155-card catalog while preserving observation
schema v6, 14 global inputs, and the 21-action sequential head.

After defense, the kernel computes ordinary penetrating damage. If the target
survives, that same post-defense amount is subtracted from the original weapon
user. If it defeats the user, the surviving defender wins. If the target is
defeated first, the match terminates and the same-damage effect does not run.
Zero penetrating damage has no secondary effect.

Schema v6's final effect feature is interpreted as a signed pending-attack
effect: `+1` remains HP absorption, `0` remains no modeled effect, and `-1`
identifies same-damage recoil. Existing rulesets therefore retain byte-for-byte
observation behavior while the new ruleset gives both neural seats enough
information to distinguish the response.

Because reflection composition has not been observed, reflection cards are
masked while a same-damage attack is pending. Numeric and elemental defense
remain available. This avoids inventing whether reflection redirects the
secondary loss or applies it twice to the original user.

The heuristic admits Evil Broadsword as ATK14 and preserves its safe finishing
case, because lethal target damage short-circuits recoil. If the attack would
defeat its user without defeating the opponent and another attack is legal,
the teacher chooses the non-suicidal alternative. The fallback remains
progress-preserving when every legal attack has that risk.

## Consequences

Native self-play can now learn the HP tradeoff, defense interaction, lethal
ordering, and self-KO outcome of Evil Broadsword without changing tensor
shapes. Existing schema-v6 checkpoints remain warm-start compatible, while the
new ruleset and 155-card catalog fingerprints isolate its trajectories and
evaluations.

This ruleset remains non-promotable. The unobserved reflection interaction,
multi-hit weapons, random targeting, status effects, Ascension, miracle
reflection and blocking, bounce, counterattacks, guardians, phenomena, and the
CP purchase economy remain separate evidence-gated increments.

## Validation

- The full Python and native-integrated suite passes with 342 tests. The new
  tests cover reduced shared damage, lethal-target short-circuiting, the signed
  effect observation, reflection masking, catalog construction, and heuristic
  suicide avoidance.
- Ruff, mypy across 49 source files, the uv lock check, and the repository diff
  check pass.
- A 4,096,000-transition native benchmark completed at approximately 8.27
  million transitions per second on the development machine.
- A CPU teacher-warm-start plus PPO smoke run produced schema-v3 candidate
  `2fed645e-bff3-4aed-a1b1-48c0dbc4aa01`. Its training context records
  observation schema v6, 21 actions, 14 global features, the 155-card catalog,
  and heuristic policy `evidenced-same-damage-weapon-resource-combo-v1`.
