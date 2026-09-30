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
from godfield_bot.simulation import AttackDefenseRuleset

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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
    acquisition_evidence_probe: Annotated[
        bool,
        typer.Option(
            "--acquisition-evidence-probe",
            help=(
                "Collection only: capture self-only raw acquisition events from API reads. "
                "Requires finite time, solo entry, reviewed catalog, and no shadow model."
            ),
        ),
    ] = False,
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
                acquisition_evidence_probe=acquisition_evidence_probe,
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
        typer.Option(min=0, max=1000, help="Hard in-match browser-click budget."),
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    database: Annotated[
        Path,
        typer.Option(help="Local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
    dream_evidence_catalog: Annotated[
        Path,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Pinned API catalog used only to decode passive Dream evidence.",
        ),
    ] = Path("data", "snapshots", "2026-09-21", "api-catalog-en.json"),
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
    dream_evidence_probe: Annotated[
        bool,
        typer.Option(
            "--dream-evidence-probe",
            help=(
                "Passively record true/displayed Dream identities and DOM selectability "
                "after policy decisions."
            ),
        ),
    ] = False,
    acquisition_evidence_probe: Annotated[
        bool,
        typer.Option(
            "--acquisition-evidence-probe",
            help="Passively queue owned-item snapshots and redacted acquisition event metadata.",
        ),
    ] = False,
    acquisition_evidence_catalog: Annotated[
        Path,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Pinned API catalog provenance for passive acquisition evidence only.",
        ),
    ] = Path("data", "snapshots", "2026-09-21", "api-catalog-en.json"),
    acquisition_miracle_focus: Annotated[
        str | None,
        typer.Option(
            help=(
                "Collection only: prioritize a reviewed miracle slug (e.g. flame) twice per game. "
                "Requires acquisition probe and finite positive game/time budgets; excludes models."
            )
        ),
    ] = None,
    acquisition_queue_capacity: Annotated[
        int,
        typer.Option(min=8, max=4096, help="Bounded acquisition snapshot queue per page document."),
    ] = 256,
    max_actions: Annotated[
        int,
        typer.Option(min=1, max=1000, help="Hard browser-click budget for each game."),
    ] = 300,
    neural_model: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            readable=True,
            help="Candidate directory allowed to choose reviewed Training actions.",
        ),
    ] = None,
    shadow_model: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            readable=True,
            help=("Schema-v10 candidate scored passively while heuristic-v0 keeps control."),
        ),
    ] = None,
    canary_model: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            readable=True,
            help=("Schema-v10 candidate allowed one guarded disagreement per Training game."),
        ),
    ] = None,
    canary_readiness_report: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Passing immutable shadow-readiness report for --canary-model.",
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
    confirm_canary_intervention: Annotated[
        bool,
        typer.Option(
            "--confirm-canary-intervention",
            help="Confirm one guarded candidate intervention in each official Training game.",
        ),
    ] = False,
) -> None:
    """Continuously play God Field's official Training computer."""

    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.domain.run import RunStatus

    try:
        if acquisition_miracle_focus is not None and (
            neural_model is not None
            or shadow_model is not None
            or canary_model is not None
            or canary_readiness_report is not None
            or confirm_neural_control
            or confirm_canary_intervention
        ):
            raise RunnerError(
                "miracle collection cannot be combined with neural, shadow, or canary control"
            )
        if neural_model is not None and not confirm_neural_control:
            raise RunnerError("neural Training control requires --confirm-neural-control")
        if neural_model is None and confirm_neural_control:
            raise RunnerError("--confirm-neural-control requires --neural-model")
        if neural_model is not None and shadow_model is not None:
            raise RunnerError("--shadow-model cannot be combined with --neural-model")
        if canary_model is not None and not confirm_canary_intervention:
            raise RunnerError("Training canary requires --confirm-canary-intervention")
        if canary_model is None and confirm_canary_intervention:
            raise RunnerError("--confirm-canary-intervention requires --canary-model")
        if canary_model is None and canary_readiness_report is not None:
            raise RunnerError("--canary-readiness-report requires --canary-model")
        if canary_model is not None and canary_readiness_report is None:
            raise RunnerError("--canary-model requires --canary-readiness-report")
        if canary_model is not None and (neural_model is not None or shadow_model is not None):
            raise RunnerError(
                "--canary-model cannot be combined with --neural-model or --shadow-model"
            )
        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        if acquisition_miracle_focus is not None:
            policy = RunnerPolicyName.OFFICIAL_TRAINING_ACQUISITION
        elif neural_model is not None:
            policy = RunnerPolicyName.OFFICIAL_TRAINING_NEURAL
        elif canary_model is not None:
            policy = RunnerPolicyName.OFFICIAL_TRAINING_CANARY
        else:
            policy = RunnerPolicyName.HEURISTIC_V0
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
                        dream_evidence_probe=dream_evidence_probe,
                        dream_evidence_catalog=(
                            dream_evidence_catalog if dream_evidence_probe else None
                        ),
                        acquisition_evidence_probe=acquisition_evidence_probe,
                        acquisition_miracle_focus=acquisition_miracle_focus,
                        acquisition_evidence_catalog=(
                            acquisition_evidence_catalog if acquisition_evidence_probe else None
                        ),
                        acquisition_queue_capacity=acquisition_queue_capacity,
                        policy=policy,
                        model_directory=neural_model or canary_model,
                        shadow_model_directory=shadow_model,
                        canary_readiness_report=canary_readiness_report,
                        bible_snapshot=(
                            snapshot
                            if (
                                neural_model is not None
                                or shadow_model is not None
                                or canary_model is not None
                            )
                            else None
                        ),
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


