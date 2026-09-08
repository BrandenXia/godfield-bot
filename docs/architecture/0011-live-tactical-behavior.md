# ADR 0011: Live tactical behavior baseline

- Status: **Accepted**
- Date: 2026-09-08
- Amends: ADR 0003 and ADR 0010

## Context

The first two completed neural-shadow games were both losses. Their recorded
states exposed a deployment gap rather than a narrow-curriculum training
failure: the behavior policy repeatedly held deterministic HP and MP recovery,
could not use affordable fixed-damage miracles, and selected one armor card
when the verified bridge exposed a sufficient multi-card defense. The combo
candidate had already passed three 4,096-game native gates, but its learned
policy is not authorized for live control.

Changing the meaning of `api-heuristic-v0` would invalidate historical run
identity. Giving the candidate control would bypass the planned live gate.

## Decision

Add `api-combo-utility-heuristic-v1` as a separate, deterministic live behavior
policy and make it the default behind the existing `--confirm-play` gate. Keep
`api-heuristic-v0` readable and executable for reproducibility.

The v1 legal-action surface is the union of:

- individually reliable actions already admitted by pygodfield;
- Bible/API-cross-checked plain base-plus-booster attacks;
- Bible/API-cross-checked compatible armor combinations;
- untargeted `boostHP` and `boostMP` sundries or miracles with known values;
- affordable, targeted, fixed-attack miracles with no additional ability;
- affordable, targeted `addCurse` miracles;
- special block, bounce, and reflect defenses already admitted as compatible
  by pygodfield's defense validator.

The policy removes all curses first when a verified cleanser is present. It
then takes the least expensive attack with potentially lethal power, heals at
25 HP or less, uses the highest verified attack value, restores MP when
otherwise idle, and passes only as a final verified fallback. Defense selects
the smallest total DEF that prevents all damage, otherwise the largest
available total DEF.

If this executable surface still yields no action while the server is awaiting
the bot, the runtime records the decision and stops immediately with
`unsupported_self_turn`. It does not wait for the generic no-progress limit or
submit a speculative command. Observer-only runs retain their prior behavior.

API game state schema v4 adds `ability_value` and `is_plus_attack` to each
private hand item. All decisions, legal sets, commands, and transitions remain
append-only evidence. The neural candidate continues in shadow: it filters the
larger legal set back to its exact schema-v4 combo curriculum and never
executes a utility or miracle action it has not learned.

## Consequences

The live bot can now use the strongest already-reviewed parts of its hand and
should no longer die while deterministically useful recovery cards remain
unused. The policy also becomes a stronger behavior-cloning teacher and a more
meaningful baseline for a future live neural gate.

This is still not full God Field. Mild-curse classification, random attacks,
trades, purchases, guardians, phenomena, most discretionary miracle effects,
and learned resource timing remain outside the executable surface. The next
native curriculum should model HP/MP utility and miracle costs before the
network can control those actions.
