from datetime import UTC, datetime

import pytest
import torch
from godfield import ItemCatalog, RoomState

from godfield_bot.api_game import normalize_api_game_state, verified_api_combo_actions
from godfield_bot.api_neural import (
    API_COMBO_SHADOW_POLICY_ID,
    ApiComboShadowPolicy,
    ApiNeuralPolicyError,
)
from godfield_bot.domain.reference import (
    ArtifactCategory,
    ArtifactRecord,
    BibleSnapshot,
    ClientFingerprint,
)
from godfield_bot.features import ArtifactVocabulary
from godfield_bot.model_registry import (
    ModelArchitecture,
    ModelManifest,
    ModelStatus,
    vocabulary_digest,
)
from godfield_bot.neural import RecurrentPolicyValueNet


def bible() -> BibleSnapshot:
    return BibleSnapshot(
        observed_at=datetime.now(UTC),
        source_url="https://godfield.net/",
        language="en",
        client=ClientFingerprint(url="https://godfield.net/main.dart.js", sha256="a" * 64),
        reference_sections={},
        catalog={
            "weapons": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="club",
                        image_path="/images/items/weapons/club.webp",
                        detail=("Club", "ATK5", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="blowgun",
                        image_path="/images/items/weapons/blowgun.webp",
                        detail=("Blowgun", "+ATK2", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
            "armor": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="shield",
                        image_path="/images/items/armor/shield.webp",
                        detail=("Shield", "DEF5", "$1", "Gift Rate: 1/500"),
                    ),
                    ArtifactRecord(
                        asset="mail",
                        image_path="/images/items/armor/mail.webp",
                        detail=("Mail", "DEF7", "$1", "Gift Rate: 1/500"),
                    ),
                )
            ),
        },
        total_artifacts=4,
    )


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            {
                "name": "Club",
                "imageName": "club",
                "category": "weapons",
                "atk": 5,
            },
            {
                "name": "Blowgun",
                "imageName": "blowgun",
                "category": "weapons",
                "atk": 2,
                "isPlusAtk": True,
            },
            {
                "name": "Shield",
                "imageName": "shield",
                "category": "armor",
                "def": 5,
            },
            {
                "name": "Mail",
                "imageName": "mail",
                "category": "armor",
                "def": 7,
            },
        ]
    )


def room(*, defending: bool = False, cursed: bool = False) -> RoomState:
    attacks = (
        [{"playerId": 2, "targetPlayerId": 1, "itemModelIds": [1], "atk": 9}]
        if defending
        else []
    )
    items = (
        [{"id": 13, "modelId": 3}, {"id": 14, "modelId": 4}]
        if defending
        else [{"id": 11, "modelId": 1}, {"id": 12, "modelId": 2}]
    )
    return RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": 40,
                        "mp": 10,
                        "cp": 20,
                        "team": 0,
                        "items": items,
                        "curses": ["dream"] if cursed else [],
                    },
                    {
                        "id": 2,
                        "userId": "opponent-user",
                        "name": "Opponent",
                        "hp": 35,
                        "mp": 8,
                        "cp": 19,
                        "team": 0,
                        "items": [],
                    },
                ],
                "attackTurnPlayerId": 1,
                "attacks": attacks,
                "gf": 7,
                "updateCount": 12,
                "isOver": False,
            }
        },
        catalog(),
    )


def shadow_policy() -> ApiComboShadowPolicy:
    snapshot = bible()
    vocabulary = ArtifactVocabulary.from_snapshot(snapshot)
    architecture = ModelArchitecture(
        vocabulary_size=len(vocabulary.tokens),
        action_count=21,
        global_feature_count=13,
        player_feature_count=4,
        policy_architecture="slot-aware-v1",
    )
    model = RecurrentPolicyValueNet(**architecture.model_dump())
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    manifest = ModelManifest(
        feature_schema_version=4,
        model_id="shadow-candidate",
        created_at=datetime.now(UTC),
        status=ModelStatus.CANDIDATE,
        client_sha256="a" * 64,
        vocabulary_sha256=vocabulary_digest(vocabulary),
        weights_sha256="b" * 64,
        weights_file="weights.pt",
        architecture=architecture,
        seed=67,
        training_context={
            "simulation": {
                "ruleset_id": "plain-elemental-combo-attack-defense-redraw-duel-v1",
                "action_semantics": "sequential-combo-selection",
            }
        },
    )
    return ApiComboShadowPolicy(manifest, model, vocabulary, snapshot)


def test_shadow_policy_translates_sequential_attack_into_one_live_macro() -> None:
    current_room = room()
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_combo_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy().decide(state, legal)

    assert proposal is not None
    assert proposal.item_instance_ids == (11, 12)
    assert decision.policy_id == API_COMBO_SHADOW_POLICY_ID
    assert decision.executable is False
    assert decision.chosen_action_id == "combo-attack:11-12:2"
    assert decision.selection_action_indices == (1, 2, 20)
    assert len(decision.selection_probabilities) == 3
    assert len(decision.value_estimates) == 3


def test_shadow_policy_translates_sequential_defense_into_one_live_macro() -> None:
    current_room = room(defending=True)
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_combo_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy().decide(state, legal)

    assert proposal is not None
    assert proposal.item_instance_ids == (13, 14)
    assert decision.chosen_action_id == "combo-defense:13-14"
    assert decision.selection_action_indices == (1, 2, 20)


def test_shadow_policy_abstains_and_resets_on_cursed_state() -> None:
    current_room = room(cursed=True)
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_combo_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )
    policy = shadow_policy()

    decision, proposal = policy.decide(state, legal)

    assert proposal is None
    assert decision.executable is False
    assert decision.chosen_action_id is None
    assert "curses" in decision.rationale
    assert policy.recurrent_state is None


def test_shadow_policy_rejects_an_untrained_or_wrong_ruleset_model() -> None:
    policy = shadow_policy()

    with pytest.raises(ApiNeuralPolicyError, match="candidate or champion"):
        ApiComboShadowPolicy(
            policy.manifest.model_copy(update={"status": ModelStatus.INITIALIZED}),
            policy.model,
            policy.vocabulary,
            policy.snapshot,
        )
    with pytest.raises(ApiNeuralPolicyError, match="combo action semantics"):
        ApiComboShadowPolicy(
            policy.manifest.model_copy(update={"training_context": {}}),
            policy.model,
            policy.vocabulary,
            policy.snapshot,
        )