@runs_app.command("dream-evidence")
def runs_dream_evidence(
    run_id: Annotated[str, typer.Argument()],
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
) -> None:
    """Summarize passive Dream identity and selectability evidence."""

    from godfield_bot.domain.run import EventKind
    from godfield_bot.dream_probe import DreamProbeSample, summarize_dream_evidence

    store = RunStore(database)
    run = store.get_run(run_id)
    if run is None:
        typer.echo("unknown run", err=True)
        raise typer.Exit(code=1)
    try:
        samples = tuple(
            DreamProbeSample.model_validate(event.payload)
            for event in store.events(run_id)
            if event.kind is EventKind.EVIDENCE
            and "dream_active" in event.payload
            and "items" in event.payload
        )
    except ValueError as error:
        typer.echo(f"invalid Dream evidence: {error}", err=True)
        raise typer.Exit(code=1) from None
    report = summarize_dream_evidence(samples)
    payload = {"run_id": run_id, **report.model_dump(mode="json")}
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@runs_app.command("inventory-evidence")
def runs_inventory_evidence(
    run_id: Annotated[str, typer.Argument()],
    database: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "runs", "godfield.sqlite"
    ),
) -> None:
    """Audit existing item-instance observations; never infer acquisition rules."""

    import sqlite3

    from godfield_bot.inventory_evidence import audit_inventory_run

    try:
        report = audit_inventory_run(database, run_id)
    except (OSError, ValueError, sqlite3.Error) as error:
        typer.echo(f"invalid inventory evidence: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@runs_app.command("acquisition-evidence")
def runs_acquisition_evidence(
    run_id: Annotated[str, typer.Argument()],
    database: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "runs", "godfield.sqlite"
    ),
) -> None:
    """Audit passive acquisition delivery, never adopt mechanics or training labels."""

    import sqlite3

    from pydantic import ValidationError

    from godfield_bot.acquisition_evidence import audit_acquisition_run

    try:
        report = audit_acquisition_run(database, run_id)
    except ValidationError:
        # Pydantic's full error text can echo malformed input; don't print raw
        # private data accidentally inserted into a corrupted evidence payload.
        typer.echo("invalid acquisition evidence: schema or content digest mismatch", err=True)
        raise typer.Exit(code=1) from None
    except (OSError, ValueError, sqlite3.Error) as error:
        typer.echo(f"invalid acquisition evidence: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@runs_app.command("acquisition-replay")
def runs_acquisition_replay(
    run_id: Annotated[str, typer.Argument()],
    database: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "runs", "godfield.sqlite"
    ),
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
) -> None:
    """Check recorded inventory projections against C++; never authorize training."""

    import sqlite3

    from pydantic import ValidationError

    from godfield_bot.acquisition_replay import (
        AcquisitionReplayUnavailableError,
        audit_acquisition_replay_run,
    )
    from godfield_bot.api_catalog import ApiCatalogError

    try:
        report = audit_acquisition_replay_run(database, run_id, catalog_path=catalog)
    except ValidationError:
        typer.echo("invalid acquisition replay: schema or content digest mismatch", err=True)
        raise typer.Exit(code=1) from None
    except (AcquisitionReplayUnavailableError, ApiCatalogError, OSError, ValueError, sqlite3.Error):
        # Never echo untrusted raw payloads, exception messages, or local secrets.
        typer.echo(
            "acquisition replay unavailable: check the run, pinned catalog, "
            "and installed simulation extra",
            err=True,
        )
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@runs_app.command("training-shadow")
def runs_training_shadow(
    run_ids: Annotated[list[str], typer.Argument(help="One or more Training run IDs.")],
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
) -> None:
    """Summarize passive schema-v10 proposals recorded during Training games."""

    from godfield_bot.domain.run import EventKind
    from godfield_bot.training_shadow import (
        TrainingShadowEvidence,
        summarize_training_shadow,
    )

    store = RunStore(database)
    missing = [run_id for run_id in run_ids if store.get_run(run_id) is None]
    if missing:
        typer.echo(f"unknown run: {missing[0]}", err=True)
        raise typer.Exit(code=1)
    try:
        samples = tuple(
            TrainingShadowEvidence.model_validate(event.payload)
            for run_id in run_ids
            for event in store.events(run_id)
            if event.kind is EventKind.EVIDENCE
            and event.payload.get("evidence_type") == "official_training_shadow"
        )
        report = summarize_training_shadow(samples)
    except ValueError as error:
        typer.echo(f"invalid Training shadow evidence: {error}", err=True)
        raise typer.Exit(code=1) from None
    payload = {"run_ids": run_ids, **report.model_dump(mode="json")}
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@runs_app.command("evaluate-training-shadow")
def runs_evaluate_training_shadow(
    model_directory: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    run_ids: Annotated[list[str], typer.Argument(help="One or more Training run IDs.")],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    database: Annotated[
        Path,
        typer.Option(help="Ignored local SQLite trajectory database."),
    ] = Path("runs", "godfield.sqlite"),
) -> None:
    """Replay stored heuristic decisions through a schema-v10 shadow model."""

    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.training_shadow import (
        evaluate_recorded_training_runs,
        summarize_training_shadow,
    )

    try:
        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        samples = evaluate_recorded_training_runs(
            RunStore(database),
            model_directory,
            bible,
            tuple(run_ids),
        )
        report = summarize_training_shadow(samples)
    except (OSError, ValueError, GameStateParseError, RunStoreError) as error:
        typer.echo(f"Training shadow replay failed: {error}", err=True)
        raise typer.Exit(code=1) from None
    payload = {"run_ids": run_ids, **report.model_dump(mode="json")}
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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


