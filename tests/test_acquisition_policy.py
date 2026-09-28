"""Collection-only interventions never invent actions or become teacher samples."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_outcome_replay import append_complete_episode
from test_policy import state
from typer.testing import CliRunner

from godfield_bot.acquisition_policy import ACQUISITION_POLICY_ID, AcquisitionMiraclePolicy
from godfield_bot.acquisition_probe import ACQUISITION_REVIEWED_CLIENT_SHA256
from godfield_bot.cli import app
from godfield_bot.config import AppSettings
from godfield_bot.domain.action import ActionKind, LegalAction, LegalActionSet
from godfield_bot.domain.game import HandArtifact
from godfield_bot.domain.observation import Bounds, ScreenKind, ScreenObservation
from godfield_bot.domain.run import RunMode, RunSpec
from godfield_bot.legal_actions import game_state_digest, verified_browser_actions
from godfield_bot.outcome_replay import (
    OutcomeReplayDatasetError,
    collect_outcome_replay,
    load_outcome_replay_jsonl,
)
from godfield_bot.policy import HeuristicV0Policy
from godfield_bot.replay import (
    ReplayDatasetError,
    collect_replay_samples,
    collect_run_replay_samples,
    load_replay_jsonl,
)
from godfield_bot.run_store import RunStore
from godfield_bot.runner import (
    RunnerPolicyName,
    TrainingCampaignConfig,
    TrainingCampaignSummary,
    TrainingRunConfig,
    _record_policy_state,
)

CATALOG = Path("data/snapshots/2026-09-21/api-catalog-en.json")
RULES = {"flame": (10, 5, "fire")}


def policy(**kwargs):
    return AcquisitionMiraclePolicy(
        {"bronze-club": ("ATK20", 20.0)},
        {"iron-shield": 4},
        RULES,
        {"herb": 10},
        {},
        focus=kwargs.get("focus", "flame"),
    )


def scene(*, field=1, mp=10, hp=40, extra=()):
    initial = state()
    return initial.model_copy(
        update={
            "field_number": field,
            "players": tuple(
                player.model_copy(update={"hp": hp, "mp": mp}) if player.is_self else player
                for player in initial.players
            ),
            "hand": (
                *initial.hand,
                HandArtifact(
                    slot=1,
                    category="miracles",
                    slug="flame",
                    asset_path="/images/items/miracles/flame.webp",
                    bounds=initial.hand[0].bounds,
                ),
                *extra,
            ),
        }
    )


def actions(game, *, omit_focus=False, extra=()):
    return LegalActionSet(
        state_digest=game_state_digest(game),
        actions=(
            LegalAction(action_id="wait", kind=ActionKind.WAIT, label="Wait"),
            *(
                LegalAction(
                    action_id=f"artifact:{item.slot}:{item.category}/{item.slug}",
                    kind=ActionKind.SELECT_ARTIFACT,
                    label=f"Select {item.slug}",
                    artifact_slot=item.slot,
                    artifact_asset_path=item.asset_path,
                )
                for item in game.hand
                if not (omit_focus and item.slug == "flame")
            ),
            *extra,
        ),
        coverage_complete=False,
        blocked_reason="synthetic reviewed actions",
    )


def test_focus_overrides_stronger_weapon_without_changing_normal_policy():
    game = scene()
    legal = actions(game)
    normal = HeuristicV0Policy({"bronze-club": ("ATK20", 20.0)}, {"iron-shield": 4}, RULES)
    assert normal.decide(game, legal).chosen_action_id == "artifact:0:weapons/bronze-club"
    focused = policy().decide(game, legal)
    assert focused.policy_id == ACQUISITION_POLICY_ID
    assert focused.chosen_action_id == "artifact:1:miracles/flame"
    assert "1/2" in focused.rationale and "not evidence" in focused.rationale


def test_budget_counts_prioritized_states_not_repeated_polls_and_resets_per_game():
    collector = policy()
    for field in (1, 2):
        game = scene(field=field)
        legal = actions(game)
        first = collector.decide(game, legal)
        assert first.chosen_action_id == "artifact:1:miracles/flame"
        for _ in range(5):
            assert collector.decide(game, legal) == first
        assert collector.prioritized_selection_count == field
    game = scene(field=3)
    assert collector.decide(game, actions(game)).chosen_action_id.endswith("weapons/bronze-club")
    game = scene(field=1)  # Revisiting an old digest cannot bypass the budget.
    assert collector.decide(game, actions(game)).chosen_action_id.endswith("weapons/bronze-club")
    assert policy().prioritized_selection_count == 0


@pytest.mark.parametrize("mp,omit_focus", [(4, False), (10, True)])
def test_unaffordable_or_unverified_focus_falls_back(mp, omit_focus):
    collector = policy()
    game = scene(mp=mp)
    decision = collector.decide(game, actions(game, omit_focus=omit_focus))
    assert decision.chosen_action_id.endswith("weapons/bronze-club")
    assert collector.prioritized_selection_count == 0


@pytest.mark.parametrize(
    "category,slug,hp", [("armor", "iron-shield", 40), ("sundries", "herb", 20)]
)
def test_defense_and_urgent_hp_utility_are_preserved(category, slug, hp):
    item = HandArtifact(
        slot=2,
        category=category,
        slug=slug,
        asset_path=f"/images/items/{category}/{slug}.webp",
        bounds=state().hand[0].bounds,
    )
    game = scene(hp=hp, extra=(item,))
    collector = policy()
    assert collector.decide(game, actions(game)).chosen_action_id == f"artifact:2:{category}/{slug}"
    assert collector.prioritized_selection_count == 0


def test_wait_and_confirmation_controls_are_preserved():
    game = scene()
    collector = policy()
    wait = actions(game).actions[0]
    only_wait = actions(game).model_copy(update={"actions": (wait,)})
    assert collector.decide(game, only_wait).chosen_action_id == "wait"
    confirmation = LegalAction(
        action_id="confirm",
        kind=ActionKind.CONFIRM,
        label="Confirm",
        artifact_slot=1,
        artifact_asset_path=game.hand[1].asset_path,
        target_player_index=1,
        target_player_name="CPU",
        control_panel="right",
    )
    assert (
        collector.decide(game, actions(game, extra=(confirmation,))).chosen_action_id == "confirm"
    )
    assert collector.prioritized_selection_count == 0


def test_invalid_focus_and_stale_action_digest_are_rejected():
    with pytest.raises(ValueError, match="reviewed"):
        policy(focus="unknown")
    game = scene()
    with pytest.raises(ValueError, match="current state"):
        policy().decide(game, actions(game).model_copy(update={"state_digest": "a" * 64}))


def test_runner_records_focus_only_with_the_existing_real_legal_generator(tmp_path, monkeypatch):
    game = scene().model_copy(
        update={
            "hand": tuple(
                item.model_copy(update={"hit_target_bounds": item.bounds}) for item in scene().hand
            ),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
            "action_hit_target_bounds": Bounds(x=115, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    collector = policy()
    legal = verified_browser_actions(
        game,
        observation,
        verified_weapon_attacks=collector.verified_weapon_attacks,
        verified_miracle_attacks=RULES,
    )
    assert "artifact:1:miracles/flame" in {action.action_id for action in legal.actions}
    storage = RunStore(tmp_path / "runs.sqlite")
    run = storage.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256="a" * 64,
            policy_id=ACQUISITION_POLICY_ID,
            config={"collection_only": True},
        )
    )
    monkeypatch.setattr("godfield_bot.runner.parse_game_state", lambda *_args, **_kwargs: game)
    digest, decision, action, _ = _record_policy_state(
        storage,
        run.run_id,
        observation,
        AppSettings(),
        collector,
        None,
        None,
    )
    assert action.action_id == "artifact:1:miracles/flame"
    assert decision.policy_id == ACQUISITION_POLICY_ID
    assert _record_policy_state(
        storage,
        run.run_id,
        observation,
        AppSettings(),
        collector,
        digest,
        game,
    )[1:3] == (None, None)
    assert collector.prioritized_selection_count == 1


def config(**changes):
    return TrainingRunConfig(
        **(
            {
                "expected_client_sha256": ACQUISITION_REVIEWED_CLIENT_SHA256,
                "policy": RunnerPolicyName.OFFICIAL_TRAINING_ACQUISITION,
                "acquisition_miracle_focus": "flame",
                "acquisition_evidence_probe": True,
                "acquisition_evidence_catalog": CATALOG,
                "max_seconds": 300,
                "max_in_match_actions": 100,
                "verified_weapon_attacks": {"bronze-club": ("ATK1", 1.0)},
                "verified_miracle_attacks": RULES,
                "plain_armor_defenses": {"iron-shield": 4},
            }
            | changes
        )
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"acquisition_evidence_probe": False},
        {"max_seconds": 0},
        {"acquisition_miracle_focus": "unknown"},
        {"acquisition_miracle_focus": None},
        {"policy": RunnerPolicyName.HEURISTIC_V0},
        {"model_directory": Path("models")},
        {"shadow_model_directory": Path("models"), "bible_snapshot": Path("bible.json")},
    ],
)
def test_collection_config_rejects_unbounded_unreviewed_or_model_control(changes):
    with pytest.raises(ValidationError):
        config(**changes)


def test_campaign_requires_positive_game_budget():
    with pytest.raises(ValidationError, match="positive --max-games"):
        TrainingCampaignConfig(game=config())
    assert TrainingCampaignConfig(game=config(), max_games=3).max_games == 3


def test_cli_focus_selects_separate_policy_and_keeps_models_off(monkeypatch):
    captured = []

    async def campaign(_settings, campaign_config):
        captured.append(campaign_config)
        return TrainingCampaignSummary(
            max_games=3,
            games_started=0,
            games_completed=0,
            wins=0,
            losses=0,
            draws=0,
            run_ids=(),
            stop_reason="game_limit",
            last_run_status="completed",
        )

    monkeypatch.setattr("godfield_bot.cli.run_training_campaign", campaign)
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        app,
        [
            "play-training",
            "--acquisition-evidence-probe",
            "--acquisition-miracle-focus",
            "flame",
            "--max-games",
            "3",
            "--max-seconds",
            "300",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured[0].game.policy is RunnerPolicyName.OFFICIAL_TRAINING_ACQUISITION
    assert captured[0].game.acquisition_miracle_focus == "flame"
    assert captured[0].game.model_directory is None


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--max-games", "1", "--max-seconds", "0", "--acquisition-evidence-probe"],
        ["--max-games", "1", "--confirm-neural-control"],
        [
            "--max-games",
            "1",
            "--acquisition-evidence-probe",
            "--acquisition-miracle-focus",
            "unknown",
        ],
    ],
)
def test_cli_rejects_invalid_focus_before_starting_campaign(monkeypatch, arguments):
    async def forbidden(*_args):
        pytest.fail("invalid collection mode reached browser workflow")

    monkeypatch.setattr("godfield_bot.cli.run_training_campaign", forbidden)
    monkeypatch.setattr("godfield_bot.cli.configure_logging", lambda **_kwargs: None)
    assert (
        CliRunner()
        .invoke(
            app,
            [
                "play-training",
                "--acquisition-miracle-focus",
                "flame",
                *arguments,
            ],
        )
        .exit_code
        != 0
    )


@pytest.mark.parametrize(
    "policy_id,metadata",
    [
        (ACQUISITION_POLICY_ID, {}),
        ("heuristic-v0", {"collection_only": True}),
    ],
)
def test_collection_runs_are_excluded_from_both_training_exports(tmp_path, policy_id, metadata):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256="a" * 64,
            policy_id=policy_id,
            config=metadata,
        )
    )
    append_complete_episode(store, run.run_id)
    samples, replay_summary = collect_replay_samples(store)
    episodes, outcome_summary = collect_outcome_replay(store)
    assert samples == episodes == ()
    assert replay_summary.skipped["collection_only_run"] == 1
    assert outcome_summary.skipped["collection_only_run"] == 1


def test_existing_jsonl_collection_policy_cannot_bypass_export_guard(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run = store.start_run(
        RunSpec(
            mode=RunMode.TRAINING,
            identity="ロキ-67",
            client_sha256="a" * 64,
            policy_id="heuristic-v0",
        )
    )
    append_complete_episode(store, run.run_id)
    completed = store.get_run(run.run_id)
    samples, _, _ = collect_run_replay_samples(completed, store.events(run.run_id))
    payload = samples[0].model_dump(mode="json")
    payload["policy_id"] = ACQUISITION_POLICY_ID
    payload["decision"]["policy_id"] = ACQUISITION_POLICY_ID
    path = tmp_path / "replay.jsonl"
    path.write_text(json.dumps(payload) + "\n")
    with pytest.raises(ReplayDatasetError, match="collection-only"):
        load_replay_jsonl(path)
    episodes, _ = collect_outcome_replay(store)
    payload = episodes[0].model_dump(mode="json")
    payload["policy_id"] = ACQUISITION_POLICY_ID
    payload["steps"][0]["policy_id"] = ACQUISITION_POLICY_ID
    payload["steps"][0]["decision"]["policy_id"] = ACQUISITION_POLICY_ID
    path.write_text(json.dumps(payload) + "\n")
    with pytest.raises(OutcomeReplayDatasetError, match="collection-only"):
        load_outcome_replay_jsonl(path)
