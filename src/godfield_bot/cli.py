import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

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
from godfield_bot.outcome_replay import (
    OutcomeReplayExportError,
    export_outcome_replay_jsonl,
)
from godfield_bot.probe import record_observation_probe
from godfield_bot.reference import (
    category_counts,
    diff_bible_snapshots,
    plain_defense_armor_values,
    plain_hp_utility_sundries,
    plain_mp_utility_sundries,
    refresh_bible,
    verified_attack_miracle_cards,
    verified_browser_weapon_attacks,
    write_snapshot,
)
from godfield_bot.replay import ReplayExportError, export_replay_jsonl
from godfield_bot.run_store import RunStore, RunStoreError
from godfield_bot.runner import (
    RunnerError,
    RunnerPolicyName,
    TrainingCampaignConfig,
    TrainingRunConfig,
    run_training_campaign,
    run_training_observer,
)

app = typer.Typer(no_args_is_help=True, help="Control and train the ロキ-67 God Field bot.")
data_app = typer.Typer(no_args_is_help=True, help="Refresh versioned public game data.")
account_app = typer.Typer(no_args_is_help=True, help="Manage the persistent ロキ-67 identity.")
api_app = typer.Typer(no_args_is_help=True, help="Observe operator-owned private API games.")
state_app = typer.Typer(no_args_is_help=True, help="Normalize saved browser observations.")
runs_app = typer.Typer(no_args_is_help=True, help="Inspect the local trajectory store.")
models_app = typer.Typer(no_args_is_help=True, help="Manage local neural policy candidates.")
simulation_app = typer.Typer(no_args_is_help=True, help="Run local batched curriculum games.")
app.add_typer(data_app, name="data")
app.add_typer(account_app, name="account")
app.add_typer(api_app, name="api")
app.add_typer(state_app, name="state")
app.add_typer(runs_app, name="runs")
app.add_typer(models_app, name="models")
app.add_typer(simulation_app, name="simulation")


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