@models_app.command("migrate-illness-features")
def models_migrate_illness_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Expand schema v6 with actor-relative illness-stage inputs."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_illness_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_illness_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_illness_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-curse-features")
def models_migrate_curse_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Expand schema v7 with actor-relative Fog and Flash inputs."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_curse_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_curse_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_curse_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-dark-cloud-features")
def models_migrate_dark_cloud_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Expand schema v8 with actor-relative Dark Cloud inputs."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_dark_cloud_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_dark_cloud_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_dark_cloud_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-dream-features")
def models_migrate_dream_features(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Expand schema v9 with actor-relative Dream inputs."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_dream_features

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_dream_features(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_dream_migration_failed",
            error_type=type(error).__name__,
            reason=str(error).splitlines()[0],
        )
        raise typer.Exit(code=1) from None
    typer.echo(manifest.model_dump_json(indent=2))


@models_app.command("migrate-hand-capacity")
def models_migrate_hand_capacity(
    source_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    root_directory: Annotated[
        Path,
        typer.Option(help="Ignored root directory for the migrated model."),
    ] = Path("models"),
) -> None:
    """Migrate schema v10 to the 18-slot, 30-action local curriculum."""

    try:
        from godfield_bot.domain.reference import BibleSnapshot
        from godfield_bot.features import ArtifactVocabulary
        from godfield_bot.model_registry import migrate_hand_capacity

        bible = BibleSnapshot.model_validate_json(snapshot.read_text(encoding="utf-8"))
        vocabulary = ArtifactVocabulary.from_snapshot(bible)
        manifest = migrate_hand_capacity(
            source_model,
            root_directory,
            vocabulary,
            client_sha256=bible.client.sha256,
        )
    except (ImportError, OSError, ValueError) as error:
        structlog.get_logger().error(
            "model_hand_capacity_migration_failed",
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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


@models_app.command("create-simulation-league")
def models_create_simulation_league(
    base_model: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    opponent_model: Annotated[
        list[Path] | None,
        typer.Option(
            "--opponent-model",
            exists=True,
            file_okay=False,
            readable=True,
            help="Additional frozen checkpoint; repeat for each accepted ancestor or champion.",
        ),
    ] = None,
    snapshot: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    league_directory: Annotated[Path, typer.Option()] = Path("models", "leagues"),
    ruleset: Annotated[AttackDefenseRuleset, typer.Option()] = "dream-resource-hand",
    heuristic_weight: Annotated[
        float,
        typer.Option(
            min=1e-8, max=1_000_000, help="Heuristic sampling weight; each model has weight 1."
        ),
    ] = 1.0,
) -> None:
    """Freeze the parent, additional checkpoints, and versioned heuristic into a league."""

    try:
        from godfield_bot.simulation import SimulationUnavailableError
        from godfield_bot.simulation_league import create_simulation_league
        from godfield_bot.simulation_policy import SimulationPolicyError

        path, league = create_simulation_league(
            base_model_directory=base_model,
            opponent_model_directories=tuple(opponent_model or ()),
            snapshot_path=snapshot,
            league_directory=league_directory,
            ruleset=ruleset,
            heuristic_weight=heuristic_weight,
        )
    except (
        ImportError,
        OSError,
        ValueError,
        SimulationUnavailableError,
        SimulationPolicyError,
    ) as e:
        structlog.get_logger().error("simulation_league_failed", reason=str(e).splitlines()[0])
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            {
                "league_path": str(path),
                "league_sha256": league.sha256,
                "league": league.model_dump(mode="json"),
            },
            indent=2,
        )
    )


