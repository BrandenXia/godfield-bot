import asyncio
import hashlib
import os
from contextlib import suppress
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import structlog
from playwright.async_api import Page
from pydantic import BaseModel, Field, JsonValue, model_validator

from godfield_bot.account import start_account_session
from godfield_bot.browser.controls import click_header_back, click_text_control
from godfield_bot.browser.profile import open_account_context, prepare_private_directory
from godfield_bot.config import AppSettings
from godfield_bot.domain.action import ActionTransition, LegalAction, PolicyDecision
from godfield_bot.domain.game import GameState
from godfield_bot.domain.observation import ScreenKind, ScreenObservation
from godfield_bot.domain.outcome import MatchOutcome, SparseTerminalReward
from godfield_bot.domain.run import EventKind, RunMode, RunRecord, RunSpec, RunStatus
from godfield_bot.elements import CombatElement
from godfield_bot.executor import execute_action
from godfield_bot.game_state import GameStateParseError, parse_game_state
from godfield_bot.legal_actions import game_state_digest, verified_browser_actions
from godfield_bot.observer import capture_screen
from godfield_bot.outcomes import append_sparse_terminal_events
from godfield_bot.policy import HeuristicV0Policy, Policy, SafeObserverPolicy
from godfield_bot.reference import fingerprint_client
from godfield_bot.run_store import RunStore
from godfield_bot.weapon_rules import WeaponAttackRule

log = structlog.get_logger()


class RunnerPolicyName(StrEnum):
    SAFE_OBSERVER = "safe-observer-v0"
    HEURISTIC_V0 = "heuristic-v0"


class TrainingRunConfig(BaseModel):
    database: Path = Path("runs", "godfield.sqlite")
    expected_client_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    headed: bool = True
    max_seconds: float = Field(default=90.0, ge=10.0, le=3600.0)
    room_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    poll_seconds: float = Field(default=2.0, ge=0.25, le=10.0)
    no_progress_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    unknown_screen_grace_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    render_settle_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    screenshot_directory: Path | None = None
    policy: RunnerPolicyName = RunnerPolicyName.SAFE_OBSERVER
    max_in_match_actions: int = Field(default=0, ge=0, le=100)
    verified_weapon_attacks: dict[str, WeaponAttackRule] = Field(default_factory=dict)
    verified_miracle_attacks: dict[str, tuple[int, int, CombatElement]] = Field(
        default_factory=dict
    )
    plain_hp_utilities: dict[str, int] = Field(default_factory=dict)
    plain_mp_utilities: dict[str, int] = Field(default_factory=dict)
    plain_armor_defenses: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def executable_policy_has_action_budget(self) -> "TrainingRunConfig":
        if self.policy is RunnerPolicyName.HEURISTIC_V0 and self.max_in_match_actions < 1:
            raise ValueError("heuristic-v0 requires a positive in-match action budget")
        if self.policy is RunnerPolicyName.HEURISTIC_V0 and (
            not self.verified_weapon_attacks or not self.plain_armor_defenses
        ):
            raise ValueError("heuristic-v0 requires Bible-audited artifact values")
        return self


class TrainingCampaignConfig(BaseModel):
    """Repeat isolated official-CPU games while preserving one run per episode."""

    game: TrainingRunConfig
    max_games: int = Field(default=0, ge=0, le=100_000)
    restart_delay_seconds: float = Field(default=2.0, ge=0.0, le=60.0)
    max_setup_retries: int = Field(default=3, ge=0, le=100)


class TrainingCampaignSummary(BaseModel):
    schema_version: int = 1
    max_games: int = Field(ge=0)
    games_started: int = Field(ge=0)
    games_completed: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    draws: int = Field(ge=0)
    setup_failures: int = Field(default=0, ge=0)
    run_ids: tuple[str, ...]
    stop_reason: str
    last_run_status: RunStatus


class RunnerError(RuntimeError):
    """Raised when a run cannot continue without violating a safety contract."""


