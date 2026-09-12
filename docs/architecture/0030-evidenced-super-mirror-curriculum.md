# ADR 0030: Evidenced Super Mirror curriculum

- Status: **Accepted**
- Date: 2026-09-12
- Amends: ADR 0029

## Context

The accepted Bible identifies Super Mirror as armor that can "Reflect anything",
but that description alone does not establish the interactive turn order. Four
official Training recordings now provide the missing transition evidence:

- `1938d8aa-5067-4d65-9acd-476cb41c38cd` reflected Hard Hammer's ATK6;
- `31d2ebb0-f1da-4f5b-ad7a-d9829d055eba` reflected Flash Dagger's ATK2;
- `45af831f-4e75-4885-aac0-c36593ad27f7` reflected Violent Flail's ATK14; and
- `87321ad1-18bb-40ad-b1e8-c4cf3d47f616` reflected Direct Smash Axe's ATK12.

In each recording, attack confirmation changed the official action to Reflect
with Super Mirror without changing HP. The original attacker then received a
normal defense decision against the original attack. Choosing Forgive dealt the
full original attack value to that attacker.

The recordings do not establish repeated reflection chains, bounce target
selection, or the ordering of miracle-block effects.

## Decision

Add `reflection-resource-hand` as a distinct native ruleset layered on
`expanded-resource-hand`. It adds the Bible-verified Super Mirror to a 127-card
catalog and preserves observation schema v6, the 14 global inputs, and the
21-action sequential head.

Super Mirror is sampled as part of the armor family. During an unresolved
defense it is an exclusive selection: it cannot be combined with numeric armor.
Confirmation consumes and redraws the armor, preserves the pending attack's
value, element, and automatic effect, and transfers the defense decision to the
original attacker. That player may then use compatible numeric armor or
Forgive. The reflector becomes the source for damage attribution and automatic
effects.

Only one reflection is allowed per attack. Reflection armor is masked during
the redirected defense, making the evidenced curriculum bounded while avoiding
an invented chain-resolution rule. The native batch exposes `pending_reflected`
for diagnostics and transition tests; the neural observation shape is unchanged
because reflected defense uses the same choices and consequences as an ordinary
incoming defense after the mask is applied.

The heuristic preserves Super Mirror when available numeric armor can prevent
lethal damage. It uses the mirror when no numeric defense is legal or when the
combined available numeric defense would still be lethal, then confirms the
exclusive reflection selection.

## Validation

The full repository suite passes with 315 tests. Ruff, mypy, and `git diff
--check` also pass. A release-build benchmark at batch size 4,096 completed
4,096,000 transitions at approximately 8.23 million transitions per second.

An end-to-end CPU smoke run initialized `reflection-resource-hand` from an
existing schema-v6 checkpoint, completed one heuristic teacher update and one
PPO update, and wrote a schema-v3 candidate manifest with 21 actions and 14
global inputs. This verifies checkpoint compatibility without treating the
smoke candidate as a performance result.

## Consequences

Native self-play can now learn a real reactive defense and the tactical cost of
redirecting a strong attack. Existing schema-v6 checkpoints can enter the new
curriculum without weight migration, while the distinct ruleset and catalog
fingerprints prevent results from being mixed with earlier evaluations.

This ruleset remains non-promotable. Reflection Sword, repeated reflections,
bounce, miracle blocking, counterattack rings, status effects, guardians,
phenomena, and the CP purchase economy remain separate evidence-gated
increments.
