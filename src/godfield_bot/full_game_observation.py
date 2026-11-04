"""Versioned public-only inputs for the separate 18-slot full-game learner."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot import full_game as game
from godfield_bot.full_game_card_features import CARD_PROPERTY_FIELDS, public_card_property_table
from godfield_bot.full_game_guardians import GENERATED_ACTION_FIELDS
from godfield_bot.full_game_trade import MARKET_FIELDS, TRADE_FIELDS
from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    IntArray = npt.NDArray[np.int64]
    FloatArray = npt.NDArray[np.float32]
    BoolArray = npt.NDArray[np.bool_]
    Array = npt.NDArray[Any]

HAND_SLOTS: Final = 18
CHOICES: Final = 28
MAX_PLAYERS: Final = 9
MODEL_VOCABULARY: Final = 297  # 0 padding, pinned API model IDs through296.
OBSERVATION_ID: Final = "full-game-public-18-slot-v1"
ATTACK_HISTORY_OBSERVATION_ID: Final = "full-game-public-18-slot-attack-history-v2"
CARD_PROPERTIES_OBSERVATION_ID: Final = "full-game-public-18-slot-card-properties-v3"
FullGameObservationId = Literal[
    "full-game-public-18-slot-v1",
    "full-game-public-18-slot-attack-history-v2",
    "full-game-public-18-slot-card-properties-v3",
]
ATTACK_HISTORY_LENGTH: Final = 8
ATTACK_HISTORY_FIELDS: Final = (
    "present",
    *(f"source_relative_seat_{i}" for i in range(9)),
    *(f"target_relative_seat_{i}" for i in range(9)),
    "attack_log",
    *(f"element_{i}" for i in range(7)),
    *(f"origin_{i}" for i in range(6)),
    "hit_rate_fraction",
    "age_turns_log",
)
# Only these reviewed views enter numeric global features. Private snapshots,
# escrow, future work and scheduler/RNG counters are intentionally absent.
CONTEXT_VIEWS: Final = (
    ("pending_observations", game.PENDING_FIELDS),
    ("special_defense_observations", game.SPECIAL_DEFENSE_FIELDS),
    ("chance_observations", game.CHANCE_FIELDS),
    ("attack_effect_observations", game.ATTACK_EFFECT_FIELDS),
    ("counter_observations", game.COUNTER_FIELDS),
    ("attack_selection_observations", game.ATTACK_SELECTION_FIELDS),
    ("utility_selection_observations", game.UTILITY_SELECTION_FIELDS),
    ("complex_weapon_observations", game.COMPLEX_WEAPON_FIELDS),
    ("danger_observations", game.DANGER_FIELDS),
    ("area_observations", game.AREA_FIELDS),
    ("discard_observations", game.DISCARD_FIELDS),
    ("guardian_effect_observations", game.GUARDIAN_EFFECT_FIELDS),
    ("generated_action_observations", GENERATED_ACTION_FIELDS),
    ("apocalypse_observations", game.APOCALYPSE_FIELDS),
    ("phenomenon_observations", game.PHENOMENON_OBSERVATION_FIELDS),
    ("trade_observations", TRADE_FIELDS),
    ("market_observations", MARKET_FIELDS),
)
GLOBAL_FIELDS: Final = (
    *(f"phase_{i}" for i in range(14)),
    *(f"actor_seat_{i}" for i in range(9)),
    "player_count_fraction",
    "completed_turn_fraction",
    "accepted_decision_fraction",
    *(f"{name}.{field}" for name, columns in CONTEXT_VIEWS for field in columns),
)
PLAYER_FEATURES: Final = (
    "present",
    "visible",
    "hp_fraction",
    "mp_fraction",
    "cp_fraction",
    "illness_fraction",
    *(f"curse_bit_{i}" for i in range(4)),
    *(f"absolute_seat_{i}" for i in range(9)),
    *(f"team_id_{i}" for i in range(5)),
    *(f"relation_{i}" for i in range(4)),
    "guardian_visible",
    *(f"guardian_group_{i}" for i in range(11)),
    "control_visible",
    "confusion_log",
)
HAND_FEATURES: Final = (
    "performed",
    "attack_selection_rank",
    "defense_selection_rank",
    "discard_selection_rank",
    *(f"passive_kind_{i}" for i in range(4)),
    "passive_value_log",
    *(f"slot_{i}" for i in range(18)),
)
PROPERTY_HAND_FIELDS: Final = (*HAND_FEATURES, *(f"card.{name}" for name in CARD_PROPERTY_FIELDS))


def observation_version(observation_id: FullGameObservationId) -> int:
    return {OBSERVATION_ID: 1, ATTACK_HISTORY_OBSERVATION_ID: 2, CARD_PROPERTIES_OBSERVATION_ID: 3}[
        observation_id
    ]


CONTEXT_MODELS: Final = (
    ("guardian_effect_observations", 1),
    ("generated_action_observations", 2),
    ("generated_action_observations", 3),
    ("phenomenon_observations", 1),
    ("market_observations", 6),
)
PUBLIC_GETTERS: Final = (
    "episode_snapshot",
    "actor_hands",
    "player_observations",
    "team_observations",
    "guardian_observations",
    "control_observations",
    "choice_masks",
    "policy_gradient_masks",
    "attack_order",
    "defense_order",
    "discard_order",
    "passive_observations",
    *(name for name, _ in CONTEXT_VIEWS),
)
HISTORY_GLOBAL_FIELDS: Final = (
    *GLOBAL_FIELDS,
    *(
        f"attack_history_{i}.{field}"
        for i in range(ATTACK_HISTORY_LENGTH)
        for field in ATTACK_HISTORY_FIELDS
    ),
)
HISTORY_PUBLIC_GETTERS: Final = (*PUBLIC_GETTERS, "attack_history_observations")


class FullGameEncoderMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=3, strict=True)
    observation_id: FullGameObservationId = OBSERVATION_ID
    ruleset_id: Literal["integrated-full-game-development-v33"] = game.FULL_GAME_RULESET_ID
    kernel_schema_version: Literal[33] = 33
    hand_slots: Literal[18] = 18
    choices: Literal[28] = 28
    maximum_players: Literal[9] = 9
    model_vocabulary: Literal[297] = 297
    environment_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    global_fields: tuple[str, ...] = GLOBAL_FIELDS
    player_fields: tuple[str, ...] = PLAYER_FEATURES
    hand_fields: tuple[str, ...] = HAND_FEATURES
    context_model_columns: tuple[tuple[str, int], ...] = CONTEXT_MODELS
    public_getters: tuple[str, ...] = PUBLIC_GETTERS
    context_numbers: Literal["signed-log1p-div-log100-no-clipping-inactive-zero"] = (
        "signed-log1p-div-log100-no-clipping-inactive-zero"
    )
    command_ids: Literal["leases-only-never-learned-instance-epoch-or-decision-identity"] = (
        "leases-only-never-learned-instance-epoch-or-decision-identity"
    )
    complete_rollout_and_learner_implemented: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def pinned_fields(self) -> FullGameEncoderMetadata:
        history = self.observation_id != OBSERVATION_ID
        if (
            self.schema_version != observation_version(self.observation_id)
            or self.global_fields != (HISTORY_GLOBAL_FIELDS if history else GLOBAL_FIELDS)
            or self.player_fields != PLAYER_FEATURES
            or self.hand_fields
            != (PROPERTY_HAND_FIELDS if self.schema_version == 3 else HAND_FEATURES)
            or self.context_model_columns != CONTEXT_MODELS
            or self.public_getters != (HISTORY_PUBLIC_GETTERS if history else PUBLIC_GETTERS)
        ):
            raise ValueError("full-game encoder feature contract differs")
        return self


def _freeze(array: Array) -> Array:
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class FullGameObservation:
    # [environment, episode, decision, actor, phase], validation/dispatch only.
    leases: IntArray
    global_features: FloatArray
    players: FloatArray
    player_mask: BoolArray
    card_model_ids: IntArray
    hand_features: FloatArray
    hand_mask: BoolArray
    context_model_ids: IntArray
    choice_mask: BoolArray
    policy_gradient_mask: BoolArray

    def take(self, indices: IntArray) -> FullGameObservation:
        import numpy as np

        if (
            not isinstance(indices, np.ndarray)
            or indices.dtype != np.int64
            or indices.ndim != 1
            or np.any(indices < 0)
            or np.any(indices >= len(self.leases))
            or len(np.unique(indices)) != len(indices)
        ):
            raise ValueError("observation row selection must be unique bounded int64 indices")
        return FullGameObservation(
            **{f.name: _freeze(getattr(self, f.name)[indices].copy()) for f in fields(self)}
        )


class FullGameObservationEncoder:
    def __init__(
        self,
        configured: game.DevelopmentFullGameBatch,
        observation_id: FullGameObservationId = OBSERVATION_ID,
    ) -> None:
        import godfield_sim as native

        game.FullGameMetadata.model_validate(configured.metadata.model_dump())
        if configured.metadata.capacity != HAND_SLOTS or configured.metadata.batch_size > 4096:
            raise ValueError("full-game encoder requires18 slots and at most4096 environments")
        history = observation_id != OBSERVATION_ID
        getters = HISTORY_PUBLIC_GETTERS if history else PUBLIC_GETTERS
        if (
            getattr(native, "FULL_GAME_KERNEL_SCHEMA_VERSION", None) != 33
            or getattr(native, "FULL_GAME_OBSERVATION_SCHEMA_VERSION", None) != 33
            or (history and getattr(native, "FULL_GAME_ATTACK_HISTORY_SCHEMA_VERSION", None) != 1)
            or any(not hasattr(configured.batch, name) for name in getters)
        ):
            raise ProvisionalRuleUnavailableError("native public observation interface differs")
        self.configured = configured
        self.metadata = FullGameEncoderMetadata(
            schema_version=observation_version(observation_id),
            hand_fields=PROPERTY_HAND_FIELDS
            if observation_id == CARD_PROPERTIES_OBSERVATION_ID
            else HAND_FEATURES,
            observation_id=observation_id,
            global_fields=HISTORY_GLOBAL_FIELDS if history else GLOBAL_FIELDS,
            public_getters=getters,
            environment_metadata_sha256=hashlib.sha256(
                json.dumps(
                    configured.metadata.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        )

        self._card_properties = (
            public_card_property_table(configured.metadata)
            if observation_id == CARD_PROPERTIES_OBSERVATION_ID
            else None
        )

    def encode(self) -> FullGameObservation:
        import numpy as np

        b, m = self.configured.batch, self.configured.metadata
        size = m.batch_size

        def read(name: str, shape: tuple[int, ...], boolean: bool = False) -> Array:
            a = getattr(b, name)()
            if (
                not isinstance(a, np.ndarray)
                or a.shape != (size, *shape)
                or a.dtype != (np.bool_ if boolean else np.int64)
            ):
                raise RuntimeError(f"native public view layout differs: {name}")
            return a

        def log(a: Array) -> FloatArray:
            return np.asarray(
                np.sign(a) * np.log1p(np.abs(a.astype(np.float64))) / np.log(100),
                dtype=np.float32,
            )

        def onehot(a: IntArray, width: int) -> FloatArray:
            if np.any((a < 0) | (a >= width)):
                raise RuntimeError("native public categorical value differs")
            return np.eye(width, dtype=np.float32)[a]

        state = read("episode_snapshot", (9,))
        if (
            np.any(state[:, 0:2] < 1)
            or np.any(state[:, 2] < 0)
            or np.any(state[:, 2] >= m.player_count)
            or np.any(state[:, 3] < 0)
            or np.any(state[:, 3] > 13)
            or np.any(state[:, 4] < 0)
            or np.any(state[:, 4] > m.max_turns)
            or np.any(state[:, 7] < 0)
            or np.any(state[:, 7] > m.max_decisions)
        ):
            raise RuntimeError("native public episode context differs")
        active = np.isin(state[:, 3], (1, 2, 3, 4, 6, 7))
        choices = read("choice_masks", (CHOICES,), True).copy()
        gradient = read("policy_gradient_masks", (1,), True)[:, 0].copy()
        if not np.array_equal(choices.any(axis=1), active) or np.any(gradient & ~active):
            raise RuntimeError("native public legal-choice lifecycle differs")
        contexts = {name: read(name, (len(cols),)) for name, cols in CONTEXT_VIEWS}
        context_models = np.column_stack([contexts[name][:, col] for name, col in CONTEXT_MODELS])
        if np.any((context_models < 0) | (context_models >= MODEL_VOCABULARY)):
            raise RuntimeError("native revealed model vocabulary differs")
        global_features = np.concatenate(
            (
                onehot(state[:, 3], 14),
                onehot(state[:, 2], 9),
                np.full((size, 1), m.player_count / 9, dtype=np.float32),
                (state[:, 4:5] / m.max_turns).astype(np.float32),
                (state[:, 7:8] / m.max_decisions).astype(np.float32),
                *(log(contexts[name]) for name, _ in CONTEXT_VIEWS),
            ),
            axis=1,
        )
        if self.metadata.observation_id != OBSERVATION_ID:
            announcements = read("attack_history_observations", (ATTACK_HISTORY_LENGTH, 8))
            present = announcements[:, :, 0]
            source, target, power, element, origin, rate, turn = (
                announcements[:, :, i] for i in range(1, 8)
            )
            actor = state[:, 2:3]
            age = state[:, 4:5] - turn
            if (
                np.any((present != 0) & (present != 1))
                or np.any(announcements[present == 0])
                or np.any(present[~active])
                or np.any(np.diff(present, axis=1) < 0)
                or np.any((np.diff(turn, axis=1) < 0) & (present[:, 1:] == 1))
                or np.any((present == 1) & (source != actor) & (target != actor))
                or np.any((source < 0) | (source >= m.player_count))
                or np.any((target < 0) | (target >= m.player_count))
                or np.any((power < 0) | (turn < 0) | (age < 0) | (rate < 0) | (rate > 100))
            ):
                raise RuntimeError("native attack history visibility, ordering or bounds differ")
            history_features = np.concatenate(
                (
                    present[:, :, None].astype(np.float32),
                    onehot((source - actor) % m.player_count, 9),
                    onehot((target - actor) % m.player_count, 9),
                    log(power[:, :, None]),
                    onehot(element, 7),
                    onehot(origin, 6),
                    (rate[:, :, None] / 100).astype(np.float32),
                    log(age[:, :, None]),
                ),
                axis=2,
            )
            history_features[present == 0] = 0
            global_features = np.concatenate(
                (global_features, history_features.reshape(size, -1)), axis=1
            )

        p = read("player_observations", (9, 8))
        t = read("team_observations", (9, 4))
        g = read("guardian_observations", (9, 4))
        c = read("control_observations", (9, 4))
        present = np.arange(9)[None, :] < m.player_count
        seats = (state[:, 2:3] + np.arange(9)[None, :]) % m.player_count
        active_players = np.broadcast_to(present, (size, 9)) & active[:, None]
        if (
            not np.array_equal(p[:, :, 1], np.broadcast_to(present, (size, 9)))
            or np.any(p[:, :, 0] != np.where(present, seats, -1))
            or np.any(p[:, :, 2] < 0)
            or np.any(p[:, :, 2] > 1)
            or np.any(p[:, :, 3:6] < 0)
            or np.any(p[:, :, 3:6] > m.resource_cap)
            or np.any(p[:, :, 6] < 0)
            or np.any(p[:, :, 6] > 4)
            or np.any(p[:, :, 7] < 0)
            or np.any(p[:, :, 7] > 15)
            or np.any((p[:, :, 2] == 0)[:, :, None] & (p[:, :, 3:] != 0))
            or not np.array_equal(t[:, :, :2], p[:, :, :2])
            or not np.array_equal(g[:, :, :3][active_players], p[:, :, :3][active_players])
            or not np.array_equal(c[:, :, :3][active_players], p[:, :, :3][active_players])
            or np.any(t[:, :, 2][np.broadcast_to(present, (size, 9))] < 0)
            or np.any(t[:, :, 2] > 4)
            or np.any(t[:, :, 3] < 0)
            or np.any(t[:, :, 3] > 3)
            or np.any(g[:, :, 3] < 0)
            or np.any(g[:, :, 3] > 10)
            or np.any(c[:, :, 3] < 0)
            or np.any((g[:, :, 2] == 0) & (g[:, :, 3] != 0))
            or np.any((c[:, :, 2] == 0) & (c[:, :, 3] != 0))
        ):
            raise RuntimeError("native public player visibility or category differs")
        players = np.concatenate(
            (
                p[:, :, 1:3].astype(np.float32),
                (p[:, :, 3:6] / m.resource_cap).astype(np.float32),
                (p[:, :, 6:7] / 4).astype(np.float32),
                ((p[:, :, 7:8] >> np.arange(4)) & 1).astype(np.float32),
                onehot(seats, 9),
                onehot(np.maximum(t[:, :, 2], 0), 5),
                onehot(t[:, :, 3], 4),
                g[:, :, 2:3].astype(np.float32),
                onehot(g[:, :, 3], 11),
                c[:, :, 2:3].astype(np.float32),
                log(c[:, :, 3:4]),
            ),
            axis=2,
        )
        player_mask = np.broadcast_to(present, (size, 9)).copy() & active[:, None]

        hand = read("actor_hands", (18, 3))
        hand_mask = (hand[:, :, 0] > 0) & active[:, None]
        physical = hand[:, :, 0] > 0
        if (
            np.any(hand[:, :, 0] < 0)
            or np.any(hand[~physical] != 0)
            or np.any((hand[:, :, 1][physical] < 3) | (hand[:, :, 1][physical] > 239))
            or np.any((hand[:, :, 2] < 0) | (hand[:, :, 2] > 1))
        ):
            raise RuntimeError("native displayed hand differs")
        ranks = []
        for name in ("attack_order", "defense_order", "discard_order"):
            order = read(name, (18,))
            rank = np.zeros((size, 18), dtype=np.float32)
            for env in range(size):
                selected = order[env, order[env] != 0]
                if (
                    np.any(selected < 1)
                    or np.any(selected > 18)
                    or len(np.unique(selected)) != len(selected)
                    or not physical[env, selected - 1].all()
                ):
                    raise RuntimeError("native public selection order differs")
                rank[env, selected - 1] = np.arange(1, len(selected) + 1) / 18
            ranks.append(rank[:, :, None])
        passive = read("passive_observations", (18, 2))
        hand_features = np.concatenate(
            (
                hand[:, :, 2:3].astype(np.float32),
                *ranks,
                onehot(passive[:, :, 0], 4),
                log(passive[:, :, 1:2]),
                np.broadcast_to(np.eye(18, dtype=np.float32), (size, 18, 18)),
            ),
            axis=2,
        )
        if self._card_properties is not None:
            hand_features = np.concatenate(
                (hand_features, self._card_properties[hand[:, :, 1]]), axis=2
            )
        cards = hand[:, :, 1].copy()
        leases = np.column_stack((np.arange(size), state[:, :4])).astype(np.int64)
        for a in (global_features, context_models):
            a[~active] = 0
        players[~player_mask] = 0
        hand_features[~hand_mask] = 0
        cards[~hand_mask] = 0
        arrays = (
            leases,
            global_features,
            players,
            player_mask,
            cards,
            hand_features,
            hand_mask,
            context_models,
            choices,
            gradient,
        )
        for a in arrays:
            _freeze(a)
        return FullGameObservation(*arrays)
