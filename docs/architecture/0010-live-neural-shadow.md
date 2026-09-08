# ADR 0010: Live neural combo shadow

- Status: **Accepted**
- Date: 2026-09-08
- Amends: ADR 0003 and ADR 0009

## Context

The schema-v4 combo candidate can select a base weapon, zero or more additive
weapons, several armor cards, and a final Confirm or Forgive action. The live
API submits the entire selection as one command instead of exposing those
intermediate choices. Native curriculum evaluation is useful evidence, but it
is explicitly not a live promotion gate and therefore cannot authorize a
candidate to control an account.

The integration needs to test the trained policy against real observations,
preserve the exact decisions needed for later evaluation, and keep matches
moving without assigning live control to an unpromoted model.

## Decision

Add `api-combo-neural-shadow-v1` to the private API runtime. It loads one
immutable candidate or champion together with the accepted Bible snapshot and
validates all of the following before joining a room:

- model, weight, client, vocabulary, feature-schema, and action-head identity;
- the exact `plain-elemental-combo-attack-defense-redraw-duel-v1` training
  ruleset and sequential combo action semantics;
- a checksummed API catalog captured by the pinned pygodfield revision.

The live legal-action bridge extends the conservative surface with bounded
plain-card macros. Each card's role, value, element, lack of an effect, and
zero-resource cost must match the accepted simulator record. An attack macro
is one effect-free base weapon followed by any subset of effect-free `+ATK`
weapons. A defense macro is a subset of at least two armor cards that
pygodfield independently accepts against the pending attack. Combinations are disabled whenever the bot
has a curse. Disguised cards, placeholders, special effects, resource prompts,
purchases, and cards outside the native curriculum are never included.

For a covered two-player state, the adapter reconstructs the sequential
21-action observation seen during training. Selected slots are hidden between
inference steps; aggregate attack power and element use schema-v4 semantics.
Confirm resolves the selected slots to exactly one verified API macro, which
can be represented as one `Command.use([...])`. Selection indices,
probabilities, value estimates, model ID, and weight checksum are written to
the append-only decision event.

Shadow proposals are always marked non-executable. `api-heuristic-v0` remains
the behavior policy and submits only its conservative single-card action. Both
decisions share the same state digest and are recorded in order. Recurrent
memory is retained only when proposal and behavior are identical; otherwise it
is cleared so a counterfactual combo does not contaminate the next live
observation. Lobby, terminal, cursed, unsupported, and multiplayer states also
clear memory.

The CLI enables this mode by supplying `--shadow-model` to the existing
explicitly confirmed `api play-private` command. The independent action,
no-progress, request, and optional wall-clock bounds remain in force.

## Consequences

The trained candidate now receives real private-game observations and produces
fully reconstructable combo proposals without controlling the account. The
resulting run contains the behavior action, shadow action, transition, and
terminal reward needed to design a live comparison gate.

The shadow data is not yet promotion evidence by itself. Before learned combo
commands can be executable, the project still needs a versioned live gate,
enough representative completed games, an explicit promotion operation, and a
separate confirmation surface for champion deployment.
