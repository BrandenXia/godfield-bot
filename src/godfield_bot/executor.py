from datetime import UTC, datetime
from time import monotonic

from playwright.async_api import Page

from godfield_bot.browser.controls import (
    click_action_panel,
    click_chance_panel,
    click_empty_action_panel,
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
    if action.kind is ActionKind.PASS:
        if action.actor_player_name is None or action.control_panel != "left":
            raise ActionExecutionError("pass is missing its verified actor or panel")
        await click_empty_action_panel(page, actor_name=action.actor_player_name)
    elif action.kind is ActionKind.SELECT_ARTIFACT:
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
        if action.target_player_name is None or action.control_panel not in {"left", "right"}:
            raise ActionExecutionError("Forgive is missing its verified identities")
        context_asset_paths = action.context_asset_paths or (
            (action.artifact_asset_path,) if action.artifact_asset_path is not None else ()
        )
        if not context_asset_paths:
            raise ActionExecutionError("Forgive has no verified action context")
        await click_phase_control(
            page,
            text="Forgive",
            panel=action.control_panel,
            context_asset_paths=context_asset_paths,
            target_name=action.target_player_name,
        )
    elif action.kind is ActionKind.CONFIRM_CHANCE:
        if (
            action.artifact_asset_path is None
            or action.actor_player_name is None
            or action.expected_action_display is None
            or action.control_panel != "left"
        ):
            raise ActionExecutionError("chance confirmation is missing its verified identities")
        await click_chance_panel(
            page,
            asset_path=action.artifact_asset_path,
            actor_name=action.actor_player_name,
            action_display=action.expected_action_display,
        )
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