@models_app.command("evaluate-simulation-league")
def models_evaluate_simulation_league(
    candidate_model: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    league: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True, help="Frozen league JSON.")
    ],
    snapshot: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    evaluation_directory: Annotated[Path, typer.Option()] = Path("models", "league-evaluations"),
    games_per_seat: Annotated[int, typer.Option(min=2, max=100_000)] = 2048,
    max_decisions_per_game: Annotated[int, typer.Option(min=2, max=100_000)] = 512,
    minimum_score: Annotated[
        float, typer.Option(min=0.5, max=1.0, help="Paired lower bound every member must exceed.")
    ] = 0.5,
    confidence_z: Annotated[float, typer.Option(min=1e-8, max=10.0)] = 1.96,
    seed: Annotated[int, typer.Option(min=0, max=18_446_744_073_709_551_615)] = 67,
    device: Annotated[Literal["cpu", "mps", "cuda"], typer.Option()] = "cpu",
    compact_inference: Annotated[
        bool, typer.Option(help="Skip neural inference on already-completed first games.")
    ] = False,
) -> None:
    """Require superiority against every league member; write a local evidence report."""

    try:
        from godfield_bot.simulation import SimulationUnavailableError
        from godfield_bot.simulation_evaluation import SimulationEvaluationError
        from godfield_bot.simulation_league import SimulationLeagueSnapshot
        from godfield_bot.simulation_league_evaluation import (
            SimulationLeagueEvaluationConfig,
            evaluate_simulation_league_candidate,
        )
        from godfield_bot.simulation_policy import SimulationPolicyError

        roster = SimulationLeagueSnapshot.model_validate_json(league.read_text(encoding="utf-8"))
        result = evaluate_simulation_league_candidate(
            candidate_model_directory=candidate_model,
            league_path=league,
            snapshot_path=snapshot,
            evaluation_directory=evaluation_directory,
            config=SimulationLeagueEvaluationConfig(
                ruleset=roster.ruleset,
                games_per_seat=games_per_seat,
                max_decisions_per_game=max_decisions_per_game,
                minimum_score=minimum_score,
                confidence_z=confidence_z,
                seed=seed,
                device=device,
                compact_inference=compact_inference,
            ),
        )
    except KeyboardInterrupt:
        typer.echo("League evaluation interrupted; no report was written", err=True)
        raise typer.Exit(code=130) from None
    except (
        ImportError,
        OSError,
        ValueError,
        SimulationUnavailableError,
        SimulationEvaluationError,
        SimulationPolicyError,
    ) as e:
        structlog.get_logger().error(
            "simulation_league_evaluation_failed", reason=str(e).splitlines()[0]
        )
        raise typer.Exit(code=1) from None
    typer.echo(result.model_dump_json(indent=2))


@models_app.command("train-simulation")
def models_train_simulation(
    base_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
            "reflection-resource-hand",
            "reflection-weapon-resource-hand",
            "dual-role-resource-hand",
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
            "miracle-block-resource-hand",
            "miracle-block-weapon-resource-hand",
            "miracle-bounce-resource-hand",
            "miracle-bounce-weapon-resource-hand",
            "miracle-bounce-miracle-resource-hand",
            "miracle-reflection-resource-hand",
            "fog-flash-resource-hand",
            "dark-cloud-resource-hand",
            "dream-resource-hand",
            "gift-weighted-dream-resource-hand",
            "wide-hand-gift-weighted-dream-resource-hand",
            "provisional-strength-powder-wide-hand",
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
    league: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Frozen league JSON; replaces the heuristic/self-play opponent mix.",
        ),
    ] = None,
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
            league_path=league,
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
            "reflection-resource-hand",
            "reflection-weapon-resource-hand",
            "dual-role-resource-hand",
            "chance-weapon-resource-hand",
            "absorption-weapon-resource-hand",
            "dynamic-mp-weapon-resource-hand",
            "same-damage-weapon-resource-hand",
            "attack-twice-weapon-resource-hand",
            "random-target-weapon-resource-hand",
            "illness-weapon-resource-hand",
            "illness-cure-resource-hand",
            "heaven-herb-resource-hand",
            "fever-mask-resource-hand",
            "miracle-block-resource-hand",
            "miracle-block-weapon-resource-hand",
            "miracle-bounce-resource-hand",
            "miracle-bounce-weapon-resource-hand",
            "miracle-bounce-miracle-resource-hand",
            "miracle-reflection-resource-hand",
            "fog-flash-resource-hand",
            "dark-cloud-resource-hand",
            "dream-resource-hand",
            "gift-weighted-dream-resource-hand",
            "wide-hand-gift-weighted-dream-resource-hand",
            "provisional-strength-powder-wide-hand",
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
    compact_inference: Annotated[
        bool, typer.Option(help="Skip neural inference on already-completed first games.")
    ] = False,
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
                compact_inference=compact_inference,
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


