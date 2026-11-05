"""Reproducible local acceptance, separate from historical metadata and live promotion."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from godfield_bot.full_game_integration_audit import (
    FullGameIntegrationAudit,
    build_full_game_integration_audit,
    canonical_sha256,
    workflow_ledger,
)
from godfield_bot.full_game_learning_probe import (
    FullGameLearningProbeConfig,
    FullGameLearningProbeReport,
    run_full_game_learning_probe,
)
from godfield_bot.full_game_training import FullGameTrainingRuntime, _training_runtime

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
EVIDENCE_FILES = (
    "catalog.json",
    "bible.json",
    "integration.json",
    "test-collection.log",
    "test-nodes.json",
    "tests.xml",
    "tests.log",
    "learning-probe.json",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class AcceptanceFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str = Field(min_length=1)
    sha256: Digest

    @model_validator(mode="after")
    def relative_path(self) -> AcceptanceFile:
        if Path(self.path).is_absolute() or ".." in Path(self.path).parts:
            raise ValueError("acceptance paths must stay within their recorded directory")
        return self


def source_files(root: Path) -> tuple[AcceptanceFile, ...]:
    """Code, native build inputs, tests and locked dependencies; never accounts or runs."""
    paths = {root / name for name in ("pyproject.toml", "uv.lock")}
    for folder in ("src", "tests", "native", "data/snapshots"):
        directory = root / folder
        if not directory.is_dir():
            raise ValueError(f"acceptance requires repository source directory: {folder}")
        paths.update(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and (
                folder in ("tests", "data/snapshots")
                or path.suffix in (".py", ".pyi", ".cpp", ".h", ".hpp", ".cmake", ".toml")
                or path.name in ("CMakeLists.txt", "py.typed")
            )
            and not {"__pycache__", ".venv", "build"}.intersection(path.relative_to(root).parts)
        )
    return tuple(
        AcceptanceFile(path=path.relative_to(root).as_posix(), sha256=file_sha256(path))
        for path in sorted(paths)
    )


class AcceptanceRuntime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    python_version: str
    package_versions: tuple[tuple[str, str], ...]
    native_binary_sha256: Digest
    native_source_sha256: Digest
    training: FullGameTrainingRuntime


def native_source_sha256(root: Path) -> str:
    """Same newline-delimited path/file-hash contract as the CMake build manifest."""
    native_root = root / "native/godfield_sim"
    paths = {native_root / name for name in ("CMakeLists.txt", "pyproject.toml")}
    paths.update(
        path
        for path in (native_root / "src").rglob("*")
        if path.is_file()
        and (
            path.suffix in (".cpp", ".h", ".hpp", ".py", ".pyi", ".cmake")
            or path.name == "py.typed"
        )
    )
    manifest = "".join(
        f"{path.relative_to(native_root).as_posix()}\n{file_sha256(path)}\n"
        for path in sorted(paths)
    )
    return hashlib.sha256(manifest.encode()).hexdigest()


def _require_checkout(root: Path) -> None:
    if root.resolve() != Path(__file__).resolve().parents[2]:
        raise ValueError("acceptance must run from the checkout that owns the imported package")


def acceptance_runtime(root: Path) -> AcceptanceRuntime:
    native = importlib.import_module("godfield_sim._native")
    if native.__file__ is None:
        raise RuntimeError("acceptance requires the loaded native extension file")
    source_hash = native_source_sha256(root)
    if getattr(native, "BUILD_SOURCE_SHA256", None) != source_hash:
        raise ValueError("native build is stale; rebuild godfield-sim before acceptance")
    return AcceptanceRuntime(
        python_version=platform.python_version(),
        package_versions=tuple(
            (name, version(name))
            for name in (
                "godfield-sim",
                "numpy",
                "pydantic",
                "pytest",
                "torch",
            )
        ),
        native_binary_sha256=file_sha256(Path(native.__file__)),
        native_source_sha256=source_hash,
        training=_training_runtime(),
    )


def collected_test_nodes(output: str) -> tuple[str, ...]:
    summary = "\n".join(line for line in output.splitlines() if not line.startswith("tests/"))
    if re.search(r"\b[1-9][0-9]* (?:skipped|deselected|errors?)\b", summary):
        raise ValueError("acceptance collection cannot skip, deselect or fail tests")
    nodes = tuple(
        line.strip() for line in output.splitlines() if line.startswith("tests/") and "::" in line
    )
    if not nodes or len(set(nodes)) != len(nodes):
        raise ValueError("acceptance requires nonempty unique collected test nodes")
    covered = {node.split("::", 1)[0] for node in nodes}
    required = {path for w in workflow_ledger() for path in w.test_files}
    if not required <= covered:
        raise ValueError("acceptance collection omitted required workflow test files")
    return tuple(sorted(nodes))


def verify_junit(path: Path, nodes: tuple[str, ...]) -> int:
    """Match every collected parameterized test, not a test-count threshold."""
    if not nodes or len(set(nodes)) != len(nodes):
        raise ValueError("acceptance expected test nodes are empty or duplicated")
    data = path.read_bytes()
    if len(data) > 50_000_000 or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("acceptance refuses oversized or entity-bearing test XML")
    root = ET.fromstring(data)
    suites = list(root.iter("testsuite"))
    tests = list(root.iter("testcase"))
    expected = set()
    for node in nodes:
        filename, *names = node.split("::")
        if not filename.startswith("tests/") or not filename.endswith(".py") or not names:
            raise ValueError("acceptance test identity is malformed")
        expected.add((".".join((filename[:-3].replace("/", "."), *names[:-1])), names[-1]))
    actual = [(test.get("classname"), test.get("name")) for test in tests]
    if (
        not suites
        or len(expected) != len(nodes)
        or len(tests) != len(nodes)
        or len(set(actual)) != len(actual)
        or set(actual) != expected
        or any(
            test.find(tag) is not None for test in tests for tag in ("failure", "error", "skipped")
        )
        or any(
            int(suite.get(key, "-1")) != 0
            for suite in suites
            for key in ("errors", "failures", "skipped")
        )
        or sum(int(suite.get("tests", "-1")) for suite in suites) != len(nodes)
    ):
        raise ValueError(
            "acceptance requires every collected test to execute and pass without skips"
        )
    return len(nodes)


def verify_learning_matrix(
    report: FullGameLearningProbeReport, audit: FullGameIntegrationAudit
) -> int:
    expected = FullGameLearningProbeConfig(seed=report.config.seed)
    if report.config != expected or len(report.cases) != 32 or not report.passed:
        raise ValueError("acceptance requires the complete standard roster learning matrix")
    canonical = audit.metadata.model_dump(
        exclude={"seed", "batch_size", "player_count", "initial_teams"}
    )
    games = 0
    for case in report.cases:
        metadata = case.training.initial_collection.environment
        if (
            metadata.model_dump(exclude={"seed", "batch_size", "player_count", "initial_teams"})
            != canonical
        ):
            raise ValueError("acceptance learning matrix sources or native configuration differ")
        for update in case.training.updates:
            if any(outcome.status not in ("winner", "draw") for outcome in update.outcomes):
                raise ValueError(
                    "acceptance matrix must finish every original game without native limits"
                )
            games += len(update.outcomes)
    if games != 256:
        raise ValueError("acceptance requires 256 original games, excluding replay repetitions")
    return games


class FullGameLocalAcceptance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    scope: Literal["pinned-provisional-full-game-local-training-v33-public-v3"] = (
        "pinned-provisional-full-game-local-training-v33-public-v3"
    )
    sources: tuple[AcceptanceFile, ...]
    source_tree_sha256: Digest
    runtime: AcceptanceRuntime
    evidence: tuple[AcceptanceFile, ...]
    executed_tests: int = Field(gt=0, strict=True)
    learning_cases: Literal[32] = 32
    optimizer_updates: Literal[64] = 64
    original_games: Literal[256] = 256
    repeated_collections: Literal[64] = 64
    artifact_routes: Literal[291] = 291
    held_models: Literal[237] = 237
    full_game_training_ready: Literal[True] = True
    official_fidelity_verified: Literal[False] = False
    live_checkpoint_compatible: Literal[False] = False
    promotion_eligible: Literal[False] = False
    competitive_strength_verified: Literal[False] = False

    @model_validator(mode="after")
    def hashes_and_scope(self) -> FullGameLocalAcceptance:
        if (
            not self.sources
            or tuple(sorted(row.path for row in self.sources))
            != tuple(row.path for row in self.sources)
            or len({row.path for row in self.sources}) != len(self.sources)
            or self.source_tree_sha256
            != canonical_sha256([row.model_dump() for row in self.sources])
            or tuple(row.path for row in self.evidence) != EVIDENCE_FILES
        ):
            raise ValueError("acceptance source/evidence identity differs")
        return self


def _read_evidence(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("acceptance evidence cannot escape through a symlink")
    return path


def verify_full_game_acceptance(
    directory: Path, *, repository_root: Path
) -> FullGameLocalAcceptance:
    """Revalidate actual artifacts and current code/build; parsing JSON alone grants nothing."""
    _require_checkout(repository_root)
    report = FullGameLocalAcceptance.model_validate_json(
        (directory / "acceptance.json").read_text()
    )
    _validate_acceptance(report, directory, repository_root=repository_root)
    return report


def _validate_acceptance(
    report: FullGameLocalAcceptance, directory: Path, *, repository_root: Path
) -> None:
    if report.sources != source_files(repository_root) or report.runtime != acceptance_runtime(
        repository_root
    ):
        raise ValueError("acceptance is stale for the current code, native build or runtime")
    for evidence in report.evidence:
        if file_sha256(_read_evidence(directory, evidence.path)) != evidence.sha256:
            raise ValueError(f"acceptance evidence checksum differs: {evidence.path}")
    audit = FullGameIntegrationAudit.model_validate_json(
        (directory / "integration.json").read_text()
    )
    rebuilt = build_full_game_integration_audit(
        catalog_path=directory / "catalog.json",
        bible_path=directory / "bible.json",
    )
    if audit != rebuilt:
        raise ValueError("acceptance integration ledger differs from the current factory")
    nodes = json.loads((directory / "test-nodes.json").read_text())
    if not isinstance(nodes, list) or any(not isinstance(node, str) for node in nodes):
        raise ValueError("acceptance test-node artifact differs")
    collected = collected_test_nodes((directory / "test-collection.log").read_text())
    if (
        tuple(nodes) != collected
        or verify_junit(directory / "tests.xml", collected) != report.executed_tests
    ):
        raise ValueError("acceptance executed tests differ from collection")
    matrix = FullGameLearningProbeReport.model_validate_json(
        (directory / "learning-probe.json").read_text()
    )
    verify_learning_matrix(matrix, audit)


def run_full_game_acceptance(
    *,
    repository_root: Path,
    output_root: Path,
    catalog_path: Path,
    bible_path: Path,
    seed: int = 1400000,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """Run the reviewed non-browser suite and full learning matrix, then certify exact artifacts."""
    root = repository_root.resolve()
    _require_checkout(root)
    directory = (output_root / str(uuid4())).resolve()
    directory.mkdir(parents=True, exist_ok=False)

    def progress(message: str) -> None:
        if on_progress is not None:
            on_progress(message)

    try:
        before, runtime = source_files(root), acceptance_runtime(root)
        inputs = {"catalog.json": catalog_path.resolve(), "bible.json": bible_path.resolve()}
        input_hashes = {name: file_sha256(path) for name, path in inputs.items()}
        for name, path in inputs.items():
            (directory / name).write_bytes(path.read_bytes())
            if file_sha256(directory / name) != input_hashes[name]:
                raise RuntimeError("source input changed while copying acceptance evidence")
        audit = build_full_game_integration_audit(
            catalog_path=directory / "catalog.json",
            bible_path=directory / "bible.json",
        )
        (directory / "integration.json").write_text(audit.model_dump_json(indent=2))
        base = [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--ignore=tests/test_browser_controls.py",
            "tests",
        ]
        test_environment = {
            key: value
            for key, value in os.environ.items()
            if key not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")
        }
        progress("Collecting exact non-browser test identities")
        with (directory / "test-collection.log").open("w") as output:
            result = subprocess.run(
                [*base, "--collect-only", "-q"],
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
                env=test_environment,
            )
        if result.returncode:
            raise RuntimeError("test collection failed")
        nodes = collected_test_nodes((directory / "test-collection.log").read_text())
        (directory / "test-nodes.json").write_text(json.dumps(nodes, indent=2))
        progress(f"Running {len(nodes)} non-browser tests; output is in {directory / 'tests.log'}")
        with (directory / "tests.log").open("w") as output:
            result = subprocess.run(
                [*base, "-q", f"--junitxml={directory / 'tests.xml'}"],
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=1800,
                check=False,
                env=test_environment,
            )
        if result.returncode:
            raise RuntimeError("non-browser tests failed")
        count = verify_junit(directory / "tests.xml", nodes)
        progress(f"All {count} tests passed; running all 32 roster learning cases")
        matrix = run_full_game_learning_probe(
            catalog_path=directory / "catalog.json",
            bible_path=directory / "bible.json",
            config=FullGameLearningProbeConfig(seed=seed),
            on_case=lambda case: progress(
                f"Learning {case.training.config.player_count} players / {case.layout}: "
                f"{'passed' if case.passed else 'failed'}"
            ),
        )
        (directory / "learning-probe.json").write_text(matrix.model_dump_json(indent=2))
        verify_learning_matrix(matrix, audit)
        if (
            before != source_files(root)
            or runtime != acceptance_runtime(root)
            or any(file_sha256(path) != input_hashes[name] for name, path in inputs.items())
        ):
            raise RuntimeError(
                "code, native build, runtime or source inputs changed during acceptance"
            )
        report = FullGameLocalAcceptance(
            sources=before,
            source_tree_sha256=canonical_sha256([row.model_dump() for row in before]),
            runtime=runtime,
            evidence=tuple(
                AcceptanceFile(path=name, sha256=file_sha256(directory / name))
                for name in EVIDENCE_FILES
            ),
            executed_tests=count,
        )
        _validate_acceptance(report, directory, repository_root=root)
        pending = directory / "acceptance.pending.json"
        pending.write_text(report.model_dump_json(indent=2))
        pending.replace(directory / "acceptance.json")
        progress("Local acceptance verified; official fidelity and live promotion remain blocked")
        return directory
    except BaseException as error:
        (directory / "acceptance.json").unlink(missing_ok=True)
        (directory / "acceptance.pending.json").unlink(missing_ok=True)
        (directory / "failure.json").write_text(
            json.dumps(
                {
                    "full_game_training_ready": False,
                    "reason": f"{type(error).__name__}: {error}",
                    "official_fidelity_verified": False,
                    "promotion_eligible": False,
                },
                indent=2,
            )
        )
        if not isinstance(error, Exception):
            raise
        raise RuntimeError(f"local acceptance failed: {error}; evidence: {directory}") from error