async def _enter_fresh_training_room(page: Page, *, timeout_ms: float) -> None:
    await click_header_back(page, "Training")
    await page.get_by_text("Hidden Melee", exact=True).wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    await click_text_control(page, "Training")


async def _reach_training_game(
    page: Page,
    observation: ScreenObservation,
    config: TrainingRunConfig,
) -> ScreenObservation:
    room_timeout_ms = config.room_timeout_seconds * 1_000
    entered_room_now = False
    if observation.kind is ScreenKind.MENU:
        await click_text_control(page, "Training")
        entered_room_now = True
        await page.wait_for_function(
            """
            () => document.body.innerText.includes('Training') &&
              !document.body.innerText.includes('Hidden Melee')
            """,
            timeout=room_timeout_ms,
        )
        observation = await capture_screen(page)
    if observation.kind is ScreenKind.GAME:
        await page.wait_for_timeout(config.render_settle_seconds * 1_000)
        return await capture_screen(page)
    if observation.kind is not ScreenKind.TRAINING_SETUP:
        raise RunnerError(f"cannot enter Training from screen {observation.kind}")

    start_battle = page.get_by_text("Start Battle", exact=True)
    if not entered_room_now and not await start_battle.is_visible():
        await _enter_fresh_training_room(page, timeout_ms=room_timeout_ms)
    await start_battle.wait_for(state="visible", timeout=room_timeout_ms)
    await click_text_control(page, "Start Battle")
    await page.wait_for_function(
        """
        () => document.body.innerText.includes('G.F.') &&
          document.body.innerText.includes('HP')
        """,
        timeout=room_timeout_ms,
    )
    await page.wait_for_timeout(config.render_settle_seconds * 1_000)
    observation = await capture_screen(page)
    if observation.kind is not ScreenKind.GAME:
        raise RunnerError(f"Start Battle did not reach a game screen: {observation.kind}")
    return observation


def _record_policy_state(
    store: RunStore,
    run_id: str,
    observation: ScreenObservation,
    settings: AppSettings,
    policy: Policy,
    previous_digest: str | None,
    previous_state: GameState | None,
) -> tuple[str, PolicyDecision | None, LegalAction | None, GameState]:
    state = parse_game_state(
        observation,
        identity=settings.identity,
        previous_state=previous_state,
    )
    digest = game_state_digest(state)
    if digest == previous_digest:
        return digest, None, None, state
    legal_actions = verified_browser_actions(
        state,
        observation,
        verified_weapon_attacks=(
            policy.verified_weapon_attacks if isinstance(policy, HeuristicV0Policy) else None
        ),
        plain_armor_defenses=(
            policy.plain_armor_defenses if isinstance(policy, HeuristicV0Policy) else None
        ),
        verified_miracle_attacks=(
            policy.verified_miracle_attacks if isinstance(policy, HeuristicV0Policy) else None
        ),
        plain_hp_utilities=(
            policy.plain_hp_utilities if isinstance(policy, HeuristicV0Policy) else None
        ),
        plain_mp_utilities=(
            policy.plain_mp_utilities if isinstance(policy, HeuristicV0Policy) else None
        ),
    )
    decision = policy.decide(state, legal_actions)
    chosen_actions = [
        action for action in legal_actions.actions if action.action_id == decision.chosen_action_id
    ]
    if len(chosen_actions) != 1:
        raise RunnerError("policy chose an action outside the recorded legal set")
    store.append_event(run_id, EventKind.OBSERVATION, observation)
    store.append_event(run_id, EventKind.GAME_STATE, state)
    store.append_event(run_id, EventKind.LEGAL_ACTIONS, legal_actions)
    store.append_event(run_id, EventKind.DECISION, decision)
    log.info(
        "policy_decision_recorded",
        run_id=run_id,
        field_number=state.field_number,
        action=decision.chosen_action_id,
        executable=decision.executable,
    )
    return digest, decision, chosen_actions[0], state