@models_app.command("evaluate-training-shadow-readiness")
def models_evaluate_training_shadow_readiness(
    candidate_model: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    database: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("runs", "godfield.sqlite"),
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
    native_evaluation_directory: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=False,
            readable=True,
            help="Directory containing immutable native curriculum reports.",
        ),
    ] = Path("models", "evaluations"),
    evaluation_directory: Annotated[
        Path,
        typer.Option(help="Owner-only directory for Training-shadow readiness reports."),
    ] = Path("models", "training-shadow-evaluations"),
) -> None:
    """Audit schema-v10 official-CPU shadow evidence without granting control."""

    try:
        from godfield_bot.training_shadow_evaluation import (
            TrainingShadowReadinessConfig,
            evaluate_training_shadow_readiness,
        )

        result = evaluate_training_shadow_readiness(
            candidate_model_directory=candidate_model,
            bible_snapshot_path=snapshot,
            native_evaluation_directory=native_evaluation_directory,
            database_path=database,
            evaluation_directory=evaluation_directory,
            config=TrainingShadowReadinessConfig(),
        )
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        structlog.get_logger().error(
            "training_shadow_readiness_failed",
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
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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


@simulation_app.command("provisional-soap-plan")
def simulation_provisional_soap_plan(
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
    bible: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
) -> None:
    """Inspect an unvalidated local Soap hypothesis; never a training gate."""

    from godfield_bot.api_catalog import read_api_catalog_snapshot
    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.provisional_rules import (
        ProvisionalRuleUnavailableError,
        build_provisional_soap_plan,
    )

    try:
        plan = build_provisional_soap_plan(
            read_api_catalog_snapshot(catalog),
            BibleSnapshot.model_validate_json(bible.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, ProvisionalRuleUnavailableError) as error:
        structlog.get_logger().error(
            "provisional_soap_plan_failed", reason=str(error).splitlines()[0]
        )
        raise typer.Exit(code=1) from None
    typer.echo(plan.model_dump_json(indent=2))


@simulation_app.command("provisional-guardian-plan")
def simulation_provisional_guardian_plan(
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
    bible: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
) -> None:
    """Inspect a catalog-derived guardian weight map; not a combat rule."""

    from godfield_bot.api_catalog import read_api_catalog_snapshot
    from godfield_bot.domain.reference import BibleSnapshot
    from godfield_bot.provisional_rules import (
        ProvisionalRuleUnavailableError,
        build_provisional_guardian_plan,
    )

    try:
        plan = build_provisional_guardian_plan(
            read_api_catalog_snapshot(catalog),
            BibleSnapshot.model_validate_json(bible.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, ProvisionalRuleUnavailableError) as error:
        structlog.get_logger().error(
            "provisional_guardian_plan_failed", reason=str(error).splitlines()[0]
        )
        raise typer.Exit(code=1) from None
    typer.echo(plan.model_dump_json(indent=2))


@simulation_app.command("guardian-batch-plan")
def simulation_guardian_batch_plan(
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
    bible: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    batch_size: Annotated[int, typer.Option(min=1, max=2_000_000)] = 512,
    player_count: Annotated[int, typer.Option(min=2, max=9)] = 2,
    slots_per_environment: Annotated[int, typer.Option(min=1, max=64)] = 8,
    combat: Annotated[
        bool, typer.Option(help="Include provisional basic guardian combat.")
    ] = False,
    initial_hp: Annotated[int, typer.Option(min=1, max=100)] = 40,
    turns: Annotated[
        bool, typer.Option(help="Include provisional card turns, armor, and reusable defenses.")
    ] = False,
    hand_slots: Annotated[int, typer.Option(min=1, max=18)] = 18,
    max_turns: Annotated[int, typer.Option(min=1, max=1_000_000_000)] = 1000,
    initial_mp: Annotated[int, typer.Option(min=0, max=100)] = 10,
    initial_cp: Annotated[int, typer.Option(min=0, max=100)] = 0,
    inventory_utilities: Annotated[
        bool,
        typer.Option(
            help="Use the separate, provisional eight-card HP/MP utility batch (requires --turns)."
        ),
    ] = False,
) -> None:
    """Inspect a separate native guardian lifecycle batch; not a training gate."""

    from godfield_bot.guardian_batch import (
        create_provisional_guardian_batch,
        create_provisional_guardian_combat_batch,
        create_provisional_guardian_turn_batch,
    )
    from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

    try:
        if inventory_utilities:
            if not turns:
                raise ValueError("--inventory-utilities requires --turns")
            from godfield_bot.guardian_utility import create_provisional_guardian_utility_turn_batch

            utility_created = create_provisional_guardian_utility_turn_batch(
                catalog_path=catalog,
                bible_path=bible,
                batch_size=batch_size,
                player_count=player_count,
                slots_per_environment=slots_per_environment,
                hand_slots=hand_slots,
                max_turns=max_turns,
                initial_hp=initial_hp,
                initial_mp=initial_mp,
                initial_cp=initial_cp,
            )
            typer.echo(utility_created.metadata.model_dump_json(indent=2))
            return
        if turns:
            turn_created = create_provisional_guardian_turn_batch(
                catalog_path=catalog,
                bible_path=bible,
                batch_size=batch_size,
                player_count=player_count,
                slots_per_environment=slots_per_environment,
                initial_hp=initial_hp,
                hand_slots=hand_slots,
                max_turns=max_turns,
                initial_mp=initial_mp,
                initial_cp=initial_cp,
            )
            typer.echo(turn_created.metadata.model_dump_json(indent=2))
            return
        if combat:
            combat_created = create_provisional_guardian_combat_batch(
                catalog_path=catalog,
                bible_path=bible,
                batch_size=batch_size,
                player_count=player_count,
                slots_per_environment=slots_per_environment,
                initial_hp=initial_hp,
                initial_mp=initial_mp,
                initial_cp=initial_cp,
            )
            typer.echo(combat_created.metadata.model_dump_json(indent=2))
            return
        created = create_provisional_guardian_batch(
            catalog_path=catalog,
            bible_path=bible,
            batch_size=batch_size,
            player_count=player_count,
            slots_per_environment=slots_per_environment,
        )
    except (OSError, ValueError, ProvisionalRuleUnavailableError) as error:
        structlog.get_logger().error(
            "guardian_batch_plan_failed", reason=str(error).splitlines()[0]
        )
        raise typer.Exit(code=1) from None
    typer.echo(created.metadata.model_dump_json(indent=2))


@simulation_app.command("guardian-rollout")
def simulation_guardian_rollout(
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
    bible: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    batch_size: Annotated[int, typer.Option(min=1, max=4096)] = 64,
    player_count: Annotated[int, typer.Option(min=2, max=9)] = 2,
    steps: Annotated[int, typer.Option(min=1, max=100_000)] = 256,
    seed: Annotated[int, typer.Option(min=0, max=2**32 - 1)] = 67,
    max_turns: Annotated[int, typer.Option(min=1, max=100_000)] = 64,
    max_decisions: Annotated[int, typer.Option(min=1, max=100_000)] = 1024,
    opening: Annotated[str, typer.Option(help="cards-only, mars-opening, or mixed.")] = "mixed",
    refill: Annotated[
        str, typer.Option(help="none, weighted-consumption-v1, or weighted-utility-consumption-v1.")
    ] = "none",
    inventory_utilities: Annotated[
        bool, typer.Option(help="Use the separate nine-feature HP/MP curriculum.")
    ] = False,
) -> None:
    """Exercise seeded local C++ arena episodes; does not train or play online."""

    from godfield_bot.api_catalog import ApiCatalogError
    from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

    try:
        from godfield_bot.guardian_rollout import (
            GuardianRolloutArena,
            GuardianRolloutConfig,
            collect_guardian_rollout,
        )

        config = GuardianRolloutConfig.model_validate(
            {
                "batch_size": batch_size,
                "player_count": player_count,
                "seed": seed,
                "max_turns": max_turns,
                "max_decisions": max_decisions,
                "opening": opening,
                "refill": refill,
                "inventory_utilities": inventory_utilities,
            }
        )
        if steps * batch_size > 1_000_000:
            raise ValueError("rollout is limited to 1000000 transitions")
        arena = GuardianRolloutArena(catalog_path=catalog, bible_path=bible, config=config)
        report = collect_guardian_rollout(arena, steps=steps)
    except (
        ImportError,
        OSError,
        ValueError,
        ApiCatalogError,
        ProvisionalRuleUnavailableError,
    ) as error:
        structlog.get_logger().error("guardian_rollout_failed", reason=str(error).splitlines()[0])
        raise typer.Exit(code=1) from None
    typer.echo(report.model_dump_json(indent=2))


@simulation_app.command("guardian-train")
def simulation_guardian_train(
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
    bible: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    checkpoint_root: Annotated[Path, typer.Option(file_okay=False)] = Path(
        "checkpoints/guardian-arena"
    ),
    resume: Annotated[Path | None, typer.Option(exists=True, file_okay=False)] = None,
    migrate_utilities_from: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            help="Explicit 7→9-feature transfer into a new utility child; not --resume.",
        ),
    ] = None,
    batch_size: Annotated[int, typer.Option(min=1, max=4096)] = 64,
    rollout_steps: Annotated[int, typer.Option(min=2, max=256)] = 64,
    updates: Annotated[int, typer.Option(min=1, max=1000)] = 10,
    teacher_updates: Annotated[int, typer.Option(min=0, max=1000)] = 64,
    teacher_selected_defense_weight: Annotated[float, typer.Option(min=1, max=16)] = 4,
    defense_feedback_weight: Annotated[
        float,
        typer.Option(min=0, max=4, help="Training-only teacher loss on learner defense states."),
    ] = 0,
    defense_feedback_scope: Annotated[
        str, typer.Option(help="all-defense, or finish-decisions (confirmation/forgiveness only).")
    ] = "all-defense",
    ppo_epochs: Annotated[int, typer.Option(min=1, max=10)] = 2,
    environment_minibatch_size: Annotated[int | None, typer.Option(min=1, max=512)] = None,
    seed: Annotated[int, typer.Option(min=0, max=2**32 - 1)] = 67,
    max_turns: Annotated[int, typer.Option(min=1, max=100_000)] = 64,
    max_decisions: Annotated[int, typer.Option(min=1, max=100_000)] = 128,
    opening: Annotated[str, typer.Option(help="cards-only, mars-opening, or mixed.")] = "mixed",
    refill: Annotated[
        str,
        typer.Option(help="none, weighted-consumption-v1, or weighted-utility-consumption-v1."),
    ] = "none",
    inventory_utilities: Annotated[
        bool, typer.Option(help="Use the separate nine-feature HP/MP curriculum.")
    ] = False,
    baseline_opponent_fraction: Annotated[float, typer.Option(min=0, max=1)] = 0.5,
    evaluation_games: Annotated[int, typer.Option(min=2, max=256)] = 32,
    cpu_threads: Annotated[int, typer.Option(min=1, max=16)] = 2,
    hidden_size: Annotated[int, typer.Option(min=16, max=256)] = 128,
    embedding_size: Annotated[int, typer.Option(min=8, max=128)] = 32,
) -> None:
    """Train a separate local C++ duel candidate; never changes live controls."""

    from godfield_bot.api_catalog import ApiCatalogError
    from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

    try:
        from godfield_bot.guardian_training import GuardianTrainingConfig, train_guardian_candidate

        config = GuardianTrainingConfig.model_validate(
            {
                "arena": {
                    "batch_size": batch_size,
                    "seed": seed,
                    "max_turns": max_turns,
                    "max_decisions": max_decisions,
                    "opening": opening,
                    "refill": refill,
                    "inventory_utilities": inventory_utilities,
                },
                "rollout_steps": rollout_steps,
                "updates": updates,
                "teacher_updates": teacher_updates,
                "teacher_selected_defense_weight": teacher_selected_defense_weight,
                "defense_feedback_weight": defense_feedback_weight,
                "defense_feedback_scope": defense_feedback_scope,
                "ppo_epochs": ppo_epochs,
                "environment_minibatch_size": environment_minibatch_size
                if environment_minibatch_size is not None
                else min(16, batch_size),
                "baseline_opponent_fraction": baseline_opponent_fraction,
                "evaluation_games": evaluation_games,
                "cpu_threads": cpu_threads,
                "hidden_size": hidden_size,
                "embedding_size": embedding_size,
            }
        )
        directory, manifest = train_guardian_candidate(
            catalog_path=catalog,
            bible_path=bible,
            checkpoint_root=checkpoint_root,
            config=config,
            resume=resume,
            migrate_utilities_from=migrate_utilities_from,
        )
    except (
        ImportError,
        OSError,
        ValueError,
        RuntimeError,
        ApiCatalogError,
        ProvisionalRuleUnavailableError,
    ) as error:
        structlog.get_logger().error("guardian_training_failed", reason=str(error).splitlines()[0])
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            {
                "checkpoint_directory": str(directory.resolve()),
                "manifest": manifest.model_dump(mode="json"),
            },
            indent=2,
        )
    )


