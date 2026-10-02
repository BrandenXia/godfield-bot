"""Deterministic offline combat probe; never a training, strength or promotion gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game import create_development_full_game_batch

Count = Annotated[int, Field(ge=0, strict=True)]


class FullGameCombatSmokeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[3] = 3
    source_kind: Literal["integrated-development-combat-smoke-v3"] = (
        "integrated-development-combat-smoke-v3"
    )
    ruleset_id: Literal["integrated-full-game-development-v5"] = (
        "integrated-full-game-development-v5"
    )
    scenario: Literal["fixed-known-hands-public-greedy-free-for-all-not-strength"] = (
        "fixed-known-hands-public-greedy-free-for-all-not-strength"
    )
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_replay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_size: int = Field(ge=1, le=4096, strict=True)
    player_count: int = Field(ge=2, le=9, strict=True)
    seed: int = Field(ge=0, le=2**64 - 1, strict=True)
    max_turns: int = Field(ge=1, le=4096, strict=True)
    max_decisions: int = Field(ge=1, le=32768, strict=True)
    winners: Count
    all_dead_draws: Count
    turn_limit_truncations: Count
    decision_limit_truncations: Count
    unfinished: Literal[0] = 0
    completed_turns: Count
    actions: Count
    passes: Count
    utilities: Count
    attack_selections: Count
    attack_toggles: Count
    attack_confirms: Count
    attack_components: Count
    darkness_finishes: Count
    attacks_cast: Count
    attacks_resolved: Count
    defense_toggles: Count
    hp_damage: Count
    mp_spent: Count
    consumed_cards: Count
    retained_miracle_uses: Count
    teacher_or_reward_dataset_eligible: Literal[False] = False
    local_training_eligible: Literal[False] = False
    full_game_training_ready: Literal[False] = False
    official_fidelity_verified: Literal[False] = False
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def bounded_accounting(self) -> FullGameCombatSmokeReport:
        if (
            self.winners
            + self.all_dead_draws
            + self.turn_limit_truncations
            + self.decision_limit_truncations
            != self.batch_size
            or self.actions
            != self.passes
            + self.utilities
            + self.attack_selections
            + self.attack_toggles
            + self.attack_confirms
            + self.attacks_cast
            + self.attacks_resolved
            + self.defense_toggles
            or self.attacks_resolved > self.attacks_cast
            or self.attacks_cast > self.attack_selections
            or self.actions > self.batch_size * self.max_decisions
            or self.completed_turns > self.batch_size * self.max_turns
        ):
            raise ValueError("full-game combat smoke outcome or action accounting differs")
        return self


def run_full_game_combat_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 32,
    player_count: int = 3,
    seed: int = 67,
    max_turns: int = 64,
) -> FullGameCombatSmokeReport:
    import numpy as np

    if type(batch_size) is not int or not 1 <= batch_size <= 4096:
        raise ValueError("combat smoke batch size must be 1 through 4096")
    if type(max_turns) is not int or not 1 <= max_turns <= 4096:
        raise ValueError("combat smoke turn bound must be 1 through 4096")
    max_decisions = max_turns * 8
    configured = create_development_full_game_batch(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        capacity=12,
        seed=seed,
        max_turns=max_turns,
        max_decisions=max_decisions,
        initial_hp=30,
        initial_mp=30,
    )
    batch = configured.batch
    # Fixture deal, NOT weighted acquisition or replacement cadence.
    models = (57, 54, 35, 218, 130, 148, 194, 195, 237, 28, 66, 210)
    for env in range(batch_size):
        for owner in range(player_count):
            batch.seed_players(
                np.asarray([env], dtype=np.int64),
                np.asarray([owner], dtype=np.int64),
                np.asarray([[30, 30, 0, (owner + env) % 5]], dtype=np.int64),
                np.asarray([1 if owner == 0 else 4 if owner == 1 else 0], dtype=np.int64),
            )
            batch.seed_hand(
                env,
                owner,
                np.asarray(
                    [
                        (owner * len(models) + index + 1, model, 0, 0)
                        for index, model in enumerate(models)
                    ],
                    dtype=np.int64,
                ),
            )
    batch.start_environments(np.arange(batch_size, dtype=np.int64))
    attacks = {row[0]: row[1:] for row in configured.metadata.plan.combat.attack_profiles}
    armor = {row[0]: row[1] for row in configured.metadata.plan.combat.armor_profiles}
    utility = {row[0]: row[1:] for row in configured.metadata.plan.effect_profiles}
    boosts = {row[0]: row[1:] for row in configured.metadata.plan.combat.boost_profiles}
    digest = hashlib.sha256()
    selections = 0

    def fingerprint() -> None:
        # Diagnostic proof only. These arrays are NEVER used to select an action.
        for view in (
            batch.episode_snapshot(),
            batch.diagnostic_players(),
            batch.diagnostic_inventory(),
            batch.pending_observations(),
            batch.special_defense_observations(),
            batch.selected_defenses(),
            batch.selected_attacks(),
            batch.attack_order(),
            batch.attack_selection_observations(),
        ):
            digest.update(view.astype("<i8", copy=False).tobytes())

    fingerprint()
    for _ in range(max_decisions):
        episodes = batch.episode_snapshot()
        active = np.flatnonzero(np.isin(episodes[:, 3], (1, 2, 3, 4)))
        if not len(active):
            break
        masks, hands = batch.choice_masks(), batch.actor_hands()
        pending, selected = batch.pending_observations(), batch.selected_defenses()
        players = batch.player_observations()
        selected_attacks = batch.selected_attacks()
        commands = []
        for env_index in active:
            env = int(env_index)
            phase = int(episodes[env, 3])
            legal = np.flatnonzero(masks[env]).tolist()
            choice = 0
            if phase == 3:
                choice = legal[0]
            elif phase == 2:
                selected_attack = selected_attacks[env]
                available = [
                    slot for slot in legal if 1 <= slot <= 12 and not selected_attack[slot - 1]
                ]
                if available:
                    choice = max(
                        available, key=lambda slot: boosts[int(hands[env, slot - 1, 1])][0]
                    )
            elif phase == 4:
                available = [
                    slot for slot in legal if 1 <= slot <= 12 and not selected[env, slot - 1]
                ]
                if pending[env, 6] < pending[env, 3] and available:
                    choice = max(available, key=lambda slot: armor[int(hands[env, slot - 1, 1])])
            else:
                spells, benefits = [], []
                for slot in legal:
                    if not 1 <= slot <= 12:
                        continue
                    model = int(hands[env, slot - 1, 1])
                    if model in attacks or model in boosts:
                        spells.append(slot)
                    elif model in utility:
                        kind, _, _ = utility[model]
                        if (
                            kind >= 3
                            or (kind == 1 and players[env, 0, 3] <= 20)
                            or (kind == 2 and players[env, 0, 4] <= 15)
                        ):
                            benefits.append(slot)
                if benefits:
                    choice = benefits[0]
                elif spells:
                    choice = max(
                        spells,
                        key=lambda slot: (
                            attacks.get(int(hands[env, slot - 1, 1]))
                            or boosts[int(hands[env, slot - 1, 1])]
                        )[0],
                    )
                    selections += 1
            commands.append([int(env), *episodes[env, :4].tolist(), choice])
        batch.step(np.asarray(commands, dtype=np.int64))
        fingerprint()
    episodes = batch.episode_snapshot()
    if np.any(~np.isin(episodes[:, 3], (12, 13))):
        raise RuntimeError("full-game combat smoke left unfinished environments")
    metadata_sha = hashlib.sha256(
        json.dumps(
            configured.metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return FullGameCombatSmokeReport(
        metadata_sha256=metadata_sha,
        diagnostic_replay_sha256=digest.hexdigest(),
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        max_turns=max_turns,
        max_decisions=max_decisions,
        winners=int(np.count_nonzero(episodes[:, 5] == 1)),
        all_dead_draws=int(np.count_nonzero(episodes[:, 5] == 2)),
        turn_limit_truncations=int(np.count_nonzero(episodes[:, 5] == 3)),
        decision_limit_truncations=int(np.count_nonzero(episodes[:, 5] == 4)),
        completed_turns=int(np.sum(episodes[:, 4])),
        actions=batch.action_count,
        passes=batch.pass_count,
        utilities=batch.utility_count,
        attack_selections=selections,
        attack_toggles=batch.attack_toggle_count,
        attack_confirms=batch.attack_confirm_count,
        attack_components=batch.attack_component_count,
        darkness_finishes=batch.darkness_finish_count,
        attacks_cast=batch.attack_count,
        attacks_resolved=batch.resolved_attack_count,
        defense_toggles=batch.defense_toggle_count,
        hp_damage=batch.hp_damage,
        mp_spent=batch.mp_spent,
        consumed_cards=batch.consumed_count,
        retained_miracle_uses=batch.miracle_use_count,
    )
