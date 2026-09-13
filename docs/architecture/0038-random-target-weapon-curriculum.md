# ADR 0038: Evidenced random-target weapon curriculum

- Status: **Accepted**
- Date: 2026-09-13
- Amends: ADR 0037

## Context

The accepted Bible defines Dangerous Pestle as Light `ATK30` with `Attack
somebody`; the accepted API catalog identifies model 94 with ability `danger`.
Official recordings establish that its requested target is not authoritative.
In private API run `25338ece-15b2-4d5c-86b3-c774ae7bca0b`, player 3 submitted
`use:8:94:4`, but the resulting pending attack named player 2 as the target.

The random set includes the attacker. Training run
`57960f7d-b634-4f30-b890-cde23e6f48a2` records the bot confirming Dangerous
Pestle against the displayed opponent while at 9 HP. The next state has no
defense prompt, the bot falls to 0 HP, the opponent remains at 50 HP, and the
match records a bot loss. By contrast, run
`f52d32b3-db4e-4c57-b3f2-1620f7f01507` selects the opponent and presents a
normal response before the opponent loses 27 HP and the match ends. Other
recordings include multi-card official-bot responses, but their hidden card
identities do not establish general booster, reflection, or special-defense
composition.

## Decision

Add `random-target-weapon-resource-hand` as a distinct native ruleset layered
on `attack-twice-weapon-resource-hand`. It adds Dangerous Pestle as a
consumable Light ATK30 weapon and produces a 157-card catalog while retaining
observation schema v6, 14 global inputs, and the 21-action sequential head.

The recordings establish the two possible targets but do not expose their
weighting, so the duel curriculum adopts the minimal symmetric assumption: on
confirmation, the kernel samples uniformly from both living players. An
opponent result opens the ordinary defense phase. A self result applies the
full attack immediately without offering the attacker a defense decision,
then passes the turn if the attacker survives. A lethal self result awards the
other player the win. This generalizes terminal ownership so an attacker's
self-KO cannot incorrectly produce an attacker win.

The selected card token identifies the risk before confirmation. After an
opponent is selected, the pending attack is tactically ordinary, so schema
v6's final effect feature remains zero and the observation shape stays
compatible. Attack boosters are masked after Dangerous Pestle selection, and
reflection is masked during its opponent response because neither composition
has an exact official trace in the accepted evidence set.

The heuristic ranks Dangerous Pestle at 15 expected opponent damage in a
two-player game, excludes it from deterministic lethal finishes, and avoids it
when its ATK30 could self-KO and another known attack is legal. It remains a
last-resort action when no safer attack exists, preventing teacher deadlocks.

## Consequences

Native self-play can now learn a high-variance action whose target sometimes
changes the acting player's HP and terminal reward, rather than approximating
Dangerous Pestle as a directed ATK30. Existing schema-v6 checkpoints remain
shape compatible, while the distinct ruleset, catalog, and sampling
fingerprints prevent trajectory mixing with earlier curricula.

This ruleset remains non-promotable. Multiplayer target distributions,
random-target composition with boosters or reflection, status effects,
Ascension, miracle reflection and blocking, bounce, counterattacks, guardians,
phenomena, and the CP purchase economy remain separate evidence-gated
increments.

## Validation

- Strict parser coverage verifies the Bible text and Light element.
- Native tests cover both sampled targets, immediate nonlethal self-damage,
  lethal self-KO ownership, the opponent response, and composition masks.
- Factory and configuration tests cover the new class, 157-card catalog,
  ruleset metadata, training/evaluation selection, and benchmark alias.
- The teacher tests cover expected-value ranking, stochastic-lethal handling,
  optional self-KO avoidance, and last-resort liveness.
- The full Python and native regression suite passes together with strict Ruff,
  mypy, lockfile, diff, and native-format checks.
- A 4,096-environment, 1,000-step benchmark sustained 7.86 million native
  transitions per second and completed 65,765 episodes.
- A 1,024-transition CPU teacher-plus-PPO smoke run produced schema-v6
  candidate `15e14d6f-71a1-4622-93bd-a81243259660` with the 157-card catalog
  and `evidenced-random-target-weapon-resource-combo-v1` teacher recorded in
  its immutable manifest.
