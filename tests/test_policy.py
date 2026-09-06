from datetime import UTC, datetime

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import (
    Bounds,
    ScreenKind,
    ScreenObservation,
)
from godfield_bot.legal_actions import (
    game_state_digest,
    observation_only_actions,
    verified_browser_actions,
)
from godfield_bot.policy import HeuristicV0Policy, SafeObserverPolicy


def state() -> GameState:
    return GameState(
        observed_at=datetime.now(UTC),
        field_number=0,
        self_player_index=0,
        players=(
            PlayerState(name="ロキ-67", hp=40, mp=10, money=20, is_self=True),
            PlayerState(name="CPU", hp=40, mp=10, money=20, is_self=False),
        ),
        hand=(
            HandArtifact(
                slot=0,
                category="weapons",
                slug="bronze-club",
                asset_path="/images/items/weapons/bronze-club.webp",
                bounds=Bounds(x=200, y=493, width=80, height=80),
            ),
        ),
        scene_layers=("/images/screens/fog.webp",),
    )


def test_state_digest_ignores_observation_time() -> None:
    first = state()
    second = first.model_copy(update={"observed_at": datetime(2030, 1, 1, tzinfo=UTC)})

    assert game_state_digest(first) == game_state_digest(second)


def test_safe_policy_only_selects_non_executable_wait() -> None:
    game_state = state()
    actions = observation_only_actions(game_state)

    decision = SafeObserverPolicy().decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait"]
    assert actions.coverage_complete is False
    assert decision.chosen_action_id == "wait"
    assert decision.executable is False
    assert decision.state_digest == actions.state_digest


def test_heuristic_selects_weapon_only_in_verified_self_phase() -> None:
    initial = state()
    weapon = initial.hand[0].model_copy(update={"hit_target_bounds": initial.hand[0].bounds})
    game_state = initial.model_copy(
        update={
            "hand": (weapon,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
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

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": 1},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "artifact:0:weapons/bronze-club",
    ]
    assert decision.chosen_action_id == "artifact:0:weapons/bronze-club"
    assert decision.executable is True


def test_heuristic_can_select_audited_passive_attack_weapon() -> None:
    initial = state()
    passive_weapon = HandArtifact(
        slot=0,
        category="weapons",
        slug="angel-sword",
        asset_path="/images/items/weapons/angel-sword.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    game_state = initial.model_copy(
        update={
            "hand": (passive_weapon,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
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

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"angel-sword": 13},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert decision.chosen_action_id == "artifact:0:weapons/angel-sword"


def test_heuristic_selects_plain_armor_for_neutral_defense() -> None:
    initial = state()
    armor = HandArtifact(
        slot=0,
        category="armor",
        slug="iron-shield",
        asset_path="/images/items/armor/iron-shield.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    game_state = initial.model_copy(
        update={
            "hand": (armor,),
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_display": "ATK13",
            "action_display_color": "rgb(79, 79, 79)",
            "action_artifact_asset_path": "/images/items/weapons/bronze-club.webp",
            "phase_control": "Forgive",
            "phase_control_hit_target_bounds": Bounds(x=455, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "ATK13", "Forgive", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": 1},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "artifact:0:armor/iron-shield",
        "forgive",
    ]
    assert decision.chosen_action_id == "artifact:0:armor/iron-shield"


def test_heuristic_forgives_elemental_attack_without_verified_defense() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_display": "ATK13",
            "action_display_color": "rgb(102, 136, 170)",
            "action_artifact_asset_path": "/images/items/weapons/diamond-sword.webp",
            "phase_control": "Forgive",
            "phase_control_hit_target_bounds": Bounds(x=455, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "ATK13", "Forgive", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": 1},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "forgive"]
    assert decision.chosen_action_id == "forgive"
    assert decision.executable is True


def test_heuristic_forgives_identified_incoming_non_attack_effect() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_artifact_asset_path": "/images/items/sundries/thump-thump-tear.webp",
            "phase_control": "Forgive",
            "phase_control_hit_target_bounds": Bounds(x=455, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "Forgive", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": 1},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "forgive"]
    assert decision.chosen_action_id == "forgive"


def test_heuristic_confirms_plain_weapon_on_named_sole_opponent() -> None:
    initial = state()
    target_bounds = Bounds(x=780, y=264, width=340, height=40)
    game_state = initial.model_copy(
        update={
            "players": (
                initial.players[0],
                initial.players[1].model_copy(update={"hit_target_bounds": target_bounds}),
            ),
            "action_actor": "ロキ-67",
            "action_target": "CPU",
            "action_display": "ATK1",
            "action_display_color": "rgb(79, 79, 79)",
            "action_artifact_asset_path": "/images/items/weapons/bronze-club.webp",
            "action_hit_target_bounds": Bounds(x=115, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "ATK1", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks={"bronze-club": 1},
    )
    decision = HeuristicV0Policy(
        {"bronze-club": 1},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "confirm:attack:bronze-club:1:CPU",
    ]
    assert actions.actions[1].target_player_index == 1
    assert actions.actions[1].target_player_name == "CPU"
    assert actions.actions[1].artifact_asset_path == "/images/items/weapons/bronze-club.webp"
    assert actions.actions[1].control_panel == "left"
    assert decision.chosen_action_id == "confirm:attack:bronze-club:1:CPU"
    assert decision.executable is True


def test_targeting_fails_closed_when_displayed_attack_does_not_match_bible() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "players": (
                initial.players[0],
                initial.players[1].model_copy(
                    update={"hit_target_bounds": Bounds(x=780, y=264, width=340, height=40)}
                ),
            ),
            "action_actor": "ロキ-67",
            "action_target": "CPU",
            "action_display": "ATK2",
            "action_display_color": "rgb(79, 79, 79)",
            "action_artifact_asset_path": "/images/items/weapons/bronze-club.webp",
            "action_hit_target_bounds": Bounds(x=115, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "ATK2", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks={"bronze-club": 1},
    )

    assert [action.action_id for action in actions.actions] == ["wait"]


def test_heuristic_confirms_plain_armor_for_neutral_attack() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_display": "ATK2",
            "action_display_color": "rgb(79, 79, 79)",
            "action_artifact_asset_path": "/images/items/weapons/whip.webp",
            "phase_control": "DEF4",
            "phase_artifact_asset_path": "/images/items/armor/iron-shield.webp",
            "phase_control_hit_target_bounds": Bounds(x=455, y=93, width=310, height=300),
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "ATK2", "DEF4", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(
        game_state,
        observation,
        plain_armor_defenses={"iron-shield": 4},
    )
    decision = HeuristicV0Policy(
        {"bronze-club": 1},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "confirm:defense:iron-shield:0:ロキ-67",
    ]
    assert actions.actions[1].control_panel == "right"
    assert decision.chosen_action_id == "confirm:defense:iron-shield:0:ロキ-67"
