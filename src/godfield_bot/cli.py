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
    account_status,
    create_account,
    status_json,
)
from godfield_bot.browser.controls import BrowserContractError
from godfield_bot.browser.profile import ProfileStorageError
from godfield_bot.config import AppSettings
from godfield_bot.domain.observation import ScreenObservation
from godfield_bot.game_state import GameStateParseError, parse_game_state
from godfield_bot.observability import configure_logging
from godfield_bot.observer import (
    ObservationError,
    ObservationTarget,
    observe_account_screen,
)
from godfield_bot.probe import record_observation_probe
from godfield_bot.reference import (
    category_counts,
    plain_attack_weapon_values,
    plain_defense_armor_values,
    refresh_bible,
    write_snapshot,
)
from godfield_bot.run_store import RunStore, RunStoreError
from godfield_bot.runner import (
    RunnerError,
    RunnerPolicyName,
    TrainingRunConfig,
    run_training_observer,
)

app = typer.Typer(no_args_is_help=True, help="Control and train the ロキ-67 God Field bot.")
data_app = typer.Typer(no_args_is_help=True, help="Refresh versioned public game data.")
account_app = typer.Typer(no_args_is_help=True, help="Manage the persistent ロキ-67 identity.")
state_app = typer.Typer(no_args_is_help=True, help="Normalize saved browser observations.")
runs_app = typer.Typer(no_args_is_help=True, help="Inspect the local trajectory store.")
models_app = typer.Typer(no_args_is_help=True, help="Manage local neural policy candidates.")
app.add_typer(data_app, name="data")
app.add_typer(account_app, name="account")
app.add_typer(state_app, name="state")
app.add_typer(runs_app, name="runs")
app.add_typer(models_app, name="models")


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
    except (ProfileStorageError, BrowserContractError, PlaywrightError) as error:
        structlog.get_logger().error(
            "account_creation_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def observe(
    screen: Annotated[
        ObservationTarget,
        typer.Option(help="Screen to inspect; targets are restricted to Training."),
    ] = ObservationTarget.MENU,
    output: Annotated[
        Path | None,
        typer.Option(help="Optional destination for the structured screen observation."),
    ] = None,
    headed: Annotated[
        bool, typer.Option("--headed", help="Show Chromium while observing the account.")
    ] = False,
    screenshot: Annotated[
        Path | None,
        typer.Option(help="Optional ignored screenshot destination for visual diagnostics."),
    ] = None,
    settle_seconds: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=30.0,
            help="Time to let the selected screen advance before capture.",
        ),
    ] = 2.0,
    timeout_seconds: Annotated[
        float, typer.Option(min=1.0, help="Per-operation browser timeout.")
    ] = 20.0,
) -> None:
    """Enter the named session and inspect a bounded Training state."""

    settings = AppSettings()
    try:
        observation = asyncio.run(
            observe_account_screen(
                settings,
                target=screen,
                headed=headed,
                screenshot=screenshot,
                settle_seconds=settle_seconds,
                timeout_seconds=timeout_seconds,
            )
        )
    except (
        ObservationError,
        ProfileStorageError,
        BrowserContractError,
        PlaywrightError,
    ) as error:
        structlog.get_logger().error(
            "screen_observation_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None

    serialized = observation.model_dump_json(indent=2)
    if output is None:
        typer.echo(serialized)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n", encoding="utf-8")
    typer.echo(output)


@app.command("run")
def run_bot(
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-06", "bible.json"),
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    headed: Annotated[
        bool,
        typer.Option("--headed/--headless", help="Show the bounded Training runner."),
    ] = True,
    max_seconds: Annotated[
        float,
        typer.Option(min=10.0, max=3600.0, help="Maximum gameplay observation time."),
    ] = 90.0,
    room_timeout_seconds: Annotated[
        float,
        typer.Option(min=5.0, max=300.0, help="Maximum wait for a Training computer."),
    ] = 60.0,
    poll_seconds: Annotated[
        float,
        typer.Option(min=0.25, max=10.0, help="Seconds between stable observations."),
    ] = 2.0,
    screenshot_directory: Annotated[
        Path | None,
        typer.Option(help="Owner-only ignored screenshots for changed game states."),
    ] = None,
    policy: Annotated[
        RunnerPolicyName,
        typer.Option(help="Policy; heuristic-v0 uses only verified plain-card Training actions."),
    ] = RunnerPolicyName.SAFE_OBSERVER,
    max_actions: Annotated[
        int,
        typer.Option(min=0, max=100, help="Hard in-match browser-click budget."),
    ] = 0,
) -> None:
    """Run one bounded Training session under a hard in-match action budget."""

    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.domain.run import RunStatus

    try:
        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        result = asyncio.run(
            run_training_observer(
                AppSettings(),
                TrainingRunConfig(
                    database=database,
                    expected_client_sha256=bible.client.sha256,
                    headed=headed,
                    max_seconds=max_seconds,
                    room_timeout_seconds=room_timeout_seconds,
                    poll_seconds=poll_seconds,
                    screenshot_directory=screenshot_directory,
                    policy=policy,
                    max_in_match_actions=max_actions,
                    plain_weapon_attacks=plain_attack_weapon_values(bible),
                    plain_armor_defenses=plain_defense_armor_values(bible),
                ),
            )
        )
    except KeyboardInterrupt:
        typer.echo("Training run interrupted by operator", err=True)
        raise typer.Exit(code=130) from None
    except (OSError, ValueError, RunnerError, ProfileStorageError, PlaywrightError) as error:
        structlog.get_logger().error(
            "training_run_failed_before_recording",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))
    if result.status is RunStatus.FAILED:
        raise typer.Exit(code=1)


