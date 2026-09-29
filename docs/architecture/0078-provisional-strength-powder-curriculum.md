# ADR 0078: Version the first provisional rule admitted to local training

## Status

Accepted, 2026-09-29. The operator approved layered provisional rules with
promotion gated on official validation. This rule is opt-in; it does not
change official-game control or existing model checkpoints.

## Source and limited rule

The pinned 2026-09-20 Bible labels Strength Powder `+ATK10` with a gift rate
of 2/500. The pinned 2026-09-21 API catalog identifies model 203 as a sundry
with `atk: 10` and `isPlusAtk: true`. Their reviewed hashes and exact fields
are checked at construction. No contiguous official Strength Powder combat
trace has been used to verify its interactions.

The opt-in `provisional-strength-powder-wide-hand` curriculum adds its sundry
token to the existing C++ additive-booster catalog with non-element and value
10. It inherits the 18-slot gift-weighted Dream curriculum's phases and
sampling. No new C++ effect implementation is invented: it reuses the tested
native additive primitive. This is a **hypothesis** that the catalog's
`isPlusAtk` maps to that primitive, not proof of official parity.

The rule catalog hash and `provisional-strength-powder-v1-` ruleset ID differ
from the evidenced wide-hand curriculum, whose hash remains unchanged. The
training config and heuristic recognize the extra booster. A deterministic
batch test confirms sampling, legal heuristic actions, and 197 unique catalog
tokens; a one-update PPO smoke test confirms the opt-in path can train locally.
The separate coverage report still declares 94 omitted artifacts, false
full-game training readiness, false official fidelity, and false promotion
eligibility.

## Validation and next work

Collect and review an official Strength Powder attack-combination trace before
claiming this effect is faithful. Migrate no old checkpoints implicitly;
compare candidates only against opponents with compatible observation and
ruleset identities. The provisional Soap primitive remains outside the
batched kernel. Larger missing systems (especially guardians and phenomena)
need explicit state/action/effect contracts, not blanket catalog admission.