def build_action_transition(
    action_id: str,
    before: GameState,
    after: GameState | None,
) -> ActionTransition:
    before_digest = game_state_digest(before)
    if after is None:
        return ActionTransition(
            observed_at=datetime.now(UTC),
            action_id=action_id,
            before_state_digest=before_digest,
            state_changed=None,
            before_state=before,
        )
    after_digest = game_state_digest(after)
    before_hp = {player.name: player.hp for player in before.players}
    player_hp_deltas = {
        player.name: player.hp - before_hp[player.name]
        for player in after.players
        if player.name in before_hp and player.hp != before_hp[player.name]
    }
    return ActionTransition(
        observed_at=after.observed_at,
        action_id=action_id,
        before_state_digest=before_digest,
        after_state_digest=after_digest,
        state_changed=after_digest != before_digest,
        field_delta=after.field_number - before.field_number,
        player_hp_deltas=player_hp_deltas,
        before_state=before,
        after_state=after,
    )


def _screen_departure_reason(
    observation: ScreenObservation,
    *,
    unknown_seconds: float,
    unknown_grace_seconds: float,
) -> str | None:
    if observation.kind is ScreenKind.GAME:
        return None
    if observation.kind is ScreenKind.UNKNOWN:
        return "unknown_screen_timeout" if unknown_seconds >= unknown_grace_seconds else None
    return "left_gameplay_screen"


def _policy_from_name(
    name: RunnerPolicyName,
    verified_weapon_attacks: dict[str, WeaponAttackRule],
    verified_miracle_attacks: dict[str, tuple[int, int, CombatElement]],
    plain_hp_utilities: dict[str, int],
    plain_mp_utilities: dict[str, int],
    plain_armor_defenses: dict[str, int],
) -> Policy:
    if name is RunnerPolicyName.SAFE_OBSERVER:
        return SafeObserverPolicy()
    if name is RunnerPolicyName.HEURISTIC_V0:
        return HeuristicV0Policy(
            verified_weapon_attacks,
            plain_armor_defenses,
            verified_miracle_attacks,
            plain_hp_utilities,
            plain_mp_utilities,
        )
    raise RunnerError(f"unsupported policy: {name}")


