# ADR 0040: Illness cure curriculum

## Status

Accepted, 2026-09-13.

## Context

The accepted 2026-09-07 Bible snapshot identifies four status cures with exact
scope and ownership semantics. Smile Shell is a consumable sundry that erases
Cold, Fever, Fog, and Flash; Heart Shell erases every curse. Tone and Song have
the same respective scopes as reusable miracles costing 2 MP and 5 MP. The
accepted API catalog independently labels these pairs `removeMildCurses` and
`removeAllCurses`.

The schema-v7 curriculum represents Cold, Fever, Hell, and Heaven, but it does
not yet represent Fog or Flash. Keeping illness permanent therefore biases both
the heuristic teacher and learned value estimates.

## Decision

Add `illness-cure-resource-hand` as a distinct cumulative ruleset layered on
`illness-weapon-resource-hand`. It adds all four verified cures to a 165-card
catalog:

- Smile Shell and Tone cure modeled Cold/Fever only.
- Heart Shell and Song cure any modeled illness, including Hell/Heaven.
- A cure is legal only while it can affect the actor. Miracle cures additionally
  require their exact MP cost.
- Cure resolution is atomic and happens before the actor's end-turn illness
  effect. Sundries redraw from the cumulative catalog; miracles remain in hand.

The observation schema stays at version 7 with 16 global features because the
existing actor-relative illness-stage features already make cure legality and
effects Markov. The native package advances to 0.21.0, while the kernel schema
remains version 1.

The heuristic always takes a legal cure before nonlethal healing or attacks. For
Cold/Fever it prefers a mild cure over an all-curse cure, then lower MP cost and
lower slot index. For Hell/Heaven the action mask admits only all-curse cures.

## Safety boundary

The environment remains non-promotable. Mild cures do not create unrepresented
Fog or Flash state, and this milestone does not infer interactions beyond the
accepted catalog text. Heaven Herb, curse transfer, curse removal by defeat,
and curse interactions with other effects remain outside this ruleset.

The established status timing and worsening rules remain grounded in the
[current strategy wiki illness page](https://w.atwiki.jp/piong/pages/23.html)
and the [beginner wiki illness summary](https://godfield-beginner.game-info.wiki/).

## Verification

Parser tests pin all four exact cards and costs. Native tests cover healthy and
insufficient-MP masking, mild-versus-all scope, pre-tick cure timing, MP spend,
sundry redraw, miracle reuse, schema/catalog identity, and teacher priority.
The full 371-test regression suite passes with strict Ruff, mypy across 49
source files, lockfile, diff, and native-format checks. A 4,096-environment,
1,000-step benchmark sustained 7.50 million native transitions per second and
completed 71,418 episodes. A 1,024-transition teacher plus 1,024-transition PPO
smoke run initialized schema-v7 candidate
`60625a19-698d-48bf-9033-97c3b5e84812` from
`a8d616c9-edd8-4cb6-8b95-d5691a026a97`; a paired 64-game smoke evaluation
completed without timeouts or incomplete games.
