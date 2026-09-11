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


def test_reflected_forgive_dispatches_to_left_panel(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_phase_control(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_phase_control", fake_click_phase_control)
    page = object()
    action = LegalAction(
        action_id="forgive:reflected",
        kind=ActionKind.FORGIVE,
        label="Forgive the reflected outgoing attack",
        artifact_asset_path="/images/items/weapons/angel-sword.webp",
        target_player_index=1,
        target_player_name="CPU",
        control_panel="left",
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {
        "page": page,
        "text": "Forgive",
        "panel": "left",
        "context_asset_paths": ("/images/items/weapons/angel-sword.webp",),
        "target_name": "CPU",
    }


def test_pass_dispatches_through_verified_empty_pray_panel(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_empty_action_panel(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_empty_action_panel", fake_click_empty_action_panel)
    page = object()
    action = LegalAction(
        action_id="pass",
        kind=ActionKind.PASS,
        label="Confirm an empty Pray action",
        actor_player_name="ロキ-67",
        control_panel="left",
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {"page": page, "actor_name": "ロキ-67"}


def test_exchange_dispatches_through_verified_trade_control(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_exchange_command(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_exchange_command", fake_click_exchange_command)
    page = object()
    action = LegalAction(
        action_id="exchange",
        kind=ActionKind.EXCHANGE,
        label="Exchange a blocked hand",
        artifact_asset_path="/images/items/trade/exchange.webp",
        actor_player_name="ロキ-67",
        expected_action_display="Pray",
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {
        "page": page,
        "asset_path": "/images/items/trade/exchange.webp",
        "actor_name": "ロキ-67",
        "action_display": "Pray",
    }


def test_exchange_confirmation_dispatches_through_verified_action_panel(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_exchange_panel(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_exchange_panel", fake_click_exchange_panel)
    page = object()
    action = LegalAction(
        action_id="confirm:exchange",
        kind=ActionKind.CONFIRM_EXCHANGE,
        label="Confirm Exchange",
        artifact_asset_path="/images/items/trade/exchange.webp",
        actor_player_name="ロキ-67",
        control_panel="left",
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {
        "page": page,
        "asset_path": "/images/items/trade/exchange.webp",
        "actor_name": "ロキ-67",
    }


def test_chance_attack_dispatches_through_verified_untargeted_panel(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_chance_panel(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_chance_panel", fake_click_chance_panel)
    page = object()
    action = LegalAction(
        action_id="confirm:chance:oversize-snowball",
        kind=ActionKind.CONFIRM_CHANCE,
        label="Resolve the selected chance attack oversize-snowball",
        artifact_asset_path="/images/items/weapons/oversize-snowball.webp",
        actor_player_name="ロキ-67",
        expected_action_display="50%ATK5",
        control_panel="left",
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {
        "page": page,
        "asset_path": "/images/items/weapons/oversize-snowball.webp",
        "actor_name": "ロキ-67",
        "action_display": "50%ATK5",
    }


def test_utility_dispatches_through_verified_untargeted_panel(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_click_utility_panel(page: object, **kwargs: object) -> None:
        captured["page"] = page
        captured.update(kwargs)

    monkeypatch.setattr(executor, "click_utility_panel", fake_click_utility_panel)
    page = object()
    action = LegalAction(
        action_id="confirm:utility:smile-dew:HP+5",
        kind=ActionKind.CONFIRM_UTILITY,
        label="Confirm the selected HP+5 utility smile-dew",
        artifact_asset_path="/images/items/sundries/smile-dew.webp",
        actor_player_name="ロキ-67",
        expected_action_display="HP+5",
        control_panel="left",
    )

    result = asyncio.run(executor.execute_action(page, action))  # type: ignore[arg-type]

    assert result.dispatched is True
    assert captured == {
        "page": page,
        "asset_path": "/images/items/sundries/smile-dew.webp",
        "actor_name": "ロキ-67",
        "effect_display": "HP+5",
    }
