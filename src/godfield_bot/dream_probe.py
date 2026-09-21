from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, cast

from playwright.async_api import BrowserContext, Page
from pydantic import BaseModel, Field

from godfield_bot.api_catalog import ApiCatalogSnapshot


class DreamProbeError(RuntimeError):
    """Raised when browser evidence cannot satisfy the probe contract."""


class DreamProbePhase(StrEnum):
    WAIT = "wait"
    TURN = "turn"
    DEFENSE = "defense"
    PURCHASE = "purchase"
    TERMINAL = "terminal"


class DreamProbeCatalogIdentity(BaseModel):
    model_id: int = Field(gt=0)
    name: str | None = None
    asset: str | None = None
    category: str | None = None
    cost: int = Field(default=0, ge=0)

    @property
    def image_path(self) -> str | None:
        if self.asset is None or self.category is None:
            return None
        return f"/images/items/{self.category}/{self.asset}.webp"


class DreamProbeRenderedCard(BaseModel):
    slot: int = Field(ge=0)
    path: str
    x: float
    y: float
    selectable: bool


class DreamProbeItemEvidence(BaseModel):
    instance_id: int | None = Field(default=None, gt=0)
    raw_index: int = Field(ge=0)
    slot: int | None = Field(default=None, ge=0)
    true_identity: DreamProbeCatalogIdentity | None = None
    displayed_identity: DreamProbeCatalogIdentity | None = None
    rendered_path: str | None = None
    selectable: bool | None = None
    used: bool = False
    disguised: bool
    rendered_matches_displayed: bool | None = None


class DreamProbeSample(BaseModel):
    schema_version: Literal[1] = 1
    observed_at: datetime
    source_sequence: int = Field(ge=1)
    field_number: int = Field(ge=0)
    update_count: int = Field(ge=0)
    phase: DreamProbePhase
    self_player_id: int = Field(gt=0)
    attack_turn_player_id: int | None = Field(default=None, gt=0)
    awaiting_player_id: int | None = Field(default=None, gt=0)
    dream_active: bool
    player_count: int = Field(ge=1)
    items: tuple[DreamProbeItemEvidence, ...]
    rendered_cards: tuple[DreamProbeRenderedCard, ...]
    hand_alignment: Literal[
        "exact",
        "ambiguous",
        "count_mismatch",
        "rendered_mismatch",
    ]


class DreamProbeFinding(BaseModel):
    field_number: int = Field(ge=0)
    update_count: int = Field(ge=0)
    phase: DreamProbePhase
    instance_id: int | None = Field(default=None, gt=0)
    true_model_id: int | None = Field(default=None, gt=0)
    true_category: str | None = None
    displayed_model_id: int | None = Field(default=None, gt=0)
    displayed_category: str | None = None
    selectable: bool | None = None
    rendered_matches_displayed: bool | None = None


class DreamProbeReport(BaseModel):
    schema_version: Literal[1] = 1
    sample_count: int = Field(ge=0)
    dream_active_sample_count: int = Field(ge=0)
    exact_alignment_count: int = Field(ge=0)
    disguised_item_observation_count: int = Field(ge=0)
    distinct_disguised_instance_count: int = Field(ge=0)
    true_identity_known_count: int = Field(ge=0)
    true_identity_hidden_count: int = Field(ge=0)
    cross_category_disguise_count: int = Field(ge=0)
    self_action_phase_disguise_count: int = Field(ge=0)
    findings: tuple[DreamProbeFinding, ...]


def dream_probe_sample_digest(sample: DreamProbeSample) -> str:
    canonical = sample.model_dump_json(exclude={"observed_at"})
    return hashlib.sha256(canonical.encode()).hexdigest()


