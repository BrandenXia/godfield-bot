import asyncio
import os
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
from godfield_bot.domain.action import LegalAction, PolicyDecision
from godfield_bot.domain.observation import ScreenKind, ScreenObservation
from godfield_bot.domain.run import EventKind, RunMode, RunRecord, RunSpec, RunStatus
from godfield_bot.executor import execute_action
from godfield_bot.game_state import GameStateParseError, parse_game_state
from godfield_bot.legal_actions import game_state_digest, verified_browser_actions
from godfield_bot.observer import capture_screen
from godfield_bot.policy import HeuristicV0Policy, Policy, SafeObserverPolicy
from godfield_bot.reference import fingerprint_client
from godfield_bot.run_store import RunStore

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
    render_settle_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    screenshot_directory: Path | None = None
    policy: RunnerPolicyName = RunnerPolicyName.SAFE_OBSERVER
    max_in_match_actions: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def executable_policy_has_action_budget(self) -> "TrainingRunConfig":
        if self.policy is RunnerPolicyName.HEURISTIC_V0 and self.max_in_match_actions < 1:
            raise ValueError("heuristic-v0 requires a positive in-match action budget")
        return self


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
        await page.wait_for_timeout(1_000)
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
) -> tuple[str, PolicyDecision | None, LegalAction | None]:
    state = parse_game_state(observation, identity=settings.identity)
    digest = game_state_digest(state)
    if digest == previous_digest:
        return digest, None, None
    legal_actions = verified_browser_actions(state, observation)
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
    return digest, decision, chosen_actions[0]


def _policy_from_name(name: RunnerPolicyName) -> Policy:
    if name is RunnerPolicyName.SAFE_OBSERVER:
        return SafeObserverPolicy()
    if name is RunnerPolicyName.HEURISTIC_V0:
        return HeuristicV0Policy()
    raise RunnerError(f"unsupported policy: {name}")


async def run_training_observer(
    settings: AppSettings,
    config: TrainingRunConfig,
) -> RunRecord:
    if settings.public_duel_enabled:
        raise RunnerError("safe observer runner requires public Duel to remain disabled")

    policy = _policy_from_name(config.policy)
    store = RunStore(config.database)
    started = datetime.now(UTC)
    run: RunRecord | None = None
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
            previous_digest: str | None = None
            in_match_actions = 0
            outcome_reason = "wall_clock_limit"
            deadline = asyncio.get_running_loop().time() + config.max_seconds
            while asyncio.get_running_loop().time() < deadline:
                if observation.kind is not ScreenKind.GAME:
                    raise RunnerError(f"Training game left the gameplay screen: {observation.kind}")
                try:
                    prior_digest = previous_digest
                    previous_digest, decision, chosen_action = _record_policy_state(
                        store,
                        run.run_id,
                        observation,
                        settings,
                        policy,
                        previous_digest,
                    )
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
                        )
                        outcome_reason = "action_limit"
                        if in_match_actions >= config.max_in_match_actions:
                            break
                except GameStateParseError as error:
                    log.info("incomplete_game_frame", reason=str(error))
                await page.wait_for_timeout(config.poll_seconds * 1_000)
                observation = await capture_screen(page)
    except asyncio.CancelledError:
        if run is not None:
            store.finish_run(
                run.run_id,
                RunStatus.ABORTED,
                outcome={"reason": "operator_interrupt", "in_match_actions": 0},
            )
        raise
    except Exception as error:
        if run is not None:
            payload: dict[str, JsonValue] = {
                "error_type": type(error).__name__,
                "reason": str(error).splitlines()[0],
            }
            store.append_event(run.run_id, EventKind.ERROR, payload)
            return store.finish_run(run.run_id, RunStatus.FAILED, outcome=payload)
        raise

    if run is None:  # pragma: no cover - run is created before browser play
        raise RunnerError("runner exited before creating a run")
    return store.finish_run(
        run.run_id,
        RunStatus.ABORTED,
        outcome={
            "reason": outcome_reason,
            "in_match_actions": in_match_actions,
        },
    )
