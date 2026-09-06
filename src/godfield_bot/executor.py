from datetime import UTC, datetime
from time import monotonic

from playwright.async_api import Page

from godfield_bot.browser.controls import (
    click_action_panel,
    click_hand_artifact,
    click_phase_control,
    click_player_target,
)
from godfield_bot.domain.action import (
    ActionExecutionResult,
    ActionKind,
    LegalAction,
)


class ActionExecutionError(RuntimeError):
    """Raised when an action is outside the verified browser executor contract."""


async def execute_action(
    page: Page,
    action: LegalAction,
) -> ActionExecutionResult:
    started = monotonic()
    if action.kind is ActionKind.WAIT:
        raise ActionExecutionError("WAIT is represented by polling, not a browser click")
    if action.kind is ActionKind.SELECT_ARTIFACT:
        if action.artifact_slot is None or action.artifact_asset_path is None:
            raise ActionExecutionError("artifact selection is missing its verified identity")
        await click_hand_artifact(
            page,
            slot=action.artifact_slot,
            asset_path=action.artifact_asset_path,
        )
    elif action.kind is ActionKind.SELECT_TARGET:
        if action.target_player_index is None or action.target_player_name is None:
            raise ActionExecutionError("target selection is missing its verified identity")
        await click_player_target(
            page,
            player_index=action.target_player_index,
            player_name=action.target_player_name,
        )
    elif action.kind is ActionKind.FORGIVE:
        await click_phase_control(page, text="Forgive")
    elif action.kind is ActionKind.CONFIRM:
        if (
            action.artifact_asset_path is None
            or action.target_player_index is None
            or action.target_player_name is None
            or action.control_panel is None
        ):
            raise ActionExecutionError("confirmation is missing its verified identities")
        await click_action_panel(
            page,
            asset_path=action.artifact_asset_path,
            target_name=action.target_player_name,
            panel=action.control_panel,
        )
    else:
        raise ActionExecutionError(f"unsupported executable action: {action.kind}")
    return ActionExecutionResult(
        executed_at=datetime.now(UTC),
        action_id=action.action_id,
        kind=action.kind,
        dispatched=True,
        latency_ms=(monotonic() - started) * 1_000,
    )