def summarize_dream_evidence(
    samples: tuple[DreamProbeSample, ...],
) -> DreamProbeReport:
    findings: list[DreamProbeFinding] = []
    distinct_instances: set[int] = set()
    true_identity_known_count = 0
    true_identity_hidden_count = 0
    cross_category_disguise_count = 0
    self_action_phase_disguise_count = 0
    for sample in samples:
        for item in sample.items:
            if not item.disguised:
                continue
            if item.instance_id is not None:
                distinct_instances.add(item.instance_id)
            if item.true_identity is None:
                true_identity_hidden_count += 1
            else:
                true_identity_known_count += 1
            if (
                item.true_identity is not None
                and item.displayed_identity is not None
                and item.true_identity.category != item.displayed_identity.category
            ):
                cross_category_disguise_count += 1
            if sample.phase in {
                DreamProbePhase.TURN,
                DreamProbePhase.DEFENSE,
                DreamProbePhase.PURCHASE,
            }:
                self_action_phase_disguise_count += 1
            findings.append(
                DreamProbeFinding(
                    field_number=sample.field_number,
                    update_count=sample.update_count,
                    phase=sample.phase,
                    instance_id=item.instance_id,
                    true_model_id=(
                        item.true_identity.model_id if item.true_identity is not None else None
                    ),
                    true_category=(
                        item.true_identity.category if item.true_identity is not None else None
                    ),
                    displayed_model_id=(
                        item.displayed_identity.model_id
                        if item.displayed_identity is not None
                        else None
                    ),
                    displayed_category=(
                        item.displayed_identity.category
                        if item.displayed_identity is not None
                        else None
                    ),
                    selectable=item.selectable,
                    rendered_matches_displayed=item.rendered_matches_displayed,
                )
            )
    return DreamProbeReport(
        sample_count=len(samples),
        dream_active_sample_count=sum(sample.dream_active for sample in samples),
        exact_alignment_count=sum(
            sample.hand_alignment == "exact" for sample in samples
        ),
        disguised_item_observation_count=len(findings),
        distinct_disguised_instance_count=len(distinct_instances),
        true_identity_known_count=true_identity_known_count,
        true_identity_hidden_count=true_identity_hidden_count,
        cross_category_disguise_count=cross_category_disguise_count,
        self_action_phase_disguise_count=self_action_phase_disguise_count,
        findings=tuple(findings),
    )


def _dream_probe_init_script(identity: str) -> str:
    encoded_identity = json.dumps(identity, ensure_ascii=False)
    return f"""
    (() => {{
      const identity = {encoded_identity};
      const key = '__godfieldDreamEvidenceV1';
      if (window[key]) return;
      const state = {{schemaVersion: 1, sequence: 0, latest: null, hookErrors: 0}};
      Object.defineProperty(window, key, {{value: state, configurable: false}});

      const positiveInteger = (value) =>
        Number.isInteger(value) && value > 0 ? value : null;
      const nonnegativeInteger = (value) =>
        Number.isInteger(value) && value >= 0 ? value : 0;
      const sanitizeItem = (item) => {{
        if (!item || typeof item !== 'object') return null;
        return {{
          instance_id: positiveInteger(item.id),
          model_id: positiveInteger(item.modelId),
          fake_model_id: positiveInteger(item.fakeModelId),
          used: item.used === true,
        }};
      }};
      const sanitizeAttack = (attack) => {{
        if (!attack || typeof attack !== 'object') return null;
        return {{
          player_id: positiveInteger(attack.playerId),
          target_player_id: positiveInteger(attack.targetPlayerId),
          buying_item_model_id: positiveInteger(attack.buyingItemModelId),
        }};
      }};
      const capture = (snapshot) => {{
        try {{
          const room = snapshot && typeof snapshot.data === 'function'
            ? snapshot.data()
            : null;
          const game = room && typeof room.game === 'object' ? room.game : null;
          if (!game || !Array.isArray(game.players)) return;
          const matches = game.players.filter(
            (player) => player && player.name === identity
          );
          if (matches.length !== 1) return;
          const self = matches[0];
          const items = Array.isArray(self.items)
            ? self.items.map(sanitizeItem).filter(Boolean)
            : [];
          const attacks = Array.isArray(game.attacks)
            ? game.attacks.map(sanitizeAttack).filter(Boolean)
            : [];
          state.sequence += 1;
          state.latest = {{
            source_sequence: state.sequence,
            field_number: nonnegativeInteger(game.gf),
            update_count: nonnegativeInteger(game.updateCount),
            attack_turn_player_id: positiveInteger(game.attackTurnPlayerId),
            is_over: game.isOver === true,
            player_count: game.players.length,
            self: {{
              player_id: positiveInteger(self.id),
              curses: Array.isArray(self.curses)
                ? self.curses.filter((curse) => typeof curse === 'string')
                : [],
              items,
            }},
            attacks,
          }};
        }} catch (_error) {{
          state.hookErrors += 1;
        }}
      }};
      const instrument = (firebase) => {{
        if (!firebase || typeof firebase.onSnapshot !== 'function' ||
            firebase.onSnapshot.__godfieldDreamProbeWrapped === true) {{
          return firebase;
        }}
        const original = firebase.onSnapshot;
        const wrapped = function(...args) {{
          if (typeof args[1] === 'function') {{
            const callback = args[1];
            args[1] = function(snapshot, ...rest) {{
              capture(snapshot);
              return callback.call(this, snapshot, ...rest);
            }};
          }}
          return original.apply(this, args);
        }};
        Object.defineProperty(wrapped, '__godfieldDreamProbeWrapped', {{value: true}});
        firebase.onSnapshot = wrapped;
        return firebase;
      }};

      let firebaseValue = window.firebase;
      if (firebaseValue) firebaseValue = instrument(firebaseValue);
      Object.defineProperty(window, 'firebase', {{
        configurable: true,
        enumerable: true,
        get: () => firebaseValue,
        set: (value) => {{firebaseValue = instrument(value);}},
      }});
    }})();
    """


