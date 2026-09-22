# ADR 0051: Strict displayed-identity Dream curriculum

## Status

Accepted, 2026-09-21.

## Context

ADR 0050 deliberately withheld Dream simulation until official-client evidence
could establish its information boundary. Official-CPU run
`87cdd1a0-ab15-413f-a582-4adc36f738d7` retained Dream from G.F.4 through G.F.17.
Its 35 Dream samples contained 165 disguised-card observations and 95 differing
true/displayed model pairs. The client received the true ID, but the player UI
and selectable controls exposed the displayed card. No sampled disguise crossed
the true card's broad category. Existing cards remained truthful when Dream was
first applied; later received cards introduced disguises.

The accepted Bible identifies Bogus Spear as neutral ATK10 with on-damage Dream,
Dream Mallet as Wood ATK4 with on-damage Dream, and `<Dream>` as a reusable Wood
miracle costing 6 MP.

## Decision

Add cumulative `dream-resource-hand` on top of
`dark-cloud-resource-hand`. Native card kinds 40 and 41 represent Dream weapons
and the direct Dream miracle. Positive damage from either weapon inflicts Dream;
the direct miracle follows the existing miracle block, bounce, reflection, MP,
and reusable-card semantics. Mild and full cures clear Dream.

While a player is dreaming, every newly drawn ordinary fixed-value weapon or
armor independently has a 50% chance to receive a displayed identity sampled
uniformly from the same ordinary semantic catalog. Sampling may select the true
identity, matching observed same-ID fake assignments. Existing hand cards are
not retroactively disguised. Curing Dream restores the visible identity of all
held cards.

The environment stores separate true and displayed token, value, element, and
kind buffers. Neural tensors, heuristic decisions, action masks, and the public
pre-confirmation selection views use displayed data only. Confirmation and
combat resolve the hidden true card. The `actual_hand_token_ids` view exists
only for diagnostics and tests and is not part of `simulation_feature_tensors`.

Observation schema v10 appends actor-relative self- and opponent-Dream flags to
the schema-v9 vector for 24 global inputs. `models migrate-dream-features`
preserves every schema-v9 parameter and zero-initializes the two new columns.
The native package advances to 0.31.0.

## Safety boundary

This remains a non-promotable curriculum. The evidence only supports ordinary
fixed-value weapons and armor as disguise targets, so special weapons,
miracles, sundries, effect armor, and other categories remain truthful.
Dreaming Hat, Jupiter Ring, Dream guardians, multiplayer targeting, and
unverified effect-order combinations remain excluded. The native curriculum
does not authorize schema-v10 models for live browser control.

## Verification

Native and Python tests cover catalog extraction, schema and package exports,
damage-gated weapon infliction, direct-miracle cost/reuse/blocking, cure/reset
behavior, actor-relative flags, and the strict displayed-versus-true identity
boundary. A batched rollout must expose a value-changing weapon disguise and
prove that pre-confirmation observations contain the displayed value while
confirmation resolves the hidden true value. The full legacy simulator suite
also guards every earlier initial-deal and response path against displayed-view
regressions.
