import asyncio
from typing import Any

from godfield_bot import executor
from godfield_bot.domain.action import ActionKind, LegalAction


def test_forgive_dispatches_with_all_verified_context_assets(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_phase_control(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_phase_control", fake_click_phase_control)
    page = object()
    action = LegalAction(
        action_id="forgive",
        kind=ActionKind.FORGIVE,
        label="Forgive the incoming targeted interaction",
        target_player_index=1,
        target_player_name="ロキ-67",
        control_panel="right",
        context_asset_paths=(
            "/images/items/trade/sell.webp",
            "/images/items/armor/dreaming-hat.webp",
        ),
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {
        "page": page,
        "text": "Forgive",
        "panel": "right",
        "context_asset_paths": action.context_asset_paths,
        "target_name": "ロキ-67",
    }