async def install_dream_evidence_probe(
    context: BrowserContext,
    *,
    identity: str,
) -> None:
    """Install a passive listener before the official client is loaded."""

    await context.add_init_script(script=_dream_probe_init_script(identity))


_CAPTURE_SCRIPT = """
() => {
  const probe = window.__godfieldDreamEvidenceV1;
  if (!probe || !probe.latest) return null;
  const rendered = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      rect.width > 0 && rect.height > 0;
  };
  const sameBounds = (left, right) =>
    Math.abs(left.x - right.x) <= 1.5 &&
    Math.abs(left.y - right.y) <= 1.5 &&
    Math.abs(left.width - right.width) <= 1.5 &&
    Math.abs(left.height - right.height) <= 1.5;
  const pointerBounds = [...document.querySelectorAll('div')]
    .filter((element) => rendered(element) && getComputedStyle(element).cursor === 'pointer')
    .map((element) => element.getBoundingClientRect());
  const cards = [...document.querySelectorAll('img')]
    .filter(rendered)
    .map((element) => ({element, rect: element.getBoundingClientRect()}))
    .filter(({element, rect}) => {
      const path = new URL(element.src).pathname;
      return path.startsWith('/images/items/') && path !== '/images/items/fake.webp' &&
        rect.x >= 100 && rect.x <= 850 && rect.y >= 480 && rect.y <= 690 &&
        rect.width >= 60 && rect.width <= 100 && rect.height >= 60 && rect.height <= 100;
    })
    .sort((left, right) => left.rect.y - right.rect.y || left.rect.x - right.rect.x)
    .map(({element, rect}, slot) => ({
      slot,
      path: new URL(element.src).pathname,
      x: rect.x,
      y: rect.y,
      selectable: pointerBounds.some((candidate) => sameBounds(candidate, rect)),
    }));
  return {
    schema_version: probe.schemaVersion,
    hook_errors: probe.hookErrors,
    raw: probe.latest,
    rendered_cards: cards,
  };
}
"""


def _catalog_identities(
    snapshot: ApiCatalogSnapshot,
) -> dict[int, DreamProbeCatalogIdentity]:
    identities: dict[int, DreamProbeCatalogIdentity] = {}
    for item in snapshot.items:
        raw = item.raw
        raw_cost = raw.get("cost")
        cost = (
            raw_cost
            if isinstance(raw_cost, int) and not isinstance(raw_cost, bool)
            else 0
        )
        identities[item.model_id] = DreamProbeCatalogIdentity(
            model_id=item.model_id,
            name=raw.get("name") if isinstance(raw.get("name"), str) else None,
            asset=(
                raw.get("imageName") if isinstance(raw.get("imageName"), str) else None
            ),
            category=raw.get("category") if isinstance(raw.get("category"), str) else None,
            cost=cost,
        )
    return identities