@simulation_app.command("guardian-evaluate")
def simulation_guardian_evaluate(
    checkpoint: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    catalog: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-21", "api-catalog-en.json"
    ),
    bible: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    games: Annotated[int, typer.Option(min=2, max=256)] = 64,
    seed: Annotated[int, typer.Option(min=0, max=2**32 - 1)] = 2_000_070,
    cpu_threads: Annotated[int, typer.Option(min=1, max=16)] = 2,
) -> None:
    """Read-only paired local evaluation; not official play or a promotion gate."""

    from godfield_bot.api_catalog import ApiCatalogError
    from godfield_bot.provisional_rules import ProvisionalRuleUnavailableError

    try:
        from godfield_bot.guardian_training import evaluate_guardian_checkpoint

        report = evaluate_guardian_checkpoint(
            checkpoint,
            catalog_path=catalog,
            bible_path=bible,
            games=games,
            seed=seed,
            cpu_threads=cpu_threads,
        )
    except (
        ImportError,
        OSError,
        ValueError,
        RuntimeError,
        ApiCatalogError,
        ProvisionalRuleUnavailableError,
    ) as error:
        structlog.get_logger().error(
            "guardian_evaluation_failed", reason=str(error).splitlines()[0]
        )
        raise typer.Exit(code=1) from None
    typer.echo(report.model_dump_json(indent=2))


