from datetime import UTC, datetime
from pathlib import Path

from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet, PolicyDecision
from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import Bounds
from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.features import (
    DREAM_FEATURE_SCHEMA_VERSION,
    DREAM_GLOBAL_FEATURE_COUNT,
    ArtifactVocabulary,
)
from godfield_bot.legal_actions import game_state_digest
from godfield_bot.model_registry import ModelStatus, initialize_model
from godfield_bot.training_shadow import (
    DREAM_RULESET_ID,
    OfficialTrainingShadowPolicy,
    summarize_training_shadow,
)

SNAPSHOT = Path("data/snapshots/2026-09-20/bible.json")
BIBLE = BibleSnapshot.model_validate_json(SNAPSHOT.read_text(encoding="utf-8"))


def _candidate(tmp_path: Path) -> Path:
    vocabulary = ArtifactVocabulary.from_snapshot(BIBLE)
    initialized = initialize_model(
        tmp_path / "models",
        vocabulary,
        client_sha256=BIBLE.client.sha256,
        feature_schema_version=DREAM_FEATURE_SCHEMA_VERSION,
        global_feature_count=DREAM_GLOBAL_FEATURE_COUNT,
    )
    candidate = initialized.model_copy(
        update={
            "status": ModelStatus.CANDIDATE,
            "training_context": {
                "simulation": {
                    "ruleset_id": DREAM_RULESET_ID,
                    "observation_schema_version": DREAM_FEATURE_SCHEMA_VERSION,
                    "action_semantics": "sequential-combo-selection",
                }
            },
        }
    )
    directory = tmp_path / "models" / candidate.model_id
    (directory / "manifest.json").write_text(
        candidate.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return directory


def _state() -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=4,
        self_player_index=0,
        players=(
            PlayerState(
                name="ロキ-67",
                hp=35,
                mp=10,
                money=20,
                is_self=True,
                dreaming=True,
            ),
            PlayerState(name="CPU", hp=28, mp=7, money=20, is_self=False),
        ),
        hand=(
            HandArtifact(
                slot=0,
                category="weapons",
                slug="bronze-club",
                asset_path="/images/items/weapons/bronze-club.webp",
                bounds=Bounds(x=110, y=493, width=80, height=80),
            ),
        ),
        scene_layers=("/images/screens/room.webp",),
    )


def _inputs(state: GameState) -> tuple[LegalActionSet, PolicyDecision]:
    digest = game_state_digest(state)
    action = LegalAction(
        action_id="artifact:0:weapons/bronze-club",
        kind=ActionKind.SELECT_ARTIFACT,
        label="Select Bronze Club",
        artifact_slot=0,
        artifact_asset_path=state.hand[0].asset_path,
    )
    actions = LegalActionSet(
        state_digest=digest,
        actions=(
            LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),
            action,
        ),
        coverage_complete=False,
        blocked_reason="fixture exposes one reviewed action",
    )
    behavior = PolicyDecision(
        decided_at=state.observed_at,
        policy_id="heuristic-v0",
        state_digest=digest,
        chosen_action_id=action.action_id,
        scores={action.action_id: 1.0},
        rationale="fixture",
        executable=True,
    )
    return actions, behavior


def test_schema_v10_shadow_proposes_without_becoming_executable(tmp_path: Path) -> None:
    policy = OfficialTrainingShadowPolicy(_candidate(tmp_path), BIBLE)
    state = _state()
    actions, behavior = _inputs(state)

    evidence = policy.evaluate(state, actions, behavior)

    assert evidence.covered is True
    assert evidence.proposed_action_id == behavior.chosen_action_id
    assert evidence.agreement is True
    assert evidence.behavior_executable is True
    assert evidence.policy_id == "official-training-neural-shadow-v1"


def test_schema_v10_shadow_abstains_and_resets_on_hidden_stats(tmp_path: Path) -> None:
    policy = OfficialTrainingShadowPolicy(_candidate(tmp_path), BIBLE)
    state = _state()
    actions, behavior = _inputs(state)
    assert policy.evaluate(state, actions, behavior).covered is True
    assert policy.recurrent_state is not None
    hidden = state.model_copy(
        update={
            "players": (
                state.players[0],
                state.players[1].model_copy(update={"stats_visible": False}),
            )
        }
    )
    hidden_actions, hidden_behavior = _inputs(hidden)

    evidence = policy.evaluate(hidden, hidden_actions, hidden_behavior)

    assert evidence.covered is False
    assert evidence.recurrent_reset is True
    assert evidence.abstain_reason == (
        "hidden player statistics require a visibility-aware feature schema"
    )
    assert policy.recurrent_state is None


def test_training_shadow_summary_counts_only_executable_decisions(tmp_path: Path) -> None:
    policy = OfficialTrainingShadowPolicy(_candidate(tmp_path), BIBLE)
    state = _state()
    actions, behavior = _inputs(state)
    covered = policy.evaluate(state, actions, behavior)
    waiting = behavior.model_copy(
        update={"chosen_action_id": "wait", "executable": False}
    )
    wait_sample = policy.evaluate(state, actions, waiting)

    report = summarize_training_shadow((covered, wait_sample))

    assert report.samples == 2
    assert report.eligible_decisions == 1
    assert report.covered_decisions == 1
    assert report.coverage == 1.0
    assert report.agreement_rate == 1.0