async def run_training_observer(
    settings: AppSettings,
    config: TrainingRunConfig,
) -> RunRecord:
    if settings.public_duel_enabled:
        raise RunnerError("safe observer runner requires public Duel to remain disabled")

    policy = _policy_from_name(
        config.policy,
        config.verified_weapon_attacks,
        config.verified_miracle_attacks,
        config.plain_hp_utilities,
        config.plain_mp_utilities,
        config.plain_armor_defenses,
    )
    store = RunStore(config.database)
    started = datetime.now(UTC)
    run: RunRecord | None = None
    terminal_outcome: MatchOutcome | None = None
    terminal_reward: SparseTerminalReward | None = None
    in_match_actions = 0
    gameplay_started = False
    outcome_reason = "wall_clock_limit"
    try:
        async with open_account_context(settings, headed=config.headed) as context:
            client = await fingerprint_client(context)
            if client.sha256 != config.expected_client_sha256:
                raise RunnerError("live client hash differs from the accepted snapshot")
            run = store.start_run(
                RunSpec(
                    mode=RunMode.TRAINING,
                    identity=settings.identity,
                    client_sha256=client.sha256,
                    policy_id=policy.policy_id,
                    config={
                        "max_games": 1,
                        "max_seconds": config.max_seconds,
                        "poll_seconds": config.poll_seconds,
                        "no_progress_seconds": config.no_progress_seconds,
                        "unknown_screen_grace_seconds": config.unknown_screen_grace_seconds,
                        "max_in_match_actions": config.max_in_match_actions,
                    },
                ),
                started_at=started,
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await start_account_session(
                page,
                settings,
                timeout_seconds=config.room_timeout_seconds,
            )
            observation = await _reach_training_game(
                page,
                await capture_screen(page),
                config,
            )
            gameplay_started = True
            previous_digest: str | None = None
            previous_state: GameState | None = None
            previous_parse_error_digest: str | None = None
            unknown_screen_started_at: float | None = None
            previous_unknown_screen_digest: str | None = None
            loop = asyncio.get_running_loop()
            deadline = loop.time() + config.max_seconds
            last_progress_at = loop.time()
            while loop.time() < deadline:
                now = loop.time()
                if observation.kind is ScreenKind.UNKNOWN:
                    if unknown_screen_started_at is None:
                        unknown_screen_started_at = now
                    unknown_seconds = now - unknown_screen_started_at
                    unknown_digest = hashlib.sha256(
                        observation.model_dump_json(exclude={"observed_at"}).encode()
                    ).hexdigest()
                    if unknown_digest != previous_unknown_screen_digest:
                        store.append_event(run.run_id, EventKind.OBSERVATION, observation)
                        store.append_event(
                            run.run_id,
                            EventKind.ERROR,
                            {
                                "error_type": "TransientUnknownScreen",
                                "reason": "gameplay capture temporarily became unknown",
                                "observation_digest": unknown_digest,
                            },
                        )
                        if config.screenshot_directory is not None:
                            prepare_private_directory(config.screenshot_directory)
                            unknown_path = (
                                config.screenshot_directory
                                / f"{run.run_id}-unknown-{unknown_digest[:12]}.png"
                            )
                            await page.screenshot(path=str(unknown_path), full_page=True)
                            os.chmod(unknown_path, 0o600)
                        previous_unknown_screen_digest = unknown_digest
                    departure_reason = _screen_departure_reason(
                        observation,
                        unknown_seconds=unknown_seconds,
                        unknown_grace_seconds=min(
                            config.unknown_screen_grace_seconds,
                            config.no_progress_seconds,
                        ),
                    )
                    if departure_reason is None:
                        log.warning(
                            "transient_unknown_gameplay_screen",
                            run_id=run.run_id,
                            unknown_seconds=unknown_seconds,
                        )
                        await page.wait_for_timeout(config.poll_seconds * 1_000)
                        observation = await capture_screen(page)
                        continue
                else:
                    unknown_screen_started_at = None
                    previous_unknown_screen_digest = None
                    departure_reason = _screen_departure_reason(
                        observation,
                        unknown_seconds=0,
                        unknown_grace_seconds=config.unknown_screen_grace_seconds,
                    )
                if departure_reason is not None:
                    if observation.kind is not ScreenKind.UNKNOWN:
                        store.append_event(run.run_id, EventKind.OBSERVATION, observation)
                    store.append_event(
                        run.run_id,
                        EventKind.MATCH_END,
                        {
                            "classification": (
                                "sustained_unknown_terminal_candidate"
                                if observation.kind is ScreenKind.UNKNOWN
                                else "unclassified_terminal_candidate"
                            ),
                            "screen_kind": observation.kind.value,
                            "visible_text": list(observation.text),
                            "unknown_seconds": (
                                now - unknown_screen_started_at
                                if unknown_screen_started_at is not None
                                else 0
                            ),
                        },
                    )
                    outcome_reason = departure_reason
                    break
                try:
                    prior_digest = previous_digest
                    previous_digest, decision, chosen_action, before_state = _record_policy_state(
                        store,
                        run.run_id,
                        observation,
                        settings,
                        policy,
                        previous_digest,
                        previous_state,
                    )
                    previous_state = before_state
                    if previous_digest != prior_digest:
                        last_progress_at = loop.time()
                    terminal = append_sparse_terminal_events(
                        store,
                        run.run_id,
                        before_state,
                    )
                    if terminal is not None:
                        terminal_outcome, terminal_reward = terminal
                        outcome_reason = "classified_terminal"
                        log.info(
                            "terminal_outcome_recorded",
                            run_id=run.run_id,
                            result=terminal_outcome.result.value,
                            reward=terminal_reward.value,
                        )
                        break
                    if config.screenshot_directory is not None and previous_digest != prior_digest:
                        prepare_private_directory(config.screenshot_directory)
                        screenshot_path = (
                            config.screenshot_directory / f"{run.run_id}-{previous_digest[:12]}.png"
                        )
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        os.chmod(screenshot_path, 0o600)
                    if decision is not None and decision.executable:
                        if chosen_action is None:
                            raise RunnerError("executable decision has no legal action")
                        if in_match_actions >= config.max_in_match_actions:
                            raise RunnerError("policy exceeded the in-match action budget")
                        execution = await execute_action(page, chosen_action)
                        store.append_event(
                            run.run_id,
                            EventKind.ACTION_RESULT,
                            execution,
                        )
                        in_match_actions += 1
                        await page.wait_for_timeout(config.poll_seconds * 1_000)
                        observation = await capture_screen(page)
                        store.append_event(
                            run.run_id,
                            EventKind.OBSERVATION,
                            observation,
                        )
                        post_state: GameState | None = None
                        if observation.kind is ScreenKind.GAME:
                            with suppress(GameStateParseError):
                                post_state = parse_game_state(
                                    observation,
                                    identity=settings.identity,
                                    previous_state=before_state,
                                )
                        transition = build_action_transition(
                            chosen_action.action_id,
                            before_state,
                            post_state,
                        )
                        store.append_event(
                            run.run_id,
                            EventKind.TRANSITION,
                            transition,
                        )
                        if post_state is not None:
                            previous_state = post_state
                            terminal = append_sparse_terminal_events(
                                store,
                                run.run_id,
                                post_state,
                            )
                            if terminal is not None:
                                terminal_outcome, terminal_reward = terminal
                                outcome_reason = "classified_terminal"
                                log.info(
                                    "terminal_outcome_recorded",
                                    run_id=run.run_id,
                                    result=terminal_outcome.result.value,
                                    reward=terminal_reward.value,
                                )
                                break
                        if config.screenshot_directory is not None:
                            post_action_path = (
                                config.screenshot_directory
                                / f"{run.run_id}-after-action-{in_match_actions}.png"
                            )
                            await page.screenshot(path=str(post_action_path), full_page=True)
                            os.chmod(post_action_path, 0o600)
                        log.info(
                            "in_match_action_executed",
                            run_id=run.run_id,
                            action=chosen_action.action_id,
                            action_count=in_match_actions,
                            state_changed=transition.state_changed,
                        )
                        if transition.state_changed is False:
                            outcome_reason = "action_not_accepted"
                            break
                        if transition.state_changed is True:
                            last_progress_at = loop.time()
                        if in_match_actions >= config.max_in_match_actions:
                            outcome_reason = "action_limit"
                            break
                except GameStateParseError as error:
                    log.info("incomplete_game_frame", reason=str(error))
                    parse_error_digest = hashlib.sha256(
                        observation.model_dump_json(exclude={"observed_at"}).encode()
                    ).hexdigest()
                    if parse_error_digest != previous_parse_error_digest:
                        store.append_event(run.run_id, EventKind.OBSERVATION, observation)
                        store.append_event(
                            run.run_id,
                            EventKind.ERROR,
                            {
                                "error_type": type(error).__name__,
                                "reason": str(error),
                                "observation_digest": parse_error_digest,
                            },
                        )
                        if config.screenshot_directory is not None:
                            prepare_private_directory(config.screenshot_directory)
                            parse_error_path = (
                                config.screenshot_directory
                                / f"{run.run_id}-parse-error-{parse_error_digest[:12]}.png"
                            )
                            await page.screenshot(path=str(parse_error_path), full_page=True)
                            os.chmod(parse_error_path, 0o600)
                        previous_parse_error_digest = parse_error_digest
                if loop.time() - last_progress_at >= config.no_progress_seconds:
                    outcome_reason = "no_progress_limit"
                    break
                await page.wait_for_timeout(config.poll_seconds * 1_000)
                observation = await capture_screen(page)
    except asyncio.CancelledError:
        if run is not None:
            store.finish_run(
                run.run_id,
                RunStatus.ABORTED,
                outcome={
                    "reason": "operator_interrupt",
                    "in_match_actions": in_match_actions,
                },
            )
        raise
    except Exception as error:
        if run is not None:
            payload: dict[str, JsonValue] = {
                "error_type": type(error).__name__,
                "reason": str(error).splitlines()[0],
                "phase": "gameplay" if gameplay_started else "setup",
            }
            store.append_event(run.run_id, EventKind.ERROR, payload)
            return store.finish_run(run.run_id, RunStatus.FAILED, outcome=payload)
        raise

    if run is None:  # pragma: no cover - run is created before browser play
        raise RunnerError("runner exited before creating a run")
    if terminal_outcome is not None and terminal_reward is not None:
        return store.finish_run(
            run.run_id,
            RunStatus.COMPLETED,
            outcome={
                "reason": outcome_reason,
                "result": terminal_outcome.result.value,
                "reward": terminal_reward.value,
                "terminal_state_digest": terminal_outcome.terminal_state_digest,
                "in_match_actions": in_match_actions,
            },
        )
    return store.finish_run(
        run.run_id,
        RunStatus.ABORTED,
        outcome={
            "reason": outcome_reason,
            "in_match_actions": in_match_actions,
        },
    )


async def run_training_campaign(
    settings: AppSettings,
    config: TrainingCampaignConfig,
) -> TrainingCampaignSummary:
    """Play official Training computers until the game limit or first gameplay anomaly."""

    run_ids: list[str] = []
    outcomes = {"win": 0, "loss": 0, "draw": 0}
    games_completed = 0
    setup_failures = 0
    consecutive_setup_failures = 0
    while True:
        run = await run_training_observer(settings, config.game)
        run_ids.append(run.run_id)
        outcome_reason = (
            str(run.outcome.get("reason", "unknown")) if run.outcome is not None else "unknown"
        )
        log.info(
            "training_campaign_game_finished",
            run_id=run.run_id,
            status=run.status.value,
            outcome_reason=outcome_reason,
            games_started=len(run_ids),
        )
        run_phase = run.outcome.get("phase") if run.outcome is not None else None
        if run.status is RunStatus.FAILED and run_phase == "setup":
            setup_failures += 1
            consecutive_setup_failures += 1
            if consecutive_setup_failures <= config.max_setup_retries:
                log.warning(
                    "training_campaign_setup_retry",
                    run_id=run.run_id,
                    consecutive_failures=consecutive_setup_failures,
                    max_retries=config.max_setup_retries,
                )
                if config.restart_delay_seconds > 0:
                    await asyncio.sleep(config.restart_delay_seconds)
                continue
        if run.status is not RunStatus.COMPLETED:
            return TrainingCampaignSummary(
                max_games=config.max_games,
                games_started=len(run_ids),
                games_completed=games_completed,
                wins=outcomes["win"],
                losses=outcomes["loss"],
                draws=outcomes["draw"],
                setup_failures=setup_failures,
                run_ids=tuple(run_ids),
                stop_reason=f"{run.status.value}:{outcome_reason}",
                last_run_status=run.status,
            )
        consecutive_setup_failures = 0
        result = run.outcome.get("result") if run.outcome is not None else None
        if not isinstance(result, str) or result not in outcomes:
            raise RunnerError("completed Training run has no classified result")
        outcomes[result] += 1
        games_completed += 1
        if config.max_games != 0 and games_completed >= config.max_games:
            return TrainingCampaignSummary(
                max_games=config.max_games,
                games_started=len(run_ids),
                games_completed=games_completed,
                wins=outcomes["win"],
                losses=outcomes["loss"],
                draws=outcomes["draw"],
                setup_failures=setup_failures,
                run_ids=tuple(run_ids),
                stop_reason="game_limit",
                last_run_status=run.status,
            )
        if config.restart_delay_seconds > 0:
            await asyncio.sleep(config.restart_delay_seconds)