def _positive_integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _nonnegative_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DreamProbeError("Dream probe received an invalid nonnegative integer")
    return value


def _phase(raw: dict[str, Any], self_player_id: int) -> tuple[DreamProbePhase, int | None]:
    attacks = raw.get("attacks")
    pending = attacks[0] if isinstance(attacks, list) and attacks else None
    attack_turn_player_id = _positive_integer(raw.get("attack_turn_player_id"))
    if isinstance(pending, dict):
        buying_item_model_id = _positive_integer(pending.get("buying_item_model_id"))
        player_id = _positive_integer(pending.get("player_id"))
        target_player_id = _positive_integer(pending.get("target_player_id"))
        awaiting_player_id = (
            player_id
            if buying_item_model_id or target_player_id is None
            else target_player_id
        )
    else:
        buying_item_model_id = None
        target_player_id = None
        awaiting_player_id = attack_turn_player_id
    if raw.get("is_over") is True:
        return DreamProbePhase.TERMINAL, awaiting_player_id
    if awaiting_player_id != self_player_id:
        return DreamProbePhase.WAIT, awaiting_player_id
    if buying_item_model_id is not None:
        return DreamProbePhase.PURCHASE, awaiting_player_id
    if target_player_id is not None:
        return DreamProbePhase.DEFENSE, awaiting_player_id
    return DreamProbePhase.TURN, awaiting_player_id


