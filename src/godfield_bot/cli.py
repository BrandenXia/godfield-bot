import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import structlog
import typer
from playwright.async_api import Error as PlaywrightError

from godfield_bot import __version__
from godfield_bot.account import (
    AccountStorageError,
    account_status,
    create_account,
    status_json,
)
from godfield_bot.browser.controls import BrowserContractError
from godfield_bot.config import AppSettings
from godfield_bot.observability import configure_logging
from godfield_bot.reference import (
    category_counts,
    refresh_bible,
    write_snapshot,
)

app = typer.Typer(no_args_is_help=True, help="Control and train the ロキ-67 God Field bot.")
data_app = typer.Typer(no_args_is_help=True, help="Refresh versioned public game data.")
account_app = typer.Typer(no_args_is_help=True, help="Manage the persistent ロキ-67 identity.")
app.add_typer(data_app, name="data")
app.add_typer(account_app, name="account")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def root(
    json_logs: Annotated[
        bool, typer.Option("--json-logs", help="Render structured logs as JSON.")
    ] = False,
    log_level: Annotated[str, typer.Option(help="Logging threshold.")] = "INFO",
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    del version
    configure_logging(json_logs=json_logs, level=log_level)


@app.command()
def doctor() -> None:
    """Print safety-relevant configuration without exposing credentials."""

    settings = AppSettings()
    status = account_status(settings)
    status["base_url"] = str(settings.base_url)
    typer.echo(json.dumps(status, ensure_ascii=False, indent=2))


@account_app.command("status")
def show_account_status() -> None:
    """Show identity state without reading or printing browser credentials."""

    typer.echo(status_json(AppSettings()))


@account_app.command("create")
def create_persistent_account(
    confirm_create: Annotated[
        bool,
        typer.Option(
            "--confirm-create",
            help="Confirm creation of the persistent ロキ-67 account on godfield.net.",
        ),
    ] = False,
    headed: Annotated[
        bool,
        typer.Option("--headed/--headless", help="Show the account-creation browser."),
    ] = True,
    timeout_seconds: Annotated[
        float, typer.Option(min=1.0, help="Per-operation browser timeout.")
    ] = 20.0,
) -> None:
    """Create the dedicated account and keep its session in a private browser profile."""

    if not confirm_create:
        typer.echo("Refusing to create external account without --confirm-create", err=True)
        raise typer.Exit(code=2)

    settings = AppSettings()
    try:
        result = asyncio.run(
            create_account(settings, headed=headed, timeout_seconds=timeout_seconds)
        )
    except (AccountStorageError, BrowserContractError, PlaywrightError) as error:
        structlog.get_logger().error(
            "account_creation_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@data_app.command("refresh")
def data_refresh(
    output: Annotated[
        Path | None,
        typer.Option(help="Destination JSON; defaults to today's snapshot directory."),
    ] = None,
    headed: Annotated[
        bool, typer.Option("--headed", help="Show Chromium while extracting the public Bible.")
    ] = False,
    timeout_seconds: Annotated[
        float, typer.Option(min=1.0, help="Per-operation browser timeout.")
    ] = 15.0,
) -> None:
    """Extract all current Bible records through the visible public web UI."""

    logger = structlog.get_logger()
    logger.info("reference_refresh_started", headed=headed)
    try:
        snapshot = asyncio.run(refresh_bible(headed=headed, timeout_seconds=timeout_seconds))
    except (BrowserContractError, PlaywrightError) as error:
        logger.error(
            "reference_refresh_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    destination = output or Path(
        "data", "snapshots", datetime.now(UTC).date().isoformat(), "bible.json"
    )
    write_snapshot(snapshot, destination)
    logger.info(
        "reference_refresh_completed",
        output=str(destination),
        client_sha256=snapshot.client.sha256,
        total=snapshot.total_artifacts,
        categories=category_counts(snapshot),
    )
    typer.echo(destination)