@simulation_app.command("coverage-report")
def simulation_coverage_report(
    snapshot: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    ruleset: Annotated[
        Literal[
            "wide-hand-gift-weighted-dream-resource-hand",
            "provisional-strength-powder-wide-hand",
        ],
        typer.Option(help="Native curriculum to audit."),
    ] = "wide-hand-gift-weighted-dream-resource-hand",
) -> None:
    """List missing artifacts in the latest native curriculum; not a fidelity gate."""

    from godfield_bot.simulation import SimulationUnavailableError
    from godfield_bot.simulation_coverage import build_simulation_coverage_report

    try:
        report = build_simulation_coverage_report(snapshot, ruleset=ruleset)
    except (OSError, ValueError, SimulationUnavailableError) as error:
        structlog.get_logger().error(
            "simulation_coverage_report_failed", reason=str(error).splitlines()[0]
        )
        raise typer.Exit(code=1) from None
    typer.echo(report.model_dump_json(indent=2))


@simulation_app.command("trace-game")
def simulation_trace_game(
    model: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    snapshot: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data", "snapshots", "2026-09-20", "bible.json"
    ),
    ruleset: Annotated[AttackDefenseRuleset, typer.Option()] = (
        "wide-hand-gift-weighted-dream-resource-hand"
    ),
    seed: Annotated[int, typer.Option(min=0, max=18_446_744_073_709_551_615)] = 67,
    environment: Annotated[int, typer.Option(min=0, max=999_999)] = 0,
    candidate_seat: Annotated[int, typer.Option(min=0, max=1)] = 0,
    max_decisions: Annotated[int, typer.Option(min=2, max=4096)] = 512,
    trace_directory: Annotated[Path, typer.Option()] = Path("runs", "simulation-traces"),
    opponent_model: Annotated[
        Path | None, typer.Option(exists=True, file_okay=False, readable=True)
    ] = None,
) -> None:
    """Trace one local first-deal index; diagnostics never count as gate passes."""

    try:
        from godfield_bot.simulation_diagnostics import SimulationTraceConfig, trace_simulation_game

        path, trace = trace_simulation_game(
            candidate_model_directory=model,
            snapshot_path=snapshot,
            trace_directory=trace_directory,
            opponent_model_directory=opponent_model,
            config=SimulationTraceConfig(
                ruleset=ruleset,
                seed=seed,
                environment=environment,
                candidate_seat=candidate_seat,
                max_decisions=max_decisions,
            ),
        )
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        structlog.get_logger().error("simulation_trace_failed", reason=str(error).splitlines()[0])
        raise typer.Exit(code=1) from None
    typer.echo(
        json.dumps(
            {
                "trace_path": str(path),
                "trace_id": trace.trace_id,
                "completed": trace.completed,
                "decisions": len(trace.decisions),
                "candidate_outcome": trace.candidate_outcome,
                "source_kind": trace.source_kind,
                "promotion_eligible": False,
            },
            indent=2,
        )
    )