def normalize_dream_probe_payload(
    payload: dict[str, Any],
    catalog: ApiCatalogSnapshot,
    *,
    observed_at: datetime | None = None,
) -> DreamProbeSample:
    """Validate a sanitized hook payload and bind its model IDs to a pinned catalog."""

    if payload.get("schema_version") != 1:
        raise DreamProbeError("unsupported Dream browser-probe schema")
    if payload.get("hook_errors") != 0:
        raise DreamProbeError("the Dream browser-probe hook reported an instrumentation error")
    raw = payload.get("raw")
    if not isinstance(raw, dict):
        raise DreamProbeError("Dream browser-probe payload has no raw game state")
    self_state = raw.get("self")
    if not isinstance(self_state, dict):
        raise DreamProbeError("Dream browser-probe payload has no self player")
    self_player_id = _positive_integer(self_state.get("player_id"))
    if self_player_id is None:
        raise DreamProbeError("Dream browser-probe payload has no self player ID")
    raw_items = self_state.get("items")
    if not isinstance(raw_items, list):
        raise DreamProbeError("Dream browser-probe payload has no self hand")
    raw_curses = self_state.get("curses")
    if not isinstance(raw_curses, list) or not all(
        isinstance(curse, str) for curse in raw_curses
    ):
        raise DreamProbeError("Dream browser-probe payload has invalid curses")
    rendered_payload = payload.get("rendered_cards")
    if not isinstance(rendered_payload, list):
        raise DreamProbeError("Dream browser-probe payload has no rendered hand")
    rendered_cards = tuple(
        DreamProbeRenderedCard.model_validate(card) for card in rendered_payload
    )
    identities = _catalog_identities(catalog)
    resolved_items: list[
        tuple[
            dict[str, Any],
            DreamProbeCatalogIdentity | None,
            DreamProbeCatalogIdentity | None,
            int | None,
        ]
    ] = []
    expected_paths: list[str | None] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise DreamProbeError("Dream browser-probe hand contains an invalid item")
        true_model_id = _positive_integer(raw_item.get("model_id"))
        fake_model_id = _positive_integer(raw_item.get("fake_model_id"))
        true_identity = identities.get(true_model_id) if true_model_id is not None else None
        displayed_model_id = fake_model_id or true_model_id
        displayed_identity = (
            identities.get(displayed_model_id) if displayed_model_id is not None else None
        )
        resolved_items.append(
            (raw_item, true_identity, displayed_identity, fake_model_id)
        )
        expected_paths.append(
            displayed_identity.image_path if displayed_identity is not None else None
        )

    raw_indices_by_path: dict[str, list[int]] = {}
    for raw_index, path in enumerate(expected_paths):
        if path is not None:
            raw_indices_by_path.setdefault(path, []).append(raw_index)
    rendered_by_path: dict[str, list[DreamProbeRenderedCard]] = {}
    for rendered_card in rendered_cards:
        rendered_by_path.setdefault(rendered_card.path, []).append(rendered_card)
    assignments: dict[int, DreamProbeRenderedCard] = {}
    ambiguous_paths: set[str] = set()
    for path, raw_indices in raw_indices_by_path.items():
        matching_cards = rendered_by_path.get(path, [])
        if len(raw_indices) == len(matching_cards) == 1:
            assignments[raw_indices[0]] = matching_cards[0]
        elif len(raw_indices) == len(matching_cards) and len(raw_indices) > 1:
            ambiguous_paths.add(path)

    expected_multiset = sorted(path for path in expected_paths if path is not None)
    rendered_multiset = sorted(card.path for card in rendered_cards)
    if len(rendered_cards) != len(resolved_items):
        hand_alignment: Literal[
            "exact",
            "ambiguous",
            "count_mismatch",
            "rendered_mismatch",
        ] = "count_mismatch"
    elif len(expected_multiset) != len(resolved_items) or (
        expected_multiset != rendered_multiset
    ):
        hand_alignment = "rendered_mismatch"
    elif ambiguous_paths:
        hand_alignment = "ambiguous"
    else:
        hand_alignment = "exact"

    evidence: list[DreamProbeItemEvidence] = []
    for raw_index, resolved in enumerate(resolved_items):
        raw_item, true_identity, displayed_identity, fake_model_id = resolved
        expected_path = expected_paths[raw_index]
        assigned_card = assignments.get(raw_index)
        ambiguous = expected_path in ambiguous_paths
        rendered_matches = (
            True
            if assigned_card is not None or ambiguous
            else False
            if expected_path is not None and expected_path not in rendered_by_path
            else None
        )
        evidence.append(
            DreamProbeItemEvidence(
                instance_id=_positive_integer(raw_item.get("instance_id")),
                raw_index=raw_index,
                slot=assigned_card.slot if assigned_card is not None else None,
                true_identity=true_identity,
                displayed_identity=displayed_identity,
                rendered_path=(
                    assigned_card.path
                    if assigned_card is not None
                    else expected_path
                    if ambiguous
                    else None
                ),
                selectable=assigned_card.selectable if assigned_card is not None else None,
                used=raw_item.get("used") is True,
                disguised=fake_model_id is not None,
                rendered_matches_displayed=rendered_matches,
            )
        )
    dream_active = any(curse.casefold() == "dream" for curse in raw_curses)
    phase, awaiting_player_id = _phase(raw, self_player_id)
    return DreamProbeSample(
        observed_at=observed_at or datetime.now(UTC),
        source_sequence=_nonnegative_integer(raw.get("source_sequence")),
        field_number=_nonnegative_integer(raw.get("field_number")),
        update_count=_nonnegative_integer(raw.get("update_count")),
        phase=phase,
        self_player_id=self_player_id,
        attack_turn_player_id=_positive_integer(raw.get("attack_turn_player_id")),
        awaiting_player_id=awaiting_player_id,
        dream_active=dream_active,
        player_count=_nonnegative_integer(raw.get("player_count")),
        items=tuple(evidence),
        rendered_cards=rendered_cards,
        hand_alignment=hand_alignment,
    )


async def capture_dream_evidence(
    page: Page,
    catalog: ApiCatalogSnapshot,
) -> DreamProbeSample | None:
    """Read passive raw/display evidence without dispatching a browser action."""

    payload = await page.evaluate(_CAPTURE_SCRIPT)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise DreamProbeError("Dream browser-probe returned a non-object payload")
    return normalize_dream_probe_payload(cast(dict[str, Any], payload), catalog)
