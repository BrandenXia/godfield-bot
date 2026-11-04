# Rare mechanics through terminal learning

The roster probe in ADR0149 finished all 256 games but did not encounter hand
overflow, protected hidden removals, or unaffordable hidden utility/defense
costs. Existing native tests proved those rules in short scripted transitions;
they did not prove that complete neural trajectories containing those branches
could enter the optimizer. Add 21 targeted tests to close that specific gap.

## Real public behavior and terminal targets

The fixtures initialize actual version 3 recurrent networks with explicit
weights. Public displayed model embeddings favor particular cards, public
selection ranks discourage toggling selected defenses/removals, and public
phase features favor confirmation. They use the normal controller and sampling
path. No actions or logits are substituted, no hidden card is supplied as a
policy feature, and no scripted action is mislabeled as a sampled neural move.
These diagnostic initial weights are not competitive candidates or demonstrations
added to the normal training distribution.

Each case starts at a real zero-command episode boundary. Collection must end
in a native winner/draw, retain every accepted decision, and have no error or
truncation. Behavior replay verifies probabilities, values and each seat's
memory. Terminal targets are independently checked against the native outcome
for the acting seat. The actual recurrent PPO optimizer must produce finite
metrics and change both the action head and the zero-initialized public-card
projection; a change confined to the value head cannot satisfy these tests.
Diagnostic preferences are deliberately not so certain that every relevant
action probability rounds to one and prevents actor learning.

## Cases and scope

All cases run with 2, 4 and 9 seats, supplementing the complete 2–9 roster matrix.
They preserve cap99, native kernel33 and all pinned profiles.

| Scenario | Required native result | Learning check |
| --- | --- | --- |
| Expensive hidden healing | Spring displayed as a two-MP cure asks for seven MP, pays two, applies no healing | Terminal targets remain valid; forced opponents have zero actor weight |
| Expensive hidden defense | An apparent filter/Wall/reducer combination has a real six-MP deficit | The incoming Darkness attack kills the defender; its four response decisions retain loss targets |
| Protected removal | Sun Amulet or Dangerous Mortar disguised as an ordinary sundry cannot be discarded or sacrificed | The accepted confirmation remains a voluntary learning row even though removal fails |
| Full-pool overflow | Reusing Fireball grants enough weighted gifts to evict the oldest card at the 18-card cap | A full hand is observed and the episode reaches a real winner before optimization |

Protected removal crosses two protected actual cards and both virtual actions,
giving 12 cases. The other three families each give three cases, for 21 total.
Utility/defense/removal cases use the existing explicitly manual acquisition
mode to isolate their initial hands. They are not relabeled as random opening
deals. Illness provides the terminal continuation without synthetic rewards;
Sun revival is still resolved normally.

Overflow uses the normal `all-held-weighted` mode, its unchanged 237-model pool,
99 starting HP/MP, and opening seed4. Only two seats are living in the larger
overflow layouts; the other seats remain present and eliminated. This isolates
the rare inventory condition, while the earlier roster matrix supplies evidence
for ordinary all-living multiplayer play. No capacity, replacement distribution,
hidden-cost rule, native action mask or live control was changed.

## Verification and remaining acceptance work

Run the targeted cases with:

```bash
UV_CACHE_DIR=.uv-cache uv run --frozen --extra simulation --extra training \
  pytest tests/test_full_game_mechanic_learning.py
```

All 21 cases pass with real action-head and card-projection updates. The broader
non-browser suite passes 13,261 tests; the strengthened actor/projection assertions
also pass in a subsequent focused run. Ruff, changed-file formatting and
whitespace checks pass. These fixtures
establish optimizer integration for the named branches, not a learned preference
for a good move, improvement against opponents, or official behavioral fidelity.

The next acceptance step is an explicit integrated artifact/workflow ledger
against ADR0097, linking the source-pinned routes to their native interaction
tests and these complete-episode learning results. The older guardian-arena
`full-game-readiness` report must not be used as the current integrated engine's
audit. Historical checkpoint metadata and all live-promotion flags remain as
recorded; no readiness claim is upgraded by these tests alone.