@state_app.command("parse")
def state_parse(
    observation_file: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    output: Annotated[
        Path | None,
        typer.Option(help="Optional destination for the normalized GameState."),
    ] = None,
) -> None:
    """Parse a saved gameplay observation into a typed, policy-facing state."""

    try:
        observation = ScreenObservation.model_validate_json(
            observation_file.read_text(encoding="utf-8")
        )
        state = parse_game_state(observation, identity=AppSettings().identity)
    except (OSError, ValueError, GameStateParseError) as error:
        structlog.get_logger().error(
            "game_state_parse_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None

    serialized = state.model_dump_json(indent=2)
    if output is None:
        typer.echo(serialized)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n", encoding="utf-8")
    typer.echo(output)


@runs_app.command("init")
def runs_init(
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
) -> None:
    """Initialize the versioned local run and event store."""

    try:
        RunStore(database).initialize()
    except RunStoreError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(database)


@runs_app.command("list")
def runs_list(
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
) -> None:
    """List recent runs without including event payloads."""

    try:
        records = RunStore(database).recent_runs(limit=limit)
    except RunStoreError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            [record.model_dump(mode="json") for record in records],
            ensure_ascii=False,
            indent=2,
        )
    )


@runs_app.command("events")
def runs_events(
    run_id: Annotated[str, typer.Argument()],
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    include_payload: Annotated[
        bool,
        typer.Option("--include-payload", help="Include full structured event payloads."),
    ] = False,
) -> None:
    """Inspect ordered events from one recorded run."""

    store = RunStore(database)
    if store.get_run(run_id) is None:
        typer.echo("unknown run", err=True)
        raise typer.Exit(code=1)
    events = store.events(run_id)
    rows = [
        event.model_dump(mode="json")
        if include_payload
        else {
            "sequence": event.sequence,
            "occurred_at": event.occurred_at.isoformat(),
            "kind": event.kind.value,
        }
        for event in events
    ]
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))


@runs_app.command("record-probe")
def runs_record_probe(
    observation_file: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    client_sha256: Annotated[
        str,
        typer.Option(help="Observed web-client SHA-256 associated with this screen."),
    ],
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
) -> None:
    """Record one saved state through the non-executing baseline policy."""

    try:
        observation = ScreenObservation.model_validate_json(
            observation_file.read_text(encoding="utf-8")
        )
        run = record_observation_probe(
            RunStore(database),
            observation,
            identity=AppSettings().identity,
            client_sha256=client_sha256,
        )
    except (OSError, ValueError, GameStateParseError, RunStoreError) as error:
        structlog.get_logger().error(
            "observation_probe_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(run.model_dump_json(indent=2))


@models_app.command("init")
def models_init(
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-06", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for model artifacts."),
    ] = Path("models"),
    seed: Annotated[int, typer.Option()] = 67,
) -> None:
    """Initialize an untrained recurrent policy/value model; never promote it."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import initialize_model

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = initialize_model(
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
            seed=seed,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_initialization_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


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
