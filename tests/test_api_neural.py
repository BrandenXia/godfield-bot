from datetime import UTC, datetime

import pytest
import torch
from godfield import ItemCatalog, RoomState

from godfield_bot.api_game import (
    normalize_api_game_state,
    verified_api_combo_actions,
    verified_api_tactical_actions,
)
from godfield_bot.api_neural import (
    API_COMBO_SHADOW_POLICY_ID,
    API_RESOURCE_SHADOW_POLICY_ID,
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
            "sundries": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="romance-water",
                        image_path="/images/items/sundries/romance-water.webp",
                        detail=("Romance Water", "HP+15", "$5", "Gift Rate: 4/500"),
                    ),
                    ArtifactRecord(
                        asset="smile-flower",
                        image_path="/images/items/sundries/smile-flower.webp",
                        detail=("Smile Flower", "MP+5", "$1", "Gift Rate: 12/500"),
                    ),
                )
            ),
            "miracles": ArtifactCategory(
                items=(
                    ArtifactRecord(
                        asset="flame",
                        image_path="/images/items/miracles/flame.webp",
                        detail=("<Flame>", "ATK10", "Cost", "5MP", "Gift Rate: 1/500"),
                        element_image_paths=("/images/elements/fire.webp",),
                    ),
                    ArtifactRecord(
                        asset="spring",
                        image_path="/images/items/miracles/spring.webp",
                        detail=("<Spring>", "HP+10", "Cost", "7MP", "Gift Rate: 1/500"),
                    ),
                )
            ),
        },
        total_artifacts=8,
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
            {
                "name": "Romance Water",
                "imageName": "romance-water",
                "category": "sundries",
                "ability": "boostHP",
                "abilityValue": 15,
            },
            {
                "name": "Smile Flower",
                "imageName": "smile-flower",
                "category": "sundries",
                "ability": "boostMP",
                "abilityValue": 5,
            },
            {
                "name": "Flame",
                "imageName": "flame",
                "category": "miracles",
                "atk": 10,
                "cost": 5,
                "element": "fire",
            },
            {
                "name": "Spring",
                "imageName": "spring",
                "category": "miracles",
                "ability": "boostHP",
                "abilityValue": 10,
                "cost": 7,
            },
        ]
    )


def room(
    *,
    defending: bool = False,
    cursed: bool = False,
    resource_model_id: int | None = None,
    hp: int = 40,
    mp: int = 10,
) -> RoomState:
    attacks = (
        [{"playerId": 2, "targetPlayerId": 1, "itemModelIds": [1], "atk": 9}]
        if defending
        else []
    )
    if resource_model_id is not None:
        items = [{"id": 15, "modelId": resource_model_id}]
    elif defending:
        items = [{"id": 13, "modelId": 3}, {"id": 14, "modelId": 4}]
    else:
        items = [{"id": 11, "modelId": 1}, {"id": 12, "modelId": 2}]
    return RoomState(
        {
            "game": {
                "players": [
                    {
                        "id": 1,
                        "userId": "loki-user",
                        "name": "ロキ-67",
                        "hp": hp,
                        "mp": mp,
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


def shadow_policy(*, feature_schema_version: int = 4) -> ApiComboShadowPolicy:
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
        feature_schema_version=feature_schema_version,
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
                "ruleset_id": (
                    "plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1"
                    if feature_schema_version == 5
                    else "plain-elemental-combo-attack-defense-redraw-duel-v1"
                ),
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


def test_shadow_policy_can_forgive_without_any_supported_armor() -> None:
    current_room = room(defending=True, resource_model_id=5)
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_tactical_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy(feature_schema_version=5).decide(state, legal)

    assert proposal is not None
    assert proposal.action_id == "pass"
    assert decision.selection_action_indices == (19,)


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


def test_shadow_policy_rejects_single_weapon_when_live_value_drifts() -> None:
    current_room = room()
    current_room._catalog.get(1).raw["atk"] = 6
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_tactical_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy().decide(state, legal)

    assert proposal is None
    assert decision.chosen_action_id is None
    assert "no live macro" in decision.rationale


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


@pytest.mark.parametrize(
    ("model_id", "expected_action_id"),
    [
        (5, "utility:boostHP:15:5"),
        (6, "utility:boostMP:15:6"),
        (8, "utility:boostHP:15:8"),
    ],
)
def test_resource_shadow_translates_atomic_utility_without_confirm(
    model_id: int,
    expected_action_id: str,
) -> None:
    current_room = room(resource_model_id=model_id)
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_tactical_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy(feature_schema_version=5).decide(state, legal)

    assert proposal is not None
    assert proposal.action_id == expected_action_id
    assert decision.policy_id == API_RESOURCE_SHADOW_POLICY_ID
    assert decision.chosen_action_id == expected_action_id
    assert decision.selection_action_indices == (1,)
    assert decision.executable is False


def test_resource_shadow_translates_attack_miracle_with_confirm() -> None:
    current_room = room(resource_model_id=7, mp=5)
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_tactical_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy(feature_schema_version=5).decide(state, legal)

    assert proposal is not None
    assert proposal.action_id == "miracle-attack:15:7:2"
    assert decision.selection_action_indices == (1, 20)


@pytest.mark.parametrize(
    ("model_id", "hp", "mp"),
    [
        (5, 100, 10),
        (6, 40, 100),
        (7, 40, 4),
        (8, 100, 10),
        (8, 40, 6),
    ],
)
def test_resource_shadow_matches_native_resource_masks(
    model_id: int,
    hp: int,
    mp: int,
) -> None:
    current_room = room(resource_model_id=model_id, hp=hp, mp=mp)
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_tactical_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    decision, proposal = shadow_policy(feature_schema_version=5).decide(state, legal)

    assert proposal is None
    assert decision.chosen_action_id is None
    assert "no live macro" in decision.rationale


def test_resource_shadow_rejects_live_value_drift_and_v4_ignores_resources() -> None:
    current_room = room(resource_model_id=5)
    current_room._catalog.get(5).raw["abilityValue"] = 14
    state = normalize_api_game_state(current_room, user_id="loki-user")
    legal = verified_api_tactical_actions(
        current_room,
        user_id="loki-user",
        bible_snapshot=bible(),
    )

    resource_decision, resource_proposal = shadow_policy(feature_schema_version=5).decide(
        state,
        legal,
    )
    combo_decision, combo_proposal = shadow_policy().decide(state, legal)

    assert resource_proposal is None
    assert resource_decision.chosen_action_id is None
    assert combo_proposal is None
    assert combo_decision.policy_id == API_COMBO_SHADOW_POLICY_ID


def test_resource_shadow_requires_the_schema_v5_ruleset_pair() -> None:
    policy = shadow_policy(feature_schema_version=5)

    with pytest.raises(ApiNeuralPolicyError, match="matching live combo action semantics"):
        ApiComboShadowPolicy(
            policy.manifest.model_copy(update={"feature_schema_version": 4}),
            policy.model,
            policy.vocabulary,
            policy.snapshot,
        )