@account_app.command("enable-api")
def enable_protocol_api(
    confirm_enable: Annotated[
        bool,
        typer.Option(
            "--confirm-enable",
            help="Copy the existing ロキ-67 session into its owner-only API credential store.",
        ),
    ] = False,
    headed: Annotated[
        bool,
        typer.Option("--headed/--headless", help="Show the credential migration browser."),
    ] = True,
    timeout_seconds: Annotated[
        float, typer.Option(min=1.0, help="Per-operation browser timeout.")
    ] = 20.0,
) -> None:
    """Enable pygodfield without creating or changing the persistent identity."""

    if not confirm_enable:
        typer.echo("Refusing to access stored credentials without --confirm-enable", err=True)
        raise typer.Exit(code=2)
    from godfield_bot.api_account import ApiAccountError, enable_api_account

    try:
        result = asyncio.run(
            enable_api_account(
                AppSettings(),
                headed=headed,
                timeout_seconds=timeout_seconds,
            )
        )
    except (
        ApiAccountError,
        ProfileStorageError,
        BrowserContractError,
        PlaywrightError,
    ) as error:
        structlog.get_logger().error(
            "api_account_enable_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@api_app.command("observe-private")
def observe_private_api_game(
    room_id: Annotated[
        str | None,
        typer.Option(help="Optional internal private room ID; omit to use keyed matchmaking."),
    ] = None,
    password_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Optional owner-only file containing the private-room matchmaking key.",
        ),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option(
            "--password-stdin",
            help="Read the private-room matchmaking key without echoing it.",
        ),
    ] = False,
    catalog_snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-09", "api-catalog-en.json"),
    database: Annotated[
        Path,
        typer.Option(help="Local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    max_seconds: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=3600.0,
            help="Maximum room observation time; 0 disables the wall-clock limit.",
        ),
    ] = 90.0,
    poll_seconds: Annotated[
        float,
        typer.Option(min=0.25, max=10.0, help="Seconds between room reads."),
    ] = 1.0,
    no_progress_seconds: Annotated[
        float,
        typer.Option(
            min=10.0,
            max=600.0,
            help="Stop after this many seconds without a normalized state change.",
        ),
    ] = 60.0,
    request_timeout_seconds: Annotated[
        float,
        typer.Option(min=1.0, max=120.0, help="Per-request API timeout."),
    ] = 20.0,
    state_read_retries: Annotated[
        int,
        typer.Option(
            min=0,
            max=20,
            help="Transient room-state read retries before a finite session stops.",
        ),
    ] = 5,
    state_read_retry_seconds: Annotated[
        float,
        typer.Option(
            min=0.1,
            max=30.0,
            help="Initial transient room-state read retry delay.",
        ),
    ] = 1.0,
) -> None:
    """Join an existing private room and record state without playing cards."""

    from godfield_bot.api_runtime import (
        ApiRuntimeError,
        PrivateApiRunConfig,
        run_private_api_observer,
    )

    try:
        if password_stdin and password_file is not None:
            raise ApiRuntimeError("provide the private-room key through only one input")
        if room_id is None and not password_stdin and password_file is None:
            raise ApiRuntimeError("keyed matchmaking requires --password-stdin or --password-file")
        room_password: str | None = None
        if password_stdin:
            from getpass import getpass

            room_password = getpass("Private room key: ")
        result = run_private_api_observer(
            AppSettings(),
            PrivateApiRunConfig(
                database=database,
                catalog_snapshot=catalog_snapshot,
                room_id=room_id,
                password_file=password_file,
                enter_match=False,
                max_seconds=max_seconds,
                poll_seconds=poll_seconds,
                no_progress_seconds=no_progress_seconds,
                request_timeout_seconds=request_timeout_seconds,
                state_read_retries=state_read_retries,
                state_read_retry_seconds=state_read_retry_seconds,
            ),
            room_password=room_password,
        )
    except (ApiRuntimeError, RunStoreError, ValueError) as error:
        structlog.get_logger().error(
            "api_private_observer_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@api_app.command("play-private")
def play_private_api_game(
    confirm_play: Annotated[
        bool,
        typer.Option(
            "--confirm-play",
            help="Confirm entry and tactical card play in an operator-owned private room.",
        ),
    ] = False,
    room_id: Annotated[
        str | None,
        typer.Option(help="Optional internal private room ID; omit to use keyed matchmaking."),
    ] = None,
    password_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Optional owner-only file containing the private-room matchmaking key.",
        ),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option(
            "--password-stdin",
            help="Read the private-room matchmaking key without echoing it.",
        ),
    ] = False,
    catalog_snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-09", "api-catalog-en.json"),
    shadow_model: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            readable=True,
            help=(
                "Optional schema-v4 combo or schema-v5 resource candidate to score live "
                "states in shadow mode; "
                "the tactical heuristic still submits every command."
            ),
        ),
    ] = None,
    bible_snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    database: Annotated[
        Path,
        typer.Option(help="Local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    team: Annotated[
        int,
        typer.Option(
            "--team",
            min=0,
            max=4,
            help="Lobby team: 0 is solo/free-for-all; 1-4 are allied teams A-D.",
        ),
    ] = 0,
    max_seconds: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=3600.0,
            help="Maximum private-session time; 0 disables the wall-clock limit.",
        ),
    ] = 3600.0,
    poll_seconds: Annotated[
        float,
        typer.Option(min=0.25, max=10.0, help="Seconds between room reads."),
    ] = 1.0,
    no_progress_seconds: Annotated[
        float,
        typer.Option(
            min=10.0,
            max=600.0,
            help=(
                "Stop after this many seconds without normalized progress; unlimited "
                "sessions rejoin an active stalled match."
            ),
        ),
    ] = 180.0,
    max_actions: Annotated[
        int,
        typer.Option(min=1, max=1000, help="Hard in-match API action budget."),
    ] = 500,
    request_timeout_seconds: Annotated[
        float,
        typer.Option(min=1.0, max=120.0, help="Per-request API timeout."),
    ] = 20.0,
    state_read_retries: Annotated[
        int,
        typer.Option(
            min=0,
            max=20,
            help="Transient room-state read retries before a finite session stops.",
        ),
    ] = 5,
    state_read_retry_seconds: Annotated[
        float,
        typer.Option(
            min=0.1,
            max=30.0,
            help="Initial transient room-state read retry delay.",
        ),
    ] = 1.0,
    command_retries: Annotated[
        int,
        typer.Option(
            min=0,
            max=5,
            help="Confirmed command-rejection retries after unchanged state reads.",
        ),
    ] = 2,
    command_reconcile_seconds: Annotated[
        float,
        typer.Option(
            min=1.0,
            max=300.0,
            help="Wait for state evidence after an ambiguous command response.",
        ),
    ] = 30.0,
) -> None:
    """Enter private games with tactical play and optional neural shadow scoring."""

    if not confirm_play:
        typer.echo("Refusing private game entry without --confirm-play", err=True)
        raise typer.Exit(code=2)
    from godfield_bot.api_runtime import (
        ApiPolicyName,
        ApiRuntimeError,
        PrivateApiRunConfig,
        run_private_api_observer,
    )

    try:
        if password_stdin and password_file is not None:
            raise ApiRuntimeError("provide the private-room key through only one input")
        if room_id is None and not password_stdin and password_file is None:
            raise ApiRuntimeError("keyed matchmaking requires --password-stdin or --password-file")
        room_password: str | None = None
        if password_stdin:
            from getpass import getpass

            room_password = getpass("Private room key: ")
        result = run_private_api_observer(
            AppSettings(),
            PrivateApiRunConfig(
                database=database,
                catalog_snapshot=catalog_snapshot,
                room_id=room_id,
                password_file=password_file,
                enter_match=True,
                entry_team=team,
                policy=(
                    ApiPolicyName.NEURAL_SHADOW
                    if shadow_model is not None
                    else ApiPolicyName.TACTICAL_HEURISTIC
                ),
                model_directory=shadow_model,
                bible_snapshot=bible_snapshot,
                max_in_match_actions=max_actions,
                max_seconds=max_seconds,
                poll_seconds=poll_seconds,
                no_progress_seconds=no_progress_seconds,
                request_timeout_seconds=request_timeout_seconds,
                state_read_retries=state_read_retries,
                state_read_retry_seconds=state_read_retry_seconds,
                command_retries=command_retries,
                command_reconcile_seconds=command_reconcile_seconds,
            ),
            room_password=room_password,
        )
    except (ApiRuntimeError, RunStoreError, ValueError) as error:
        structlog.get_logger().error(
            "api_private_play_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@api_app.command("verify")
def verify_protocol_api() -> None:
    """Verify the stored identity with one authenticated, read-only API request."""

    from godfield_bot.api_account import ApiAccountError, verify_api_connection

    try:
        status = verify_api_connection(AppSettings())
    except ApiAccountError as error:
        structlog.get_logger().error(
            "api_connection_verification_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(status.model_dump_json(indent=2))


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
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
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
    no_progress_seconds: Annotated[
        float,
        typer.Option(
            min=10.0,
            max=600.0,
            help="Stop after this many seconds without a normalized state change.",
        ),
    ] = 60.0,
    unknown_screen_grace_seconds: Annotated[
        float,
        typer.Option(
            min=1.0,
            max=60.0,
            help="Grace period for a transient unknown gameplay render.",
        ),
    ] = 15.0,
    screenshot_directory: Annotated[
        Path | None,
        typer.Option(help="Owner-only ignored screenshots for changed game states."),
    ] = None,
    policy: Annotated[
        RunnerPolicyName,
        typer.Option(help="Policy; heuristic-v0 uses only Bible-audited Training actions."),
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
                    no_progress_seconds=no_progress_seconds,
                    unknown_screen_grace_seconds=unknown_screen_grace_seconds,
                    screenshot_directory=screenshot_directory,
                    policy=policy,
                    max_in_match_actions=max_actions,
                    verified_weapon_attacks=verified_browser_weapon_attacks(bible),
                    verified_miracle_attacks=verified_attack_miracle_cards(bible),
                    plain_hp_utilities=plain_hp_utility_sundries(bible),
                    plain_mp_utilities=plain_mp_utility_sundries(bible),
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


@app.command("play-training")
def play_official_training_computers(
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    database: Annotated[
        Path,
        typer.Option(help="Local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    headed: Annotated[
        bool,
        typer.Option("--headed/--headless", help="Show or hide the official browser client."),
    ] = False,
    max_games: Annotated[
        int,
        typer.Option(
            min=0,
            max=100_000,
            help="Completed official-CPU games; 0 continues until an anomaly or interruption.",
        ),
    ] = 0,
    max_seconds: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=3600.0,
            help="Maximum time for each Training game; 0 disables this limit.",
        ),
    ] = 3600.0,
    room_timeout_seconds: Annotated[
        float,
        typer.Option(min=5.0, max=300.0, help="Maximum wait for a Training computer."),
    ] = 60.0,
    poll_seconds: Annotated[
        float,
        typer.Option(min=0.25, max=10.0, help="Seconds between stable observations."),
    ] = 2.0,
    no_progress_seconds: Annotated[
        float,
        typer.Option(
            min=10.0,
            max=600.0,
            help="Stop the campaign on this many seconds without normalized progress.",
        ),
    ] = 60.0,
    unknown_screen_grace_seconds: Annotated[
        float,
        typer.Option(
            min=1.0,
            max=60.0,
            help="Grace period for a transient unknown gameplay render.",
        ),
    ] = 15.0,
    restart_delay_seconds: Annotated[
        float,
        typer.Option(min=0.0, max=60.0, help="Delay between completed Training games."),
    ] = 2.0,
    max_setup_retries: Annotated[
        int,
        typer.Option(
            min=0,
            max=100,
            help="Consecutive pre-game failures tolerated before stopping.",
        ),
    ] = 3,
    max_gameplay_retries: Annotated[
        int,
        typer.Option(
            min=0,
            max=100,
            help="Consecutive frozen games tolerated before stopping.",
        ),
    ] = 3,
    screenshot_directory: Annotated[
        Path | None,
        typer.Option(help="Optional owner-only screenshots for changed game states."),
    ] = None,
    max_actions: Annotated[
        int,
        typer.Option(min=1, max=100, help="Hard browser-click budget for each game."),
    ] = 100,
    neural_model: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            readable=True,
            help="Candidate directory allowed to choose reviewed Training actions.",
        ),
    ] = None,
    neural_seed: Annotated[
        int,
        typer.Option(
            min=0,
            max=2**63 - 1,
            help="Reproducible first action-sampling seed; each game increments it.",
        ),
    ] = 67,
    confirm_neural_control: Annotated[
        bool,
        typer.Option(
            "--confirm-neural-control",
            help="Confirm that the selected candidate may control official Training games.",
        ),
    ] = False,
) -> None:
    """Continuously play God Field's official browser-local Training computer."""

    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.domain.run import RunStatus

    try:
        if neural_model is not None and not confirm_neural_control:
            raise RunnerError("neural Training control requires --confirm-neural-control")
        if neural_model is None and confirm_neural_control:
            raise RunnerError("--confirm-neural-control requires --neural-model")
        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        policy = (
            RunnerPolicyName.OFFICIAL_TRAINING_NEURAL
            if neural_model is not None
            else RunnerPolicyName.HEURISTIC_V0
        )
        summary = asyncio.run(
            run_training_campaign(
                AppSettings(),
                TrainingCampaignConfig(
                    game=TrainingRunConfig(
                        database=database,
                        expected_client_sha256=bible.client.sha256,
                        headed=headed,
                        max_seconds=max_seconds,
                        room_timeout_seconds=room_timeout_seconds,
                        poll_seconds=poll_seconds,
                        no_progress_seconds=no_progress_seconds,
                        unknown_screen_grace_seconds=unknown_screen_grace_seconds,
                        screenshot_directory=screenshot_directory,
                        policy=policy,
                        model_directory=neural_model,
                        bible_snapshot=snapshot if neural_model is not None else None,
                        neural_sampling_seed=neural_seed,
                        max_in_match_actions=max_actions,
                        verified_weapon_attacks=verified_browser_weapon_attacks(bible),
                        verified_miracle_attacks=verified_attack_miracle_cards(bible),
                        plain_hp_utilities=plain_hp_utility_sundries(bible),
                        plain_mp_utilities=plain_mp_utility_sundries(bible),
                        plain_armor_defenses=plain_defense_armor_values(bible),
                    ),
                    max_games=max_games,
                    restart_delay_seconds=restart_delay_seconds,
                    max_setup_retries=max_setup_retries,
                    max_gameplay_retries=max_gameplay_retries,
                ),
            )
        )
    except KeyboardInterrupt:
        typer.echo("Official Training campaign interrupted by operator", err=True)
        raise typer.Exit(code=130) from None
    except (
        ImportError,
        OSError,
        ValueError,
        RunnerError,
        ProfileStorageError,
        PlaywrightError,
    ) as error:
        structlog.get_logger().error(
            "training_campaign_failed_before_summary",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(summary.model_dump_json(indent=2))
    if summary.stop_reason != "game_limit":
        raise typer.Exit(code=1 if summary.last_run_status is RunStatus.FAILED else 2)


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


@runs_app.command("export-replay")
def runs_export_replay(
    destination: Annotated[
        Path,
        typer.Argument(dir_okay=False, help="Destination JSONL dataset."),
    ],
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
) -> None:
    """Export only fully verified, state-changing browser transitions."""

    try:
        summary = export_replay_jsonl(RunStore(database), destination)
    except (OSError, RunStoreError, ReplayExportError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(summary.model_dump_json(indent=2))


@runs_app.command("export-outcomes")
def runs_export_outcomes(
    destination: Annotated[
        Path,
        typer.Argument(dir_okay=False, help="Destination terminal-labeled JSONL dataset."),
    ],
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    model_id: Annotated[
        str | None,
        typer.Option(help="Include only runs controlled by this immutable model ID."),
    ] = None,
) -> None:
    """Export complete episodes with verified sparse terminal rewards."""

    try:
        summary = export_outcome_replay_jsonl(
            RunStore(database),
            destination,
            model_id=model_id,
        )
    except (OSError, RunStoreError, OutcomeReplayExportError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(summary.model_dump_json(indent=2))


@models_app.command("init")
def models_init(
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
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


@models_app.command("migrate-element-features")
def models_migrate_element_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Expand a six-global checkpoint into the elemental observation-value schema."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_element_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_element_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_element_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-combo-features")
def models_migrate_combo_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Version an elemental checkpoint for sequential combo observations."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_combo_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_combo_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_combo_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-resource-features")
def models_migrate_resource_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Version a combo checkpoint for stateful resources and miracle costs."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_resource_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_resource_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_resource_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-stochastic-resource-features")
def models_migrate_stochastic_resource_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Expand schema v5 with the pending absorption-effect input."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_stochastic_resource_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_stochastic_resource_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_stochastic_resource_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("train-replay")
def models_train_replay(
    base_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    replay: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the new candidate."),
    ] = Path("models"),
    epochs: Annotated[
        int,
        typer.Option(min=1, max=10_000, help="Offline passes over replay trajectories."),
    ] = 20,
    learning_rate: Annotated[
        float,
        typer.Option(min=1e-8, max=1.0, help="Behavior-cloning learning rate."),
    ] = 1e-3,
    seed: Annotated[int, typer.Option()] = 67,
) -> None:
    """Create a non-deployable imitation candidate from verified replay."""

    try:
        from godfield_bot.imitation import (
            ImitationTrainingConfig,
            train_imitation_candidate,
        )
        from godfield_bot.replay import ReplayDatasetError
        from godfield_bot.training import TrainingError

        manifest = train_imitation_candidate(
            base_model_directory=base_model,
            model_root=root_directory,
            replay_path=replay,
            snapshot_path=snapshot,
            config=ImitationTrainingConfig(
                epochs=epochs,
                learning_rate=learning_rate,
                seed=seed,
            ),
        )
    except (ImportError, OSError, ValueError, ReplayDatasetError, TrainingError) as error:
        structlog.get_logger().error(
            "replay_training_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("train-outcomes")
def models_train_outcomes(
    base_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    outcome_replay: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the new candidate."),
    ] = Path("models"),
    epochs: Annotated[
        int,
        typer.Option(min=1, max=10_000, help="Offline passes over terminal episodes."),
    ] = 4,
    learning_rate: Annotated[
        float,
        typer.Option(min=1e-8, max=1.0, help="Outcome-supervised learning rate."),
    ] = 1e-4,
    minimum_episodes: Annotated[
        int,
        typer.Option(min=1, help="Minimum completed official games required."),
    ] = 20,
    minimum_wins: Annotated[
        int,
        typer.Option(min=0, help="Minimum official wins required."),
    ] = 2,
    minimum_losses: Annotated[
        int,
        typer.Option(min=0, help="Minimum official losses required."),
    ] = 2,
    seed: Annotated[int, typer.Option()] = 67,
) -> None:
    """Create a non-deployable policy/value candidate from terminal episodes."""

    try:
        from godfield_bot.outcome_replay import OutcomeReplayDatasetError
        from godfield_bot.outcome_training import (
            OutcomeTrainingConfig,
            train_outcome_candidate,
        )
        from godfield_bot.training import TrainingError

        manifest = train_outcome_candidate(
            base_model_directory=base_model,
            model_root=root_directory,
            outcome_replay_path=outcome_replay,
            snapshot_path=snapshot,
            config=OutcomeTrainingConfig(
                epochs=epochs,
                learning_rate=learning_rate,
                minimum_episodes=minimum_episodes,
                minimum_wins=minimum_wins,
                minimum_losses=minimum_losses,
                seed=seed,
            ),
        )
    except (
        ImportError,
        OSError,
        ValueError,
        OutcomeReplayDatasetError,
        TrainingError,
    ) as error:
        structlog.get_logger().error(
            "outcome_training_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("train-simulation")
def models_train_simulation(
    base_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the new candidate."),
    ] = Path("models"),
    ruleset: Annotated[
        Literal[
            "fixed-role",
            "mixed-hand",
            "elemental-hand",
            "combo-hand",
            "resource-hand",
            "stochastic-resource-hand",
            "expanded-resource-hand",
        ],
        typer.Option(help="Attack/defense hand-distribution curriculum."),
    ] = "fixed-role",
    batch_size: Annotated[
        int,
        typer.Option(min=1, max=1_000_000, help="Parallel native self-play games."),
    ] = 256,
    rollout_steps: Annotated[
        int,
        typer.Option(min=2, max=4096, help="Decisions collected per game and update."),
    ] = 32,
    updates: Annotated[
        int,
        typer.Option(min=1, max=100_000, help="On-policy rollout/update cycles."),
    ] = 10,
    ppo_epochs: Annotated[
        int,
        typer.Option(min=1, max=100, help="Optimization passes over each rollout."),
    ] = 2,
    environment_minibatch_size: Annotated[
        int,
        typer.Option(min=1, max=1_000_000, help="Whole recurrent games per minibatch."),
    ] = 128,
    teacher_updates: Annotated[
        int,
        typer.Option(min=0, max=10_000, help="Heuristic imitation batches before PPO."),
    ] = 16,
    teacher_epochs: Annotated[
        int,
        typer.Option(min=1, max=100, help="Optimization passes per teacher batch."),
    ] = 2,
    teacher_learning_rate: Annotated[
        float,
        typer.Option(min=1e-8, max=1.0),
    ] = 1e-3,
    heuristic_opponent_fraction: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=1.0,
            help="Share of PPO games assigning one seat to the frozen heuristic.",
        ),
    ] = 0.5,
    learning_rate: Annotated[
        float,
        typer.Option(min=1e-8, max=1.0),
    ] = 3e-4,
    gamma: Annotated[float, typer.Option(min=1e-8, max=1.0)] = 0.99,
    gae_lambda: Annotated[float, typer.Option(min=0.0, max=1.0)] = 0.95,
    clip_range: Annotated[float, typer.Option(min=1e-8, max=1.0)] = 0.2,
    value_weight: Annotated[float, typer.Option(min=0.0, max=100.0)] = 0.5,
    entropy_weight: Annotated[float, typer.Option(min=0.0, max=100.0)] = 0.01,
    max_gradient_norm: Annotated[
        float,
        typer.Option(min=1e-8, max=100.0),
    ] = 0.5,
    seed: Annotated[int, typer.Option(min=0)] = 67,
    device: Annotated[
        Literal["cpu", "mps", "cuda"],
        typer.Option(help="PyTorch training device; native simulation remains on CPU."),
    ] = "cpu",
) -> None:
    """Create a non-deployable recurrent PPO candidate from native self-play."""

    try:
        from godfield_bot.simulation import SimulationUnavailableError
        from godfield_bot.simulation_training import (
            SimulationTrainingConfig,
            SimulationTrainingError,
            train_simulation_candidate,
        )

        manifest = train_simulation_candidate(
            base_model_directory=base_model,
            model_root=root_directory,
            snapshot_path=snapshot,
            config=SimulationTrainingConfig(
                ruleset=ruleset,
                batch_size=batch_size,
                rollout_steps=rollout_steps,
                updates=updates,
                ppo_epochs=ppo_epochs,
                environment_minibatch_size=environment_minibatch_size,
                teacher_updates=teacher_updates,
                teacher_epochs=teacher_epochs,
                teacher_learning_rate=teacher_learning_rate,
                heuristic_opponent_fraction=heuristic_opponent_fraction,
                learning_rate=learning_rate,
                gamma=gamma,
                gae_lambda=gae_lambda,
                clip_range=clip_range,
                value_weight=value_weight,
                entropy_weight=entropy_weight,
                max_gradient_norm=max_gradient_norm,
                seed=seed,
                device=device,
            ),
        )
    except KeyboardInterrupt:
        typer.echo("Simulation training interrupted; no candidate was written", err=True)
        raise typer.Exit(code=130) from None
    except (
        ImportError,
        OSError,
        ValueError,
        SimulationUnavailableError,
        SimulationTrainingError,
    ) as error:
        structlog.get_logger().error(
            "simulation_training_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("evaluate-simulation")
def models_evaluate_simulation(
    candidate_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    evaluation_directory: Annotated[
        Path,
        typer.Option(help="Owner-only directory for immutable evaluation reports."),
    ] = Path("models", "evaluations"),
    ruleset: Annotated[
        Literal[
            "fixed-role",
            "mixed-hand",
            "elemental-hand",
            "combo-hand",
            "resource-hand",
            "stochastic-resource-hand",
            "expanded-resource-hand",
        ],
        typer.Option(help="Attack/defense hand-distribution curriculum."),
    ] = "fixed-role",
    games_per_seat: Annotated[
        int,
        typer.Option(min=1, max=100_000, help="Paired initial deals per seat assignment."),
    ] = 512,
    max_decisions_per_game: Annotated[
        int,
        typer.Option(min=2, max=100_000, help="Fail incomplete games after this horizon."),
    ] = 512,
    minimum_score: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=1.0,
            help="Parent score to exceed with a paired lower confidence bound.",
        ),
    ] = 0.5,
    heuristic_noninferiority_margin: Annotated[
        float,
        typer.Option(
            min=0.0,
            max=1.0,
            help="Allowed paired-score deficit versus the frozen heuristic.",
        ),
    ] = 0.025,
    confidence_z: Annotated[
        float,
        typer.Option(min=1e-8, max=10.0, help="Normal critical value for confidence bounds."),
    ] = 1.96,
    seed: Annotated[int, typer.Option(min=0, max=18_446_744_073_709_551_615)] = 67,
    device: Annotated[
        Literal["cpu", "mps", "cuda"],
        typer.Option(help="PyTorch evaluation device; native simulation remains on CPU."),
    ] = "cpu",
) -> None:
    """Run a paired, non-promoting curriculum gate for one candidate."""

    try:
        from godfield_bot.simulation import SimulationUnavailableError
        from godfield_bot.simulation_evaluation import (
            SimulationEvaluationConfig,
            SimulationEvaluationError,
            evaluate_simulation_candidate,
        )
        from godfield_bot.simulation_policy import SimulationPolicyError

        result = evaluate_simulation_candidate(
            candidate_model_directory=candidate_model,
            snapshot_path=snapshot,
            evaluation_directory=evaluation_directory,
            config=SimulationEvaluationConfig(
                ruleset=ruleset,
                games_per_seat=games_per_seat,
                max_decisions_per_game=max_decisions_per_game,
                minimum_score=minimum_score,
                heuristic_noninferiority_margin=heuristic_noninferiority_margin,
                confidence_z=confidence_z,
                seed=seed,
                device=device,
            ),
        )
    except KeyboardInterrupt:
        typer.echo("Simulation evaluation interrupted; no report was written", err=True)
        raise typer.Exit(code=130) from None
    except (
        ImportError,
        OSError,
        ValueError,
        SimulationUnavailableError,
        SimulationEvaluationError,
        SimulationPolicyError,
    ) as error:
        structlog.get_logger().error(
            "simulation_evaluation_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@models_app.command("evaluate-live-shadow")
def models_evaluate_live_shadow(
    candidate_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    native_evaluation: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ],
    database: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("runs", "godfield.sqlite"),
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    evaluation_directory: Annotated[
        Path,
        typer.Option(help="Owner-only directory for immutable live-shadow reports."),
    ] = Path("models", "live-evaluations"),
    minimum_completed_games: Annotated[
        int,
        typer.Option(min=1, max=100_000),
    ] = 20,
    minimum_turn_opportunities: Annotated[
        int,
        typer.Option(min=1, max=1_000_000),
    ] = 40,
    minimum_defense_opportunities: Annotated[
        int,
        typer.Option(min=1, max=1_000_000),
    ] = 20,
    minimum_resource_opportunities: Annotated[
        int,
        typer.Option(min=1, max=1_000_000),
    ] = 12,
    minimum_each_resource_kind: Annotated[
        int,
        typer.Option(min=1, max=1_000_000),
    ] = 1,
    minimum_completion_lower_bound: Annotated[
        float,
        typer.Option(min=0.0, max=1.0),
    ] = 0.75,
    minimum_coverage_lower_bound: Annotated[
        float,
        typer.Option(min=0.0, max=1.0),
    ] = 0.50,
    minimum_agreement_lower_bound: Annotated[
        float,
        typer.Option(min=0.0, max=1.0),
    ] = 0.60,
    minimum_resource_coverage_lower_bound: Annotated[
        float,
        typer.Option(min=0.0, max=1.0),
    ] = 0.50,
    minimum_resource_agreement_lower_bound: Annotated[
        float,
        typer.Option(min=0.0, max=1.0),
    ] = 0.50,
    maximum_failed_runs: Annotated[
        int,
        typer.Option(min=0, max=100_000),
    ] = 0,
    maximum_operational_aborts: Annotated[
        int,
        typer.Option(min=0, max=100_000),
    ] = 0,
    confidence_z: Annotated[
        float,
        typer.Option(min=1e-8, max=10.0),
    ] = 1.96,
) -> None:
    """Evaluate immutable schema-v5 live shadow evidence; never promote a model."""

    try:
        from godfield_bot.live_shadow_evaluation import (
            LiveShadowEvaluationConfig,
            LiveShadowEvaluationError,
            evaluate_live_shadow_candidate,
        )
    except ImportError as error:
        structlog.get_logger().error(
            "live_shadow_evaluation_failed",
            error_type=type(error).__name__,
            reason="live shadow dependencies are unavailable; run `uv sync --extra training`",
        )
        raise typer.Exit(code=1) from None
    try:
        result = evaluate_live_shadow_candidate(
            candidate_model_directory=candidate_model,
            bible_snapshot_path=snapshot,
            native_evaluation_path=native_evaluation,
            database_path=database,
            evaluation_directory=evaluation_directory,
            config=LiveShadowEvaluationConfig(
                minimum_completed_games=minimum_completed_games,
                minimum_turn_opportunities=minimum_turn_opportunities,
                minimum_defense_opportunities=minimum_defense_opportunities,
                minimum_resource_opportunities=minimum_resource_opportunities,
                minimum_each_resource_kind=minimum_each_resource_kind,
                minimum_completion_lower_bound=minimum_completion_lower_bound,
                minimum_coverage_lower_bound=minimum_coverage_lower_bound,
                minimum_agreement_lower_bound=minimum_agreement_lower_bound,
                minimum_resource_coverage_lower_bound=(minimum_resource_coverage_lower_bound),
                minimum_resource_agreement_lower_bound=(minimum_resource_agreement_lower_bound),
                maximum_failed_runs=maximum_failed_runs,
                maximum_operational_aborts=maximum_operational_aborts,
                confidence_z=confidence_z,
            ),
        )
    except (OSError, ValueError, LiveShadowEvaluationError, RunStoreError) as error:
        structlog.get_logger().error(
            "live_shadow_evaluation_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@simulation_app.command("benchmark")
def simulation_benchmark(
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-07", "bible.json"),
    batch_size: Annotated[
        int,
        typer.Option(min=1, max=1_000_000, help="Parallel native curriculum games."),
    ] = 4096,
    batch_steps: Annotated[
        int,
        typer.Option(min=1, max=1_000_000, help="Batched simulator calls to measure."),
    ] = 1000,
    seed: Annotated[int, typer.Option(min=0)] = 67,
    ruleset: Annotated[
        Literal[
            "attack",
            "attack-defense",
            "mixed-attack-defense",
            "elemental-attack-defense",
            "combo-attack-defense",
            "resource-attack-defense",
            "stochastic-resource-attack-defense",
            "expanded-resource-attack-defense",
        ],
        typer.Option(help="Native curriculum ruleset to benchmark."),
    ] = "attack-defense",
) -> None:
    """Benchmark native transition collection without neural inference."""

    try:
        from godfield_bot.simulation import (
            SimulationUnavailableError,
            benchmark_attack_defense_simulation,
            benchmark_fixed_attack_simulation,
        )

        if ruleset == "attack":
            result = benchmark_fixed_attack_simulation(
                snapshot,
                batch_size=batch_size,
                batch_steps=batch_steps,
                seed=seed,
            )
        else:
            attack_defense_ruleset: Literal[
                "fixed-role",
                "mixed-hand",
                "elemental-hand",
                "combo-hand",
                "resource-hand",
                "stochastic-resource-hand",
                "expanded-resource-hand",
            ]
            if ruleset == "expanded-resource-attack-defense":
                attack_defense_ruleset = "expanded-resource-hand"
            elif ruleset == "stochastic-resource-attack-defense":
                attack_defense_ruleset = "stochastic-resource-hand"
            elif ruleset == "resource-attack-defense":
                attack_defense_ruleset = "resource-hand"
            elif ruleset == "combo-attack-defense":
                attack_defense_ruleset = "combo-hand"
            elif ruleset == "elemental-attack-defense":
                attack_defense_ruleset = "elemental-hand"
            elif ruleset == "mixed-attack-defense":
                attack_defense_ruleset = "mixed-hand"
            else:
                attack_defense_ruleset = "fixed-role"
            result = benchmark_attack_defense_simulation(
                snapshot,
                batch_size=batch_size,
                batch_steps=batch_steps,
                seed=seed,
                ruleset=attack_defense_ruleset,
            )
    except (ImportError, OSError, ValueError, SimulationUnavailableError) as error:
        structlog.get_logger().error(
            "simulation_benchmark_failed",
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


@data_app.command("refresh-api-catalog")
def data_refresh_api_catalog(
    output: Annotated[
        Path | None,
        typer.Option(help="Destination JSON; defaults to today's snapshot directory."),
    ] = None,
    language: Annotated[
        str,
        typer.Option(help="Published God Field catalog language."),
    ] = "en",
    timeout_seconds: Annotated[
        float, typer.Option(min=1.0, help="Catalog request timeout.")
    ] = 20.0,
) -> None:
    """Capture the current item catalog through the pinned pygodfield client."""

    from godfield_bot.api_catalog import (
        ApiCatalogError,
        fetch_api_catalog_snapshot,
        write_api_catalog_snapshot,
    )

    try:
        snapshot = fetch_api_catalog_snapshot(
            language=language,
            timeout_seconds=timeout_seconds,
        )
    except ApiCatalogError as error:
        structlog.get_logger().error(
            "api_catalog_refresh_failed",
            reason=str(error),
        )
        raise typer.Exit(code=1) from None
    destination = output or Path(
        "data",
        "snapshots",
        datetime.now(UTC).date().isoformat(),
        f"api-catalog-{language}.json",
    )
    write_api_catalog_snapshot(snapshot, destination)
    structlog.get_logger().info(
        "api_catalog_refresh_completed",
        output=str(destination),
        language=language,
        total=snapshot.total_items,
        content_sha256=snapshot.content_sha256,
    )
    typer.echo(destination)


@data_app.command("diff")
def data_diff(
    baseline: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    candidate: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    fail_on_change: Annotated[
        bool,
        typer.Option(help="Exit nonzero when a semantic or client change is found."),
    ] = False,
) -> None:
    """Compare two Bible snapshots without treating timestamps as changes."""

    from godfield_bot.domain.reference import BibleSnapshot

    try:
        before = BibleSnapshot.model_validate_json(baseline.read_text(encoding="utf-8"))
        after = BibleSnapshot.model_validate_json(candidate.read_text(encoding="utf-8"))
        result = diff_bible_snapshots(before, after)
    except (OSError, ValueError) as error:
        structlog.get_logger().error(
            "reference_diff_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))
    if fail_on_change and result.has_semantic_changes:
        raise typer.Exit(code=3)
