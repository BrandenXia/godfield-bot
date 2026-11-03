# ADR 0110: Inventory lifecycle integration source audit

## Status

2026-10-02, implementation preparation following the tested v8 counter milestone.
This is a source audit and integration checklist, not new executable card
coverage or training readiness. The engine remains native 0.57.0, 212/237 held
models, with full-game training, official fidelity and promotion false.

The v8 changes are locally saved and tested but not committed: Git staging was
not executed because approval review reported its usage limit. No alternate
Git write path is used. Local source inspection and documentation can proceed.

## Evidence that changes the next implementation

Sources retain the Oct 1 catalog and Sep 20 Bible/client pins documented in
ADR 0109. Saved client `A.aN.gkN` explicitly excludes sundry abilities `cutCost`,
`revive` and `attractDanger` from ordinary ready-phase card leaders. Bible Sun
Amulet says HP+10 when HP becomes zero; catalog model 208 has `revive`, value 10.
Therefore Sun Amulet is **passive**, not a player-chosen action that targets an
already eliminated seat. Adding a generic manual revival-target phase would
misrepresent the pinned contract.

The client `removeItems`/`removeUsedMiracles` dispatcher renders event-provided
`items` and resolves the opposite pending role when present. It does not show
an attacker selecting arbitrary victim instance IDs. Existing narrow Broom
evidence only proves removal of an explicit three-item server array and stable
survivor order. Existing Soap's selected-two primitive is a caller-driven
hypothesis, not proof of player-controlled selection. The engine must not expose
private victim identities as learner action choices simply because those old
diagnostic primitives accepted exact owned rows.

| Model | Catalog ability | Pinned contract | Still unverified |
| --- | --- | --- | --- |
| 205 Broom | removeItems | sweep three artifacts; performed miracles excluded | victim sampling, short hands, receipts and compound ordering |
| 206 Soap | removeUsedMiracles | wash two performed miracles | short eligible pools, sampling and receipts |
| 208 Sun Amulet | revive, value 10 | passive HP gain at zero HP, not ordinary leader | chain ordering, retained statuses, receipt cadence and multiple copies |
| 178 Dreaming Hat | selfCurseAndRedraw, Dream | Wood DEF14, catch Dream/redraw | redraw scope/timing and existing fake identities |
| 236 Treasure | boostCP, value 10, MP cost 5 | reusable CP-gain miracle | targeting/timing and local caps |

Removal counts and category restrictions are source-derived. Any uniform victim
sampling or minimum-of-count-and-eligible-pool rule must be explicitly
provisional, generated natively and separately versioned. Lack of an official
Soap event must remain visible; broad implementation must not rewrite the
strict replay admission rules or turn the curated Broom fixture into generic
official validation.

## Native integration requirements

1. Add a versioned passive lifecycle hook, not a public resource-write command.
   Check owned Amulets on every HP-zero transition: ordinary/Darkness damage,
   illness infliction, CP-payment spill and original-owner periodic illness.
   Consume only real owned instances, preserve survivor order, stage receipts,
   and resolve revival before any provisional liveness-dependent suppression
   or final winner check. Specify each compound ordering explicitly.
2. Do not resurrect a player on every idle step or merely because an Amulet was
   dealt after death. Avoid recursive revival loops; bound consumed copies by
   owned inventory and actual zero-HP transitions. Never represent revival as
   an unconditional reset of illness, masks, resources or inventory.
3. Add Broom/Soap target-and-response handling to the authoritative scheduler,
   using current pending source/target semantics and displayed legal choices.
   Victim selection belongs to staged native RNG, not hidden learner commands.
   Validate final actual identities before committing all environments.
4. Preserve used-miracle flags and order, including Dream display identities.
   Separate removed-card counters from ordinary consumption and never invent
   one replacement gift per victim without labeling that receipt rule.
5. Keep actor policy projections separate from full victim-hand diagnostics.
   A failed last environment must roll back earlier removals, revival,
   payments, native random tickets, status updates, receipts and queue changes.
6. Test revival at each death source, multiple copies, reflected/self-bounced
   hits, pending counter families, final survivor/outcome precedence, and
   repeated steps. Test Broom's used-miracle exclusion, Soap's used-only pool,
   partial pools, hidden identities, survivor order and whole-batch rollback.
7. Advance native/metadata/observation identities before joining these effects;
   preserve v8 diagnostics and existing arena/checkpoint/live identities.

This checklist continues the full-game objective. It does not substitute a
separate caller-driven primitive for the required joined game loop. Further
special attacks, economy, guardians/events, teams and complete neural
interfaces remain necessary after inventory lifecycle integration.
