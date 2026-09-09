from datetime import UTC, datetime

from godfield_bot.domain.game import GameState, HandArtifact, PlayerState
from godfield_bot.domain.observation import (
    Bounds,
    ScreenKind,
    ScreenObservation,
    VisibleImage,
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

    weapon_rules = {"bronze-club": ("ATK1", 1.0)}
    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
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

    weapon_rules = {"angel-sword": ("ATK13", 13.0)}
    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert decision.chosen_action_id == "artifact:0:weapons/angel-sword"


def test_heuristic_selects_and_confirms_mp_scaled_weapon() -> None:
    initial = state()
    magical_stick = HandArtifact(
        slot=0,
        category="weapons",
        slug="magical-stick",
        asset_path="/images/items/weapons/magical-stick.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    selecting = initial.model_copy(
        update={
            "hand": (magical_stick,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
        }
    )
    observation = ScreenObservation(
        observed_at=selecting.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.15", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    weapon_rules = {"magical-stick": ("ATK{2\N{MULTIPLICATION SIGN}MP}", 2.0)}
    policy = HeuristicV0Policy(weapon_rules, {"iron-shield": 4})

    selection_actions = verified_browser_actions(
        selecting,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    selection = policy.decide(selecting, selection_actions)

    assert selection.chosen_action_id == "artifact:0:weapons/magical-stick"

    confirming = selecting.model_copy(
        update={
            "action_target": "CPU",
            "action_display": "ATK20",
            "action_artifact_asset_path": magical_stick.asset_path,
            "action_hit_target_bounds": Bounds(x=115, y=93, width=310, height=300),
        }
    )
    confirmation_actions = verified_browser_actions(
        confirming,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    confirmation = policy.decide(confirming, confirmation_actions)

    assert confirmation.chosen_action_id == "confirm:attack:magical-stick:1:CPU"

    mismatched = confirming.model_copy(update={"action_display": "ATK18"})
    mismatched_actions = verified_browser_actions(
        mismatched,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    assert [action.action_id for action in mismatched_actions.actions] == ["wait"]


def test_heuristic_selects_and_confirms_automatic_effect_weapon() -> None:
    initial = state()
    spiritual_staff = HandArtifact(
        slot=0,
        category="weapons",
        slug="spiritual-staff",
        asset_path="/images/items/weapons/spiritual-staff.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    weapon_rules = {"spiritual-staff": ("ATK12", 12.0)}
    policy = HeuristicV0Policy(weapon_rules, {"iron-shield": 4})
    selecting = initial.model_copy(
        update={
            "hand": (spiritual_staff,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
        }
    )
    observation = ScreenObservation(
        observed_at=selecting.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.22", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    selection_actions = verified_browser_actions(
        selecting,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    assert policy.decide(selecting, selection_actions).chosen_action_id == (
        "artifact:0:weapons/spiritual-staff"
    )

    confirming = selecting.model_copy(
        update={
            "action_target": "CPU",
            "action_display": "ATK12",
            "action_artifact_asset_path": spiritual_staff.asset_path,
            "action_hit_target_bounds": Bounds(x=115, y=93, width=310, height=300),
        }
    )
    confirmation_actions = verified_browser_actions(
        confirming,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    assert policy.decide(confirming, confirmation_actions).chosen_action_id == (
        "confirm:attack:spiritual-staff:1:CPU"
    )


def test_heuristic_confirms_audited_random_target_weapon() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_target": None,
            "action_display": "ATK30",
            "action_artifact_asset_path": "/images/items/weapons/dangerous-pestle.webp",
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
        text=("Training", "G.F.1", "ATK30", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    weapon_rules = {"dangerous-pestle": ("ATK30", 30.0)}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert actions.actions[-1].action_id == "confirm:untargeted:dangerous-pestle"
    assert decision.chosen_action_id == "confirm:untargeted:dangerous-pestle"


def test_heuristic_accepts_ascension_variant_of_chance_weapon() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_target": None,
            "action_display": "75%ATK30",
            "action_artifact_asset_path": "/images/items/weapons/ascension-bow.webp",
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
        text=("Training", "G.F.1", "75%ATK30", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    weapon_rules = {"ascension-bow": ("25%ATK1", 0.25, ("75%ATK30",))}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert actions.actions[-1].action_id == "confirm:chance:ascension-bow"
    assert actions.actions[-1].expected_action_display == "75%ATK30"
    assert decision.chosen_action_id == "confirm:chance:ascension-bow"


def test_heuristic_selects_affordable_fixed_attack_miracle() -> None:
    initial = state()
    miracle = HandArtifact(
        slot=0,
        category="miracles",
        slug="flame",
        asset_path="/images/items/miracles/flame.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    game_state = initial.model_copy(
        update={
            "hand": (miracle,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
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
        text=("Training", "G.F.1", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    miracle_rules = {"flame": (10, 5, "fire")}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_miracle_attacks=miracle_rules,
    )
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
        miracle_rules,
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "pass",
        "artifact:0:miracles/flame",
    ]
    assert decision.chosen_action_id == "artifact:0:miracles/flame"


def test_heuristic_excludes_unaffordable_fixed_attack_miracle() -> None:
    initial = state()
    miracle = HandArtifact(
        slot=0,
        category="miracles",
        slug="flame",
        asset_path="/images/items/miracles/flame.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    players = tuple(
        player.model_copy(update={"mp": 4}) if player.is_self else player
        for player in initial.players
    )
    game_state = initial.model_copy(
        update={
            "players": players,
            "hand": (miracle,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
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
        text=("Training", "G.F.1", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_miracle_attacks={"flame": (10, 5, "fire")},
    )

    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
        {"flame": (10, 5, "fire")},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "pass"]
    assert decision.chosen_action_id == "pass"
    assert decision.executable is True


def test_heuristic_passes_when_only_attack_booster_weapon_is_usable() -> None:
    initial = state()
    booster = HandArtifact(
        slot=0,
        category="weapons",
        slug="sky-harpoon",
        asset_path="/images/items/weapons/sky-harpoon.webp",
        bounds=Bounds(x=200, y=493, width=80, height=80),
        hit_target_bounds=Bounds(x=200, y=493, width=80, height=80),
    )
    game_state = initial.model_copy(
        update={
            "hand": (booster,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
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
        text=("Training", "G.F.10", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks={"bronze-club": ("ATK1", 1.0)},
    )
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "pass"]
    assert decision.chosen_action_id == "pass"
    assert decision.executable is True


def test_heuristic_passes_when_verified_attack_weapon_is_disabled() -> None:
    initial = state()
    disabled_weapon = initial.hand[0].model_copy(update={"hit_target_bounds": None})
    game_state = initial.model_copy(
        update={
            "hand": (disabled_weapon,),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
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
        text=("Training", "G.F.17", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    weapon_rules = {"bronze-club": ("ATK1", 1.0)}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "pass"]
    assert decision.chosen_action_id == "pass"
    assert decision.executable is True


def test_pray_transition_without_hit_target_does_not_expose_pass() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "hand": (),
            "action_actor": "ロキ-67",
            "action_display": "Pray",
            "action_hit_target_bounds": None,
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.20", "Pray", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(game_state, observation)

    assert [action.action_id for action in actions.actions] == ["wait"]


def test_heuristic_confirms_selected_fixed_attack_miracle() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_target": "CPU",
            "action_display": "ATK10",
            "action_display_color": "rgb(221, 102, 68)",
            "action_artifact_asset_path": "/images/items/miracles/flame.webp",
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
        text=("Training", "G.F.1", "ATK10", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    miracle_rules = {"flame": (10, 5, "fire")}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_miracle_attacks=miracle_rules,
    )
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
        miracle_rules,
    ).decide(game_state, actions)

    assert actions.actions[-1].action_id == "confirm:attack:flame:1:CPU"
    assert decision.chosen_action_id == "confirm:attack:flame:1:CPU"


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

    armor_rules = {"iron-shield": 4}
    actions = verified_browser_actions(
        game_state,
        observation,
        plain_armor_defenses=armor_rules,
    )
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        armor_rules,
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
        {"bronze-club": ("ATK1", 1.0)},
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
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "forgive"]
    assert decision.chosen_action_id == "forgive"


def test_heuristic_forgives_targeted_interaction_with_multiple_context_artifacts() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
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
        text=("Training", "G.F.3", "Sell", "Dreaming Hat", "Forgive", "HP"),
        text_elements=(),
        controls=(),
        images=(
            VisibleImage(
                path="/images/items/trade/sell.webp",
                bounds=Bounds(x=125, y=103, width=80, height=80),
            ),
            VisibleImage(
                path="/images/items/armor/dreaming-hat.webp",
                bounds=Bounds(x=125, y=203, width=80, height=80),
            ),
        ),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "forgive"]
    assert actions.actions[1].artifact_asset_path is None
    assert actions.actions[1].context_asset_paths == (
        "/images/items/trade/sell.webp",
        "/images/items/armor/dreaming-hat.webp",
    )
    assert decision.chosen_action_id == "forgive"


def test_heuristic_forgives_incoming_artifact_rendered_low_in_action_panel() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "CPU",
            "action_target": "ロキ-67",
            "action_display": "ATK5",
            "action_display_color": "rgb(197, 197, 0)",
            "phase_control": "Forgive",
            "phase_control_hit_target_bounds": Bounds(x=455, y=93, width=310, height=300),
        }
    )
    blessing = "/images/items/guardians/blessing.webp"
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.35", "ATK5", "Forgive", "HP"),
        text_elements=(),
        controls=(),
        images=(
            VisibleImage(
                path="/images/guardians/large/uranus.webp",
                bounds=Bounds(x=120, y=93, width=300, height=300),
            ),
            VisibleImage(
                path=blessing,
                bounds=Bounds(x=125, y=303, width=80, height=80),
            ),
        ),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == ["wait", "forgive"]
    assert actions.actions[1].context_asset_paths == (blessing,)
    assert decision.chosen_action_id == "forgive"


def test_heuristic_forgives_reflected_outgoing_attack_from_left_panel() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_target": "CPU",
            "action_display": "Forgive",
            "action_display_color": "rgb(238, 221, 221)",
            "action_hit_target_bounds": Bounds(x=115, y=93, width=310, height=300),
            "phase_artifact_asset_path": "/images/items/weapons/angel-sword.webp",
            "phase_control": "ATK13",
            "phase_control_color": "rgb(79, 79, 79)",
        }
    )
    observation = ScreenObservation(
        observed_at=game_state.observed_at,
        url="https://godfield.net/?lang=en",
        title="God Field",
        kind=ScreenKind.GAME,
        viewport_width=1280,
        viewport_height=800,
        text=("Training", "G.F.1", "Forgive", "ATK13", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )

    actions = verified_browser_actions(game_state, observation)
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "forgive:reflected",
    ]
    assert actions.actions[1].control_panel == "left"
    assert actions.actions[1].context_asset_paths == (
        "/images/items/weapons/angel-sword.webp",
    )
    assert decision.chosen_action_id == "forgive:reflected"


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
        verified_weapon_attacks={"bronze-club": ("ATK1", 1.0)},
    )
    decision = HeuristicV0Policy(
        {"bronze-club": ("ATK1", 1.0)},
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
        verified_weapon_attacks={"bronze-club": ("ATK1", 1.0)},
    )

    assert [action.action_id for action in actions.actions] == ["wait"]


def test_heuristic_confirms_probabilistic_elemental_weapon() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_target": "CPU",
            "action_display": "ATK2",
            "action_display_color": "rgb(136, 102, 170)",
            "action_artifact_asset_path": "/images/items/weapons/shadow-hand.webp",
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
    weapon_rules = {"shadow-hand": ("50%ATK2", 1.0)}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert actions.actions[-1].action_id == "confirm:attack:shadow-hand:1:CPU"
    assert decision.chosen_action_id == "confirm:attack:shadow-hand:1:CPU"


def test_heuristic_resolves_untargeted_probabilistic_weapon() -> None:
    initial = state()
    game_state = initial.model_copy(
        update={
            "action_actor": "ロキ-67",
            "action_display": "50%ATK5",
            "action_display_color": "rgb(102, 102, 255)",
            "action_artifact_asset_path": "/images/items/weapons/oversize-snowball.webp",
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
        text=("Training", "G.F.7", "50%ATK5", "HP"),
        text_elements=(),
        controls=(),
        images=(),
    )
    weapon_rules = {"oversize-snowball": ("50%ATK5", 2.5)}

    actions = verified_browser_actions(
        game_state,
        observation,
        verified_weapon_attacks=weapon_rules,
    )
    decision = HeuristicV0Policy(
        weapon_rules,
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert actions.actions[-1].action_id == "confirm:chance:oversize-snowball"
    assert actions.actions[-1].target_player_name is None
    assert decision.chosen_action_id == "confirm:chance:oversize-snowball"


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
        {"bronze-club": ("ATK1", 1.0)},
        {"iron-shield": 4},
    ).decide(game_state, actions)

    assert [action.action_id for action in actions.actions] == [
        "wait",
        "confirm:defense:iron-shield:0:ロキ-67",
    ]
    assert actions.actions[1].control_panel == "right"
    assert decision.chosen_action_id == "confirm:defense:iron-shield:0:ロキ-67"