@simulation_app.command("benchmark")
def simulation_benchmark(
    snapshot: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data", "snapshots", "2026-09-20", "bible.json"),
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
            "reflection-resource-attack-defense",
            "reflection-weapon-resource-attack-defense",
            "dual-role-resource-attack-defense",
            "chance-weapon-resource-attack-defense",
            "absorption-weapon-resource-attack-defense",
            "dynamic-mp-weapon-resource-attack-defense",
            "same-damage-weapon-resource-attack-defense",
            "attack-twice-weapon-resource-attack-defense",
            "random-target-weapon-resource-attack-defense",
            "illness-weapon-resource-attack-defense",
            "illness-cure-resource-attack-defense",
            "heaven-herb-resource-attack-defense",
            "fever-mask-resource-attack-defense",
            "miracle-block-resource-attack-defense",
            "miracle-block-weapon-resource-attack-defense",
            "miracle-bounce-resource-attack-defense",
            "miracle-bounce-weapon-resource-attack-defense",
            "miracle-bounce-miracle-resource-attack-defense",
            "miracle-reflection-resource-attack-defense",
            "fog-flash-resource-attack-defense",
            "dark-cloud-resource-attack-defense",
            "dream-resource-attack-defense",
            "gift-weighted-dream-resource-attack-defense",
            "wide-hand-gift-weighted-dream-resource-attack-defense",
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
                "reflection-resource-hand",
                "reflection-weapon-resource-hand",
                "dual-role-resource-hand",
                "chance-weapon-resource-hand",
                "absorption-weapon-resource-hand",
                "dynamic-mp-weapon-resource-hand",
                "same-damage-weapon-resource-hand",
                "attack-twice-weapon-resource-hand",
                "random-target-weapon-resource-hand",
                "illness-weapon-resource-hand",
                "illness-cure-resource-hand",
                "heaven-herb-resource-hand",
                "fever-mask-resource-hand",
                "miracle-block-resource-hand",
                "miracle-block-weapon-resource-hand",
                "miracle-bounce-resource-hand",
                "miracle-bounce-weapon-resource-hand",
                "miracle-bounce-miracle-resource-hand",
                "miracle-reflection-resource-hand",
                "fog-flash-resource-hand",
                "dark-cloud-resource-hand",
                "dream-resource-hand",
                "gift-weighted-dream-resource-hand",
                "wide-hand-gift-weighted-dream-resource-hand",
            ]
            if ruleset == "wide-hand-gift-weighted-dream-resource-attack-defense":
                attack_defense_ruleset = "wide-hand-gift-weighted-dream-resource-hand"
            elif ruleset == "gift-weighted-dream-resource-attack-defense":
                attack_defense_ruleset = "gift-weighted-dream-resource-hand"
            elif ruleset == "dream-resource-attack-defense":
                attack_defense_ruleset = "dream-resource-hand"
            elif ruleset == "dark-cloud-resource-attack-defense":
                attack_defense_ruleset = "dark-cloud-resource-hand"
            elif ruleset == "fog-flash-resource-attack-defense":
                attack_defense_ruleset = "fog-flash-resource-hand"
            elif ruleset == "miracle-reflection-resource-attack-defense":
                attack_defense_ruleset = "miracle-reflection-resource-hand"
            elif ruleset == "miracle-bounce-miracle-resource-attack-defense":
                attack_defense_ruleset = "miracle-bounce-miracle-resource-hand"
            elif ruleset == "miracle-bounce-weapon-resource-attack-defense":
                attack_defense_ruleset = "miracle-bounce-weapon-resource-hand"
            elif ruleset == "miracle-bounce-resource-attack-defense":
                attack_defense_ruleset = "miracle-bounce-resource-hand"
            elif ruleset == "miracle-block-weapon-resource-attack-defense":
                attack_defense_ruleset = "miracle-block-weapon-resource-hand"
            elif ruleset == "miracle-block-resource-attack-defense":
                attack_defense_ruleset = "miracle-block-resource-hand"
            elif ruleset == "fever-mask-resource-attack-defense":
                attack_defense_ruleset = "fever-mask-resource-hand"
            elif ruleset == "heaven-herb-resource-attack-defense":
                attack_defense_ruleset = "heaven-herb-resource-hand"
            elif ruleset == "illness-cure-resource-attack-defense":
                attack_defense_ruleset = "illness-cure-resource-hand"
            elif ruleset == "illness-weapon-resource-attack-defense":
                attack_defense_ruleset = "illness-weapon-resource-hand"
            elif ruleset == "random-target-weapon-resource-attack-defense":
                attack_defense_ruleset = "random-target-weapon-resource-hand"
            elif ruleset == "attack-twice-weapon-resource-attack-defense":
                attack_defense_ruleset = "attack-twice-weapon-resource-hand"
            elif ruleset == "same-damage-weapon-resource-attack-defense":
                attack_defense_ruleset = "same-damage-weapon-resource-hand"
            elif ruleset == "dynamic-mp-weapon-resource-attack-defense":
                attack_defense_ruleset = "dynamic-mp-weapon-resource-hand"
            elif ruleset == "absorption-weapon-resource-attack-defense":
                attack_defense_ruleset = "absorption-weapon-resource-hand"
            elif ruleset == "chance-weapon-resource-attack-defense":
                attack_defense_ruleset = "chance-weapon-resource-hand"
            elif ruleset == "dual-role-resource-attack-defense":
                attack_defense_ruleset = "dual-role-resource-hand"
            elif ruleset == "reflection-weapon-resource-attack-defense":
                attack_defense_ruleset = "reflection-weapon-resource-hand"
            elif ruleset == "reflection-resource-attack-defense":
                attack_defense_ruleset = "reflection-resource-hand"
            elif ruleset == "expanded-resource-attack-defense":
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
