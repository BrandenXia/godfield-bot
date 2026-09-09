# ADR 0016: Versioned Sell dead-end recovery

- Status: **Accepted**
- Date: 2026-09-09
- Amends: ADR 0003, ADR 0011, and ADR 0015

## Context

Private run `b9b1fd1f-ea45-4b55-995b-38a731fea9ed` safely aborted after six
accepted commands when the bot reached its own cursed turn with 14 HP and 4
MP. Its hand had no base weapon, affordable miracle, curse cleanser, or utility.
It did contain Sell and four armor cards, but the reviewed tactical surface
excluded all trade actions and therefore exposed no command.

The pinned protocol documentation and live-client-derived upstream tests model
Sell as a non-damaging two-card action: Sell followed by the offered artifact,
with an opponent target. The public Bible says miracles cannot be sold. This is
enough evidence for a narrow recovery without designing general trade policy.

## Decision

Add Sell actions only when all of these checks pass:

- the leading card has reliable identity, category `trade`, asset and ability
  `sell`, and the upstream model says it needs a target;
- the offered card has reliable identity and exactly matches a plain armor
  record in the accepted Bible by asset, defense, element, cost, and absence of
  special ability;
- the target is a living non-team opponent selected by pygodfield's reviewed
  opponent resolver.

The deterministic behavior policy uses this only after attacks, curse attacks,
and HP/MP utilities are unavailable. It offers the weakest eligible armor to
the healthiest eligible opponent, then uses stable target and instance-ID ties.
Buy, Exchange, Discard, Sacrifice, miracle sales, purchase acceptance, and
arbitrary special-card sales remain outside the action surface.

Version the changed behavior as `api-combo-utility-heuristic-v2`. Version the
live readiness contract as `live-resource-shadow-readiness-v2`, report schema
2, so no v1 behavior evidence can satisfy the new gate.

Also update the exact pygodfield pin from `b33a312` to `0673312`. The reviewed
upstream change prevents pending death attacks, diseases, and guardians from
being mistaken for completed games. A newly fetched 2026-09-09 English catalog
still contains 296 models and retains content checksum
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`.

## Consequences

The captured failure state now has a verified action that serializes to Sell
plus Leather Cap targeted at the opponent. An opponent may still decline the
offer; that is normal game progress. Unknown trade shapes continue to fail
closed, and the neural resource policy remains non-executable and abstains on
cursed states.
