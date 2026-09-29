# ADR 0076: Isolated provisional mechanics before full-game training

## Status

Accepted, 2026-09-29. The operator chose to layer provisional client/catalog
rules for future local training while keeping promotion gated on official
validation. This implements the first isolated primitive and identity, **not**
a training-ready full game. No official account, game, credential, model
checkpoint, live action policy, or promotion status changed.

## Source and hypothesis

The reviewed 2026-09-21 catalog (SHA-256
`df182c8a230876886f50ac83a79cf6aa7b737eec7b76279737e4cf6a1dcb6249`)
labels model 206/Goddess's Soap as the sundry `removeUsedMiracles`. The
reviewed 2026-09-20 Bible, client SHA-256
`764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`,
describes washing away two performed miracles. The catalog has 30 miracle
models. No official `removeUsedMiracles` event has been collected, so these
facts support only a **provisional effect hypothesis**.

The native `ProvisionalSoapProjection` is separate from
`OrderedInventoryReplay` and from all batched curricula. It accepts an
explicit caller-selected pair of exact owned, used, undisguised catalog
miracles, then removes both atomically without reordering survivors. This
models only the inventory projection under that selection. It does not choose
which miracles Soap removes, establish whether fewer than two can be removed,
pay the $10 cost, gift replacements, update combat, or infer a missing event.
The constructor validates instance IDs, model IDs, and the caller's miracle
allowlist; failed operations do not mutate state. Tests are synthetic and do
not count as official validation.

## Isolation and admission

Native package 0.37.0 exports provisional schema 1 and ruleset
`catalog-derived-selected-two-used-miracles-provisional-v1` without changing
observed replay schema 3 or any C++ training ruleset. The offline
`simulation provisional-soap-plan` command verifies the exact native identity
and catalog pin, then reports `provisional-unvalidated`, zero observed official
events, and false complete-game, local-training, official-validation, and
promotion eligibility. The primitive has no `step`/`reset` training API and
cannot be selected as a PPO curriculum or live policy. A future provisional
training curriculum must have its own schema/manifest/checkpoint identity;
mere existence of this primitive must never qualify one.

To validate Soap, collect an actual contiguous self-targeted
`removeUsedMiracles` event with an explicit item array, reliable preceding
defense selection, used flags, before/after inventory, and any later gifts.
The strict acquisition checker continues to reject Soap. If real evidence
differs, correct or retire this provisional hypothesis without rewriting
historical run or model identities. Promotion remains blocked until the
broader full-game rules, transport, and independent official performance
criteria are met.
